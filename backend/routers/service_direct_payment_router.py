"""Direct Payment Requests — repeat payments to vendors already paid through the
Service workflow, without raising a new SR / RFQ / PO / SRN.

Lifecycle: pending_approval → (Super Admin) payment_pending → paid, or rejected /
withdrawn. Approval hands the request to the Accounts Payment Processing Center
(a `project_requests` payment row, source = service_direct_payment); the paid
callback closes the loop. Linking to an earlier Service PO is optional; amounts
have no system cap — a warning is returned when the net exceeds the vendor's last
paid invoice.
"""
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from audit import audit
from core import db, get_current_user, require_permission, now_iso, new_id
from dedupe import ensure_no_duplicate
from sequences import next_sequence
from routers.service_workflow_router import ACCOUNTS_ROLES, PROC_ROLES, _hist, _uname, _ip

logger = logging.getLogger("erp")
router = APIRouter(prefix="/service-direct-payments", tags=["service-direct-payments"])

LOGISTICS_ROLES = {"manager_log", "manager_l_o_g", "logistics_executive", "logistics_manager"}
RAISE_ROLES = ACCOUNTS_ROLES | PROC_ROLES | LOGISTICS_ROLES
APPROVER_ROLE = "super_admin"
OPEN_STATUSES = ("pending_approval", "payment_pending")
PAID_INVOICE_STATUSES = ("payment_pending", "paid")
LIVE_PO_STATUSES = ("approved", "issued", "in_progress", "completed", "closed")


class DirectPaymentIn(BaseModel):
    vendor_id: str
    ref_po_id: Optional[str] = None
    project_code: Optional[str] = None
    project_name: Optional[str] = None
    service_period: str = ""          # YYYY-MM
    description: str = ""
    vendor_invoice_no: str = ""
    invoice_date: str = ""
    invoice_amount: float = 0.0
    tax_amount: float = 0.0
    other_charges: float = 0.0
    tds_amount: float = 0.0
    payment_amount: Optional[float] = None
    due_date: str = ""
    remarks: str = ""


class ActionIn(BaseModel):
    action: str = "approve"  # approve | reject | withdraw
    remarks: str = ""


class InboxIn(BaseModel):
    remarks: Optional[str] = ""


def _can_raise(user: dict) -> bool:
    return user.get("role") in RAISE_ROLES


def _require_raise(user: dict):
    if not _can_raise(user):
        raise HTTPException(403, "Only Accounts, Procurement and Logistics roles can raise Direct Payment Requests")


def _require_approver(user: dict):
    if user.get("role") != APPROVER_ROLE:
        raise HTTPException(403, "Direct Payment Requests are approved by the Super Admin only")


async def _dp(dp_id: str) -> dict:
    r = await db.svc_direct_payments.find_one({"id": dp_id}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Direct Payment Request not found")
    return r


async def _eligible_vendor_ids() -> set:
    inv_ids = await db.svc_invoices.distinct("vendor_id", {"status": {"$in": list(PAID_INVOICE_STATUSES)}, "vendor_id": {"$ne": None}})
    po_ids = await db.svc_pos.distinct("vendor_id", {"status": {"$in": list(LIVE_PO_STATUSES)}, "vendor_id": {"$ne": None}})
    return {v for v in inv_ids + po_ids if v}


async def _vendor_summary(vendor_id: str) -> dict:
    v = await db.vendors.find_one({"id": vendor_id}, {"_id": 0, "id": 1, "name": 1, "code": 1, "gst": 1, "pan": 1,
                                                    "email": 1, "phone": 1, "bank_accounts": 1, "status": 1})
    if not v:
        raise HTTPException(404, "Vendor not found")
    last_po = await db.svc_pos.find_one({"vendor_id": vendor_id, "status": {"$in": list(LIVE_PO_STATUSES)}},
                                        {"_id": 0, "id": 1, "po_no": 1, "sr_no": 1, "sr_id": 1, "project_code": 1,
                                         "project_name": 1, "total_value": 1, "paid_amount": 1, "status": 1,
                                         "service_category": 1, "created_at": 1}, sort=[("created_at", -1)])
    last_paid = await db.svc_invoices.find_one({"vendor_id": vendor_id, "status": "paid"},
                                               {"_id": 0, "inv_no": 1, "vendor_invoice_no": 1, "net_payable": 1,
                                                "invoice_amount": 1, "payment": 1, "invoice_date": 1},
                                               sort=[("payment.paid_at", -1), ("updated_at", -1)])
    last_dp = await db.svc_direct_payments.find_one({"vendor_id": vendor_id, "status": "paid"},
                                                    {"_id": 0, "dp_no": 1, "net_payable": 1, "payment_amount": 1,
                                                     "payment": 1, "service_period": 1}, sort=[("payment.paid_at", -1)])
    agg = [{"$match": {"vendor_id": vendor_id, "status": "paid"}},
           {"$group": {"_id": None, "n": {"$sum": 1}, "total": {"$sum": "$net_payable"}}}]
    inv_tot = await db.svc_invoices.aggregate(agg).to_list(1)
    dp_tot = await db.svc_direct_payments.aggregate(
        [{"$match": {"vendor_id": vendor_id, "status": "paid"}},
         {"$group": {"_id": None, "n": {"$sum": 1}, "total": {"$sum": "$payment_amount"}}}]).to_list(1)
    open_dp = await db.svc_direct_payments.count_documents({"vendor_id": vendor_id, "status": {"$in": list(OPEN_STATUSES)}})
    last_paid_amount = None
    if last_dp and (not last_paid or (last_dp.get("payment") or {}).get("paid_at", "") > (last_paid.get("payment") or {}).get("paid_at", "")):
        last_paid_amount = float(last_dp.get("payment_amount") or 0)
    elif last_paid:
        last_paid_amount = float(last_paid.get("net_payable") or 0)
    return {"vendor": v, "last_po": last_po, "last_paid_invoice": last_paid, "last_direct_payment": last_dp,
            "last_paid_amount": last_paid_amount,
            "service_invoices_paid": (inv_tot[0]["n"] if inv_tot else 0),
            "service_invoices_total": round(float(inv_tot[0]["total"]) if inv_tot else 0.0, 2),
            "direct_payments_paid": (dp_tot[0]["n"] if dp_tot else 0),
            "direct_payments_total": round(float(dp_tot[0]["total"]) if dp_tot else 0.0, 2),
            "open_direct_payments": open_dp}


@router.get("/meta")
async def meta(user: dict = Depends(require_permission("service_workflow", "read"))):
    ids = await _eligible_vendor_ids()
    vendors = await db.vendors.find({"id": {"$in": list(ids)}},
                                    {"_id": 0, "id": 1, "name": 1, "code": 1, "gst": 1, "status": 1}).sort("name", 1).to_list(2000)
    return {"can_raise": _can_raise(user), "can_approve": user.get("role") == APPROVER_ROLE,
            "vendors": vendors}


@router.get("/vendors/{vendor_id}/summary")
async def vendor_summary(vendor_id: str, user: dict = Depends(require_permission("service_workflow", "read"))):
    if vendor_id not in await _eligible_vendor_ids():
        raise HTTPException(400, "This vendor has not been paid through the Service workflow yet — raise a Service Request instead")
    s = await _vendor_summary(vendor_id)
    s["pos"] = await db.svc_pos.find({"vendor_id": vendor_id, "status": {"$in": list(LIVE_PO_STATUSES)}},
                                     {"_id": 0, "id": 1, "po_no": 1, "sr_no": 1, "sr_id": 1, "project_code": 1,
                                      "project_name": 1, "total_value": 1, "paid_amount": 1, "status": 1,
                                      "service_category": 1}).sort("created_at", -1).to_list(50)
    return s


@router.get("/vendors/{vendor_id}/history")
async def vendor_history(vendor_id: str, user: dict = Depends(require_permission("service_workflow", "read"))):
    invs = await db.svc_invoices.find({"vendor_id": vendor_id, "status": {"$in": list(PAID_INVOICE_STATUSES)}},
                                      {"_id": 0, "id": 1, "inv_no": 1, "vendor_invoice_no": 1, "invoice_date": 1,
                                       "net_payable": 1, "status": 1, "payment": 1, "po_no": 1, "sr_no": 1,
                                       "project_code": 1}).sort("created_at", -1).to_list(200)
    dps = await db.svc_direct_payments.find({"vendor_id": vendor_id, "status": {"$ne": "withdrawn"}},
                                            {"_id": 0, "history": 0}).sort("created_at", -1).to_list(200)
    rows = [{"kind": "service_invoice", "ref": i["inv_no"], "vendor_invoice_no": i.get("vendor_invoice_no"),
             "date": i.get("invoice_date"), "amount": i.get("net_payable"), "status": i.get("status"),
             "utr_no": (i.get("payment") or {}).get("utr_no"), "paid_date": (i.get("payment") or {}).get("paid_date"),
             "link": i.get("po_no"), "project_code": i.get("project_code")} for i in invs]
    rows += [{"kind": "direct_payment", "ref": d["dp_no"], "vendor_invoice_no": d.get("vendor_invoice_no"),
              "date": d.get("invoice_date"), "amount": d.get("payment_amount"), "status": d.get("status"),
              "utr_no": (d.get("payment") or {}).get("utr_no"), "paid_date": (d.get("payment") or {}).get("paid_date"),
              "link": d.get("ref_po_no"), "project_code": d.get("project_code"), "service_period": d.get("service_period")}
             for d in dps]
    rows.sort(key=lambda r: (r.get("paid_date") or r.get("date") or ""), reverse=True)
    return rows


def _amounts(p: DirectPaymentIn) -> dict:
    if p.invoice_amount <= 0:
        raise HTTPException(400, "Invoice amount must be > 0")
    if min(p.tax_amount, p.other_charges, p.tds_amount) < 0:
        raise HTTPException(400, "Amounts cannot be negative")
    net = round(p.invoice_amount + p.tax_amount + p.other_charges - p.tds_amount, 2)
    if net <= 0:
        raise HTTPException(400, "Net payable must be > 0")
    pay = round(float(p.payment_amount) if p.payment_amount is not None else net, 2)
    if pay <= 0:
        raise HTTPException(400, "Payment amount must be > 0")
    if pay > net + 0.01:
        raise HTTPException(400, f"Payment amount cannot exceed the net payable ₹{net:,.2f}")
    return {"net_payable": net, "payment_amount": pay}


async def _ref_po(p: DirectPaymentIn, vendor_id: str) -> dict:
    if not p.ref_po_id:
        return {"ref_po_id": None, "ref_po_no": None, "ref_sr_id": None, "ref_sr_no": None}
    po = await db.svc_pos.find_one({"id": p.ref_po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "Referenced Service PO not found")
    if po.get("vendor_id") != vendor_id:
        raise HTTPException(400, "The referenced PO belongs to a different vendor")
    out = {"ref_po_id": po["id"], "ref_po_no": po.get("po_no"), "ref_sr_id": po.get("sr_id"), "ref_sr_no": po.get("sr_no")}
    if not p.project_code:
        out.update(project_code=po.get("project_code"), project_name=po.get("project_name"))
    return out


async def _duplicate_checks(p: DirectPaymentIn, vendor: dict, user: dict, request: Request, exclude_id: str = ""):
    inv_no = (p.vendor_invoice_no or "").strip()
    excl = {"id": {"$ne": exclude_id}} if exclude_id else {}
    if inv_no:
        await ensure_no_duplicate(
            module="svc_direct_payments", collection="svc_direct_payments", no_field="dp_no",
            query={"vendor_id": vendor["id"], "vendor_invoice_no": inv_no, "status": {"$nin": ["rejected", "withdrawn"]}, **excl},
            message=f"Vendor invoice '{inv_no}' from {vendor.get('name')} is already requested as {{no}}.",
            user=user, request=request)
        await ensure_no_duplicate(
            module="svc_direct_payments", collection="svc_invoices", no_field="inv_no",
            query={"vendor_id": vendor["id"], "vendor_invoice_no": inv_no, "status": {"$ne": "rejected"}},
            message=f"Vendor invoice '{inv_no}' from {vendor.get('name')} is already booked as service invoice {{no}}.",
            user=user, request=request)
    if p.service_period:
        same = await db.svc_direct_payments.find_one(
            {"vendor_id": vendor["id"], "service_period": p.service_period, "status": {"$in": list(OPEN_STATUSES)},
             "payment_amount": round(float(p.payment_amount if p.payment_amount is not None else
                                           p.invoice_amount + p.tax_amount + p.other_charges - p.tds_amount), 2), **excl},
            {"_id": 0, "dp_no": 1})
        if same:
            raise HTTPException(409, f"An identical request for {p.service_period} is already open as {same['dp_no']}")


def _warnings(amounts: dict, summary: dict) -> List[str]:
    out = []
    lp = summary.get("last_paid_amount")
    if lp and amounts["payment_amount"] > lp + 0.01:
        out.append(f"Payment ₹{amounts['payment_amount']:,.2f} exceeds the vendor's last paid amount ₹{lp:,.2f}")
    if summary.get("open_direct_payments"):
        out.append(f"{summary['open_direct_payments']} other Direct Payment request(s) for this vendor are still open")
    return out


@router.post("")
async def create_direct_payment(p: DirectPaymentIn, request: Request, user: dict = Depends(get_current_user)):
    _require_raise(user)
    if p.vendor_id not in await _eligible_vendor_ids():
        raise HTTPException(400, "Direct Payments are only for vendors already paid through the Service workflow")
    summary = await _vendor_summary(p.vendor_id)
    vendor = summary["vendor"]
    amounts = _amounts(p)
    ref = await _ref_po(p, p.vendor_id)
    await _duplicate_checks(p, vendor, user, request)
    warnings = _warnings(amounts, summary)
    doc = {**p.dict(), **ref, **amounts,
           "project_code": p.project_code or ref.get("project_code"), "project_name": p.project_name or ref.get("project_name"),
           "vendor_invoice_no": (p.vendor_invoice_no or "").strip(),
           "invoice_date": p.invoice_date or now_iso()[:10],
           "id": new_id(), "dp_no": await next_sequence("SDP"),
           "vendor_name": vendor.get("name"), "vendor_code": vendor.get("code"), "vendor_gstin": vendor.get("gst"),
           "status": "pending_approval", "warnings": warnings,
           "history": [_hist(user, "raised", "; ".join(warnings), "", "pending_approval")],
           "created_by": _uname(user), "created_by_id": user.get("id"), "created_by_role": user.get("role"),
           "created_at": now_iso(), "updated_at": now_iso()}
    await db.svc_direct_payments.insert_one(dict(doc))
    await audit(user=user, action="svc_direct_payment_create", resource="service_direct_payment",
                record_id=doc["id"], after={"dp_no": doc["dp_no"], "vendor": vendor.get("name"),
                                            "payment_amount": amounts["payment_amount"], "warnings": warnings}, ip=_ip(request))
    return doc


@router.get("")
async def list_direct_payments(status: str = "", vendor: str = "", q: str = "",
                               user: dict = Depends(require_permission("service_workflow", "read"))):
    fl: dict = {}
    if status:
        fl["status"] = status
    if vendor:
        fl["$or"] = [{"vendor_id": vendor}, {"vendor_name": {"$regex": vendor, "$options": "i"}}]
    if q:
        fl.setdefault("$and", []).append({"$or": [
            {"dp_no": {"$regex": q, "$options": "i"}}, {"vendor_name": {"$regex": q, "$options": "i"}},
            {"vendor_invoice_no": {"$regex": q, "$options": "i"}}, {"ref_po_no": {"$regex": q, "$options": "i"}},
            {"service_period": {"$regex": q, "$options": "i"}}]})
    return await db.svc_direct_payments.find(fl, {"_id": 0, "history": 0}).sort("created_at", -1).to_list(500)


@router.get("/{dp_id}")
async def get_direct_payment(dp_id: str, user: dict = Depends(require_permission("service_workflow", "read"))):
    dp = await _dp(dp_id)
    pr = await db.project_requests.find_one({"source": "service_direct_payment", "source_id": dp_id}, {"_id": 0, "id": 1})
    ver = await db.payment_verifications.find_one({"request_id": pr["id"]}, {"_id": 0}) if pr else None
    return {**dp, "queue_stage": (ver or {}).get("stage") or ("pending_verification" if pr else None)}


@router.put("/{dp_id}")
async def update_direct_payment(dp_id: str, p: DirectPaymentIn, request: Request, user: dict = Depends(get_current_user)):
    dp = await _dp(dp_id)
    if dp["status"] != "pending_approval":
        raise HTTPException(400, "Only requests awaiting approval can be edited")
    if not (user.get("id") == dp.get("created_by_id") or user.get("role") == APPROVER_ROLE):
        raise HTTPException(403, "Only the requester or the Super Admin can edit this request")
    if p.vendor_id != dp["vendor_id"]:
        raise HTTPException(400, "Vendor cannot be changed — withdraw and raise a new request")
    summary = await _vendor_summary(p.vendor_id)
    amounts = _amounts(p)
    ref = await _ref_po(p, p.vendor_id)
    await _duplicate_checks(p, summary["vendor"], user, request, exclude_id=dp_id)
    warnings = _warnings(amounts, summary)
    upd = {**p.dict(), **ref, **amounts,
           "project_code": p.project_code or ref.get("project_code"), "project_name": p.project_name or ref.get("project_name"),
           "vendor_invoice_no": (p.vendor_invoice_no or "").strip(), "warnings": warnings, "updated_at": now_iso()}
    await db.svc_direct_payments.update_one({"id": dp_id}, {
        "$set": upd, "$push": {"history": _hist(user, "edited", f"payment ₹{amounts['payment_amount']:,.2f}")}})
    await audit(user=user, action="svc_direct_payment_update", resource="service_direct_payment", record_id=dp_id,
                before={"payment_amount": dp.get("payment_amount")}, after={"payment_amount": amounts["payment_amount"]},
                ip=_ip(request))
    return await _dp(dp_id)


async def _push_to_payment_queue(dp: dict, user: dict) -> str:
    existing = await db.project_requests.find_one({"source": "service_direct_payment", "source_id": dp["id"]}, {"_id": 0, "id": 1})
    if existing:
        return existing["id"]
    pr_id = new_id()
    await db.project_requests.insert_one({
        "id": pr_id, "request_no": dp["dp_no"],
        "request_type": "service_direct_payment", "request_type_label": "Direct Payment (Service Vendor)",
        "is_payment": True, "is_stockable": False, "owning_dept": "procurement",
        "status": "with_dept", "payment_status": "payment_pending",
        "source": "service_direct_payment", "source_id": dp["id"],
        "project_code": dp.get("project_code"), "project_name": dp.get("project_name"),
        "vendor_id": dp.get("vendor_id"), "vendor": dp.get("vendor_name"), "vendor_name": dp.get("vendor_name"),
        "invoice_no": dp.get("vendor_invoice_no"), "invoice_date": dp.get("invoice_date"), "due_date": dp.get("due_date"),
        "est_value": float(dp["payment_amount"]), "amount": float(dp["payment_amount"]),
        "pay_debit_account_code": "5150",
        "description": (f"Direct payment {dp['dp_no']} — {dp.get('vendor_name')}"
                        + (f" · {dp.get('service_period')}" if dp.get("service_period") else "")
                        + (f" · ref PO {dp.get('ref_po_no')}" if dp.get("ref_po_no") else "")
                        + (f" · {dp.get('description')}" if dp.get("description") else "")),
        "approved_at": (dp.get("approval") or {}).get("at"), "approved_by": (dp.get("approval") or {}).get("by"),
        "items": [], "chain": [], "current_step": None,
        "created_by": dp.get("created_by"), "created_by_id": dp.get("created_by_id"), "created_at": now_iso()})
    try:
        from file_links import mirror_files
        await mirror_files("service_direct_payments", dp["id"], "project_requests", pr_id)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Direct payment document auto-link skipped: {e}")
    return pr_id


@router.post("/{dp_id}/action")
async def direct_payment_action(dp_id: str, p: ActionIn, request: Request, user: dict = Depends(get_current_user)):
    dp = await _dp(dp_id)
    if p.action not in ("approve", "reject", "withdraw"):
        raise HTTPException(400, "action must be approve | reject | withdraw")
    if dp["status"] != "pending_approval":
        raise HTTPException(400, f"Request is not awaiting approval (status '{dp['status']}')")
    if p.action == "withdraw":
        if not (user.get("id") == dp.get("created_by_id") or user.get("role") == APPROVER_ROLE):
            raise HTTPException(403, "Only the requester can withdraw this request")
        to = "withdrawn"
    else:
        _require_approver(user)
        if p.action == "reject" and not (p.remarks or "").strip():
            raise HTTPException(400, "Remarks are required to reject a Direct Payment Request")
        to = "payment_pending" if p.action == "approve" else "rejected"
    stamp = {"action": p.action, "by": _uname(user), "by_id": user.get("id"), "role": user.get("role"),
             "at": now_iso(), "remarks": p.remarks or ""}
    await db.svc_direct_payments.update_one({"id": dp_id}, {
        "$set": {"status": to, "updated_at": now_iso(), "approval": stamp},
        "$push": {"history": _hist(user, p.action, p.remarks or "", "pending_approval", to)}})
    if p.action == "approve":
        dp = await _dp(dp_id)
        pr_id = await _push_to_payment_queue(dp, user)
        await db.svc_direct_payments.update_one({"id": dp_id}, {"$set": {"payment_request_id": pr_id}})
    await audit(user=user, action=f"svc_direct_payment_{p.action}", resource="service_direct_payment",
                record_id=dp_id, after={"dp_no": dp["dp_no"], "status": to, "remarks": p.remarks}, ip=_ip(request))
    return await _dp(dp_id)


@router.post("/{dp_id}/inbox-approve")
async def inbox_approve(dp_id: str, p: InboxIn, request: Request, user: dict = Depends(get_current_user)):
    return await direct_payment_action(dp_id, ActionIn(action="approve", remarks=p.remarks or ""), request, user)


@router.post("/{dp_id}/inbox-reject")
async def inbox_reject(dp_id: str, p: InboxIn, request: Request, user: dict = Depends(get_current_user)):
    return await direct_payment_action(dp_id, ActionIn(action="reject", remarks=p.remarks or ""), request, user)


async def on_direct_payment_paid(dp_id: str, utr_no: str, paid_date: str, user: dict):
    dp = await db.svc_direct_payments.find_one({"id": dp_id}, {"_id": 0})
    if not dp or dp.get("status") == "paid":
        return
    await db.svc_direct_payments.update_one({"id": dp_id}, {
        "$set": {"status": "paid", "updated_at": now_iso(),
                 "payment": {"utr_no": utr_no, "paid_date": paid_date, "paid_by": _uname(user), "paid_at": now_iso()}},
        "$push": {"history": _hist(user, "paid", f"UTR {utr_no}", "payment_pending", "paid")}})
    if dp.get("ref_po_id"):
        await db.svc_pos.update_one({"id": dp["ref_po_id"]}, {
            "$inc": {"direct_paid_amount": float(dp["payment_amount"])},
            "$push": {"history": _hist(user, "direct_payment_recorded",
                                       f"{dp['dp_no']} ₹{float(dp['payment_amount']):,.2f} · UTR {utr_no}")}})
