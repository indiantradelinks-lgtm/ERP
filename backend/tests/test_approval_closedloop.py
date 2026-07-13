"""Iter 50 — Phase 1 closed-loop approval workflow regression."""
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


def _mk_approval(admin, *, type_="expense", title="Test approval", record_id=None) -> str:
    """Create an approval doc directly via mongo (no admin REST endpoint for raw insert)."""
    load_dotenv("/app/backend/.env")
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    from datetime import datetime, timezone

    async def _do():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        # Build a chain by hitting the public chains endpoint
        chains = (await db.approval_chains.find_one({"type": type_}, {"_id": 0})) or {}
        template = chains.get("steps") or [
            {"role": "supervisor", "label": "Supervisor"},
            {"role": "accounts_executive", "label": "Finance"},
        ]
        if type_ == "expense":
            template = [
                {"role": "supervisor", "label": "Supervisor"},
                {"role": "accounts_executive", "label": "Finance"},
            ]
        chain = [{**s, "status": "pending", "approver": None, "at": None, "comment": None}
                 for s in template]
        doc = {
            "id": f"itr50-test-{int(time.time()*1000)}",
            "type": type_, "title": title,
            "module": "test", "record_id": record_id,
            "created_by": "originator@erp.com",
            "created_by_email": "originator@erp.com",
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
    asyncio.run(_do())


# ─── Mandatory remarks ──────────────────────────────────────────────

def test_reject_without_remark_returns_400(admin):
    aid = _mk_approval(admin)
    try:
        r = admin.post(f"/approvals/{aid}/action", json={"action": "reject"})
        assert r.status_code == 400
        assert "5 characters" in r.json()["detail"]
        # also blank string
        r2 = admin.post(f"/approvals/{aid}/action", json={"action": "reject", "comment": "  "})
        assert r2.status_code == 400
    finally:
        _cleanup(aid)


def test_reject_with_short_remark_returns_400(admin):
    aid = _mk_approval(admin)
    try:
        r = admin.post(f"/approvals/{aid}/action", json={"action": "reject", "comment": "no"})
        assert r.status_code == 400
    finally:
        _cleanup(aid)


# ─── Closed loop: reject → revision_required → resubmit ─────────────

def test_reject_flips_to_rejected_revision_required(admin):
    aid = _mk_approval(admin)
    try:
        r = admin.post(f"/approvals/{aid}/action",
                       json={"action": "reject", "comment": "Budget exceeds allocation by 25%."})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "rejected_revision_required"
        assert body["last_reject_reason"].startswith("Budget exceeds")
        assert body["rejected_at_step"] == 0
        assert len(body["history"]) == 1
        assert body["history"][0]["action"] == "reject"
        assert body["history"][0]["version"] == "1.0"
    finally:
        _cleanup(aid)


def test_resubmit_restarts_chain_from_zero_by_default(admin):
    aid = _mk_approval(admin)
    try:
        # Reject at step 0
        admin.post(f"/approvals/{aid}/action",
                   json={"action": "reject", "comment": "Please re-check the vendor quote attached."})
        # Resubmit
        r = admin.post(f"/approvals/{aid}/resubmit",
                       json={"comment": "Updated quote attached", "file_ids": ["test-file-1"]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["version"] == "2.0"
        assert body["status"] == "pending"           # back to step 0
        assert body["current_step"] == 0
        # every chain step reset
        assert all(s["status"] == "pending" for s in body["chain"])
        assert body["resubmit_count"] == 1
        assert "test-file-1" in body.get("attachments", [])
        # Version snapshot recorded
        v = admin.get(f"/approvals/{aid}/versions")
        assert v.status_code == 200
        assert len(v.json()) >= 1
        assert v.json()[0]["version"] == "2.0"
    finally:
        _cleanup(aid)


def test_resubmit_resumes_from_rejected_step_when_admin_configured(admin):
    # Flip admin setting to disable restart
    r = admin.put("/admin/approval-workflow-config",
                  json={"restart_on_resubmit": False,
                        "mandatory_attachment_types": [], "reject_remark_min_chars": 5})
    assert r.status_code == 200
    try:
        aid = _mk_approval(admin)
        # Approve step 0 first
        admin.post(f"/approvals/{aid}/action", json={"action": "approve", "comment": "OK"})
        # Reject at step 1
        admin.post(f"/approvals/{aid}/action",
                   json={"action": "reject", "comment": "Finance does not agree to this cost."})
        # Resubmit → should resume at step 1, NOT step 0
        r2 = admin.post(f"/approvals/{aid}/resubmit",
                        json={"comment": "Adjusted figures"})
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["current_step"] == 1
        assert body["status"] == "in_progress"
        _cleanup(aid)
    finally:
        # Restore default
        admin.put("/admin/approval-workflow-config",
                  json={"restart_on_resubmit": True,
                        "mandatory_attachment_types": [], "reject_remark_min_chars": 5})


# ─── request_info path ──────────────────────────────────────────────

def test_request_info_flips_status_with_docs_and_deadline(admin):
    aid = _mk_approval(admin)
    try:
        r = admin.post(f"/approvals/{aid}/action", json={
            "action": "request_info",
            "comment": "Need vendor PAN and last 3 invoices.",
            "required_documents": ["Vendor PAN", "Invoice #1", "Invoice #2", "Invoice #3"],
            "deadline": "2026-06-30",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "additional_info_required"
        info = body["last_info_request"]
        assert "Vendor PAN" in info["required_documents"]
        assert info["deadline"] == "2026-06-30"
        assert body["chain"][0]["status"] == "info_requested"
    finally:
        _cleanup(aid)


def test_request_info_without_remark_returns_400(admin):
    aid = _mk_approval(admin)
    try:
        r = admin.post(f"/approvals/{aid}/action", json={
            "action": "request_info", "comment": "",
            "required_documents": ["PAN"], "deadline": "2026-06-30",
        })
        assert r.status_code == 400
    finally:
        _cleanup(aid)


# ─── Resubmit gating ────────────────────────────────────────────────

def test_resubmit_fails_when_not_rejected(admin):
    aid = _mk_approval(admin)
    try:
        # Fresh approval (status=pending) — can't resubmit
        r = admin.post(f"/approvals/{aid}/resubmit", json={"comment": "x"})
        assert r.status_code == 400
        assert "Cannot resubmit" in r.json()["detail"]
    finally:
        _cleanup(aid)


# ─── my-revisions inbox ─────────────────────────────────────────────

def test_my_revisions_lists_only_bounced_back(admin):
    aid = _mk_approval(admin)
    try:
        admin.post(f"/approvals/{aid}/action",
                   json={"action": "reject", "comment": "Need revision asap."})
        r = admin.get("/approvals/my-revisions")
        assert r.status_code == 200
        ids = [a["id"] for a in r.json()]
        assert aid in ids
        # statuses are restricted to bounce-back set
        for a in r.json():
            assert a["status"] in {"rejected_revision_required", "additional_info_required", "rejected"}
    finally:
        _cleanup(aid)


# ─── Admin config CRUD ──────────────────────────────────────────────

def test_admin_config_default_and_update(admin):
    g = admin.get("/admin/approval-workflow-config")
    assert g.status_code == 200
    body = g.json()
    assert body.get("restart_on_resubmit") in (True, False)
    # Toggle
    r = admin.put("/admin/approval-workflow-config",
                  json={"restart_on_resubmit": False,
                        "mandatory_attachment_types": ["PR>5L"],
                        "reject_remark_min_chars": 10})
    assert r.status_code == 200
    g2 = admin.get("/admin/approval-workflow-config")
    assert g2.json()["restart_on_resubmit"] is False
    assert g2.json()["mandatory_attachment_types"] == ["PR>5L"]
    # Restore
    admin.put("/admin/approval-workflow-config",
              json={"restart_on_resubmit": True,
                    "mandatory_attachment_types": [], "reject_remark_min_chars": 5})


# ─── Original happy path still works (regression) ───────────────────

def test_approve_terminal_status_still_works(admin):
    aid = _mk_approval(admin)
    try:
        # Two steps in the test chain (supervisor + accounts_executive); super_admin
        # can act on any step.
        r1 = admin.post(f"/approvals/{aid}/action", json={"action": "approve", "comment": "ok"})
        assert r1.status_code == 200
        assert r1.json()["status"] == "in_progress"
        r2 = admin.post(f"/approvals/{aid}/action", json={"action": "approve", "comment": "ok"})
        assert r2.status_code == 200
        assert r2.json()["status"] == "approved"
    finally:
        _cleanup(aid)
