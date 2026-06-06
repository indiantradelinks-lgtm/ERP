"""Data Linkage router — cross-module record graph, Google Sheets live link, Tally XML sync."""
from __future__ import annotations

import csv
import io
import logging
from typing import Any
from xml.etree import ElementTree as ET

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core import db, get_current_user, now_iso, new_id

logger = logging.getLogger("erp.linkage")
router = APIRouter(prefix="/linkage", tags=["linkage"])


# ────────────────────────────────────────────────────────────────────────
# 1. CROSS-MODULE LINK GRAPH
# ────────────────────────────────────────────────────────────────────────
# For a given entity (resource + id), return all records in other modules
# that reference it. Used by a "Linked Records" side panel on detail pages.
#
# Convention used across the ERP:
# - clients ←→ enquiries.client_id, quotations.client_id|client, orders.client_id,
#             projects.client|client_id, ra_bills.client_id, sites.client_id
# - projects ←→ purchase_requisitions.project_id, purchase_orders.project|project_id,
#             rfqs.project_id, dprs.project_id, measurements.project_id,
#             ra_bills.project_id|project_code, deployments.project_id|project|project_code
# - enquiries ←→ quotations.enquiry_id, orders.enquiry_id
# - quotations ←→ orders.quotation_id (when conversion records id)
# - purchase_requisitions ←→ rfqs.pr_id, purchase_orders.pr_id
# - rfqs ←→ purchase_orders.rfq_id
# - purchase_orders ←→ grns.po_id|po_number
# - measurements ←→ ra_bills (via measurement_ids[])
# - ra_bills ←→ payments_in (via bill_ids[])
# ────────────────────────────────────────────────────────────────────────

LINK_MAP: dict[str, list[dict]] = {
    "clients": [
        {"collection": "sites", "label": "Sites", "match": [{"client_id": "$id"}], "fields": ["site_code", "city", "state", "status"]},
        {"collection": "enquiries", "label": "Enquiries", "match": [{"client_id": "$id"}], "fields": ["enquiry_no", "status", "amount"]},
        {"collection": "quotations", "label": "Quotations", "match": [{"client_id": "$id"}, {"client": "$name"}], "fields": ["quote_number", "status", "total"]},
        {"collection": "orders", "label": "Sales Orders", "match": [{"client_id": "$id"}], "fields": ["order_no", "amount", "status"]},
        {"collection": "projects", "label": "Projects", "match": [{"client_id": "$id"}, {"client": "$name"}], "fields": ["code", "name", "status", "progress"]},
        {"collection": "ra_bills", "label": "RA Bills", "match": [{"client_id": "$id"}], "fields": ["bill_no", "gross", "net_payable", "status"]},
    ],
    "projects": [
        {"collection": "purchase_requisitions", "label": "Purchase Requisitions", "match": [{"project_id": "$id"}, {"project": "$code"}, {"project_code": "$code"}], "fields": ["pr_no", "status", "total_amount"]},
        {"collection": "rfqs", "label": "RFQs", "match": [{"project_id": "$id"}, {"project_code": "$code"}], "fields": ["rfq_no", "status"]},
        {"collection": "purchase_orders", "label": "Purchase Orders", "match": [{"project_id": "$id"}, {"project": "$name"}, {"project_code": "$code"}], "fields": ["po_number", "vendor", "total", "status"]},
        {"collection": "grns", "label": "Goods Receipts", "match": [{"project_id": "$id"}, {"project_code": "$code"}], "fields": ["grn_no", "po_number", "status"]},
        {"collection": "dprs", "label": "Daily Site Reports", "match": [{"project_id": "$id"}, {"project_code": "$code"}], "fields": ["dpr_no", "date", "status"]},
        {"collection": "measurements", "label": "Measurements", "match": [{"project_id": "$id"}, {"project_code": "$code"}], "fields": ["measurement_no", "status", "billable_value"]},
        {"collection": "ra_bills", "label": "RA Bills", "match": [{"project_id": "$id"}, {"project_code": "$code"}], "fields": ["bill_no", "gross", "status"]},
        {"collection": "deployments", "label": "Deployments", "match": [{"project_id": "$id"}, {"project": "$code"}, {"project_code": "$code"}], "fields": ["employee_name", "site_role", "status"]},
        {"collection": "safety_reports", "label": "Safety Reports", "match": [{"project": "$name"}, {"project_id": "$id"}], "fields": ["report_id", "type", "severity", "status"]},
    ],
    "enquiries": [
        {"collection": "quotations", "label": "Quotations", "match": [{"enquiry_id": "$id"}], "fields": ["quote_number", "status", "total"]},
        {"collection": "orders", "label": "Sales Orders", "match": [{"enquiry_id": "$id"}], "fields": ["order_no", "amount", "status"]},
    ],
    "quotations": [
        {"collection": "orders", "label": "Sales Orders", "match": [{"quotation_id": "$id"}], "fields": ["order_no", "amount", "status"]},
    ],
    "purchase_requisitions": [
        {"collection": "rfqs", "label": "RFQs", "match": [{"pr_id": "$id"}], "fields": ["rfq_no", "status"]},
        {"collection": "purchase_orders", "label": "Purchase Orders", "match": [{"pr_id": "$id"}], "fields": ["po_number", "vendor", "total", "status"]},
    ],
    "rfqs": [
        {"collection": "purchase_orders", "label": "Purchase Orders", "match": [{"rfq_id": "$id"}], "fields": ["po_number", "vendor", "total", "status"]},
    ],
    "purchase_orders": [
        {"collection": "grns", "label": "Goods Receipts", "match": [{"po_id": "$id"}, {"po_number": "$po_number"}], "fields": ["grn_no", "status", "received_at"]},
        {"collection": "vendor_invoices", "label": "Vendor Invoices", "match": [{"po_id": "$id"}, {"po_number": "$po_number"}], "fields": ["invoice_no", "amount", "status"]},
    ],
    "measurements": [
        {"collection": "ra_bills", "label": "RA Bills", "match": [{"measurement_ids": "$id"}], "fields": ["bill_no", "gross", "status"]},
    ],
    "ra_bills": [
        {"collection": "payments_in", "label": "Payments", "match": [{"bill_ids": "$id"}], "fields": ["payment_no", "amount", "date"]},
    ],
    "vendors": [
        {"collection": "purchase_orders", "label": "Purchase Orders", "match": [{"vendor_id": "$id"}, {"vendor": "$name"}], "fields": ["po_number", "total", "status"]},
        {"collection": "rfqs", "label": "RFQs", "match": [{"vendor_ids": "$id"}], "fields": ["rfq_no", "status"]},
        {"collection": "vendor_invoices", "label": "Invoices", "match": [{"vendor_id": "$id"}], "fields": ["invoice_no", "amount", "status"]},
        {"collection": "vendor_evaluations", "label": "Evaluations", "match": [{"vendor_id": "$id"}], "fields": ["rating", "evaluated_on"]},
    ],
}


def _substitute(template: dict, parent: dict) -> dict:
    """Replace `$field` tokens in template values with parent[field]."""
    out: dict[str, Any] = {}
    for k, v in template.items():
        if isinstance(v, str) and v.startswith("$"):
            field = v[1:]
            if parent.get(field) is None:
                continue  # skip filters whose source value is missing
            out[k] = parent[field]
        else:
            out[k] = v
    return out


@router.get("/graph/{resource}/{record_id}")
async def linkage_graph(resource: str, record_id: str, user: dict = Depends(get_current_user)):
    """Return cross-module links for a given record.
    Response shape:
      {
        resource, record_id, anchor: {<parent doc minus _id>},
        groups: [{collection, label, count, items: [...]}]
      }
    """
    if resource not in LINK_MAP:
        raise HTTPException(status_code=404, detail=f"no link rules for resource '{resource}'")
    parent = await db[resource].find_one({"id": record_id}, {"_id": 0})
    if not parent:
        raise HTTPException(status_code=404, detail=f"{resource} not found")

    groups = []
    for rule in LINK_MAP[resource]:
        match_clauses = []
        for tmpl in rule["match"]:
            substituted = _substitute(tmpl, parent)
            if substituted:
                match_clauses.append(substituted)
        if not match_clauses:
            continue
        query: dict[str, Any] = {"$or": match_clauses} if len(match_clauses) > 1 else match_clauses[0]
        proj = {"_id": 0, "id": 1}
        for f in rule["fields"]:
            proj[f] = 1
        try:
            rows = await db[rule["collection"]].find(query, proj).limit(50).to_list(50)
        except Exception as e:
            logger.warning(f"linkage query {rule['collection']} failed: {e}")
            rows = []
        if rows:
            groups.append({
                "collection": rule["collection"],
                "label": rule["label"],
                "count": len(rows),
                "items": rows,
            })

    return {
        "resource": resource,
        "record_id": record_id,
        "anchor": parent,
        "groups": groups,
        "generated_at": now_iso(),
    }


# ────────────────────────────────────────────────────────────────────────
# 2. GOOGLE SHEETS LIVE LINK (read-only via published CSV)
# ────────────────────────────────────────────────────────────────────────
# Owner publishes a Google Sheet → File > Share > Publish to web > CSV.
# We store the URL + a friendly name per "channel" and offer:
#   - GET /linkage/sheets — list
#   - POST /linkage/sheets — add a channel
#   - DELETE /linkage/sheets/{id}
#   - GET /linkage/sheets/{id}/data — live fetch + CSV parse → JSON rows
# ────────────────────────────────────────────────────────────────────────

class SheetChannelIn(BaseModel):
    name: str
    csv_url: str
    description: str = ""


def _normalise_sheet_url(url: str) -> str:
    """Accept either a /pub?output=csv URL or a regular spreadsheet URL with /gid;
    leave the former unchanged and try to coerce the latter."""
    if not url:
        return url
    if "output=csv" in url or "/pub?" in url:
        return url
    if "/spreadsheets/d/" in url and "/gviz/" not in url:
        # Tell the user to use Publish to Web — but at least try the export endpoint.
        # Format: https://docs.google.com/spreadsheets/d/<ID>/export?format=csv&gid=<GID>
        if "/edit" in url:
            base = url.split("/edit")[0]
            gid = ""
            if "gid=" in url:
                gid = url.split("gid=")[1].split("&")[0].split("#")[0]
            return f"{base}/export?format=csv" + (f"&gid={gid}" if gid else "")
    return url


@router.get("/sheets")
async def list_sheets(user: dict = Depends(get_current_user)):
    rows = await db.sheet_channels.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return rows


@router.post("/sheets")
async def add_sheet(payload: SheetChannelIn, user: dict = Depends(get_current_user)):
    if user.get("role") not in {"super_admin", "director", "general_manager", "accounts_executive"}:
        raise HTTPException(status_code=403, detail="not allowed")
    record = {
        "id": new_id(),
        "name": payload.name.strip(),
        "csv_url": _normalise_sheet_url(payload.csv_url.strip()),
        "description": payload.description.strip(),
        "created_by": user.get("name") or user.get("email"),
        "created_at": now_iso(),
    }
    await db.sheet_channels.insert_one(record)
    record.pop("_id", None)
    return record


@router.delete("/sheets/{channel_id}")
async def delete_sheet(channel_id: str, user: dict = Depends(get_current_user)):
    if user.get("role") not in {"super_admin", "director"}:
        raise HTTPException(status_code=403, detail="not allowed")
    res = await db.sheet_channels.delete_one({"id": channel_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@router.get("/sheets/{channel_id}/data")
async def fetch_sheet_data(channel_id: str, user: dict = Depends(get_current_user)):
    """Live-fetch the published CSV and return parsed rows + headers + meta."""
    ch = await db.sheet_channels.find_one({"id": channel_id}, {"_id": 0})
    if not ch:
        raise HTTPException(status_code=404, detail="sheet channel not found")
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            r = await client.get(ch["csv_url"])
            r.raise_for_status()
            text = r.text
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"failed to fetch sheet: {e}")

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    headers = rows[0] if rows else []
    data = []
    for r in rows[1:]:
        # Pad short rows
        padded = r + [""] * (len(headers) - len(r))
        data.append(dict(zip(headers, padded)))
    # Persist last-sync info
    await db.sheet_channels.update_one(
        {"id": channel_id},
        {"$set": {"last_synced_at": now_iso(), "last_row_count": len(data)}},
    )
    return {
        "channel_id": channel_id,
        "name": ch["name"],
        "headers": headers,
        "row_count": len(data),
        "data": data[:500],   # cap response size
        "fetched_at": now_iso(),
    }


# ────────────────────────────────────────────────────────────────────────
# 3. TALLY XML SYNC (Tally Prime / ERP 9 HTTP-XML gateway)
# ────────────────────────────────────────────────────────────────────────
# Tally exposes an HTTP-XML interface (default port 9000). We do not push
# automatically; we provide:
#   - Settings persist (host, port, company)
#   - "Test" endpoint that sends a CompanyInfo collection request
#   - "Sync masters" endpoint that pulls Tally ledgers (customers/vendors)
#     into db.tally_ledgers for one-way reference
# Heavy bi-directional sync intentionally deferred.
# ────────────────────────────────────────────────────────────────────────

class TallyConfigIn(BaseModel):
    host: str = "localhost"
    port: int = 9000
    company: str = ""
    enabled: bool = True


@router.get("/tally/config")
async def get_tally_config(user: dict = Depends(get_current_user)):
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="super_admin only")
    doc = await db.settings.find_one({"_id": "tally"}, {"_id": 0}) or {}
    return {
        "host": doc.get("host", "localhost"),
        "port": doc.get("port", 9000),
        "company": doc.get("company", ""),
        "enabled": doc.get("enabled", False),
        "last_test_at": doc.get("last_test_at"),
        "last_test_ok": doc.get("last_test_ok"),
        "last_test_error": doc.get("last_test_error"),
        "last_sync_at": doc.get("last_sync_at"),
        "ledger_count": doc.get("ledger_count", 0),
    }


@router.put("/tally/config")
async def save_tally_config(payload: TallyConfigIn, user: dict = Depends(get_current_user)):
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="super_admin only")
    await db.settings.update_one(
        {"_id": "tally"},
        {"$set": {
            "host": payload.host.strip(),
            "port": payload.port,
            "company": payload.company.strip(),
            "enabled": payload.enabled,
            "updated_at": now_iso(),
        }},
        upsert=True,
    )
    return await get_tally_config(user=user)


async def _tally_request(host: str, port: int, body: str, timeout: int = 30) -> str:
    url = f"http://{host}:{port}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, content=body, headers={"Content-Type": "application/xml"})
        r.raise_for_status()
        return r.text


@router.post("/tally/test")
async def test_tally(user: dict = Depends(get_current_user)):
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="super_admin only")
    cfg = await db.settings.find_one({"_id": "tally"}, {"_id": 0}) or {}
    host, port = cfg.get("host", "localhost"), int(cfg.get("port", 9000))
    body = """<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>EXPORT</TALLYREQUEST><TYPE>COLLECTION</TYPE><ID>List of Companies</ID></HEADER><BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES><TDL><TDLMESSAGE><COLLECTION NAME="List of Companies" ISMODIFY="No"><TYPE>Company</TYPE><FETCH>Name</FETCH></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>"""
    try:
        text = await _tally_request(host, port, body, timeout=10)
        companies = [e.text for e in ET.fromstring(text).iter("NAME") if e.text]
        await db.settings.update_one(
            {"_id": "tally"},
            {"$set": {"last_test_at": now_iso(), "last_test_ok": True, "last_test_error": None}},
        )
        return {"ok": True, "companies": companies[:20], "host": host, "port": port}
    except Exception as e:
        err = str(e)
        await db.settings.update_one(
            {"_id": "tally"},
            {"$set": {"last_test_at": now_iso(), "last_test_ok": False, "last_test_error": err}},
        )
        return {"ok": False, "error": err, "host": host, "port": port}


@router.post("/tally/sync-masters")
async def sync_masters(user: dict = Depends(get_current_user)):
    """Pull ledgers (customers + vendors) from Tally for reference."""
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="super_admin only")
    cfg = await db.settings.find_one({"_id": "tally"}, {"_id": 0}) or {}
    if not cfg.get("enabled"):
        raise HTTPException(status_code=400, detail="Tally integration disabled")
    host, port = cfg.get("host", "localhost"), int(cfg.get("port", 9000))
    body = """<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>EXPORT</TALLYREQUEST><TYPE>COLLECTION</TYPE><ID>Ledgers</ID></HEADER><BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES><TDL><TDLMESSAGE><COLLECTION NAME="Ledgers" ISMODIFY="No"><TYPE>Ledger</TYPE><FETCH>Name,Parent,LedgerPhone,Email,GSTIN</FETCH></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>"""
    try:
        text = await _tally_request(host, port, body, timeout=60)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Tally fetch failed: {e}")
    rows = []
    for ldg in ET.fromstring(text).iter("LEDGER"):
        rows.append({
            "name": ldg.findtext("NAME") or ldg.attrib.get("NAME"),
            "parent": ldg.findtext("PARENT"),
            "phone": ldg.findtext("LEDGERPHONE"),
            "email": ldg.findtext("EMAIL"),
            "gstin": ldg.findtext("GSTIN"),
        })
    await db.tally_ledgers.delete_many({})
    if rows:
        await db.tally_ledgers.insert_many([{**r, "id": new_id(), "synced_at": now_iso()} for r in rows])
    await db.settings.update_one(
        {"_id": "tally"},
        {"$set": {"last_sync_at": now_iso(), "ledger_count": len(rows)}},
    )
    return {"ok": True, "ledger_count": len(rows)}


@router.get("/tally/ledgers")
async def list_tally_ledgers(q: str = Query("", description="search"), user: dict = Depends(get_current_user)):
    filt: dict = {}
    if q:
        import re
        safe = re.escape(q)
        filt = {"$or": [{"name": {"$regex": safe, "$options": "i"}}, {"gstin": {"$regex": safe, "$options": "i"}}]}
    rows = await db.tally_ledgers.find(filt, {"_id": 0}).sort("name", 1).limit(200).to_list(200)
    return rows
