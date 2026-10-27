# INDIAN TRADE LINKS — ERP (WorkSite Command)

React + FastAPI + MongoDB ERP covering Procurement, Sales, Accounts, HR, Projects,
Store/Inventory, Logistics, approvals, PDF/Excel exports and RBAC.
Backend routes are prefixed `/api`; frontend calls via `REACT_APP_BACKEND_URL`.

## Core product rules (standing)
- Duplicate prevention blocks genuine business duplicates and records blocked attempts for audit.
- Payment requests dedupe on project + vendor/employee + amount + type while open/unpaid.
- Repeat employee advances are allowed when legitimate; identical instant resubmissions are blocked.
- Sales auto-creates/heals exactly one quotation per enquiry.
- Vendor invoice payment states: `advance_paid`, `partially_paid`, `fully_paid`.
- An advance / payment release never short-circuits a bill's approval chain.

## Implemented (recent)
- **Iter 208–217**: repeat advances unblock, ICICI CMS bank-file format, Pending Billing all-month
  filter + Excel/PDF exports, vendor bill advance/part payments, PO PDF terms + project name,
  bulk stock adjustment/transfer via Excel, project-wise allocation exports, enquiry→quotation coverage.
- **Iter 218 (Jun 2026) — Cloudflare 520s & ERP slowness**: root cause was backend-origin —
  pods OOMKilled at 512 Mi (tier_0) plus synchronous PDF/Excel generation blocking the single
  Uvicorn event loop (a 300-row report PDF froze all requests ~5 s, timing out `/health`).
  Fixes: `offload.run_blocking` for all 39 PDF/Excel endpoints (concurrency-capped), gc after
  WeasyPrint render, Mongo pool limits in `core.py`, hot-path indexes via `perf_indexes.py`,
  Mongo-backed scheduler leader lock so only one replica runs the ~15 jobs, Latin-1 response
  header sanitiser in `server.py`. Tests: 9 + 47 passed. **Still required from the user:
  raise the deployment from tier_0/512 Mi to at least tier_1.**
- **Iter 219 (27 Jun 2026) — Vendor Bill → Payment Processing routing** *(this change)*:
  - Payments popup now offers two routes: **Send to Payment Processing** (default — creates a
    linked payment request that appears in Accounts → Payment Processing for verification,
    bank file and UTR) and **Already paid** (previous behaviour, records a settled VPAY).
  - `POST /api/payables/vendor-bills/{id}/payment-requests` creates the request; `GET .../payments`
    now returns `pending_requests`, `pending_amount`, `payable_now`.
  - Fixed dedupe bug: a bill could never re-enter the queue once any earlier request existed —
    now only *un-paid* requests block, and instalments get `-P2`, `-P3` request numbers.
  - `mark_paid` for `accounts_vendor_bill` now mirrors the release back onto the bill via
    `settle_bill_from_payment_queue` (writes a vendor_payments history row, recomputes
    paid/outstanding/payment_status, and no longer forces status on unapproved bills).
  - Double-payment guards: the "Already paid" route blocks amounts beyond
    outstanding − queued, and verification cannot exceed the requested amount.
  - Tests: `tests/test_iter219_bill_payment_request_queue.py` 9 passed; regression 68 passed.
    Testing agent report: `/app/test_reports/iteration_209.json` (all HIGH items fixed).

## Backlog
- **P1** Cancel / edit an open vendor-bill payment request from the Payments popup.
- **P1** Export queue: very large reports as a background job with a "ready to download" notice.
- **P2** Admin health dashboard (slow endpoints, memory headroom).
- **P2** Verify a Resend sending domain so outbound mail reaches staff (currently test mode only).
- **P2** Archive/trim audit + notification history older than a year.
- **P2** Memory-lean large exports (openpyxl `write_only`, streaming downloads).
