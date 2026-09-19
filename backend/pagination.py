"""Shared server-side pagination / search / sort helpers for list endpoints."""
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import Request

from core import db

SAFE_FIELD = re.compile(r"^[A-Za-z0-9_.]{1,64}$")
MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50
RESERVED_PARAMS = {"search", "page", "page_size", "master", "sort_by", "sort_dir", "search_keys",
                   "fields", "limit", "status", "folder", "parent_type", "parent_id", "unread_only"}


def clamp_page(page: int, page_size: int) -> Tuple[int, int]:
    return max(1, int(page or 1)), max(1, min(int(page_size or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))


def search_clause(search: str, keys: Iterable[str]) -> Optional[dict]:
    s = (search or "").strip()
    keys = [k for k in keys if k and SAFE_FIELD.match(k)]
    if not s or not keys:
        return None
    rx = {"$regex": re.escape(s), "$options": "i"}
    return {"$or": [{k: rx} for k in keys]}


def parse_keys(csv: str) -> List[str]:
    return [k.strip() for k in (csv or "").split(",") if k.strip() and SAFE_FIELD.match(k.strip())]


def sort_spec(sort_by: str, sort_dir: str, default: str = "created_at") -> List[Tuple[str, int]]:
    field = sort_by.strip() if sort_by and SAFE_FIELD.match(sort_by.strip()) else default
    direction = 1 if (sort_dir or "").lower() == "asc" else -1
    spec = [(field, direction)]
    if field != "id":
        spec.append(("id", direction))  # stable tie-breaker
    return spec


def extra_filters(request: Request) -> List[dict]:
    """`f_<field>=value` query params become equality filters; comma → $in."""
    out: List[dict] = []
    for key, value in request.query_params.multi_items():
        if not key.startswith("f_"):
            continue
        field = key[2:]
        if not SAFE_FIELD.match(field) or value == "":
            continue
        vals = [v for v in value.split(",") if v != ""]
        out.append({field: vals[0]} if len(vals) == 1 else {field: {"$in": vals}})
    return out


def projection(fields: str) -> dict:
    keys = parse_keys(fields)
    proj: Dict[str, Any] = {"_id": 0}
    if keys:
        proj.update({k: 1 for k in keys})
        proj["id"] = 1
    return proj


def combine(*clauses: Optional[dict]) -> dict:
    parts = [c for c in clauses if c]
    if not parts:
        return {}
    if len(parts) == 1:
        return parts[0]
    return {"$and": parts}


async def paged_find(collection: str, q: dict, page: int, page_size: int,
                     sort: List[Tuple[str, int]], proj: Optional[dict] = None) -> dict:
    page, page_size = clamp_page(page, page_size)
    total = await db[collection].count_documents(q)
    cursor = db[collection].find(q, proj or {"_id": 0}).sort(sort)
    try:
        rows = await cursor.allow_disk_use(True).skip((page - 1) * page_size).limit(page_size).to_list(page_size)
    except Exception:
        rows = await db[collection].find(q, proj or {"_id": 0}).skip((page - 1) * page_size)\
            .limit(page_size).to_list(page_size)
    return {"rows": rows, "total": total, "page": page, "page_size": page_size,
            "pages": max(1, -(-total // page_size))}


async def maybe_paged(request: Request, collection: str, q: dict, default_sort: str = "created_at",
                      default_keys: Iterable[str] = ()) -> Optional[dict]:
    """Return a paged result when `page>=1` is in the query string, else None (legacy path)."""
    qp = request.query_params
    try:
        page = int(qp.get("page") or 0)
    except ValueError:
        page = 0
    if page < 1:
        return None
    keys = parse_keys(qp.get("search_keys", "")) or list(default_keys)
    full_q = combine(q, search_clause(qp.get("search", ""), keys), *extra_filters(request))
    try:
        page_size = int(qp.get("page_size") or DEFAULT_PAGE_SIZE)
    except ValueError:
        page_size = DEFAULT_PAGE_SIZE
    return await paged_find(collection, full_q, page, page_size,
                            sort_spec(qp.get("sort_by", ""), qp.get("sort_dir", "desc"), default_sort))


def paged_or_rows(paged: Optional[dict], rows: list):
    return {**paged, "rows": rows} if paged else rows
