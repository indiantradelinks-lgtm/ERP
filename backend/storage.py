"""Emergent built-in object storage helper.

Uses EMERGENT_LLM_KEY for auth. Soft-delete is implemented in MongoDB
(the storage backend has no delete API). All paths are prefixed with APP_NAME
to keep namespaces isolated.
"""
import os
import uuid
import logging
import requests

logger = logging.getLogger("erp.storage")

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
APP_NAME = os.environ.get("APP_NAME", "worksite-command")

_storage_key: str | None = None

MIME_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp", "heic": "image/heic",
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv", "txt": "text/plain",
}

MAX_BYTES = 25 * 1024 * 1024  # 25 MB


def init_storage() -> str | None:
    """Initialise the session-scoped storage key. Returns None on failure (storage stays disabled)."""
    global _storage_key
    if _storage_key:
        return _storage_key
    emergent_key = os.environ.get("EMERGENT_LLM_KEY")
    if not emergent_key:
        logger.warning("EMERGENT_LLM_KEY not set — object storage disabled.")
        return None
    try:
        resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": emergent_key}, timeout=30)
        resp.raise_for_status()
        _storage_key = resp.json().get("storage_key")
        logger.info("Object storage initialised.")
        return _storage_key
    except Exception as e:
        logger.exception(f"Object storage init failed: {e}")
        return None


def _resolve_content_type(filename: str, provided: str | None) -> str:
    if provided and provided != "application/octet-stream":
        return provided
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return MIME_TYPES.get(ext, "application/octet-stream")


def put_object(folder: str, filename: str, data: bytes, content_type: str | None = None) -> dict:
    """Upload bytes. Returns {path, size, etag, content_type}."""
    key = init_storage()
    if not key:
        raise RuntimeError("Object storage not initialised")
    if len(data) > MAX_BYTES:
        raise ValueError(f"File too large ({len(data)} bytes; max {MAX_BYTES})")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    resolved_ct = _resolve_content_type(filename, content_type)
    path = f"{APP_NAME}/{folder}/{uuid.uuid4()}.{ext}"
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": resolved_ct},
        data=data,
        timeout=120,
    )
    resp.raise_for_status()
    body = resp.json()
    body["content_type"] = resolved_ct
    return body


def get_object(path: str) -> tuple[bytes, str]:
    """Download. Returns (bytes, content_type)."""
    key = init_storage()
    if not key:
        raise RuntimeError("Object storage not initialised")
    resp = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
