"""Iteration 204 — Service Invoice attachment auto-mirrors to Accounts payment row.

Validates file_links.mirror_service_invoice_docs:
  1. Upload-after-push: uploading a doc to a service_invoices parent that already has
     a project_requests payment row creates a mirrored link row on the payment row
     with auto_linked=True and linked_from.type='service_invoices'. Download works.
  2. Idempotency: re-uploading the same file (sha256) and re-triggering the mirror
     does not create duplicates on the destination.
  3. No leakage A → direct uploads to project_requests do NOT appear on the
     service invoice.
  4. No leakage B → invoice A docs never appear on invoice B's payment row.
  5. Regression: a normal upload for an unrelated parent_type (vendor_bills) does
     not get mirrored anywhere.
"""
import io
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text[:200]}"
    # Session carries the httpOnly cookie automatically
    return s


@pytest.fixture(scope="module")
def service_invoice_rows(session):
    """Discover service-invoice payment rows already in the Accounts queue."""
    r = session.get(f"{API}/service-workflow/payments", timeout=20)
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    rows = data if isinstance(data, list) else data.get("rows") or data.get("items") or []
    # Each row is a svc_invoices doc. We also need its project_requests id.
    assert rows, "No service-invoice payment rows found in preview DB — cannot test mirror"
    # Enrich with pr_id by querying project_requests
    enriched = []
    for row in rows:
        inv_id = row.get("id")
        if not inv_id:
            continue
        pr = session.get(f"{API}/project-requests",
                         params={"source": "service_invoice", "source_id": inv_id},
                         timeout=15)
        pr_row = None
        if pr.status_code == 200:
            body = pr.json()
            candidates = body if isinstance(body, list) else body.get("rows") or body.get("items") or []
            for c in candidates:
                if c.get("source") == "service_invoice" and c.get("source_id") == inv_id:
                    pr_row = c
                    break
        if pr_row:
            enriched.append({"inv_id": inv_id, "inv_no": row.get("inv_no"),
                             "pr_id": pr_row["id"], "pr_no": pr_row.get("request_no")})
    assert enriched, "Could not resolve payment row ids for any invoice"
    return enriched


# tracked for cleanup
_created_file_ids: list = []


def _upload(session, parent_type, parent_id, folder, name="iter204-doc.txt", content=None):
    content = content or f"iter204 {uuid.uuid4()}".encode()
    files = {"file": (name, io.BytesIO(content), "text/plain")}
    data = {"folder": folder, "parent_type": parent_type, "parent_id": parent_id,
            "title": name}
    r = session.post(f"{API}/uploads", files=files, data=data, timeout=30)
    return r, content


def _list_files(session, parent_type, parent_id):
    r = session.get(f"{API}/files",
                    params={"parent_type": parent_type, "parent_id": parent_id},
                    timeout=15)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    return body if isinstance(body, list) else body.get("rows") or body.get("items") or []


# ---------- tests ----------
class TestUploadAfterPushMirror:
    def test_upload_mirrors_to_payment_row_and_download_works(self, session, service_invoice_rows):
        tgt = service_invoice_rows[0]
        name = f"TEST_iter204_{uuid.uuid4().hex[:8]}.txt"
        resp, content = _upload(session, "service_invoices", tgt["inv_id"], "service_invoices", name=name)
        assert resp.status_code == 200, resp.text[:300]
        rec = resp.json()
        assert rec.get("parent_type") == "service_invoices"
        assert rec.get("parent_id") == tgt["inv_id"]
        src_file_id = rec["id"]
        _created_file_ids.append(src_file_id)

        # Mirror should appear on the payment row
        pr_files = _list_files(session, "project_requests", tgt["pr_id"])
        mirrored = [f for f in pr_files
                    if (f.get("linked_from") or {}).get("file_id") == src_file_id]
        assert mirrored, (
            f"Mirrored row not found on payment row {tgt['pr_id']}. "
            f"Files: {[f.get('original_filename') for f in pr_files]}")
        m = mirrored[0]
        assert m.get("auto_linked") is True, f"auto_linked not True: {m}"
        assert (m.get("linked_from") or {}).get("type") == "service_invoices"
        assert m.get("sha256") == rec.get("sha256")
        assert m.get("id") != src_file_id, "mirror must have its own id"
        _created_file_ids.append(m["id"])

        # Accounts download of the mirrored row works
        dl = session.get(f"{API}/files/{m['id']}/download", timeout=20)
        assert dl.status_code == 200, dl.text[:200]
        assert dl.content == content, "Downloaded bytes do not match original"

    def test_mirror_is_idempotent_on_duplicate_upload(self, session, service_invoice_rows):
        tgt = service_invoice_rows[0]
        payload = f"iter204-dup-{uuid.uuid4()}".encode()
        name = f"TEST_iter204_dup_{uuid.uuid4().hex[:8]}.txt"

        r1, _ = _upload(session, "service_invoices", tgt["inv_id"], "service_invoices",
                        name=name, content=payload)
        assert r1.status_code == 200
        rec1 = r1.json()
        _created_file_ids.append(rec1["id"])
        assert rec1.get("duplicate") is not True

        before_count = len(_list_files(session, "project_requests", tgt["pr_id"]))

        # Second identical upload — server should return duplicate=True
        r2, _ = _upload(session, "service_invoices", tgt["inv_id"], "service_invoices",
                        name=name, content=payload)
        assert r2.status_code == 200
        rec2 = r2.json()
        assert rec2.get("duplicate") is True, f"Expected duplicate flag, got {rec2}"
        assert rec2.get("id") == rec1["id"]

        after_count = len(_list_files(session, "project_requests", tgt["pr_id"]))
        assert after_count == before_count, (
            f"Mirror duplicated! before={before_count} after={after_count}")

        # And ensure only one mirror exists for this sha256 on the payment row
        pr_files = _list_files(session, "project_requests", tgt["pr_id"])
        matching = [f for f in pr_files if f.get("sha256") == rec1.get("sha256")]
        assert len(matching) == 1, f"Expected 1 mirrored row for sha, got {len(matching)}"


class TestNoLeakage:
    def test_direct_payment_row_upload_does_not_appear_on_invoice(self, session, service_invoice_rows):
        tgt = service_invoice_rows[0]
        name = f"TEST_iter204_pr_{uuid.uuid4().hex[:8]}.txt"
        resp, _ = _upload(session, "project_requests", tgt["pr_id"], "project_requests", name=name)
        assert resp.status_code == 200, resp.text[:300]
        rec = resp.json()
        _created_file_ids.append(rec["id"])
        assert rec.get("auto_linked") is not True, "Direct PR upload must not be auto_linked"

        # Must NOT appear on the invoice
        inv_files = _list_files(session, "service_invoices", tgt["inv_id"])
        assert rec["id"] not in [f.get("id") for f in inv_files]
        # Also no sha-level leak
        assert rec.get("sha256") not in [f.get("sha256") for f in inv_files]

    def test_invoice_a_doc_does_not_leak_to_invoice_b_payment_row(self, session, service_invoice_rows):
        if len(service_invoice_rows) < 2:
            pytest.skip("Need at least 2 service invoices with payment rows")
        a, b = service_invoice_rows[0], service_invoice_rows[1]
        name = f"TEST_iter204_isolate_{uuid.uuid4().hex[:8]}.txt"
        resp, _ = _upload(session, "service_invoices", a["inv_id"], "service_invoices", name=name)
        assert resp.status_code == 200
        rec = resp.json()
        _created_file_ids.append(rec["id"])

        other = _list_files(session, "project_requests", b["pr_id"])
        for f in other:
            lf = f.get("linked_from") or {}
            assert lf.get("file_id") != rec["id"], (
                f"Invoice A doc leaked onto Invoice B payment row! file={f}")
            assert f.get("sha256") != rec.get("sha256") or f.get("parent_id") == b["pr_id"] and lf.get("id") != a["inv_id"]


class TestRegressionOtherParentTypes:
    def test_vendor_bills_upload_no_mirror_no_error(self, session):
        # Dummy parent_id — mirror logic only triggers for service_invoices
        parent_id = f"TEST_iter204_vb_{uuid.uuid4().hex[:8]}"
        resp, _ = _upload(session, "vendor_bills", parent_id, "vendor_bills",
                          name=f"TEST_iter204_vb_{uuid.uuid4().hex[:6]}.txt")
        assert resp.status_code == 200, resp.text[:300]
        rec = resp.json()
        _created_file_ids.append(rec["id"])
        assert rec.get("auto_linked") is not True
        assert rec.get("linked_from") is None

        # And delete works
        d = session.delete(f"{API}/files/{rec['id']}", timeout=15)
        assert d.status_code == 200, d.text[:200]


# ---------- cleanup ----------
def teardown_module(module):
    try:
        s = requests.Session()
        s.post(f"{API}/auth/login", json=ADMIN, timeout=15)
        for fid in _created_file_ids:
            try:
                s.delete(f"{API}/files/{fid}", timeout=10)
            except Exception:
                pass
    except Exception:
        pass
