"""Backend tests for Enquiry Follow-Up Tracker.
Iter 144 covered default view + bucket badges.
Iter 145 (this) covers _norm_enquiry field mapping (client_name/enquiry_number/quotation_no),
dashboard aggregations, CSV/XLSX export headers+rows, closed-enquiry exclusion,
and mobile quick-action status validity (submitted vs invalid quotation_submitted).
"""
import os
import re
import io
import csv
import datetime
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")


def _login():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


# ─────────────────────────────────────────────────────────────
# Inbox: normalized row shape
# ─────────────────────────────────────────────────────────────
def test_inbox_all_returns_rows_with_bucket():
    s = _login()
    r = s.get(f"{BASE}/api/enquiry-followups/inbox?view=all")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] > 0, "expected open enquiries in preview DB"
    for row in data["rows"][:5]:
        assert row["_bucket"] in ("no_date", "today", "upcoming", "overdue")


def test_inbox_rows_have_real_client_and_enquiry_number():
    """Client column must not be all '-'; enquiry_number should be ENQ-...
    when enquiry_no exists (never a bare UUID fragment)."""
    s = _login()
    rows = s.get(f"{BASE}/api/enquiry-followups/inbox?view=all").json()["rows"]
    assert len(rows) > 0
    non_empty_clients = [r for r in rows if (r.get("client_name") or "").strip()]
    # Expect substantial majority of rows have real customer names
    assert len(non_empty_clients) >= max(1, int(0.5 * len(rows))), \
        f"Only {len(non_empty_clients)}/{len(rows)} rows have client_name"
    enq_prefixed = [r for r in rows if str(r.get("enquiry_number", "")).startswith("ENQ-")]
    assert len(enq_prefixed) >= max(1, int(0.5 * len(rows))), \
        f"Only {len(enq_prefixed)}/{len(rows)} rows have ENQ-... enquiry_number"
    # priority should default to 'medium' where not set
    priorities = {r.get("priority") for r in rows}
    assert "medium" in priorities, f"expected 'medium' among priorities: {priorities}"


def test_inbox_excludes_closed_enquiries():
    """No enquiry with status in {won, lost, dropped} should appear."""
    s = _login()
    rows = s.get(f"{BASE}/api/enquiry-followups/inbox?view=all").json()["rows"]
    bad = [r for r in rows if r.get("status") in ("won", "lost", "dropped")]
    assert bad == [], f"closed enquiries leaked into inbox: {bad[:3]}"


def test_inbox_shows_quotation_no_when_linked():
    """At least one row should carry quotation_no (per main agent preview: QTN-2026-0017)."""
    s = _login()
    rows = s.get(f"{BASE}/api/enquiry-followups/inbox?view=all").json()["rows"]
    with_q = [r for r in rows if (r.get("quotation_no") or "").startswith("QTN-")]
    # not strictly required across all rows but should exist somewhere
    assert len(with_q) >= 1, "expected at least one row with QTN-... quotation_no"


# ─────────────────────────────────────────────────────────────
# Dashboard aggregations
# ─────────────────────────────────────────────────────────────
def test_dashboard_consistent_and_pipeline_nonzero():
    s = _login()
    r = s.get(f"{BASE}/api/enquiry-followups/dashboard")
    assert r.status_code == 200
    d = r.json()
    for k in ("open", "due_today", "overdue", "quotations_pending", "quotations_submitted", "pipeline_value"):
        assert k in d, f"missing dashboard key: {k}"
    inbox_count = s.get(f"{BASE}/api/enquiry-followups/inbox?view=all").json()["count"]
    assert d["open"] == inbox_count
    # pipeline should now be non-zero (~557210 in preview)
    assert d["pipeline_value"] > 0, f"pipeline_value expected non-zero, got {d['pipeline_value']}"
    # quotations split should sum to open
    assert d["quotations_pending"] + d["quotations_submitted"] == d["open"], \
        f"{d['quotations_pending']}+{d['quotations_submitted']} != open {d['open']}"
    # by_client should surface real names (not all '(unknown)')
    clients = [c["client"] for c in d.get("by_client", [])]
    real_names = [c for c in clients if c and c != "(unknown)"]
    assert len(real_names) >= 1, f"by_client seems empty of real names: {clients[:5]}"


# ─────────────────────────────────────────────────────────────
# Exports
# ─────────────────────────────────────────────────────────────
def test_export_csv_contains_normalized_columns_and_rows():
    s = _login()
    r = s.get(f"{BASE}/api/enquiry-followups/export.csv?view=all")
    assert r.status_code == 200
    text = r.text
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    # Check the expected columns exist (case-insensitive contains)
    joined = ",".join(h.lower() for h in header)
    for needle in ("enquiry", "client", "quotation", "status"):
        assert needle in joined, f"CSV header missing '{needle}': {header}"
    data_rows = list(reader)
    assert len(data_rows) > 0, "CSV had no data rows"
    # At least one row references an ENQ- style number somewhere in the row
    flat = " ".join(",".join(r_) for r_ in data_rows[:20])
    assert re.search(r"ENQ-\d{4}-\d{4}", flat), f"CSV rows missing ENQ-YYYY-NNNN pattern: {flat[:400]}"


def test_export_xlsx_ok():
    s = _login()
    r = s.get(f"{BASE}/api/enquiry-followups/export.xlsx?view=all")
    assert r.status_code == 200
    ct = r.headers.get("content-type", "")
    assert "spreadsheet" in ct or "excel" in ct.lower() or "octet-stream" in ct


# ─────────────────────────────────────────────────────────────
# Follow-up post + upcoming bucket
# ─────────────────────────────────────────────────────────────
def test_upcoming_view_after_scheduling():
    s = _login()
    inbox = s.get(f"{BASE}/api/enquiry-followups/inbox?view=all").json()
    assert inbox["count"] > 0
    enq = inbox["rows"][0]
    future = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()
    r = s.post(f"{BASE}/api/enquiries/{enq['id']}/followups", json={
        "mode": "Call", "remarks": "TEST_backend regression schedule", "next_followup_date": future
    })
    assert r.status_code in (200, 201), r.text[:200]
    up = s.get(f"{BASE}/api/enquiry-followups/inbox?view=upcoming").json()
    assert any(row["id"] == enq["id"] for row in up["rows"])


# ─────────────────────────────────────────────────────────────
# Mobile quick-action status validity
# ─────────────────────────────────────────────────────────────
def test_status_transition_submitted_valid_and_quotation_submitted_invalid():
    """The mobile quick-action must post valid statuses. 'submitted' from 'open'
    should succeed; the old invalid 'quotation_submitted' must be rejected."""
    s = _login()
    # find an open enquiry — but do NOT consume the one we just scheduled follow-up on
    inbox = s.get(f"{BASE}/api/enquiry-followups/inbox?view=all").json()
    open_rows = [r for r in inbox["rows"] if r.get("status") == "open"]
    assert open_rows, "no open enquiries to test status transitions"
    target = open_rows[-1]  # take the last one to avoid conflict
    # invalid legacy status should be rejected
    bad = s.post(f"{BASE}/api/enquiries/{target['id']}/status", json={"status": "quotation_submitted"})
    assert bad.status_code == 400, f"expected 400 for invalid status, got {bad.status_code} {bad.text[:200]}"
    # valid status transition (open -> submitted) should succeed
    ok = s.post(f"{BASE}/api/enquiries/{target['id']}/status", json={"status": "submitted"})
    assert ok.status_code == 200, f"expected 200 for submitted, got {ok.status_code} {ok.text[:200]}"
