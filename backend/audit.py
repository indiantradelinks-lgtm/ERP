"""Audit log helper. Centralised so every mutation can record a tamper-evident
entry in `audit_logs` (id, ts, actor, action, resource, record_id, before, after, ip).
"""
from typing import Any, Optional

from core import db, now_iso, new_id, logger


async def audit(
    *,
    user: dict,
    action: str,
    resource: str,
    record_id: Optional[str] = None,
    before: Any = None,
    after: Any = None,
    ip: Optional[str] = None,
    meta: Optional[dict] = None,
) -> None:
    """Insert one audit log row. Fire-and-forget; failures must never break the caller."""
    try:
        doc = {
            "id": new_id(),
            "ts": now_iso(),
            "actor_id": (user or {}).get("id"),
            "actor_name": (user or {}).get("name") or (user or {}).get("email"),
            "actor_role": (user or {}).get("role"),
            "action": action,
            "resource": resource,
            "record_id": record_id,
            "before": _sanitize(before),
            "after": _sanitize(after),
            "ip": ip,
            "meta": meta or None,
        }
        await db.audit_logs.insert_one(doc)
    except Exception as e:  # pragma: no cover
        logger.warning(f"audit log failed: {e}")


def _sanitize(value: Any) -> Any:
    """Strip MongoDB internals + secrets before persisting/serialising."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items() if k not in ("_id", "password", "password_hash")}
    if isinstance(value, list):
        return [_sanitize(x) for x in value]
    return value
