"""PM Handover Pack — one-click snapshot for an incoming Project Manager.

GET /projects/{pid}/handover-pack      → JSON (open requests, pending approvals,
                                          accounts payment queue, pending bills, delayed items)
GET /projects/{pid}/handover-pack.pdf  → branded PDF download
"""
from datetime import date, datetime
from io import BytesIO
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from core import db, require_permission, now_iso

router = APIRouter(prefix="/projects", tags=["pm-handover"])

OPEN_STATUSES = ["pending_approval", "with_dept", "pr_raised", "sourcing"]
STATUS_LABEL = {"pending_approval": "Pending Approval", "with_dept": "With Department",
                "pr_raised": "PR Raised", "sourcing": "Sourcing", "fulfilled": "Fulfilled"}
PAY_LABEL = {"pending_verification": "Accounts: Pending Verification", "verified": "Accounts: Verified",
             "in_bank_file": "Accounts: In Bank File", "rejected": "Accounts: Rejected", "paid": "Paid"}
APPROVAL_DELAY_DAYS = 3
ACCOUNTS_DELAY_DAYS = 7


def _days_since(iso: str) -> int:
    try:
        return (date.today() - datetime.fromisoformat(iso[:10]).date()).days
    except Exception:
        return 0


async def _build_pack(pid: str, user: dict) -> Dict[str, Any]:
    proj = await db.projects.find_one({"$or": [{"id": pid}, {"code": pid}]}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")
    today = date.today().isoformat()

    reqs = await db.project_requests.find(
        {"project_id": proj["id"], "status": {"$in": OPEN_STATUSES}}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    pay_ids = [r["id"] for r in reqs if r.get("is_payment")]
    vmap = {v["request_id"]: v async for v in db.payment_verifications.find(
        {"request_id": {"$in": pay_ids}}, {"_id": 0})} if pay_ids else {}

    open_requests, pending_approvals, accounts_queue, delayed = [], [], [], []
    for r in reqs:
        age = _days_since(r.get("created_at") or "")
        base = {"request_no": r["request_no"], "type": r.get("request_type_label"),
                "description": r.get("description") or "", "est_value": r.get("est_value") or 0,
                "status": STATUS_LABEL.get(r["status"], r["status"]), "need_by": r.get("need_by"),
                "raised_by": r.get("created_by"), "raised_at": (r.get("created_at") or "")[:16].replace("T", " "),
                "age_days": age, "vendor": r.get("vendor"), "employee_name": r.get("employee_name")}
        open_requests.append(base)

        if r["status"] == "pending_approval":
            chain = r.get("chain") or []
            idx = r.get("current_step") or 0
            pending_with = (chain[idx].get("label") if idx < len(chain) else "—") if chain else "—"
            pending_approvals.append({**base, "pending_with": pending_with})
            if age > APPROVAL_DELAY_DAYS:
                delayed.append({**base, "reason": f"Approval pending with {pending_with} for {age} days"})

        if r.get("is_payment") and r["status"] != "pending_approval":
            v = vmap.get(r["id"])
            stage = (v or {}).get("stage") or "pending_verification"
            if stage != "paid":
                acc_age = _days_since((v or {}).get("verified_at") or r.get("approved_at") or r.get("created_at") or "")
                accounts_queue.append({**base, "pay_stage": PAY_LABEL.get(stage, stage),
                                       "verified_amount": (v or {}).get("verified_amount"),
                                       "bank_file_no": (v or {}).get("bank_file_no")})
                if stage == "pending_verification" and acc_age > ACCOUNTS_DELAY_DAYS:
                    delayed.append({**base, "reason": f"Awaiting Accounts verification for {acc_age} days"})

        if r.get("need_by") and r["need_by"] < today:
            overdue = _days_since(r["need_by"])
            delayed.append({**base, "reason": f"Need-by date passed {overdue} days ago"})

    bills = await db.bill_requests.find(
        {"project_code": proj["code"], "status": "pending_approval"}, {"_id": 0}).to_list(200)
    pending_bills = [{"request_no": b["request_no"], "bill_type": b.get("bill_type"),
                      "expected_amount": b.get("expected_amount") or 0,
                      "period": f"{b.get('period_from') or ''} → {b.get('period_to') or ''}",
                      "requested_by": b.get("requested_by"),
                      "age_days": _days_since(b.get("created_at") or "")} for b in bills]
    for b in pending_bills:
        if b["age_days"] > APPROVAL_DELAY_DAYS:
            delayed.append({"request_no": b["request_no"], "type": f"Bill Request ({b['bill_type']})",
                            "est_value": b["expected_amount"],
                            "reason": f"Bill approval pending for {b['age_days']} days"})

    return {
        "project": {"id": proj["id"], "code": proj["code"], "name": proj.get("name"),
                    "client": proj.get("client"), "site": proj.get("site"), "status": proj.get("status"),
                    "project_manager": proj.get("project_manager_name") or proj.get("manager"),
                    "start_date": proj.get("start_date"), "end_date": proj.get("end_date"),
                    "budget": proj.get("budget"), "progress": proj.get("progress")},
        "generated_at": now_iso(), "generated_by": user.get("name") or user.get("email"),
        "summary": {"open_requests": len(open_requests), "pending_approvals": len(pending_approvals),
                    "accounts_queue": len(accounts_queue), "pending_bills": len(pending_bills),
                    "delayed_items": len(delayed),
                    "open_value": round(sum(float(r["est_value"] or 0) for r in open_requests), 2)},
        "open_requests": open_requests, "pending_approvals": pending_approvals,
        "accounts_queue": accounts_queue, "pending_bills": pending_bills, "delayed": delayed,
    }


@router.get("/{pid}/handover-pack")
async def handover_pack(pid: str, user: dict = Depends(require_permission("projects", "read"))):
    return await _build_pack(pid, user)


@router.get("/{pid}/handover-pack.pdf")
async def handover_pack_pdf(pid: str, user: dict = Depends(require_permission("projects", "read"))):
    pack = await _build_pack(pid, user)
    pdf = _render_pdf(pack)
    fname = f"HANDOVER_{pack['project']['code']}.pdf"
    return StreamingResponse(BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


def _render_pdf(pack: Dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from pdf_watermark import attach_watermark

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm)
    attach_watermark(doc, width_mm=180.0)
    styles = getSampleStyleSheet()
    cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=7, leading=9)
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=15, textColor=colors.HexColor("#0f172a"), spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=10.5, textColor=colors.HexColor("#0f172a"),
                        spaceBefore=8, spaceAfter=3)
    meta = ParagraphStyle("meta", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#475569"))
    p = pack["project"]
    s = pack["summary"]
    story = [
        Paragraph(f"PM Handover Pack — {p['code']}", h1),
        Paragraph(f"{p.get('name') or ''} · Client: {p.get('client') or '—'} · Site: {p.get('site') or '—'}", meta),
        Paragraph(f"Current PM: <b>{p.get('project_manager') or '—'}</b> · Contract: {p.get('start_date') or '—'} → "
                  f"{p.get('end_date') or '—'} · Status: {p.get('status') or '—'}", meta),
        Paragraph(f"Generated {pack['generated_at'][:16].replace('T', ' ')} by {pack['generated_by']}", meta),
        Spacer(1, 4 * mm),
    ]
    sum_tbl = Table([["Open Requests", "Pending Approvals", "With Accounts", "Pending Bills", "Delayed Items", "Open Value (Rs)"],
                     [s["open_requests"], s["pending_approvals"], s["accounts_queue"], s["pending_bills"],
                      s["delayed_items"], f"{s['open_value']:,.0f}"]],
                    colWidths=[45 * mm] * 6)
    sum_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5), ("FONTSIZE", (0, 1), (-1, 1), 11),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(sum_tbl)

    def section(title: str, headers: List[str], data_rows: List[List[Any]], widths: List[float]):
        story.append(Paragraph(title, h2))
        if not data_rows:
            story.append(Paragraph("None — nothing pending in this section.", meta))
            return
        tbl_data = [headers] + [[Paragraph(str(x if x not in (None, "") else "—"), cell) for x in row] for row in data_rows]
        t = Table(tbl_data, colWidths=[w * mm for w in widths], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, 0), 7),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story.append(t)

    inr = lambda v: f"{float(v or 0):,.0f}"  # noqa: E731
    section("1 · Open Requests", ["Request #", "Type", "Description", "Value (Rs)", "Status", "Need By", "Raised By", "Raised At", "Age (d)"],
            [[r["request_no"], r["type"], r["description"][:120], inr(r["est_value"]), r["status"],
              r["need_by"], r["raised_by"], r["raised_at"], r["age_days"]] for r in pack["open_requests"]],
            [24, 32, 62, 20, 26, 20, 30, 26, 14])
    section("2 · Pending Approvals", ["Request #", "Type", "Value (Rs)", "Pending With", "Raised By", "Raised At", "Age (d)"],
            [[r["request_no"], r["type"], inr(r["est_value"]), r["pending_with"], r["raised_by"],
              r["raised_at"], r["age_days"]] for r in pack["pending_approvals"]],
            [28, 45, 25, 50, 40, 40, 20])
    section("3 · Payments with Accounts", ["Request #", "Type", "Paid To", "Value (Rs)", "Verified Amt (Rs)", "Accounts Stage", "Bank File"],
            [[r["request_no"], r["type"], r.get("vendor") or r.get("employee_name"), inr(r["est_value"]),
              inr(r["verified_amount"]) if r.get("verified_amount") else "—", r["pay_stage"], r.get("bank_file_no")]
             for r in pack["accounts_queue"]],
            [28, 42, 45, 25, 30, 50, 28])
    section("4 · Pending Bill Requests", ["Request #", "Bill Type", "Expected Amt (Rs)", "Period", "Requested By", "Age (d)"],
            [[b["request_no"], b["bill_type"], inr(b["expected_amount"]), b["period"], b["requested_by"], b["age_days"]]
             for b in pack["pending_bills"]],
            [30, 40, 32, 60, 45, 20])
    section("5 · Delayed Items (action needed)", ["Request #", "Item", "Value (Rs)", "Why delayed"],
            [[d["request_no"], d.get("type"), inr(d.get("est_value")), d["reason"]] for d in pack["delayed"]],
            [30, 55, 28, 130])
    doc.build(story)
    return buf.getvalue()
