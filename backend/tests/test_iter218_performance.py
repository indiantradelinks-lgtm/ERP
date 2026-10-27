"""Iter 218 — performance hardening: blocking work off the event loop, safe headers, indexes."""
import asyncio
import os
import time

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=60)
    assert r.status_code == 200, r.text
    return sess


def test_run_blocking_keeps_the_loop_free():
    """A 1 s blocking call must not stop other coroutines from making progress."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from offload import run_blocking

    async def main():
        ticks = 0

        async def ticker():
            nonlocal ticks
            for _ in range(20):
                await asyncio.sleep(0.05)
                ticks += 1

        t = asyncio.create_task(ticker())
        await run_blocking(time.sleep, 1.0)
        await t
        return ticks

    assert asyncio.run(main()) >= 15, "the event loop was starved while blocking work ran"


def test_heavy_pdf_does_not_stall_other_requests(s):
    """Three report PDFs render while light calls keep answering quickly."""
    import threading
    heavy_done = []

    def heavy():
        r = s.get(f"{API}/billing/pending-report/export", params={"fmt": "pdf", "month": "all"}, timeout=180)
        heavy_done.append(r.status_code)

    threads = [threading.Thread(target=heavy) for _ in range(3)]
    for t in threads:
        t.start()
    time.sleep(0.3)
    timings = []
    for _ in range(5):
        started = time.perf_counter()
        r = s.get(f"{API}/sites", timeout=60)
        assert r.status_code == 200
        timings.append(time.perf_counter() - started)
    for t in threads:
        t.join(180)
    assert heavy_done == [200, 200, 200]
    assert max(timings) < 3.0, f"light calls were blocked by the renders: {timings}"


@pytest.mark.parametrize("path,params", [
    ("/billing/pending-report/export", {"fmt": "pdf", "month": "all"}),
    ("/allocations/export", {"fmt": "pdf"}),
    ("/allocations/export", {"fmt": "xlsx"}),
    ("/scaffolding/export.xlsx", {"kind": "stock"}),
])
def test_exports_still_produce_real_files(s, path, params):
    r = s.get(f"{API}{path}", params=params, timeout=180)
    assert r.status_code == 200, r.text[:200]
    assert len(r.content) > 5000
    if params.get("fmt") == "pdf":
        assert r.content[:4] == b"%PDF"
    else:
        assert r.content[:2] == b"PK"


def test_hot_path_indexes_exist():
    from pymongo import MongoClient
    db = MongoClient("mongodb://localhost:27017")["erp_database"]
    expected = {
        "scaf_stock": ["item_loc", "location_id_1"],
        "vendor_bills": ["vendor_id_1", "invoice_no_1"],
        "vendor_payments": ["bill_ids_1"],
        "material_allocations": ["project_id_1"],
        "quotations": ["quote_number_1"],
    }
    for coll, idxs in expected.items():
        have = set(db[coll].index_information())
        for i in idxs:
            assert i in have, f"{coll} is missing index {i} (have {sorted(have)})"


def test_only_one_replica_schedules_jobs():
    from pymongo import MongoClient
    db = MongoClient("mongodb://localhost:27017")["erp_database"]
    lease = db.scheduler_lease.find_one({"_id": "erp-scheduler"})
    assert lease and lease.get("holder"), "scheduler lease missing — every replica would run the jobs"


def test_api_latency_is_healthy(s):
    paths = ["/sites", "/projects", "/quotations?page=1&page_size=50", "/enquiries",
             "/allocations", "/scaffolding/stock-matrix", "/my-inbox"]
    slow = []
    for p in paths:
        started = time.perf_counter()
        r = s.get(f"{API}{p}", timeout=60)
        took = time.perf_counter() - started
        assert r.status_code == 200, p
        if took > 2.5:
            slow.append((p, round(took, 2)))
    assert not slow, f"slow endpoints: {slow}"
