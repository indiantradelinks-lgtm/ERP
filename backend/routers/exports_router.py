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
}


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
    fname = f"{perm_key}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.{fmt}"
    if fmt == "xlsx":
        data = to_excel(perm_key, rows)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        data = to_pdf(perm_key, rows)
        media = "application/pdf"
    return StreamingResponse(io.BytesIO(data), media_type=media, headers={"Content-Disposition": f'attachment; filename="{fname}"'})
