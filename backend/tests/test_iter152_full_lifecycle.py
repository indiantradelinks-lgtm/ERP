"""Iter 152 — Full Project Lifecycle E2E (Sales → Ops → Closure).

Chains through every stage using the real APIs, reports each failure verbosely.
Uses per-role cookie sessions. Not intended as green pytest — designed as a
diagnostic/regression scenario. Run with:
    pytest /app/backend/tests/test_iter152_full_lifecycle.py -v -s --tb=short
"""
from __future__ import annotations
import os
import io
import json
import time
import uuid
from typing import Any, Dict, Optional

import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"

# ── Credentials ─────────────────────────────────────────────────────────────
USERS: Dict[str, Dict[str, str]] = {
    "admin":    {"email": "admin@erp.com",         "password": "Admin@123"},
    "pm":       {"email": "test_pm@erp.com",       "password": "PM@12345"},
    "depthead": {"email": "depthead.ops@erp.com",  "password": "DeptHead@123"},
    "gm":       {"email": "gm@erp.com",            "password": "GM@12345"},
    "director": {"email": "director@erp.com",      "password": "Director@123"},
    "accounts": {"email": "accounts@erp.com",      "password": "Accounts@123"},
    "sales":    {"email": "sales@erp.com",         "password": "Sales@123"},
}

SESSIONS: Dict[str, requests.Session] = {}
ISSUES: list = []
ARTIFACTS: Dict[str, Any] = {}
TAG = f"E2E-TEST-{int(time.time())}"


def _log(msg: str) -> None:
    print(f"[E2E-152] {msg}")


def _issue(stage: str, endpoint: str, detail: str, resp: Optional[requests.Response] = None):
    entry = {"stage": stage, "endpoint": endpoint, "detail": detail}
    if resp is not None:
        try:
            entry["status"] = resp.status_code
            entry["body"] = resp.text[:500]
        except Exception:
            pass
    ISSUES.append(entry)
    _log(f"❌ [{stage}] {endpoint} — {detail}"
         + (f" | HTTP {resp.status_code}: {resp.text[:300]}" if resp is not None else ""))


def login(key: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json=USERS[key])
    assert r.status_code == 200, f"Login failed for {key}: {r.status_code} {r.text}"
    SESSIONS[key] = s
    return s


@pytest.fixture(scope="module", autouse=True)
def _login_all():
    for k in USERS:
        try:
            login(k)
            _log(f"✓ logged in {k} ({USERS[k]['email']})")
        except Exception as e:
            _issue("auth", "/auth/login", f"{k}: {e}")
    yield
    # Print summary
    _log("=" * 60)
    _log(f"Total issues collected: {len(ISSUES)}")
    for i, it in enumerate(ISSUES, 1):
        _log(f"{i}. [{it['stage']}] {it['endpoint']} — {it['detail']}")
    _log(f"Artifacts: {json.dumps({k: v for k, v in ARTIFACTS.items() if not isinstance(v, dict)}, default=str)}")


# ══════════════════════════════════════════════════════════════════════════
# STAGE 1 — SALES: enquiry → quotation (draft) → items → approval → won
# ══════════════════════════════════════════════════════════════════════════
def test_01_create_client_and_site():
    s = SESSIONS["admin"]
    name = f"{TAG} CLIENT"
    r = s.post(f"{BASE}/clients", json={"name": name, "status": "active", "category": "private"})
    if r.status_code != 200:
        _issue("stage1_client", "/clients", "create client failed", r)
        pytest.skip("client create failed")
    client = r.json()
    ARTIFACTS["client"] = client
    _log(f"✓ client {client.get('customer_code')} · {client['id']}")

    # Site with GST
    gst = f"27{uuid.uuid4().hex[:10].upper()}1ZZ"[:15]
    r2 = s.post(f"{BASE}/clients/{client['id']}/sites",
                json={"name": f"{TAG} SITE", "city": "Pune", "state": "Maharashtra",
                      "gst": gst, "address": "Testing lane 1"})
    if r2.status_code != 200:
        _issue("stage1_site", "/clients/{id}/sites", "create site failed", r2)
        pytest.skip("site create failed")
    site = r2.json()
    ARTIFACTS["site"] = site
    _log(f"✓ site {site.get('site_code')} · {site['id']}")


def test_02_create_enquiry_and_auto_quotation():
    if "site" not in ARTIFACTS:
        pytest.skip("no site")
    s = SESSIONS["admin"]
    payload = {
        "site_id": ARTIFACTS["site"]["id"],
        "client_id": ARTIFACTS["client"]["id"],
        "customer_enquiry_no": f"{TAG}-ENQ",
        "customer": ARTIFACTS["client"]["name"],
        "service_type": "services",
        "rfq_type": [],
        "priority": "medium",
        "scope_of_work": "E2E scaffolding erection @ 3200 m² platform area",
        "expected_value": 500000,
        "enquiry_date": "2026-01-15",
        "submission_deadline": "2026-01-30",
        "contact_person": "E2E QA",
        "contact_email": "qa@example.com",
        "contact_phone": "9999999999",
    }
    r = s.post(f"{BASE}/enquiries", json=payload)
    if r.status_code != 200:
        _issue("stage1_enquiry", "/enquiries", "create enquiry failed", r)
        pytest.skip("enq failed")
    enq = r.json()
    ARTIFACTS["enquiry"] = enq
    _log(f"✓ enquiry {enq.get('enquiry_no')} auto-quotation {enq.get('quotation_no')}")
    assert enq.get("quotation_id"), "no auto quotation"


def test_03_add_items_to_quotation():
    if "enquiry" not in ARTIFACTS:
        pytest.skip()
    s = SESSIONS["admin"]  # super_admin can direct-edit
    qid = ARTIFACTS["enquiry"]["quotation_id"]
    sections = [{
        "title": "Scaffolding Erection",
        "items": [
            {"description": "Scaffolding Erection at Site A", "quantity": 1500, "unit": "m²", "rate": 120, "gst_pct": 18},
            {"description": "Scaffolding Dismantling", "quantity": 1500, "unit": "m²", "rate": 40, "gst_pct": 18},
            {"description": "Material Rental (Steel Pipes) — monthly", "quantity": 3, "unit": "month", "rate": 30000, "gst_pct": 18},
        ],
    }]
    r = s.put(f"{BASE}/quotations/{qid}", json={"sections": sections, "total": 1500*120 + 1500*40 + 3*30000, "amount": 1500*120 + 1500*40 + 3*30000})
    if r.status_code != 200:
        _issue("stage1_qedit", f"/quotations/{qid}", "edit failed", r)
        pytest.skip()
    q = r.json()
    ARTIFACTS["quotation"] = q
    _log(f"✓ quotation items added; total {q.get('total')}")


def test_04_quotation_send_for_approval_and_approve():
    if "quotation" not in ARTIFACTS:
        pytest.skip()
    s = SESSIONS["admin"]
    qid = ARTIFACTS["quotation"]["id"]
    r = s.post(f"{BASE}/quotations/{qid}/send-for-approval", json={"documents_not_required": True, "documents_not_required_reason": "E2E test — skip docs"})
    if r.status_code != 200:
        _issue("stage1_quote_send", f"/quotations/{qid}/send-for-approval", "send failed", r)
        pytest.skip()
    approval = r.json().get("approval") or {}
    aid = approval.get("id")
    ARTIFACTS["quote_approval"] = approval
    _log(f"✓ approval created {aid}, chain len={len(approval.get('chain') or [])}")

    # Approve every step as super_admin (approval_engine allows super_admin bypass)
    for i in range(len(approval.get("chain") or [])):
        r2 = s.post(f"{BASE}/approvals/{aid}/action", json={"action": "approve", "comment": f"E2E step {i+1}"})
        if r2.status_code != 200:
            _issue("stage1_approve_step", f"/approvals/{aid}/action step={i}", f"approve failed", r2)
            break
    # Check quotation.approval_status
    q = s.get(f"{BASE}/quotations/{qid}").json() if s.get(f"{BASE}/quotations/{qid}").status_code == 200 else {}
    q2 = s.get(f"{BASE}/quotations").json()
    match = [x for x in q2 if x.get("id") == qid]
    if match:
        _log(f"quote approval_status={match[0].get('approval_status')}")

    # Now transition to submitted → won
    for status in ["submitted", "won"]:
        r3 = s.post(f"{BASE}/quotations/{qid}/status", json={"status": status, "note": f"E2E → {status}"})
        if r3.status_code != 200:
            _issue("stage1_status_transition", f"/quotations/{qid}/status → {status}", "transition failed", r3)
            break
        _log(f"✓ quotation → {status}")
        if status == "won":
            ARTIFACTS["auto_handover"] = r3.json().get("auto_handover")


def test_05_verify_pdf_download():
    if "quotation" not in ARTIFACTS:
        pytest.skip()
    qid = ARTIFACTS["quotation"]["id"]
    s = SESSIONS["admin"]
    # Try common export endpoints
    for url in [f"{BASE}/quotations/{qid}/pdf", f"{BASE}/quotations/{qid}/export.pdf",
                f"{BASE}/quotations/{qid}/download"]:
        r = s.get(url)
        if r.status_code == 200 and len(r.content) > 100:
            _log(f"✓ quotation PDF via {url} ({len(r.content)} bytes)")
            ARTIFACTS["quote_pdf_url"] = url
            return
    _issue("stage1_qpdf", "/quotations/*/pdf", "no working PDF endpoint found")


# ══════════════════════════════════════════════════════════════════════════
# STAGE 2 — HANDOVER: verify auto-handover from won quote + list contract handovers
# ══════════════════════════════════════════════════════════════════════════
def test_06_contract_handovers():
    s = SESSIONS["admin"]
    r = s.get(f"{BASE}/ops/handovers")
    if r.status_code != 200:
        _issue("stage2_handovers", "/ops/handovers", "list failed", r)
        return
    hos = r.json()
    ours = [h for h in hos if h.get("quotation_id") == ARTIFACTS.get("quotation", {}).get("id")]
    _log(f"✓ ops/handovers returned {len(hos)}; matching quote: {len(ours)}")
    if ours:
        ARTIFACTS["handover"] = ours[0]


# ══════════════════════════════════════════════════════════════════════════
# STAGE 3 — PROJECT: create project, WO with items from context, cost centers
# ══════════════════════════════════════════════════════════════════════════
def test_07_create_project():
    s = SESSIONS["admin"]
    proj_code = f"{TAG[:15]}-P1"
    payload = {
        "code": proj_code,
        "name": f"{TAG} PROJECT",
        "client": ARTIFACTS.get("client", {}).get("name", "E2E CLIENT"),
        "client_id": ARTIFACTS.get("client", {}).get("id"),
        "site": ARTIFACTS.get("site", {}).get("name", "E2E SITE"),
        "site_id": ARTIFACTS.get("site", {}).get("id"),
        "status": "active",
        "start_date": "2026-01-15",
        "end_date": "2026-06-15",
        "budget": 500000,
        "quotation_no": ARTIFACTS.get("quotation", {}).get("quote_number"),
        "quotation_id": ARTIFACTS.get("quotation", {}).get("id"),
    }
    r = s.post(f"{BASE}/projects", json=payload)
    if r.status_code != 200:
        _issue("stage3_project", "/projects", "create failed", r)
        pytest.skip()
    proj = r.json()
    ARTIFACTS["project"] = proj
    _log(f"✓ project {proj.get('code')} · id={proj['id']}")


def test_08_project_context_and_workorder():
    if "project" not in ARTIFACTS:
        pytest.skip()
    s = SESSIONS["admin"]
    code = ARTIFACTS["project"]["code"]
    r = s.get(f"{BASE}/ra-bills/project-context/{code}")
    if r.status_code != 200:
        _issue("stage3_context", f"/ra-bills/project-context/{code}", "context failed", r)
    else:
        ctx = r.json()
        ARTIFACTS["project_context"] = ctx
        _log(f"✓ project-context items={len(ctx.get('items') or [])} po_number={ctx.get('po_number')} quotation_no={ctx.get('quotation_no')}")
        if not ctx.get("items"):
            _issue("stage3_context_items", f"/ra-bills/project-context/{code}",
                   "offer items did not flow into project context (empty items[])")

    # Create WO
    wo_items = (ARTIFACTS.get("project_context") or {}).get("items") or []
    wo_payload = {
        "wo_no": f"{TAG}-WO1",
        "project_id": ARTIFACTS["project"]["id"],
        "project_code": code,
        "client_id": ARTIFACTS.get("client", {}).get("id"),
        "client_name": ARTIFACTS.get("client", {}).get("name"),
        "site_id": ARTIFACTS.get("site", {}).get("id"),
        "site_name": ARTIFACTS.get("site", {}).get("name"),
        "wo_date": "2026-01-16",
        "valid_from": "2026-01-16",
        "valid_until": "2026-07-15",
        "scope": "E2E test WO",
        "value": 500000,
        "status": "active",
        "items": [{"description": i.get("description"), "quantity": i.get("quantity") or 100,
                   "unit": i.get("unit") or "m²", "rate": i.get("rate") or 100}
                  for i in wo_items] or [{"description": "Fallback item", "quantity": 100, "unit": "m²", "rate": 120}],
        "quotation_id": ARTIFACTS.get("quotation", {}).get("id"),
        "quotation_no": ARTIFACTS.get("quotation", {}).get("quote_number"),
    }
    r2 = s.post(f"{BASE}/work-orders", json=wo_payload)
    if r2.status_code != 200:
        _issue("stage3_wo", "/work-orders", "create failed", r2)
    else:
        wo = r2.json()
        ARTIFACTS["work_order"] = wo
        _log(f"✓ work-order {wo['wo_no']} · id={wo['id']} · items={len(wo.get('items') or [])}")


def test_09_cost_centers_auto_provision():
    if "project" not in ARTIFACTS:
        pytest.skip()
    s = SESSIONS["admin"]
    pid = ARTIFACTS["project"]["id"]
    r = s.post(f"{BASE}/procurement/master/cost-centers/auto-provision/{pid}")
    if r.status_code != 200:
        _issue("stage3_cc_prov", f"/procurement/master/cost-centers/auto-provision/{pid}", "failed", r)
        return
    created = r.json()
    _log(f"✓ auto-provisioned {created.get('created')} cost centers")
    r2 = s.get(f"{BASE}/procurement/master/cost-centers", params={"project_id": pid})
    if r2.status_code != 200:
        _issue("stage3_cc_list", "/procurement/master/cost-centers", "list failed", r2)
        return
    ccs = r2.json()
    ARTIFACTS["cost_centers"] = ccs
    cats = {c.get("category_code") for c in ccs}
    _log(f"✓ cost-centers listed: {len(ccs)} categories={sorted(cats)}")


# ══════════════════════════════════════════════════════════════════════════
# STAGE 4 — EXPENSES
# ══════════════════════════════════════════════════════════════════════════
def _find_cc(category_key: str) -> Optional[str]:
    for c in ARTIFACTS.get("cost_centers") or []:
        cat = (c.get("category_code") or "").lower()
        name = (c.get("category_name") or "").lower()
        if category_key in cat or category_key in name:
            return c["id"]
    return (ARTIFACTS.get("cost_centers") or [{}])[0].get("id")


def _approve_chain_expense(eid: str, chain: list):
    """Advance the expense through its chain using the appropriate role user."""
    role_map = {
        "dept_head": "depthead",
        "general_manager": "gm",
        "director": "director",
        "accounts_executive": "accounts",
    }
    for i, step in enumerate(chain):
        role = step["role"]
        user_key = role_map.get(role, "admin")
        s = SESSIONS.get(user_key) or SESSIONS["admin"]
        r = s.post(f"{BASE}/project-expenses/{eid}/approve", json={"remarks": f"E2E step {i+1} {role}"})
        if r.status_code != 200:
            # Fallback to super_admin
            r = SESSIONS["admin"].post(f"{BASE}/project-expenses/{eid}/approve",
                                        json={"remarks": f"E2E admin bypass step {i+1}"})
        if r.status_code != 200:
            _issue("stage4_expense_approve", f"/project-expenses/{eid}/approve step={i} role={role}",
                   "approve failed", r)
            return False
    return True


def test_10_create_and_approve_expenses():
    if "project" not in ARTIFACTS:
        pytest.skip()
    pid = ARTIFACTS["project"]["id"]
    pm = SESSIONS["pm"]
    to_book = [
        ("fuel", 2000, "Small fuel bill"),
        ("ppe_safety", 4000, "PPE issue"),
        ("scaffolding_material", 30000, "Steel pipes lot"),  # LARGE — 5-step chain
    ]
    ARTIFACTS["expenses"] = []
    for etype, amt, desc in to_book:
        cc_id = _find_cc(etype.split("_")[0])
        payload = {
            "project_id": pid,
            "project_code": ARTIFACTS["project"]["code"],
            "cost_center_id": cc_id,
            "expense_type": etype,
            "expense_date": "2026-01-16",
            "amount": amt,
            "description": desc,
            "payment_mode": "Cash",
            "settlement_mode": "petty_cash",
        }
        r = pm.post(f"{BASE}/project-expenses", json=payload)
        if r.status_code != 200:
            _issue("stage4_expense_create", "/project-expenses", f"create {etype} amt={amt} failed", r)
            continue
        exp = r.json()
        ARTIFACTS["expenses"].append(exp)
        _log(f"✓ expense {exp['expense_no']} type={etype} amt={amt} large={exp.get('is_large_value')} steps={len(exp['chain'])}")
        _approve_chain_expense(exp["id"], exp["chain"])
        after = SESSIONS["admin"].get(f"{BASE}/project-expenses", params={"project_code": ARTIFACTS["project"]["code"]}).json()
        row = next((x for x in after if x["id"] == exp["id"]), {})
        _log(f"  → after approval: status={row.get('status')} je_id={row.get('je_id')}")
        if row.get("status") != "approved_for_payment":
            _issue("stage4_expense_state", f"/project-expenses/{exp['id']}",
                   f"expected approved_for_payment, got {row.get('status')}")


def test_11_notifications_for_accounts():
    s = SESSIONS["accounts"]
    r = s.get(f"{BASE}/notifications/mine")
    if r.status_code != 200:
        _issue("stage4_notif", "/notifications/mine", "list failed for accounts", r)
        return
    notes = r.json() if isinstance(r.json(), list) else (r.json().get("notifications") or [])
    rfp = [n for n in notes if n.get("kind") == "expense_payment_request"]
    _log(f"✓ accounts notifications: total={len(notes)}, RFP={len(rfp)}")
    if not rfp:
        _issue("stage4_rfp_notif", "/notifications",
               "no 'Request For Payment' (expense_payment_request) notification for accounts")


def test_12_upload_proof_and_mark_paid():
    if not ARTIFACTS.get("expenses"):
        pytest.skip()
    exp = ARTIFACTS["expenses"][0]
    acc = SESSIONS["accounts"]
    files = {"file": ("proof.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"E2E-proof" * 20), "image/png")}
    data = {"parent_type": "project_expenses", "parent_id": exp["id"], "category": "payment_proof"}
    r = acc.post(f"{BASE}/uploads", data=data, files=files)
    if r.status_code != 200:
        _issue("stage4_upload_proof", "/uploads", "upload failed", r)
        return
    _log(f"✓ payment proof uploaded")
    r2 = acc.post(f"{BASE}/project-expenses/{exp['id']}/mark-paid",
                  json={"payment_ref": f"UTR-{TAG}"})
    if r2.status_code != 200:
        _issue("stage4_mark_paid", f"/project-expenses/{exp['id']}/mark-paid", "mark-paid failed", r2)
        return
    _log(f"✓ expense {exp['expense_no']} → PAID")


def test_13_cost_center_actual_reflects_expenses():
    if "project" not in ARTIFACTS:
        pytest.skip()
    s = SESSIONS["admin"]
    pid = ARTIFACTS["project"]["id"]
    r = s.get(f"{BASE}/procurement/master/cost-centers", params={"project_id": pid})
    if r.status_code != 200:
        _issue("stage4_cc_actual", "/procurement/master/cost-centers", "list failed", r)
        return
    ccs = r.json()
    total_actual = sum(float(c.get("actual") or 0) for c in ccs)
    approved_sum = sum(float(e.get("amount") or 0) for e in ARTIFACTS.get("expenses") or [])
    _log(f"✓ cost center total actual={total_actual} (approved expenses total={approved_sum})")
    if total_actual < approved_sum * 0.5:
        _issue("stage4_actual_rollup", "/procurement/master/cost-centers",
               f"cost-center actual ({total_actual}) is much less than approved expenses ({approved_sum})")


# ══════════════════════════════════════════════════════════════════════════
# STAGE 5 — INVOICES: bill request → approve → RA bill
# ══════════════════════════════════════════════════════════════════════════
def test_14_create_and_approve_bill_request():
    if "project" not in ARTIFACTS:
        pytest.skip()
    s = SESSIONS["admin"]
    code = ARTIFACTS["project"]["code"]
    ctx = ARTIFACTS.get("project_context") or {}
    items = [{"description": i["description"], "quantity": min(i.get("quantity") or 100, 500),
              "unit": i.get("unit") or "m²", "rate": i.get("rate") or 100}
             for i in (ctx.get("items") or [])[:3]] or \
            [{"description": "E2E scaffolding partial", "quantity": 500, "unit": "m²", "rate": 120}]
    payload = {
        "project_code": code,
        "bill_type": "running",
        "period_from": "2026-01-15",
        "period_to": "2026-01-31",
        "items": items,
        "remarks": "E2E RA #1",
    }
    r = s.post(f"{BASE}/bill-requests", json=payload)
    if r.status_code != 200:
        _issue("stage5_br_create", "/bill-requests", "create failed", r)
        pytest.skip()
    br = r.json()
    ARTIFACTS["bill_request"] = br
    _log(f"✓ bill-request {br['request_no']} approval_id={br.get('approval_id')} expected={br.get('expected_amount')}")

    # Approve chain via /approvals
    aid = br.get("approval_id")
    if not aid:
        _issue("stage5_br_approval", "/bill-requests", "approval_id missing in response")
        return
    ap = s.get(f"{BASE}/approvals").json()
    chain_len = 0
    for a in (ap if isinstance(ap, list) else ap.get("approvals") or []):
        if a.get("id") == aid:
            chain_len = len(a.get("chain") or [])
            break
    _log(f"  chain_len={chain_len}")
    for i in range(max(chain_len, 5)):
        r2 = s.post(f"{BASE}/approvals/{aid}/action", json={"action": "approve", "comment": f"E2E BR step {i+1}"})
        if r2.status_code != 200:
            # Chain may already be approved
            break
    # Check status
    r3 = s.get(f"{BASE}/bill-requests/{br['id']}")
    if r3.status_code == 200:
        _log(f"  → br status={r3.json().get('status')}")


def test_15_generate_ra_bill():
    if "bill_request" not in ARTIFACTS:
        pytest.skip()
    s = SESSIONS["accounts"]  # accounts generates
    br = ARTIFACTS["bill_request"]
    payload = {
        "bill_type": "running",
        "bill_date": "2026-02-01",
        "client_id": ARTIFACTS.get("client", {}).get("id"),
        "client_name": ARTIFACTS.get("client", {}).get("name"),
        "project_id": ARTIFACTS["project"]["id"],
        "project_code": ARTIFACTS["project"]["code"],
        "site_name": ARTIFACTS.get("site", {}).get("name"),
        "items": br["items"],
        "gst_pct": 18,
        "retention_pct": 5,
        "tds_pct": 2,
        "notes": "E2E RA #1",
        "quotation_no": ARTIFACTS.get("quotation", {}).get("quote_number"),
        "submit": True,
    }
    r = s.post(f"{BASE}/ra-bills", json=payload)
    if r.status_code != 200:
        # Try as admin
        r = SESSIONS["admin"].post(f"{BASE}/ra-bills", json=payload)
    if r.status_code != 200:
        _issue("stage5_rabill", "/ra-bills", "create failed", r)
        return
    bill = r.json()
    ARTIFACTS["ra_bill"] = bill
    _log(f"✓ RA bill {bill['bill_number']} subtotal={bill.get('subtotal')} net_payable={bill.get('net_payable')}")

    # Link to bill request
    r2 = SESSIONS["admin"].post(f"{BASE}/bill-requests/{br['id']}/mark-generated",
                                 json={"bill_id": bill["id"]})
    if r2.status_code != 200:
        _issue("stage5_mark_generated", f"/bill-requests/{br['id']}/mark-generated",
               "link failed (bill request may not be fully approved)", r2)
    else:
        _log(f"✓ bill request marked generated → {r2.json()}")


# ══════════════════════════════════════════════════════════════════════════
# STAGE 6 — P&L
# ══════════════════════════════════════════════════════════════════════════
def test_16_project_pnl():
    if "project" not in ARTIFACTS:
        pytest.skip()
    s = SESSIONS["admin"]
    code = ARTIFACTS["project"]["code"]
    r = s.get(f"{BASE}/project-pnl", params={"project_code": code})
    if r.status_code != 200:
        _issue("stage6_pnl", "/project-pnl", "get failed", r)
        return
    body = r.json()
    _log(f"✓ P&L: {json.dumps(body, default=str)[:600]}")
    ARTIFACTS["pnl"] = body

    # Check income_billed matches RA bill subtotal
    ra = ARTIFACTS.get("ra_bill") or {}
    ra_sub = float(ra.get("subtotal") or 0)
    # body may be list or dict
    row = None
    if isinstance(body, list):
        row = next((x for x in body if x.get("project_code") == code), None)
    elif isinstance(body, dict):
        # single project shape
        if body.get("project_code") == code:
            row = body
        else:
            row = (body.get("projects") or [{}])[0] if body.get("projects") else body
    if row:
        income = float(row.get("income_billed") or row.get("billed") or 0)
        _log(f"  income_billed={income} vs RA subtotal={ra_sub}")
        if ra_sub and abs(income - ra_sub) > 1:
            _issue("stage6_pnl_income", "/project-pnl",
                   f"income_billed {income} != RA bill subtotal {ra_sub}")


# ══════════════════════════════════════════════════════════════════════════
# STAGE 7 — CLOSURE
# ══════════════════════════════════════════════════════════════════════════
def test_17_closure_endpoints():
    if "project" not in ARTIFACTS:
        pytest.skip()
    s = SESSIONS["admin"]
    pid = ARTIFACTS["project"]["id"]

    # Checklist
    r = s.get(f"{BASE}/proj-phase5/closure/{pid}/checklist")
    if r.status_code != 200:
        _issue("stage7_checklist", f"/proj-phase5/closure/{pid}/checklist", "failed", r)
    else:
        _log(f"✓ closure checklist items={len(r.json().get('items') or [])}")

    # Profitability
    r2 = s.get(f"{BASE}/proj-phase5/profitability/{pid}")
    if r2.status_code != 200:
        _issue("stage7_profit", f"/proj-phase5/profitability/{pid}", "failed", r2)
    else:
        _log(f"✓ profitability: {json.dumps(r2.json(), default=str)[:300]}")

    # Reports list
    r3 = s.get(f"{BASE}/proj-phase5/reports")
    if r3.status_code != 200:
        _issue("stage7_reports_list", "/proj-phase5/reports", "failed", r3)
    else:
        _log(f"✓ reports available: {len(r3.json() or [])}")

    # Try complete
    r4 = s.post(f"{BASE}/proj-phase5/closure/{pid}/complete",
                params={"override_reason": "E2E test closure"})
    if r4.status_code != 200:
        _issue("stage7_complete", f"/proj-phase5/closure/{pid}/complete",
               "complete failed (may need all checklist items done)", r4)
    else:
        _log(f"✓ project closed: {r4.json()}")

    # Verify project status
    r5 = s.get(f"{BASE}/projects")
    if r5.status_code == 200:
        me = next((p for p in r5.json() if p.get("id") == pid), None)
        _log(f"  project final status={(me or {}).get('status')}")


# ══════════════════════════════════════════════════════════════════════════
# STAGE 8 — Deep API healthchecks
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("endpoint", [
    "/enquiries", "/quotations", "/ops/handovers", "/projects",
    "/work-orders", "/project-expenses", "/procurement/master/cost-centers",
    "/bill-requests", "/ra-bills", "/project-pnl",
    "/proj-phase5/reports",
])
def test_18_page_link_endpoints(endpoint):
    s = SESSIONS["admin"]
    r = s.get(f"{BASE}{endpoint}")
    if r.status_code >= 400:
        _issue("stage8_api_healthcheck", endpoint, f"HTTP {r.status_code}", r)
    else:
        _log(f"✓ GET {endpoint} → {r.status_code} ({len(r.text)} bytes)")


def test_99_summary_dump():
    """Always-passing test that dumps issue log to a JSON artefact."""
    out_path = "/app/test_reports/iter152_issues.json"
    os.makedirs("/app/test_reports", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"issues": ISSUES, "artifacts_summary": {
            "client_id": ARTIFACTS.get("client", {}).get("id"),
            "site_id": ARTIFACTS.get("site", {}).get("id"),
            "enquiry_no": ARTIFACTS.get("enquiry", {}).get("enquiry_no"),
            "quote_no": ARTIFACTS.get("quotation", {}).get("quote_number"),
            "project_code": ARTIFACTS.get("project", {}).get("code"),
            "wo_no": (ARTIFACTS.get("work_order") or {}).get("wo_no"),
            "ra_bill_number": (ARTIFACTS.get("ra_bill") or {}).get("bill_number"),
            "expenses": [e.get("expense_no") for e in ARTIFACTS.get("expenses") or []],
        }}, f, indent=2, default=str)
    print(f"\nWROTE {out_path}")
    assert True
