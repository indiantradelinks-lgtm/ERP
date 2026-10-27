"""Excel + PDF export endpoint."""
import io
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse

from core import db, get_current_user
from rbac import can
from exports import to_excel, to_pdf
from offload import run_blocking

router = APIRouter(tags=["exports"])

_EXPORT_RESOURCE_MAP = {
    "clients": "clients", "vendors": "vendors", "employees": "employees",
    "attendance": "attendance", "projects": "projects", "inventory": "inventory",
    "purchase-orders": "purchase_orders", "quotations": "quotations",
    "journal-entries": "journal_entries", "safety-reports": "safety_reports",
    "assets": "assets", "payroll": "payroll", "vehicles": "vehicles",
    "documents": "documents", "approvals": "approvals",
    # Iter 76 — candidates added so HR can export shortlists too (PII-aware)
    "candidates": "candidates",
    "enquiries": "enquiries",
    "ptws": "ptws",
}

# DPDP Act 2023 — roles allowed to see un-masked PII per resource.
# Anyone else gets the masked (redacted) export automatically.
_PII_PRIVILEGED_ROLES = {
    "employees":   {"super_admin", "director", "general_manager", "hr_executive"},
    "candidates":  {"super_admin", "director", "general_manager", "hr_executive"},
    "payroll":     {"super_admin", "director", "general_manager", "hr_executive", "accounts_executive"},
    "attendance":  {"super_admin", "director", "general_manager", "hr_executive", "dept_head"},
    "clients":     {"super_admin", "director", "general_manager", "accounts_executive", "client_rep"},
    "vendors":     {"super_admin", "director", "general_manager", "accounts_executive", "purchase_officer"},
    "documents":   {"super_admin", "director", "general_manager"},
}


def _should_mask_pii(role: str | None, resource_key: str) -> bool:
    """True ⇒ redact PII columns for this user on this resource."""
    privileged = _PII_PRIVILEGED_ROLES.get(resource_key)
    if not privileged:
        return False  # resource has no declared PII columns
    return (role or "") not in privileged


async def _enrich_projects(rows: list[dict]) -> list[dict]:
    """Fill contract dates from Contract Handover data and resolve the assigned PM name."""
    codes = [r.get("code") for r in rows if r.get("code")]
    ho_by_code: dict = {}
    ho_by_id: dict = {}
    async for h in db.project_handovers.find(
            {"project_code": {"$in": codes}},
            {"_id": 0, "id": 1, "project_code": 1, "status": 1, "updated_at": 1, "created_at": 1,
             "contract_start_date": 1, "contract_end_date": 1, "work_order_number": 1,
             "project_manager_label": 1, "project_manager_id": 1}):
        ho_by_id[h.get("id")] = h
        cur = ho_by_code.get(h.get("project_code"))
        # prefer non-draft, then most recent
        def rank(x):
            return (0 if x.get("status") == "draft" else 1, x.get("updated_at") or x.get("created_at") or "")
        if not cur or rank(h) > rank(cur):
            ho_by_code[h["project_code"]] = h
    pm_ids = {r.get("project_manager_id") for r in rows if r.get("project_manager_id")}
    pm_ids |= {h.get("project_manager_id") for h in ho_by_code.values() if h.get("project_manager_id")}
    users = {u["id"]: u.get("name") async for u in db.users.find(
        {"id": {"$in": list(pm_ids)}}, {"_id": 0, "id": 1, "name": 1})} if pm_ids else {}
    for i, r in enumerate(rows, start=1):
        h = ho_by_id.get(r.get("handover_id")) or ho_by_code.get(r.get("code")) or {}
        r["s_no"] = i
        r["work_order_number"] = h.get("work_order_number") or r.get("work_order_number") or ""
        r["contract_start_date"] = h.get("contract_start_date") or r.get("contract_start_date") or ""
        r["contract_end_date"] = h.get("contract_end_date") or r.get("contract_end_date") or ""
        r["manager"] = (r.get("project_manager_name")
                        or users.get(r.get("project_manager_id"))
                        or h.get("project_manager_label")
                        or users.get(h.get("project_manager_id"))
                        or r.get("manager") or "")
        r["category_label"] = str(r.get("category") or "").replace("_", " ").title() or "—"
        r["priority_label"] = str(r.get("priority") or "").replace("_", " ").title() or "—"
        llr = r.get("labour_licence_required")
        if isinstance(llr, bool):
            r["labour_licence_label"] = "Yes" if llr else "No"
        else:
            r["labour_licence_label"] = {"yes": "Yes", "true": "Yes", "no": "No", "false": "No"}.get(
                str(llr or "").strip().lower(), "—")
    return rows


@router.get("/export/{resource}.{fmt}")
async def export_resource(resource: str, fmt: str,
                          master: str | None = None, project_code: str | None = None,
                          status: str | None = None,
                          from_date: str | None = None, to_date: str | None = None,
                          user: dict = Depends(get_current_user)):
    if resource not in _EXPORT_RESOURCE_MAP:
        raise HTTPException(status_code=404, detail="Unknown resource")
    perm_key = _EXPORT_RESOURCE_MAP[resource]
    if not can(user.get("role"), perm_key, "read"):
        raise HTTPException(status_code=403, detail=f"Forbidden: cannot read {perm_key}")
    if fmt not in ("xlsx", "pdf"):
        raise HTTPException(status_code=400, detail="Format must be xlsx or pdf")

    q: dict = {}
    if perm_key == "employees":
        if master == "worker":
            q["master_category"] = "worker"
        elif master == "employee":
            q["$or"] = [{"master_category": {"$in": [None, "", "employee"]}},
                        {"master_category": {"$exists": False}}]
        if project_code:
            q["current_project_code"] = project_code

    if status:
        q["status"] = status
    if from_date or to_date:
        rng: dict = {}
        if from_date:
            rng["$gte"] = from_date
        if to_date:
            from datetime import datetime as _dt, timedelta as _td
            try:
                rng["$lt"] = (_dt.strptime(to_date, "%Y-%m-%d") + _td(days=1)).strftime("%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="to_date must be YYYY-MM-DD")
        q["created_at"] = rng

    rows = await db[perm_key].find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)
    if perm_key == "projects":
        rows = await _enrich_projects(rows)
    if perm_key == "enquiries":
        from exports import enrich_enquiries
        uids = list({r.get("created_by") for r in rows if r.get("created_by")})
        umap = {u["id"]: u.get("name") async for u in db.users.find({"id": {"$in": uids}}, {"_id": 0, "id": 1, "name": 1})}
        rows = enrich_enquiries(rows, umap)
    mask = _should_mask_pii(user.get("role"), perm_key)
    fname = f"{perm_key}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.{fmt}"
    if fmt == "xlsx":
        data = await run_blocking(to_excel, perm_key, rows, mask_pii=mask)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        data = await run_blocking(to_pdf, perm_key, rows, mask_pii=mask)
        media = "application/pdf"
    return StreamingResponse(io.BytesIO(data), media_type=media, headers={"Content-Disposition": f'attachment; filename="{fname}"'})
