"""Allocation & manpower management.

Endpoints:
- GET  /api/me/scope                              user's scope (depts + projects)
- POST /api/employees/{id}/move-department        update employee.departments[] + history
- POST /api/deployments/{id}/end                  end an active deployment + history
- GET  /api/allocation/idle-employees             active employees with NO active deployment
- GET  /api/allocation/by-department              dept-wise headcount
- GET  /api/allocation/by-project                 project-wise headcount
- GET  /api/allocation/history                    employee_history log (most recent first)
- GET  /api/projects/{code}/manpower              project manpower dashboard payload
"""
from datetime import datetime, timezone
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException, Depends, Request

from core import db, get_current_user, require_permission, now_iso, new_id, logger
from scope import resolve_scope, _today
from audit import audit
from approval_engine import build_chain, insert_approval, copy_approval_doc_fields


# Roles that may apply department/deployment changes immediately, bypassing
# the multi-level approval workflow added in Phase 3.
DIRECT_ALLOC_ROLES = {"super_admin", "hr_executive"}


# Master department allow-list. Keep in sync with frontend Employees.jsx
# DEPARTMENT_OPTIONS — additions here must also be reflected there.
DEPARTMENT_MASTER = {
    "Executive", "Operations", "HSE", "Finance", "Stores", "HR",
    "Procurement", "Scaffolding", "Painting", "Sales", "IT",
}


router = APIRouter(tags=["allocation"])


# ---------- helpers ----------
async def _log_history(*, employee_id: str, employee_name: str, action: str,
                       from_value: Any, to_value: Any, project: str | None,
                       actor: dict, note: str = "") -> None:
    await db.employee_history.insert_one({
        "id": new_id(),
        "employee_id": employee_id,
        "employee_name": employee_name,
        "action": action,                     # "department_move" | "deployment_start" | "deployment_end"
        "from": from_value,
        "to": to_value,
        "project": project,
        "actor_id": actor.get("id"),
        "actor_name": actor.get("name"),
        "note": note,
        "at": now_iso(),
    })


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ---------- scope (current user) ----------
@router.get("/me/scope")
async def me_scope(user: dict = Depends(get_current_user)):
    return await resolve_scope(user)


# ---------- department moves ----------
@router.post("/employees/{emp_id}/move-department")
async def move_department(emp_id: str, payload: Dict[str, Any], request: Request,
                          user: dict = Depends(get_current_user)):
    """Update an employee's department list. Body: {departments: [...], note?: str}.

    Authorization model:
      - super_admin / hr_executive → direct mutation
      - any other authenticated role → creates a `department_move` approval
        (dept_head → hr_executive chain). No mutation happens until the
        approval is fully approved.
    """
    target_depts: List[str] = [d for d in (payload.get("departments") or []) if d]
    if not target_depts:
        raise HTTPException(status_code=400, detail="At least one department is required")
    unknown = [d for d in target_depts if d not in DEPARTMENT_MASTER]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown department(s): {', '.join(unknown)}. Allowed: {sorted(DEPARTMENT_MASTER)}",
        )
    emp = await db.employees.find_one({"id": emp_id}, {"_id": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    if not emp.get("allow_multi_dept") and len(target_depts) > 1:
        raise HTTPException(status_code=400,
                            detail="This employee is not approved for multi-department assignment")
    before_depts = emp.get("departments") or ([emp.get("department")] if emp.get("department") else [])

    # Phase 3 — non-HR roles raise an approval instead of mutating directly.
    if user.get("role") not in DIRECT_ALLOC_ROLES:
        chain = await build_chain("department_move")
        approval = {
            "id": new_id(),
            "title": f"Dept move — {emp.get('name','')} → {', '.join(target_depts)}",
            "type": "department_move",
            "reference": emp.get("employee_id") or emp.get("emp_code") or emp_id,
            "record_id": emp_id,
            "module": "employees",
            "requested_by": user.get("name") or user.get("email"),
            "requester_role": user.get("role"),
            "chain": chain,
            "current_step": 0,
            "history": [],
            "status": "pending",
            "metadata": {
                "employee_id": emp_id,
                "target_departments": target_depts,
                "previous_departments": before_depts,
                "note": payload.get("note", ""),
            },
            "created_at": now_iso(),
            "created_by": user.get("id"),
        }
        copy_approval_doc_fields(approval, payload)
        await insert_approval(approval)
        await audit(user=user, action="request_move_department", resource="employees",
                    record_id=emp_id, after={"requested_departments": target_depts},
                    ip=_ip(request))
        return {"pending_approval": True, "approval_id": approval["id"], "approval": approval}

    await db.employees.update_one(
        {"id": emp_id},
        {"$set": {"departments": target_depts, "department": target_depts[0],
                  "updated_at": now_iso(), "updated_by": user["id"]}},
    )
    await _log_history(
        employee_id=emp_id, employee_name=emp.get("name", ""),
        action="department_move", from_value=before_depts, to_value=target_depts,
        project=None, actor=user, note=payload.get("note", ""),
    )
    await audit(user=user, action="move_department", resource="employees",
                record_id=emp_id, before={"departments": before_depts},
                after={"departments": target_depts}, ip=_ip(request))
    row = await db.employees.find_one({"id": emp_id}, {"_id": 0})
    return row


# ---------- end deployment ----------
@router.post("/deployments/{dep_id}/end")
async def end_deployment(dep_id: str, request: Request,
                         payload: Dict[str, Any] | None = None,
                         user: dict = Depends(require_permission("deployments", "write"))):
    """Mark a deployment as completed with optional end_date + note.
    Body: { end_date?: YYYY-MM-DD, note?: string }
    """
    payload = payload or {}
    dep = await db.deployments.find_one({"id": dep_id}, {"_id": 0})
    if not dep:
        raise HTTPException(status_code=404, detail="Deployment not found")
    end_date = payload.get("end_date") or _today()
    await db.deployments.update_one(
        {"id": dep_id},
        {"$set": {"status": "completed", "end_date": end_date,
                  "updated_at": now_iso(), "updated_by": user["id"]}},
    )
    await _log_history(
        employee_id=dep.get("employee_id") or "",
        employee_name=dep.get("employee", ""),
        action="deployment_end",
        from_value={"project": dep.get("project"), "start_date": dep.get("start_date")},
        to_value={"end_date": end_date},
        project=dep.get("project"),
        actor=user, note=payload.get("note", ""),
    )
    await audit(user=user, action="end_deployment", resource="deployments",
                record_id=dep_id, before=dep,
                after={"status": "completed", "end_date": end_date}, ip=_ip(request))
    row = await db.deployments.find_one({"id": dep_id}, {"_id": 0})
    return row


# ---------- idle / utilisation reports ----------
def _active_dep_query() -> dict:
    today = _today()
    return {
        "$and": [
            {"status": {"$nin": ["completed", "withdrawn"]}},
            {"$or": [{"end_date": {"$exists": False}}, {"end_date": None},
                     {"end_date": ""}, {"end_date": {"$gte": today}}]},
        ],
    }


@router.get("/allocation/idle-employees")
async def idle_employees(user: dict = Depends(require_permission("employees", "read"))):
    """Employees whose status is active but who have no active deployment."""
    deployed = await db.deployments.distinct("employee_id", _active_dep_query())
    rows = await db.employees.find(
        {"status": "active", "id": {"$nin": [d for d in deployed if d]}},
        {"_id": 0},
    ).sort("name", 1).to_list(1000)
    return rows


@router.get("/allocation/by-department")
async def by_department(user: dict = Depends(require_permission("employees", "read"))):
    """Headcount per department from employees collection (legacy single-dept aware)."""
    pipeline = [
        {"$match": {"status": {"$ne": "exited"}}},
        # explode departments[] (or legacy single) into a virtual array
        {"$addFields": {"_depts": {"$cond": [{"$isArray": "$departments"}, "$departments", ["$department"]]}}},
        {"$unwind": "$_depts"},
        {"$match": {"_depts": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$_depts", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    rows = await db.employees.aggregate(pipeline).to_list(100)
    return [{"department": r["_id"], "count": r["count"]} for r in rows]


@router.get("/allocation/by-project")
async def by_project(user: dict = Depends(require_permission("deployments", "read"))):
    pipeline = [
        {"$match": _active_dep_query()},
        {"$group": {"_id": "$project", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    rows = await db.deployments.aggregate(pipeline).to_list(200)
    return [{"project": r["_id"] or "—", "count": r["count"]} for r in rows]


@router.get("/allocation/history")
async def allocation_history(employee_id: str | None = None,
                             project: str | None = None,
                             action: str | None = None,
                             since: str | None = None,
                             limit: int = 200,
                             user: dict = Depends(require_permission("employees", "read"))):
    """Allocation event log. Supports filters by employee, project, action and
    `since` (ISO date). Used by Reports → Transfer History.
    """
    q: dict = {}
    if employee_id:
        q["employee_id"] = employee_id
    if project:
        q["project"] = project
    if action:
        q["action"] = action
    if since:
        q["at"] = {"$gte": since}
    rows = await db.employee_history.find(q, {"_id": 0}).sort("at", -1).to_list(min(limit, 500))
    return rows


# ---------- Phase 3 reports ----------
@router.get("/allocation/resource-utilization")
async def resource_utilization(user: dict = Depends(require_permission("employees", "read"))):
    """Per-employee deployed-days / available-days ratio.

    deployed_days  = sum over all deployments of min(end_date, today) - start_date
    available_days = today - joining_date (capped at the same window)
    """
    from datetime import date
    today = date.today()
    emps = await db.employees.find(
        {"status": {"$ne": "exited"}},
        {"_id": 0, "id": 1, "name": 1, "employee_id": 1, "joining_date": 1, "department": 1, "departments": 1},
    ).to_list(2000)
    if not emps:
        return {"summary": {"avg_utilization": 0, "deployed_employees": 0, "total_employees": 0}, "rows": []}
    emp_ids = [e["id"] for e in emps]
    deps = await db.deployments.find(
        {"employee_id": {"$in": emp_ids},
         "status": {"$nin": ["withdrawn", "pending_approval"]}},
        {"_id": 0, "employee_id": 1, "start_date": 1, "end_date": 1, "status": 1},
    ).to_list(5000)
    days_by_emp: dict[str, int] = {}
    for d in deps:
        try:
            start = date.fromisoformat(d.get("start_date") or "")
        except ValueError:
            continue
        end_raw = d.get("end_date")
        try:
            end = date.fromisoformat(end_raw) if end_raw else today
        except ValueError:
            end = today
        if end > today:
            end = today
        if end < start:
            continue
        days = (end - start).days + 1
        days_by_emp[d["employee_id"]] = days_by_emp.get(d["employee_id"], 0) + days

    rows = []
    total_util = 0.0
    deployed = 0
    for e in emps:
        try:
            jd = date.fromisoformat(e.get("joining_date") or "")
        except (ValueError, TypeError):
            jd = today  # unknown joining_date -> available = 0
        available = max((today - jd).days + 1, 1)
        used = days_by_emp.get(e["id"], 0)
        util = round(min(used / available, 1.0) * 100, 1)
        if used > 0:
            deployed += 1
            total_util += util
        rows.append({
            "employee_id": e.get("employee_id") or "—",
            "name": e.get("name"),
            "department": (e.get("departments") or [e.get("department")])[0] if (e.get("departments") or e.get("department")) else "—",
            "deployed_days": used,
            "available_days": available,
            "utilization_pct": util,
        })
    rows.sort(key=lambda r: r["utilization_pct"], reverse=True)
    return {
        "summary": {
            "avg_utilization": round(total_util / deployed, 1) if deployed else 0,
            "deployed_employees": deployed,
            "total_employees": len(emps),
        },
        "rows": rows,
    }


@router.get("/allocation/site-attendance")
async def site_attendance(user: dict = Depends(require_permission("attendance", "read"))):
    """Per-project attendance roll-up for today.

    For every active deployment we look up today's attendance row of the
    deployed employee and aggregate present/absent counts by project.
    """
    today = _today()
    deps = await db.deployments.find(
        _active_dep_query(),
        {"_id": 0, "project": 1, "employee_id": 1},
    ).to_list(2000)
    if not deps:
        return []
    emp_ids = list({d.get("employee_id") for d in deps if d.get("employee_id")})
    att_rows = await db.attendance.find(
        {"employee_id": {"$in": emp_ids}, "date": today},
        {"_id": 0, "employee_id": 1, "status": 1},
    ).to_list(5000)
    att_map = {a["employee_id"]: a.get("status") for a in att_rows}
    by_project: dict[str, dict] = {}
    for d in deps:
        proj = d.get("project") or "—"
        bucket = by_project.setdefault(proj, {"project": proj, "present": 0, "absent": 0, "unknown": 0, "total": 0})
        bucket["total"] += 1
        st = att_map.get(d.get("employee_id"))
        if st == "present":
            bucket["present"] += 1
        elif st == "absent":
            bucket["absent"] += 1
        else:
            bucket["unknown"] += 1
    out = sorted(by_project.values(), key=lambda r: r["total"], reverse=True)
    return out


@router.get("/allocation/transfer-history")
async def transfer_history(since: str | None = None, limit: int = 500,
                           user: dict = Depends(require_permission("employees", "read"))):
    """Org-wide chronological feed of department & deployment transfers.
    Filterable by ?since=YYYY-MM-DD.
    """
    q: dict = {"action": {"$in": ["department_move", "deployment_start", "deployment_end"]}}
    if since:
        q["at"] = {"$gte": since}
    rows = await db.employee_history.find(q, {"_id": 0}).sort("at", -1).to_list(min(limit, 1000))
    return rows


# ---------- project manpower dashboard ----------
@router.get("/projects/{code}/manpower")
async def project_manpower(code: str, user: dict = Depends(require_permission("projects", "read"))):
    """Manpower dashboard for a project.

    Returns:
        project: {code, name, site, status, manager}
        kpis: { total_deployed, present_today, absent_today, distinct_depts }
        by_role: [{role, count}]
        by_department: [{department, count}]
        deployments: [...active deployment rows...]
        attendance_today: [{employee_id, status}]
    """
    # match project by code OR by name (legacy data uses name in deployments)
    proj = await db.projects.find_one({"$or": [{"code": code}, {"name": code}]}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    name_or_code = {"$in": [proj.get("code"), proj.get("name")]}

    deps = await db.deployments.find(
        {"$and": [_active_dep_query(), {"project": name_or_code}]},
        {"_id": 0},
    ).sort("start_date", -1).to_list(500)

    # KPIs
    employee_ids = [d.get("employee_id") for d in deps if d.get("employee_id")]
    today = _today()
    att_rows = await db.attendance.find(
        {"employee_id": {"$in": employee_ids}, "date": today},
        {"_id": 0, "employee_id": 1, "status": 1},
    ).to_list(1000)
    att_map = {a["employee_id"]: a.get("status") for a in att_rows}
    present = sum(1 for d in deps if att_map.get(d.get("employee_id")) == "present")
    absent = sum(1 for d in deps if att_map.get(d.get("employee_id")) == "absent")

    # role breakdown (use site_role if set, else role)
    role_counts: Dict[str, int] = {}
    for d in deps:
        r = d.get("site_role") or d.get("role") or "unassigned"
        role_counts[r] = role_counts.get(r, 0) + 1

    # department breakdown via employees lookup
    dept_counts: Dict[str, int] = {}
    if employee_ids:
        emps = await db.employees.find(
            {"id": {"$in": employee_ids}},
            {"_id": 0, "id": 1, "department": 1, "departments": 1},
        ).to_list(1000)
        for e in emps:
            ds = e.get("departments") or ([e.get("department")] if e.get("department") else [])
            for d in ds:
                if d:
                    dept_counts[d] = dept_counts.get(d, 0) + 1

    return {
        "project": {
            "code": proj.get("code"), "name": proj.get("name"),
            "site": proj.get("site"), "status": proj.get("status"),
            "manager": proj.get("manager"),
        },
        "kpis": {
            "total_deployed": len(deps),
            "present_today": present,
            "absent_today": absent,
            "distinct_depts": len(dept_counts),
        },
        "by_role": sorted([{"role": k, "count": v} for k, v in role_counts.items()],
                          key=lambda x: x["count"], reverse=True),
        "by_department": sorted([{"department": k, "count": v} for k, v in dept_counts.items()],
                                key=lambda x: x["count"], reverse=True),
        "deployments": deps,
        "attendance_today": [{"employee_id": k, "status": v} for k, v in att_map.items()],
    }


# ---------- Phase 4 — shortage scan, calendar, drag-drop board data ----------
async def compute_manpower_shortages() -> list[dict]:
    """For each open recruitment_request (vacancies > 0), compare the demand
    against how many *active* deployments exist matching the requested
    department / project context. Return a list of shortage rows.

    Heuristic (deliberately simple — no skill-matching yet):
        shortfall = vacancies - active_deployments_in(project, role)
    A request is a shortage if shortfall > 0. Bucketed by department to keep
    the daily alert email short.
    """
    reqs = await db.recruitment_requests.find(
        {"status": {"$nin": ["filled", "closed"]}},
        {"_id": 0},
    ).to_list(500)
    today = _today()
    active_q = {
        "$and": [
            {"status": {"$nin": ["completed", "withdrawn", "pending_approval"]}},
            {"$or": [{"end_date": {"$exists": False}}, {"end_date": None},
                     {"end_date": ""}, {"end_date": {"$gte": today}}]},
        ],
    }
    rows = []
    for r in reqs:
        vac = int(r.get("vacancies") or 0)
        if vac <= 0:
            continue
        # Count active deployments whose role + project align with this req.
        project = r.get("project")
        position_raw = (r.get("position") or "").strip()
        q: dict = dict(active_q)
        if project:
            q = {"$and": [active_q, {"project": project}]}
        deployed = await db.deployments.count_documents(q)
        if position_raw:
            # Case-insensitive match across either site_role or role — accepts
            # 'Site Engineer', 'site_engineer', 'SITE-ENGINEER' etc.
            import re
            pat = re.compile("^" + re.escape(position_raw).replace(r"\ ", r"[\s_-]+") + "$", re.IGNORECASE)
            tighter = {"$and": [q, {"$or": [{"site_role": {"$regex": pat}}, {"role": {"$regex": pat}}]}]}
            deployed = await db.deployments.count_documents(tighter)
        shortfall = vac - deployed
        if shortfall > 0:
            rows.append({
                "req_no": r.get("req_no") or r.get("id"),
                "position": r.get("position"),
                "department": r.get("department") or "—",
                "project": project or "—",
                "vacancies": vac,
                "deployed": deployed,
                "shortfall": shortfall,
                "needed_by": r.get("needed_by"),
            })
    rows.sort(key=lambda r: r["shortfall"], reverse=True)
    return rows


@router.get("/allocation/shortages")
async def shortages(user: dict = Depends(require_permission("employees", "read"))):
    """Live manpower shortage report. Powers the dashboard widget + cron alert."""
    rows = await compute_manpower_shortages()
    total = sum(r["shortfall"] for r in rows)
    return {"total_shortfall": total, "rows": rows}


@router.get("/allocation/calendar")
async def deployment_calendar(year: int | None = None, month: int | None = None,
                              user: dict = Depends(require_permission("deployments", "read"))):
    """Calendar view of deployments. Returns one row per project with the
    deployment spans that overlap the requested (year, month) — defaults to
    the current UTC month.

    Response: { year, month, days, projects: [{project, deployments: [{employee, site_role, shift, start_offset, end_offset, status, employee_id}]}] }
    `start_offset` / `end_offset` are 1-based day-of-month integers clamped to
    the visible window, so the frontend can render fixed-width bars.
    """
    from calendar import monthrange
    from datetime import date as _date

    today = _date.today()
    y = int(year) if year else today.year
    m = int(month) if month else today.month
    days_in_month = monthrange(y, m)[1]
    win_start = _date(y, m, 1)
    win_end = _date(y, m, days_in_month)

    # Deployments overlapping the window: start_date <= win_end AND (end_date is null OR end_date >= win_start)
    win_end_iso = win_end.isoformat()
    win_start_iso = win_start.isoformat()
    q = {
        "status": {"$nin": ["pending_approval", "withdrawn"]},
        "start_date": {"$lte": win_end_iso, "$nin": [None, ""]},
        "$or": [
            {"end_date": {"$exists": False}}, {"end_date": None}, {"end_date": ""},
            {"end_date": {"$gte": win_start_iso}},
        ],
    }
    deps = await db.deployments.find(q, {"_id": 0}).sort("start_date", 1).to_list(2000)

    def _clip(iso_str: str | None, fallback: _date) -> int:
        try:
            d = _date.fromisoformat(iso_str) if iso_str else fallback
        except ValueError:
            d = fallback
        if d < win_start:
            return 1
        if d > win_end:
            return days_in_month
        return d.day

    by_project: dict[str, list] = {}
    for d in deps:
        proj = d.get("project") or "—"
        by_project.setdefault(proj, []).append({
            "id": d.get("id"),
            "employee": d.get("employee") or "—",
            "employee_id": d.get("employee_id"),
            "site_role": d.get("site_role") or d.get("role") or "",
            "shift": d.get("shift") or "",
            "status": d.get("status") or "active",
            "start_offset": _clip(d.get("start_date"), win_start),
            "end_offset": _clip(d.get("end_date"), win_end),
            "deployment_no": d.get("deployment_no"),
        })

    projects = sorted(
        [{"project": k, "deployments": v} for k, v in by_project.items()],
        key=lambda r: r["project"],
    )
    return {"year": y, "month": m, "days": days_in_month, "projects": projects}


# ──────────────────────────────────────────────────────────────────────────────
# Bulk import — Site Teams (deployments) from CSV
# ──────────────────────────────────────────────────────────────────────────────
DEPLOYMENT_IMPORT_COLUMNS = [
    "employee_code", "employee_email", "employee_name",
    "project", "site_role", "shift", "site",
    "start_date", "end_date", "reporting_to", "status",
]


@router.get("/deployments/import-template")
async def deployment_import_template(user: dict = Depends(require_permission("deployments", "read"))):
    import csv as _csv
    import io as _io
    from fastapi.responses import StreamingResponse
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(DEPLOYMENT_IMPORT_COLUMNS)
    w.writerow(["EMP-2026-0001", "", "", "PRJ-2026-0001", "site_engineer", "day", "Site A", "2026-02-15", "", "Foreman 1", "active"])
    w.writerow(["", "rigger1@example.com", "", "PRJ-2026-0002", "rigger", "night", "Tower B", "2026-02-20", "2026-04-30", "", "planned"])
    w.writerow(["", "", "John Doe", "PRJ-2026-0001", "scaffolder", "general", "", "2026-02-20", "", "", ""])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="site_teams_template.csv"'},
    )


async def _resolve_employee(row: Dict[str, str]) -> Dict[str, Any] | None:
    """Try employee_code → email → name (case-insensitive)."""
    import re as _re
    code = (row.get("employee_code") or "").strip()
    if code:
        emp = await db.employees.find_one(
            {"$or": [{"employee_id": code}, {"id": code}, {"code": code}]}, {"_id": 0},
        )
        if emp:
            return emp
    email = (row.get("employee_email") or "").strip().lower()
    if email:
        emp = await db.employees.find_one({"email": {"$regex": f"^{_re.escape(email)}$", "$options": "i"}}, {"_id": 0})
        if emp:
            return emp
    name = (row.get("employee_name") or "").strip()
    if name:
        emp = await db.employees.find_one({"name": {"$regex": f"^{_re.escape(name)}$", "$options": "i"}}, {"_id": 0})
        if emp:
            return emp
    return None


async def _resolve_project(project_token: str) -> Dict[str, Any] | None:
    import re as _re
    token = (project_token or "").strip()
    if not token:
        return None
    return await db.projects.find_one(
        {"$or": [{"code": token}, {"name": {"$regex": f"^{_re.escape(token)}$", "$options": "i"}}]},
        {"_id": 0},
    )


@router.post("/deployments/import.csv")
async def deployment_import(request: Request,
                            user: dict = Depends(require_permission("deployments", "write"))):
    """Bulk import site teams (deployments) from a CSV file. Multipart `file`.

    Approval gating mirrors `POST /api/deployments`:
      * super_admin / hr_executive / general_manager → deployments go live immediately
        (status as provided, default `active`).
      * All other roles → forced into `status="pending_approval"` and an approval
        document is created using the `deployment` chain.
    """
    import csv as _csv
    import io as _io
    from sequences import next_sequence
    form = await request.form()
    file = form.get("file")
    if not file or not hasattr(file, "read"):
        raise HTTPException(status_code=400, detail="Multipart 'file' is required")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1", errors="ignore")
    reader = _csv.DictReader(_io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV has no header row")

    # At least one of these columns is required so we can find an employee.
    if not any(c in reader.fieldnames for c in ("employee_code", "employee_email", "employee_name")):
        raise HTTPException(status_code=400, detail="CSV must include at least one of employee_code, employee_email, employee_name")
    if "project" not in reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV must include the 'project' column")

    needs_approval = user.get("role") not in {"super_admin", "hr_executive", "general_manager"}

    created: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for line_no, row in enumerate(reader, start=2):
        try:
            emp = await _resolve_employee(row)
            if not emp:
                errors.append({"row": line_no, "error": "employee not found"})
                continue
            proj = await _resolve_project(row.get("project") or "")
            if not proj:
                errors.append({"row": line_no, "error": f"project '{row.get('project')}' not found"})
                continue
            start_date = (row.get("start_date") or "").strip() or _today()
            end_date = (row.get("end_date") or "").strip() or None
            site_role = (row.get("site_role") or "").strip()
            if not site_role:
                errors.append({"row": line_no, "error": "site_role is required"})
                continue
            shift = (row.get("shift") or "day").strip()
            site = (row.get("site") or "").strip() or None
            reporting_to = (row.get("reporting_to") or "").strip() or None
            status = (row.get("status") or "").strip() or "active"
            if needs_approval:
                status = "pending_approval"

            # Idempotency — skip if an active/planned/pending deployment for the
            # same employee + project already exists.
            dup = await db.deployments.find_one({
                "employee_id": emp["id"],
                "project": proj.get("code") or proj.get("name"),
                "status": {"$nin": ["completed", "withdrawn"]},
            }, {"_id": 0})
            if dup:
                errors.append({"row": line_no, "error": f"already deployed (dep {dup.get('deployment_no') or dup.get('id')})"})
                continue

            doc = {
                "id": new_id(),
                "deployment_no": await next_sequence("DEP"),
                "employee_id": emp["id"],
                "employee": emp.get("name"),
                "project": proj.get("code") or proj.get("name"),
                "site": site,
                "site_role": site_role,
                "shift": shift,
                "start_date": start_date,
                "end_date": end_date,
                "reporting_to": reporting_to,
                "status": status,
                "created_at": now_iso(),
                "created_by": user["id"],
                "source": "bulk_import",
            }
            await db.deployments.insert_one(doc)

            if needs_approval:
                chain = await build_chain("deployment")
                approval = {
                    "id": new_id(),
                    "type": "deployment",
                    "module": "hr",
                    "record_id": doc["id"],
                    "title": f"Deployment {doc['deployment_no']} · {emp.get('name')}",
                    "summary": f"{emp.get('name')} → {doc['project']} · {site_role}",
                    "requested_by": user.get("name") or user.get("email"),
                    "requested_by_id": user["id"],
                    "status": "pending",
                    "current_step": 0,
                    "chain": chain,
                    "history": [],
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                }
                # Bulk-imported deployments: auto-mark docs as N/A; importer can attach later
                approval["documents_not_required"] = True
                approval["documents_not_required_reason"] = "Bulk import — supporting documents on parent deployment record"
                await insert_approval(approval)
                await db.deployments.update_one({"id": doc["id"]}, {"$set": {"approval_id": approval["id"]}})
                pending.append({"row": line_no, "id": doc["id"], "deployment_no": doc["deployment_no"], "employee": emp.get("name"), "approval_id": approval["id"]})
            else:
                await _log_history(
                    employee_id=emp["id"], employee_name=emp.get("name") or "",
                    action="deployment_start",
                    from_value=None,
                    to_value={"project": doc["project"], "site_role": site_role,
                              "start_date": start_date, "shift": shift},
                    project=doc["project"], actor=user, note="bulk import",
                )
                created.append({"row": line_no, "id": doc["id"], "deployment_no": doc["deployment_no"], "employee": emp.get("name")})
        except Exception as ex:  # noqa: BLE001
            logger.warning(f"deployment_import row {line_no} failed: {ex}")
            errors.append({"row": line_no, "error": str(ex)})

    await audit(user=user, action="bulk_import", resource="deployments",
                record_id="bulk", after={"created": len(created), "pending": len(pending), "errors": len(errors)},
                ip=_ip(request))
    return {
        "summary": {"created": len(created), "pending_approval": len(pending), "errors": len(errors)},
        "created": created, "pending": pending, "errors": errors,
    }
