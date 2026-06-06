"""Hierarchical Client / Site / Contact management.

Schema:
  clients (parent):
    id, customer_code (auto), name, category, pan, cin, corporate_address,
    main_contact, main_phone, main_email, status, credit_limit, created_at, ...

  sites (child of clients):
    id, client_id (FK→clients), site_code (auto, parent-prefixed), name,
    city, state, state_code, gst, pan, billing_address, shipping_address,
    plant_name, payment_terms, credit_limit, geo_lat, geo_lng, status

  client_contacts (child of sites):
    id, site_id (FK→sites), client_id (denormalised), name, designation,
    department (Purchase|Accounts|Technical|Stores|Safety|Project|Management|User),
    mobile, alt_mobile, email, whatsapp, reporting_to, remarks

Customer-code format is configurable from `settings.customer_code_format`:
    {prefix: "CUST", padding: 4, include_fy: false}
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, Request, Query

from core import db, require_permission, get_current_user, now_iso, new_id, logger
from sequences import next_sequence
from audit import audit
from approval_engine import build_chain, insert_approval, copy_approval_doc_fields


router = APIRouter(tags=["clients"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ---------- code format settings ----------
DEFAULT_FORMAT = {"prefix": "CUST", "padding": 4, "include_fy": False}


async def _get_code_format() -> dict:
    doc = await db.settings.find_one({"_id": "customer_code_format"})
    if not doc:
        return dict(DEFAULT_FORMAT)
    return {
        "prefix": doc.get("prefix") or DEFAULT_FORMAT["prefix"],
        "padding": int(doc.get("padding") or DEFAULT_FORMAT["padding"]),
        "include_fy": bool(doc.get("include_fy", DEFAULT_FORMAT["include_fy"])),
    }


async def _next_customer_code() -> str:
    fmt = await _get_code_format()
    if fmt["include_fy"]:
        return await next_sequence(fmt["prefix"], padding=fmt["padding"])
    # year-less code: stash sequence under <prefix>-NOFY
    key = f"{fmt['prefix']}-NOFY"
    doc = await db.sequences.find_one_and_update(
        {"_id": key}, {"$inc": {"value": 1}}, upsert=True, return_document=True,
    )
    if not doc or "value" not in doc:
        doc = await db.sequences.find_one({"_id": key})
    n = int((doc or {}).get("value", 1))
    return f"{fmt['prefix']}-{str(n).zfill(fmt['padding'])}"


@router.get("/admin/customer-code-format")
async def get_code_format(user: dict = Depends(require_permission("clients", "write"))):
    return await _get_code_format()


@router.put("/admin/customer-code-format")
async def update_code_format(payload: Dict[str, Any], user: dict = Depends(require_permission("clients", "delete"))):
    """Only super_admin (clients.delete is super_admin-only) can change format."""
    prefix = (payload.get("prefix") or "").strip().upper()
    if not prefix or len(prefix) > 10:
        raise HTTPException(status_code=400, detail="Prefix must be 1-10 uppercase chars")
    padding = int(payload.get("padding", 4))
    if padding < 3 or padding > 8:
        raise HTTPException(status_code=400, detail="Padding must be between 3 and 8")
    include_fy = bool(payload.get("include_fy", False))
    await db.settings.update_one(
        {"_id": "customer_code_format"},
        {"$set": {"prefix": prefix, "padding": padding, "include_fy": include_fy,
                  "updated_at": now_iso(), "updated_by": user.get("id")}},
        upsert=True,
    )
    return {"prefix": prefix, "padding": padding, "include_fy": include_fy}


# ---------- clients (parent) ----------
@router.get("/clients")
async def list_clients(include_inactive: bool = False,
                       user: dict = Depends(require_permission("clients", "read"))):
    """Flat list of parent clients (no nested sites). For dropdowns + legacy
    consumers. The tree view uses /api/clients-tree instead.
    """
    q: dict = {} if include_inactive else {"status": {"$ne": "inactive"}}
    rows = await db.clients.find(q, {"_id": 0}).sort("name", 1).to_list(2000)
    return rows


@router.get("/clients-tree")
async def list_clients_tree(include_inactive: bool = False,
                            user: dict = Depends(require_permission("clients", "read"))):
    """Hierarchical list — clients with nested sites + contacts. Used by the
    new tree view on /app/clients."""
    q: dict = {} if include_inactive else {"status": {"$ne": "inactive"}}
    clients = await db.clients.find(q, {"_id": 0}).sort("name", 1).to_list(2000)
    if not clients:
        return []
    client_ids = [c["id"] for c in clients]
    sites = await db.sites.find({"client_id": {"$in": client_ids}}, {"_id": 0}).sort("site_code", 1).to_list(5000)
    contacts = await db.client_contacts.find({"client_id": {"$in": client_ids}}, {"_id": 0}).to_list(5000)
    sites_by_client: dict[str, list] = {}
    for s in sites:
        sites_by_client.setdefault(s["client_id"], []).append(s)
    contacts_by_site: dict[str, list] = {}
    for c in contacts:
        contacts_by_site.setdefault(c.get("site_id", ""), []).append(c)
    out = []
    for c in clients:
        c_sites = sites_by_client.get(c["id"], [])
        for s in c_sites:
            s["contacts"] = contacts_by_site.get(s["id"], [])
        c["sites"] = c_sites
        out.append(c)
    return out


@router.post("/clients")
async def create_client(payload: Dict[str, Any], request: Request,
                        user: dict = Depends(require_permission("clients", "write"))):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Client name is required")
    # Duplicate name guard — case-insensitive exact match, escaping any regex
    # metacharacters in the name (e.g. dots in 'A.B & Co').
    import re
    existing = await db.clients.find_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
        {"_id": 0, "id": 1},
    )
    if existing:
        raise HTTPException(status_code=400, detail=f"Client with name '{name}' already exists")
    doc = dict(payload)
    doc["id"] = new_id()
    doc["customer_code"] = await _next_customer_code()
    # Mirror legacy `code` so existing modules keep working.
    doc["code"] = doc["customer_code"]
    doc["name"] = name
    # Phase D — every new client starts in pending_approval; super_admin can fast-track
    if user.get("role") == "super_admin" and payload.get("status") == "active":
        doc["status"] = "active"
    else:
        doc["status"] = "pending_approval"
    doc["created_at"] = now_iso()
    doc["created_by"] = user["id"]
    await db.clients.insert_one(doc)
    doc.pop("_id", None)

    # Auto-create onboarding approval (skip when super_admin fast-tracked)
    if doc["status"] == "pending_approval":
        try:
            chain = await build_chain("client_onboarding")
            approval = {
                "id": new_id(),
                "type": "client_onboarding",
                "module": "clients",
                "record_id": doc["id"],
                "title": f"Onboard {doc['customer_code']} · {doc['name']}",
                "summary": f"New client requesting onboarding ({doc.get('category') or 'uncategorised'})",
                "requested_by": user.get("name") or user.get("email"),
                "requested_by_id": user["id"],
                "status": "pending",
                "current_step": 0,
                "chain": chain,
                "history": [],
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
            copy_approval_doc_fields(approval, payload)
            if not approval.get("documents") and not approval.get("documents_not_required"):
                approval["documents_not_required"] = True
                approval["documents_not_required_reason"] = "KYC documents attached to client master record"
            await insert_approval(approval)
            doc["approval_id"] = approval["id"]
            await db.clients.update_one({"id": doc["id"]}, {"$set": {"approval_id": approval["id"]}})
        except Exception as e:
            logger.warning(f"client_onboarding approval creation failed for {doc['id']}: {e}")

    await audit(user=user, action="create", resource="clients", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.post("/clients/{client_id}/resubmit")
async def resubmit_client(client_id: str, request: Request, body: Optional[Dict[str, Any]] = None,
                          user: dict = Depends(require_permission("clients", "write"))):
    """Re-trigger onboarding approval for a previously rejected client."""
    client = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if client.get("status") not in ("rejected", "pending_revision"):
        raise HTTPException(status_code=400, detail="Only rejected/pending-revision clients can be resubmitted")
    # Mark any previous (now-rejected) onboarding approval as superseded so
    # /app/approvals doesn't list stale entries for this record.
    await db.approvals.update_many(
        {"type": "client_onboarding", "record_id": client_id,
         "status": {"$in": ["rejected", "rejected_revision_required"]}},
        {"$set": {"superseded": True, "superseded_at": now_iso()}},
    )
    chain = await build_chain("client_onboarding")
    approval = {
        "id": new_id(),
        "type": "client_onboarding",
        "module": "clients",
        "record_id": client_id,
        "title": f"Re-onboard {client.get('customer_code')} · {client.get('name')}",
        "summary": "Resubmitted after rejection",
        "requested_by": user.get("name") or user.get("email"),
        "requested_by_id": user["id"],
        "status": "pending",
        "current_step": 0,
        "chain": chain,
        "history": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    copy_approval_doc_fields(approval, body)
    if not approval.get("documents") and not approval.get("documents_not_required"):
        approval["documents_not_required"] = True
        approval["documents_not_required_reason"] = "KYC documents attached to client master record"
    await insert_approval(approval)
    await db.clients.update_one(
        {"id": client_id},
        {"$set": {"status": "pending_approval", "approval_id": approval["id"],
                  "reject_reason": None, "updated_at": now_iso(), "updated_by": user["id"]}},
    )
    await audit(user=user, action="resubmit", resource="clients", record_id=client_id, after={"approval_id": approval["id"]}, ip=_ip(request))
    return {"client_id": client_id, "approval_id": approval["id"]}


@router.get("/clients/by-id/{client_id}")
async def get_client(client_id: str, user: dict = Depends(require_permission("clients", "read"))):
    row = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Client not found")
    return row


@router.put("/clients/{client_id}")
async def update_client(client_id: str, payload: Dict[str, Any], request: Request,
                        user: dict = Depends(require_permission("clients", "write"))):
    payload.pop("id", None)
    # Don't allow customer_code rewrite — it's system-controlled.
    payload.pop("customer_code", None)
    payload.pop("code", None)
    payload["updated_at"] = now_iso()
    payload["updated_by"] = user["id"]
    before = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Client not found")
    await db.clients.update_one({"id": client_id}, {"$set": payload})
    row = await db.clients.find_one({"id": client_id}, {"_id": 0})
    await audit(user=user, action="update", resource="clients", record_id=client_id, before=before, after=row, ip=_ip(request))
    return row


@router.delete("/clients/{client_id}")
async def delete_client(client_id: str, request: Request,
                        user: dict = Depends(require_permission("clients", "delete"))):
    """Soft-delete cascade — marks client + all sites + contacts as inactive."""
    before = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Client not found")
    await db.clients.update_one({"id": client_id}, {"$set": {"status": "inactive", "updated_at": now_iso()}})
    await db.sites.update_many({"client_id": client_id}, {"$set": {"status": "inactive"}})
    await db.client_contacts.update_many({"client_id": client_id}, {"$set": {"status": "inactive"}})
    await audit(user=user, action="soft_delete", resource="clients", record_id=client_id, before=before, ip=_ip(request))
    return {"ok": True}


# ---------- sites (child of client) ----------
async def _next_site_code(client: dict) -> str:
    """Site codes use a numeric 2-digit suffix on the parent customer_code:
        e.g. parent CUST-0001 → site CUST-0001-01, -02, ...

    Race-safe: uses a per-client sequence in db.sequences rather than counting
    existing rows. This means deleted site codes are NOT reused (intentional).
    """
    parent_code = client.get("customer_code") or client.get("code") or "SITE"
    key = f"{parent_code}-SITE"
    doc = await db.sequences.find_one_and_update(
        {"_id": key}, {"$inc": {"value": 1}}, upsert=True, return_document=True,
    )
    n = int((doc or {}).get("value", 1))
    pad = 3 if n >= 100 else 2
    return f"{parent_code}-{str(n).zfill(pad)}"


def _normalise_gst(gst: str | None) -> str:
    return (gst or "").strip().upper()


@router.post("/clients/{client_id}/sites")
async def create_site(client_id: str, payload: Dict[str, Any], request: Request,
                      user: dict = Depends(require_permission("clients", "write"))):
    client = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    gst = _normalise_gst(payload.get("gst"))
    if gst:
        dup = await db.sites.find_one({"gst": gst}, {"_id": 0, "id": 1, "site_code": 1, "client_id": 1})
        if dup:
            dup_client = await db.clients.find_one({"id": dup["client_id"]}, {"_id": 0, "name": 1})
            raise HTTPException(
                status_code=400,
                detail=f"GST {gst} is already registered under {dup_client.get('name') if dup_client else 'another site'} ({dup.get('site_code')})",
            )
    doc = dict(payload)
    doc["id"] = new_id()
    doc["client_id"] = client_id
    doc["client_name"] = client.get("name")
    doc["site_code"] = await _next_site_code(client)
    doc["gst"] = gst
    doc["status"] = doc.get("status") or "active"
    doc["created_at"] = now_iso()
    doc["created_by"] = user["id"]
    if not doc.get("name"):
        doc["name"] = f"{client.get('name','')} – {doc.get('city') or doc.get('state') or 'Site'}"
    await db.sites.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="clients", record_id=doc["id"],
                after={"site_code": doc["site_code"], "client_id": client_id}, ip=_ip(request))
    return doc


@router.put("/sites/{site_id}")
async def update_site(site_id: str, payload: Dict[str, Any], request: Request,
                      user: dict = Depends(require_permission("clients", "write"))):
    payload.pop("id", None)
    payload.pop("site_code", None)
    payload.pop("client_id", None)
    before = await db.sites.find_one({"id": site_id}, {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Site not found")
    new_gst = _normalise_gst(payload.get("gst")) if "gst" in payload else None
    if new_gst and new_gst != before.get("gst"):
        dup = await db.sites.find_one({"gst": new_gst, "id": {"$ne": site_id}}, {"_id": 0, "site_code": 1})
        if dup:
            raise HTTPException(status_code=400, detail=f"GST {new_gst} is already used by site {dup.get('site_code')}")
        payload["gst"] = new_gst
    payload["updated_at"] = now_iso()
    payload["updated_by"] = user["id"]
    await db.sites.update_one({"id": site_id}, {"$set": payload})
    row = await db.sites.find_one({"id": site_id}, {"_id": 0})
    await audit(user=user, action="update", resource="clients", record_id=site_id, before=before, after=row, ip=_ip(request))
    return row


@router.delete("/sites/{site_id}")
async def delete_site(site_id: str, request: Request,
                      user: dict = Depends(require_permission("clients", "delete"))):
    before = await db.sites.find_one({"id": site_id}, {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Site not found")
    await db.sites.delete_one({"id": site_id})
    await db.client_contacts.delete_many({"site_id": site_id})
    await audit(user=user, action="delete", resource="clients", record_id=site_id, before=before, ip=_ip(request))
    return {"ok": True}


# ---------- contacts ----------
CONTACT_DEPARTMENTS = {"Purchase", "Accounts", "Technical", "User", "Stores", "Safety", "Project", "Management"}


@router.post("/sites/{site_id}/contacts")
async def create_contact(site_id: str, payload: Dict[str, Any], request: Request,
                         user: dict = Depends(require_permission("clients", "write"))):
    site = await db.sites.find_one({"id": site_id}, {"_id": 0})
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    dept = (payload.get("department") or "").strip().title()
    if dept and dept not in CONTACT_DEPARTMENTS:
        raise HTTPException(status_code=400, detail=f"Unknown contact department '{dept}'. Allowed: {sorted(CONTACT_DEPARTMENTS)}")
    doc = dict(payload)
    doc["id"] = new_id()
    doc["site_id"] = site_id
    doc["client_id"] = site["client_id"]
    doc["department"] = dept or "Management"
    doc["created_at"] = now_iso()
    doc["created_by"] = user["id"]
    await db.client_contacts.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="clients", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.put("/contacts/{contact_id}")
async def update_contact(contact_id: str, payload: Dict[str, Any], request: Request,
                         user: dict = Depends(require_permission("clients", "write"))):
    payload.pop("id", None)
    payload["updated_at"] = now_iso()
    before = await db.client_contacts.find_one({"id": contact_id}, {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.client_contacts.update_one({"id": contact_id}, {"$set": payload})
    row = await db.client_contacts.find_one({"id": contact_id}, {"_id": 0})
    await audit(user=user, action="update", resource="clients", record_id=contact_id, before=before, after=row, ip=_ip(request))
    return row


@router.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: str, request: Request,
                         user: dict = Depends(require_permission("clients", "delete"))):
    before = await db.client_contacts.find_one({"id": contact_id}, {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.client_contacts.delete_one({"id": contact_id})
    await audit(user=user, action="delete", resource="clients", record_id=contact_id, before=before, ip=_ip(request))
    return {"ok": True}


# ---------- flat helpers for downstream-module dropdowns ----------
@router.get("/sites")
async def list_sites(client_id: str | None = Query(default=None),
                     user: dict = Depends(require_permission("clients", "read"))):
    q: dict = {}
    if client_id:
        q["client_id"] = client_id
    rows = await db.sites.find(q, {"_id": 0}).sort("site_code", 1).to_list(5000)
    return rows


@router.get("/sites/map")
async def sites_map(user: dict = Depends(require_permission("clients", "read"))):
    """Return all geo-tagged sites for the Client Map view."""
    rows = await db.sites.find(
        {"geo_lat": {"$nin": [None, ""]}, "geo_lng": {"$nin": [None, ""]}, "status": {"$ne": "inactive"}},
        {"_id": 0, "id": 1, "site_code": 1, "name": 1, "client_id": 1, "client_name": 1,
         "city": 1, "state": 1, "status": 1, "geo_lat": 1, "geo_lng": 1},
    ).to_list(5000)
    out = []
    for r in rows:
        try:
            lat = float(r.get("geo_lat"))
            lng = float(r.get("geo_lng"))
        except (TypeError, ValueError):
            continue
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            continue
        out.append({**r, "geo_lat": lat, "geo_lng": lng})
    return out


# ---------- search ----------
@router.get("/clients/search")
async def search_clients(q: str = Query(default="", min_length=1),
                         user: dict = Depends(require_permission("clients", "read"))):
    """Global cross-search: customer_code, site_code, GST, client name, city,
    state, contact name, mobile, email.
    """
    import re
    pat = re.compile(re.escape(q), re.IGNORECASE)
    by_client = await db.clients.find(
        {"$or": [{"customer_code": pat}, {"name": pat}, {"main_phone": pat}, {"main_email": pat}, {"pan": pat}, {"cin": pat}]},
        {"_id": 0},
    ).to_list(50)
    by_site = await db.sites.find(
        {"$or": [{"site_code": pat}, {"gst": pat}, {"city": pat}, {"state": pat}, {"name": pat}]},
        {"_id": 0},
    ).to_list(50)
    by_contact = await db.client_contacts.find(
        {"$or": [{"name": pat}, {"mobile": pat}, {"email": pat}, {"alt_mobile": pat}, {"whatsapp": pat}]},
        {"_id": 0},
    ).to_list(50)
    return {"clients": by_client, "sites": by_site, "contacts": by_contact}


# ---------- reports (Phase C) ----------
@router.get("/clients/reports/by-client")
async def report_by_client(user: dict = Depends(require_permission("clients", "read"))):
    pipeline = [
        {"$match": {"client_id": {"$exists": True, "$nin": [None, ""]}}},
        {"$group": {"_id": "$client_id", "amount": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ]
    qrows = await db.quotations.aggregate(pipeline).to_list(500)
    srows = await db.sales_orders.aggregate(pipeline).to_list(500)
    clients = await db.clients.find({}, {"_id": 0, "id": 1, "name": 1, "customer_code": 1}).to_list(2000)
    name_map = {c["id"]: c for c in clients}
    by: dict[str, dict] = {}
    for r in qrows:
        cid = r["_id"]
        by.setdefault(cid, {"client_id": cid, "client_name": name_map.get(cid, {}).get("name", "—"),
                            "customer_code": name_map.get(cid, {}).get("customer_code", "—"),
                            "quotation_amount": 0, "order_amount": 0, "deal_count": 0})
        by[cid]["quotation_amount"] += r.get("amount", 0)
        by[cid]["deal_count"] += r.get("count", 0)
    for r in srows:
        cid = r["_id"]
        by.setdefault(cid, {"client_id": cid, "client_name": name_map.get(cid, {}).get("name", "—"),
                            "customer_code": name_map.get(cid, {}).get("customer_code", "—"),
                            "quotation_amount": 0, "order_amount": 0, "deal_count": 0})
        by[cid]["order_amount"] += r.get("amount", 0)
    return sorted(by.values(), key=lambda r: r["order_amount"] + r["quotation_amount"], reverse=True)


@router.get("/clients/reports/by-site")
async def report_by_site(user: dict = Depends(require_permission("clients", "read"))):
    pipeline = [
        {"$match": {"site_id": {"$exists": True, "$nin": [None, ""]}}},
        {"$group": {"_id": "$site_id", "amount": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ]
    qrows = await db.quotations.aggregate(pipeline).to_list(500)
    srows = await db.sales_orders.aggregate(pipeline).to_list(500)
    sites = await db.sites.find({}, {"_id": 0, "id": 1, "site_code": 1, "name": 1, "city": 1, "state": 1, "client_name": 1}).to_list(5000)
    site_map = {s["id"]: s for s in sites}
    by: dict[str, dict] = {}
    for r in qrows:
        sid = r["_id"]
        s = site_map.get(sid, {})
        by.setdefault(sid, {"site_id": sid, "site_code": s.get("site_code", "—"), "site_name": s.get("name", "—"),
                            "city": s.get("city", "—"), "state": s.get("state", "—"),
                            "client_name": s.get("client_name", "—"),
                            "quotation_amount": 0, "order_amount": 0})
        by[sid]["quotation_amount"] += r.get("amount", 0)
    for r in srows:
        sid = r["_id"]
        s = site_map.get(sid, {})
        by.setdefault(sid, {"site_id": sid, "site_code": s.get("site_code", "—"), "site_name": s.get("name", "—"),
                            "city": s.get("city", "—"), "state": s.get("state", "—"),
                            "client_name": s.get("client_name", "—"),
                            "quotation_amount": 0, "order_amount": 0})
        by[sid]["order_amount"] += r.get("amount", 0)
    return sorted(by.values(), key=lambda r: r["order_amount"], reverse=True)


@router.get("/clients/reports/by-gst")
async def report_by_gst(user: dict = Depends(require_permission("clients", "read"))):
    sites = await db.sites.find({"gst": {"$nin": [None, ""]}},
                                {"_id": 0, "id": 1, "gst": 1, "site_code": 1, "name": 1, "state": 1, "client_name": 1}).to_list(5000)
    by_gst: dict[str, dict] = {}
    for s in sites:
        gst = s["gst"]
        by_gst.setdefault(gst, {"gst": gst, "state": s.get("state", "—"), "sites": []})
        by_gst[gst]["sites"].append({"site_code": s.get("site_code"), "name": s.get("name"), "client_name": s.get("client_name")})
    return sorted(by_gst.values(), key=lambda r: len(r["sites"]), reverse=True)


@router.get("/clients/reports/outstanding-by-site")
async def report_outstanding(user: dict = Depends(require_permission("clients", "read"))):
    """Sum of invoices.amount where status != 'paid', grouped by site."""
    pipeline = [
        {"$match": {"status": {"$ne": "paid"}, "site_id": {"$exists": True, "$nin": [None, ""]}}},
        {"$group": {"_id": "$site_id", "outstanding": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ]
    rows = await db.invoices.aggregate(pipeline).to_list(500)
    sites = await db.sites.find({}, {"_id": 0, "id": 1, "site_code": 1, "name": 1, "client_name": 1, "city": 1}).to_list(5000)
    smap = {s["id"]: s for s in sites}
    out = []
    for r in rows:
        s = smap.get(r["_id"], {})
        out.append({
            "site_id": r["_id"],
            "site_code": s.get("site_code", "—"),
            "name": s.get("name", "—"),
            "client_name": s.get("client_name", "—"),
            "city": s.get("city", "—"),
            "outstanding": r["outstanding"],
            "invoice_count": r["count"],
        })
    out.sort(key=lambda r: r["outstanding"], reverse=True)
    return out


@router.get("/clients/reports/by-location")
async def report_by_location(user: dict = Depends(require_permission("clients", "read"))):
    pipeline = [
        {"$group": {"_id": {"state": "$state", "city": "$city"}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    rows = await db.sites.aggregate(pipeline).to_list(500)
    return [{"state": r["_id"].get("state") or "—", "city": r["_id"].get("city") or "—", "count": r["count"]} for r in rows]


@router.get("/clients/reports/contact-directory")
async def report_contact_directory(user: dict = Depends(require_permission("clients", "read"))):
    rows = await db.client_contacts.find({}, {"_id": 0}).sort("name", 1).to_list(5000)
    site_map: dict = {}
    if rows:
        ids = list({r.get("site_id") for r in rows if r.get("site_id")})
        sites = await db.sites.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "site_code": 1, "client_name": 1}).to_list(5000)
        site_map = {s["id"]: s for s in sites}
    for r in rows:
        s = site_map.get(r.get("site_id"), {})
        r["site_code"] = s.get("site_code", "—")
        r["client_name"] = s.get("client_name", r.get("client_name", "—"))
    return rows


@router.get("/clients/reports/activity-history")
async def report_activity_history(client_id: str | None = None, limit: int = 200,
                                  user: dict = Depends(require_permission("clients", "read"))):
    q: dict = {"resource": "clients"}
    if client_id:
        q["record_id"] = client_id
    rows = await db.audit_logs.find(q, {"_id": 0}).sort("at", -1).to_list(min(limit, 500))
    return rows


# ---------- CSV import / export ----------
from fastapi import UploadFile, File
from fastapi.responses import Response
import csv
import io

CLIENT_CSV_HEADERS = [
    "customer_code", "name", "category", "pan", "cin",
    "corporate_address", "main_contact", "main_phone", "main_email",
    "credit_limit", "status",
]


@router.get("/clients/export.csv")
async def export_clients_csv(user: dict = Depends(require_permission("clients", "read"))):
    rows = await db.clients.find({}, {"_id": 0}).sort("customer_code", 1).to_list(5000)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CLIENT_CSV_HEADERS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in CLIENT_CSV_HEADERS})
    return Response(content=buf.getvalue(),
                    media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="clients.csv"'})


@router.post("/clients/import.csv")
async def import_clients_csv(file: UploadFile = File(...),
                             user: dict = Depends(require_permission("clients", "write"))):
    """Bulk-create clients from a CSV file. Skips rows whose name already exists
    (case-insensitive). Returns per-row outcome.

    Expected headers (subset accepted, extras ignored):
      name, category, pan, cin, corporate_address, main_contact,
      main_phone, main_email, credit_limit, status

    `customer_code` is ignored on import — every imported client gets a fresh
    system-generated code.
    """
    raw = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    created: list[dict] = []
    skipped: list[dict] = []
    import re as _re
    for idx, row in enumerate(reader, start=2):  # row 1 is header
        name = (row.get("name") or "").strip()
        if not name:
            skipped.append({"row": idx, "reason": "blank name"})
            continue
        existing = await db.clients.find_one(
            {"name": {"$regex": f"^{_re.escape(name)}$", "$options": "i"}},
            {"_id": 0, "id": 1},
        )
        if existing:
            skipped.append({"row": idx, "name": name, "reason": "duplicate"})
            continue
        try:
            doc = {k: (row.get(k) or "").strip() for k in CLIENT_CSV_HEADERS if k != "customer_code"}
            doc["name"] = name
            try:
                doc["credit_limit"] = float(doc.get("credit_limit") or 0)
            except ValueError:
                doc["credit_limit"] = 0
            doc["status"] = (doc.get("status") or "active").lower()
            doc["id"] = new_id()
            doc["customer_code"] = await _next_customer_code()
            doc["code"] = doc["customer_code"]
            doc["created_at"] = now_iso()
            doc["created_by"] = user["id"]
            doc["created_via"] = "csv_import"
            await db.clients.insert_one(doc)
            doc.pop("_id", None)
            created.append({"row": idx, "name": name, "customer_code": doc["customer_code"]})
        except Exception as e:
            logger.warning(f"CSV import row {idx} failed: {e}")
            skipped.append({"row": idx, "name": name, "reason": str(e)})
    return {"created": created, "skipped": skipped, "summary": {"created": len(created), "skipped": len(skipped)}}
