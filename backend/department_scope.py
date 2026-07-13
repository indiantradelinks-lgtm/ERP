"""Department visibility & scope helpers (Iter 47 — strict dept segregation).

Every list endpoint that should be department-scoped can call `apply_scope(user, base_query, mode)`
to get a Mongo filter that respects the user's role + dept allowlist + project/site mapping.

Privileged roles bypass scoping entirely:
- super_admin, director, general_manager always see everything (audit/compliance need).

Scope modes:
- "project": filter by user.assigned_projects (PM/Site Engineer see only their projects)
- "site":    filter by user.assigned_sites
- "owner":   filter by created_by_id == user.id  OR  approver in any chain step
- "department": filter records whose `ownership_department` is in user's role-allowed depts

Mixed: a list endpoint can pass `modes=["project","department"]` to AND/OR-combine.
"""
from __future__ import annotations

from typing import Iterable, Optional

from core import db

GLOBAL_BYPASS = {"super_admin", "director", "general_manager"}


async def _allowed_departments(user: dict) -> list[str]:
    """Returns the dept slugs the user's role is mapped to (via Role × Department matrix)."""
    role = user.get("role")
    if not role:
        return []
    row = await db.role_department_map.find_one({"role": role}, {"_id": 0, "departments": 1})
    return list((row or {}).get("departments", [])) if row else []


async def apply_scope(
    user: dict,
    base_query: dict,
    *,
    modes: Iterable[str] = (),
    project_field: str = "project_id",
    site_field: str = "site",
    owner_field: str = "created_by_id",
    dept_field: str = "ownership_department",
) -> dict:
    """Returns an enriched Mongo query that combines `base_query` with scope clauses.

    Always-allow:
    - super_admin / director / general_manager → returns base_query unchanged.

    Returns dict suitable for `db.<coll>.find(query)`. Never raises — gracefully no-ops
    when the user has no constraints in metadata.
    """
    role = user.get("role")
    if role in GLOBAL_BYPASS:
        return dict(base_query)
    clauses: list[dict] = [base_query] if base_query else []

    or_terms: list[dict] = []

    if "project" in modes:
        prjs = user.get("assigned_projects") or []
        if prjs:
            or_terms.append({project_field: {"$in": prjs}})
        # User who created the record also sees it
        or_terms.append({owner_field: user.get("id")})

    if "site" in modes:
        sites = user.get("assigned_sites") or []
        if sites:
            or_terms.append({site_field: {"$in": sites}})

    if "department" in modes:
        depts = await _allowed_departments(user)
        if depts:
            or_terms.append({dept_field: {"$in": depts}})

    if "owner" in modes:
        or_terms.append({owner_field: user.get("id")})
        if user.get("email"):
            or_terms.append({"created_by": user["email"]})

    if or_terms:
        clauses.append({"$or": or_terms})

    if not clauses:
        return dict(base_query)
    if len(clauses) == 1:
        return dict(clauses[0])
    return {"$and": clauses}


async def stamp_ownership(doc: dict, user: dict, *, owner_dept: Optional[str] = None) -> dict:
    """Idempotently stamp ownership tagging fields on a new record before insert."""
    doc.setdefault("ownership_department", owner_dept or user.get("department"))
    doc.setdefault("created_by_id", user.get("id"))
    doc.setdefault("created_by", user.get("name") or user.get("email"))
    doc.setdefault("created_by_role", user.get("role"))
    return doc
