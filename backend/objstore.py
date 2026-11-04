"""Emergent managed object storage — used for challan PDFs kept with a transfer."""
import logging
import os

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("erp")

STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
APP_NAME = "itl-erp"

_storage_key = None


def init_storage(force: bool = False) -> str:
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    r = requests.post(f"{STORAGE_URL}/init",
                      json={"emergent_key": os.environ.get("EMERGENT_LLM_KEY")}, timeout=30)
    r.raise_for_status()
    _storage_key = r.json()["storage_key"]
    return _storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    r = requests.put(f"{STORAGE_URL}/objects/{path}",
                     headers={"X-Storage-Key": init_storage(), "Content-Type": content_type},
                     data=data, timeout=120)
    if r.status_code == 404:                       # cached key went inactive
        r = requests.put(f"{STORAGE_URL}/objects/{path}",
                         headers={"X-Storage-Key": init_storage(force=True), "Content-Type": content_type},
                         data=data, timeout=120)
    r.raise_for_status()
    return r.json()


def get_object(path: str) -> tuple:
    r = requests.get(f"{STORAGE_URL}/objects/{path}",
                     headers={"X-Storage-Key": init_storage()}, timeout=60)
    if r.status_code == 404:
        r = requests.get(f"{STORAGE_URL}/objects/{path}",
                         headers={"X-Storage-Key": init_storage(force=True)}, timeout=60)
    r.raise_for_status()
    return r.content, r.headers.get("Content-Type", "application/octet-stream")
