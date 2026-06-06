"""CSV bulk-import for master data.

Workflow:
  1) POST /api/import/{collection}/preview  — multipart file
     Returns parsed rows, per-row validation errors, and a dedup match indicator.
  2) POST /api/import/{collection}/commit   — JSON list of validated rows
     Inserts the rows that aren't already present. Returns inserted_count.

Supported masters (P0): clients, vendors, employees, inventory.
Each master declares:
  - required fields (must be non-empty in every row)
  - numeric fields (cast on parse)
  - the lookup field used to detect existing rows (sku / email / phone / name)
All inserts go through the same audit pipeline as crud_router.
"""
import csv
import io
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends, File, Form, UploadFile, Request
from pydantic import BaseModel

from core import db, require_permission, now_iso, new_id
from audit import audit

router = APIRouter(prefix="/import", tags=["import"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# Per-collection schema for the importer.
# `dedup_keys` is tried in order — the first one with a value triggers the lookup.
SCHEMAS: Dict[str, Dict[str, Any]] = {
    "clients": {
        "perm": "clients",
        "label": "Clients",
        "required": ["name"],
        "numeric": [],
        "dedup_keys": ["email", "name"],
        "allowed": [
            "name", "contact_person", "email", "phone", "address", "city",
            "state", "country", "gst", "pan", "industry", "status",
        ],
    },
    "vendors": {
        "perm": "vendors",
        "label": "Vendors",
        "required": ["name"],
        "numeric": ["rating"],
        "dedup_keys": ["contact_email", "name"],
        "allowed": [
            "name", "contact_person", "contact_email", "contact_phone",
            "address", "city", "gst", "pan", "category", "status",
            "bank_account", "ifsc", "bank_name", "rating",
        ],
    },
    "employees": {
        "perm": "employees",
        "label": "Employees",
        "required": ["name"],
        "numeric": ["ctc", "experience_yrs"],
        "dedup_keys": ["email", "phone", "name"],
        "allowed": [
            "name", "code", "email", "phone", "department", "designation",
            "role", "join_date", "ctc", "experience_yrs", "blood_group",
            "emergency_contact", "address", "status",
        ],
    },
    "inventory": {
        "perm": "inventory",
        "label": "Inventory Items",
        "required": ["name"],
        "numeric": ["quantity", "min_stock", "unit_price", "issue_threshold"],
        "dedup_keys": ["sku", "barcode", "name"],
        "allowed": [
            "name", "sku", "barcode", "category", "unit", "quantity",
            "min_stock", "unit_price", "issue_threshold", "location", "description",
        ],
    },
}


def _coerce_number(value: str) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _normalize_row(raw: Dict[str, Any], schema: Dict[str, Any]) -> tuple[Dict[str, Any], List[str]]:
    """Drop unknown columns, coerce numerics, trim strings, return (row, errors)."""
    errors: List[str] = []
    out: Dict[str, Any] = {}
    for key in schema["allowed"]:
        if key in raw:
            v = raw[key]
            if isinstance(v, str):
                v = v.strip()
                if v == "":
                    v = None
            if key in schema["numeric"] and v is not None:
                nv = _coerce_number(v)
                if nv is None:
                    errors.append(f"{key}: not a number ('{raw[key]}')")
                else:
                    v = nv
            if v is not None:
                out[key] = v
    for req in schema["required"]:
        if not out.get(req):
            errors.append(f"missing required field: {req}")
    return out, errors


async def _find_duplicate(collection: str, schema: Dict[str, Any], row: Dict[str, Any]) -> Optional[str]:
    for k in schema["dedup_keys"]:
        v = row.get(k)
        if v:
            existing = await db[collection].find_one({k: v}, {"_id": 0, "id": 1})
            if existing:
                return existing["id"]
    return None


@router.get("/schemas")
async def list_schemas(user: dict = Depends(require_permission("clients", "read"))):
    """Return all importable schemas so the frontend can display headers, sample
    columns and dedup keys without hard-coding them. Permission gate is a single
    'clients' read — anyone who can read masters can browse the schema list.
    """
    return {
        slug: {
            "label": s["label"],
            "required": s["required"],
            "numeric": s["numeric"],
            "allowed": s["allowed"],
            "dedup_keys": s["dedup_keys"],
        }
        for slug, s in SCHEMAS.items()
    }


@router.get("/template/{collection}")
async def template_csv(collection: str, user: dict = Depends(require_permission("clients", "read"))):
    """Return a sample CSV header (and one example row) so the user can
    download → fill in Excel → re-upload.
    """
    schema = SCHEMAS.get(collection)
    if not schema:
        raise HTTPException(status_code=404, detail=f"No importer for '{collection}'")
    header = ",".join(schema["allowed"])
    sample = ",".join(["sample value" if k not in schema["numeric"] else "0" for k in schema["allowed"]])
    return {"filename": f"{collection}-template.csv", "content": header + "\n" + sample + "\n"}


@router.post("/{collection}/preview")
async def preview_import(
    collection: str,
    file: UploadFile = File(...),
    user: dict = Depends(require_permission("clients", "write")),
):
    schema = SCHEMAS.get(collection)
    if not schema:
        raise HTTPException(status_code=404, detail=f"No importer for '{collection}'")
    raw_bytes = await file.read()
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw_bytes.decode("latin-1")
        except UnicodeDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Could not decode file as UTF-8/Latin-1: {e}") from e

    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    if not headers:
        raise HTTPException(status_code=400, detail="CSV has no header row")

    unknown_headers = [h for h in headers if h not in schema["allowed"]]
    rows: List[Dict[str, Any]] = []
    valid = 0
    errors_count = 0
    duplicates = 0

    for idx, raw in enumerate(reader, start=2):  # row 1 was the header
        norm, errs = _normalize_row(raw, schema)
        dup_id = None
        if not errs:
            dup_id = await _find_duplicate(collection, schema, norm)
        ok = (not errs) and (not dup_id)
        if ok:
            valid += 1
        elif errs:
            errors_count += 1
        elif dup_id:
            duplicates += 1
        rows.append({
            "row": idx,
            "data": norm,
            "errors": errs,
            "duplicate_of": dup_id,
            "ok": ok,
        })

    return {
        "collection": collection,
        "label": schema["label"],
        "headers": headers,
        "unknown_headers": unknown_headers,
        "rows": rows,
        "summary": {
            "total": len(rows),
            "valid": valid,
            "errors": errors_count,
            "duplicates": duplicates,
        },
    }


class CommitIn(BaseModel):
    rows: List[Dict[str, Any]]
    skip_duplicates: bool = True


@router.post("/{collection}/commit")
async def commit_import(
    collection: str,
    payload: CommitIn,
    request: Request,
    user: dict = Depends(require_permission("clients", "write")),
):
    schema = SCHEMAS.get(collection)
    if not schema:
        raise HTTPException(status_code=404, detail=f"No importer for '{collection}'")

    # Re-check permission for the target collection specifically.
    # (We gate the endpoint on 'clients' write for convenience, but the actual
    # insert must respect the real permission.)
    perm = schema["perm"]
    from rbac import has_permission
    if not has_permission(user.get("role"), perm, "write"):
        raise HTTPException(status_code=403, detail=f"Missing write permission on {perm}")

    inserted = 0
    skipped = 0
    failed = 0
    for raw in payload.rows:
        norm, errs = _normalize_row(raw, schema)
        if errs:
            failed += 1
            continue
        dup_id = await _find_duplicate(collection, schema, norm)
        if dup_id and payload.skip_duplicates:
            skipped += 1
            continue
        doc = {
            **norm,
            "id": new_id(),
            "created_at": now_iso(),
            "created_by": user["id"],
            "import_source": "csv",
        }
        await db[collection].insert_one(doc)
        doc.pop("_id", None)
        await audit(user=user, action="import_create", resource=collection, record_id=doc["id"], after=doc, ip=_ip(request))
        inserted += 1

    return {"inserted": inserted, "skipped_duplicates": skipped, "failed": failed}
