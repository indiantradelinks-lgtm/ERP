"""Inventory Items & Item Category bulk update — Excel export template + Excel import patch.

Mirrors the proven pattern used in `employees_bulk_router.py`:

  Items:
    GET  /api/inv-bulk/items/template     → xlsx with current items + allowed editable columns.
    POST /api/inv-bulk/items/import       → multipart xlsx upload; match by `id` (preferred)
                                            or `code`/`item_code`. Diff-aware: only fields that
                                            actually changed are written. Blank id rows create
                                            new items.

  Categories:
    GET  /api/inv-bulk/categories/template
    POST /api/inv-bulk/categories/import

Every import writes one entry to `audit_logs` AND a snapshot to
`inventory_bulk_updates` / `inv_categories_bulk_updates` so changes are
recoverable.

Allowed columns are an explicit whitelist — anything else in the xlsx is ignored.
Use the literal sentinel `__CLEAR__` to clear a value.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook

from core import db, require_permission, now_iso, new_id
from audit import audit


router = APIRouter(prefix="/inv-bulk", tags=["inventory-bulk"])


# ───────────────────────── ITEMS ─────────────────────────
ITEM_FIELDS = [
    "code", "item_code", "name", "category", "category_id",
    "uom", "unit", "quantity", "min_stock", "max_stock", "reorder_level",
    "rate", "location", "store_location", "store_id",
    "batch", "serial_no", "vendor_name", "asset_tag",
    "description", "remarks", "hsn_code", "is_active",
    "unit_weight_kg", "size", "material_spec", "material_type", "grade", "make",
]


def _xlsx_response(wb: Workbook, fname: str) -> StreamingResponse:
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


def _instructions_sheet(wb: Workbook, title: str, allowed_fields: List[str]) -> None:
    inst = wb.create_sheet("INSTRUCTIONS")
    inst.append([f"INDIAN TRADE LINKS ERP — {title} Bulk Update"])
    inst.append([])
    inst.append(["1. Do NOT modify the `id` column (column A). It is the match key."])
    inst.append(["2. Edit any of the allowed columns. Empty cell = leave existing value unchanged."])
    inst.append(["3. To explicitly clear a value, type the literal text:  __CLEAR__"])
    inst.append(["4. Adding NEW rows (blank id) will create new records."])
    inst.append(["5. Save as .xlsx and re-upload via the corresponding 'Bulk Update' button."])
    inst.append([])
    inst.append(["Allowed columns:"])
    for f in allowed_fields:
        inst.append(["", f])


@router.get("/items/template")
async def items_template(user: dict = Depends(require_permission("inventory", "write"))):
    """Download current inventory items as an editable xlsx template."""
    rows = await db.inventory.find({}, {"_id": 0}).sort("code", 1).to_list(20000)
    wb = Workbook()
    ws = wb.active
    ws.title = "Items"
    headers = ["id"] + ITEM_FIELDS
    ws.append(headers)
    for col_idx, _ in enumerate(headers, 1):
        c = ws.cell(row=1, column=col_idx)
        c.font = c.font.copy(bold=True)
    for r in rows:
        ws.append([r.get(h, "") if r.get(h) is not None else "" for h in headers])
    _instructions_sheet(wb, "Item Master", ITEM_FIELDS)
    fname = f"item-master-bulk-template-{datetime.now(timezone.utc).date()}.xlsx"
    return _xlsx_response(wb, fname)


@router.post("/items/import")
async def items_import(file: UploadFile = File(...),
                       user: dict = Depends(require_permission("inventory", "write"))):
    """Diff-aware bulk patch on inventory items."""
    return await _generic_import(
        file=file, user=user,
        collection="inventory",
        snapshot_collection="inventory_bulk_updates",
        sheet_name="Items",
        allowed_fields=ITEM_FIELDS,
        match_by_secondary=("code", "item_code"),
        required_new_field="name",
        audit_resource="inventory",
    )


# ─────────────────────── CATEGORIES ───────────────────────
CATEGORY_FIELDS = [
    "code", "name", "description", "sub_categories", "active",
]


@router.get("/categories/template")
async def categories_template(user: dict = Depends(require_permission("inventory", "write"))):
    rows = await db.inv_categories.find({}, {"_id": 0}).sort("code", 1).to_list(5000)
    wb = Workbook()
    ws = wb.active
    ws.title = "Categories"
    headers = ["id"] + CATEGORY_FIELDS
    ws.append(headers)
    for col_idx, _ in enumerate(headers, 1):
        c = ws.cell(row=1, column=col_idx)
        c.font = c.font.copy(bold=True)
    for r in rows:
        out = []
        for h in headers:
            v = r.get(h)
            if h == "sub_categories" and isinstance(v, list):
                v = ", ".join(str(x) for x in v)
            out.append("" if v is None else v)
        ws.append(out)
    _instructions_sheet(wb, "Item Category Master", CATEGORY_FIELDS)
    inst = wb["INSTRUCTIONS"]
    inst.append([])
    inst.append(["Note: `sub_categories` is a comma-separated list (e.g. `Bolts, Nuts, Washers`)."])
    fname = f"item-category-bulk-template-{datetime.now(timezone.utc).date()}.xlsx"
    return _xlsx_response(wb, fname)


@router.post("/categories/import")
async def categories_import(file: UploadFile = File(...),
                            user: dict = Depends(require_permission("inventory", "write"))):
    return await _generic_import(
        file=file, user=user,
        collection="inv_categories",
        snapshot_collection="inv_categories_bulk_updates",
        sheet_name="Categories",
        allowed_fields=CATEGORY_FIELDS,
        match_by_secondary=("code",),
        required_new_field="name",
        audit_resource="inv_categories",
        list_fields={"sub_categories"},
    )


# ─────────────────────── shared engine ───────────────────────
async def _generic_import(*, file: UploadFile, user: dict,
                          collection: str, snapshot_collection: str,
                          sheet_name: str, allowed_fields: List[str],
                          match_by_secondary: tuple, required_new_field: str,
                          audit_resource: str,
                          list_fields: set | None = None) -> dict:
    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(400, "Please upload a .xlsx file")
    try:
        wb = load_workbook(io.BytesIO(await file.read()), data_only=True)
    except Exception as e:
        raise HTTPException(400, f"Invalid xlsx file: {e}")
    ws = wb[sheet_name] if sheet_name in wb.sheetnames else wb.active
    if ws.max_row < 2:
        raise HTTPException(400, "Sheet is empty (need at least one data row)")

    headers: List[str] = []
    for cell in ws[1]:
        headers.append((cell.value or "").strip() if cell.value else "")
    if "id" not in headers:
        raise HTTPException(400, "Missing `id` column in header row")

    list_fields = list_fields or set()
    summary = {"total_rows": 0, "updated": 0, "created": 0, "unchanged": 0, "skipped": 0, "errors": []}
    per_row = []
    snapshot_id = new_id()
    snapshot_rows = []

    for ri, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        summary["total_rows"] += 1
        row_dict = dict(zip(headers, row))
        rec_id = row_dict.get("id")
        if isinstance(rec_id, str):
            rec_id = rec_id.strip() or None

        # Build patch of allowed fields only
        patch: Dict[str, Any] = {}
        for f in allowed_fields:
            if f not in row_dict:
                continue
            val = row_dict[f]
            if val is None or (isinstance(val, str) and val.strip() == ""):
                continue
            if isinstance(val, str) and val.strip() == "__CLEAR__":
                patch[f] = None if f not in list_fields else []
                continue
            if f in list_fields and isinstance(val, str):
                patch[f] = [x.strip() for x in val.split(",") if x.strip()]
            else:
                patch[f] = val

        if not patch and rec_id:
            summary["unchanged"] += 1
            per_row.append({"row": ri, "id": rec_id, "action": "unchanged"})
            continue

        try:
            existing = None
            if rec_id:
                existing = await db[collection].find_one({"id": rec_id}, {"_id": 0})
            if not existing and rec_id:
                # Fall back to secondary match keys
                for fld in match_by_secondary:
                    existing = await db[collection].find_one({fld: rec_id}, {"_id": 0})
                    if existing:
                        break

            if existing:
                # Diff against existing — only write actually-changed fields.
                diff_patch: Dict[str, Any] = {}
                for k, v in patch.items():
                    cur = existing.get(k)
                    cur_n = cur.strip() if isinstance(cur, str) else cur
                    v_n = v.strip() if isinstance(v, str) else v
                    if cur_n != v_n:
                        diff_patch[k] = v
                if not diff_patch:
                    summary["unchanged"] += 1
                    per_row.append({"row": ri, "id": existing["id"], "action": "unchanged"})
                    continue
                diff_patch["updated_at"] = now_iso()
                diff_patch["updated_by"] = user.get("name") or user.get("email")
                diff_patch["bulk_update_snapshot_id"] = snapshot_id
                await db[collection].update_one({"id": existing["id"]}, {"$set": diff_patch})
                snapshot_rows.append({"id": existing["id"], "before": existing, "patch": diff_patch})
                summary["updated"] += 1
                per_row.append({"row": ri, "id": existing["id"], "action": "updated",
                                "fields": [k for k in diff_patch if k not in ("updated_at", "updated_by", "bulk_update_snapshot_id")]})
            elif rec_id and not existing:
                summary["skipped"] += 1
                summary["errors"].append({"row": ri, "id": rec_id, "error": "record not found"})
                per_row.append({"row": ri, "id": rec_id, "action": "skipped", "error": "not found"})
            else:
                # Create new record
                if not patch.get(required_new_field):
                    summary["skipped"] += 1
                    summary["errors"].append({"row": ri, "error": f"blank id and blank {required_new_field} — row ignored"})
                    per_row.append({"row": ri, "action": "skipped", "error": f"blank id+{required_new_field}"})
                    continue
                new_doc = {
                    "id": new_id(),
                    "created_at": now_iso(),
                    "created_by": user.get("name") or user.get("email"),
                    "bulk_update_snapshot_id": snapshot_id,
                    **patch,
                }
                # category-specific default
                if collection == "inv_categories" and "active" not in new_doc:
                    new_doc["active"] = True
                await db[collection].insert_one(new_doc)
                new_doc.pop("_id", None)
                summary["created"] += 1
                per_row.append({"row": ri, "id": new_doc["id"], "action": "created"})
        except Exception as e:
            summary["skipped"] += 1
            summary["errors"].append({"row": ri, "id": rec_id, "error": str(e)})
            per_row.append({"row": ri, "id": rec_id, "action": "error", "error": str(e)})

    # Persist snapshot for rollback/audit
    await db[snapshot_collection].insert_one({
        "id": snapshot_id,
        "filename": file.filename,
        "at": now_iso(),
        "by_id": user.get("id"),
        "by_name": user.get("name") or user.get("email"),
        "summary": summary,
        "rows": snapshot_rows[:2000],
    })
    try:
        await audit(user=user, action="bulk_update", resource=audit_resource,
                    record_id=snapshot_id, after=summary, ip="bulk")
    except Exception:
        pass

    return {"snapshot_id": snapshot_id, "summary": summary, "per_row": per_row[:500]}


# ─────────────────── history (read-only) ───────────────────
@router.get("/items/history")
async def items_history(user: dict = Depends(require_permission("inventory", "read"))):
    rows = await db.inventory_bulk_updates.find({}, {"_id": 0, "rows": 0}).sort("at", -1).limit(50).to_list(50)
    return rows


@router.get("/categories/history")
async def categories_history(user: dict = Depends(require_permission("inventory", "read"))):
    rows = await db.inv_categories_bulk_updates.find({}, {"_id": 0, "rows": 0}).sort("at", -1).limit(50).to_list(50)
    return rows
