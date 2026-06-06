"""Authentication, registration, user listing, permissions."""
import os
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel, EmailStr

from core import (
    db, ROLES, hash_password, verify_password,
    create_access_token, create_refresh_token,
    set_auth_cookies, clear_auth_cookies,
    get_current_user, now_iso, new_id, JWT_SECRET, JWT_ALGORITHM, ACCESS_MIN,
    logger,
)
from rbac import permissions_for
import jwt as pyjwt

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class RegisterInput(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "site_engineer"
    department: Optional[str] = None
    phone: Optional[str] = None


class UserOut(BaseModel):
    id: str
    email: EmailStr
    name: str
    role: str
    department: Optional[str] = None
    phone: Optional[str] = None
    created_at: str


@router.post("/login")
async def login(payload: LoginInput, request: Request, response: Response):
    email = payload.email.lower().strip()
    ip = request.client.host if request.client else "unknown"
    identifier = f"{ip}:{email}"

    attempts_doc = await db.login_attempts.find_one({"identifier": identifier})
    if attempts_doc and attempts_doc.get("count", 0) >= 5:
        locked_until = attempts_doc.get("locked_until")
        if locked_until and datetime.fromisoformat(locked_until) > datetime.now(timezone.utc):
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in 15 minutes.")

    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {"$inc": {"count": 1}, "$set": {"locked_until": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}},
            upsert=True,
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Reject inactive / disabled accounts.
    if user.get("active") is False:
        raise HTTPException(status_code=403, detail="Account is disabled. Contact your administrator.")

    await db.login_attempts.delete_one({"identifier": identifier})
    access = create_access_token(user["id"], user["email"], user["role"])
    refresh = create_refresh_token(user["id"])
    set_auth_cookies(response, access, refresh)
    # Stamp last_login on the user doc
    try:
        await db.users.update_one({"id": user["id"]},
                                  {"$set": {"last_login": now_iso(),
                                            "last_login_ip": ip}})
    except Exception:
        pass
    user.pop("_id", None)
    user.pop("password_hash", None)
    # Record login activity for the session monitor (best-effort).
    try:
        from audit import audit as _audit
        await db.login_activity.insert_one({
            "id": new_id(),
            "user_id": user["id"],
            "email": user["email"],
            "name": user.get("name"),
            "role": user.get("role"),
            "ip": ip,
            "user_agent": request.headers.get("user-agent", "")[:240],
            "at": now_iso(),
        })
        await _audit(user=user, action="login", resource="auth", record_id=user["id"], ip=ip)
    except Exception as _e:
        logger.warning(f"login activity capture failed: {_e}")
    return user


@router.post("/logout")
async def logout(response: Response, _user: dict = Depends(get_current_user)):
    clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user)):
    return UserOut(**user)


@router.post("/refresh")
async def refresh_token(request: Request, response: Response):
    rt = request.cookies.get("refresh_token")
    if not rt:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = pyjwt.decode(rt, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        access = create_access_token(user["id"], user["email"], user["role"])
        response.set_cookie("access_token", access, httponly=True, secure=True, samesite="none", max_age=ACCESS_MIN * 60, path="/")
        return {"ok": True}
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@router.post("/register", response_model=UserOut)
async def register(payload: RegisterInput, user: dict = Depends(get_current_user)):
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super_admin can register users")
    email = payload.email.lower().strip()
    if payload.role not in ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Allowed: {ROLES}")
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    doc = {
        "id": new_id(),
        "email": email,
        "name": payload.name,
        "role": payload.role,
        "department": payload.department,
        "phone": payload.phone,
        "password_hash": hash_password(payload.password),
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    doc.pop("_id", None)
    doc.pop("password_hash", None)
    return UserOut(**doc)


@router.get("/users", response_model=List[UserOut])
async def list_users(user: dict = Depends(get_current_user)):
    rows = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)
    return [UserOut(**r) for r in rows]


@router.get("/permissions")
async def my_permissions(user: dict = Depends(get_current_user)):
    return permissions_for(user.get("role"))
