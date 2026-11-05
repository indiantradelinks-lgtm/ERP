"""Microsoft Graph OneDrive integration (app-only / client_credentials).

Pushes files one-way from Emergent object storage to a user's OneDrive
(typically a dedicated backup account such as `backup@indiantradelinks.in`).

Key features
------------
- Settings (tenant_id / client_id / client_secret / backup_user_upn / base_folder)
  are persisted in `db.settings._id="onedrive"`; the client_secret is encrypted
  at rest using the existing `M365_FERNET_KEY` (Fernet).
- MSAL `ConfidentialClientApplication` with a persistent `SerializableTokenCache`
  stored in `db.onedrive_token_cache` so tokens survive process restarts.
- Auto folder-creation for nested paths like `2026/02/Quotations`.
- Small files via `PUT …/content`; files > 4 MB via resumable upload session.
- All Graph calls go through one `httpx.AsyncClient` per call (short-lived).

Public coroutines
-----------------
- `get_settings()`           → dict (decrypted, safe for backend use)
- `save_settings(payload)`   → persists + re-initialises MSAL app
- `test_connection()`        → returns `{ok, drive_id, drive_name, owner}`
- `upload_bytes(path, name, data, content_type)` → uploads to backup drive
- `upload_path(folder_segments, filename, data, content_type)`

This module is intentionally backend-only — the router calls into it.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Optional
from urllib.parse import quote, unquote

import httpx
import msal
from cryptography.fernet import Fernet, InvalidToken

from core import db, now_iso

logger = logging.getLogger("erp.onedrive")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
DEFAULT_SCOPE = ["https://graph.microsoft.com/.default"]
LARGE_FILE_THRESHOLD = 4 * 1024 * 1024  # 4 MB — anything larger uses upload session
CHUNK_SIZE = 5 * 1024 * 1024            # 5 MB chunks for resumable uploads

# ── Name sanitisation ───────────────────────────────────────────────────
# OneDrive/SharePoint reject these characters in item names, and '#'/'%'
# additionally break Graph's `root:/path:/content` addressing — the cause of
# the repeated "400 Bad Request" push failures. Names are cleaned, then the
# whole path is URL-encoded before it goes on the wire.
SANITIZER_VERSION = 2
_INVALID_CHARS = "\"*:<>?/\\|#%{}^~[]`'"
_MAX_NAME_LEN = 180
_RESERVED = {"con", "prn", "aux", "nul", "com1", "com2", "com3", "com4",
             "lpt1", "lpt2", "lpt3", ".lock", "desktop.ini", "_vti_"}


def safe_name(name: str) -> str:
    """Make `name` a valid OneDrive file name (extension preserved)."""
    raw = (name or "").strip()
    # Undo accidental URL-encoding coming from upstream filenames ("MOB%20BILL.pdf")
    if "%" in raw:
        try:
            unq = unquote(raw)
            if unq and "%" not in unq:
                raw = unq
        except Exception:  # noqa: BLE001
            pass
    cleaned = "".join("_" if (c in _INVALID_CHARS or ord(c) < 32) else c for c in raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    cleaned = re.sub(r"_{2,}", "_", cleaned)
    if not cleaned or cleaned.lower() in _RESERVED:
        cleaned = ("file_" + cleaned).strip("_") or "file"
    if len(cleaned) > _MAX_NAME_LEN:
        stem, dot, ext = cleaned.rpartition(".")
        if dot and 0 < len(ext) <= 8:
            cleaned = stem[: _MAX_NAME_LEN - len(ext) - 1].strip(" ._") + "." + ext
        else:
            cleaned = cleaned[:_MAX_NAME_LEN].strip(" ._")
    return cleaned


def safe_segment(segment: str) -> str:
    """Make `segment` a valid OneDrive folder name."""
    return safe_name(str(segment or "").replace("/", "_").replace("\\", "_")).strip(" .")


def _quote_path(path: str) -> str:
    """URL-encode a drive path, keeping '/' separators intact."""
    return quote(path, safe="/")


def is_retryable(exc: Exception) -> tuple[bool, str]:
    """(retryable?, short reason). 429/5xx/network are transient; other 4xx are permanent."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (408, 429) or code >= 500:
            return True, f"http_{code}"
        return False, f"http_{code}"
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True, "network"
    msg = str(exc).lower()
    if any(k in msg for k in ("authority", "token", "credential", "disabled", "not configured")):
        return True, "auth_or_config"   # admin-fixable → keep retrying
    return True, "unknown"

_FERNET_KEY = os.environ.get("M365_FERNET_KEY", "").strip()
_fernet: Optional[Fernet] = Fernet(_FERNET_KEY.encode()) if _FERNET_KEY else None

# In-process MSAL app cache (re-built on settings save)
_msal_app: Optional[msal.ConfidentialClientApplication] = None
_token_cache: Optional[msal.SerializableTokenCache] = None
_settings_cache: Optional[dict] = None
_init_lock = asyncio.Lock()


# ────────────────────────────────────────────────────────────────────────
# Secret encryption helpers
# ────────────────────────────────────────────────────────────────────────
def _enc(plain: str) -> str:
    if not _fernet:
        raise RuntimeError("M365_FERNET_KEY not configured")
    return _fernet.encrypt(plain.encode("utf-8")).decode("utf-8")


def _dec(token: str) -> str:
    if not _fernet:
        raise RuntimeError("M365_FERNET_KEY not configured")
    try:
        return _fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("Failed to decrypt onedrive secret") from e


# ────────────────────────────────────────────────────────────────────────
# Settings
# ────────────────────────────────────────────────────────────────────────
async def get_settings(*, include_secret: bool = False) -> dict:
    """Returns the current OneDrive settings. The client_secret is masked
    unless `include_secret=True` (backend-internal use only)."""
    global _settings_cache
    if _settings_cache and not include_secret:
        out = dict(_settings_cache)
        if out.get("client_secret"):
            out["client_secret"] = "********"
        return out
    doc = await db.settings.find_one({"_id": "onedrive"}, {"_id": 0}) or {}
    if not doc:
        return {
            "enabled": False,
            "tenant_id": "",
            "client_id": "",
            "client_secret": "",
            "backup_user_upn": "",
            "base_folder": "ITL-ERP-Backups",
            "configured": False,
        }
    secret = ""
    if doc.get("client_secret_enc"):
        try:
            secret = _dec(doc["client_secret_enc"])
        except Exception as e:
            logger.error(f"Failed to decrypt onedrive secret: {e}")
    out = {
        "enabled": doc.get("enabled", False),
        "tenant_id": doc.get("tenant_id", ""),
        "client_id": doc.get("client_id", ""),
        "client_secret": secret,
        "backup_user_upn": doc.get("backup_user_upn", ""),
        "base_folder": doc.get("base_folder", "ITL-ERP-Backups"),
        "primary_reads": doc.get("primary_reads", True),
        "configured": bool(doc.get("tenant_id") and doc.get("client_id") and doc.get("client_secret_enc")),
        "last_test_at": doc.get("last_test_at"),
        "last_test_ok": doc.get("last_test_ok"),
        "last_test_error": doc.get("last_test_error"),
        "drive_id": doc.get("drive_id"),
        "drive_name": doc.get("drive_name"),
    }
    _settings_cache = dict(out)
    if not include_secret and out.get("client_secret"):
        out["client_secret"] = "********"
    return out


async def save_settings(payload: dict) -> dict:
    """Persists settings; encrypts the secret. Resets in-process MSAL app."""
    global _msal_app, _token_cache, _settings_cache
    tenant_id = (payload.get("tenant_id") or "").strip()
    client_id = (payload.get("client_id") or "").strip()
    client_secret = (payload.get("client_secret") or "").strip()
    backup_user_upn = (payload.get("backup_user_upn") or "").strip()
    base_folder = (payload.get("base_folder") or "ITL-ERP-Backups").strip()
    enabled = bool(payload.get("enabled", True))

    update = {
        "tenant_id": tenant_id,
        "client_id": client_id,
        "backup_user_upn": backup_user_upn,
        "base_folder": base_folder,
        "enabled": enabled,
        "primary_reads": bool(payload.get("primary_reads", True)),
        "updated_at": now_iso(),
    }
    # Only overwrite the encrypted secret if a non-masked value is supplied
    if client_secret and client_secret != "********":
        update["client_secret_enc"] = _enc(client_secret)

    await db.settings.update_one({"_id": "onedrive"}, {"$set": update}, upsert=True)
    _settings_cache = None
    _msal_app = None
    _token_cache = None
    return await get_settings()


# ────────────────────────────────────────────────────────────────────────
# MSAL token acquisition (persisted cache in MongoDB)
# ────────────────────────────────────────────────────────────────────────
async def _load_msal() -> msal.ConfidentialClientApplication:
    global _msal_app, _token_cache
    async with _init_lock:
        if _msal_app is not None:
            return _msal_app
        s = await get_settings(include_secret=True)
        if not s.get("configured"):
            raise RuntimeError("OneDrive integration not configured")
        cache = msal.SerializableTokenCache()
        doc = await db.onedrive_token_cache.find_one({"_id": s["client_id"]})
        if doc and doc.get("cache"):
            try:
                cache.deserialize(doc["cache"])
            except Exception as e:
                logger.warning(f"Failed to deserialize MSAL cache: {e}")
        app = msal.ConfidentialClientApplication(
            client_id=s["client_id"],
            client_credential=s["client_secret"],
            authority=f"https://login.microsoftonline.com/{s['tenant_id']}",
            token_cache=cache,
        )
        _msal_app = app
        _token_cache = cache
        return app


async def _persist_cache():
    global _token_cache
    s = _settings_cache or await get_settings()
    if _token_cache and _token_cache.has_state_changed and s.get("client_id"):
        await db.onedrive_token_cache.update_one(
            {"_id": s["client_id"]},
            {"$set": {"cache": _token_cache.serialize(), "updated_at": now_iso()}},
            upsert=True,
        )


async def _acquire_token() -> str:
    app = await _load_msal()
    # client_credentials flow doesn't use accounts; just acquire for client
    result = app.acquire_token_silent(scopes=DEFAULT_SCOPE, account=None)
    if not result:
        result = app.acquire_token_for_client(scopes=DEFAULT_SCOPE)
    if "access_token" not in result:
        err = result.get("error_description") or result.get("error") or "unknown"
        raise RuntimeError(f"Graph token acquisition failed: {err}")
    await _persist_cache()
    return result["access_token"]


async def _headers(extra: dict | None = None) -> dict:
    token = await _acquire_token()
    h = {"Authorization": f"Bearer {token}"}
    if extra:
        h.update(extra)
    return h


# ────────────────────────────────────────────────────────────────────────
# Drive + folder helpers
# ────────────────────────────────────────────────────────────────────────
async def _get_backup_drive() -> dict:
    s = await get_settings(include_secret=False)
    upn = s.get("backup_user_upn")
    if not upn:
        raise RuntimeError("backup_user_upn not configured")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{GRAPH_BASE}/users/{upn}/drive", headers=await _headers())
        resp.raise_for_status()
        return resp.json()


async def _ensure_folder(drive_id: str, segments: list[str]) -> dict:
    """Walks the path; creates missing folders. Returns the final folder driveItem."""
    if not segments:
        # Return drive root
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{GRAPH_BASE}/drives/{drive_id}/root", headers=await _headers())
            resp.raise_for_status()
            return resp.json()

    segments = [safe_segment(seg) for seg in segments if safe_segment(seg)]
    current_path = ""
    final_item: dict = {}
    async with httpx.AsyncClient(timeout=30) as client:
        for i, seg in enumerate(segments):
            seg_safe = seg
            current_path = f"{current_path}/{seg_safe}" if current_path else seg_safe
            url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{_quote_path(current_path)}"
            r = await client.get(url, headers=await _headers())
            if r.status_code == 200:
                final_item = r.json()
                continue
            if r.status_code != 404:
                r.raise_for_status()
            # Create folder under parent
            if i == 0:
                parent_url = f"{GRAPH_BASE}/drives/{drive_id}/root/children"
            else:
                parent_path = "/".join(segments[:i]).strip("/")
                parent_url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{_quote_path(parent_path)}:/children"
            body = {
                "name": seg_safe,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "fail",
            }
            cr = await client.post(parent_url, headers=await _headers({"Content-Type": "application/json"}), json=body)
            if cr.status_code == 409:
                # Race condition: another worker created it. Re-fetch.
                rr = await client.get(url, headers=await _headers())
                rr.raise_for_status()
                final_item = rr.json()
            else:
                cr.raise_for_status()
                final_item = cr.json()
    return final_item


# ────────────────────────────────────────────────────────────────────────
# Public test + upload
# ────────────────────────────────────────────────────────────────────────
async def test_connection() -> dict:
    """Attempts to authenticate and resolve the configured backup drive.
    Persists result on the settings doc."""
    try:
        drive = await _get_backup_drive()
        owner = (drive.get("owner") or {}).get("user", {}) or {}
        info = {
            "ok": True,
            "drive_id": drive.get("id"),
            "drive_name": drive.get("name"),
            "drive_type": drive.get("driveType"),
            "owner": owner.get("displayName") or owner.get("email") or "",
            "quota": drive.get("quota") or {},
        }
        await db.settings.update_one(
            {"_id": "onedrive"},
            {"$set": {
                "last_test_at": now_iso(),
                "last_test_ok": True,
                "last_test_error": None,
                "drive_id": info["drive_id"],
                "drive_name": info["drive_name"],
            }},
            upsert=True,
        )
        global _settings_cache
        _settings_cache = None
        return info
    except Exception as e:
        err = str(e)
        if isinstance(e, httpx.HTTPStatusError):
            err = f"{e.response.status_code}: {e.response.text[:300]}"
        logger.error(f"OneDrive test_connection failed: {err}")
        await db.settings.update_one(
            {"_id": "onedrive"},
            {"$set": {"last_test_at": now_iso(), "last_test_ok": False, "last_test_error": err}},
            upsert=True,
        )
        return {"ok": False, "error": err}


async def download_item(item_id: str) -> tuple[bytes, str]:
    """Fetch a driveItem's content from the backup drive (primary / fallback reads)."""
    s = await get_settings(include_secret=False)
    drive_id = s.get("drive_id") or (await _get_backup_drive())["id"]
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        r = await client.get(f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content", headers=await _headers())
        r.raise_for_status()
        return r.content, r.headers.get("content-type", "application/octet-stream")


async def upload_to_folder(
    folder_segments: list[str],
    filename: str,
    data: bytes,
    content_type: str | None = None,
) -> dict:
    """Upload `data` as `filename` into `<base_folder>/<segments...>/`.
    Returns the resulting driveItem json."""
    s = await get_settings(include_secret=False)
    if not s.get("enabled") or not s.get("configured"):
        raise RuntimeError("OneDrive integration disabled or not configured")
    base = (s.get("base_folder") or "").strip().strip("/")
    full_segments = ([base] if base else []) + [seg for seg in folder_segments if seg]

    drive = await _get_backup_drive()
    drive_id = drive["id"]
    folder = await _ensure_folder(drive_id, full_segments)
    parent_id = folder["id"]

    if len(data) <= LARGE_FILE_THRESHOLD:
        return await _upload_small(drive_id, parent_id, filename, data, content_type)
    return await _upload_large(drive_id, parent_id, filename, data)


async def _upload_small(drive_id: str, parent_id: str, filename: str, data: bytes, content_type: str | None) -> dict:
    """Single-shot PUT for files ≤ 4 MB (replaces on retry, so pushes are idempotent)."""
    name = safe_name(filename)
    url = (f"{GRAPH_BASE}/drives/{drive_id}/items/{parent_id}:/{_quote_path(name)}:/content"
           "?@microsoft.graph.conflictBehavior=replace")
    headers = await _headers({"Content-Type": content_type or "application/octet-stream"})
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.put(url, headers=headers, content=data)
        r.raise_for_status()
        return r.json()


async def _upload_large(drive_id: str, parent_id: str, filename: str, data: bytes) -> dict:
    """Resumable upload session for files > 4 MB."""
    name = safe_name(filename)
    create_url = f"{GRAPH_BASE}/drives/{drive_id}/items/{parent_id}:/{_quote_path(name)}:/createUploadSession"
    body = {"item": {"@microsoft.graph.conflictBehavior": "replace", "name": name}}
    async with httpx.AsyncClient(timeout=None) as client:
        r = await client.post(create_url, headers=await _headers({"Content-Type": "application/json"}), json=body)
        r.raise_for_status()
        session = r.json()
        upload_url = session["uploadUrl"]

        total = len(data)
        sent = 0
        last_resp: Optional[httpx.Response] = None
        while sent < total:
            chunk = data[sent:sent + CHUNK_SIZE]
            end = sent + len(chunk) - 1
            chunk_headers = {
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {sent}-{end}/{total}",
            }
            resp = await client.put(upload_url, headers=chunk_headers, content=chunk)
            if resp.status_code not in (200, 201, 202):
                resp.raise_for_status()
            sent += len(chunk)
            last_resp = resp
        return last_resp.json() if last_resp and last_resp.content else {}
