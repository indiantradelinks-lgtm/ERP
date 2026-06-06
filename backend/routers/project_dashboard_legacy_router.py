"""Project-wise dashboard aggregator.

Returns a single rich payload for one project — financials, site execution,
procurement, safety, manpower, timeline, recent activity — so the frontend can
render a 360° view in one network round-trip.

Mounted at /api/project-dashboard/*.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from core import db, require_permission, now_iso

router = APIRouter(prefix="/project-dashboard", tags=["project-dashboard"])


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _r(v) -> float:
    return round(_num(v), 2)


def _ymd(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    try:
        return s[:10]
    except Exception:
        return None


# ───────────────────────────────────────────── helpers ─────────────────────────
async def _project_or_404(project_id: str) -> Dict[str, Any]:
    p = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


def _link_query(project: Dict[str, Any], *, by_id: str = "project_id", by_code: str = "project_code", by_alias: str = "project") -> Dict[str, Any]:
    """Some collections link by id, some by code, some by name/alias.

    Returns a MongoDB $or query that matches any of those. We always include
    every available linking key for the project, so the dashboard works
    regardless of how each writer chose to reference the project.
    """
    pid = project.get("id")
    pcode = project.get("code")
    pname = project.get("name")
    ors = []
    if pid:
        ors.append({by_id: pid})
    if pcode:
        ors.append({by_code: pcode})
        ors.append({by_alias: pcode})  # PurchaseOrder.project sometimes stores code
    if pname:
        ors.append({by_alias: pname})  # PurchaseOrder.project sometimes stores name
    return {"$or": ors} if ors else {by_id: pid or ""}


def _safe_iso_date(s: Optional[str]):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except Exception:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except Exception:
            return None


async def _financials(project_id: str, project: Dict[str, Any]) -> Dict[str, Any]:
    contract_value = _num(project.get("budget") or project.get("contract_value") or 0)
    link = _link_query(project)

    # PO commitment (linked to project)
    po_rows = await db.purchase_orders.find(link, {"_id": 0}).to_list(2000)
    po_value = sum(_num(p.get("total") or p.get("amount") or p.get("grand_total")) for p in po_rows)
    po_received = sum(_num(p.get("received_value") or 0) for p in po_rows)

    # GRN — value received against POs
    grn_rows = await db.grn.find(link, {"_id": 0}).to_list(2000)
    grn_value = sum(_num(g.get("total") or g.get("amount") or 0) for g in grn_rows)

    # RA Bills raised
    ra_rows = await db.ra_bills.find(link, {"_id": 0}).to_list(2000)
    bills_raised = sum(_num(r.get("gross_amount") or r.get("amount") or 0) for r in ra_rows)
    bills_net_due = sum(_num(r.get("net_due") or 0) for r in ra_rows)
    retention_held = sum(_num(r.get("retention_amount") or 0) for r in ra_rows)
    tds_deducted = sum(_num(r.get("tds_amount") or 0) for r in ra_rows)
    gst_charged = sum(_num(r.get("gst_amount") or 0) for r in ra_rows)

    # Payments received
    pay_rows = await db.payments_in.find(link, {"_id": 0}).to_list(2000)
    payments_received = sum(_num(p.get("amount") or 0) for p in pay_rows)
    outstanding = max(bills_net_due - payments_received, 0)

    # Measurements certified vs claimed (advisory)
    m_rows = await db.measurements.find(link, {"_id": 0}).to_list(2000)
    certified_value = sum(_num(m.get("certified_amount") or 0) for m in m_rows)
    claimed_value = sum(_num(m.get("claimed_amount") or 0) for m in m_rows)

    revenue_recognised = bills_raised or certified_value
    cost_incurred = grn_value  # crude proxy until we have a true cost rollup
    gross_profit = revenue_recognised - cost_incurred
    gp_pct = (gross_profit / revenue_recognised * 100.0) if revenue_recognised > 0 else 0.0
    progress_billed_pct = (bills_raised / contract_value * 100.0) if contract_value > 0 else 0.0

    return {
        "contract_value": _r(contract_value),
        "po_committed": _r(po_value),
        "po_received_value": _r(po_received),
        "grn_value": _r(grn_value),
        "bills_raised": _r(bills_raised),
        "bills_count": len(ra_rows),
        "bills_net_due": _r(bills_net_due),
        "retention_held": _r(retention_held),
        "tds_deducted": _r(tds_deducted),
        "gst_charged": _r(gst_charged),
        "payments_received": _r(payments_received),
        "payments_count": len(pay_rows),
        "outstanding": _r(outstanding),
        "measurements_claimed": _r(claimed_value),
        "measurements_certified": _r(certified_value),
        "revenue_recognised": _r(revenue_recognised),
        "cost_incurred": _r(cost_incurred),
        "gross_profit": _r(gross_profit),
        "gp_pct": _r(gp_pct),
        "progress_billed_pct": _r(progress_billed_pct),
    }


async def _site_execution(project_id: str, project: Dict[str, Any]) -> Dict[str, Any]:
    link = _link_query(project)
    dpr_rows = await db.dprs.find(link, {"_id": 0}).to_list(2000)
    manpower_today = 0
    manpower_avg = 0
    last_dpr_date = None
    today = datetime.now(timezone.utc).date()
    manpower_30d_by_day: Dict[str, int] = defaultdict(int)
    dpr_30d = 0

    for d in dpr_rows:
        d_date = _safe_iso_date(d.get("date") or d.get("created_at"))
        mp_raw = d.get("manpower_count") or d.get("manpower") or 0
        # DPR may store manpower as a dict/list — try common shapes
        if isinstance(mp_raw, dict):
            mp = int(sum(_num(v) for v in mp_raw.values()))
        elif isinstance(mp_raw, list):
            mp = int(sum(_num(x.get("count") if isinstance(x, dict) else x) for x in mp_raw))
        else:
            mp = int(_num(mp_raw))
        if not d_date:
            continue
        if d_date == today:
            manpower_today = max(manpower_today, mp)
        if (today - d_date).days <= 30:
            dpr_30d += 1
            manpower_30d_by_day[d_date.isoformat()] += mp
        if last_dpr_date is None or d_date > last_dpr_date:
            last_dpr_date = d_date

    if manpower_30d_by_day:
        manpower_avg = int(sum(manpower_30d_by_day.values()) / len(manpower_30d_by_day))

    manpower_trend = [{"date": k, "manpower": v} for k, v in sorted(manpower_30d_by_day.items())][-30:]

    # Measurements (count by status)
    m_rows = await db.measurements.find(link, {"_id": 0}).to_list(2000)
    m_status = defaultdict(int)
    for m in m_rows:
        m_status[(m.get("status") or "draft").lower()] += 1

    # Active deployments
    deploys = await db.deployments.find(
        {**link, "active": {"$ne": False}}, {"_id": 0}
    ).to_list(2000)
    cat_counts: Dict[str, int] = defaultdict(int)
    for dep in deploys:
        cat = (dep.get("trade") or dep.get("category") or dep.get("role") or "other").title()
        cat_counts[cat] += 1

    return {
        "dpr_count_total": len(dpr_rows),
        "dpr_count_30d": dpr_30d,
        "last_dpr_date": last_dpr_date.isoformat() if last_dpr_date else None,
        "manpower_today": manpower_today,
        "manpower_avg_30d": manpower_avg,
        "manpower_trend_30d": manpower_trend,
        "manpower_by_category": sorted(
            [{"category": k, "count": v} for k, v in cat_counts.items()],
            key=lambda x: -x["count"],
        )[:12],
        "measurements_count": len(m_rows),
        "measurements_by_status": dict(m_status),
        "deployment_count_active": len(deploys),
    }


async def _procurement(project_id: str, project: Dict[str, Any]) -> Dict[str, Any]:
    link = _link_query(project)
    pr_rows = await db.purchase_requisitions.find(link, {"_id": 0}).to_list(2000)
    po_rows = await db.purchase_orders.find(link, {"_id": 0}).to_list(2000)
    grn_rows = await db.grn.find(link, {"_id": 0}).to_list(2000)
    alloc_rows = await db.material_allocations.find(link, {"_id": 0}).to_list(2000)

    def by_status(rows: List[Dict[str, Any]]) -> Dict[str, int]:
        out: Dict[str, int] = defaultdict(int)
        for r in rows:
            out[(r.get("status") or "draft").lower()] += 1
        return dict(out)

    return {
        "pr_count": len(pr_rows),
        "pr_by_status": by_status(pr_rows),
        "po_count": len(po_rows),
        "po_by_status": by_status(po_rows),
        "grn_count": len(grn_rows),
        "alloc_count": len(alloc_rows),
        "alloc_qty_total": _r(sum(_num(a.get("qty") or a.get("quantity") or 0) for a in alloc_rows)),
    }


async def _safety(project_id: str, project: Dict[str, Any]) -> Dict[str, Any]:
    link = _link_query(project)
    sr_rows = await db.safety_reports.find(link, {"_id": 0}).to_list(2000)
    ptw_rows = await db.ptws.find(link, {"_id": 0}).to_list(2000)
    ppe_rows = await db.ppe_issuance.find(link, {"_id": 0}).to_list(2000)
    tbt_rows = await db.toolbox_talks.find(link, {"_id": 0}).to_list(2000)

    sev_count: Dict[str, int] = defaultdict(int)
    open_count = 0
    for r in sr_rows:
        sev_count[(r.get("severity") or "minor").lower()] += 1
        if (r.get("status") or "open").lower() in ("open", "in_progress", "investigating"):
            open_count += 1

    ptw_status: Dict[str, int] = defaultdict(int)
    for p in ptw_rows:
        ptw_status[(p.get("status") or "draft").lower()] += 1

    return {
        "incidents_total": len(sr_rows),
        "incidents_by_severity": dict(sev_count),
        "incidents_open": open_count,
        "ptw_total": len(ptw_rows),
        "ptw_by_status": dict(ptw_status),
        "ppe_issued_count": len(ppe_rows),
        "toolbox_talks_count": len(tbt_rows),
    }


async def _recent_activity(project_id: str, project: Dict[str, Any], limit: int = 12) -> List[Dict[str, Any]]:
    """Latest events across DPRs, RA bills, payments, GRNs, measurements."""
    events: List[Dict[str, Any]] = []
    link = _link_query(project)

    async def push(coll, kind: str, label_fn, n: int = 5):
        rows = await coll.find(link, {"_id": 0}).sort([("created_at", -1)]).to_list(n)
        for r in rows:
            events.append({
                "kind": kind,
                "label": label_fn(r),
                "ts": r.get("created_at") or r.get("date") or "",
                "ref_id": r.get("id"),
            })

    await push(db.dprs, "dpr", lambda r: f"DPR · {_ymd(r.get('date'))} · {int(_num(r.get('manpower_count')))} manpower")
    await push(db.ra_bills, "ra_bill", lambda r: f"RA Bill · {r.get('bill_number') or r.get('id', '')[:8]} · ₹{int(_num(r.get('net_due'))):,}")
    await push(db.payments_in, "payment", lambda r: f"Payment · ₹{int(_num(r.get('amount'))):,} · {r.get('mode') or ''}")
    await push(db.grn, "grn", lambda r: f"GRN · {r.get('grn_number') or ''} · ₹{int(_num(r.get('total'))):,}")
    await push(db.measurements, "measurement", lambda r: f"Measurement · {r.get('status') or 'draft'} · ₹{int(_num(r.get('certified_amount'))):,}")
    await push(db.safety_reports, "safety", lambda r: f"Safety · {r.get('severity') or 'minor'} · {(r.get('description') or '')[:50]}")

    # Sort newest first
    events.sort(key=lambda x: x.get("ts") or "", reverse=True)
    return events[:limit]


# ───────────────────────────────────────────── endpoints ───────────────────────
@router.get("/projects")
async def list_projects(user: dict = Depends(require_permission("projects", "read"))):
    """Lightweight list for the dashboard project picker."""
    rows = await db.projects.find(
        {}, {"_id": 0, "id": 1, "code": 1, "name": 1, "client": 1, "site": 1, "status": 1, "budget": 1}
    ).sort([("created_at", -1)]).to_list(500)
    return rows


@router.get("/{project_id}")
async def project_dashboard(
    project_id: str,
    user: dict = Depends(require_permission("projects", "read")),
):
    project = await _project_or_404(project_id)
    financials = await _financials(project_id, project)
    execution = await _site_execution(project_id, project)
    procurement = await _procurement(project_id, project)
    safety = await _safety(project_id, project)
    recent = await _recent_activity(project_id, project)

    # Headline KPIs (used by the top strip)
    kpis = {
        "contract_value": financials["contract_value"],
        "billed_pct": financials["progress_billed_pct"],
        "outstanding": financials["outstanding"],
        "gp_pct": financials["gp_pct"],
        "manpower_today": execution["manpower_today"],
        "open_safety_incidents": safety["incidents_open"],
    }

    return {
        "project": {
            "id": project.get("id"),
            "code": project.get("code"),
            "name": project.get("name"),
            "client": project.get("client"),
            "site": project.get("site"),
            "status": project.get("status"),
            "type": project.get("type"),
            "start_date": project.get("start_date"),
            "end_date": project.get("end_date"),
            "pm": project.get("project_manager") or project.get("pm"),
            "budget": _r(project.get("budget") or 0),
        },
        "kpis": kpis,
        "financials": financials,
        "execution": execution,
        "procurement": procurement,
        "safety": safety,
        "recent_activity": recent,
        "generated_at": now_iso(),
    }
