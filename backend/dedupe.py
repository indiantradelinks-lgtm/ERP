"""ERP-wide duplicate prevention (Iter 205).

Two independent layers:

1. ``DuplicateSubmissionMiddleware`` — makes every create/action POST idempotent.
   The first request of a given (user + path + body) fingerprint runs normally and
   its JSON response is cached for a short window; a repeated click, a browser
   resubmit or a retry after a network error replays that cached response instead
   of inserting a second record. Nothing downstream has to change.

2. ``ensure_no_duplicate()`` — business-key guard called by a module right before
   its insert. On a match it raises ``DuplicateRecordError`` → HTTP 409 carrying
   the existing record number so the UI can tell the user which record to open.

Every blocked attempt is journalled in ``duplicate_blocks`` for the Admin screen
(/app/admin/duplicate-blocks).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from pymongo.errors import DuplicateKeyError
from starlette.middleware.base import BaseHTTPMiddleware

from core import db, logger, new_id, now_iso, user_display_name

# How long an identical submission is treated as a repeat of the first one.
# Short on purpose: a double click / network retry lands within a few seconds,
# while a deliberate second identical entry (two identical site payments, say)
# must never be swallowed.
WINDOW_SECONDS = 25
MAX_BODY_BYTES = 200_000
MAX_CACHED_RESPONSE = 256_000
# How long a repeat waits for the original request to finish (0.25s × 48 = 12s).
WAIT_TICKS = 48

# POST endpoints that are queries/streams, not record creation — never guarded.
EXEMPT_PATH_PARTS = (
    "/auth/", "/cron/", "/telemetry", "/module-visit", "/impersonat",
    "/files/upload", "/upload", "/import", "/parse", "/search", "/stock-check",
    "/preview", "/export", "/download", "/pdf", "/report", "/scan",
    "/refresh", "/logout", "/login",
)

# State transitions on an existing record (approve / reject / verify / issue …).
# Their handlers already refuse an out-of-state repeat, and a multi-step chain is
# cleared by posting the same payload again — so these are left alone.
STATE_ACTION_VERBS = (
    "action", "approve", "reject", "submit", "verify", "issue", "close", "cancel",
    "status", "send", "resend", "mark", "paid", "fulfil", "assign", "unassign",
    "sync", "retry", "run", "skip", "foreclose", "settle", "hold", "release",
    "publish", "pause", "resume", "revise", "amend", "reopen", "restore", "ack",
    "acknowledge", "convert", "recalc", "refresh", "seed", "backfill", "migrate",
    "notify", "remind", "read", "archive", "activate", "deactivate", "toggle",
)


def _is_state_action(path: str) -> bool:
    last = path.rstrip("/").rsplit("/", 1)[-1].lower()
    tokens = re.split(r"[-_]", last)
    return any(t in STATE_ACTION_VERBS for t in tokens)


def _norm(value: Any) -> str:
    """Normalised text for business-key comparison."""
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def norm_key(value: Any) -> str:
    return _norm(value)


class DuplicateRecordError(Exception):
    """Raised by ensure_no_duplicate() — server.py converts it to a 409."""

    def __init__(self, message: str, *, module: str, existing_id: Optional[str] = None,
                 existing_no: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.module = module
        self.existing_id = existing_id
        self.existing_no = existing_no

    def payload(self) -> Dict[str, Any]:
        return {"detail": self.message, "duplicate": True, "module": self.module,
                "existing_id": self.existing_id, "existing_no": self.existing_no}


def _client_ip(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


async def log_block(*, kind: str, module: str, message: str, user: Optional[dict] = None,
                    request: Optional[Request] = None, path: Optional[str] = None,
                    existing_id: Optional[str] = None, existing_no: Optional[str] = None,
                    match_key: Optional[dict] = None) -> None:
    """Journal a blocked duplicate attempt (never raises)."""
    try:
        name = user_display_name(user) if user else None
        if user and user.get("id") and (not name or "@" in str(name)):
            row = await db.users.find_one({"id": user["id"]}, {"_id": 0, "name": 1, "email": 1})
            name = user_display_name(row) if row else name
        await db.duplicate_blocks.insert_one({
            "id": new_id(),
            "at": now_iso(),
            "kind": kind,                       # business_key | rapid_resubmit
            "module": module,
            "message": message,
            "path": path or (request.url.path if request else None),
            "user_id": (user or {}).get("id"),
            "user_name": name,
            "user_role": (user or {}).get("role"),
            "existing_id": existing_id,
            "existing_no": existing_no,
            "match_key": match_key,
            "ip": _client_ip(request),
        })
    except Exception as e:  # noqa: BLE001 — logging must never break a request
        logger.warning(f"[dedupe] block log failed: {e}")


async def ensure_no_duplicate(*, module: str, collection: str, query: dict,
                              message: str, user: Optional[dict] = None,
                              request: Optional[Request] = None,
                              no_field: str = "request_no") -> None:
    """Hard-block an insert when `query` already matches a live record.

    `message` may contain `{no}` — replaced with the existing record's number.
    """
    existing = await db[collection].find_one(query, {"_id": 0, "id": 1, no_field: 1})
    if not existing:
        return
    existing_no = existing.get(no_field)
    text = message.replace("{no}", str(existing_no or "—"))
    await log_block(kind="business_key", module=module, message=text, user=user, request=request,
                    existing_id=existing.get("id"), existing_no=existing_no,
                    match_key={k: v for k, v in query.items() if not isinstance(v, dict)})
    raise DuplicateRecordError(text, module=module, existing_id=existing.get("id"),
                               existing_no=existing_no)


# ───────────────────────── submission idempotency ─────────────────────────
def _fingerprint(actor: str, path: str, body: bytes) -> str:
    h = hashlib.sha256()
    h.update(actor.encode("utf-8"))
    h.update(b"|")
    h.update(path.encode("utf-8"))
    h.update(b"|")
    h.update(body)
    return h.hexdigest()


def _actor_key(request: Request) -> str:
    token = request.cookies.get("access_token") or request.headers.get("authorization") or ""
    if token:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]
    return _client_ip(request) or "anon"


def _token_user(request: Request) -> Optional[dict]:
    """Light user identity straight off the JWT — no DB round-trip in the middleware."""
    token = request.cookies.get("access_token")
    if not token:
        header = request.headers.get("authorization") or ""
        token = header[7:] if header.startswith("Bearer ") else None
    if not token:
        return None
    try:
        import jwt
        from core import JWT_ALGORITHM, JWT_SECRET
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return {"id": payload.get("sub"), "name": payload.get("email"), "role": payload.get("role")}
    except Exception:  # noqa: BLE001
        return None


def _module_of(path: str) -> str:
    return (path.split("/api/", 1)[-1].split("/", 1)[0] or path).strip()


def _record_no(payload: Any) -> Optional[str]:
    """Pull the business number out of a cached create response (ENQ-…, REQ-…)."""
    if not isinstance(payload, dict):
        return None
    for key in ("request_no", "enquiry_no", "quote_number", "advance_no", "inv_no",
                "po_no", "pr_number", "order_no", "code", "number"):
        if payload.get(key):
            return str(payload[key])
    return None


def _resource_prefix(path: str) -> str:
    """Record this POST belongs to, e.g. /api/accounts/payment-queue/<id>/verify
    → /api/accounts/payment-queue/<id>. Any later action on the SAME record
    releases the earlier fingerprints, so a genuine redo (reject → re-verify)
    is never mistaken for a double click."""
    parts = [p for p in path.split("/api/", 1)[-1].split("/") if p]
    return "/api/" + "/".join(parts[:-1]) if len(parts) >= 3 else path


class DuplicateSubmissionMiddleware(BaseHTTPMiddleware):
    """Replays the first response for an identical POST resubmitted within the window."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method != "POST" or not path.startswith("/api/"):
            return await call_next(request)
        if any(part in path for part in EXEMPT_PATH_PARTS):
            return await call_next(request)
        if _is_state_action(path):
            return await call_next(request)
        if "multipart/form-data" in (request.headers.get("content-type") or ""):
            return await call_next(request)

        body = await request.body()
        if len(body) > MAX_BODY_BYTES:
            return await call_next(request)

        fp = _fingerprint(_actor_key(request), path, body)
        now = datetime.now(timezone.utc)
        try:
            await db.request_fingerprints.insert_one({
                "_id": fp, "path": path, "prefix": _resource_prefix(path), "at": now,
                "expires_at": now + timedelta(seconds=WINDOW_SECONDS),
            })
        except DuplicateKeyError:
            return await self._replay(request, fp, path, call_next)
        except Exception as e:  # noqa: BLE001 — a dedupe outage must not block the ERP
            logger.warning(f"[dedupe] fingerprint insert failed: {e}")
            return await call_next(request)

        response = await call_next(request)
        await self._remember(fp, response, _resource_prefix(path))
        return response

    async def _replay(self, request: Request, fp: str, path: str, call_next) -> Response:
        row = await db.request_fingerprints.find_one({"_id": fp})
        for _ in range(WAIT_TICKS):
            if row is None or row.get("response") is not None:
                break
            await asyncio.sleep(0.25)
            row = await db.request_fingerprints.find_one({"_id": fp})
        cached = (row or {}).get("response") or {}
        if cached.get("body"):
            payload = json.loads(cached["body"])
            existing_no = _record_no(payload)
            await log_block(kind="rapid_resubmit", module=_module_of(path),
                            message=f"Repeat submission — the original response"
                                    f"{f' ({existing_no})' if existing_no else ''} was returned instead of "
                                    f"creating a second record.",
                            user=_token_user(request), request=request, path=path,
                            existing_id=payload.get("id") if isinstance(payload, dict) else None,
                            existing_no=existing_no)
            return JSONResponse(status_code=cached.get("status", 200), content=payload,
                                headers={"X-Duplicate-Submission": "replayed",
                                         "X-Duplicate-Record": str(existing_no or "")})
        if row is None:
            # The original attempt failed and released the fingerprint — run this one.
            return await call_next(request)
        await log_block(kind="rapid_resubmit", module=_module_of(path),
                        message="Duplicate submission blocked — the same request was already in progress.",
                        user=_token_user(request), request=request, path=path)
        return JSONResponse(
            status_code=409,
            content={"detail": "This looks like a duplicate submission — the same request was just sent and is "
                               "still being processed. Please wait a moment instead of clicking again.",
                     "duplicate": True, "module": path},
            headers={"X-Duplicate-Submission": "blocked"},
        )

    @staticmethod
    async def _remember(fp: str, response: Response, prefix: str) -> None:
        """Cache a successful JSON response; release the fingerprint on failure."""
        try:
            status = response.status_code
            body = b""
            if hasattr(response, "body_iterator"):
                chunks = [chunk async for chunk in response.body_iterator]  # type: ignore[attr-defined]
                body = b"".join(chunks)
                response.body_iterator = _async_iter(body)  # type: ignore[attr-defined]
            elif hasattr(response, "body"):
                body = response.body or b""
            if status >= 400:
                await db.request_fingerprints.delete_one({"_id": fp})
                return
            is_json = "application/json" in (response.headers.get("content-type") or "")
            stored = body.decode("utf-8") if (is_json and 0 < len(body) <= MAX_CACHED_RESPONSE) else None
            await db.request_fingerprints.update_one(
                {"_id": fp}, {"$set": {"response": {"status": status, "body": stored}}})
            # This action changed the record — release sibling fingerprints so a
            # follow-up step on the same record is not treated as a repeat.
            await db.request_fingerprints.delete_many({"prefix": prefix, "_id": {"$ne": fp}})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[dedupe] response capture failed: {e}")


async def _async_iter(payload: bytes):
    yield payload


async def ensure_dedupe_indexes() -> None:
    try:
        await db.request_fingerprints.create_index("expires_at", expireAfterSeconds=0)
        await db.duplicate_blocks.create_index([("at", -1)])
        await db.duplicate_blocks.create_index([("module", 1), ("at", -1)])
        await db.duplicate_blocks.create_index("user_id")
        await db.duplicate_blocks.create_index("id", unique=True)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[dedupe] index ensure skipped: {e}")
