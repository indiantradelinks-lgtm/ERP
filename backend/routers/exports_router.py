"""Excel + PDF export endpoint."""
import io
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse

from core import db, get_current_user
from rbac import can
from exports import to_excel, to_pdf

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
}

# DPDP Act 2023 — roles allowed to see un-masked PII per resource.
# Anyone else gets the masked (redacted) export automatically.
_PII_PRIVILEGED_ROLES = {
    "employees":   {"super_admin", "director", "general_manager", "hr_executive", "dept_head"},
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


@router.get("/export/{resource}.{fmt}")
async def export_resource(resource: str, fmt: str, user: dict = Depends(get_current_user)):
    if resource not in _EXPORT_RESOURCE_MAP:
        raise HTTPException(status_code=404, detail="Unknown resource")
    perm_key = _EXPORT_RESOURCE_MAP[resource]
    if not can(user.get("role"), perm_key, "read"):
        raise HTTPException(status_code=403, detail=f"Forbidden: cannot read {perm_key}")
    if fmt not in ("xlsx", "pdf"):
        raise HTTPException(status_code=400, detail="Format must be xlsx or pdf")

    rows = await db[perm_key].find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    mask = _should_mask_pii(user.get("role"), perm_key)
    fname = f"{perm_key}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.{fmt}"
    if fmt == "xlsx":
        data = to_excel(perm_key, rows, mask_pii=mask)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        data = to_pdf(perm_key, rows, mask_pii=mask)
        media = "application/pdf"
    return StreamingResponse(io.BytesIO(data), media_type=media, headers={"Content-Disposition": f'attachment; filename="{fname}"'})
