"""Shared core: env, MongoDB client, JWT/auth utilities, helpers."""
import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt
import jwt
from fastapi import HTTPException, Request, Response, Depends
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("erp")

# ---------- env ----------
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
ACCESS_MIN = 60 * 8  # 8h
REFRESH_DAYS = 7

# ---------- mongo ----------
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]


# ---------- helpers ----------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    """Current time in IST — for user-facing stamps on PDFs / Excel exports."""
    return datetime.now(IST)


def fmt_ist(value=None, fmt: str = "%d %b %Y · %I:%M %p IST") -> str:
    """Render a UTC ISO string (or datetime / now) as an IST display stamp."""
    if value is None:
        dt = now_ist()
    else:
        dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(IST)
    return dt.strftime(fmt).replace(" 0", " ")


def new_id() -> str:
    return str(uuid.uuid4())


def user_display_name(user: dict) -> str:
    return (user or {}).get("name") or (user or {}).get("email") or "—"


async def attach_user_names(rows, fields=("created_by", "updated_by")):
    """Add `<field>_name` for user-id audit fields (resolved from users; non-id strings kept as-is)."""
    items = rows if isinstance(rows, list) else [rows]
    ids = {r.get(f) for r in items for f in fields if r.get(f) and not r.get(f"{f}_name")}
    if not ids:
        return rows
    users = await db.users.find({"id": {"$in": list(ids)}}, {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(len(ids))
    names = {u["id"]: user_display_name(u) for u in users}
    for r in items:
        for f in fields:
            v = r.get(f)
            if v and not r.get(f"{f}_name"):
                r[f"{f}_name"] = names.get(v) or ("Unknown user" if len(str(v)) == 36 and str(v).count("-") == 4 else str(v))
    return rows


# ---------- password hashing ----------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ---------- jwt ----------
def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id, "email": email, "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_MIN),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_DAYS),
        "type": "refresh",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    response.set_cookie("access_token", access, httponly=True, secure=True, samesite="lax", max_age=ACCESS_MIN * 60, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=True, samesite="lax", max_age=REFRESH_DAYS * 86400, path="/")


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


# ---------- auth deps ----------
async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        if payload.get("imp"):
            user["impersonated"] = True
            user["impersonator_id"] = payload["imp"]
            user["impersonator_name"] = payload.get("imp_name")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_permission(resource: str, action: str):
    """Dependency factory enforcing per-resource RBAC. action ∈ {read, write, delete}."""
    from rbac import can

    async def dep(user: dict = Depends(get_current_user)) -> dict:
        if not can(user.get("role"), resource, action):
            raise HTTPException(status_code=403, detail=f"Forbidden: '{user.get('role')}' cannot {action} {resource}")
        return user

    return dep


ROLES = [
    "super_admin", "director", "general_manager", "dept_head", "project_manager",
    "site_engineer", "supervisor", "store_incharge", "accounts_executive",
    "hr_executive", "safety_officer", "purchase_officer", "sales_executive", "client_rep", "vendor",
]
