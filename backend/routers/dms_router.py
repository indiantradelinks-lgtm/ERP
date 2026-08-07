"""DMS · Central Document Management System (prefix /dms).

Storage strategy — fast + ERP load-free:
  1. Upload lands in Emergent object storage instantly (works at low bandwidth).
  2. File is queued to the existing OneDrive push worker (background sync,
     folder: ERP-Documents/<Module>/<Project|General>/<Category>).
  3. Downloads stream from object storage; OneDrive webUrl exposed once synced.

Collections: dms_categories, dms_documents (versions embedded), reuses db.files
and db.onedrive_queue. Approval: categories flagged requires_approval create a
central approval (type "document"); effective doc status is computed live.
"""
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, Depends, Request, UploadFile, File, Form
from pydantic import BaseModel

from core import db, require_permission, now_iso, new_id
from audit import audit
from sequences import next_sequence
from approval_engine import build_chain, insert_approval
from scope import apply_project_scope
from storage import put_object, MAX_BYTES

router = APIRouter(prefix="/dms", tags=["dms"])

MODULES = {"projects": "Projects", "hr": "HR", "safety": "Safety", "procurement": "Procurement",
           "accounts": "Accounts", "logistics": "Logistics", "company": "Company"}

DEFAULT_CATEGORIES = [
    ("Contracts", True), ("Drawings", True), ("Work Orders", False), ("Invoices", False),
    ("Certifications", False), ("Compliance", False), ("Photos", False), ("Others", False),
]


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _seed_categories():
    if await db.dms_categories.count_documents({}) == 0:
        await db.dms_categories.insert_many([
            {"id": new_id(), "name": n, "requires_approval": ra, "sort": i, "active": True,
             "created_at": now_iso()} for i, (n, ra) in enumerate(DEFAULT_CATEGORIES)])


def _doc_status(d: dict, a: Optional[dict]) -> str:
    if d.get("status") == "archived":
        return "archived"
    if d.get("approval_id"):
        st = (a or {}).get("status")
        if st == "rejected":
            return "rejected"
        if st and st != "approved":
            return "pending_approval"
        if not a:
            return "pending_approval"
    return "active"


# ──────────────────────────── Categories ────────────────────────────
@router.get("/categories")
async def list_categories(user: dict = Depends(require_permission("documents", "read"))):
    await _seed_categories()
    return await db.dms_categories.find({"active": True}, {"_id": 0}).sort("sort", 1).to_list(100)


class CategoryIn(BaseModel):
    name: str
    requires_approval: bool = False


@router.post("/categories")
async def create_category(p: CategoryIn, user: dict = Depends(require_permission("documents", "write"))):
    if await db.dms_categories.find_one({"name": {"$regex": f"^{p.name.strip()}$", "$options": "i"}, "active": True}):
        raise HTTPException(400, "Category already exists")
    n = await db.dms_categories.count_documents({})
    doc = {"id": new_id(), "name": p.name.strip(), "requires_approval": p.requires_approval,
           "sort": n, "active": True, "created_at": now_iso(), "created_by": user.get("name")}
    await db.dms_categories.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/categories/{cid}")
async def update_category(cid: str, p: CategoryIn, user: dict = Depends(require_permission("documents", "write"))):
    r = await db.dms_categories.update_one({"id": cid}, {"$set": {
        "name": p.name.strip(), "requires_approval": p.requires_approval, "updated_at": now_iso()}})
    if not r.matched_count:
        raise HTTPException(404, "Category not found")
    return await db.dms_categories.find_one({"id": cid}, {"_id": 0})


# ──────────────────────────── Stats ────────────────────────────
@router.get("/stats")
async def dms_stats(user: dict = Depends(require_permission("documents", "read"))):
    from datetime import date, timedelta
    today = date.today().isoformat()
    soon = (date.today() + timedelta(days=30)).isoformat()
    base = {"status": {"$ne": "archived"}}
    total = await db.dms_documents.count_documents(base)
    expired = await db.dms_documents.count_documents({**base, "expiry_date": {"$gt": "", "$lt": today}})
    expiring = await db.dms_documents.count_documents({**base, "expiry_date": {"$gte": today, "$lte": soon}})
    pend_ids = [d["approval_id"] async for d in db.dms_documents.find(
        {**base, "approval_id": {"$ne": None}}, {"_id": 0, "approval_id": 1})]
    pending = await db.approvals.count_documents({"id": {"$in": pend_ids}, "status": "pending"}) if pend_ids else 0
    by_module = {r["_id"]: r["n"] for r in await db.dms_documents.aggregate([
        {"$match": base}, {"$group": {"_id": "$module", "n": {"$sum": 1}}}]).to_list(20)}
    return {"total": total, "expired": expired, "expiring_30d": expiring,
            "pending_approval": pending, "by_module": by_module}


# ──────────────────────────── List ────────────────────────────
@router.get("/documents")
async def list_documents(module: str = "", project_code: str = "", category_id: str = "",
                         q: str = "", status: str = "", expiring: str = "",
                         user: dict = Depends(require_permission("documents", "read"))):
    conds: List[Dict[str, Any]] = [{"status": {"$ne": "deleted"}}]
    if module:
        conds.append({"module": module})
    if project_code:
        conds.append({"project_code": project_code})
    if category_id:
        conds.append({"category_id": category_id})
    if q:
        rx = {"$regex": q.strip(), "$options": "i"}
        conds.append({"$or": [{"title": rx}, {"doc_no": rx}, {"tags": rx},
                              {"remarks": rx}, {"versions.file_name": rx}]})
    if expiring in ("soon", "expired"):
        from datetime import date, timedelta
        today = date.today().isoformat()
        if expiring == "soon":
            conds.append({"expiry_date": {"$gte": today, "$lte": (date.today() + timedelta(days=30)).isoformat()}})
        else:
            conds.append({"expiry_date": {"$gt": "", "$lt": today}})
    # Project isolation — scoped users see their projects' docs + non-project docs
    scope_q = await apply_project_scope(user, {}, id_field="project_id", code_field="project_code")
    if "project_code" in scope_q:
        conds.append({"$or": [{"project_code": scope_q["project_code"]},
                              {"project_code": {"$in": [None, ""]}}]})
    query = {"$and": conds}
    rows = await db.dms_documents.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    aids = [r["approval_id"] for r in rows if r.get("approval_id")]
    approvals = {a["id"]: a async for a in db.approvals.find(
        {"id": {"$in": aids}}, {"_id": 0, "id": 1, "status": 1, "chain": 1, "current_step": 1})}
    fids = [v["file_id"] for r in rows for v in (r.get("versions") or [])]
    sync = {s["file_id"]: s async for s in db.onedrive_queue.find(
        {"file_id": {"$in": fids}}, {"_id": 0, "file_id": 1, "status": 1, "web_url": 1})}
    out = []
    for r in rows:
        st = _doc_status(r, approvals.get(r.get("approval_id")))
        if status and st != status:
            continue
        latest = (r.get("versions") or [{}])[-1]
        s = sync.get(latest.get("file_id")) or {}
        out.append({**r, "status": st,
                    "onedrive_status": s.get("status") or "pending",
                    "onedrive_url": s.get("web_url")})
    return out


# ──────────────────────────── Upload / versions ────────────────────────────
async def _store_file(file: UploadFile, doc_id: str, user: dict,
                      segments: List[str]) -> dict:
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"File too large (max {MAX_BYTES // (1024 * 1024)} MB)")
    stored = put_object(folder="documents", filename=file.filename or "file.bin",
                        data=data, content_type=file.content_type)
    rec = {"id": new_id(), "storage_path": stored["path"], "original_filename": file.filename,
           "content_type": stored.get("content_type") or file.content_type,
           "size": stored.get("size") or len(data), "title": file.filename,
           "folder": "documents", "parent_type": "dms_documents", "parent_id": doc_id,
           "uploaded_by": user.get("name") or user.get("email"), "uploaded_by_id": user["id"],
           "is_deleted": False, "created_at": now_iso()}
    await db.files.insert_one(rec)
    try:
        from routers.onedrive_router import enqueue_file
        await enqueue_file(rec["id"], folder_segments=segments)
    except Exception:
        pass
    return rec


def _segments(module: str, project_code: str, category_name: str) -> List[str]:
    return ["ERP-Documents", MODULES.get(module, module.title()),
            project_code or "General", category_name]


@router.post("/documents")
async def upload_document(request: Request,
                          file: UploadFile = File(...),
                          title: str = Form(""),
                          module: str = Form(...),
                          project_code: str = Form(""),
                          category_id: str = Form(...),
                          tags: str = Form(""),
                          expiry_date: str = Form(""),
                          remarks: str = Form(""),
                          user: dict = Depends(require_permission("documents", "write"))):
    if module not in MODULES:
        raise HTTPException(400, f"module must be one of {sorted(MODULES)}")
    cat = await db.dms_categories.find_one({"id": category_id, "active": True}, {"_id": 0})
    if not cat:
        raise HTTPException(404, "Category not found")
    project = None
    if project_code:
        scoped_q = await apply_project_scope(user, {"code": project_code}, id_field="id", code_field="code")
        project = await db.projects.find_one(scoped_q, {"_id": 0, "code": 1, "name": 1})
        if not project:
            raise HTTPException(404, "Project not found or outside your project scope")
    elif module == "projects":
        raise HTTPException(400, "project_code is required for the Projects module")

    doc_id = new_id()
    file_rec = await _store_file(file, doc_id, user, _segments(module, project_code, cat["name"]))
    doc_no = await next_sequence("DOC")
    doc = {
        "id": doc_id, "doc_no": doc_no,
        "title": (title or file.filename or "Untitled").strip(),
        "module": module, "project_code": project_code or None,
        "project_name": (project or {}).get("name"),
        "category_id": cat["id"], "category_name": cat["name"],
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
        "remarks": remarks or "", "expiry_date": expiry_date or None,
        "status": "active", "requires_approval": bool(cat.get("requires_approval")),
        "current_version": 1,
        "versions": [{"version": 1, "file_id": file_rec["id"], "file_name": file.filename,
                      "size": file_rec["size"], "content_type": file_rec["content_type"],
                      "uploaded_by": user.get("name") or user.get("email"), "uploaded_at": now_iso()}],
        "approval_id": None,
        "created_by": user.get("name") or user.get("email"),
        "created_by_id": user["id"], "created_at": now_iso(),
    }
    if cat.get("requires_approval"):
        approval = {
            "id": new_id(),
            "title": f"Document {doc_no} — {doc['title']} ({cat['name']}, {MODULES[module]}"
                     + (f" · {project_code}" if project_code else "") + ")",
            "type": "document", "reference": doc_id, "amount": 0,
            "requested_by": doc["created_by"],
            "chain": await build_chain("document"), "current_step": 0, "history": [],
            "status": "pending", "created_at": now_iso(),
        }
        await insert_approval(approval, skip_gate=True)
        doc["approval_id"] = approval["id"]
    await db.dms_documents.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="dms_upload", resource="documents",
                record_id=doc_id, after={"doc_no": doc_no, "title": doc["title"]}, ip=_ip(request))
    return {**doc, "status": "pending_approval" if doc["approval_id"] else "active",
            "onedrive_status": "pending"}


@router.post("/documents/{doc_id}/versions")
async def upload_version(doc_id: str, request: Request, file: UploadFile = File(...),
                         user: dict = Depends(require_permission("documents", "write"))):
    doc = await db.dms_documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc or doc.get("status") == "archived":
        raise HTTPException(404, "Document not found")
    if doc.get("project_code"):
        scoped_q = await apply_project_scope(user, {"code": doc["project_code"]}, id_field="id", code_field="code")
        if not await db.projects.find_one(scoped_q, {"_id": 0, "id": 1}):
            raise HTTPException(403, "Outside your project scope")
    file_rec = await _store_file(file, doc_id, user,
                                 _segments(doc["module"], doc.get("project_code") or "", doc["category_name"]))
    v = int(doc.get("current_version") or 1) + 1
    ver = {"version": v, "file_id": file_rec["id"], "file_name": file.filename,
           "size": file_rec["size"], "content_type": file_rec["content_type"],
           "uploaded_by": user.get("name") or user.get("email"), "uploaded_at": now_iso()}
    await db.dms_documents.update_one({"id": doc_id}, {
        "$push": {"versions": ver}, "$set": {"current_version": v, "updated_at": now_iso()}})
    await audit(user=user, action="dms_new_version", resource="documents",
                record_id=doc_id, after={"version": v}, ip=_ip(request))
    return await db.dms_documents.find_one({"id": doc_id}, {"_id": 0})


@router.delete("/documents/{doc_id}")
async def archive_document(doc_id: str, request: Request,
                           user: dict = Depends(require_permission("documents", "write"))):
    doc = await db.dms_documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Document not found")
    if user.get("role") not in ("super_admin", "director") and user.get("id") != doc.get("created_by_id"):
        raise HTTPException(403, "Only the uploader or Admin/Director can archive this document")
    await db.dms_documents.update_one({"id": doc_id}, {"$set": {
        "status": "archived", "archived_at": now_iso(), "archived_by": user.get("name")}})
    await audit(user=user, action="dms_archive", resource="documents",
                record_id=doc_id, after={"doc_no": doc.get("doc_no")}, ip=_ip(request))
    return {"ok": True}
