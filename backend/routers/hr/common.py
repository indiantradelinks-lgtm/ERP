"""Shared helpers and constants for the HR sub-modules."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request

from core import db


def ip_of(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def strip_id(d: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if d is None:
        return None
    d.pop("_id", None)
    return d


async def next_emp_code() -> str:
    last = await db.employees.find({"emp_code": {"$regex": "^E-"}}, {"_id": 0, "emp_code": 1}) \
        .sort([("emp_code", -1)]).limit(1).to_list(1)
    n = 2000
    if last:
        try:
            n = int(str(last[0]["emp_code"]).split("-")[-1]) + 1
        except Exception:
            n = 2000
    return f"E-{n}"


async def seq(prefix: str) -> str:
    doc = await db.counters.find_one_and_update(
        {"id": f"seq_{prefix.rstrip('-')}"},
        {"$inc": {"n": 1}, "$setOnInsert": {"id": f"seq_{prefix.rstrip('-')}"}},
        upsert=True, return_document=True,
    )
    n = (doc or {}).get("n", 1)
    return f"{prefix}{datetime.now(timezone.utc).year}-{n:04d}"


def days_between(a: str, b: str, half: bool = False) -> float:
    try:
        d1 = datetime.fromisoformat(a).date()
        d2 = datetime.fromisoformat(b).date()
    except Exception:
        raise HTTPException(400, "Bad date format, expect YYYY-MM-DD")
    if d2 < d1:
        raise HTTPException(400, "to_date < from_date")
    n = (d2 - d1).days + 1
    return n - 0.5 if half else float(n)
