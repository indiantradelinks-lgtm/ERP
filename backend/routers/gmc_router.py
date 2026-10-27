"""HR · Group Medical (GMC) Policy management.

Policies (insurer/policy no/period) + member enrolment pulled from the
Employee Master (single source of truth). Members can be filtered
project-wise, designation-wise or head-office-wise. When an employee's
exit/FNF is finalised the member row is auto-removed (see hr/exit_fnf.py).
Extras: dependents (spouse/kids) with over-20 kid flags, weekly HR review
digest, insurer update email with Excel attachment, bulk upload/template.
"""
from __future__ import annotations

import base64
import io
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core import db, require_permission, now_iso, new_id
from audit import audit
from exports import to_excel, to_pdf
from offload import run_blocking

router = APIRouter(tags=["gmc"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


KID_AGE_FLAG = 20


def _age(dob: Optional[str]) -> Optional[int]:
    if not dob:
        return None
    try:
        b = datetime.strptime(dob[:10], "%Y-%m-%d")
    except ValueError:
        return None
    t = datetime.now(timezone.utc)
    return t.year - b.year - ((t.month, t.day) < (b.month, b.day))


def _annotate_dependents(member: dict) -> dict:
    for d in (member.get("dependent_details") or []):
        d["age"] = _age(d.get("dob"))
        d["over_20"] = bool(d.get("relation") in ("son", "daughter")
                            and d["age"] is not None and d["age"] > KID_AGE_FLAG)
    return member


class PolicyIn(BaseModel):
    policy_number: str
    insurer: str
    insurer_email: Optional[str] = None
    tpa: Optional[str] = None
    policy_start: Optional[str] = None
    policy_end: Optional[str] = None
    sum_insured_default: float = 0
    premium_total: float = 0
    notes: Optional[str] = None
    status: str = "active"


class BulkAddIn(BaseModel):
    policy_id: str
    employee_ids: list[str]
    coverage_scope: str = "auto"     # auto | project | head_office
    project_code: Optional[str] = None
    sum_insured: Optional[float] = None
    premium: Optional[float] = None
    dependents: int = 0


class MemberPatch(BaseModel):
    coverage_scope: Optional[str] = None
    project_code: Optional[str] = None
    sum_insured: Optional[float] = None
    premium: Optional[float] = None
    dependents: Optional[int] = None
    designation: Optional[str] = None


class DependentIn(BaseModel):
    name: str
    relation: str                    # spouse | son | daughter
    dob: Optional[str] = None
    gender: Optional[str] = None
    sum_insured: Optional[float] = None


class DependentsIn(BaseModel):
    dependents: list[DependentIn] = []


class RemoveIn(BaseModel):
    reason: Optional[str] = None


# ─── Policies ────────────────────────────────────────────────────────────
@router.get("/gmc/policies")
async def list_policies(user: dict = Depends(require_permission("hr_gmc", "read"))):
    rows = await db.gmc_policies.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    for p in rows:
        p["active_members"] = await db.gmc_members.count_documents({"policy_id": p["id"], "status": "active"})
    return rows


@router.post("/gmc/policies")
async def create_policy(p: PolicyIn, request: Request,
                        user: dict = Depends(require_permission("hr_gmc", "write"))):
    if await db.gmc_policies.find_one({"policy_number": p.policy_number}, {"_id": 0, "id": 1}):
        raise HTTPException(400, "Policy number already exists")
    doc = {"id": new_id(), **p.model_dump(), "created_at": now_iso(),
           "created_by": user.get("name") or user.get("email")}
    await db.gmc_policies.insert_one(doc); doc.pop("_id", None)
    await audit(user=user, action="create", resource="gmc_policies", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.put("/gmc/policies/{pid}")
async def update_policy(pid: str, p: PolicyIn, request: Request,
                        user: dict = Depends(require_permission("hr_gmc", "write"))):
    row = await db.gmc_policies.find_one({"id": pid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    if await db.gmc_policies.find_one({"policy_number": p.policy_number, "id": {"$ne": pid}}, {"_id": 0, "id": 1}):
        raise HTTPException(400, "Policy number already exists on another policy")
    await db.gmc_policies.update_one({"id": pid}, {"$set": {**p.model_dump(), "updated_at": now_iso()}})
    await audit(user=user, action="update", resource="gmc_policies", record_id=pid, before=row, after=p.model_dump(), ip=_ip(request))
    return await db.gmc_policies.find_one({"id": pid}, {"_id": 0})


@router.delete("/gmc/policies/{pid}")
async def delete_policy(pid: str, request: Request,
                        user: dict = Depends(require_permission("hr_gmc", "delete"))):
    if await db.gmc_members.count_documents({"policy_id": pid, "status": "active"}):
        raise HTTPException(400, "Policy has active members — remove them first")
    await db.gmc_policies.delete_one({"id": pid})
    await db.gmc_members.delete_many({"policy_id": pid})
    await audit(user=user, action="delete", resource="gmc_policies", record_id=pid, ip=_ip(request))
    return {"deleted": True}


# ─── Members ─────────────────────────────────────────────────────────────
def _member_query(policy_id: Optional[str], scope: Optional[str], project_code: Optional[str],
                  designation: Optional[str], status: Optional[str], q: Optional[str]) -> dict:
    query: dict = {}
    if policy_id:
        query["policy_id"] = policy_id
    if scope:
        query["coverage_scope"] = scope
    if project_code:
        query["project_code"] = project_code
    if designation:
        query["designation"] = designation
    if status:
        query["status"] = status
    if q:
        query["$or"] = [{"name": {"$regex": q, "$options": "i"}},
                        {"emp_code": {"$regex": q, "$options": "i"}}]
    return query


@router.get("/gmc/members")
async def list_members(policy_id: Optional[str] = None, scope: Optional[str] = None,
                       project_code: Optional[str] = None, designation: Optional[str] = None,
                       status: Optional[str] = None, q: Optional[str] = None,
                       user: dict = Depends(require_permission("hr_gmc", "read"))):
    query = _member_query(policy_id, scope, project_code, designation, status, q)
    rows = await db.gmc_members.find(query, {"_id": 0}).sort("name", 1).to_list(3000)
    return [_annotate_dependents(m) for m in rows]


@router.get("/gmc/summary")
async def gmc_summary(policy_id: Optional[str] = None,
                      user: dict = Depends(require_permission("hr_gmc", "read"))):
    q: dict = {"policy_id": policy_id} if policy_id else {}
    active = await db.gmc_members.find({**q, "status": "active"}, {"_id": 0, "sum_insured": 1, "premium": 1, "coverage_scope": 1, "dependents": 1, "dependent_details": 1}).to_list(5000)
    removed = await db.gmc_members.count_documents({**q, "status": "removed"})
    kids_over_20 = sum(
        1 for m in active for d in (m.get("dependent_details") or [])
        if d.get("relation") in ("son", "daughter") and (_age(d.get("dob")) or 0) > KID_AGE_FLAG)
    return {
        "active": len(active),
        "removed": removed,
        "head_office": sum(1 for m in active if m.get("coverage_scope") == "head_office"),
        "project": sum(1 for m in active if m.get("coverage_scope") == "project"),
        "dependents": sum(int(m.get("dependents") or 0) for m in active),
        "kids_over_20": kids_over_20,
        "sum_insured_total": sum(float(m.get("sum_insured") or 0) for m in active),
        "premium_total": sum(float(m.get("premium") or 0) for m in active),
    }


@router.get("/gmc/eligible-employees")
async def eligible_employees(policy_id: str, q: Optional[str] = None,
                             user: dict = Depends(require_permission("hr_gmc", "read"))):
    enrolled = await db.gmc_members.distinct("employee_id", {"policy_id": policy_id, "status": "active"})
    query: dict = {"status": {"$nin": ["exited", "inactive"]}, "id": {"$nin": enrolled}}
    if q:
        query["$or"] = [{"name": {"$regex": q, "$options": "i"}},
                        {"emp_code": {"$regex": q, "$options": "i"}}]
    rows = await db.employees.find(query, {"_id": 0, "id": 1, "emp_code": 1, "name": 1,
                                           "designation": 1, "department": 1,
                                           "current_project_code": 1}).sort("name", 1).to_list(2000)
    return rows


@router.post("/gmc/members/bulk-add")
async def bulk_add_members(p: BulkAddIn, request: Request,
                           user: dict = Depends(require_permission("hr_gmc", "write"))):
    policy = await db.gmc_policies.find_one({"id": p.policy_id}, {"_id": 0})
    if not policy:
        raise HTTPException(404, "Policy not found")
    if not p.employee_ids:
        raise HTTPException(400, "Select at least one employee")
    added, skipped = [], []
    for eid in p.employee_ids:
        emp = await db.employees.find_one({"id": eid}, {"_id": 0})
        if not emp or emp.get("status") in ("exited", "inactive"):
            skipped.append(eid); continue
        if await db.gmc_members.find_one({"policy_id": p.policy_id, "employee_id": eid, "status": "active"}, {"_id": 0, "id": 1}):
            skipped.append(eid); continue
        proj = p.project_code or emp.get("current_project_code") or ""
        scope = p.coverage_scope if p.coverage_scope in ("project", "head_office") else ("project" if proj else "head_office")
        doc = {
            "id": new_id(), "policy_id": p.policy_id, "employee_id": eid,
            "emp_code": emp.get("emp_code") or "", "name": emp.get("name") or "",
            "designation": emp.get("designation") or "", "department": emp.get("department") or "",
            "coverage_scope": scope, "project_code": proj if scope == "project" else "",
            "sum_insured": p.sum_insured if p.sum_insured is not None else float(policy.get("sum_insured_default") or 0),
            "premium": p.premium if p.premium is not None else 0,
            "dependents": p.dependents, "dependent_details": [], "status": "active",
            "added_at": now_iso(), "added_by": user.get("name") or user.get("email"),
            "removed_at": None, "removed_by": None, "removal_reason": None,
        }
        await db.gmc_members.insert_one(doc); doc.pop("_id", None)
        added.append(doc)
    await audit(user=user, action="gmc_bulk_add", resource="gmc_members",
                record_id=p.policy_id, after={"added": len(added), "skipped": len(skipped)}, ip=_ip(request))
    return {"added": len(added), "skipped": len(skipped)}


@router.put("/gmc/members/{mid}")
async def update_member(mid: str, p: MemberPatch, request: Request,
                        user: dict = Depends(require_permission("hr_gmc", "write"))):
    row = await db.gmc_members.find_one({"id": mid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    patch = {k: v for k, v in p.model_dump().items() if v is not None}
    if patch.get("coverage_scope") == "head_office":
        patch["project_code"] = ""
    await db.gmc_members.update_one({"id": mid}, {"$set": {**patch, "updated_at": now_iso()}})
    await audit(user=user, action="update", resource="gmc_members", record_id=mid, before=row, after=patch, ip=_ip(request))
    return await db.gmc_members.find_one({"id": mid}, {"_id": 0})


@router.put("/gmc/members/{mid}/dependents")
async def set_dependents(mid: str, p: DependentsIn, request: Request,
                         user: dict = Depends(require_permission("hr_gmc", "write"))):
    row = await db.gmc_members.find_one({"id": mid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    if row.get("status") == "removed":
        raise HTTPException(400, "Member is removed — restore first")
    allowed = {"spouse", "son", "daughter"}
    deps = []
    for d in p.dependents:
        rel = (d.relation or "").lower().strip()
        if rel not in allowed:
            raise HTTPException(400, f"Relation must be one of {sorted(allowed)}")
        if not d.name.strip():
            raise HTTPException(400, "Dependent name is required")
        deps.append({"name": d.name.strip(), "relation": rel, "dob": d.dob or "",
                     "gender": d.gender or "", "sum_insured": float(d.sum_insured or 0)})
    if sum(1 for d in deps if d["relation"] == "spouse") > 1:
        raise HTTPException(400, "Only one spouse can be added")
    await db.gmc_members.update_one({"id": mid}, {"$set": {
        "dependent_details": deps, "dependents": len(deps), "updated_at": now_iso()}})
    await audit(user=user, action="gmc_dependents", resource="gmc_members", record_id=mid,
                before={"dependents": row.get("dependent_details") or []}, after={"dependents": deps}, ip=_ip(request))
    return await db.gmc_members.find_one({"id": mid}, {"_id": 0})


@router.post("/gmc/members/{mid}/remove")
async def remove_member(mid: str, p: RemoveIn, request: Request,
                        user: dict = Depends(require_permission("hr_gmc", "write"))):
    row = await db.gmc_members.find_one({"id": mid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    if row.get("status") == "removed":
        raise HTTPException(400, "Already removed")
    await db.gmc_members.update_one({"id": mid}, {"$set": {
        "status": "removed", "removed_at": now_iso(),
        "removed_by": user.get("name") or user.get("email"),
        "removal_reason": p.reason or "Removed manually"}})
    await audit(user=user, action="gmc_remove", resource="gmc_members", record_id=mid,
                after={"reason": p.reason}, ip=_ip(request))
    return await db.gmc_members.find_one({"id": mid}, {"_id": 0})


@router.post("/gmc/members/{mid}/restore")
async def restore_member(mid: str, request: Request,
                         user: dict = Depends(require_permission("hr_gmc", "write"))):
    row = await db.gmc_members.find_one({"id": mid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    emp = await db.employees.find_one({"id": row["employee_id"]}, {"_id": 0, "status": 1})
    if not emp or emp.get("status") in ("exited", "inactive"):
        raise HTTPException(400, "Employee is exited/inactive — cannot restore cover")
    await db.gmc_members.update_one({"id": mid}, {"$set": {
        "status": "active", "removed_at": None, "removed_by": None, "removal_reason": None}})
    await audit(user=user, action="gmc_restore", resource="gmc_members", record_id=mid, ip=_ip(request))
    return await db.gmc_members.find_one({"id": mid}, {"_id": 0})


@router.get("/gmc/export.{fmt}")
async def export_members(fmt: str, policy_id: Optional[str] = None, scope: Optional[str] = None,
                         project_code: Optional[str] = None, designation: Optional[str] = None,
                         status: Optional[str] = None,
                         user: dict = Depends(require_permission("hr_gmc", "read"))):
    if fmt not in ("xlsx", "pdf"):
        raise HTTPException(400, "Format must be xlsx or pdf")
    query = _member_query(policy_id, scope, project_code, designation, status, None)
    rows = await db.gmc_members.find(query, {"_id": 0}).sort("name", 1).to_list(5000)
    for r in rows:
        parts = []
        for d in (r.get("dependent_details") or []):
            age = _age(d.get("dob"))
            flag = " — OVER 20!" if (d.get("relation") in ("son", "daughter") and (age or 0) > KID_AGE_FLAG) else ""
            parts.append(f"{d.get('name')} ({d.get('relation')}{f', {age}y' if age is not None else ''}{flag})")
        r["dependent_names"] = "; ".join(parts)
    fname = f"group_medical_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.{fmt}"
    if fmt == "xlsx":
        data = await run_blocking(to_excel, "gmc_members", rows)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        data = await run_blocking(to_pdf, "gmc_members", rows)
        media = "application/pdf"
    return StreamingResponse(io.BytesIO(data), media_type=media,
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ─── Weekly HR review digest + insurer update email ─────────────────────
def _member_lines(rows: list[dict]) -> str:
    if not rows:
        return "<li>None</li>"
    return "".join(
        f"<li><b>{m.get('name')}</b> ({m.get('emp_code')}) — {m.get('designation') or '—'} · "
        f"{'Head Office' if m.get('coverage_scope') == 'head_office' else 'Project ' + (m.get('project_code') or '')} · "
        f"SI ₹{m.get('sum_insured') or 0:,.0f}"
        f"{' · Removed: ' + (m.get('removal_reason') or '') if m.get('status') == 'removed' else ''}</li>"
        for m in rows)


async def _policy_changes(policy_id: str, since_iso: str) -> dict:
    added = await db.gmc_members.find({"policy_id": policy_id, "added_at": {"$gte": since_iso}}, {"_id": 0}).to_list(1000)
    removed = await db.gmc_members.find({"policy_id": policy_id, "status": "removed", "removed_at": {"$gte": since_iso}}, {"_id": 0}).to_list(1000)
    active = await db.gmc_members.find({"policy_id": policy_id, "status": "active"}, {"_id": 0}).to_list(5000)
    over20 = [f"{d.get('name')} ({d.get('relation')}, {_age(d.get('dob'))}y) — child of {m.get('name')}"
              for m in active for d in (m.get("dependent_details") or [])
              if d.get("relation") in ("son", "daughter") and (_age(d.get("dob")) or 0) > KID_AGE_FLAG]
    return {"added": added, "removed": removed, "active": active, "over20": over20}


async def _queue_gmc_email(to: list[str], subject: str, html: str, attachment: Optional[dict] = None) -> Optional[str]:
    """Queue via shared M365 outbox; falls back to Resend notification_service."""
    from m365_email import shared_mailbox_configured, SHARED_USERNAME, SHARED_DISPLAY_NAME
    if shared_mailbox_configured():
        from routers.email_router import _queue_outbox, _send_and_log
        outbox_id = await _queue_outbox(
            sender_type="shared", sender_user_id="system", sender_email=SHARED_USERNAME,
            sender_display_name=SHARED_DISPLAY_NAME, to=to, cc=[], bcc=[],
            subject=subject, body_text="", body_html=html, reply_to=None,
            attachments_inline=[attachment] if attachment else [], file_ids=[],
            related={"entity_type": "gmc", "entity_id": ""}, queued_by="system")
        await _send_and_log(outbox_id)
        return outbox_id
    from notification_service import email_enabled, SENDER_NAME, SENDER_EMAIL
    if not email_enabled():
        return None
    import asyncio
    import resend
    params = {"from": f"{SENDER_NAME} <{SENDER_EMAIL}>", "to": to, "subject": subject, "html": html}
    if attachment:
        params["attachments"] = [{"filename": attachment["filename"], "content": attachment["content_b64"]}]
    await asyncio.to_thread(resend.Emails.send, params)
    return None


async def run_gmc_weekly_review() -> dict:
    """Weekly digest to HR: review GMC additions/removals & email the insurer."""
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    policies = await db.gmc_policies.find({"status": "active"}, {"_id": 0}).to_list(100)
    if not policies:
        return {"policies": 0, "emails_sent": 0}
    from routers.notifications_router import emails_for_role
    recipients = list({*(await emails_for_role("hr_executive")), *(await emails_for_role("super_admin"))})
    sections = []
    for p in policies:
        ch = await _policy_changes(p["id"], since)
        sections.append(f"""
          <h3 style="margin:16px 0 4px 0;">{p['policy_number']} — {p['insurer']}</h3>
          <p style="margin:0 0 6px 0;font-size:13px;color:#475569;">
            Active members: <b>{len(ch['active'])}</b> · Added this week: <b>{len(ch['added'])}</b> · Removed this week: <b>{len(ch['removed'])}</b></p>
          <p style="margin:6px 0 2px 0;"><b>Additions (last 7 days)</b></p><ul>{_member_lines(ch['added'])}</ul>
          <p style="margin:6px 0 2px 0;"><b>Removals (last 7 days)</b></p><ul>{_member_lines(ch['removed'])}</ul>
          {'<p style="margin:6px 0 2px 0;color:#b45309;"><b>⚠ Kids over ' + str(KID_AGE_FLAG) + ' (verify insurer eligibility)</b></p><ul>' + ''.join(f'<li>{x}</li>' for x in ch['over20']) + '</ul>' if ch['over20'] else ''}
        """)
    import os
    app_url = os.environ.get("FRONTEND_URL", "")
    html = f"""
      <h2 style="margin:0 0 8px 0;">Weekly GMC Review — please finalise additions & removals</h2>
      <p style="font-size:13px;color:#475569;">Review the list below, make corrections on the Group Medical Policy page,
      then use <b>Email Insurer Update</b> to send the finalised changes to the insurance company.</p>
      {''.join(sections)}
      <p><a href="{app_url}/app/hr/group-medical">Open Group Medical Policy page →</a></p>
    """
    subject = f"[GMC Weekly Review] {sum(1 for _ in policies)} policy(ies) — review additions/removals"
    try:
        await _queue_gmc_email(recipients, subject, html)
        sent = len(recipients)
    except Exception:
        sent = 0
    hr_users = await db.users.find({"role": {"$in": ["hr_executive", "super_admin"]}}, {"_id": 0, "id": 1}).to_list(100)
    for u in hr_users:
        await db.notifications.insert_one({
            "id": new_id(), "user_id": u["id"], "kind": "gmc_weekly_review",
            "title": "Weekly GMC review due",
            "message": "Review Group Medical Policy additions/removals and email the insurer update.",
            "link": "/app/hr/group-medical", "read": False, "at": now_iso()})
    return {"policies": len(policies), "recipients": recipients, "emails_sent": sent}


@router.post("/gmc/run-weekly-review")
async def trigger_weekly_review(user: dict = Depends(require_permission("hr_gmc", "write"))):
    return await run_gmc_weekly_review()


@router.post("/gmc/policies/{pid}/email-insurer")
async def email_insurer_update(pid: str, request: Request,
                               user: dict = Depends(require_permission("hr_gmc", "write"))):
    policy = await db.gmc_policies.find_one({"id": pid}, {"_id": 0})
    if not policy:
        raise HTTPException(404, "Not found")
    if not policy.get("insurer_email"):
        raise HTTPException(400, "Set the insurer's email on the policy first (Edit Policy → Insurer Email)")
    since = policy.get("last_insurer_update_at") or (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    ch = await _policy_changes(pid, since)
    rows = await db.gmc_members.find({"policy_id": pid, "status": "active"}, {"_id": 0}).sort("name", 1).to_list(5000)
    for r in rows:
        r["dependent_names"] = "; ".join(
            f"{d.get('name')} ({d.get('relation')})" for d in (r.get("dependent_details") or []))
    xlsx = await run_blocking(to_excel, "gmc_members", rows)
    html = f"""
      <p>Dear {policy['insurer']} team,</p>
      <p>Please find below the member updates for Group Medical Policy <b>{policy['policy_number']}</b>
      (since {since[:10]}). The complete current member list is attached as Excel.</p>
      <p><b>Additions</b></p><ul>{_member_lines(ch['added'])}</ul>
      <p><b>Deletions</b></p><ul>{_member_lines(ch['removed'])}</ul>
      <p>Current active members: <b>{len(rows)}</b> · Total dependents: <b>{sum(int(m.get('dependents') or 0) for m in rows)}</b></p>
      <p>Kindly endorse the above changes and confirm.</p>
      <p>Regards,<br/>HR — INDIAN TRADE LINKS</p>
    """
    subject = f"GMC Endorsement Request — Policy {policy['policy_number']} — {len(ch['added'])} addition(s), {len(ch['removed'])} deletion(s)"
    attachment = {"filename": f"GMC_{policy['policy_number'].replace('/', '-')}_members.xlsx",
                  "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                  "content_b64": base64.b64encode(xlsx).decode("ascii")}
    try:
        outbox_id = await _queue_gmc_email([policy["insurer_email"]], subject, html, attachment)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Email could not be sent: {exc}")
    await db.gmc_policies.update_one({"id": pid}, {"$set": {"last_insurer_update_at": now_iso()}})
    await audit(user=user, action="gmc_email_insurer", resource="gmc_policies", record_id=pid,
                after={"to": policy["insurer_email"], "added": len(ch["added"]), "removed": len(ch["removed"])}, ip=_ip(request))
    return {"sent_to": policy["insurer_email"], "additions": len(ch["added"]),
            "deletions": len(ch["removed"]), "outbox_id": outbox_id}


# ─── Bulk upload / template ──────────────────────────────────────────────
_TEMPLATE_COLS = ["emp_code", "coverage_scope", "project_code", "sum_insured", "premium",
                  "spouse_name", "spouse_dob", "kids"]


@router.get("/gmc/upload-template.xlsx")
async def upload_template(user: dict = Depends(require_permission("hr_gmc", "read"))):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "GMC Members"
    for i, c in enumerate(_TEMPLATE_COLS, start=1):
        cell = ws.cell(row=1, column=i, value=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
        ws.column_dimensions[cell.column_letter].width = 20
    ws.append(["E-1001", "auto", "", 300000, 3500, "Priya Reddy", "1992-05-10",
               "Aarav|son|2018-01-20; Diya|daughter|2015-06-05"])
    ws.append([])
    ws.append(["Notes:", "coverage_scope = auto / project / head_office. kids format = Name|son or daughter|YYYY-MM-DD, separated by ;. Dates YYYY-MM-DD. emp_code must exist in Employee Master."])
    buf = io.BytesIO(); wb.save(buf)
    return StreamingResponse(io.BytesIO(buf.getvalue()),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": 'attachment; filename="gmc_upload_template.xlsx"'})


@router.post("/gmc/bulk-upload")
async def bulk_upload(policy_id: str, request: Request, file: UploadFile = File(...),
                      user: dict = Depends(require_permission("hr_gmc", "write"))):
    policy = await db.gmc_policies.find_one({"id": policy_id}, {"_id": 0})
    if not policy:
        raise HTTPException(404, "Policy not found")
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(await file.read()), data_only=True)
    except Exception:
        raise HTTPException(400, "Could not read file — upload the .xlsx template")
    ws = wb.active
    headers = [str(c.value).strip().lower() if c.value else "" for c in ws[1]]
    if "emp_code" not in headers:
        raise HTTPException(400, "Missing 'emp_code' header — use the download template")
    idx = {h: i for i, h in enumerate(headers)}

    def val(row, key):
        i = idx.get(key)
        v = row[i] if i is not None and i < len(row) else None
        return str(v).strip() if v is not None else ""

    added = updated = 0
    errors: list[str] = []
    for rn, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        code = val(row, "emp_code")
        if not code or code.lower() in ("notes:",):
            continue
        emp = await db.employees.find_one({"emp_code": code}, {"_id": 0})
        if not emp:
            errors.append(f"Row {rn}: emp_code '{code}' not found in Employee Master"); continue
        if emp.get("status") in ("exited", "inactive"):
            errors.append(f"Row {rn}: {code} is {emp.get('status')} — skipped"); continue
        deps = []
        if val(row, "spouse_name"):
            deps.append({"name": val(row, "spouse_name"), "relation": "spouse",
                         "dob": val(row, "spouse_dob"), "gender": "", "sum_insured": 0.0})
        for part in val(row, "kids").split(";"):
            part = part.strip()
            if not part:
                continue
            bits = [b.strip() for b in part.split("|")]
            rel = bits[1].lower() if len(bits) > 1 and bits[1].lower() in ("son", "daughter") else "son"
            deps.append({"name": bits[0], "relation": rel,
                         "dob": bits[2] if len(bits) > 2 else "", "gender": "", "sum_insured": 0.0})
        proj = val(row, "project_code") or emp.get("current_project_code") or ""
        scope_in = val(row, "coverage_scope").lower()
        scope = scope_in if scope_in in ("project", "head_office") else ("project" if proj else "head_office")
        try:
            si = float(val(row, "sum_insured") or policy.get("sum_insured_default") or 0)
            prem = float(val(row, "premium") or 0)
        except ValueError:
            errors.append(f"Row {rn}: sum_insured/premium must be numbers"); continue
        patch = {"coverage_scope": scope, "project_code": proj if scope == "project" else "",
                 "sum_insured": si, "premium": prem,
                 "dependent_details": deps, "dependents": len(deps), "updated_at": now_iso()}
        existing = await db.gmc_members.find_one({"policy_id": policy_id, "employee_id": emp["id"], "status": "active"}, {"_id": 0, "id": 1})
        if existing:
            await db.gmc_members.update_one({"id": existing["id"]}, {"$set": patch})
            updated += 1
        else:
            await db.gmc_members.insert_one({
                "id": new_id(), "policy_id": policy_id, "employee_id": emp["id"],
                "emp_code": emp.get("emp_code") or "", "name": emp.get("name") or "",
                "designation": emp.get("designation") or "", "department": emp.get("department") or "",
                "status": "active", "added_at": now_iso(),
                "added_by": f"{user.get('name') or user.get('email')} (bulk upload)",
                "removed_at": None, "removed_by": None, "removal_reason": None, **patch})
            added += 1
    await audit(user=user, action="gmc_bulk_upload", resource="gmc_members", record_id=policy_id,
                after={"added": added, "updated": updated, "errors": len(errors)}, ip=_ip(request))
    return {"added": added, "updated": updated, "errors": errors}
