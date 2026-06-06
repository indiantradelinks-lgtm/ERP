"""Iteration 33 — Data Cleanup Control Panel tests.

Covers:
- /api/admin/data-cleanup/collections (super_admin + RBAC)
- /{collection} browse + filters
- /{collection}/orphans
- /{collection}/preview-delete & /delete (with confirm=DELETE, archive on/off)
- /archive/list, /archive/restore (idempotency), /archive/purge
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
SUPERVISOR = {"email": "supervisor@erp.com", "password": "Super@1234"}

SAFE_COLL = "pr_categories"


# ─── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, f"super_admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def supervisor_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=SUPERVISOR, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"supervisor login failed: {r.status_code}")
    return s


@pytest.fixture(scope="module")
def seed_category(admin_session):
    """Create a TEST_ pr_category for delete/restore flow."""
    ts = int(time.time())
    payload = {"code": f"TST{ts}", "name": f"TEST_cleanup_{ts}", "gst_pct": 18, "active": True}
    r = admin_session.post(f"{API}/procurement/master/categories", json=payload, timeout=20)
    assert r.status_code in (200, 201), f"seed failed: {r.status_code} {r.text}"
    data = r.json()
    cid = data.get("id")
    assert cid, f"no id in seed response: {data}"
    return cid


# ─── Collections listing & RBAC ──────────────────────────────────────────────
class TestCollectionsListing:
    def test_super_admin_lists_collections(self, admin_session):
        r = admin_session.get(f"{API}/admin/data-cleanup/collections", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert "collections" in data and isinstance(data["collections"], list)
        assert data["archive_ttl_days"] == 30
        # whitelisted ones present
        names = {c["collection"] for c in data["collections"]}
        for must in ("pr_categories", "quotations", "enquiries"):
            assert must in names
        # excluded (sensitive) ones absent
        for forbidden in ("users", "audit_logs", "rbac_overrides", "login_attempts", "sessions"):
            assert forbidden not in names
        # tier values are valid
        for c in data["collections"]:
            assert c["tier"] in ("safe", "caution", "dangerous")
            assert isinstance(c["row_count"], int)

    def test_supervisor_forbidden(self, supervisor_session):
        r = supervisor_session.get(f"{API}/admin/data-cleanup/collections", timeout=20)
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text}"


# ─── Browse w/ filters ───────────────────────────────────────────────────────
class TestBrowseCollection:
    def test_browse_safe_coll(self, admin_session):
        r = admin_session.get(f"{API}/admin/data-cleanup/{SAFE_COLL}", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert "total" in data and "rows" in data
        assert isinstance(data["rows"], list)

    def test_browse_with_keyword(self, admin_session, seed_category):
        r = admin_session.get(
            f"{API}/admin/data-cleanup/{SAFE_COLL}",
            params={"q": "TEST_cleanup"},
            timeout=20,
        )
        assert r.status_code == 200
        data = r.json()
        # at least the seeded one matches
        assert any("TEST_cleanup" in (row.get("name") or "") for row in data["rows"]), \
            f"seeded TEST_cleanup not found in rows: {data['rows'][:3]}"

    def test_browse_with_older_than(self, admin_session):
        r = admin_session.get(
            f"{API}/admin/data-cleanup/{SAFE_COLL}",
            params={"older_than_days": 0},
            timeout=20,
        )
        assert r.status_code == 200

    def test_browse_unknown_collection(self, admin_session):
        r = admin_session.get(f"{API}/admin/data-cleanup/bogus_xyz", timeout=20)
        assert r.status_code == 400

    def test_browse_excluded_collection(self, admin_session):
        # users is excluded from whitelist → 400
        r = admin_session.get(f"{API}/admin/data-cleanup/users", timeout=20)
        assert r.status_code == 400

    def test_browse_supervisor_forbidden(self, supervisor_session):
        r = supervisor_session.get(f"{API}/admin/data-cleanup/{SAFE_COLL}", timeout=20)
        assert r.status_code == 403


# ─── Orphans ─────────────────────────────────────────────────────────────────
class TestOrphans:
    def test_orphans_for_collection_with_refs(self, admin_session):
        r = admin_session.get(f"{API}/admin/data-cleanup/quotations/orphans", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "rows" in data and isinstance(data["rows"], list)

    def test_orphans_no_refs_collection(self, admin_session):
        r = admin_session.get(f"{API}/admin/data-cleanup/pr_categories/orphans", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert "note" in data

    def test_orphans_supervisor_forbidden(self, supervisor_session):
        r = supervisor_session.get(f"{API}/admin/data-cleanup/quotations/orphans", timeout=20)
        assert r.status_code == 403


# ─── Preview + Delete ────────────────────────────────────────────────────────
class TestPreviewAndDelete:
    def test_preview_requires_ids(self, admin_session):
        r = admin_session.post(
            f"{API}/admin/data-cleanup/{SAFE_COLL}/preview-delete",
            json={"ids": []},
            timeout=20,
        )
        assert r.status_code == 400

    def test_preview_returns_match(self, admin_session, seed_category):
        r = admin_session.post(
            f"{API}/admin/data-cleanup/{SAFE_COLL}/preview-delete",
            json={"ids": [seed_category]},
            timeout=20,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["matched"] == 1
        assert data["total_requested"] == 1
        assert len(data["sample"]) == 1
        assert data["sample"][0]["id"] == seed_category

    def test_delete_wrong_confirm(self, admin_session, seed_category):
        r = admin_session.post(
            f"{API}/admin/data-cleanup/{SAFE_COLL}/delete",
            json={"ids": [seed_category], "confirm": "delete"},
            timeout=20,
        )
        assert r.status_code == 400

    def test_delete_missing_confirm(self, admin_session, seed_category):
        r = admin_session.post(
            f"{API}/admin/data-cleanup/{SAFE_COLL}/delete",
            json={"ids": [seed_category]},
            timeout=20,
        )
        assert r.status_code == 400

    def test_soft_delete_archives_and_purges_original(self, admin_session, seed_category):
        # Verify exists first
        b = admin_session.get(
            f"{API}/admin/data-cleanup/{SAFE_COLL}",
            params={"q": seed_category},
            timeout=20,
        ).json()
        assert any(r["id"] == seed_category for r in b["rows"])

        # Soft delete
        r = admin_session.post(
            f"{API}/admin/data-cleanup/{SAFE_COLL}/delete",
            json={"ids": [seed_category], "confirm": "DELETE",
                  "archive": True, "reason": "iter33 test"},
            timeout=20,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["deleted"] == 1
        assert data["archived"] == 1
        assert "restorable_until" in data

        # Original gone
        b2 = admin_session.get(
            f"{API}/admin/data-cleanup/{SAFE_COLL}",
            params={"q": seed_category},
            timeout=20,
        ).json()
        assert not any(r["id"] == seed_category for r in b2["rows"])

        # Archive entry exists
        a = admin_session.get(
            f"{API}/admin/data-cleanup/archive/list",
            params={"collection": SAFE_COLL},
            timeout=20,
        ).json()
        assert any(row["doc_id"] == seed_category for row in a["rows"]), \
            "archive should contain the soft-deleted doc"

    def test_archive_restore_brings_back(self, admin_session, seed_category):
        # find archive id
        a = admin_session.get(
            f"{API}/admin/data-cleanup/archive/list",
            params={"collection": SAFE_COLL},
            timeout=20,
        ).json()
        archive_entry = next((row for row in a["rows"] if row["doc_id"] == seed_category), None)
        assert archive_entry is not None
        arch_id = archive_entry["id"]

        # restore
        r = admin_session.post(
            f"{API}/admin/data-cleanup/archive/restore",
            json={"archive_ids": [arch_id]},
            timeout=20,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["restored"] == 1
        assert data["skipped"] == []

        # confirm row back in collection
        b = admin_session.get(
            f"{API}/admin/data-cleanup/{SAFE_COLL}",
            params={"q": seed_category},
            timeout=20,
        ).json()
        assert any(r["id"] == seed_category for r in b["rows"])

        # restoring same arch_id again → archive entry is gone → skipped (or restored=0)
        r2 = admin_session.post(
            f"{API}/admin/data-cleanup/archive/restore",
            json={"archive_ids": [arch_id]},
            timeout=20,
        )
        assert r2.status_code == 200
        d2 = r2.json()
        # since archive entry deleted on restore, second call has nothing to do
        assert d2["restored"] == 0

    def test_hard_purge_no_archive(self, admin_session, seed_category):
        # seed_category should be back now after restore
        r = admin_session.post(
            f"{API}/admin/data-cleanup/{SAFE_COLL}/delete",
            json={"ids": [seed_category], "confirm": "DELETE", "archive": False, "reason": "hard"},
            timeout=20,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["deleted"] == 1
        assert data["archived"] == 0

        # original gone
        b = admin_session.get(
            f"{API}/admin/data-cleanup/{SAFE_COLL}",
            params={"q": seed_category},
            timeout=20,
        ).json()
        assert not any(row["id"] == seed_category for row in b["rows"])

        # no new archive entry for this id
        a = admin_session.get(
            f"{API}/admin/data-cleanup/archive/list",
            params={"collection": SAFE_COLL},
            timeout=20,
        ).json()
        assert not any(row["doc_id"] == seed_category for row in a["rows"])

    def test_delete_supervisor_forbidden(self, supervisor_session):
        r = supervisor_session.post(
            f"{API}/admin/data-cleanup/{SAFE_COLL}/delete",
            json={"ids": ["xxx"], "confirm": "DELETE"},
            timeout=20,
        )
        assert r.status_code == 403


# ─── Archive endpoints ───────────────────────────────────────────────────────
class TestArchive:
    def test_archive_list(self, admin_session):
        r = admin_session.get(f"{API}/admin/data-cleanup/archive/list", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert "rows" in data and "ttl_days" in data

    def test_archive_filter_by_collection(self, admin_session):
        r = admin_session.get(
            f"{API}/admin/data-cleanup/archive/list",
            params={"collection": "quotations"},
            timeout=20,
        )
        assert r.status_code == 200
        for row in r.json()["rows"]:
            assert row["collection"] == "quotations"

    def test_archive_supervisor_forbidden(self, supervisor_session):
        r = supervisor_session.get(f"{API}/admin/data-cleanup/archive/list", timeout=20)
        assert r.status_code == 403

    def test_purge_supervisor_forbidden(self, supervisor_session):
        r = supervisor_session.delete(
            f"{API}/admin/data-cleanup/archive/purge?older_than_days=0", timeout=20
        )
        assert r.status_code == 403

    def test_restore_supervisor_forbidden(self, supervisor_session):
        r = supervisor_session.post(
            f"{API}/admin/data-cleanup/archive/restore",
            json={"archive_ids": ["x"]},
            timeout=20,
        )
        assert r.status_code == 403
