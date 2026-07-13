"""Iter 51 — Phase 2 + Phase 3 approval workflow regression."""
import os
import time
import pytest
import httpx
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
API = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")


@pytest.fixture(scope="module")
def admin():
    c = httpx.Client(base_url=f"{API}/api", timeout=30.0)
    r = c.post("/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"})
    assert r.status_code == 200
    yield c
    c.close()


def _mk_approval(*, type_="expense", title="Iter51 test") -> str:
    load_dotenv("/app/backend/.env")
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    from datetime import datetime, timezone

    async def _do():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        template = [
            {"role": "supervisor", "label": "Supervisor"},
            {"role": "accounts_executive", "label": "Finance"},
        ]
        chain = [{**s, "status": "pending", "approver": None, "at": None, "comment": None}
                 for s in template]
        doc = {
            "id": f"itr51-{int(time.time()*1000)}",
            "type": type_, "title": title, "module": "test",
            "record_id": None,
            "created_by": "admin@erp.com",
            "created_by_email": "admin@erp.com",
            "chain": chain, "current_step": 0, "history": [],
            "status": "pending", "version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.approvals.insert_one(doc)
        return doc["id"]
    return asyncio.run(_do())


def _cleanup(approval_id: str):
    load_dotenv("/app/backend/.env")
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _do():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.approvals.delete_one({"id": approval_id})
        await db.approval_versions.delete_many({"approval_id": approval_id})
        await db.notifications.delete_many({"approval_id": approval_id})
    asyncio.run(_do())


# ─── Phase 2: Version compare ───────────────────────────────────────

def test_versions_compare_returns_diff(admin):
    aid = _mk_approval(title="Compare test v1")
    try:
        # Reject and resubmit → creates v2.0
        admin.post(f"/approvals/{aid}/action",
                   json={"action": "reject", "comment": "Please redo with corrections"})
        admin.post(f"/approvals/{aid}/resubmit", json={"comment": "v2 ready"})
        # Reject again and resubmit → v3.0
        admin.post(f"/approvals/{aid}/action",
                   json={"action": "reject", "comment": "One more issue"})
        admin.post(f"/approvals/{aid}/resubmit", json={"comment": "v3 ready"})

        # Versions list
        v = admin.get(f"/approvals/{aid}/versions")
        assert v.status_code == 200
        versions = [x["version"] for x in v.json()]
        assert "2.0" in versions and "3.0" in versions

        # Compare v2 ↔ v3
        c = admin.get(f"/approvals/{aid}/versions/compare?v1=2.0&v2=3.0")
        assert c.status_code == 200, c.text
        body = c.json()
        assert body["v1"]["version"] == "2.0"
        assert body["v2"]["version"] == "3.0"
        assert isinstance(body["rows"], list)
        assert isinstance(body["history_diff"]["v1_tail"], list)
        # version row should be present and changed
        version_row = next((r for r in body["rows"] if r["key"] == "version"), None)
        assert version_row and version_row["changed"]
    finally:
        _cleanup(aid)


def test_compare_404_when_version_missing(admin):
    aid = _mk_approval()
    try:
        r = admin.get(f"/approvals/{aid}/versions/compare?v1=99.0&v2=1.0")
        assert r.status_code == 404
    finally:
        _cleanup(aid)


# ─── Phase 2: Mandatory-attachment enforcement helper ───────────────

def test_mandatory_attachment_helper_raises_400(admin):
    """The assert_attachments_for_type helper should 400 when the config flags
    the type and no file_ids are supplied."""
    # set config
    admin.put("/admin/approval-workflow-config", json={
        "restart_on_resubmit": True, "mandatory_attachment_types": ["test_mandatory_type"],
        "reject_remark_min_chars": 5, "escalation_days": 3, "reminder_days": 1,
        "auto_reminders_enabled": True,
    })
    try:
        import asyncio, sys
        sys.path.insert(0, "/app/backend")
        from fastapi import HTTPException
        from routers.approvals_router import assert_attachments_for_type

        async def run_all():
            # should pass with files
            await assert_attachments_for_type("test_mandatory_type", ["f1"])
            # should raise 400 without files
            raised = False
            try:
                await assert_attachments_for_type("test_mandatory_type", [])
            except HTTPException as e:
                raised = e.status_code == 400
            assert raised, "Expected HTTPException 400"
            # type not in list → no enforcement
            await assert_attachments_for_type("free_type", [])
        asyncio.run(run_all())
    finally:
        admin.put("/admin/approval-workflow-config", json={
            "restart_on_resubmit": True, "mandatory_attachment_types": [],
            "reject_remark_min_chars": 5, "escalation_days": 3, "reminder_days": 1,
            "auto_reminders_enabled": True,
        })


# ─── Phase 2: Reminder job idempotency ──────────────────────────────

def test_reminder_job_runs_without_errors(admin):
    """Smoke: invoke the scheduler job directly and confirm it returns without
    raising. We don't assert emails are sent (depends on stuck-window timing)."""
    import asyncio, sys
    sys.path.insert(0, "/app/backend")
    from scheduler import _approval_reminder_job, _last_results
    asyncio.run(_approval_reminder_job())
    # _last_results may be `None`, `{"skipped": "disabled"}`, or a real result
    last = _last_results.get("approval_reminders")
    assert last is None or isinstance(last, dict)


# ─── Phase 3: 5-lane dashboard ──────────────────────────────────────

def test_lanes_returns_5_buckets(admin):
    aid = _mk_approval(title="Lane bucket test")
    try:
        admin.post(f"/approvals/{aid}/action",
                   json={"action": "reject", "comment": "Send back for revision"})
        r = admin.get("/approvals/lanes")
        assert r.status_code == 200
        body = r.json()
        assert set(body["lanes"].keys()) == {
            "pending", "rejected", "revision_required",
            "additional_info", "resubmitted",
        }
        # The created approval should appear in revision_required
        rev_ids = [a["id"] for a in body["lanes"]["revision_required"]]
        assert aid in rev_ids
        assert body["totals"]["revision_required"] >= 1
    finally:
        _cleanup(aid)


def test_lanes_resubmitted_lane(admin):
    aid = _mk_approval(title="Resubmitted lane test")
    try:
        admin.post(f"/approvals/{aid}/action",
                   json={"action": "reject", "comment": "Need updates"})
        admin.post(f"/approvals/{aid}/resubmit", json={"comment": "fixed"})
        r = admin.get("/approvals/lanes")
        rs_ids = [a["id"] for a in r.json()["lanes"]["resubmitted"]]
        assert aid in rs_ids
    finally:
        _cleanup(aid)


# ─── Phase 3: Analytics ─────────────────────────────────────────────

def test_analytics_basic_shape(admin):
    r = admin.get("/approvals/analytics?days=90")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["window_days"] == 90
    assert "totals" in body and "by_type" in body and "bottleneck_roles" in body
    for k in ("approvals", "avg_cycle_days", "p50_cycle_days", "p95_cycle_days",
              "rejections", "info_requests", "resubmits"):
        assert k in body["totals"]


def test_analytics_rbac_blocks_unauthorized():
    """Analytics is restricted; unauth gets 401."""
    bare = httpx.Client(base_url=f"{API}/api", timeout=15.0)
    r = bare.get("/approvals/analytics")
    assert r.status_code == 401
    bare.close()


# ─── Phase 3: In-app notifications inbox ────────────────────────────

def test_inapp_notif_created_on_reject(admin):
    aid = _mk_approval(title="Notif test")
    try:
        # Reject → should push an in-app notification to the originator (admin)
        admin.post(f"/approvals/{aid}/action",
                   json={"action": "reject", "comment": "Reject for notification test"})
        # Allow a tiny gap (insert is awaited but the test uses HTTP)
        time.sleep(0.3)
        r = admin.get("/notifications/mine?unread_only=true")
        assert r.status_code == 200
        body = r.json()
        # admin@erp.com is the originator and a user — should see at least 1 unread
        items = body.get("items", [])
        approval_notifs = [n for n in items if n.get("approval_id") == aid]
        assert len(approval_notifs) >= 1
        notif = approval_notifs[0]
        assert notif["type"] == "approval_rejected"
        assert notif["read"] is False

        # Mark as read
        m = admin.post(f"/notifications/{notif['id']}/read")
        assert m.status_code == 200
        # Read-all
        ma = admin.post("/notifications/read-all")
        assert ma.status_code == 200
    finally:
        _cleanup(aid)


def test_inapp_notif_unread_count(admin):
    r = admin.get("/notifications/mine")
    assert r.status_code == 200
    assert "unread" in r.json()
    assert "items" in r.json()
