"""Access Preview — super_admin impersonation ("view as user").

Start: issues the target user's access token (with impersonator claims) as the
session cookie and stashes the admin's own token in `imp_return_token` so the
admin can exit preview instantly. Stop: restores the admin session.
Every start/stop is audit-logged; actions taken while previewing carry the
impersonator stamp in audit rows (see audit.py).
"""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
import jwt as pyjwt

from core import (
    db, get_current_user, now_iso,
    JWT_SECRET, JWT_ALGORITHM, ACCESS_MIN, create_access_token,
)
from audit import audit

router = APIRouter(prefix="/admin/impersonation", tags=["impersonation"])

_COOKIE_KW = dict(httponly=True, secure=True, samesite="lax", path="/")


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/start/{user_id}")
async def start_preview(user_id: str, request: Request, response: Response,
                        user: dict = Depends(get_current_user)):
    if user.get("impersonated"):
        raise HTTPException(400, "Already in preview mode — exit the current preview first")
    if user.get("role") != "super_admin":
        raise HTTPException(403, "Only Super Admin can preview as another user")
    target = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not target:
        raise HTTPException(404, "User not found")
    if target["id"] == user["id"]:
        raise HTTPException(400, "You are already logged in as this user")
    if target.get("role") == "super_admin":
        raise HTTPException(403, "Cannot preview as another Super Admin")
    if target.get("active") is False:
        raise HTTPException(400, "Cannot preview as a deactivated user")

    payload = {
        "sub": target["id"], "email": target["email"], "role": target["role"],
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_MIN),
        "type": "access",
        "imp": user["id"], "imp_name": user.get("name") or user.get("email"),
    }
    preview_token = pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    admin_token = request.cookies.get("access_token") or \
        create_access_token(user["id"], user["email"], user["role"])
    response.set_cookie("access_token", preview_token, max_age=ACCESS_MIN * 60, **_COOKIE_KW)
    response.set_cookie("imp_return_token", admin_token, max_age=ACCESS_MIN * 60, **_COOKIE_KW)
    await audit(user=user, action="impersonation_start", resource="users", record_id=target["id"],
                after={"viewing_as": target["email"], "role": target["role"]}, ip=_ip(request))
    return {"ok": True, "viewing_as": {"id": target["id"], "name": target.get("name"),
                                       "email": target["email"], "role": target["role"]}}


@router.post("/stop")
async def stop_preview(request: Request, response: Response,
                       user: dict = Depends(get_current_user)):
    rt = request.cookies.get("imp_return_token")
    if not rt:
        raise HTTPException(400, "Not in preview mode")
    try:
        payload = pyjwt.decode(rt, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(401, "Invalid return token")
    except pyjwt.InvalidTokenError:
        raise HTTPException(401, "Preview session expired — please log in again")
    admin = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not admin or admin.get("role") != "super_admin" or admin.get("active") is False:
        raise HTTPException(403, "Return account is no longer a valid Super Admin")
    response.set_cookie("access_token", rt, max_age=ACCESS_MIN * 60, **_COOKIE_KW)
    response.delete_cookie("imp_return_token", path="/")
    await audit(user=admin, action="impersonation_stop", resource="users", record_id=user.get("id"),
                after={"was_viewing_as": user.get("email")}, ip=_ip(request))
    return {"ok": True, "restored": {"id": admin["id"], "name": admin.get("name"), "email": admin["email"]}}
