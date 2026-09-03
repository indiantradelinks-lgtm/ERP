"""Iter 180 — Labour License Compliance & Expiry Tracking module tests.

Covers: CRUD, status engine, daily check + in-app alerts (idempotency), renewal +
history + audit, documents via /api/uploads, project scoping & read-only RBAC,
dashboard, scheduler job registration.
"""
import os
from datetime import date, timedelta

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = base_url.rstrip("/") + "/api"

ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
MOP = {"email": "test_mop@erp.com", "password": "Mop@12345"}

TODAY = date.today()
PFX = "TEST_LL_180"
MY_PROJECT = "PRJ-2025-01"

created_ids = []


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json=creds, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed for {creds['email']}: {r.status_code} {r.text[:300]}")
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def mop():
    return _login(MOP)


@pytest.fixture(scope="module")
def other_project(admin):
    """A project code NOT belonging to test_mop."""
    r = admin.get(f"{BASE}/projects", timeout=30)
    assert r.status_code == 200, r.text[:300]
    codes = [p.get("code") for p in r.json() if p.get("code") and p.get("code") != MY_PROJECT]
    if not codes:
        pytest.skip("No second project available")
    return codes[0]


def _create(sess, project_code, num_suffix, expiry, form_type="Form V", **extra):
    payload = {
        "project_code": project_code,
        "license_number": f"{PFX}-{num_suffix}",
        "form_type": form_type,
        "valid_from": str(TODAY - timedelta(days=30)),
        "issue_date": str(TODAY - timedelta(days=30)),
        "expiry_date": str(expiry),
        "remarks": "iter180 test",
        **extra,
    }
    return sess.post(f"{BASE}/labour-licenses", json=payload, timeout=30)


# ---------- CRUD ----------
class TestCrud:
    def test_create_and_get(self, admin):
        exp = TODAY + timedelta(days=20)
        r = _create(admin, MY_PROJECT, "A20", exp)
        assert r.status_code in (200, 201), r.text[:400]
        d = r.json()
        created_ids.append(d["id"])
        assert d["status"] == "active"
        assert d["days_remaining"] == 20
        assert d["form_type"] == "Form V"
        assert d["project_code"] == MY_PROJECT
        assert d["renewal_count"] == 0
        assert "_id" not in d

        g = admin.get(f"{BASE}/labour-licenses/{d['id']}", timeout=30)
        assert g.status_code == 200
        assert g.json()["license_number"] == f"{PFX}-A20"
        assert g.json()["status"] == "active"

    def test_invalid_form_type_rejected(self, admin):
        r = _create(admin, MY_PROJECT, "BAD", TODAY + timedelta(days=10), form_type="Form ZZZ")
        assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text[:300]}"

    def test_update_resets_alert_and_persists(self, admin):
        lid = created_ids[0]
        new_exp = str(TODAY + timedelta(days=25))
        payload = {
            "project_code": MY_PROJECT, "license_number": f"{PFX}-A20",
            "form_type": "Form VI", "expiry_date": new_exp,
            "valid_from": str(TODAY - timedelta(days=30)), "remarks": "updated",
        }
        r = admin.put(f"{BASE}/labour-licenses/{lid}", json=payload, timeout=30)
        assert r.status_code == 200, r.text[:400]
        assert r.json()["form_type"] == "Form VI"
        assert r.json()["days_remaining"] == 25
        g = admin.get(f"{BASE}/labour-licenses/{lid}", timeout=30).json()
        assert g["expiry_date"] == new_exp
        assert g["form_type"] == "Form VI"
        assert g["remarks"] == "updated"
        assert g.get("alert_sent_for") is None

    def test_update_404(self, admin):
        payload = {"project_code": MY_PROJECT, "license_number": "X", "form_type": "Form V",
                   "expiry_date": str(TODAY)}
        r = admin.put(f"{BASE}/labour-licenses/nope-does-not-exist", json=payload, timeout=30)
        assert r.status_code == 404

    def test_get_404(self, admin):
        assert admin.get(f"{BASE}/labour-licenses/nope-xyz", timeout=30).status_code == 404


# ---------- Status engine ----------
class TestStatusEngine:
    def test_three_statuses(self, admin):
        r5 = _create(admin, MY_PROJECT, "E5", TODAY + timedelta(days=5))
        r_x = _create(admin, MY_PROJECT, "X2", TODAY - timedelta(days=2))
        assert r5.status_code in (200, 201), r5.text[:300]
        assert r_x.status_code in (200, 201), r_x.text[:300]
        created_ids.extend([r5.json()["id"], r_x.json()["id"]])

        rows = admin.get(f"{BASE}/labour-licenses", timeout=30).json()
        mine = {r["license_number"]: r for r in rows if r["license_number"].startswith(PFX)}
        assert mine[f"{PFX}-E5"]["status"] == "expiring_soon"
        assert mine[f"{PFX}-E5"]["days_remaining"] == 5
        assert mine[f"{PFX}-X2"]["status"] == "expired"
        assert mine[f"{PFX}-X2"]["days_remaining"] == -2
        assert mine[f"{PFX}-A20"]["status"] == "active"

    def test_status_filter(self, admin):
        rows = admin.get(f"{BASE}/labour-licenses?status=expiring_soon", timeout=30).json()
        assert all(r["status"] == "expiring_soon" for r in rows)
        assert any(r["license_number"] == f"{PFX}-E5" for r in rows)

    def test_form_type_filter(self, admin):
        rows = admin.get(f"{BASE}/labour-licenses?form_type=Form V", timeout=30).json()
        assert all(r["form_type"] == "Form V" for r in rows)


# ---------- Daily check + alerts ----------
class TestDailyCheck:
    def test_run_check_alerts(self, admin):
        r = admin.post(f"{BASE}/labour-licenses/admin/run-daily-check", timeout=90)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["alerted"] >= 1, d
        assert d["checked"] >= 3
        assert d["expired"] >= 1

    def test_notifications_created(self, admin):
        r = admin.get(f"{BASE}/notifications/mine?limit=100", timeout=30)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        items = body if isinstance(body, list) else (body.get("items") or body.get("notifications") or [])
        target = [n for n in items if n.get("type") == "labour_license_expiry"
                  and f"{PFX}-E5" in (n.get("message") or "")]
        assert target, f"no labour_license_expiry notification found; sample={items[:3]}"
        msg = target[0]["message"]
        assert "Form V" in msg
        assert "5 day" in msg
        assert "renewal" in msg.lower()
        meta = target[0].get("meta") or {}
        if meta:
            assert meta.get("action") == "Renewal action required"
            assert meta.get("project_code") == MY_PROJECT
            assert meta.get("days_remaining") == 5

    def test_idempotent_second_run(self, admin):
        r = admin.post(f"{BASE}/labour-licenses/admin/run-daily-check", timeout=90)
        assert r.status_code == 200
        assert r.json()["alerted"] == 0, r.json()


# ---------- Renewal ----------
class TestRenewal:
    def test_renew_sets_renewed_status_and_history(self, admin):
        lid = created_ids[1]  # the E5 expiring_soon license
        new_exp = str(TODAY + timedelta(days=365))
        r = admin.post(f"{BASE}/labour-licenses/{lid}/renew", json={
            "valid_from": str(TODAY), "expiry_date": new_exp,
            "remarks": "TEST_LL_180 renewal"}, timeout=30)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["status"] == "renewed", d["status"]
        assert d["days_remaining"] >= 360
        assert d["renewal_count"] == 1
        h = d["renewal_history"][0]
        assert h["expiry_date"] == str(TODAY + timedelta(days=5))
        assert h["renewed_by"]
        assert h["renewed_at"]
        assert h["renewal_remarks"] == "TEST_LL_180 renewal"
        assert d.get("alert_sent_for") is None

        g = admin.get(f"{BASE}/labour-licenses/{lid}", timeout=30).json()
        assert g["expiry_date"] == new_exp
        assert g["status"] == "renewed"

    def test_audit_log_renew(self, admin):
        r = admin.get(f"{BASE}/admin/audit-logs?resource=labour_licenses&limit=50", timeout=30)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        items = body if isinstance(body, list) else (body.get("items") or body.get("logs") or [])
        actions = {i.get("action") for i in items}
        assert "renew" in actions, f"actions seen: {actions}"
        assert "create" in actions

    def test_renew_404(self, admin):
        r = admin.post(f"{BASE}/labour-licenses/zzz-none/renew",
                       json={"valid_from": str(TODAY), "expiry_date": str(TODAY)}, timeout=30)
        assert r.status_code == 404


# ---------- Documents ----------
class TestDocuments:
    uploaded_file_id = None

    def test_upload_and_list_and_download(self, admin):
        lid = created_ids[0]
        files = {"file": ("TEST_LL_180_doc.txt", b"labour license doc iter180", "text/plain")}
        r = admin.post(f"{BASE}/uploads", files=files,
                       data={"parent_type": "labour_license", "parent_id": lid,
                             "folder": "labour_license"}, timeout=60)
        assert r.status_code in (200, 201), r.text[:400]
        d = r.json()
        fid = d.get("id") or d.get("file_id")
        assert fid, d
        TestDocuments.uploaded_file_id = fid

        lr = admin.get(f"{BASE}/files?parent_type=labour_license&parent_id={lid}", timeout=30)
        assert lr.status_code == 200, lr.text[:300]
        body = lr.json()
        items = body if isinstance(body, list) else (body.get("items") or [])
        assert any((i.get("id") or i.get("file_id")) == fid for i in items), items[:3]

        dl = admin.get(f"{BASE}/files/{fid}/download", timeout=60)
        assert dl.status_code == 200, f"{dl.status_code} {dl.text[:200]}"


# ---------- Project scope & RBAC ----------
class TestScopeRbac:
    def test_other_project_license_created(self, admin, other_project):
        r = _create(admin, other_project, "OTHER", TODAY + timedelta(days=40))
        assert r.status_code in (200, 201), r.text[:400]
        created_ids.append(r.json()["id"])

    def test_mop_sees_only_own_projects(self, mop, other_project):
        r = mop.get(f"{BASE}/labour-licenses", timeout=30)
        assert r.status_code == 200, r.text[:300]
        rows = r.json()
        codes = {x.get("project_code") for x in rows}
        assert other_project not in codes, f"scope leak: {codes}"
        assert any(x["license_number"] == f"{PFX}-A20" for x in rows), \
            f"own-project license missing for scoped user; codes={codes}"

    def test_mop_write_forbidden(self, mop):
        r = _create(mop, MY_PROJECT, "MOPWRITE", TODAY + timedelta(days=9))
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:300]}"

    def test_mop_renew_forbidden(self, mop):
        r = mop.post(f"{BASE}/labour-licenses/{created_ids[0]}/renew",
                     json={"valid_from": str(TODAY), "expiry_date": str(TODAY + timedelta(days=1))},
                     timeout=30)
        assert r.status_code == 403, r.status_code

    def test_mop_daily_check_forbidden(self, mop):
        r = mop.post(f"{BASE}/labour-licenses/admin/run-daily-check", timeout=60)
        assert r.status_code == 403, r.status_code

    def test_mop_cannot_read_other_project_license_by_id(self, mop):
        other_id = created_ids[-1]
        r = mop.get(f"{BASE}/labour-licenses/{other_id}", timeout=30)
        assert r.status_code == 404, f"expected 404, got {r.status_code}"

    def test_unauthenticated_blocked(self):
        r = requests.get(f"{BASE}/labour-licenses", timeout=30)
        assert r.status_code in (401, 403)


# ---------- Dashboard ----------
class TestDashboard:
    def test_dashboard_cards_and_by_project(self, admin):
        r = admin.get(f"{BASE}/labour-licenses/dashboard", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        cards = d["cards"]
        for k in ("total", "active", "expiring_soon", "expired", "renewed"):
            assert k in cards and isinstance(cards[k], int)
        assert cards["total"] >= 4
        assert cards["renewed"] >= 1
        assert cards["expired"] >= 1
        projects = {p["project_code"] for p in d["by_project"]}
        assert MY_PROJECT in projects
        mine = [p for p in d["by_project"] if p["project_code"] == MY_PROJECT][0]
        assert mine["total"] >= 3

    def test_dashboard_scoped_for_mop(self, mop, other_project):
        d = mop.get(f"{BASE}/labour-licenses/dashboard", timeout=30).json()
        assert other_project not in {p["project_code"] for p in d["by_project"]}


# ---------- Regression ----------
class TestRegression:
    def test_scheduler_status_has_job(self, admin):
        r = admin.get(f"{BASE}/scheduler/status", timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert "labour_license_daily" in r.text, r.text[:600]

    @pytest.mark.parametrize("path", ["/payroll/master", "/advances", "/advance-types"])
    def test_existing_hr_endpoints(self, admin, path):
        r = admin.get(f"{BASE}{path}", timeout=30)
        assert r.status_code in (200, 404), f"{path} -> {r.status_code} {r.text[:200]}"


# ---------- Cleanup ----------
@pytest.fixture(scope="module", autouse=True)
def cleanup(admin):
    yield
    import asyncio
    import sys
    sys.path.insert(0, "/app/backend")
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _clean():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        d = cli[os.environ["DB_NAME"]]
        await d.labour_licenses.delete_many({"license_number": {"$regex": f"^{PFX}"}})
        await d.notifications.delete_many({"type": "labour_license_expiry"})
        await d.audit_logs.delete_many({"resource": "labour_licenses"})
        fid = TestDocuments.uploaded_file_id
        if fid:
            await d.files.delete_many({"id": fid})
        cli.close()

    asyncio.run(_clean())
