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
- **Iter 227 (Jun 2026) — Direct Payments for existing service vendors**: `service_direct_payment_router.py`
  (`/api/service-direct-payments`, collection `svc_direct_payments`, seq `SDP`). Eligible = vendors with a paid
  service invoice or live Service PO; optional ref PO (pre-filled from last PO, project auto-filled); raised by
  Accounts/Procurement/Logistics; amounts (invoice/GST/other/TDS → net, payment ≤ net) editable while pending;
  warning (not block) when payment > vendor's last paid; duplicate guards (vendor+invoice no across DPs and service
  invoices; identical open request same month → 409). Super Admin approve/reject (remarks required to reject) from
  the page or My Pending Approvals; approval creates a `project_requests` payment row (source
  `service_direct_payment`) in Payment Processing Center; mark-paid callback `on_direct_payment_paid` closes it and
  stamps the ref PO. Vendor-wise history endpoint, audit actions `svc_direct_payment_*`, optional attachments
  (folder `service_direct_payments`). UI: Services → Direct Payments page + 'Direct Payment' button on Service
  Requests. Existing SR workflow untouched. Tests: `tests/test_iter227_direct_payments.py` (15) + UI iteration_211.
- **Iter 226 (Jun 2026) — Performance & storage remediation (approved, implemented)**: RCA +
  before/after in `/app/memory/PERF_RCA_2026-06.md`. (a) `ai_worker.py`: every LLM call
  (challan OCR, HR doc scan, AI quotation, attendance AI, email drafts, request imports) runs in a
  short-lived child process — litellm (+160 MB) never loads in the API (RSS +2 MB per call vs +160);
  PyMuPDF text extraction also out-of-process. (b) `system_health.py` + `/api/admin/system-health`
  + Admin → System Health page: RSS/CPU/loop-lag/disk/DB/p95, slow-request log (≥1.5 s), 5-min
  samples (30 d TTL), thresholds → in-app + email alerts, daily housekeeping (temp files, technical
  logs only), malloc tuning + `gc.freeze` + `malloc_trim` after heavy exports. (c) Route-level
  `React.lazy` for all 229 pages: main bundle 4.76 MB → 686 KB. (d) `doc_storage.py`: verified
  OneDrive-primary tier (download-back + SHA-256), `fetch_bytes` OneDrive-first with object-store
  fallback, storage audit per module, `primary_reads` switch, challan PDFs registered in `files`.
  Backup taken before changes: `/app/backups/erp_database-20261105-101030.archive.gz` + files manifest.
  **Blocked on user:** valid Azure client secret for backup@indiantradelinks.in (AADSTS7000215).
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

- **Iter 220 (27 Jun 2026) — approver visibility, fuel vehicle no., RFQ vendor search** *(this change)*:
  - **My Pending Approvals** has a **Pay Mode** column: payment requests show `UPI` or `Accounts`
    (anything without an explicit UPI choice is processed by Accounts), non-payment rows show `—`.
    `/api/my-inbox` items now all carry a `payment_mode` key.
  - **Payment Request → Fuel** shows a mandatory, auto-uppercased **Vehicle Number** field; the
    backend rejects a fuel request without `vehicle_ref` (400) and stores it uppercase. The field
    clears when the request type changes, and the detail dialog shows a "Vehicle No" tile.
    Legacy tests that raised fuel requests were updated to send a vehicle number.
  - **New RFQ** vendor list has a search box (name / code / city / category) with a clear button,
    an empty-state message and a "Selected (n)" summary so filtered-out picks stay visible.
    Category filtering and "Show all vendors" still apply before the search.
  - Tests: `tests/test_iter220_paymode_fuel_vehicle.py` 6 passed; all three verified in the browser.

- **Iter 221 (30 Jun 2026) — New RA Bill white screen on Save** *(this change)*:
  - Root cause: FastAPI 422s return `detail` as a **list of objects**; pages toast
    `e.response.data.detail` directly, React cannot render an object, so the app unmounted —
    a blank white page and nothing saved. Triggered whenever a numeric box (GST/Retention/
    TDS/Advance/Qty/Rate) was left blank, since `""` fails float parsing.
  - Fix 1 (app-wide): the axios error interceptor in `lib/api.js` now flattens any non-string
    `detail` to readable text (`gst_pct: Input should be a valid number · items → 0 → ...`) and
    keeps the original under `detail_raw`, so no page can hand an object to a toast.
  - Fix 2 (form): `RaBills.create()` coerces every numeric field and line to a number, trims
    descriptions, blocks a line with no description with a clear toast, and reports failures
    through `apiErrorMessage`. A cleared % box now saves as 0 instead of erroring.
  - Tests: `tests/test_iter221_ra_bill_save.py` 4 passed + receivables suite 13 passed;
    reproduced the white screen before the fix and confirmed a clean save after.

- **Iter 222 (2 Nov 2026) — Service Request cost centres & P&V visibility** *(this change)*:
  - Cost centres exist per project × category (109 rows / 22 categories), so the SR dropdown
    repeated every category once per project with `CC-PRJ-…` codes. `/service-workflow/meta`
    now also returns `cost_center_categories` (unique, name only) and the SR form lists those,
    silently binding `cost_center_id` to the selected project's matching cost centre.
  - **Manager PNV** now sees Service Requests raised by **Manager OP** as well as its own,
    excluding Transportation / Room Rent / Accommodation categories (Logistics & Admin own
    those). Applies to both the list and the detail route via `_pnv_filter` / `_can_view_sr`;
    the `q` search can no longer widen visibility (now nested under `$and`).
  - Tests: `tests/test_iter222_svc_cc_and_pnv_visibility.py` 9 passed; both verified in the
    browser as test_mop@erp.com and test_pnv@erp.com. (`test_service_workflow_iter181.py` has
    pre-existing failures from the earlier removal of the SR approval stage.)

- **Iter 223 (3 Nov 2026) — Manager PNV owns the service procurement chain** *(this change)*:
  - `manager_pnv` added to `PROC_ROLES` (service workflow) and to `RAISE_ROLES` in
    `service_recurring_router.py`, unlocking: Create RFQ → Issue RFQ → record vendor quotations →
    comparison → vendor selection → create/submit/issue PO → SRN → vendor invoice →
    Monthly Service Payments. The UI follows automatically (`meta.role_caps.procurement`).
  - Scope kept intact: `VIEW_ALL_ROLES` now excludes `PNV_ROLES`, so Iter 222's Service Request
    visibility rule still holds, and `create_rfq` rejects a request outside P&V's scope (403) —
    Transportation / Room Rent stay with Logistics.
  - Segregation kept: vendor-invoice approval (the payment release) remains with Accounts;
    P&V can see payment status but not approve it.
  - Tests: `tests/test_iter223_pnv_procurement_chain.py` 10 passed (full chain driven as
    test_pnv@erp.com) + Iter 222/203/204 suites 34 passed; Create RFQ verified in the browser.

- **Iter 224 (3 Nov 2026) — Attendance Summary Location / Project filter** *(this change)*:
  - Root cause: the filter matched only `attendance.project_code`, but most rows carry no
    project tag (414 of 446 in preview) — the punch-machine import and auto-derive write rows
    from the punch file, and `project_code` is copied from `employees.current_project_code`,
    which is empty for staff mapped through HR **deployments** instead. So picking a project
    matched nothing and everything fell into Head Office.
  - Fix in `attendance_plus_router.py`: one shared `_project_match(project_code, month)` helper
    used by the summary **and** the breakdown export — a row counts for a project when the row
    is tagged with it OR it is untagged and the employee is mapped there (HR posting or a
    deployment overlapping the month). Head Office = tagged HO rows + untagged rows of staff
    with no posting and no deployment. New rows also stamp the deployment project at write time
    (`_deployed_project_code`), so fresh imports carry it.
  - Permanence: single code path for both endpoints + 9 regression tests that seed untagged
    attendance exactly as the importers do.
  - Tests: `tests/test_iter224_attendance_project_filter.py` 9 passed, related attendance suites
    34 passed, verified in the browser (All 43 → PRJ-2025-01 shows its 1 mapped employee).
    (`test_iter165::test_rollback` and `test_iter192::test_default_shared_view_flow` fail before
    and after this change — pre-existing.)

- **Iter 225 (4 Nov 2026) — Challan PDF → Material Lines (AI/OCR)** *(this change)*:
  - New `challan_ai.py` reads a delivery challan with **Gemini 3.1 Pro** via the Emergent
    universal key (embedded PDF text when present, page images for scans) and returns strict
    JSON: challan no, date, vehicle, and every item row with unit + quantity.
  - `POST /api/scaffolding/transfers/challan-extract?from_location_id=…` maps each row to
    `db.inventory`: exact code / normalised-name hit, else closest name ≥ 0.86 (`_norm_item`
    collapses 2.5M / 2.5 m / 2.5 MTR and unit words). Returns per-row status
    `matched | review | unmatched`, live availability, shortage flags, totals, and `lines`
    containing **only** real Item Master ids — nothing invented can reach a transfer.
  - The PDF is stored in Emergent object storage (`objstore.py`) and attached to the transfer
    (`challan_attachment`); `GET /scaffolding/transfers/{id}/challan-file` serves it back.
  - UI (`ScaffoldingMovements.jsx`): "Challan PDF → Material Lines" pane with total items,
    matched / unmatched / short counts, an editable per-row mapping table (red = unmatched,
    amber = confirm), "Load N line(s)", a shortage confirm before raising, and a challan icon
    on the transfer row to reopen the PDF.
  - The LLM call runs through `run_blocking` — the client reaches litellm synchronously and
    froze the whole API (and `/health`) before that was fixed.
  - Tests: `tests/test_iter225_challan_ai_extract.py` 10 passed against the real 29-row sample
    (`tests/fixtures/challan_sample.pdf`); verified in the browser; light API calls stayed at
    ~0.12 s while an extraction ran.

## Iter 228 — Attendance Summary (All Locations) + unlimited Google Sheet connections (18 Jun 2026)
- `attendance_plus_router._summary_data` no longer caps the month's rows at `20000`
  (production months hold 31k–37k rows — they were silently truncated, which is what made
  **All Locations & Projects** disagree with the uploads). Rows are now streamed with a cursor
  (`batch_size(2000)`, lean projection) straight into a `(employee, date)` dedupe map, so peak
  memory is one copy and re-uploads / overlapping sheets count once (newest wins).
- Rows uploaded without an `employee_id` are resolved through the employee code; otherwise they
  are grouped by employee name (never one group per row) and surfaced instead of dropped —
  "Not in master" badge + a data-quality line under the KPIs
  (`records`, `duplicates_merged`, `unresolved_rows`, `no_code_rows`, `inactive_employees`,
  `unknown_status_rows`). Unmatched rows are not clickable (no drill-down available).
- The `status == "inactive"` exclusion never matched the real master values
  (`Active/active/exited/null`); such attendance is now kept and badged **Inactive** instead of
  vanishing from the totals. The day-wise matrix export was also uncapped.
- `attendance_gsheet_router`: `MAX_SHEETS = None` — unlimited connections (verified with 46),
  `PUT /sheets/{sid}` now validates and changes the **Tab (gid)** (stores `previous_gid`,
  resets that row's sync stats, rejects a non-numeric gid and a tab already connected, and
  rewrites the stored link to the new tab); sheet fetches run under a semaphore (6) and the
  sync writes via an atomic upsert on `(employee_id, date)` so no sheet can duplicate a day.
- `GoogleSheetSync.jsx`: pencil → inline edit of label / link / gid with Save & Cancel,
  "N connected · M active" (no /40), per-row sync busy state.
- Verified: 2026-06 now counts all 17 records (9 distinct people) and the project breakdown sums
  to the all-projects total; two consecutive syncs = 0 imported / 30 unchanged, 0 duplicate
  `(employee_id, date)` pairs in Mongo; UI flows passed the testing agent (iteration_212).
- Production note: the deployer RCA also flagged the backend pod OOMKilled at tier_0 (512Mi)
  while loading those 31k–37k rows — the query is now memory-safe, but a tier bump is still
  advisable, and several Mysore sheet rows stay unmatched until their E-Codes exist in the master.

## Iter 229 — Multiple bills per month + Service Period on Bill Requests (19 Jun 2026)
- `POST /bill-requests` no longer blocks a second request for an AMC/ARC month (the
  `ensure_no_duplicate` gate on `project_code + billing_month` is removed) — part-month bills and
  several work fronts in one month can each be raised.
- **Service Period (From–To)** is now a first-class field on every bill request: month-wise
  projects pre-fill the month's first/last day but the dates stay editable, scope projects keep
  the project start/end default, and `from > to` is rejected (API 400 + a UI toast). The dates are
  stored on the request, shown in the Bill Requests list under the billing month
  (`br-period-cell-<id>`), in the request detail, and in the approval card title.
- `GET /ra-bills/project-context/{code}` month ledger now returns every request per month
  (`requests[]`, `request_count`); the month chips stay clickable, show `×N`, and an amber note in
  the dialog lists the existing request numbers instead of the old red "pick another month" error.
- Verified by curl (two requests for the same month, custom period saved, inverted range rejected)
  and by the testing agent — 7/7 UI flows passed (iteration_213); test records cleaned up.

## Backlog
- **P1** Cancel / edit an open vendor-bill payment request from the Payments popup.
- **P1** Export queue: very large reports as a background job with a "ready to download" notice.
- **P2** Admin health dashboard (slow endpoints, memory headroom).
- **P2** Verify a Resend sending domain so outbound mail reaches staff (currently test mode only).
- **P2** Archive/trim audit + notification history older than a year.
- **P2** Memory-lean large exports (openpyxl `write_only`, streaming downloads).
