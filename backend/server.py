"""Corporate ERP - FastAPI backend.

Auth (JWT cookies + bcrypt), RBAC roles, MongoDB via Motor, and CRUD endpoints
for 14 ERP modules plus dashboard aggregation + sample data seeding.
"""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import io
import uuid
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Any, Dict

import bcrypt
import jwt
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr

from rbac import PERMISSIONS, can, permissions_for
from approval_engine import build_chain, apply_action, APPROVAL_CHAINS
from exports import to_excel, to_pdf, COLUMNS as EXPORT_COLUMNS

# ---------- Config ----------
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
ACCESS_MIN = 60 * 8  # 8h
REFRESH_DAYS = 7

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("erp")

app = FastAPI(title="Corporate ERP API")
api = APIRouter(prefix="/api")

# ---------- Helpers ----------
ROLES = [
    "super_admin", "director", "general_manager", "dept_head", "project_manager",
    "site_engineer", "supervisor", "store_incharge", "accounts_executive",
    "hr_executive", "safety_officer", "purchase_officer", "client_rep", "vendor",
]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


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
    response.set_cookie("access_token", access, httponly=True, secure=True, samesite="none", max_age=ACCESS_MIN * 60, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=True, samesite="none", max_age=REFRESH_DAYS * 86400, path="/")


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


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
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_roles(*roles: str):
    async def dep(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles and "super_admin" not in roles:
            # super_admin always allowed
            if user.get("role") != "super_admin":
                raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return dep


def require_permission(resource: str, action: str):
    """Dependency factory enforcing per-resource RBAC. action ∈ {read, write, delete}."""
    async def dep(user: dict = Depends(get_current_user)) -> dict:
        if not can(user.get("role"), resource, action):
            raise HTTPException(status_code=403, detail=f"Forbidden: '{user.get('role')}' cannot {action} {resource}")
        return user
    return dep


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


# ---------- Models ----------
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


# ---------- Auth Endpoints ----------
@api.post("/auth/login")
async def login(payload: LoginInput, request: Request, response: Response):
    email = payload.email.lower().strip()
    ip = request.client.host if request.client else "unknown"
    identifier = f"{ip}:{email}"

    # brute force
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

    await db.login_attempts.delete_one({"identifier": identifier})
    access = create_access_token(user["id"], user["email"], user["role"])
    refresh = create_refresh_token(user["id"])
    set_auth_cookies(response, access, refresh)
    user.pop("_id", None)
    user.pop("password_hash", None)
    return user


@api.post("/auth/logout")
async def logout(response: Response, _user: dict = Depends(get_current_user)):
    clear_auth_cookies(response)
    return {"ok": True}


@api.get("/auth/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user)):
    return UserOut(**user)


@api.post("/auth/refresh")
async def refresh_token(request: Request, response: Response):
    rt = request.cookies.get("refresh_token")
    if not rt:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(rt, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        access = create_access_token(user["id"], user["email"], user["role"])
        response.set_cookie("access_token", access, httponly=True, secure=True, samesite="none", max_age=ACCESS_MIN * 60, path="/")
        return {"ok": True}
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@api.post("/auth/register", response_model=UserOut)
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


@api.get("/auth/users", response_model=List[UserOut])
async def list_users(user: dict = Depends(get_current_user)):
    rows = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)
    return [UserOut(**r) for r in rows]


# ---------- Generic CRUD factory (RBAC-aware) ----------
def make_crud(resource: str, collection: str, perm_key: str | None = None):
    """`resource` is URL slug, `collection` is Mongo collection, `perm_key` maps to PERMISSIONS."""
    perm = perm_key or collection

    @api.get(f"/{resource}")
    async def list_items(user: dict = Depends(require_permission(perm, "read"))):
        rows = await db[collection].find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
        return rows

    @api.post(f"/{resource}")
    async def create_item(payload: Dict[str, Any], user: dict = Depends(require_permission(perm, "write"))):
        doc = dict(payload)
        doc["id"] = new_id()
        doc["created_at"] = now_iso()
        doc["created_by"] = user["id"]
        # Auto-attach approval chain when creating an approval request
        if perm == "approvals" and not doc.get("chain"):
            doc["chain"] = build_chain(doc.get("type") or "expense")
            doc["current_step"] = 0
            doc["history"] = []
            doc["status"] = doc.get("status") or "pending"
        await db[collection].insert_one(doc)
        doc.pop("_id", None)
        return doc

    @api.get(f"/{resource}/{{item_id}}")
    async def get_item(item_id: str, user: dict = Depends(require_permission(perm, "read"))):
        row = await db[collection].find_one({"id": item_id}, {"_id": 0})
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        return row

    @api.put(f"/{resource}/{{item_id}}")
    async def update_item(item_id: str, payload: Dict[str, Any], user: dict = Depends(require_permission(perm, "write"))):
        payload.pop("id", None)
        payload["updated_at"] = now_iso()
        payload["updated_by"] = user["id"]
        result = await db[collection].update_one({"id": item_id}, {"$set": payload})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Not found")
        row = await db[collection].find_one({"id": item_id}, {"_id": 0})
        return row

    @api.delete(f"/{resource}/{{item_id}}")
    async def delete_item(item_id: str, user: dict = Depends(require_permission(perm, "delete"))):
        result = await db[collection].delete_one({"id": item_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Not found")
        return {"ok": True}


# ---------- Approval workflow endpoints ----------
class ApprovalAction(BaseModel):
    action: str  # approve | reject | comment
    comment: Optional[str] = None


@api.post("/approvals/{approval_id}/action")
async def approval_action(approval_id: str, payload: ApprovalAction, user: dict = Depends(get_current_user)):
    approval = await db.approvals.find_one({"id": approval_id}, {"_id": 0})
    if not approval:
        raise HTTPException(status_code=404, detail="Not found")
    if not approval.get("chain"):
        approval["chain"] = build_chain(approval.get("type") or "expense")
        approval["current_step"] = 0
        approval["history"] = []
    try:
        updated = apply_action(approval, payload.action, user, payload.comment)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.approvals.update_one(
        {"id": approval_id},
        {"$set": {
            "chain": updated["chain"],
            "current_step": updated["current_step"],
            "history": updated["history"],
            "status": updated["status"],
            "updated_at": updated["updated_at"],
        }},
    )
    return updated


@api.get("/approvals-config/chains")
async def approval_chains(user: dict = Depends(get_current_user)):
    return APPROVAL_CHAINS


# ---------- Export endpoints (Excel + PDF) ----------
_EXPORT_RESOURCE_MAP = {
    "clients": "clients", "vendors": "vendors", "employees": "employees",
    "attendance": "attendance", "projects": "projects", "inventory": "inventory",
    "purchase-orders": "purchase_orders", "quotations": "quotations",
    "journal-entries": "journal_entries", "safety-reports": "safety_reports",
    "assets": "assets", "payroll": "payroll", "vehicles": "vehicles",
    "documents": "documents", "approvals": "approvals",
}


@api.get("/export/{resource}.{fmt}")
async def export_resource(resource: str, fmt: str, user: dict = Depends(get_current_user)):
    if resource not in _EXPORT_RESOURCE_MAP:
        raise HTTPException(status_code=404, detail="Unknown resource")
    perm_key = _EXPORT_RESOURCE_MAP[resource]
    if not can(user.get("role"), perm_key, "read"):
        raise HTTPException(status_code=403, detail=f"Forbidden: cannot read {perm_key}")
    if fmt not in ("xlsx", "pdf"):
        raise HTTPException(status_code=400, detail="Format must be xlsx or pdf")

    rows = await db[perm_key].find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    fname = f"{perm_key}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.{fmt}"
    if fmt == "xlsx":
        data = to_excel(perm_key, rows)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        data = to_pdf(perm_key, rows)
        media = "application/pdf"
    return StreamingResponse(io.BytesIO(data), media_type=media, headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@api.get("/auth/permissions")
async def my_permissions(user: dict = Depends(get_current_user)):
    return permissions_for(user.get("role"))


# Register CRUD modules
MODULES = [
    ("clients", "clients"),
    ("vendors", "vendors"),
    ("employees", "employees"),
    ("attendance", "attendance"),
    ("projects", "projects"),
    ("inventory", "inventory"),
    ("purchase-orders", "purchase_orders"),
    ("quotations", "quotations"),
    ("journal-entries", "journal_entries"),
    ("safety-reports", "safety_reports"),
    ("assets", "assets"),
    ("payroll", "payroll"),
    ("vehicles", "vehicles"),
    ("documents", "documents"),
    ("approvals", "approvals"),
]
for r, c in MODULES:
    make_crud(r, c)


# ---------- Dashboard aggregation ----------
@api.get("/dashboard/summary")
async def dashboard_summary(user: dict = Depends(get_current_user)):
    async def count(col):
        return await db[col].count_documents({})

    clients = await count("clients")
    vendors = await count("vendors")
    employees = await count("employees")
    projects_total = await count("projects")
    projects_active = await db.projects.count_documents({"status": "active"})
    inventory_items = await count("inventory")
    low_stock = await db.inventory.count_documents({"$expr": {"$lt": ["$quantity", "$min_stock"]}})
    pending_pos = await db.purchase_orders.count_documents({"status": {"$in": ["pending", "draft"]}})
    open_quotations = await db.quotations.count_documents({"status": {"$in": ["sent", "draft"]}})
    safety_open = await db.safety_reports.count_documents({"status": {"$ne": "closed"}})
    pending_approvals = await db.approvals.count_documents({"status": "pending"})

    # Revenue & expenses from journal_entries (type: revenue/expense, amount)
    pipeline = [
        {"$group": {"_id": "$type", "total": {"$sum": "$amount"}}}
    ]
    sums = {d["_id"]: d["total"] async for d in db.journal_entries.aggregate(pipeline)}
    revenue = float(sums.get("revenue", 0) or 0)
    expenses = float(sums.get("expense", 0) or 0)
    profit = revenue - expenses

    # Receivables (invoices unpaid) — from quotations with status invoiced
    receivables_cursor = db.quotations.find({"status": "invoiced"}, {"_id": 0, "total": 1})
    receivables = 0.0
    async for r in receivables_cursor:
        receivables += float(r.get("total", 0) or 0)

    payables_cursor = db.purchase_orders.find({"status": {"$in": ["approved", "received"]}, "paid": {"$ne": True}}, {"_id": 0, "total": 1})
    payables = 0.0
    async for p in payables_cursor:
        payables += float(p.get("total", 0) or 0)

    # Monthly revenue/expense for last 6 months
    months = []
    now = datetime.now(timezone.utc)
    for i in range(5, -1, -1):
        m = (now.replace(day=1) - timedelta(days=30 * i))
        months.append(m.strftime("%Y-%m"))

    monthly = {m: {"revenue": 0.0, "expense": 0.0} for m in months}
    async for e in db.journal_entries.find({}, {"_id": 0, "type": 1, "amount": 1, "date": 1}):
        d = e.get("date") or ""
        m = d[:7] if isinstance(d, str) else ""
        if m in monthly and e.get("type") in ("revenue", "expense"):
            monthly[m][e["type"]] += float(e.get("amount") or 0)

    chart_revenue_expense = [
        {"month": m, "revenue": round(v["revenue"], 2), "expense": round(v["expense"], 2)}
        for m, v in monthly.items()
    ]

    # Project status breakdown
    proj_pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    project_status = [{"status": d["_id"] or "unknown", "count": d["count"]} async for d in db.projects.aggregate(proj_pipeline)]

    # Attendance today
    today = now.strftime("%Y-%m-%d")
    present = await db.attendance.count_documents({"date": today, "status": "present"})
    absent = await db.attendance.count_documents({"date": today, "status": "absent"})

    # Safety stats by severity
    sev_pipeline = [{"$group": {"_id": "$severity", "count": {"$sum": 1}}}]
    safety_by_severity = [{"severity": d["_id"] or "low", "count": d["count"]} async for d in db.safety_reports.aggregate(sev_pipeline)]

    return {
        "kpis": {
            "revenue": round(revenue, 2),
            "expenses": round(expenses, 2),
            "profit": round(profit, 2),
            "receivables": round(receivables, 2),
            "payables": round(payables, 2),
            "active_projects": projects_active,
            "total_projects": projects_total,
            "employees": employees,
            "clients": clients,
            "vendors": vendors,
            "inventory_items": inventory_items,
            "low_stock_alerts": low_stock,
            "pending_purchase_orders": pending_pos,
            "open_quotations": open_quotations,
            "open_safety_incidents": safety_open,
            "pending_approvals": pending_approvals,
            "attendance_today_present": present,
            "attendance_today_absent": absent,
        },
        "chart_revenue_expense": chart_revenue_expense,
        "project_status": project_status,
        "safety_by_severity": safety_by_severity,
    }


@api.get("/")
async def root():
    return {"service": "Corporate ERP API", "version": "1.0.0"}


# ---------- Startup: indexes, admin seed, sample data ----------
async def seed_admin():
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@erp.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "id": new_id(),
            "email": admin_email,
            "name": "Super Admin",
            "role": "super_admin",
            "department": "Executive",
            "phone": "+1-000-0000",
            "password_hash": hash_password(admin_password),
            "created_at": now_iso(),
        })
        logger.info(f"Seeded admin user: {admin_email}")
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})
        logger.info(f"Updated admin password for {admin_email}")


async def seed_sample_data():
    # Only seed if clients collection is empty (idempotent on first run)
    if await db.clients.count_documents({}) > 0:
        return

    admin = await db.users.find_one({"role": "super_admin"}, {"_id": 0, "id": 1})
    creator = admin["id"] if admin else "system"

    def _doc(**fields):
        return {"id": new_id(), "created_at": now_iso(), "created_by": creator, **fields}

    clients = [
        _doc(name="Reliance Industries", code="CL-001", contact="Rajesh Sharma", email="rajesh@reliance.in", phone="+91-9810000001", gst="27AAACR5055K1Z5", address="Mumbai, MH", credit_limit=5000000, status="active"),
        _doc(name="Tata Steel", code="CL-002", contact="Anita Verma", email="anita@tata.in", phone="+91-9810000002", gst="20AAACT2727Q1ZZ", address="Jamshedpur, JH", credit_limit=8000000, status="active"),
        _doc(name="Adani Power", code="CL-003", contact="Vikram Singh", email="vikram@adani.in", phone="+91-9810000003", gst="24AAACA4502R1ZZ", address="Mundra, GJ", credit_limit=6000000, status="active"),
        _doc(name="ONGC", code="CL-004", contact="Suresh Kumar", email="suresh@ongc.co.in", phone="+91-9810000004", gst="07AAACO1598A1ZZ", address="Dehradun, UK", credit_limit=10000000, status="active"),
    ]
    await db.clients.insert_many(clients)

    vendors = [
        _doc(name="SteelTech Supplies", code="VN-001", category="material", contact="Manoj Patel", email="manoj@steeltech.in", phone="+91-9820000001", gst="27AAACS0001A1ZZ", rating=4.5, status="approved"),
        _doc(name="SafetyFirst Equip", code="VN-002", category="ppe", contact="Priya Mehta", email="priya@safetyfirst.in", phone="+91-9820000002", gst="27AAACS0002B1ZZ", rating=4.2, status="approved"),
        _doc(name="PaintMaster Co", code="VN-003", category="paint", contact="Amit Desai", email="amit@paintmaster.in", phone="+91-9820000003", gst="27AAACS0003C1ZZ", rating=4.7, status="approved"),
        _doc(name="RopeAccess Gear", code="VN-004", category="rope_access", contact="Ravi Kapoor", email="ravi@ropegear.in", phone="+91-9820000004", gst="27AAACS0004D1ZZ", rating=4.3, status="pending"),
    ]
    await db.vendors.insert_many(vendors)

    employees = [
        _doc(emp_code="E-1001", name="Arjun Reddy", role="project_manager", department="Operations", phone="+91-9830000001", email="arjun@company.in", joining_date="2022-04-01", salary=120000, status="active"),
        _doc(emp_code="E-1002", name="Sneha Iyer", role="site_engineer", department="Operations", phone="+91-9830000002", email="sneha@company.in", joining_date="2023-01-15", salary=75000, status="active"),
        _doc(emp_code="E-1003", name="Karan Malhotra", role="safety_officer", department="HSE", phone="+91-9830000003", email="karan@company.in", joining_date="2021-08-20", salary=85000, status="active"),
        _doc(emp_code="E-1004", name="Deepa Nair", role="accounts_executive", department="Finance", phone="+91-9830000004", email="deepa@company.in", joining_date="2020-06-10", salary=65000, status="active"),
        _doc(emp_code="E-1005", name="Rohit Sharma", role="supervisor", department="Scaffolding", phone="+91-9830000005", email="rohit@company.in", joining_date="2022-11-05", salary=55000, status="active"),
        _doc(emp_code="E-1006", name="Mohan Lal", role="store_incharge", department="Stores", phone="+91-9830000006", email="mohan@company.in", joining_date="2019-03-12", salary=48000, status="active"),
    ]
    await db.employees.insert_many(employees)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    attendance = []
    for i, e in enumerate(employees):
        attendance.append(_doc(employee_id=e["id"], employee_name=e["name"], date=today, status="present" if i < 5 else "absent", check_in="09:00", check_out="18:00", hours=9))
    await db.attendance.insert_many(attendance)

    projects = [
        _doc(code="PRJ-2025-01", name="Reliance Jamnagar Scaffolding", client=clients[0]["name"], type="scaffolding", site="Jamnagar, GJ", manager="Arjun Reddy", start_date="2025-11-01", end_date="2026-04-30", budget=12500000, status="active", progress=42),
        _doc(code="PRJ-2025-02", name="Tata Steel Rope Access Inspection", client=clients[1]["name"], type="rope_access", site="Jamshedpur, JH", manager="Arjun Reddy", start_date="2025-12-10", end_date="2026-02-28", budget=4500000, status="active", progress=68),
        _doc(code="PRJ-2025-03", name="Adani Painting Works", client=clients[2]["name"], type="painting", site="Mundra, GJ", manager="Sneha Iyer", start_date="2025-09-15", end_date="2026-01-30", budget=6800000, status="active", progress=85),
        _doc(code="PRJ-2024-09", name="ONGC Roof Sheeting", client=clients[3]["name"], type="roof_sheeting", site="Mumbai High, MH", manager="Sneha Iyer", start_date="2024-08-01", end_date="2025-12-15", budget=8200000, status="completed", progress=100),
        _doc(code="PRJ-2026-01", name="Reliance Shutdown Maintenance", client=clients[0]["name"], type="shutdown", site="Hazira, GJ", manager="Arjun Reddy", start_date="2026-03-01", end_date="2026-05-30", budget=22000000, status="planned", progress=0),
    ]
    await db.projects.insert_many(projects)

    inventory = [
        _doc(code="INV-S001", name="Steel Pipe 48mm", category="scaffolding", uom="meter", quantity=2400, min_stock=500, rate=180, location="Warehouse A"),
        _doc(code="INV-S002", name="Cuplock Standard 2m", category="scaffolding", uom="nos", quantity=320, min_stock=400, rate=950, location="Warehouse A"),
        _doc(code="INV-P001", name="Industrial Paint - Grey 20L", category="painting", uom="can", quantity=85, min_stock=30, rate=4200, location="Warehouse B"),
        _doc(code="INV-R001", name="Rope Access Harness", category="rope_access", uom="nos", quantity=42, min_stock=20, rate=8500, location="Warehouse C"),
        _doc(code="INV-PPE001", name="Safety Helmet Class A", category="ppe", uom="nos", quantity=210, min_stock=100, rate=450, location="Warehouse C"),
        _doc(code="INV-PPE002", name="Safety Harness Full Body", category="ppe", uom="nos", quantity=18, min_stock=50, rate=3200, location="Warehouse C"),
        _doc(code="INV-RS001", name="GI Roof Sheet 0.5mm", category="roof_sheeting", uom="sqm", quantity=4500, min_stock=1000, rate=620, location="Warehouse D"),
    ]
    await db.inventory.insert_many(inventory)

    purchase_orders = [
        _doc(po_number="PO-2026-001", vendor=vendors[0]["name"], project=projects[0]["name"], date="2026-01-12", total=485000, status="approved", paid=False, items=[{"name": "Steel Pipe 48mm", "qty": 1000, "rate": 180, "amount": 180000}, {"name": "Cuplock Standard", "qty": 200, "rate": 950, "amount": 190000}]),
        _doc(po_number="PO-2026-002", vendor=vendors[1]["name"], project=projects[1]["name"], date="2026-01-20", total=128000, status="pending", paid=False, items=[{"name": "Safety Harness", "qty": 30, "rate": 3200, "amount": 96000}]),
        _doc(po_number="PO-2026-003", vendor=vendors[2]["name"], project=projects[2]["name"], date="2026-02-01", total=315000, status="approved", paid=True, items=[{"name": "Industrial Paint Grey 20L", "qty": 60, "rate": 4200, "amount": 252000}]),
        _doc(po_number="PO-2026-004", vendor=vendors[3]["name"], project=projects[1]["name"], date="2026-02-05", total=72000, status="draft", paid=False, items=[]),
    ]
    await db.purchase_orders.insert_many(purchase_orders)

    quotations = [
        _doc(quote_number="QT-2026-001", client=clients[0]["name"], project="Hazira Maintenance", date="2026-01-25", valid_until="2026-02-25", total=1850000, status="sent", items=[{"desc": "Scaffolding Erection", "qty": 1, "rate": 1850000, "amount": 1850000}]),
        _doc(quote_number="QT-2026-002", client=clients[1]["name"], project="Plant 2 Inspection", date="2026-02-02", valid_until="2026-03-02", total=620000, status="invoiced", items=[{"desc": "Rope Access Inspection", "qty": 1, "rate": 620000, "amount": 620000}]),
        _doc(quote_number="QT-2026-003", client=clients[2]["name"], project="External Painting Q2", date="2026-02-08", valid_until="2026-03-08", total=1240000, status="draft", items=[]),
    ]
    await db.quotations.insert_many(quotations)

    # Journal entries — last 6 months revenue & expense
    je_rows = []
    base = datetime.now(timezone.utc).replace(day=15)
    rev_amounts = [3200000, 4100000, 3800000, 5200000, 4600000, 5800000]
    exp_amounts = [2100000, 2400000, 2300000, 3100000, 2800000, 3400000]
    for i in range(6):
        d = (base - timedelta(days=30 * (5 - i))).strftime("%Y-%m-%d")
        je_rows.append(_doc(je_number=f"JE-{i+1:04d}", date=d, type="revenue", account="Project Revenue", amount=rev_amounts[i], narration="Client billing", cost_centre="Operations"))
        je_rows.append(_doc(je_number=f"JE-E{i+1:04d}", date=d, type="expense", account="Materials & Labor", amount=exp_amounts[i], narration="Operational expenses", cost_centre="Operations"))
    await db.journal_entries.insert_many(je_rows)

    safety_reports = [
        _doc(report_id="SR-001", date="2026-02-04", project=projects[0]["name"], type="near_miss", severity="medium", description="Tool dropped from height-3 platform; barricade intact", reporter="Karan Malhotra", status="open"),
        _doc(report_id="SR-002", date="2026-02-08", project=projects[1]["name"], type="observation", severity="low", description="PPE compliance reminder for new crew", reporter="Karan Malhotra", status="closed"),
        _doc(report_id="SR-003", date="2026-02-10", project=projects[2]["name"], type="incident", severity="high", description="Minor injury — finger pinch during scaffold dismantle", reporter="Rohit Sharma", status="under_review"),
    ]
    await db.safety_reports.insert_many(safety_reports)

    assets = [
        _doc(asset_id="AST-001", name="Scissor Lift 12m", category="equipment", purchase_date="2022-05-10", cost=2850000, location="Yard 1", assigned_to=projects[0]["name"], status="in_use", depreciation_rate=15),
        _doc(asset_id="AST-002", name="Air Compressor 7HP", category="equipment", purchase_date="2023-02-18", cost=185000, location="Yard 2", assigned_to=projects[2]["name"], status="in_use", depreciation_rate=20),
        _doc(asset_id="AST-003", name="Welding Machine Inverter", category="equipment", purchase_date="2024-08-22", cost=78000, location="Stores", assigned_to=None, status="available", depreciation_rate=20),
    ]
    await db.assets.insert_many(assets)

    payroll = []
    pay_month = datetime.now(timezone.utc).strftime("%Y-%m")
    for e in employees:
        gross = e["salary"]
        deductions = round(gross * 0.12, 2)
        net = round(gross - deductions, 2)
        payroll.append(_doc(employee_id=e["id"], employee_name=e["name"], month=pay_month, gross=gross, deductions=deductions, net=net, status="processed"))
    await db.payroll.insert_many(payroll)

    vehicles = [
        _doc(reg_number="MH-12-AB-1234", type="truck", capacity="5T", driver="Suresh Yadav", status="active", last_service="2026-01-15", fuel_avg=4.2),
        _doc(reg_number="MH-04-CD-5678", type="pickup", capacity="1T", driver="Ramesh Kumar", status="active", last_service="2026-02-01", fuel_avg=9.8),
        _doc(reg_number="GJ-01-EF-9012", type="crane", capacity="20T", driver="Sanjay Patil", status="maintenance", last_service="2026-02-08", fuel_avg=2.1),
    ]
    await db.vehicles.insert_many(vehicles)

    documents = [
        _doc(doc_id="DOC-001", title="Master Service Agreement - Reliance", category="contract", project=projects[0]["name"], uploaded_by="Admin", expiry="2027-03-31", version="1.0"),
        _doc(doc_id="DOC-002", title="ISO 45001 Certification", category="certification", project=None, uploaded_by="Admin", expiry="2026-09-30", version="2.0"),
        _doc(doc_id="DOC-003", title="Scaffold Design Drawings - Jamnagar", category="drawing", project=projects[0]["name"], uploaded_by="Arjun Reddy", expiry=None, version="3.2"),
    ]
    await db.documents.insert_many(documents)

    approvals = [
        _doc(title="PO-2026-002 Approval", type="purchase_order", reference="PO-2026-002", amount=128000, requested_by="Rohit Sharma", chain=build_chain("purchase_order"), current_step=0, history=[], status="pending"),
        _doc(title="Leave Request - Sneha Iyer", type="leave", reference="LV-2026-008", amount=0, requested_by="Sneha Iyer", chain=build_chain("leave"), current_step=0, history=[], status="pending"),
        _doc(title="Capex - New Welding Machine", type="capex", reference="CAP-2026-001", amount=92000, requested_by="Mohan Lal", chain=build_chain("capex"), current_step=0, history=[], status="pending"),
    ]
    await db.approvals.insert_many(approvals)

    logger.info("Seeded sample ERP data.")


async def migrate_approvals_chain():
    """Backfill chain/history/current_step on legacy approval docs that lack them."""
    async for doc in db.approvals.find({"chain": {"$exists": False}}, {"_id": 0, "id": 1, "type": 1}):
        await db.approvals.update_one(
            {"id": doc["id"]},
            {"$set": {
                "chain": build_chain(doc.get("type") or "expense"),
                "current_step": 0,
                "history": [],
            }},
        )


@app.on_event("startup")
async def on_startup():
    try:
        await db.users.create_index("email", unique=True)
        await db.login_attempts.create_index("identifier")
        for _, c in MODULES:
            await db[c].create_index("id", unique=True)
        await seed_admin()
        await seed_sample_data()
        await migrate_approvals_chain()
        logger.info("ERP backend started successfully.")
    except Exception as e:
        logger.exception(f"Startup error: {e}")


@app.on_event("shutdown")
async def on_shutdown():
    client.close()


app.include_router(api)

# CORS — allow credentials means we need explicit origins, but ingress proxies
# the same origin. We allow any origin via regex for dev preview environments.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
