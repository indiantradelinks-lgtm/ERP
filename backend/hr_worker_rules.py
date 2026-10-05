"""Worker / Labour Master pay rules.

An employee belongs to the Worker / Labour Master when `employees.master_category
== "worker"` (the master the HR UI writes), or when the legacy `hr_workers`
master carries the same code. For those people the weekly off is **not** a paid
day — staff employees keep the existing behaviour (weekly off paid).
"""
from __future__ import annotations

from typing import Optional, Set

from core import db

WORKER_CATEGORIES = {"worker", "workers", "labour", "labor", "labour master", "worker master"}


async def worker_key_set() -> Set[str]:
    """Upper-cased ids + codes of everyone in the Worker / Labour Master."""
    keys: Set[str] = set()
    rows = await db.employees.find({"master_category": "worker"},
                                   {"_id": 0, "id": 1, "emp_code": 1, "employee_id": 1}).to_list(100000)
    for r in rows:
        for v in (r.get("id"), r.get("emp_code"), r.get("employee_id")):
            if v:
                keys.add(str(v).strip().upper())
    for c in await db.hr_workers.distinct("code"):
        if c:
            keys.add(str(c).strip().upper())
    return keys


# Back-compat alias (older callers)
worker_code_set = worker_key_set


def is_worker_row(emp: dict, worker_keys: Optional[Set[str]] = None) -> bool:
    if (emp.get("master_category") or "").strip().lower() == "worker":
        return True
    if emp.get("is_worker") is True:
        return True
    if (emp.get("employee_category") or emp.get("category") or "").strip().lower() in WORKER_CATEGORIES:
        return True
    if worker_keys:
        for key in ("id", "employee_id", "emp_code", "employee_code", "code"):
            v = emp.get(key)
            if v and str(v).strip().upper() in worker_keys:
                return True
    return False


async def is_worker_master(emp: dict) -> bool:
    if is_worker_row(emp):
        return True
    codes = [str(emp.get(k)).strip().upper() for k in ("emp_code", "employee_id") if emp.get(k)]
    if not codes:
        return False
    return bool(await db.hr_workers.find_one({"code": {"$in": codes}}, {"_id": 0, "id": 1}))


def paid_weights(week_off_paid: bool = True) -> dict:
    """Day-status → paid-day weight. Worker/Labour Master: weekly off is unpaid."""
    return {"present": 1, "on_duty": 1, "leave": 1, "holiday": 1, "half_day": 0.5,
            "weekly_off": 1 if week_off_paid else 0}
