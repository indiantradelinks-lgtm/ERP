"""Project Category → billing behaviour (Iter 206).

Project Master already carries `category`:
    amc_arc    → recurring, one bill per month for the whole project validity
    short_term / long_term / shutdown / one_time → billed against the project
                 scope / timeline (period from–to), no monthly cycle

Everything in the billing workflow reads the category from here so the Bill
Request, the Pending Billing Report and the reminders stay in step.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

CATEGORY_LABELS: Dict[str, str] = {
    "amc_arc": "AMC / ARC",
    "short_term": "Short-Term",
    "long_term": "Long-Term",
    "shutdown": "Shutdown",
    "one_time": "One-Time",
}
RECURRING_CATEGORIES = {"amc_arc"}
# Legacy billing_type still decides when a project has no category yet.
LEGACY_RECURRING_BILLING_TYPES = {"annual_rate_contract"}


def category_of(project: Dict[str, Any]) -> str:
    cat = (project.get("category") or "").strip().lower()
    if cat in CATEGORY_LABELS:
        return cat
    if (project.get("billing_type") or "") in LEGACY_RECURRING_BILLING_TYPES:
        return "amc_arc"
    return cat or ""


def category_label(cat: str) -> str:
    return CATEGORY_LABELS.get(cat, (cat or "Not Set").replace("_", " ").title())


def is_recurring(project: Dict[str, Any]) -> bool:
    return category_of(project) in RECURRING_CATEGORIES


def billing_mode(project: Dict[str, Any]) -> str:
    return "monthly" if is_recurring(project) else "scope"


def _month_str(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _add_month(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    return f"{y + (m // 12):04d}-{(m % 12) + 1:02d}"


def _parse_month(value: Optional[str]) -> Optional[str]:
    v = (value or "")[:7]
    return v if len(v) == 7 and v[4] == "-" else None


def month_bounds(month: str) -> tuple[str, str]:
    """First and last calendar day of YYYY-MM."""
    y, m = int(month[:4]), int(month[5:7])
    nxt = date(y + (m // 12), (m % 12) + 1, 1)
    last = nxt.toordinal() - 1
    return f"{y:04d}-{m:02d}-01", date.fromordinal(last).isoformat()


def contract_months(project: Dict[str, Any], *, cap_today: bool = False) -> List[str]:
    """Every billing month of the project — start month … end month (project validity)."""
    start = _parse_month(project.get("start_date") or project.get("created_at"))
    if not start:
        return []
    end = _parse_month(project.get("extended_end_date") or project.get("end_date")) or _month_str(date.today())
    if cap_today:
        end = min(end, _month_str(date.today()))
    if end < start:
        return [start]
    months, cur = [], start
    while cur <= end and len(months) < 120:
        months.append(cur)
        cur = _add_month(cur)
    return months


def monthly_amount(project: Dict[str, Any]) -> float:
    """Expected billing value for one month: the master's monthly amount when set,
    otherwise the contract / work-order value spread over the contract months."""
    direct = float(project.get("monthly_billing_amount") or 0)
    if direct > 0:
        return round(direct, 2)
    total = float(project.get("contract_value") or project.get("work_order_value") or 0)
    if total <= 0:
        return 0.0
    months = contract_months(project)
    return round(total / max(len(months), 1), 2)


def scope_value(project: Dict[str, Any]) -> float:
    """Total billable value of a scope/timeline project."""
    return round(float(project.get("contract_value") or project.get("work_order_value") or 0), 2)
