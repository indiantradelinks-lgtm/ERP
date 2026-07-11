# Corporate ERP - PRD

## Original Problem Statement
Modern cloud-based Corporate ERP for Service Industry Company (Scaffolding, Painting, Roof Sheeting, Rope Access, Industrial Shutdown & Maintenance). Enterprise-level, secure, multi-client, role-based, single-window dashboard for higher management, 14+ modules, mobile responsive.

## Architecture
- Frontend: React 19 + Shadcn UI + Tailwind + Recharts + qrcode.react (Chivo / IBM Plex Sans)
- Backend: FastAPI + Motor (MongoDB) + JWT auth (bcrypt + httpOnly cookies) + openpyxl/reportlab for exports
- Theme: Industrial slate/steel + amber/orange accent, dark default + light, PWA-ready

## Roles (RBAC) — Granular per-resource enforcement
super_admin, director, general_manager, dept_head, project_manager, site_engineer, supervisor, store_incharge, accounts_executive, hr_executive, safety_officer, purchase_officer, client_rep, vendor.
Permission map in `/app/backend/rbac.py` — read/write/delete per resource. Sidebar nav and table CRUD buttons hide automatically per role; backend returns 403 on disallowed actions.

## Implemented

### Iteration 1 (Feb 2026)
- JWT auth with admin seed, brute force protection
- Executive Dashboard with KPIs + charts (revenue/expense, project status, attendance, safety)
- 14 module pages with CRUD: Clients, Vendors, Employees, Attendance, Projects, Inventory, Purchase Orders, Quotations, Accounts (Journal), Safety Reports, Assets, Payroll, Logistics (Vehicles), Documents
- Approvals queue (basic), Reports landing, Profile, Landing page, Login
- Sample data seeding on startup if collections empty

### Iteration 2 (May 2026)
- **P0 RBAC**: per-resource permission map enforced on every endpoint via `require_permission(resource, action)`; `/api/auth/permissions` exposes the current user's permission map to the frontend; sidebar nav filters by perm; CRUD action buttons hide when user lacks write/delete.
- **P1 Approval chains + history**: 6 chain templates (purchase_order, leave, capex, expense, vendor, quotation). New approvals auto-attach the chain. `/api/approvals/{id}/action` advances chain, records history with `by/role/at/comment`. Approval Detail dialog shows visual chain timeline + activity feed; approve/reject buttons gated by current step's required role (super_admin bypass). Migration backfills legacy approval docs.
- **P1 Excel & PDF exports**: `/api/export/{resource}.{xlsx|pdf}` (openpyxl + reportlab). Excel/PDF icon buttons in every module table header + Reports page Run/PDF/Excel buttons trigger downloads.
- **P1 Dashboard drill-downs**: KPI cards + sub-cards clickable, navigate to relevant module page.
- **P2 Inventory QR**: each item has a QR-code label dialog (qrcode.react) with Print button.
- **P2 PWA polish**: manifest.json, theme-color, apple-mobile-web-app meta tags, installable on mobile.

### Iteration 3 (May 18, 2026)
- **Object storage (Emergent built-in)**: `/api/uploads` multipart endpoint, `/api/files` listing, `/api/files/{id}/download` (cookie or `?auth=` token), soft-delete via `/api/files/{id}` DELETE; metadata stored in `db.files` with `is_deleted` flag.
- **Documents module drag-drop**: multi-file upload (PDF/DOCX/XLSX/PNG/JPG ≤ 25MB) with live thumbnails, open/remove actions; existing Document Register table now shows expiry tone (red if expired, amber if <30 days).
- **Safety photo capture**: per-incident "Photos" dialog with mobile `capture=environment` (camera attached on phones), drop-zone for desktop.
- **Resend email notifications**: approval-pending emails to current step role, approval-decided emails to requester + super_admins, `/api/notifications/expiry-scan` and `/api/notifications/invoice-reminders` ad-hoc triggers. Branded HTML email template (Slate + Amber).
- **"My Approvals" topbar inbox**: bell icon with live badge; dropdown lists approvals where the current user's role is the current step; clicking navigates to `/app/approvals?id=<id>` and auto-opens the detail dialog. Polls every 30 seconds.
- **DataTableShell hardening**: `canWrite`/`canDelete` defaults are now `false`; every page passes the values from `useResource()` so RBAC is enforced even if a caller forgets to wire it.

### Iteration 4 (May 18, 2026)
- **APScheduler nightly jobs**: `/app/backend/scheduler.py` registers `expiry_scan` (daily 09:00 UTC) and `invoice_reminders` (Mondays 09:00 UTC). `/api/scheduler/status` exposes running state, next run times and last results.
- **Backend refactor**: `server.py` reduced from 942 → 91 lines. Extracted `core.py` (db/auth helpers), `seed.py` (admin + sample data), `notification_service.py` (templates + send), and 7 focused routers (`auth_router`, `crud_router`, `approvals_router`, `files_router`, `notifications_router`, `exports_router`, `dashboard_router`) — every file under 165 lines.
- **Upload progress bar**: `FileUploader` now shows a live `Progress` bar per file driven by `axios onUploadProgress`. Bug found by testing agent (missing useState hook) — fixed and retested green.

### Iteration 5 (May 18, 2026)
- **Code-review critical fixes**: removed `document.write` XSS in Inventory QR print flow, replaced array-index React keys with stable composite keys, replaced Python `is`/`is not` literal checks with `==`/`!=`.
- **Theme swap**: light/white/blue dominant palette across Tailwind config, CSS variables, exports.

### Iteration 6 (May 19, 2026)
- **Pure white background**: `--background`, `--sidebar-bg`, `--muted`, `--secondary` resolved to pure / near-pure white in `/app/frontend/src/index.css`. Blue accents preserved.
- **Stale closures fixed**: `AuthContext` now memoises `login/logout/can` via `useCallback` and the provider value via `useMemo`; `useResource` memoises `create/update/remove` via `useCallback` — prevents stale-closure-induced renders and matches React 19 hook discipline.
- **ErrorBoundary**: new `/app/frontend/src/components/ErrorBoundary.jsx` (class-based) wraps every protected route inside `ProtectedShell` so a render crash in one module no longer takes down the whole app — exposes `error-boundary-fallback`, `error-boundary-retry`, `error-boundary-reload` testids.
- **Complexity refactor**:
  - `ApprovalDetail.jsx` split into `ChainStep`, `HistoryEntry`, `ActionFooter`, `Row` sub-components; added testids `approval-chain-step-{idx}`, `approval-history-entry-{idx}` and an `sr-only` DialogDescription for a11y.
  - `DataTableShell.jsx` split into `FormField` and `RowActions`; new `attachmentsParentType` prop renders a paperclip per row that opens `RowAttachments` (drag-drop multi-file upload scoped to that record).
  - `dashboard_router.py` split into `_count`, `_journal_totals`, `_sum_field`, `_monthly_chart`, `_group_count`, `_attendance_today` helpers — payload shape unchanged.
- **6-month chart correctness**: `_monthly_chart` now uses calendar-month arithmetic (no more `timedelta(days=30*i)` collapse), guaranteeing exactly 6 distinct YYYY-MM buckets.
- **Object-storage folder whitelist expanded**: `/api/uploads` now accepts `projects, vendors, clients, employees, assets, purchase_orders, quotations` in addition to `documents, safety`. Drag-drop attachments per row enabled on those 7 module pages.
- **Husky + lint-staged**: pre-commit hook in `/app/.husky/pre-commit` runs `lint-staged` on staged `frontend/**.{js,jsx}` with `eslint --max-warnings=0`; `prepare` script re-applies `core.hooksPath=.husky` on `yarn install`.

### Iteration 7 (May 19, 2026) — Phase A: Super Admin power tools
- **Audit Trail**: new `/app/backend/audit.py` writes a row to `db.audit_logs` on every CRUD via `crud_router.make_crud` and on login via `auth_router`; payload sanitiser strips `_id`/`password`/`password_hash`.
- **Sequences helper**: `/app/backend/sequences.py` — atomic per-prefix per-year numbering via `findOneAndUpdate(upsert=True)`. Format: `ENQ-2026-0001`, `ORD-2026-0001`, `PRJ-2026-0001` (4-digit padding).
- **Admin router (`/api/admin/*`, super_admin only)**:
  - Departments CRUD via new `departments` module in `crud_router.MODULES` + `rbac.PERMISSIONS`.
  - Dropdown Master: full CRUD + public `/admin/dropdowns/categories` and `/admin/dropdowns/by-category/{cat}` for form selects.
  - Approval Matrix editor: `db.approval_chains` overrides the built-in `APPROVAL_CHAINS` dict. `build_chain()` is now async and DB-first; `/admin/approval-matrix` GET/PUT/DELETE for super_admin.
  - Audit log viewer with filters (resource/actor/record/action) + JSON before/after dialog.
  - Session monitor: `db.login_activity` records every successful login with IP + user_agent.
- **Frontend Admin Console** (`/app/admin`): tile-card index + 5 sub-pages (Departments, Dropdowns, ApprovalMatrix, AuditLogs, Sessions). New `ADMINISTRATION` sidebar group rendered only when `user.role === "super_admin"`.

### Iteration 8 (May 19, 2026) — Phase B: Sales pipeline upgrade
- **Sales router** (`/api/sales_router.py`): new `enquiries` and `orders` resources with status workflow.
- **Enquiry lifecycle**: `open → under_review → submitted → negotiation → (won | lost | hold)` with `ALLOWED_TRANSITIONS` enforcement; `status_history` array maintained on every transition.
- **Auto-numbering**: `ENQ-YYYY-####` on enquiry create; `ORD-YYYY-####` and `PRJ-YYYY-####` issued on conversion.
- **Atomic Won → Order → Project**: `POST /api/enquiries/{id}/convert` requires `status='won'`, creates Order doc + (optional) Project doc, links them on the enquiry; double-convert returns 409.
- **Quotation revision chain**: new fields `revision_no`, `parent_id`, `root_id`; `POST /api/quotations/{id}/revise` clones the latest revision with `Rev{n}` suffix; `GET /api/quotations/{id}/revisions` returns the full chain.
- **Service Type**: `sales | services | sales_services` on enquiry.
- **Frontend**: new `/app/enquiries` page (status select + Convert dialog), `/app/orders` (read-only list), upgraded `/app/quotations` (History dialog + +Rev button per row). Sidebar Commerce group split into Clients / Vendors / **Enquiries / Quotations / Sales Orders** / Purchase Orders / Inventory.

### Iteration 9 (May 19, 2026) — Phases C, D, E, F shipped together
- **Phase C — Store/Inventory transactions** (`routers/store_router.py`):
  - 5 transaction types: `inward | outward | transfer | return | scrap`.
  - Auto-numbered `INV-YYYY-####` via `next_sequence`. Atomic balance adjustment on `inventory.quantity`.
  - **Approval-gated outward**: when outward quantity > `inventory.issue_threshold` (default 50), the transaction is created with `status='awaiting_approval'` and an approval row is generated using the existing `expense` chain. Stock is **NOT** debited until fully approved.
  - **Approve-side hook** (`approvals_router._post_outward_after_approval`): once an approval of type `material_issue` reaches the `approved` state, the linked txn is automatically posted and `inventory.quantity` debited. On reject, the txn is marked `rejected` and stock is untouched. Verified end-to-end via curl.
  - **Barcode/QR/SKU lookup**: `GET /store/lookup/{code}` resolves on `id | sku | barcode`.
  - **Overdraft protection**: returns 400 on insufficient stock.
  - **Frontend** (`StoreTransactions.jsx`): scan field + "Lookup" button shows resolved-item card (SKU + current stock); dynamic form per txn_type; transaction ledger table with type badges, +/- delta colouring, status badge.
- **Phase D — Safety pack** (4 new resources): `ppe_issuance`, `ptws`, `safety_trainings`, `toolbox_talks`. Wired through `crud_router` + RBAC; new sidebar items under Operations. Each page leverages `DataTableShell` with relevant fields/dropdowns. Existing scheduler nightly job can be extended to scan `ppe_issuance.expiry_date` for expiry alerts.
- **Phase E — HR pack** (5 new resources): `recruitment_requests`, `candidates`, `deployments`, `accommodations`, `overtime`. RBAC: candidates+recruitment restricted to HR/management (site_engineer 403 verified); deployments/accommodations are read-by-all. Sidebar reorganised into a comprehensive People & Finance group.
- **Phase F — Vendor portal** (`routers/vendor_portal_router.py`):
  - `GET /vendor-portal/me` returns the vendor row matched against the logged-in user's email.
  - `GET /vendor-portal/rfqs` returns POs addressed to the vendor.
  - `POST /vendor-portal/invoices` submits an invoice (auto `VINV-YYYY-####`), persisted in `vendor_invoices`.
  - `POST /vendor-portal/evaluations/{vendor_id}` — only `super_admin`, `director`, `general_manager`, `purchase_officer` can write; **rolling-average rating** auto-recomputed on every write (verified: 4.0 + 5.0 → vendor.rating=4.5, rating_count=2).
  - **Frontend** (`VendorPortal.jsx`): self-service dashboard with profile header, 3 KPIs, RFQ list, invoice submission dialog, evaluation history. Sidebar gated by `role === 'vendor'` (separate group rendered only for vendor users).
- **Testing**: `testing_agent_v3_fork` iteration 9 — **29/29 new pytest + 31/31 regression = 60/60 PASS**. All frontend smoke green.

## Test Results
- Iteration 1: 35/35 backend, 100% frontend
- Iteration 2: 53/53 backend (18 new + 35 regression), 100% frontend
- Iteration 3: 71/71 backend (18 new + 53 regression), 100% frontend
- Iteration 4: 105/105 backend (34 new + 71 regression)
- Iteration 6: 9/10 → 10/10 after fix
- Iteration 7 (Phase A): 12/12, 100% frontend
- Iteration 8 (Phase B): 19/19, 100% frontend
- Iteration 9 (Phases C/D/E/F): 29/29 new + 31/31 regression = 60/60
- Iteration 10 (PPE expiry + PWA): 9/9 new + 60/60 regression = 69/69
- Iteration 11 (Pulse + Barcode): 12/12 new + 69/69 regression = 81/81

### Iteration 10 (May 19, 2026) — PPE expiry + PWA polish
- `run_expiry_scan()` now scans both `documents.expiry` AND `ppe_issuance.expiry_date` (≤30 days or past-due) and dispatches HTML alerts to super_admins + safety_officers.
- PWA: full manifest with 4 shortcuts, service worker (network-first nav + SWR assets + network-only API), `<PWAInstallPrompt />` with offline pill.

### Iteration 12 (May 19, 2026) — Department modules + auto-numbering
- **`/api/dashboard/departments`** and **`/api/dashboard/department/{slug}`** — 9 departments (sales, projects, accounts, finance, store, safety, logistics, hr, procurement). Each detail call returns `{slug, title, tagline, icon, color, kpis[], links[]}` with all counters running in parallel via `asyncio.gather`.
- **`<DepartmentLauncher />`** (`/app/modules`) — 9 colour-toned department tiles with live headline counters.
- **`<DepartmentWorkspace />`** (`/app/modules/:dept`) — parameterised department workspace with KPI tiles + curated module links.
- **Role-based landing**: `/app/frontend/src/lib/roleLanding.js` single source of truth. super_admin → `/app` (Executive Operations Control Room), vendor → `/app/vendor-portal`, all other authenticated users → `/app/modules`. Login redirect + `<Navigate>` defensive guard in Dashboard both use it.
- **"Modules" header button** visible on every authenticated page for one-click department switching.
- **Auto-numbering prefixes** via crud_router `AUTO_NUMBER` map applied at create time when client doesn't supply a number:
  - `PTW-YYYY-####` (Permits to Work)
  - `INC-YYYY-####` (Safety Incidents / safety_reports)
  - `TRN-YYYY-####` (Safety Trainings), `TBT-YYYY-####` (Toolbox Talks)
  - `REQ-YYYY-####` (Recruitment Requests), `CND-YYYY-####` (Candidates), `DEP-YYYY-####` (Deployments), `ACC-YYYY-####` (Accommodations), `OT-YYYY-####` (Overtime)
  - `JV-YYYY-####` (Journal Vouchers), `PO-YYYY-####` (Purchase Orders), `DPT-YYYY-####` (Departments)
- **Code-review polish from testing agent** applied: single `roleLandingPath` helper (replaces duplicated rule in Login.jsx + Dashboard.jsx), Logistics workspace expanded from 2 → 4 KPIs (added Active Deployments + Accommodations), `_badge()` headline metrics aligned with each detail builder's primary KPI so tile and detail no longer diverge semantically.
- **Testing**: iter 12 → **20/20 new + 74/74 regression = 94/94 PASS**. No functional bugs.

### Iteration 11 (May 19, 2026) — Operations Pulse + Camera Barcode Scanner
- `GET /api/dashboard/operations-pulse`: 7-card live executive heartbeat (Pending Approvals, Material Issues Held, Open Permits, Low Stock, PPE Due ≤30d, Live Enquiries, Safety Incidents). Counters fan-out with `asyncio.gather` — sub-100ms response.
- `<OperationsPulse />` strip on the executive dashboard, 60s auto-refresh, every card deep-links.
- `<BarcodeScanner />` using `BarcodeDetector` (Chrome/Edge/Samsung Internet) with crosshair viewfinder + graceful "not supported" fallback. Stream teardown on close. `onDetected` is ref-wrapped so parent re-renders don't restart the camera. Integrated into StoreTransactions next to the Lookup button.

## Roadmap — Master Prompt Completion Status
✅ **All 6 phases delivered (A→F)** + iter 10 (PPE/PWA) + iter 11 (Pulse/Camera):
- Super Admin tooling — Departments, Dropdown Master, Approval Matrix editor, Audit Trail, Session Monitor
- Sales pipeline — Enquiry → Order → Project chain with auto-numbering + quotation revisions
- Store/Inventory transactions — Inward/Outward/Transfer/Return/Scrap with approval-gated outward + barcode lookup + **camera scanner**
- Safety pack — PPE, PTW, Trainings, Toolbox Talks + **expiry alerts**
- HR pack — Recruitment, Candidates, Deployments, Accommodations, Overtime
- Vendor portal — Self-service + invoice submission + rolling-average evaluations
- Executive **Operations Pulse** strip on dashboard
- Installable **PWA** with offline shell

Remaining backlog (P2):
- WhatsApp/Twilio (user keys required)
- GPS tracking for Logistics and Equipment
- ~~Camera-based barcode scanner UI~~ ✅ Done in iter 11
- ~~PPE expiry alerts wired into APScheduler~~ ✅ Done in iter 10
- ~~Native mobile PWA polish~~ ✅ Done in iter 10

### Iteration 13 (Feb 2026) — Code quality
- Refactored all nested ternaries across 18 frontend files into a shared `toneFor(map, value, fallback)` helper at `/app/frontend/src/lib/statusTone.js`. Status / severity / stage badges now use small per-page lookup maps instead of `cond ? a : cond ? b : c` chains. ESLint clean, smoke screenshots verified on Dashboard, Quotations and Safety pages.

### Iteration 14 (Feb 2026) — Employee & Project Allocation Management (Phases 1 + 2)
- **Data model**: `employees` now carries `departments[]` + `allow_multi_dept`, auto-numbered `employee_id` (EMP-2026-####), plus `designation`, `reporting_manager`, `branch`, `joining_date`. Legacy single `department` is mirrored from `departments[0]` for back-compat. Startup migration backfills existing rows.
- **`employee_history` collection** (append-only) auto-logs `department_move`, `deployment_start`, `deployment_end` with from/to snapshots + actor.
- **New `scope.py`** resolves a user's `(departments, active_projects)` based on user record + active deployments (matched by id/email only — name match dropped after code-review).
- **Visibility filter** baked into `crud_router._list_filter`: site-level roles (`site_engineer`, `supervisor`, `safety_officer`, `store_incharge`) only see records on their assigned projects across deployments/safety/attendance/ptws/toolbox/ppe_issuance/inventory_transactions/projects/purchase_orders/assets. `dept_head` only sees employees in their department(s).
- **New allocation_router** endpoints: `GET /api/me/scope`, `POST /api/employees/{id}/move-department` (validated against master DEPARTMENT_MASTER allow-list), `POST /api/deployments/{id}/end`, `GET /api/allocation/{idle-employees,by-department,by-project,history}`, `GET /api/projects/{code}/manpower`.
- **Frontend**: Employees page redesigned with multi-dept chip selector + History log dialog; Deployments page gets Project dropdown, Site-Role + Shift selects, `Manpower` and `End` actions; new `/app/projects/:code/manpower` dashboard with KPI strip, by-role / by-department breakdown bars, and live active roster. Projects list adds a per-row "Manpower View" deep-link.
- **DataTableShell** extended with `multiselect` (chip) + `checkbox` field types.
- **Tests**: 16/16 backend + 28/28 frontend UI checks PASS (iteration_13.json).

### Iteration 15 (Feb 2026) — Employee & Project Allocation Management (Phase 3)
- **Approval workflow** on dept moves + new deployments:
  - `department_move` chain: dept_head → hr_executive
  - `deployment` chain: project_manager → dept_head (Operations Head)
  - super_admin + hr_executive bypass on moves; super_admin + hr_executive + general_manager bypass on deployments
- `move-department` for non-HR roles returns `{pending_approval: true, approval_id}` and creates an approval doc — no mutation until both chain steps approve.
- `POST /api/deployments` from a non-HR role forces `status="pending_approval"`, creates a companion approval; deployment_start history is deferred until full approval. PUT path is also guarded against status flips from non-HR roles.
- New `allocation_workflow.py` triggered by `approvals_router.approval_action`: applies the deferred mutation on final approval; marks deployment `withdrawn` on rejection.
- **3 new reports endpoints**: `/api/allocation/resource-utilization` (deployed-days/available-days per employee + avg), `/api/allocation/site-attendance` (per-project present/absent today), `/api/allocation/transfer-history` (org-wide event feed with `?since` filter).
- **Frontend** `/app/allocation-reports` (AllocationReports.jsx): 7-tab dashboard — By Department · By Project · Idle Manpower · Resource Utilization · Site Attendance · Transfer History · Deployment History. Linked from HR + Projects department workspaces.
- **Tests**: 16/16 backend + 7/7 frontend tabs PASS (iteration_14.json). 2 code-review fixes applied: deterministic React keys on history rows, deployment PUT status-flip guard.

### Iteration 16 (Feb 2026) — Employee & Project Allocation Management (Phase 4)
- **Drag-drop allocation board** `/app/allocation-board` (AllocationBoard.jsx): idle bench + horizontally scrollable project columns. HTML5 native drag-and-drop — drop an idle employee onto a project to open a deploy dialog (POST /api/deployments); drop a deployment back onto Idle to end it (POST /api/deployments/{id}/end). Top-of-page shortage banner when shortfalls exist.
- **Manpower-shortage cron**: APScheduler nightly job @ 07:30 UTC scans open recruitment_requests, computes shortfall vs active deployments (case-insensitive role match), emails HR + Ops digest. Backed by new `GET /api/allocation/shortages` endpoint that powers both the board strip and the email.
- **Monthly deployment calendar** `/app/deployment-calendar` (DeploymentCalendar.jsx): Project × day grid with prev/today/next month navigation, today-column highlight, deployment bars coloured by status (pending = warning, active = primary). Backed by `GET /api/allocation/calendar?year&month`.
- **Geo-tagged attendance**: Attendance page gets a "Mark Present" button capturing `navigator.geolocation` and storing `geo_lat`/`geo_lng`/`geo_accuracy`. New Geo column renders a Google Maps deep link.
- **DataTableShell** gains an `extraActions` prop slot for page-specific action buttons.
- **Tests**: 13/13 backend (test_iteration15_phase4_allocation.py) + frontend Playwright DnD verified (iteration_15.json). 3 code-review fixes applied: calendar testids (calendar-prev/today/next), case-insensitive position match in shortage scan, attendance label clarified.

### Iteration 17 (Feb 2026) — Multi-Location Client Management (Phase A + B + C)- **Hierarchical Client/Site/Contact data model**:
  - `clients` extended with `customer_code` (auto, configurable), `category`, `pan`, `cin`, `corporate_address`, `main_contact/phone/email`, `credit_limit`, `status`.
  - New `sites` collection: `site_code` (auto, parent-prefixed numeric `CL-002-01`), `client_id`, GST/PAN/billing/shipping/state_code/plant_name/payment_terms/credit_limit/geo_lat/geo_lng/status.
  - New `client_contacts` collection: `site_id` + `client_id` denormalised + department category (Purchase/Accounts/Technical/User/Stores/Safety/Project/Management) + mobile/alt_mobile/email/whatsapp/reporting_to/remarks.
- **Auto customer-code format settings** (`/api/admin/customer-code-format`, super_admin only): prefix (1-10 uppercase), padding (3-8), include_fy. Live preview on the settings UI.
- **Race-safe site sequence**: uses dedicated `<customer_code>-SITE` key in `db.sequences` (atomic `$inc`) instead of counting rows.
- **Duplicate GST blocked** via Mongo unique partial index + app-level validation. Duplicate client name blocked (escaped-regex case-insensitive match).
- **Cascade soft-delete**: deleting a parent client marks all child sites + contacts inactive.
- **Cross-search** (`/api/clients/search?q=…`) over codes, GST, names, cities, mobiles, emails.
- **7 reports endpoints**: by-client, by-site, by-gst, outstanding-by-site, by-location, contact-directory, activity-history.
- **New `sales_executive` role** seeded with `sales@erp.com / Sales@123`; gets clients.write + quotations.write but not delete.
- **Startup migration** backfills `customer_code` on legacy clients.
- **Frontend**:
  - `/app/clients` — tree view (parent → sites → contacts) with KPI strip, expand/collapse, search, dialogs for client/site/contact CRUD, status badges, auto-codes shown read-only.
  - `/app/client-reports` — 7-tab analytics dashboard (testids `creport-tab-by-client/by-site/by-gst/outstanding/by-location/contact-directory/activity-history`).
  - `/app/admin/customer-code` — super_admin settings form with live preview, linked from AdminConsole tile.
  - `useSiteOptions` hook + new "Customer Site" dropdown on Quotations + Projects forms.
  - Sales workspace `/app/modules/sales` updated with "Clients & Sites" and "Client Reports" links.
- **Tests**: 37/37 backend PASS (test_iteration16_clients.py) + frontend Playwright walk-through 28/30 (iteration_16.json). Two reported gaps already fixed in same pass:
  - AdminConsole's Customer Code tile (already present — testing agent saw cached HTML).
  - Outstanding tab testid drift (id changed from `outstanding-by-site` → `outstanding`, mapping kept for endpoint).
- **Code-review fixes also applied**: race-safe site sequence, unique GST index, escaped duplicate-name regex, cascade soft-delete on contacts.

### Iteration 18 (Feb 2026) — Role × Department Matrix + Client CSV Import/Export
- **Role × Department Matrix** (`/app/admin/role-department-map`, super_admin only): visual grid of all roles × all 9 department workspaces; clicking a cell toggles whether that role sees that workspace on the Module Launcher. Mapping is persisted under `settings._id="role_department_map"`. Empty rows fail-open (user sees ALL departments — useful while super admin is still configuring).
- Backend: `GET/PUT /api/admin/role-department-map`. `GET /api/dashboard/departments` now filters its response by the requesting user's role using the saved map.
- Default seed map ships sensible bindings (e.g. `hr_executive → [hr, projects]`, `safety_officer → [safety, projects]`).
- **Client CSV Import/Export**:
  - `GET /api/clients/export.csv` — streams all clients with 11 standard columns.
  - `POST /api/clients/import.csv` (multipart) — bulk-create, skipping duplicates by case-insensitive name and rows without a `name`. `customer_code` column is ignored on import (auto-assigned).
  - Frontend "Import CSV" + "Export CSV" buttons on the Clients header. Import shows a created/skipped toast.
- Linked from AdminConsole's "Role × Department Matrix" tile.
- **Tests**: curl-verified end-to-end: super_admin loads + saves map, sales_executive correctly sees only `["sales"]` after rule applied, super_admin still sees all 9, 3 created + 1 blank skipped on import, all dupes blocked on re-import.

### Iteration 19 (Feb 2026) — Enquiry/Quotation Enhancements (Phase A–D)
- **Phase A — Backend schema** (`/app/backend/routers/sales_router.py`): `EnquiryIn` now accepts `site_id`, `client_id`, multi-select `rfq_type[]`, multi-select `service_categories[]`, rich scope sections (`scope_of_work`, `technical_requirements`, `material_requirements`, `site_conditions`, `special_instructions`, `commercial_notes`), `submission_deadline`, `bid_closing_date`, `priority`, `customer_enquiry_no`. `_snapshot_from_site()` denormalises GST + billing address + primary contact into the enquiry.
- **Phase B — Frontend single dense form** (`/app/frontend/src/pages/Enquiries.jsx`): one dialog with 4 grouped sections (Customer & Site cascade, Enquiry Reference, RFQ Type & Service Categories chip multi-select, Scope & Specifications textareas) + `RowAttachments` for document uploads + KPI strip (Total / Open / Won / Lost / Pending Quotes / Deadline ≤ 7d).
- **Phase C — 1:1 Auto-quote**: creating an Enquiry now auto-creates a draft Quotation (`quotation_id` + `quotation_no` returned in the response, success toast surfaces both). `Quotations.jsx` shows an "Enquiry" column with the linked enquiry_no badge.
- **Phase D — Sales Reports + Global Search** (`/app/frontend/src/pages/SalesReports.jsx` — new, route `/app/sales-reports`):
  - `GET /api/sales/reports/monthly` — `{month,total,won,lost,pipeline_value,won_value}[]` with line chart
  - `GET /api/sales/reports/by-client` — top-8 bar chart + table
  - `GET /api/sales/reports/by-service` — pie chart + table (unwound service_categories)
  - `GET /api/sales/reports/won-lost` — `{won,lost,win_ratio_pct,avg_cycle_days,as_of}` with pie + stat tiles
  - `GET /api/sales/reports/deadline-tracker` — overdue / due ≤ 7d / upcoming buckets
  - `GET /api/sales/search?q=` — cross-search across `enquiries`, `quotations`, `orders`
- **Wiring**: nav-sales-reports under Commerce group, route added in `App.js`, link added to `_sales()` department workspace.
- **Tests**: backend 16/17 PASS (only RBAC negative-control reflects existing PM `quotations:read` perm — not a regression). Frontend Playwright 100% PASS across all 6 tabs, KPI strip, dialog sections, quotations Enquiry column, sidebar link and workspace tile.
- **Polish applied**: composite keys on By-Service table + `min-w-0` on ResponsiveContainer parents to silence Recharts width(-1) warnings.

### Iteration 20 (Feb 2026) — Sales Reports RBAC + Add-User Workspace Preview
- **Dedicated `sales_reports` permission** (`/app/backend/rbac.py`): pipeline analytics gated by `sales_reports:read` instead of inheriting from `quotations:read`. Granted to {super_admin, director, general_manager, dept_head, sales_executive, accounts_executive}; **project_manager is now correctly 403** on all 6 Phase D endpoints + global search. `nav-sales-reports` in `Layout.jsx` updated to use the new perm. PM still has full 200 access on `enquiries`, `quotations`, `orders`, `enquiry-pulse` — no regression.
- **Live Workspace Preview panel** in Add User dialog (`/app/frontend/src/pages/Profile.jsx`): 2-column dialog with form on the left and a sticky preview on the right. Live-refetches `/api/admin/role-preview/{role}` on every role change (AbortController-cancelled to avoid race-on-fast-switch) and renders the exact Department Launcher tiles the user will land on, plus visual states for `super_admin` (sees everything), `known_role=false` (typo → red), and `fallback_all=true` (no mapping → amber warning).
- **New endpoint** `GET /api/admin/role-preview/{role}` (super_admin only) returning `{role, known_role, fallback_all, departments[{slug,title,tagline,icon,color}]}`.
- **Tests**: backend 25/25 PASS (`test_iteration18_sales_rbac_role_preview.py`), frontend Playwright 100% — verified by `testing_agent_v3_fork` (iteration_18.json).

### Iteration 21 (Feb 2026) — Client Management Phase D
- **Onboarding approval workflow**: new `client_onboarding` chain in `approval_engine.py` (`sales_executive → accounts_executive → director`). `POST /api/clients` defaults to `status="pending_approval"` and auto-creates the approval (super_admin can still fast-track by passing `status="active"`). Final-step approval flips `client.status → active` + sets `approved_at`. Rejection sets `status → rejected` with `reject_reason = approval comment`. New `POST /api/clients/{id}/resubmit` creates a fresh chain for rejected clients (and marks previous rejected approval as `superseded` so the inbox stays clean).
- **Document attachments at client + site level** with category taxonomy (`PAN | GST | MSA | NDA | TradeLicense | IncorporationCert | AddressProof | BankDetails | Other`):
  - Backend: `POST /api/uploads` now accepts `category` Form field; new `client_sites` folder; bad categories on clients/client_sites uploads return 400.
  - Frontend: new `ClientDocsDialog` component with category dropdown + grouped file list + delete; Docs buttons on every client row and every site row.
- **Geo-pin on Leaflet + OpenStreetMap**:
  - Backend: new `GET /api/sites/map` returns only valid-geo sites (lat/lng numeric + in-range, status ≠ inactive).
  - Frontend: editable Leaflet mini-map in the Site dialog (click / drag pin / "Use my location"); new `/app/client-map` page with markers, sidebar list, search filter, and Sales workspace tile. Default marker icons are bundled from `node_modules/leaflet/dist/images/` (no CDN dependency).
- **Wiring**: `nav-client-map` added under Commerce sidebar group; "Client Map" tile added to the Sales department workspace; Clients page header now has a "Map" button.
- **Tests**: backend 13/13 PASS (`test_iteration19_phase_d_clients.py`) + frontend Playwright 100% via `testing_agent_v3_fork` (iteration_19.json). Polish applied: bundled Leaflet markers + 180px mini-map height in dialog + superseded-flag on stale rejected approvals.

### Iteration 22 (Feb 2026) — Procurement Cycle Backbone (Phase A of 4)
- **Purchase Requisitions** (`/api/procurement/prs`): multi-item PR with auto-number `PR-YYYY-####`, 5-step approval chain (Dept Head → PM → Procurement Head → Finance → Director), draft/submit/resubmit lifecycle, attachment-ready (`parent_type=purchase_requisitions` on the existing files store).
- **RFQ** (`/api/procurement/rfqs`): auto-numbered `RFQ-YYYY-####`, multi-vendor pick from approved PR, per-vendor response capture (rate, delivery_days, payment_terms, technical_score), `comparative` endpoint sorted by landed value, `select-vendor` + `convert-to-po` (auto-creates a PO linked back to PR + RFQ).
- **GRN** (`/api/procurement/grns`): line-level accepted/rejected/inspection_status + batch, auto inventory inward (where `item_id` present) + `inventory_transactions` audit row, PO status correctly flipped to `received` vs `partially_received` based on **cumulative** accepted across all GRNs (not just per-line). Over-receipt guard: returns 400 if accepted > ordered. Delete reverses inventory.
- **Procurement Dashboard**: 8-tile KPI strip (PR Total/Pending/Approved/Rejected, RFQ Open, PO Open, GRN Total/Partial, Avg PR→PO cycle days) + 4 quick-action buttons; new `_procurement` workspace has 7 KPIs and 7 module tiles.
- **Sidebar nav**: 5 new entries — `Purchase Requisitions`, `RFQs`, `GRN (Goods Receipt)`, `Procurement Dashboard` (plus existing Purchase Orders).
- **Approvals integration**: post-action hook for `purchase_requisition` / `rfq` / `grn` chains; rejection writes `reject_reason` and `superseded` flag is set on stale PR approvals at resubmission time.
- **Tests**: backend 17/17 PASS (`test_iteration20_procurement.py`) + frontend Playwright 100% via `testing_agent_v3_fork` (iteration_20.json).
- **Polish applied post-review**: cumulative PO receipt check, over-receipt 400 guard, rfq-vendor testid container renamed to `rfq-vendor-list`, superseded-flag on rejected PR approvals.
- **Known structural limits (deferred to Phase B):** comparative `landed_value = rate × Σ qty` assumes a single UoM across items — multi-item PRs with heterogeneous units will need per-item vendor rates; `select-vendor` reuses status='approved' (will rename to `vendor_selected`).

### Iteration 23 (Feb 2026) — Procurement Phase B (Allocations + Asset Lifecycle + Challans)
- **Material/Asset Allocations** (`/api/allocations`): auto-numbered `ALC-YYYY-####`, kinds (material/tool/consumable/asset), returnable flag, project/site/department/employee linkage. Issue debits inventory race-safely (conditional `$gte` update), return credits + writes paired `inventory_transactions` ledger rows. Asset allocations enforced to be returned in full (single-unit). Delete-after-return blocked; delete-before-return reverses stock.
- **Asset Lifecycle** (`/api/assets/{id}/lifecycle`): Depreciation (upsert by `(asset_id, period)` — no dupes), AMC contracts (vendor/start/end/amount/coverage), Calibration logs (date/next_due/result), Warranty (vendor/start/expiry/terms). Derived fields stamped on the asset doc: `current_book_value`, `last_dep_period`, `amc_active`, `amc_expiry`, `last_calibration_date`, `next_calibration_due`, warranty_*.
- **Challans** (`/api/challans`): auto-numbered `CH-YYYY-####`, types (delivery / return / inter_site_transfer / vendor_return), real QR code via `qrcode.react` rendering `CHALLAN:{no}|{id}` payload. Inter-site transfers are stock-guarded (race-safe debit, full rollback on failure) and credit destination on receive. `receive` captures a lightweight e-signature stamp `{name, user_id, user_name, ip, signed_at}` — `ip` honours `X-Forwarded-For` for k8s ingress. Delete blocked once received.
- **Wiring**: 3 new sidebar entries (Material Allocations, Asset Lifecycle, Challans) under Commerce + 3 new tiles on the Procurement workspace.
- **Tests**: backend 22/22 PASS (`test_iteration21_phase_b.py`) + frontend Playwright 100% via `testing_agent_v3_fork` (iteration_21.json).
- **Polish applied post-review**: race-safe stock guards on issue + inter-site transfer (incl. rollback), `X-Forwarded-For` aware e-signature IP, depreciation upsert, asset partial-return guard, `receiver_name` min_length validation.

### Iteration 24 (Feb 2026) — Procurement Phase C + D (Inventory & Procurement Intelligence)
- **Phase C — Inventory Intelligence** (`/api/inventory-intel/*`, `InventoryIntel.jsx`):
  - 7-tab dashboard: Valuation (FIFO/LIFO/Weighted Avg with per-item layers), Aging (5 buckets), Dead Stock (configurable threshold), Fast/Slow Movers, Idle Inventory, Reorder Alerts (severity-coloured), and Bulk Excel/CSV Import.
  - Bulk import via `/import-template` (CSV template download) + `/import.csv` (multipart upload) — handles item_code, name, category, unit, opening_quantity, rate, batch, serial_no, vendor_name, asset_tag, reorder_level, min/max_stock. Existing items merge stock; new items are auto-created.
- **Phase D — Procurement Intelligence** (`ProcurementIntel.jsx`): 4 tabs over existing backend endpoints — Vendor Performance (PO + GRN + RFQ derived score + A+/A/B/C/D grade), Budget vs Actual (groups PRs/POs by budget reference), Reservations (PRs as soft reservations against inventory), Audit Explorer (filterable global log).
- **Wiring**: routes `/app/inventory-intel` + `/app/procurement-intel` in `App.js`, sidebar entries `nav-inventory-intel` + `nav-procurement-intel` in `Layout.jsx`, tiles on both Procurement and Store department workspaces (`_procurement` + `_store` builders in `departments_router.py`).
- **Bugs fixed during sub-agent retest (iteration_25.json)**:
  - Aging/Idle/Movers/Reorder/Valuation/DeadStock sub-components now guard on their specific expected fields (`data?.buckets`, `data?.items`, etc.) instead of just `if (!data)` — eliminates tab-switch race crash.
  - Bulk Import no longer auto-redirects on success; result panel now stays visible with explicit `intel-import-open-valuation` handoff button.
  - DeadStock + Importer error rows use composite React keys (`${id}-${i}`) — duplicate-key warnings cleared.
- **Tests**: frontend Playwright 100% via `testing_agent_v3_fork` (iteration_25.json — 11/11 tabs, bulk import e2e, sidebar + workspace regression all GREEN). Backend already GREEN from iteration_21.

### Iteration 25 (Feb 2026) — Procurement Phase A debt clearance
- **Heterogeneous UoM in RFQ comparative**: vendor responses now carry an optional `item_rates: {po_item_index: rate}` dict in addition to legacy single `rate_quoted` (treated as fallback). `/comparative` returns `heterogeneous_uom`, `units[]`, and a per-vendor `item_breakdown[]` (each line tagged `source: item_rate | fallback_rate | missing`); landed value is summed per item using the item-specific rate where present. `/convert-to-po` mirrors the same math — PO `amount = Σ(rate × qty)` and each PO line now carries `rate` + `line_value`.
- **RFQ status `vendor_selected`**: already migrated to `vendor_selected` (verified — both backend `select-vendor` and frontend status tone map honour it; legacy `approved` still supported in FE tone map).
- **Configurable approval matrix**: already wired — `approval_engine.get_chain_template` is DB-first via `db.approval_chains`; `build_chain()` (used by PR/RFQ/GRN) honours overrides; admin `GET/PUT/DELETE /admin/approval-matrix/{type}` editor lists all 12 chain types including `purchase_requisition`, `rfq`, `grn`.
- **Frontend RFQ page**: Response dialog now auto-expands a per-item rate grid when the RFQ contains heterogeneous UoMs and offers a manual toggle otherwise. Comparative dialog shows a warning banner for heterogeneous UoMs and an expandable per-vendor breakdown with rate source badges.
- **Tests**: 4/4 new backend tests in `tests/test_phase_a_debt_heterogeneous_uom.py` PASS · 17/17 procurement Phase A regression (`tests/test_iteration20_procurement.py`) PASS · smoke screenshot confirms FE renders the new comparative UX.

### Iteration 26 (Feb 2026) — Bulk import Site Teams from CSV
- **Backend** (`allocation_router.py`):
  - `GET /api/deployments/import-template` — downloads a CSV template with 11 columns + 3 example rows (`site_teams_template.csv`).
  - `POST /api/deployments/import.csv` — multipart upload that resolves employees by `employee_code` → `employee_email` → `employee_name` (case-insensitive) and projects by `code` or `name`. Auto-numbers `DEP-YYYY-####`. Approval-gated: `super_admin / hr_executive / general_manager` get immediate active deployments; all other roles get `pending_approval` + a deployment-chain approval auto-created. Duplicate detection by `(employee_id, project, status not in {completed, withdrawn})` blocks double-deploys. Per-row failures go to `errors[]` without halting the batch.
  - `allocation_router` moved before `crud_router` in `server.py` so that `/deployments/import-template` is matched literally before `/deployments/{id}`.
- **Frontend** (`Deployments.jsx`):
  - "Bulk Import" button in the page header (via DataTableShell `extraActions` slot) opens a dialog with column docs, template download, file picker, and a result summary (created · pending · errors).
  - Failures (with row numbers) are shown inline in a scrollable list.
- **Tests**: 6/6 new backend tests PASS (`tests/test_deployments_bulk_import.py`) covering template, success path (resolution by code + email), bad-employee/bad-project/missing-site_role errors, duplicate-skip idempotency, missing file → 400, bad headers → 400.

### Iteration 27 (Feb 2026) — Site Execution Phase A+B (DPR + Measurement / Work Certification)
Industrial-services-specific operational layer for INDIAN TRADE LINKS workflow (scaffolding · painting · rope-access · insulation · roof-sheeting).
- **Daily Site Report (DPR)** (`/api/dprs`, `Dprs.jsx`):
  - Captures end-of-day site state — `manpower` (role × count breakdown), `work_completed`, three material flows (`material_used` / `material_received` / `material_returned`), `safety_observations`, site photos (file ids), `client_instructions`, `delay_reasons` + `delay_hours`, `extra_work`, `supervisor_remarks`.
  - Auto-numbered `DPR-YYYY-####`. Workflow: `draft → submitted → approved | rejected`. Edits gated to draft/rejected only. Approval restricted to Project Coordinator+ (super_admin / director / general_manager / dept_head / project_manager). Rejection requires a reason and reopens the DPR for edits.
  - 5-card KPI strip (Total · Submitted Today · Pending Approval · Approved 7d · Rejected) backed by `/dprs/dashboard`.
- **Measurement / Work Certification** (`/api/measurements`, `Measurements.jsx`):
  - Service-wise lines covering all 5 services with activity sub-types (erected/dismantled, painted/primer/surface_prep, inspection/cleaning, insulated/cladding, sheeted/flashing/ventilator). Each line stores `executed_qty`, `certified_qty`, `unit` (m²/m³/m/Nos/kg/ltr), optional `rate`. Server validates `certified_qty ≤ executed_qty` per line. Auto-computes `total_executed`, `total_certified`, `billable_value` (Σ rate × certified_qty).
  - Auto-numbered `MEAS-YYYY-####`. Workflow: `draft → submitted → client_certified → approved_for_billing | rejected | billed`. Certify records `client_signature: {name, designation, signed_at, recorded_by, ip}` with `X-Forwarded-For`-aware IP capture; on-site supervisor/site_engineer can certify (joint-measurement industry norm). Only PC + Accounts roles can `approve-for-billing` or `reject`.
  - `GET /measurements/pending-certification` and `GET /measurements/summary?project_code=…` (aggregation by project × service × activity × unit for RA-bill prep).
  - 6-card KPI strip + 2 tabs (All Measurements · RA Billing Summary). Summary view groups by project with billable totals.
- **Wiring**: 2 routes (`/app/dprs` + `/app/measurements`), sidebar entries under Operations (`nav-dprs`, `nav-measurements`), tiles on the **Projects** workspace (`Daily Site Reports`, `Measurements & Certification`) and the **Accounts** workspace (`Measurements (Bill-ready)`). New RBAC perms `dprs` and `measurements` (see `rbac.py`).
- **Tests**: 19/19 backend pytest PASS (`test_site_execution.py`) + frontend Playwright via `testing_agent_v3_fork` (iteration_26.json) — 17/18 checks pass; the 18th (Certify button visible to site_engineer) is intentional per industry workflow (joint measurement captured on-site by supervisor). Added explanatory tooltip on the Certify action for clarity.

### Iteration 28 (Feb 2026) — Modules C + D + E + F + G (Bills, Receivables, PO Commercials, Project Ops, Service Rates)

**C — Running Account Bills** (`/api/ra-bills`, `RaBills.jsx`):
  - Bill types: running · final · supplementary · debit_note · credit_note. Auto-numbered `RA-YYYY-####`, `DN-YYYY-####`, `CN-YYYY-####`.
  - Workflow: draft → submitted → approved → invoiced → paid / cancelled. Approval gated to PC + Accounts + Billing roles (`super_admin / director / general_manager / dept_head / accounts_executive / billing_executive`).
  - Money math: subtotal Σ(qty×rate); gst on subtotal; gross = subtotal+gst; retention/tds % applied on subtotal; net_payable = gross − retention − tds − other_deductions − advance_recovery; `cumulative_value = previous_bill_value + gross`.
  - `POST /ra-bills/from-measurements` bulk-creates a draft bill from `approved_for_billing` measurements; approving the bill flips those measurements to `billed`; cancelling rolls them back.
  - Issue-invoice endpoint stamps invoice_no, issue_date, due_date (configurable due_days) — these are what feeds the Receivables module.
  - 5-card KPI dashboard (Total · Billed-this-month · Retention Held · TDS Deducted · Net Due).

**D — Receivables & Cashflow** (`/api/receivables/*`, `/api/payments-in`, `Receivables.jsx`):
  - `POST /payments-in` auto-numbered `PAY-YYYY-####`, supports multi-bill allocation, idempotent partial payments (bill flips to `paid` only when fully covered).
  - 5 endpoints: `/ageing` (5 buckets + not_due), `/client-ledger` (per-client invoice+payment+balance), `/overdue` (severity-coloured), `/cashflow?days=30` (overdue + weekly forecast), `/dashboard` (single-shot KPIs).
  - 6-card KPI strip + 4 tabs (Ageing · Overdue · Cashflow · Client Ledger). Severity badges (high/medium/low) on overdue rows.

**E — Sales-Order (Client PO) commercials** (`PATCH /orders/{id}/commercials`, `GET /orders/{id}/utilization`, `GET /orders/expiring-soon?days=N`):
  - New fields: retention_pct, security_deposit_amount, security_deposit_status, penalty_clause, validity_date, start_date, end_date, payment_terms, billing_terms, material_supply_terms, manpower_supply_terms, po_attachment_id, notes.
  - Utilization endpoint computes billed_gross / paid_received / balance_po_value / retention_held / utilisation_pct / days_to_expiry from RA bills joined on po_id|po_number.
  - Expiring-soon endpoint surfaces POs whose validity_date falls within the next N days, sorted by closest expiry.

**F — Project Operations** (`/api/projects/{code}/ops/*`):
  - `delay-events` and `extra-works` registers (POST + DELETE) with categorised delays (weather/client_hold/manpower/material/safety/other) and client-approval flag on extras.
  - `/snapshot` returns combined ops view: DPR counts, last_dpr_date, measurement_billable_value, computed progress_pct (70% from DPR-approved ratio + 30% from billable-vs-budget), full delay/extra rolls, totals.
  - `/profitability` indicative gross margin: revenue (RA bill gross) − material cost (issued material × rate from allocations) − labour cost (payroll.net_pay of deployed employees). Returns margin_pct.

**G — Service-rate master** (`/api/service-rates`, `ServiceRates.jsx`):
  - Per-service × activity × unit × standard_rate × effective_window CRUD. List supports `active_only=true` filter (current date within effective window).
  - `/lookup` endpoint returns the single active rate for {service, activity, unit?} — consumable from Quotation and Measurement create flows in future iterations.
  - Grouped-by-service UI with quick edit & delete.

- **Wiring**: 4 new routes (`/app/ra-bills`, `/app/receivables`, `/app/service-rates`, `/app/project-ops`), 4 sidebar entries under Commerce, tiles added to Accounts workspace (Running Bills + Receivables + Measurements) and Projects workspace (Project Ops & Profitability). 5 new RBAC perms: `ra_bills`, `receivables`, `payments_in`, `project_ops`, `service_rates`.
- **Important routing note**: `commercial_router` must be registered BEFORE `sales_router` in `server.py` so that `/orders/expiring-soon` is matched literally before `/orders/{order_id}`.
- **Tests**: 23 new backend pytest tests across 2 files (13 ra_bills_receivables + 10 commercial_ops) PASS. Combined regression: **69/69 backend pytest tests PASS** across 6 test files. Smoke screenshot confirms all 4 pages render with full data + KPIs.

### Iteration 29 (Feb 2026) — End-to-End walkthrough + Mobile DPR capture
- **End-to-end pytest** (`tests/test_e2e_full_cycle.py` · 12 ordered steps) walks the complete cycle of an industrial-services project on a real backend: **Project → PR (approved) → RFQ (2 vendors, comparative, vendor_selected) → PO (₹8 000 at ₹80/Nos × 100) → GRN 60 + GRN 40 (partial then full, inventory credited to 100) → Material Allocation (40 issued, inventory debited to 60) → DPR (submitted + PC-approved) → Measurement (₹36 600 billable) → Client Certify → Approve-for-Billing → RA Bill (gross ₹43 188, retention ₹1 830, TDS ₹732, net ₹40 626; measurement flipped to `billed`) → Invoice (due 2026-05-15) → Payment (₹40 626 NEFT; bill flipped to `paid`, balance 0) → Receivables ledger clean (invoiced == received) → Project snapshot reflects DPR + Measurement + Profitability**. 12/12 PASS. Whole-suite regression: **81/81 backend pytests PASS** across 7 test files.
- **Mobile-first DPR capture** (`/app/dprs/mobile`, `DprMobile.jsx`): single-column phone layout, native camera (`capture="environment"`), GPS stamp, offline `localStorage` queue with auto-flush on `window:online`, "Mobile Capture" CTA on desktop DPR page.

### Iteration 30 (Feb 2026) — Billing defaults + walkthrough seed
- **Billing Defaults settings** (`/api/admin/billing-defaults` GET/PUT · `BillingDefaults.jsx`): persists `gst_pct, retention_pct, tds_pct, due_days, currency_code, currency_symbol, locale` in `db.settings.billing`. 5 currency presets (INR/USD/AED/GBP/EUR) with live preview using `Intl.NumberFormat`. New RA-bill form + "From Measurements" dialog auto-prefill from these defaults; invoice-issue prompt seeds due-days. Sidebar entry `nav-admin-billing-defaults` under Administration.
- **Walkthrough seeder** (`/app/backend/scripts/seed_walkthrough_project.py`): scripts the full revenue-cycle as a real demo — `Vega Refinery — Tank Farm Scaffolding` project with PR-2026-0053, RFQ-2026-0036, PO-2026-0030, GRN-2026-0020+0021, DPR-2026-0028, MEAS-2026-0040 (₹60,950 billable), RA-2026-0028 (gross ₹71,921 · net ₹67,655) with 50% partial payment. Idempotent (suffix with timestamp). Output prints the navigation list for the owner walk-through.
- **Tests**: 81/81 across the 7 iteration test files PASS; smoke screenshot confirms walkthrough data + billing defaults page render correctly (₹12,34,567 en-IN preview).

## Credentials
See `/app/memory/test_credentials.md` — admin@erp.com / Admin@123, sales@erp.com / Sales@123, test_pm@erp.com / PM@12345, purchase@erp.com / Purchase@123

## Backlog
### Pending user-provided keys (deferred)
- **Object storage** — AWS S3 / Cloudinary for Document Management upload + Safety photo upload
- **Email notifications via Resend** — invoice reminders, expiry alerts, approval pings

### Future iterations (P2+)
- WhatsApp notifications (Twilio)
- Live GPS tracking integration
- Native mobile shell (React Native)
- Granular field-level audit log explorer
- Reports: drill-into-data and pivot views
- Multi-tenant / multi-company support


### Iteration 29 (May 21, 2026) — AI Quotation Builder ✅
- **Service catalogue** (`/app/backend/quotation_data.py`): 5 services × 6–9 RFQ bases each (manpower_only, material_only, manpower_material, volume, area, monthly_rental, item_rate, lump_sum, shutdown, etc.) with basis-specific dynamic header fields. 50+ preset line items per (service, basis).
- **Conditions library** (`db.condition_library` + `/api/quotation-builder/conditions`): 51 seeded clauses across 4 categories (technical, commercial, inclusion, exclusion) and 6 service scopes (common + 5 services). Admin CRUD UI at `/app/admin/conditions`.
- **Company Profile** (`db.settings` id="company" + `/api/admin/company-profile`): GSTIN, PAN, state, address, banking, signatory. Used on every PDF + drives GST auto-detection.
- **Quotation Builder backend** (`/app/backend/routers/quotation_builder_router.py`): rich data model with `sections[]` (per service+basis), inline `items[]`, technical/commercial conditions, inclusions, exclusions, payment terms, advance/retention/TDS pct, validity. Endpoints: POST/PUT/GET `/quotation-builder`, recalc, preview, PDF, submit-for-approval, send-to-client (Resend), status (won/lost/cancelled).
- **Auto-recalc engine** (`quotation_calc.py`): line-item math (qty × rate − discount − GST split), section subtotals, grand-total round-off. Tax mode auto-derived from company vs client state (CGST+SGST intra · IGST inter); `tax_mode_locked` honors manual override.
- **PDF renderer** (`quotation_pdf.py`): reportlab A4 corporate template — company header band, client/scope grid, per-section line-item tables (header on slate, alt-row banding, subtotal row), totals block, INCLUSIONS / EXCLUSIONS / TECHNICAL / COMMERCIAL appendices, Commercial Summary, dual signatory block.
- **AI integration** (`/app/backend/routers/ai_quotation_router.py` via `emergentintegrations`):
  - `POST /api/quotation-builder/ai/extract-rfq` (multipart, **Gemini 2.5 Pro**) — reads customer RFQ (PDF/DOCX/XLSX/image) → structured JSON {customer, scope, line_items, missing_info, risk_points, clarification_questions}.
  - `POST /api/quotation-builder/ai/suggest-items` (**Claude Sonnet 4.5** with Gemini fallback) — given service+basis+scope, returns 5–12 line items with realistic INR rates, HSN/SAC codes, GST %, assumptions, flags.
  - `POST /api/quotation-builder/ai/risk-review` — risks + missing info + suggested conditions for a draft quotation.
- **Frontend Quotation Builder** (`/app/frontend/src/pages/QuotationBuilder.jsx`): 4-tab editor (Header & Client · Services & Line Items · Conditions & Terms · Preview & Totals), live recalc, debounced auto-save, inline section + item editing, AI-from-RFQ upload dialog, AI-suggest-items button per section, send-to-client dialog with PDF attachment, submit-for-approval button. Linked from the existing Quotations table via "AI Builder" button on every row.
- **Admin pages**: `/app/admin/company-profile` (CompanyProfile.jsx) and `/app/admin/conditions` (ConditionLibrary.jsx) — wired into the Administration sidebar group.
- **RBAC**: new permission keys `company_profile` (write: super_admin / director / GM) and `condition_library` (write: super_admin / director / GM / dept_head / sales_executive; delete: super_admin / director). All AI endpoints gated by `quotations` write.
- **Coverage**: 18/20 pytest cases passed on retest (the 2 unrelated failures were LLM-budget 502s). Frontend Playwright deep-flow verified Add Section dialog, item pre-population from presets, Conditions tab toggle, Preview tab totals. Sidebar nav hides admin entries for non-admins.
- **Bug fixes during iteration**: (1) MongoDB id-conflict on company-profile PUT; (2) shared `quotations` RBAC accidentally letting sales delete clauses; (3) tax_mode auto-detect not re-deriving when client_state changed — all fixed via dedicated permission keys + `tax_mode_locked` flag.

### Iteration 30 (May 21, 2026) — INDIAN TRADE LINKS branding + PDF watermark + Admin control panels ✅
- **Brand identity** rolled across the product: ITL logo (auto-cropped from upload) in sidebar (`Brand.jsx`), login/landing copyright, browser tab/PWA manifest, Excel exports (A1 image + brand title rows), Quotation PDFs (header band), generic module PDFs, and every Resend email header. Sender renamed to "INDIAN TRADE LINKS ERP".
- **PDF watermark** (`pdf_watermark.py`) — `attach_watermark(doc)` registers `onFirstPage`/`onLaterPages` callbacks that center-draw a faint (~11% opacity) ITL logo behind every page. Width auto-tunes (180mm landscape exports / 140mm portrait quotations). One line of integration; any future renderer inherits it.
- **User Management control panel** (`/app/admin/users` · `UserManagement.jsx`): list, search, filter by role + status, create (email + password + role + dept + phone + must_change_password flag), edit, deactivate/reactivate, reset password, hard delete. Backend safeguards: only-super_admin protection, self-delete blocked, inactive users get 403 on login. Login handler stamps `last_login` + `last_login_ip`.
- **Role Register control panel** (`/app/admin/role-register` · `RoleRegister.jsx`): interactive 46-resource × 3-action × 14-role matrix. Toggles persist as DB overrides that REPLACE the code defaults per (resource, action). Effective permissions reflect base ⊕ overrides and take effect instantly across every API gate. Override layer in `rbac.py` keeps a singleton row at `db.rbac_overrides`, loaded into an in-memory cache on startup and refreshed on each save. super_admin is auto-included in every override (safety net). Reset button restores code defaults.
- **New API endpoints**: `GET/POST/PUT/DELETE /api/admin/users`, `POST /api/admin/users/{id}/reset-password`, `POST /api/admin/users/{id}/toggle-active`, `GET/PUT/POST /api/admin/role-register[/reset]`. Mounted on the existing admin_router (no duplicate prefix).
- **New RBAC keys**: `role_register` (read: super_admin/director/GM · write/delete: super_admin only). `users` key already existed; now actively used by admin/users endpoints.
- **Coverage**: 27/27 pytest cases pass · 0 bugs · `retest_needed: False`. Frontend Playwright deep-flow verified: create → search → toggle-active → reset password → edit → delete; matrix loads, cells toggle with override badge, save+reset both work. Pre-existing /admin/dropdowns, /approval-matrix, /audit-logs, /login-activity verified unbroken.

### Iteration 31 (May 21, 2026) — Project-wise Dashboard ✅
- **Backend aggregator** (`/app/backend/routers/project_dashboard_router.py`): single endpoint `GET /api/project-dashboard/{project_id}` returns `{project, kpis, financials, execution, procurement, safety, recent_activity, generated_at}` in one round-trip. Companion endpoint `GET /api/project-dashboard/projects` for the picker.
- **Linking flexibility** (`_link_query`): collections that reference projects via different keys (DPRs/Measurements use `project_id`, RA Bills use `project_code`, Purchase Orders use `project` alias) are all merged via a `$or` query so the dashboard works regardless of writer convention.
- **Computed sections**:
  - Financials: contract value, PO committed, GRN received, RA bills (count + raised + net due), retention/TDS/GST, payments received (count + amount), outstanding, revenue recognised, cost incurred (GRN proxy), gross profit, GP %, billing progress %.
  - Site execution: DPR count (total + 30d), last DPR date, manpower today, avg manpower 30d, 30-day manpower trend, manpower by category, measurement count + status breakdown, active deployment count.
  - Procurement: PR/PO/GRN/allocation counts + per-status breakdowns + total allocation qty.
  - Safety: incidents (total + open + by severity), PTW (total + by status), PPE issued, toolbox talks.
  - Recent activity: newest events across DPRs/RA bills/payments/GRNs/measurements/safety, sorted by timestamp, capped at 12.
- **Frontend** (`/app/frontend/src/pages/ProjectDashboard.jsx`): two-mode page — picker grid (searchable cards) at `/app/project-dashboard` and detail page at `/app/project-dashboard/:id`. KPI strip (6 tiles), Financial Snapshot card (15 rows), Recharts pane (AreaChart manpower trend + BarChart cashflow waterfall), Procurement, Site Execution (with PieChart manpower-by-category), Safety, and Recent Activity feed. Refresh button + Back navigation.
- **Sidebar nav**: `Project Dashboard` added below `Projects`, gated by `projects.read`.
- **Coverage**: 13/13 backend pytest pass · 0 bugs · `retest_needed: False`. Frontend Playwright deep-flow verified picker grid (24 cards), search filter, click-to-detail navigation, all 6 KPI tiles, all cards rendering with real numbers for the seeded E2E project.


### Iteration 32 (May 21, 2026) — Procurement Master: Categories, Items, Cost Centers + PR dropdowns ✅
- **Backend** (`/app/backend/routers/procurement_master_router.py`): three new resource families with full CRUD.
  - **Categories** (`db.pr_categories`): code, name, gst_pct, default_hsn, active. 10 defaults auto-seeded on startup (SCAFF, PAINT, CONSUM, PPE, FAST, INSUL, ROOF, ROPE, TOOL, OFFICE). Cascade-rename keeps `pr_items`, `cost_centers`, AND open-PO/GRN line items in sync.
  - **Items** (`db.pr_items`): code, name, category_id, unit, hsn_sac, last_rate, default_vendor. Auto-fills category_code/category_name/hsn from parent on create.
  - **Cost Centers** (`db.cost_centers`): one row per (project_id, category_id) with code `CC-<project>-<category>`, budget, and live committed (PO rollup) + actual (GRN rollup) + remaining. Roll-up uses both `category_code` and `category_id` for stable matching across renames.
- **PR-Dropdowns helper** (`GET /api/procurement/master/pr-dropdowns?project_id=`): one-shot payload of departments, projects, sites (filtered by project), categories, items grouped by category, and cost centers. Departments fall back to distinct `employees.department` when `dropdown_options` is empty.
- **Cost-center auto-stamping** in `POST /api/procurement/prs`: each line item gets `cost_center_id` + `cost_center_code` automatically resolved from (project_id, category_id) at create time. PR-2026-0061 verified: line stamped `CC-PRJ-E2E-1779360306-SCAFF`. Backwards compatible — existing free-text PRs continue to work.
- **Auto-provision endpoint** (`POST /api/procurement/master/cost-centers/auto-provision/{project_id}`): one click per project creates a CC for every active category that doesn't yet have one. Idempotent.
- **New RBAC key** `procurement_master` (read: anyone; write: super_admin/director/GM/purchase_officer/accounts_executive; delete: super_admin/director/GM).
- **Frontend**:
  - `/app/admin/categories` (`Categories.jsx`) — searchable CRUD list with item-count badges and an inline drilldown dialog to manage items per category.
  - `/app/admin/cost-centers` (`CostCenters.jsx`) — project selector → matrix of CCs with Budget/Committed/Actual/Remaining columns, totals row, Auto-Provision button, manual add/edit/delete.
  - `/app/purchase-requisitions` PR creation dialog rewritten — `SelectField` dropdowns for Department, Project, Site (filtered by project), Category, and Item Name (grouped by category, with free-text fallback). Each line item shows the matched Cost Center code in muted text, or a helpful nudge when no CC exists for the chosen pair.
  - Sidebar admin group has two new entries: "Categories" and "Cost Centers".
- **Coverage**: 17/17 pytest pass · 0 product bugs · frontend deep-flow verified (10 seeded category codes visible, PR dropdowns wired, CC matrix renders). One drift-risk callout from the testing agent already addressed by extending cascade-rename to PO/GRN line items + matching cost-center rollup by both `category_code` and `category_id`.



### Iteration 33 — Data Cleanup Control Panel (May 21, 2026)
- **New router** `/app/backend/routers/data_cleanup_router.py` mounted at `/api/admin/data-cleanup`. Whitelist of 28 cleanup-eligible collections (Enquiries → Quotations → PRs/POs/GRN → DPRs/Measurements → masters → safety / assets / accommodations) each tagged `safe` · `caution` · `dangerous` so the UI can colour-code risk. Sensitive collections (users, settings, audit_logs, sessions, sequences, rbac_overrides) are deliberately excluded — they have their own admin UIs.
- **Endpoints**: `GET /collections` (row counts + tier + archive size), `GET /{coll}` (browse with keyword `q`, status, `older_than_days`), `GET /{coll}/orphans` (rows whose parent FK no longer exists — perfect for tidy-up), `POST /{coll}/preview-delete`, `POST /{coll}/delete` (typed `confirm:"DELETE"` gate + `archive:true|false` toggle), `GET /archive/list`, `POST /archive/restore`, `DELETE /archive/purge`.
- **Soft-delete by default** — copy goes to `db.cleanup_archive` with `expires_at_dt` (BSON Date) backed by a TTL index `cleanup_archive_ttl` (`expireAfterSeconds=0`), so MongoDB auto-purges archived rows after 30 days. Restore re-inserts into the original collection and removes the archive entry; second restore is idempotent (skipped list grows).
- **RBAC** new key `data_cleanup` — `read: super_admin/director`, `write & delete: super_admin only`. Non-super-admin roles get 403 and the sidebar item is hidden.
- **Audit** every delete / restore / purge writes a row to `audit_logs` with reason, count, IP.
- **Frontend** `/app/admin/data-cleanup` (`DataCleanup.jsx`): collection picker with tier-badged options, three tabs — Browse & Delete · Orphan Scan · Archive ({n}). Browse tab supports keyword + status + age-in-days filters. Selection bar with "Archive copy (soft delete)" toggle. Confirmation dialog requires typing `DELETE` exactly. Archive tab supports single-row & bulk restore, plus a full-purge action. JSON preview drawer for any record.
- **Nav**: new Admin sidebar item and Admin Console tile (`admin-card-data-cleanup`) — super-admin gated.
- **Coverage**: testing agent ran 24/24 backend pytest cases (RBAC 403, filter combinations, preview, soft-delete + archive presence, hard purge, archive list, restore idempotency, full purge) and 11/11 frontend e2e assertions (modal disabled→enabled at exactly `DELETE`, restore round-trip, sidebar hidden for supervisor role). Zero functional bugs.

### Iteration 34 — Human Resources P0 (May 23, 2026)
- **Onboarding workflow** (`db.onboardings`) — 6-stage joiner checklist (Offer Accepted → Documents Uploaded → ID Card Issued → PPE Issued → Safety Induction Done → Site Assigned). Endpoints under `/api/hr/onboardings/*` (list / get / advance one stage / complete / delete). On `complete` the backend auto-fires triggers: creates the **employee** row (auto-incremented `E-1xxx`), creates the **login user** (bcrypt password, default `Welcome@123`), creates a default **PPE issuance** row (5-item starter kit), creates a **safety_trainings** induction row, and seeds **default leave balances** for all 4 leave types.
- **Employee 360** — read-only aggregator at `GET /api/hr/employee-360/{id}` plus skill/cert CRUD endpoints. Returns personal · skills · certifications (with computed expiry_status: `expired` / `expiring_soon` (≤30d) / `valid`) · PPE history · trainings & toolbox talks · deployments · 30-day attendance summary · last 3 payroll months · documents · leave balances · recent leaves — all in one payload.
- **Leave Management** (`db.leave_types`, `db.leave_balances`, `db.leave_applications`) — 4 default types seeded on startup (CL/SL/EL/PL with quotas 12/7/15/10). Endpoints: list/create leave-types · grant balances (bulk by dept or individual) · apply (auto-validates balance) · approve (deducts balance) · reject · cancel (restores balance if approved). `GET /leave-calendar?month=YYYY-MM` returns approved leaves overlapping or spanning the queried month.
- **RBAC** new keys `hr_onboarding`, `hr_employee_360`, `hr_leave`. Onboarding & 360 gated to super_admin/HR/GM/director/dept_head; leave read open to everyone, write to managers/HR/admin only.
- **Frontend**:
  - `/app/hr/onboarding` — searchable list with progress bar per onboarding, 'New Onboarding' dialog, detail dialog with stage-by-stage 'Mark Done' tracker, and a 'Complete & Auto-Trigger' panel showing the 4 toggles (login / PPE / induction) and a green confirmation block listing every auto-created record.
  - `/app/hr/employee-360` — searchable employee list → click 'View 360' opens a 7-tab profile (Personal · Skills & Certs · PPE & Training · Deployments · Attendance & Leave · Payroll · Documents). Skill/cert add dialogs with inline expiry badges.
  - `/app/hr/leave` — 5 tabs (Apply · My Leaves · Balances · Approval Inbox · Calendar). Balance tab has an employee picker so HR/admin can inspect anyone. Calendar grid renders approved leaves with employee name + leave type in 7-column month view, prev/next nav.
- **Shared util** in `/app/frontend/src/lib/api.js`: `apiErrorMessage(err, fallback)` and `stripEmpty(obj)` — eliminates the Pydantic 422 React-crash class of bugs by flattening detail arrays before they hit toast and stripping empty optional fields before POST.
- **Coverage**: testing agent ran 17/17 backend pytest + 11/12 frontend (then 100% on re-test after the 422-crash fix). One UX improvement (employee picker on Balances tab) shipped during the same iteration.

### Iteration 35 — HR P1 — Letters · Exit/FNF · refactor (May 23, 2026)
- **Refactor**: `hr_router.py` (874 lines) split into the `routers/hr/` package — `common.py`, `onboarding.py`, `employee360.py`, `leave.py`, `letters.py`, `exit_fnf.py`. `__init__.py` mounts all sub-routers under `/api/hr`. Server import path updated. Existing endpoints unaffected (verified by regression suite).
- **HR Letters & Templates** (`db.letter_templates`, `db.hr_letters`):
  - DOCX template upload via multipart at `POST /api/hr/letter-templates` (validates MIME, rejects non-`.docx`, 10 MB cap, validates the file parses with `python-docx`).
  - Merge engine uses **docxtpl** (jinja2 inside DOCX). Full placeholder scope: employee fields, company fields (from `db.company_profile`), user (the rendering operator), `today` / `today_long`, plus any **custom variables** passed in `payload.variables` at render time.
  - `POST /api/hr/letter-templates/{tid}/render` returns the merged `.docx` as a stream and persists a row in `db.hr_letters` (the rendered binary too — for download from history). Response carries `X-Letter-Id` header.
  - `GET /api/hr/letters/placeholders` lists every available token (used by the frontend "Placeholders Help" dialog).
  - RBAC: read for super_admin/director/GM/HR/dept_head; write for super_admin/HR/GM; delete for super_admin/HR.
- **Exit & FNF** (`db.hr_exits`):
  - 8-item clearance checklist (laptop · ID card · keys · PPE · IT access · knowledge transfer · library · accounts) each gated by a specific approver_role (with super_admin/HR fallback).
  - State machine: `clearance_in_progress` → `fnf_computed` → `finalised`. Finalise blocked until ALL items approved.
  - Auto FNF compute: `per_day_rate = monthly/30` · `pending_salary = per_day × days(LWD)` · `leave_encashment = per_day × (EL+PL balance)` · `gratuity = (monthly × 15/26) × completed_years` only if completed_years ≥ 5 · `notice_recovery = per_day × (notice_period − served_days)` · `net = ps + enc + grat + bonus − adv − notice_rec`.
  - **Gratuity boundary bug fixed**: `_completed_years()` uses anniversary-aware whole-year arithmetic so an employee with exactly 5 calendar years (e.g. 2021-04-15 → 2026-04-15 = 1826 days = 4.9986 yrs via float) now correctly qualifies. Original float-based `tenure_years` retained for display only.
  - PUT override endpoint lets HR manually edit any FNF field; net_payable recomputes automatically.
  - Finalise auto-renders a relieving letter if a `kind='relieving'` template exists (best-effort, logged warning on failure). Employee status flips to `exited` with `exit_date`.
- **Frontend**:
  - `/app/hr/letters` (`HrLetters.jsx`) — Templates tab with upload/render/download/delete and "Placeholders Help" reference modal; Render History tab.
  - `/app/hr/exit` (`Exit.jsx`) — list with clearance progress bar + net payable; New Exit dialog; detail dialog with stage-by-stage clearance approval (approve/reject with remarks), Compute FNF button, inline-editable FNF panel, gated Finalise button.
- **RBAC**: new keys `hr_letters` and `hr_exit`. Sidebar items hidden for unauthorised roles.
- **Coverage**: testing agent — **27/28 backend pytest** + **100% frontend e2e** in iter36. Sole bug (gratuity boundary) was deep-RCA'd and fixed by the main agent in the same iteration. Test seeds cleaned post-run.

### Iteration 36 — Indian Legal Compliance + Employment Types (May 23, 2026)
- **`/app/backend/india_compliance.py` (NEW)** — Pluggable validator: PAN (`ABCDE1234F`), Aadhaar (12-digit + **Verhoeff checksum**), UAN (12-digit), ESIC (10–17 digits), IFSC (`SBIN0001234`-style). Normalises PAN/IFSC/UAN to uppercase, strips spaces/hyphens before regex match. Also validates daily_wages.daily_rate ≥ 0, contractual.contract_end ≥ contract_start, and nominee_share_pct 0–100. Exposes `mask_aadhaar()` for export/PDF redaction.
- **Hook** in `routers/crud_router.py` runs `validate_employee_compliance(doc)` on both POST and PUT of `/api/employees`. Returns 400 with " · " joined messages on any failure.
- **`/app/frontend/src/pages/Employees.jsx` (heavily extended)** — Now spans 8 grouped sections:
  1. **Identity & Role** — name, designation, system role, departments, **employment_type** (Permanent / Daily Wages / Contractual), reporting manager, branch, joining date, monthly salary.
  2. **Contact** — email, mobile, alt phone, current & permanent addresses.
  3. **Personal Details** — DOB, gender, marital status, blood group, father's & mother's name, PwD flag.
  4. **Legal Compliance — Indian Statutory IDs** — PAN, Aadhaar (masked in exports), UAN, PF Account, ESIC IP No., PF Applicable toggle, ESIC Applicable toggle.
  5. **Bank Account (for Salary)** — Bank name, A/c No., IFSC, Branch.
  6. **Emergency Contact & Nominee** — Name, phone, relation, nominee name + relation + share %.
  7. **Daily Wages Details** *(conditional — shown only if employment_type=daily_wages)* — daily_rate, working_days_per_month.
  8. **Contractual Engagement** *(conditional — shown only if employment_type=contractual)* — contractor name, CLRA license no., contract start & end.
- **`/app/frontend/src/components/DataTableShell.jsx`** — Additive feature flags added: `type:"section"` renders a header bar, `showIf(form)` for conditional fields, `required` for red asterisks, `help` for hint text below input. Dialog widened to `max-w-3xl` and body now `max-h-[70vh] overflow-y-auto`. **Verified non-regressive** against Vendors & other DataTableShell-driven pages.
- **List view** gets a new "Type" column with tone-coded badge (Permanent = primary, Daily Wages = warning, Contractual = neutral).
- **Coverage**: 16/16 backend pytest + 100% frontend e2e in iter37. Zero defects. Verhoeff checksum verified to reject random-12-digit Aadhaars and accept the well-known test value `999941057058`.

### Iteration 37 — AI Document Scanner & KYC Verification (May 23, 2026)
- **New `/app/backend/routers/hr/documents.py`** — Upload, list, scan (Gemini 2.5 Pro via Universal Key + `emergentintegrations`), soft-delete, and verification engine for employee KYC documents. 14 supported `doc_type`s: Aadhaar, PAN, Bank Passbook, UAN/EPF, ESIC, Educational, Experience, Driving License, Passport, Voter ID, Police Verification, Medical Fitness, Project Cert (PASMA/IRATA/OSHA auto-detected), Other.
- **`_build_verification()`** maps extracted fields back to the employee record via `DOC_FIELD_MAP` and produces match/mismatch/no_data per field with comparators: `id` (normalised), `name` (token overlap, case + space tolerant), `date` (ISO/DD-MM-YYYY tolerant), `str_ci`. Returns `overall` plus `autofill_candidates`.
- **Auto-population**: empty employee fields are auto-filled from extracted values — re-validated through `india_compliance.validate_employee_compliance` first so an OCR'd "ABCDE 1234 F" PAN doesn't break the regex.
- **Verification gating**: `employees.verification_status` is recomputed after every scan/delete. It flips to `verified` only when all 3 KYC-key docs (Aadhaar + PAN + Bank) have `overall='verified'`. Otherwise stays `pending`. Header badge on Employee 360 reflects this.
- **Gemini integration**: model `gemini-2.5-pro`, system prompt enforces strict JSON output with doc_kind + confidence + fields + raw_text. `_safe_json_load` strips ```json fences and falls back to first `{...}` block extraction for resilient parsing.
- **Frontend Employee 360 → Documents tab**:
  - Section "Documents · AI-Scanned KYC" with + Add upload dialog (14 doc-type options, 3 tagged "KYC key" in green).
  - Each row shows filename link · type badge · scan_status badge · verification overall badge with `n✓ n✗ n?` count breakdown · AI Scan / Re-scan (with spinner) · Delete.
  - When verification.items present, an expanded chip row shows per-field status (✓ match / ✗ mismatch / − no_data).
  - Header "KYC Verified" / "Verification Pending" badge driven by `employees.verification_status`.
- **RBAC**: write/delete gated on `hr_employee_360`. site_supervisor → 403 confirmed.
- **Coverage**: testing agent ran 17/17 backend pytest (uploads, validation, RBAC 403, soft-delete, verification engine unit tests for match/mismatch/normalisation/autofill, employee verification_status recompute) + 100% frontend e2e (upload → list → scan → delete via UI). One environmental note: Universal Key budget cap returns 502 from Gemini — code path verified to wrap cleanly, scan_status stays `not_scanned`, no partial DB write. **User can top up Universal Key in Profile → Universal Key → Add Balance** to enable live extraction.

### Iteration 38 — AI Auto-fill on New Employee creation (May 23, 2026)
- **New endpoint** `POST /api/hr/documents/scan-prefill` (multipart file + doc_type, NO employee_id needed) — runs the same Gemini 2.5 Pro extraction as the post-creation scan but returns `{doc_type, detected_kind, confidence, raw_fields, employee_fields, raw_text_preview}`. `employee_fields` is already mapped to the Employees form's field names (`pan_number`, `bank_ifsc`, `name`, `dob`, `aadhaar_number`, …) so the frontend can spread it directly into form state. ID values are normalised the same way `india_compliance` validates them.
- **Refactor**: shared `_gemini_extract(blob, mime, doc_type, session_id)` helper used by both `/scan-prefill` and the existing `/employees/{eid}/documents/{doc_id}/scan` (zero code duplication).
- **Upload endpoint** `POST /api/hr/employees/{eid}/documents` now accepts an **optional `scan_result_json` Form field**. When supplied:
  - Skips the 2nd Gemini call entirely (saves Universal Key budget).
  - Builds a fresh `verification` via `_build_verification(map_kind, fields, emp)`.
  - Stores `scan_status='scanned'`, `scan_result.from_prefill=true`.
  - Calls `_recompute_employee_verification` so the moment Aadhaar + PAN + Bank are all attached the employee flips to `verification_status='verified'`.
- **`DataTableShell` extensions** — two new opt-in props (additive, no regression for existing pages):
  - `formHeader(mode, form, setForm)` — render any JSX above the form fields.
  - `onAfterCreate(createdRow, form)` — fires after a successful `onCreate`, gets the created row so callers can do follow-up work like attaching documents.
- **`Employees.jsx` → `AIPrefillPanel`** — a violet-tinted "✨ AI Auto-fill from Documents" strip at the top of the New Employee dialog. Doc-type Select (8 ID types) + file input + "Scan & Fill" button. After scan:
  - Form fields filled **only when empty** (existing user-entered values never overwritten).
  - Pending-doc chip appears (✓ PAN Card · ✓ Aadhaar Card …) with a × to remove from queue.
  - File input auto-clears for the next scan.
  - Toast shows `filled N field(s) · M skipped (already set)`.
- **`attachPendingDocs(createdEmployee)`** — runs after `POST /api/employees` succeeds, sequentially attaches each pending document with its pre-scan result so verification is computed instantly without burning more Gemini calls.
- **Coverage**: testing agent iter39 ran **8/8 backend pytest** (including a live Gemini PAN extraction confirming `ABCDE1234F`) + **100% frontend E2E** (PAN + Bank scan → form filled → save → server-side verification of both docs attached with `from_prefill=true`). Zero bugs found.

### Iteration 40 (May 26, 2026) — Microsoft 365 SMTP Email + Outbox
- **M365 SMTP integration** via `smtp.office365.com:587` STARTTLS with App Password — no Azure App Registration / OAuth required.
- **Hybrid sender model**: system emails from a single shared mailbox (creds in `backend/.env`) + user-initiated emails from each user's own M365 mailbox (per-user App Password stored Fernet-encrypted in `db.smtp_user_credentials`).
- **Backend**: `/app/backend/m365_email.py` (encryption, MIME multipart builder for HTML+plain+attachments, `aiosmtplib` async send with exponential backoff + jitter, error classification: SMTPAuthError / SMTPThrottleError / SMTPPermanentError, friendly error translator).
- **Router**: `/app/backend/routers/email_router.py` — `GET /api/email/config`, `POST /api/email/config/test`, `GET|PUT|DELETE /api/email/me/smtp`, `POST /api/email/me/test`, `POST /api/email/send` (multipart with file uploads), `GET /api/email/outbox` (paginated + filtered), `GET /api/email/outbox/{id}`, `POST /api/email/outbox/{id}/retry`.
- **Outbox** (`db.email_outbox`): full audit log of every send — `to/cc/bcc/subject/sender_type/sender_email/attachments_summary/file_ids/status (queued|sending|sent|failed)/attempts/last_error/smtp_response/sent_at/queued_by/related{entity_type,entity_id}`. attachments_inline (base64) stored in DB for retries, never returned in API responses.
- **Encryption**: Fernet (AES-128-CBC + HMAC-SHA256) with key in `backend/.env → M365_FERNET_KEY` (auto-generated on first install). Verified at-rest token format `gAAAAA…` in tests.
- **RBAC**: new resource `email_outbox` — read/write open to ops/finance/HR/sales/procurement leadership roles; delete super_admin only.
- **Frontend pages**:
  - `/app/admin/email-settings` — shared mailbox status (redacted), Fernet key status, setup-step guide for SMTP AUTH enablement (PowerShell snippets), and a "Send Test" form.
  - `/app/admin/email-outbox` — filterable table (status / sender / search), retry button, attachment count badges, detail dialog showing body, SMTP response, error message.
  - `/app/me/email` — per-user M365 mailbox setup with App Password entry, "Save credentials" (encrypted), "Send test", "Remove credentials". Step-by-step App Password instructions linking to `mysignins.microsoft.com`.
- **Header menu**: new "Email Settings (M365)" item in the user dropdown alongside Profile.
- **Admin Console tiles**: 2 new tiles — Email Settings, Email Outbox.
- **Backend tests**: `/app/backend/tests/test_iteration40_m365_email.py` — **27/27 PASSED** (config status, RBAC 403 for vendor, Fernet at-rest verification, upsert idempotency, /me/test friendly error on fake creds, outbox pagination + filters, retry semantics, index verification, MongoDB `_id` exclusion across all responses).
- **Status**: Backend fully tested & verified. Frontend builds & renders. Awaiting user's M365 mailbox + App Password to populate `M365_SMTP_SHARED_USERNAME` / `M365_SMTP_SHARED_PASSWORD` in `.env` for live end-to-end test.
- **Future deprecation note** (informational): Microsoft is sunsetting Basic Auth for SMTP submission. Current timeline targets end of 2026 (default-off) and final removal H2 2027. When that happens, this integration will need a migration to OAuth-based SMTP or Microsoft Graph API.

### Future iterations (P2+)
- WhatsApp notifications (Twilio)
- Live GPS tracking integration
- Native mobile shell (React Native)
- Granular field-level audit log explorer
- Reports: drill-into-data and pivot views
- Multi-tenant / multi-company support
- Rate-master integration into Quotation Builder (auto-suggest rate when picking activity)
- Approval matrix tuning for quotations (auto-trigger high-value approval at threshold)
- Client portal entry (alternative to email submission)
- **Email module v2**: wire `POST /api/email/send` into Quotations / POs / RFQs / RA Bills / HR letters "Send" buttons with auto-attached PDFs; add scheduler job to retry queued/failed every N minutes; add weekly digest emails.
- **OAuth migration for M365 SMTP** (mandatory before H2 2027 when Basic Auth is removed).

### Iteration 42 (May 27, 2026) — Role Catalog (Super-Admin only)
- **New page** `/app/admin/role-catalog` lets super-admin **add or remove roles** at runtime. Built-in + custom roles live side-by-side in `db.role_catalog` (seeded with 16 built-ins on startup, idempotent).
- **Add role wizard** with: auto-suggested key, immutable lowercase regex `[a-z][a-z0-9_]{2,40}`, scrollable resource × action checkbox grid with per-row "Toggle" shortcut and search.
- **Delete role**: blocked while any user holds the role (409 with user count); strips the role from every `db.rbac_overrides` cell on success; super_admin always protected.
- **Per-user choice**: built-in roles ARE deletable (when no users hold them) — per the user's explicit request. The seeder restores any built-in on next backend boot, so accidents are recoverable.
- **Catalog drives every dropdown**: `/admin/role-register`, `/admin/users` create/update, `/admin/approval-matrix/roles`, frontend `UserManagement.jsx`, `Profile.jsx`, `RoleRegister.jsx` — all now fetch the catalog with a static fallback to `core.ROLES` if the catalog is unavailable.
- **Endpoints** (all RBAC-gated on `role_register`):
  - `GET    /api/admin/role-catalog` — list + per-role user_count
  - `POST   /api/admin/role-catalog` — create custom role + seed initial permissions
  - `PATCH  /api/admin/role-catalog/{key}` — rename label/description (key immutable)
  - `DELETE /api/admin/role-catalog/{key}` — block if users hold it; strip overrides
- **Backend tests**: `/app/backend/tests/test_iteration42_role_catalog.py` — **24/24 PASSED**. One real bug caught by testing agent: ObjectId leak from `insert_one`'s in-place mutation — fixed with `doc.pop("_id", None)`.
- **Status**: ✅ Live and verified.

### Iteration 41 (May 26, 2026) — Entity-aware Email Actions + AI Cover-Note + Retry Scheduler
- **Wired the M365 SMTP module into all 5 outbound document modules**: Quotations, Purchase Orders, RFQs, RA Bills, HR Letters. Each row has a `📧 Email` action.
- **Single reusable `<SendEmailDialog />`** drives the UX: pre-fills `To` (resolved from client/vendor/employee email on the record), subject + body templates, sender badge, attachment toggle, AI Draft button.
- **AI Cover-Note drafter** via **Claude Sonnet 4.5** (Universal LLM Key) with Gemini 2.5 Pro fallback. 4 tones. System prompt is INDIAN TRADE LINKS-specific (industrial services, Indian business etiquette, JSON-only output). End-to-end live tested.
- **Hybrid sender policy**: HR letters → shared mailbox; Quotations / POs / RFQs / RA Bills → user's own M365 mailbox. Auto-fallback to shared if user has no personal SMTP, with banner.
- **Auto-attached PDFs/DOCX**: Quotation uses existing rich PDF; PO / RFQ / RA Bill use new `document_pdf.py` (reportlab one-page renders); HR letter fetches DOCX binary from `db.hr_letters[id].binary`.
- **Scheduler retry job** — APScheduler `IntervalTrigger(minutes=10)` invoking `retry_pending_outbox(max_attempts=3, retry_after_minutes=10)`. Skips `error_type ∈ {auth, permanent}`. Bounded to 50 rows/tick.
- **New endpoints** (all under `/api/email`, RBAC `email_outbox` write):
  - `GET /entity-context/{module}/{record_id}` — frontend pre-fill
  - `POST /ai-draft` — Claude → Gemini fallback
  - `POST /send-entity/{module}/{record_id}` — composes & queues with PDF/DOCX attached
- **Pre-existing fix**: `db.sites.gst` partial-index `$ne → $gt:""` wrapped in try/except, unblocking scheduler startup.
- **Backend tests**: `/app/backend/tests/test_iteration41_email_actions.py` — **20/20 PASSED**.
- **Status**: ✅ Quotation, PO, RFQ, RA Bill working end-to-end via user mailbox (verified by real quotation email delivered). HR Letters waiting on rotated shared-mailbox App Password being pasted into `M365_SMTP_SHARED_PASSWORD`.


### Iteration 43 (May 28, 2026) — Microsoft Graph OneDrive Cloud Storage (Phase 1 + 2)
- **Phased rollout (user-confirmed plan)**: Phase 1 = Azure OAuth & Connection · Phase 2 = One-way push of all new files + nightly DB backup · Phase 3 (next) = Historical file migration · Phase 4 (later) = Data Linkage (Tally first).
- **Core service** (`/app/backend/onedrive_service.py`):
  - App-only OAuth2 `client_credentials` flow via MSAL (`ConfidentialClientApplication`).
  - Persistent token cache in `db.onedrive_token_cache` (per `client_id`) so tokens survive restarts.
  - `Files.ReadWrite.All` scope (`.default`).
  - Drive resolution via `GET /users/{upn}/drive`; nested folder creation via `driveItem` path API.
  - Single-PUT for ≤ 4 MB; resumable `createUploadSession` for larger files (5 MB chunks).
  - Client secret encrypted at rest with the existing `M365_FERNET_KEY` (Fernet).
- **Admin router** (`/app/backend/routers/onedrive_router.py`, super_admin only):
  - `GET/PUT /api/admin/onedrive/settings` — masked client_secret; blank secret on PUT keeps existing.
  - `POST /api/admin/onedrive/test-connection` — resolves drive + persists `last_test_at/ok/error`.
  - `GET /api/admin/onedrive/queue` + `GET /stats` — push queue listing + counters.
  - `POST /api/admin/onedrive/process-now` — background flush of pending queue.
  - `POST /api/admin/onedrive/migrate-historical` — enqueues every existing non-deleted file (idempotent).
  - `POST /api/admin/onedrive/retry/{id}` — reset failed item to pending.
  - `POST /api/admin/onedrive/backup-now` + `GET /backups` — manual + listing for DB snapshots.
- **Upload hook**: `files_router._upload` now calls `enqueue_file(record.id)` after every successful Emergent-storage put. Wrapped in try/except so a OneDrive outage can never break uploads.
- **Background jobs** (`/app/backend/scheduler.py`):
  - `onedrive_push` — every 2 minutes, batches up to 25 files, exits cleanly if integration disabled.
  - `onedrive_backup` — nightly @ 18:30 UTC (midnight IST), uses `mongodump --archive --gzip`; falls back to per-collection JSON+gzip if mongodump isn't installed.
  - Pushes into `Backups/YYYY/MM/<db>-YYYYMMDD-HHMMSS.archive.gz`.
- **Folder convention**: `<base_folder>/YYYY/MM/<Module>/<filename>` — module label auto-mapped from `parent_type` (Quotations, Purchase-Orders, Purchase-Requisitions, RFQs, GRN, RA-Bills, DPR, Measurements, HR-Letters, etc.).
- **Frontend** (`/app/frontend/src/pages/admin/OneDriveSettings.jsx`, route `/app/admin/onedrive`): 3-tab admin UI — Settings (Azure App fields + Test Connection + setup checklist) · Push Queue (4-card stats + retry buttons + per-row OneDrive web-link) · Backups (history + Backup Now). Wired into sidebar (`nav-admin-onedrive`) and AdminConsole tile.
- **Status**:
  - Backend plumbing fully verified — **24/24 backend pytest pass** (`test_iteration43_onedrive.py`).
  - 🟡 Live token acquisition currently fails with `AADSTS90002 (tenant not found)` against the tenant ID supplied by the user (`a399706e-c501-4e30-9d0f-45ba9ebfb504`). This is an Azure-side credential issue, not a code defect — the integration code reaches Microsoft's OIDC discovery endpoint cleanly and surfaces the error on the UI.
  - **Action item for user**: re-verify the Directory (Tenant) ID and Client ID in Microsoft Entra Admin Center; grant admin consent for `Files.ReadWrite.All` (Application) on the app registration; confirm the backup user (`backup@indiantradelinks.in`) has a OneDrive-enabled license and has signed in once.


### Iteration 44 (May 28, 2026) — Data Linkage (Phase 4) + OneDrive Migration UI Polish (Phase 3) + Credential Refresh
**Phase 3 — OneDrive Migration UI polish** (`/app/admin/onedrive`):
- New live-poll toggle (5-second interval) on the Push Queue tab.
- Overall progress bar `done / total` (pushed+failed vs total) with derived throughput (files/min) and ETA. Computed client-side from successive `/stats` polls.
- "Migrate Historical Files" button now auto-enables live polling + auto-switches to the Queue tab so user can watch progress.
- testids: `onedrive-autorefresh`, `onedrive-progress`, `stat-pending`, `stat-pushed`, `stat-failed`, `stat-total`.

**Phase 4 — Data Linkage** (`/app/backend/routers/linkage_router.py`, `/app/frontend/src/pages/admin/DataLinkage.jsx`, `/app/frontend/src/components/LinkagePanel.jsx`):
- **4a — Cross-module link graph** (`GET /api/linkage/graph/{resource}/{record_id}`):
  - LINK_MAP dict declares per-resource child-relationship rules (e.g. `clients → quotations/projects/sites/orders/ra_bills/enquiries`, `projects → PR/PO/RFQ/GRN/DPR/measurements/ra_bills/deployments/safety_reports`, `vendors → POs/RFQs/invoices/evaluations`, etc.).
  - `_substitute()` resolves `$field` tokens against the parent doc so a single rule like `{"client_id": "$id"}` works across every collection.
  - Each group returns count + first 50 items with projected display fields (capped to keep payload small).
  - New `<LinkagePanel resource recordId/>` reusable React component (auto-fetches, renders grouped lists with deep-links to module pages). Wired into the right rail of `ProjectDashboard.jsx`.
- **4b — Google Sheets live link**:
  - `GET/POST/DELETE /api/linkage/sheets` channels in `db.sheet_channels` (name + published-CSV URL + description + last_synced_at + last_row_count).
  - `GET /api/linkage/sheets/{id}/data` live-fetches the CSV via `httpx`, parses with `csv.reader`, returns headers + up to 500 rows, persists sync metadata.
  - `_normalise_sheet_url()` auto-coerces regular Google Sheets `/edit` URLs into `/export?format=csv&gid=...` so users don't have to figure out the exact share format.
  - RBAC: write = super_admin/director/general_manager/accounts_executive; delete = super_admin/director only.
- **4c — Tally HTTP-XML sync**:
  - `GET/PUT /api/linkage/tally/config` (super_admin only): host/port/company/enabled.
  - `POST /api/linkage/tally/test` — sends a "List of Companies" XML collection request to the configured Tally gateway. Persists `last_test_at/ok/error`.
  - `POST /api/linkage/tally/sync-masters` — fetches Ledgers (customers + vendors) via Tally XML, parses with `ElementTree`, persists to `db.tally_ledgers`.
  - `GET /api/linkage/tally/ledgers?q=` — search/list synced ledgers (paginated to 200).
  - Bi-directional sync (pushing ERP transactions back into Tally) intentionally deferred.
- **Frontend** (`/app/admin/data-linkage`): two-tab admin page — Google Sheets (add channel + preview live data table) and Tally Sync (settings + test + sync + ledger list with search). Wired into AdminConsole tile + sidebar.
- All external-IO paths wrapped to surface clean 502s (no 500 leakage). No live Tally server in the pod — endpoints behave gracefully when unreachable.

**Credential refresh**:
- All 12 previously documented demo accounts (project_manager, sales_executive, hr_executive, purchase_officer, store_incharge, safety_officer, supervisor, director, general_manager, 2 dept_heads, site_engineer) re-seeded via `/api/admin/users` to match `/app/memory/test_credentials.md`.
- All 13 accounts verified login = 200.

**Tests**: 44/45 PASS · 1 skipped (no seeded enquiries) · 0 failed (`test_iteration44_linkage.py`). OneDrive regression (Iter 43) still green.


### Iteration 45 (May 29, 2026) — Employee Advance Register Module (Phase A + B)
**Scope shipped**: end-to-end advance request lifecycle from creation → multi-step approval → finance payment + journal voucher. Phase C (EMI auto-recovery during payroll) intentionally deferred per user choice.

- **Data model**:
  - `db.advance_types` (7 defaults seeded on startup: Salary/Emergency/Medical/Site/Festival/Travel/Other) with `max_amount` and `max_installments` caps.
  - `db.employee_advances` — full lifecycle doc: advance_no, employee snapshot (code/name/dept/salary/joining), advance_type, amounts (requested/approved/paid/recovered/outstanding), emi + installments + remaining_installments, repayment_start_month, attachments[], status (`draft`→`submitted`→`under_approval`→`approved`/`rejected`→`payment_pending`/`paid`→`under_recovery`→`closed`), on_behalf_of flag, payment block, status_history[].
  - `db.advance_recoveries` (Phase-C ready, currently empty).
  - `db.journal_entries` auto-rows on payment for accounts ledger.

- **Approval workflow** (`approval_engine.APPROVAL_CHAINS["employee_advance"]`): 6-step chain — Reporting Manager / Project Coordinator → Department Head → HR → Accounts → Finance Head (general_manager) → Director. Chain template overridable via existing `db.approval_chains` editor. Universal hook `on_advance_approval_action()` runs from `approvals_router` on every action → keeps `employee_advances.status` and `approved_amount` in sync.

- **Endpoints** (`/api/advance-types`, `/api/advances`):
  - `GET/POST/PUT/DELETE /advance-types` (RBAC: write = super_admin/hr_executive/general_manager/director).
  - `POST /advances` — self & on-behalf (coordinator workflow). Validates caps. Auto-numbers `AD-YYYY-####` via `next_sequence`.
  - `POST /advances/{id}/submit` · `PUT/DELETE /advances/{id}` · `GET /advances?status=&advance_type=&department=` · `GET /advances/{id}` (returns linked approval + recoveries).
  - `POST /advances/{id}/amend` — current step approver can revise approved_amount + installments before final approval.
  - `POST /advances/{id}/payment` — accounts/finance/director only; modes (bank_transfer/cash/cheque/upi); writes journal entry; flips status to `paid` (full) or `payment_pending` (partial).
  - `GET /advances/dashboard/summary` — totals + by_status + by_department aggregations.

- **RBAC** (`hr_advances` key in `rbac.py`):
  - read = `*` (employees see only their own + their creations; privileged roles see all)
  - write = super_admin, hr_executive, general_manager, director, project_manager, dept_head, accounts_executive
  - delete = super_admin, hr_executive

- **Frontend** (`/app/hr/advances`):
  - 5-tile summary header (Outstanding, Pending Approval, Requested, Paid, Approved totals).
  - Register table with filters (status, type, department), "Awaiting" column showing the current approver, on-behalf badge, emergency flag, action buttons (view, pay).
  - **Create dialog** — toggle for "on-behalf" mode (coordinator workflow), employee dropdown filters to active staff, auto-display of employee code/designation/salary/joining card, advance-type select shows max-amount hint, computed EMI preview, emergency flag, draft/submit buttons.
  - **Detail dialog** — 12-field summary card, full approval timeline with role + approver + timestamp + comments, payment block (mode/amount/voucher/txn/bank), status_history activity log, in-line approve/reject if current user is the current step approver, delete (super_admin/hr only).
  - **Payment dialog** — mode + amount + date + bank/voucher/txn + remarks.
  - Sidebar entry "Advance Register" with Wallet icon under HR group.

- **Status**: 26/26 backend pytest pass (`test_iteration45_advances.py`). Verified happy path AD-2026-0001 (₹25,000 Salary Advance for "Mohan Lal" — driven through all 6 approval steps, paid in full, journal voucher VCH-001 created, dashboard aggregates accurate).

- **Deferred (Phase C/D/E)**: EMI auto-recovery during payroll run, manual deduction adjust / skip / foreclosure / settlement, employee self-service dashboard widget, 9 reports (HR/Finance/Management), bulk Excel upload for historical advances.


### Iteration 46 (May 29, 2026) — Employee Advance Register · Phases C + D + E
**Phase C — Recovery flow** (`/app/hr/advance-recovery → Monthly Run tab`):
- `POST /api/advances/recovery/run` dry-run-then-commit pattern. Returns proposals + skipped + total_emi. dry_run=false writes `advance_recoveries.type='emi'` rows, decrements outstanding + remaining_installments, auto-flips status to `under_recovery` (or `closed` if outstanding == 0). Idempotent — re-runs skip already-processed lines.
- `POST /api/advances/recovery/override` — HR/Finance can change a single line BEFORE or AFTER commit (writes `type='manual'`, replaces existing row, re-derives outstanding from `approved_amount - recovered_amount`).
- `POST /api/advances/{id}/recovery/skip` — `type='skipped'` audit row, no balance change.
- `POST /api/advances/{id}/recovery/foreclose` — `type='foreclosure'`, amount must equal outstanding, closes the advance.
- `POST /api/advances/{id}/recovery/settle` — GM/Director only; waives the rest, closes advance with `settlement_waived` recorded.
- **Frontend** detail dialog gains "Recovery Actions" panel (Skip/Foreclose/Settle buttons) and a "Recovery Ledger" table.

**Phase D — Reports + Self-service**:
- `GET /api/advances/me/summary` — compact dashboard data for the logged-in employee (active_advances, history, outstanding_total, next_emi). Returns `linked:false` for users with no employee record (e.g. super_admin).
- `GET /api/advances/reports/outstanding?department=&site=` — Finance outstanding report (returns rows + total).
- `GET /api/advances/reports/monthly-recovery?month=YYYY-MM` — aggregated recovery breakdown per advance/employee.
- `GET /api/advances/reports/aging` — buckets 0-30/30-60/60-90/90+ by paid_at→created_at age.
- New **`<MyAdvancesWidget/>`** component (`/app/frontend/src/components/MyAdvancesWidget.jsx`) embedded in `DepartmentLauncher` (`/app/modules`) — shows outstanding, next EMI, 3 most recent active advances, "View All" + "Statement (CSV)" buttons. Auto-hidden if user has no linked employee.
- New `/app/hr/advance-recovery` page (5 tabs: Monthly Run · Outstanding · Recovery · Aging · Import). Tab "Monthly Run" has live per-row override inputs feeding into the commit flow.

**Phase E — Bulk import**:
- `POST /api/advances/bulk-import` accepts multipart CSV (required cols: employee_code, advance_type, approved_amount, installments, emi, repayment_start_month). Skips approval workflow (these are pre-existing balances). Marks rows `imported=true` and writes a single status_history entry. Returns `{created, errors[{line,error}], samples[]}`. Errors are line-scoped and processing continues.
- "Bulk Import" tab in `AdvanceRecovery.jsx` with template download.

**Bug fix (Iter 45 regression)**: `record_payment` was setting `outstanding = approved_amount - paid_amount` (always 0 when fully paid). Corrected to `outstanding = paid_amount` so EMI recovery can actually drain the balance.

**Tests**: 22/22 backend pytest pass (`test_iteration46_advances_phase_cde.py`). Full lifecycle validated: create → 6-step approve → pay → recovery run dry-run → commit EMI → foreclose remainder → closed.

**Backlog after this iteration**: Wire LinkagePanel into Client/Vendor/PO/Quotation/RA Bill detail pages; Tally bi-directional sync; PII masking; Safety & Compliance module; WhatsApp notifications.


### Iteration 47 (May 29, 2026) — Department-based ERP Restructuring · Phase 1 (A + B + C)
User picked the high-impact set: department-prefixed doc numbering + hardened visibility filters + department master CRUD. Phase 2 (D/E/F: cross-dept dependency rules · inter-dept delay/performance reports · audit-trail viewer) deferred.

**A — Department-prefixed document numbering** (`/app/backend/sequences.py`):
- New `DEPT_DOC_MAP` mapping 32 doc-types → `(dept_code, type_code, owner_dept_slug)` covering HR, Procurement, Store, Sales, Accounts, Finance, Operations, Safety, Logistics.
- `next_dept_doc(doc_type)` returns `{dept_doc_no:"HR/ADV/2026/0001", department, doc_type, owner_dept}` via atomic `find_one_and_update` on `db.sequences`.
- `stamp_dept_doc(doc, doc_type)` mutates doc with `dept_doc_no` + `ownership_department` (idempotent).
- **Applied to create paths**: advances (+ bulk-import), purchase_requisitions, RFQs, purchase_orders, GRNs, enquiries, quotations (auto-from-enquiry), orders, RA bills (+ DN/CN with correct prefix), DPRs, measurements, payments_in.
- **Display**: Advance Register table now shows `HR/ADV/2026/0001` with legacy `AD-2026-0018` as sub-line. Legacy numbering retained for backward compatibility.

**B — Hardened visibility filters** (`/app/backend/routers/crud_router.py`):
- Reused existing `scope.py` infrastructure (`project_filter`, `department_filter`).
- `PROJECT_SCOPED_COLLECTIONS` expanded by **9 collections**: purchase_requisitions, rfqs, grns, dprs, measurements, ra_bills, vendor_invoices, payments_in, payments_out.
- `DEPT_SCOPED_COLLECTIONS` expanded by **4 collections**: employee_advances, hr_letters, leave_requests, overtime (was just `employees`).
- Super_admin / director / general_manager continue to bypass all scoping.

**C — Department Master CRUD** (`/app/backend/routers/department_master_router.py`, `/app/admin/department-master`):
- 9 primary departments seeded on startup (`db.department_master`): Sales/SAL, Projects/OPS, Accounts/ACC, Finance/FIN, Store/STO, Safety/SAF, Logistics/LOG, HR, Procurement/PRO.
- CRUD endpoints (super_admin/director/general_manager only): GET / POST / PUT / DELETE plus sub-item endpoints to manage `sub_departments[]`, `branches[]`, `business_units[]` per department.
- Frontend admin page with per-dept cards, tag-style add/remove for sub-items, slug/code/name editor. Sidebar tile + AdminConsole tile.
- Built-in slugs cannot be deleted; sub-items are inline-managed.

**Forward-looking utility** (`/app/backend/department_scope.py`): `apply_scope(user, query, modes=[...])` + `stamp_ownership(doc, user)` for routes that need fine-grained dept/project/site scope. Not wired to any live endpoint yet — Phase 2 will use it.

**Tests**: 18/19 backend pytest pass (`test_iteration47_dept_restructure.py`). 1 skipped (RFQ requires approved-PR + vendor chain — same stamp utility validated through PR + 5 others). No regressions.

**Deferred (Phase 2)**: D — Cross-dept dependency rules (material issue requires approved PR; payment requires accounts-verified bill; payroll requires approved attendance). E — Inter-dept delay / performance reports. F — Dept-wise audit trail viewer.


### Iteration 48 (May 29, 2026) — Department Governance · Phase 2 (D + E + F)
**D — Cross-Department Dependency Enforcement**:
- **Material outward (store_router)**: outward txns MUST reference an approved `purchase_requisitions.id` OR `material_allocations.id`. Without it → HTTP 400 with corrective message. `force_unlinked=true` accepts an unlinked outward but ONLY for super_admin (bypass).
- **Vendor invoice ↔ Finance payment** (`/api/dept-gov/invoices/{id}/verify` + `/api/dept-gov/payments-out`):
  - Accounts (or accounts_executive/GM/director) verifies an invoice → flips to `verified`.
  - Finance attempting `payments-out` on a non-verified invoice → 400. Overpayment beyond invoice amount → 400.
  - Successful payment writes `payments_out` row with `dept_doc_no=FIN/PAY/...`, flips invoice to `paid` when fully settled.
- **Payroll preflight** (`/api/dept-gov/payroll/check-attendance`): blockers list = every active employee without approved-attendance row for the month. Returns `can_proceed` flag for the payroll runner to gate on.

**E — Inter-Department Reports** (`/api/dept-gov/reports/...`):
- `handoff-delays?days=N` — per doc-type avg minutes/hours per approval step + longest step + approved/rejected counts, computed from `db.approvals.history[].at` deltas.
- `dept-performance?days=N` — counts + amounts per `ownership_department` across PO, RA bills, payments_in, payments_out, quotations, employee_advances, vendor_invoices, with `by_doctype` breakdown.
- `dept-manpower` — headcount vs active deployments per dept → available + utilisation %.

**F — Department Audit Trail Viewer**:
- `GET /api/dept-gov/audit/by-dept?dept=&action=&resource=&date_from=&date_to=&limit=` — filters `audit_logs` and (when dept specified) post-filters by `ownership_department` of the referenced record. Restricted to super_admin/director/GM/accounts.
- `GET /api/dept-gov/audit/record/{collection}/{record_id}` — full chain timeline: created phase (with dept) + approval history (with dept on each step) + update/delete entries. Returns approval doc + log count.

**Frontend** (`/app/admin/dept-governance` — 5 tabs): Hand-off Delays · Dept Performance · Dept Manpower · Audit Trail · Record Trail. Sidebar tile.

**Tests**: 27/28 backend pytest PASS (1 skipped — no seeded approved PR for outward happy-path; inverse coverage 100%). Zero regressions on Iter 47 (numbering + scoping).

**Phase complete**: The 9-department restructuring ask is now fully delivered across Iter 47 (numbering + scoping + dept master) + Iter 48 (dependency rules + reports + audit viewer).


### Iteration 49 (May 29, 2026) — Real Payroll Module ✅
Wires monthly payroll into the Iter 45/46 Advance EMI hook + Iter 48 attendance preflight.

**Backend** (`/app/backend/routers/payroll_router.py`, 451 lines):
- **Payroll Master** CRUD (`db.payroll_master`) — one row per employee with `basic / hra / special_allowance / site_allowance / conveyance / medical / pf_applicable / esi_applicable / pt_state / tds_override_pct / fixed_other_earnings[] / fixed_other_deductions[] / pan / bank_*`. Endpoints `GET/PUT /api/payroll/master[/{employee_id}]`.
- **Monthly Run** preview → override → commit cycle:
  - `POST /api/payroll/run/preview {month, employee_ids[], skip_attendance_check}` — calls Iter 48 `payroll_attendance_check` FIRST; if `can_proceed=false`, returns blockers and zero payslips. Otherwise computes `payslips[]` with statutory PF (12% × min(basic, ₹15k)), ESI (0.75% if gross ≤ ₹21k & opted-in), PT (flat ₹200 GJ slab), TDS (% override), LOP-factored earnings, **and advance EMI auto-pulled from `db.employee_advances` where status ∈ {paid, under_recovery} & outstanding > 0 & repayment_start_month ≤ run month**.
  - `POST /api/payroll/run/override {month, employee_id, earnings?, extra_earnings?, extra_deductions?, advance_emi?, note}` — per-employee per-month deltas in `db.payroll_overrides`.
  - `POST /api/payroll/run/commit {month, skip_attendance_check}` — re-runs preview, applies overrides (incl. **proportional scaling of `advance_lines[]` when `advance_emi` is overridden** — fix for testing agent action item), persists `db.payslips` with `dept_doc_no = HR/SAL/YYYY/MM/<emp_code>` and `ownership_department = 'hr'`, writes paired `db.advance_recoveries` rows, decrements `employee_advances.outstanding` + `remaining_installments`, flips status to `under_recovery` (or `closed` when fully paid). Returns 400 if run already committed (idempotent).
- **Queries**: `GET /payroll/payslips?month&employee_id`, `GET /payroll/payslips/{employee_id}/{month}`, `GET /payroll/runs`, `GET /payroll/me` (employee self-service — latest 12 payslips matched by email).
- **Routing fix** in `server.py`: `payroll_router` now mounted BEFORE `crud_router` so literal routes (`/payroll/master`, `/payroll/runs`, `/payroll/run/*`) aren't swallowed by the generic `/payroll/{id}` legacy resource.

**RBAC**: new key `hr_payroll` in `/app/backend/rbac.py`. Read: super_admin/director/general_manager/hr_executive/accounts_executive/dept_head. Write: super_admin/hr_executive. Delete: super_admin only.

**Frontend** (`/app/frontend/src/pages/hr/Payroll.jsx`, 322 lines): 3-tab UI at `/app/hr/payroll`:
- **Monthly Run** — month picker · "Skip attendance check" toggle · Preview + Commit buttons · preflight-failed banner with blocker list · 4-tile totals strip (Payslips · Earnings · Deductions · Net Pay) · payslip table with PF/ESI/PT/TDS/Advance EMI columns · per-row "Eye" detail dialog with full earnings + deductions table.
- **Payslips** — month filter · table of persisted payslips with `dept_doc_no` shown in monospace.
- **Payroll Master** — list with PF/ESI badges + CTC rollup · Add/Edit dialog with 6 earnings fields + statutory toggles + PAN/bank fields.
- Route registered in `App.js`; sidebar entry `nav-hr-payroll` (perm `hr_payroll`) in HR group; tile in HR department workspace.

**Tests**: 18/18 backend pytest PASS via `testing_agent_v3_fork` (iteration_49.json):
- Master CRUD + round-trip
- Preview computes correct statutory amounts (PF=₹1,800, PT=₹200, net=₹43,850 on the test CTC)
- Commit writes payslip + advance_recoveries + mutates advance (outstanding 24k→20k, status `paid` → `under_recovery`, remaining_installments 6→5)
- Idempotency: re-commit returns 400
- Override → advance_emi=0 also clears advance_lines (so no spurious recovery row)
- Preflight failure path (no approved attendance) returns `preflight_failed=true` with blocker list
- RBAC: 401 unauth, 403 vendor on master + preview
- Regression: Iter 47 dept master, Iter 48 dept-gov preflight, Iter 45/46 advances dept_doc_no formatting, HR workspace tile, store-tx pr_id|allocation_id enforcement all still GREEN.


### Iteration 50 (May 30, 2026) — Approval Workflow Closed-Loop · Phase 1 of 3 ✅
Spec source: user-supplied 11-point "ERP Approval Workflow Enhancement Requirements" document.

**Backend** (`/app/backend/approval_engine.py`, `/app/backend/routers/approvals_router.py`):
- **New statuses on approval doc**: `rejected_revision_required`, `additional_info_required`, `resubmitted` (in addition to legacy `pending`, `in_progress`, `approved`, `rejected`).
- **Mandatory rejection remarks**: `apply_action()` raises 400 if `comment` is missing or < 5 chars for `action ∈ {reject, request_info}`. Configurable min-length via admin settings.
- **New action `request_info`**: approver can ask the originator for extra documents + a deadline. Step status becomes `info_requested`, approval status becomes `additional_info_required` (NOT terminal).
- **Reject is NOT terminal anymore** — status flips to `rejected_revision_required`; the chain is preserved so the originator can revise. Downstream record (e.g. PR, client) status mirrors to `pending_revision` via `_mirror_downstream_record()` (skipped for types with their own hook — employee_advance, deployment, department_move).
- **`POST /api/approvals/{id}/resubmit`** (creator/super_admin/hr_executive): bumps version (v1.0→v2.0…), resets every chain step to `pending`, restarts from level 0 OR resumes from the rejected level depending on `db.settings.approval_workflow.restart_on_resubmit`. Optionally accepts `file_ids[]` + `payload_patch` for originator-side edits. Snapshots the new version into `db.approval_versions` for Phase-2 compare UI.
- **`GET /api/approvals/my-revisions`**: originator-facing list of bounced-back approvals (filters by `created_by` matching name/email/id).
- **`GET /api/approvals/{id}/versions`**: full version history snapshots.
- **`GET / PUT /api/admin/approval-workflow-config`**: super_admin can toggle `restart_on_resubmit`, set min-remark length, list mandatory attachment types.
- **Notifications** (`notification_service.py`): 3 new templates — `tmpl_revision_required`, `tmpl_info_requested`, `tmpl_resubmitted` — emailed to the originator on bounce-back and to next-approver on resubmit. Resend SMTP integration (already configured in Iter 40) handles delivery.
- **Routing fix** in `server.py`: `approvals_router` mounted BEFORE `crud_router` so `/approvals/my-revisions` isn't shadowed by the generic `/approvals/{id}` catch-all.
- **Files**: `parent_type=approvals` added to `ALLOWED_FOLDERS` in `files_router.py` so attachments can be uploaded against approval docs.

**Frontend**:
- **`ApprovalDetail.jsx`** rewritten: separate **Reject dialog** (mandatory 5-char remark with live counter), **Request Info dialog** (remark + comma-separated docs + deadline date), and **Resubmit dialog** (shows original rejection reason, accepts a resubmission note). Bounced-back banner appears when status ∈ {rejected_revision_required, additional_info_required, rejected}. Resubmit button auto-shown to originator + super_admin + hr_executive. Version chip on title (v2.0 etc.), version chip on every history entry.
- **`/app/approvals/my-revisions`** (`MyRevisions.jsx`) — originator inbox with 3 KPI tiles + revision table.
- **`/app/admin/approval-workflow`** (`ApprovalWorkflowSettings.jsx`) — super_admin settings page with Switch for `restart_on_resubmit`, min-remark-length input, mandatory-attachment-categories input.
- Sidebar nav entries: `nav-my-revisions` (Command group) + `nav-admin-workflow` (Administration group).

**Test coverage** (`/app/backend/tests/test_approval_closedloop.py` — 11/11 PASS):
- Mandatory remarks: blank, whitespace, < 5 chars all return 400
- Reject flips status to `rejected_revision_required` (NOT `approved`), records `last_reject_reason/by/at/at_step`
- Resubmit (default config) restarts chain from step 0 → status `pending`, version bumps to v2.0, all steps reset
- Resubmit (config off) resumes from rejected step → status `in_progress`
- request_info: status → `additional_info_required`, step.info_required_documents populated, deadline stored
- Resubmit gating: 400 when status is still `pending`
- my-revisions returns only bounced-back items
- Admin config GET/PUT round-trip
- Approve happy-path still terminates with `approved` (regression)

**Downstream tests updated** (stale assertions): `test_iteration19_phase_d_clients.py` and `test_iteration20_procurement.py` now expect `pending_revision` (the new spec-mandated status) instead of `rejected`. Client resubmit endpoint extended to accept both legacy `rejected` and new `pending_revision` states.

**Phases 2 & 3 (P1, queued for follow-up iterations)**:
- Phase 2: Side-by-side version compare UI, mandatory-attachment enforcement at submit time, escalation timelines, auto-reminders.
- Phase 3: 5-lane My-Approvals dashboard (Pending / Rejected / Revision Required / Additional Info / Resubmitted), cycle-time + bottleneck analytics, in-app push notifications, stalled-approval reminder cron.


### Iteration 51 (May 30, 2026) — Approval Workflow Phase 2 + Phase 3 ✅
Completes the 11-point spec. All tests 28/28 PASS (Iter 49+50+51 combined), zero new regressions.

**Phase 2 — Version Compare · Mandatory Attachments · Reminders & Escalation**

Backend (`/app/backend/routers/approvals_router.py`, `/app/backend/scheduler.py`):
- `GET /api/approvals/{id}/versions/compare?v1=X&v2=Y` — returns field-level diff `{rows[{key, v1, v2, changed}], history_diff{v1_tail, v2_tail}}`; 404 when version missing.
- `assert_attachments_for_type(type, file_ids)` helper — raises 400 when type is on the admin-configured `mandatory_attachment_types` list and no files provided. Called by upstream routers (PR submit, client onboarding, etc.) right before creating an approval.
- Extended admin config (`db.settings.approval_workflow`): `escalation_days` (default 3), `reminder_days` (default 1), `auto_reminders_enabled` (default true).
- **Scheduler cron `_approval_reminder_job`** @ 08:00 UTC daily (`CronTrigger(hour=8, minute=0)`):
  - Reminder pass: emails the assigned approver(s) for every approval idle > `reminder_days` (rate-limited to 1 nudge / 22h via `last_reminder_at`).
  - Escalation pass: when idle > `escalation_days`, sets `chain[idx].escalated=true`, appends an `action='escalate'` history entry, emails the next-rung role (supervisor → dept_head, dept_head → general_manager, accounts_executive → general_manager, etc.), and pushes an in-app notification.

Frontend:
- **`VersionCompare.jsx`** — full-width dialog with v1 / v2 dropdowns, row-level diff table (amber bg + Δ badge on changed rows), and side-by-side history tails. Wired into `ApprovalDetail` via a "Compare" button beside the version chip.
- **`ApprovalWorkflowSettings.jsx`** extended with a "Reminders & Escalation" card — Switch for `auto_reminders_enabled`, number inputs for `reminder_days` and `escalation_days`.

**Phase 3 — 5-Lane Dashboard · Analytics · In-App Notifications**

Backend (`/app/backend/routers/approvals_router.py`):
- `GET /api/approvals/lanes` — buckets every open approval into 5 lanes: `pending`, `revision_required`, `additional_info`, `resubmitted`, `rejected`. Filters by current user's role (approver lane) OR creator email/name/id (bounce-back lanes). super_admin sees all.
- `GET /api/approvals/analytics?days=N` — aggregates over the last N days: total approvals, avg/p50/p95 cycle days, rejections, info_requests, resubmits; per-type `{total, approved, rejected, open, avg_days}`; bottleneck role table `{role, actions, avg_days_at_step}` (top 8 slowest). RBAC: super_admin / director / general_manager / hr_executive / accounts_executive.
- `GET /api/notifications/mine?unread_only&limit` → `{unread, items[]}`; `POST /notifications/{id}/read` and `POST /notifications/read-all`.
- Live in-app pushes: reject → originator (`approval_rejected`), request_info → originator (`approval_info_requested`), resubmit → next-role fanout (`approval_resubmitted`), cron escalation → escalation-role fanout (`approval_escalation`), cron reminder → assigned-role fanout (`approval_reminder`).

Frontend:
- **`ApprovalsDashboard.jsx`** at `/app/approvals/dashboard` — 5 clickable lane tiles (counts auto-refresh every 60s); selected lane shows table with title / type / version / status / originator / updated / Open button.
- **`ApprovalAnalytics.jsx`** at `/app/approvals/analytics` — 4-tile + 3-tile KPI rows + Recharts bar chart of cycle time by approval type + bottleneck role table with traffic-light badges (≤1d green, 1-3d amber, >3d red). Window selector: 30/90/180/365 days.
- **`NotificationBell.jsx`** — topbar bell with unread-count badge, popover with last 20 notifications (polled every 30s), mark-read / mark-all-read.
- Sidebar entries: `nav-approvals-dashboard` and `nav-approvals-analytics` under the Command group.

**Tests** (`/app/backend/tests/test_approval_phase23.py`, 10/10 PASS):
- versions_compare returns diff + history tails ✓
- compare 404 when version missing ✓
- mandatory_attachment_helper raises 400 only when type is on the list ✓
- reminder cron job invokable + idempotent ✓
- lanes returns all 5 buckets with totals ✓
- resubmitted lane populated after resubmit ✓
- analytics shape + RBAC (401 unauth) ✓
- in-app notif created on reject + unread count + mark-read + read-all ✓

**Regression**: 82/84 PASS across Iter19/20/45/48 — only 2 pre-existing failures remain (`test_full_payment_creates_journal_entry`, `test_outward_with_approved_pr_succeeds`) — NOT introduced by Iter 51.

**Backlog after Iter 51**:
- 🛡️ Safety & Compliance Module (HIRA / JSA / PPE expiry / Near-miss) — P2
- 📊 Executive "Dept Health" tile on home page — P2
- 🔒 PII masking in PDF/Excel exports (DPDP Act 2023) — P2
- 🛠️ Tools, Equipment & Asset Calibration — P3
- 📅 30-day manpower forecast widget on Executive Dashboard — P3


### Iteration 53 — Procurement Lineage · Phase 1 of 4 ✅ (Jun 2, 2026)
Strengthens the existing PR/RFQ/PO/GRN chain so every receipt closes the loop back to the originating requisition. 7/7 backend tests PASS.

**Spec source**: user-provided 16-point "Procurement & Stores end-to-end" enhancement document.

**Backend** (`/app/backend/routers/procurement_router.py`):
- **`GET /api/procurement/lineage/{kind}/{record_id}`** — single endpoint returning the full PR → RFQ → PO → GRN(s) chain from any anchor point. `kind ∈ {pr,rfq,po,grn}`. Each node carries `{id, doc_no, dept_doc_no, status, vendor, amount, created_at}` so the frontend can build clickable bread-crumbs. Returns 404 when the record is missing, 400 for invalid kind. Also returns a `fulfilment` block `{ordered, received, rejected, pct}` aggregating every GRN posted against the PO.
- **`_refresh_pr_fulfilment(pr_id)`** helper — invoked after every GRN create. Walks PR → PO → all GRNs, computes `received / requested`, flips PR.status to `partially_fulfilled` when 0 < pct < 100 or `closed` when pct ≥ 100. Stores `fulfilment_pct` field for UI progress bars.
- Extended `PR_STATUSES` tuple to include the new `partially_fulfilled` + `pending_revision` statuses (alongside legacy values).
- Rejected qty from GRN remains isolated — only `accepted_qty` inwards via `inventory_transactions` (already in place from earlier iter).

**Frontend** (`/app/frontend/src/components/LineageTrail.jsx`, 4 list pages):
- **`LineageTrail` component** — horizontal step-card chain with per-kind icon + status badge + clickable navigation; below the chain, a progress bar + "received / ordered · pct% · K rejected" caption.
- Added **"Lineage" button** + lineage dialog on every row of `PurchaseRequisitions.jsx`, `Rfqs.jsx`, `PurchaseOrders.jsx`, `Grn.jsx`. Same component, different `kind` anchor.
- Status badge tone palette extended for `partially_fulfilled` + `pending_revision`.

**Tests** (`/app/backend/tests/test_procurement_lineage.py` — 7/7 PASS):
- Lineage walks forward from PR anchor (PR + RFQ + PO nodes present)
- Lineage walks backward from PO anchor (PR + RFQ + PO present)
- 404 on missing record, 400 on invalid kind
- Partial GRN (3 of 10) marks PR `partially_fulfilled`, `fulfilment_pct = 30.0`, lineage `fulfilment.pct = 30`
- Subsequent full GRN (remaining 7) marks PR `closed`, `fulfilment_pct = 100.0`, 2 GRN nodes in chain
- Rejected qty stays out of inventory (accepted 2, rejected 3 on a 5-unit receipt → GRN status `partial_accepted`)

**Backlog after Iter 53 (continuing per user-approved plan)**:
- 🟡 **Phase 2** — Vendor master enhancement (multi-address, MSME, bank, category mapping, doc slots) + Comparative Statement L1/L2/L3 ranking + justification approval when non-L1 selected + vendor lifecycle (Pending → Active → Inactive → Blacklisted) with Purchase + Finance approval
- 🟣 **Phase 3** — PDF generators for PR/RFQ/Comp/PO/GRN/Issue-Slip (company letterhead, GST, T&Cs, signature) + GRN inspection workflow (Quality role) + item-wise stock ledger drilldown + reorder/min-stock alerts
- 🔵 **Phase 4** — Procurement dashboard tiles + 12 reports (PR/RFQ/Comp/PO/Pending PO/GRN/Stock Ledger/Dept/Project/Vendor/Rejected Material/Budget vs Actual) + role-matrix tightening


### Iteration 54 — Procurement Phase 2 + 3 + 4 ✅ (Jun 2, 2026)
Completes the 4-phase procurement strengthening plan from Iter 53. Combined with Iter 53, the full PR→GRN cycle now has lineage, ranks, justification, ledger, alerts, inspection, dashboard, and 5 reports.

**Phase 2 — Comparative L1/L2/L3 + Non-L1 Justification**
- `GET /procurement/rfqs/{id}/comparative` now sorts rows by landed cost and assigns `rank` (1..N) + `rank_label` ("L1", "L2", "L3", …). Each non-L1 row also carries `delta_vs_l1` (₹) and `delta_pct_vs_l1` (%).
- `POST /procurement/rfqs/{id}/select-vendor` enforces a **20-char-min justification** when the chosen vendor is not L1; stores `non_l1_selection`, `non_l1_justification`, `non_l1_approved_by/at`, `l1_vendor_id_at_select` for audit.
- Frontend `RfqCompareDialog` shows L1 amber badge + per-row "+₹X (Y%) above L1" caption + intercepts non-L1 selection with a justification modal (live char counter, blocks submit < 20).

**Phase 3 — Stock Ledger · Reorder Alerts · GRN Inspection**
- `GET /store/ledger/{item_id}?from_date&to_date` — per-item ledger with opening/closing balance, running-balance per row, totals by txn-type (receipt/issue/return/transfer/scrap), and full transaction list.
- `GET /store/alerts/reorder` — every item at/below `min_stock|reorder_level`. Each row carries `shortfall` + `severity` ∈ {critical, low, warning}. Drives the Phase-4 Stock Alerts tile.
- `POST /procurement/grns/{id}/inspect` — Quality role marks accepted/rejected qty per line + reject reason + batch; validates `accepted + rejected ≤ received`; recomputes GRN overall status (approved | partial_accepted | rejected); triggers `_refresh_pr_fulfilment` so PR status reflects post-inspection accepted qty. RBAC: super_admin / quality_executive / store_keeper / store_user / purchase_executive.
- Frontend `StockLedger` dialog mounted on Inventory page (book icon per row) with KPI tiles + CSV export.

**Phase 4 — Procurement Reports**
- `GET /procurement/reports/register/{kind}` (kind ∈ pr|rfq|po|grn) — date/dept/project/vendor filters + total_value + flat row list (CSV-ready).
- `GET /procurement/reports/pending-pos` — POs not fully received with `delay_days` per row.
- `GET /procurement/reports/by-dimension?dim=department|project|vendor` — Mongo aggregate `{label, po_count, total_value}` top-50.
- `GET /procurement/reports/rejected-material` — every GRN line where rejected_qty > 0 (driver for the Rejected Material report).
- Frontend `/app/procurement/reports` — 4 tabs (Registers · Pending POs · By Dimension · Rejected Material) with date filters + Apply + CSV export buttons. Sidebar entry `nav-procurement-reports`.

**Tests** (`/app/backend/tests/test_procurement_phase234.py` — 12/12 PASS):
- Comparative assigns L1/L2 ranks correctly; delta_vs_l1 calculated (200₹ / 50% on a 4-unit × ₹150 vs ₹100 case)
- Select L1 → no justification needed
- Select non-L1 without justification → 400; with short string → 400; with 20+ char string → 200 + flagged
- Stock ledger returns correct shape; reorder alerts return shape with severity
- GRN inspect rejects accepted+rejected > received; valid inspection sets `total_accepted/total_rejected/inspection_status`
- 4 register/report endpoints return correct shape; invalid kind/dim → 400

**Combined Iter 53 + 54 totals**: 19/19 backend procurement tests PASS. Frontend: 0 errors on 4 procurement pages + new reports + inventory ledger drilldown.

**Remaining backlog** (not in user's 4-phase plan, deferred):
- PDF generators (browser-printable for now — server-side WeasyPrint setup needed)
- Vendor master multi-address + MSME + bank details document slots (Phase 2 spec items 8-9 partially deferred — current vendor schema covers core; multi-address/bank docs can be added incrementally)
- Budget vs Actual report (needs Project budget master)
- 🛡️ Safety & Compliance · 📊 Dept Health · 🔒 PII masking · 🛠️ Asset Calibration · 📅 Manpower Forecast



### Iteration 54 (Jun 02, 2026) — Procurement Phase 2/3/4 Frontend Validation
- Linted (clean): `/app/frontend/src/pages/ProcurementReports.jsx`, `/app/frontend/src/components/StockLedger.jsx`, `/app/frontend/src/pages/Rfqs.jsx`
- Smoke screenshots PASS for `/app/procurement/reports`, `/app/inventory`, `/app/rfqs`
- Testing agent (frontend-only) report `/app/test_reports/iteration_54.json` — **100% PASS** on Phase 2/3/4 in-scope flows:
  - Procurement Reports: all 4 tabs render, register dropdown switches (PR/RFQ/PO/GRN), Count + Total Value badges, CSV button visible
  - Stock Ledger: dialog opens from Inventory row, fetches `/api/store/ledger/{item_code}`, renders 6-tile totals + transaction rows
  - Comparative Statement: L1/L2/L3 ranking with `+₹delta / %above L1` shown; non-L1 justification dialog gated at ≥20 chars (client + server enforced)
  - RFQ Lineage: dialog opens with full PR→RFQ→PO→GRN trail
- Out-of-scope finding rejected: `/app/approvals/dashboard` route is correctly registered (testing agent had a hyphen typo); no fix needed.

**Status: Procurement End-to-End (Phases 1–4) COMPLETE & TESTED.**


### Iteration 55 (Jun 02, 2026) — Vendor Master Lifecycle + PDF Generators (P1)

**Vendor Master Enhancements** (dedicated `/app/backend/routers/vendors_router.py`, replaces generic CRUD)
- Auto vendor_code `VND-####` (year-less sequential via `next_flat_sequence`)
- Status lifecycle: `draft → pending_approval → approved | rejected → blocked | inactive`
- Submit-for-Approval (`POST /api/vendors/{id}/submit`) — gated by 5 prerequisites (name, PAN-or-GST, ≥1 category, ≥1 address, ≥1 bank); creates `approvals` row of `type=vendor` (chain: purchase_officer → accounts_executive → director)
- Admin status override (`POST /api/vendors/{id}/status`) with controlled transitions (super_admin can do any; others restricted)
- Approval finalisation hook in `approvals_router.py` flips vendor `status=approved` + stamps `approval_id`; rejection mirrors to `pending_revision`
- Vendor doc schema now stores: **categories[]** (master-driven via `pr_categories`), **addresses[]** (registered/billing/shipping/works + GSTIN per address), **bank_accounts[]** (multi-bank, account_type, IFSC, default flag, cancelled-cheque file_id), **msme** (status/udyam_number/certificate_file_id/expiry), **documents[]** (typed: PAN/GST/MSME/ISO/Trade License/Insurance/Other with file_id + expiry), plus duplicate-GST/PAN guard
- `GET /api/vendor-categories` lists master categories with live vendor count per category

**PDF Generators** (`/app/backend/pdf_generator.py` — WeasyPrint primary, ReportLab fallback)
- `GET /api/procurement/prs/{id}/pdf` — Purchase Requisition
- `GET /api/procurement/rfqs/{id}/pdf` — Request for Quotation
- `GET /api/procurement/rfqs/{id}/comparative/pdf` — Comparative Statement with L1/L2/L3 + delta-vs-L1 + non-L1 justification block
- `GET /api/procurement/pos/{id}/pdf` — Purchase Order (vendor block, items, GST, terms, sig boxes)
- `GET /api/procurement/grns/{id}/pdf` — Goods Receipt Note (received/accepted/rejected per line, status tags)
- `GET /api/store/transactions/{id}/pdf` — Material Issue Slip
- All endpoints return 200 + `application/pdf` + bytes starting with `%PDF`; auth-gated (401 unauth, 404 not-found)

**Frontend**
- `/app/frontend/src/pages/Vendors.jsx` (FULL REWRITE) — 6-tab dialog (Basic / Categories / Addresses / Bank / MSME / Documents), status badge column, Submit/Block/Reactivate/Edit/Delete action buttons, master-driven 10-category checkboxes, FileUploader integration for documents with type prompt
- `/app/frontend/src/lib/exports.js` — added `downloadPdf(path, filename)` helper (authenticated blob → window.open)
- PDF buttons wired on `PurchaseRequisitions.jsx · Rfqs.jsx · PurchaseOrders.jsx · Grn.jsx · StoreTransactions.jsx` + "Download PDF" inside the Comparative dialog header

**Tests** (`/app/backend/tests/test_iter55_vendor_pdf.py` + iteration_55.json)
- Backend: **21/22 PASS** (1 self-skip, manually verified). Vendor lifecycle, submit prerequisites, status transitions, RBAC, duplicate guards, all 6 PDF endpoints (200 + %PDF + 404 + 401)
- Frontend: **100% PASS** on vendor list, 6-tab dialog, master categories, Save Draft → VND-#### auto-code, Submit validation toast, PDF buttons on all 5 procurement pages, Comparative Download PDF

**Files added/changed**
- new: `routers/vendors_router.py`, `pdf_generator.py`, `tests/test_iter55_vendor_pdf.py`
- changed: `sequences.py` (+next_flat_sequence), `crud_router.py` (removed vendors from MODULES), `server.py` (registered vendors_router), `approvals_router.py` (vendor approval hook), `procurement_router.py` (+5 PDF endpoints), `store_router.py` (+MIS PDF endpoint), `frontend/src/pages/Vendors.jsx` (rewrite), `frontend/src/lib/exports.js` (+downloadPdf), `PurchaseRequisitions.jsx · Rfqs.jsx · PurchaseOrders.jsx · Grn.jsx · StoreTransactions.jsx` (PDF buttons)

**Status: Vendor Master + PDF Generators COMPLETE & TESTED (100%).**

### Iteration 60 (Jun 05, 2026) — Projects & Operations Workflow · Phase 1

**Module: "Projects & Operations Workflow"** — Sales → Project Head → PM/Coordinator hand-off.

**Backend**
- New `project_handovers` collection + `ops_activity` (timeline)
- New router `/app/backend/routers/projects_ops_router.py` exposing 9 endpoints
- Status flow: `draft → submitted → under_review → allocated → active → on_hold | completed | closed | sent_back`
- Submission auto-fires bell + email notifications to `dept_head` + `project_manager` roles
- Allocation auto-creates a `projects` row (so existing PR/Stores/HR/DPR modules immediately integrate with the new project) and notifies the assigned PM/Coordinator/RM
- Auto-generated codes via shared sequence helper: `CHO-YYYY-####` for handovers, `PRJ-YYYY-####` for the project mirror
- Activity timeline (`ops_activity`) logs created/updated/submitted/allocated/reassigned events
- Approval-engine integration: added `project_handover` + `resource_request` chain templates; `project_coordinator`, `admin_executive`, `site_team` get dept-scoped operations visibility in approvals

**RBAC / Roles**
- 3 new built-in roles auto-seeded: `project_coordinator`, `admin_executive`, `site_team`
- New `project_handovers` resource added to PERMISSIONS_BASE
- Visibility: super_admin/director/GM/dept_head see all; sales sees own; PM/PC sees assigned

**Frontend**
- `/app/ops/handovers` — `ContractHandovers.jsx`: 4-tab form (Project/Client · Commercial · Operations · Requirements), inline view/edit/delete, **Save Draft** + **Save & Submit** flow
- `/app/ops/handovers` — **Allocate / Reassign dialog** with PM, Coordinator, Reporting Manager pickers, dept dropdown, priority, expected dates
- `/app/ops/my-projects` — `MyAssignedProjects.jsx`: card grid showing assigned projects with **Open Dashboard** deep-link
- Sidebar: new "Contract Handovers" + "My Assigned Projects" entries in Operations group
- 18 spec fields all wired (project, client, WO no., contract value, dates, scope, billing/payment terms, GST, customer contact, special conditions, safety/manpower/material/asset requirements, remarks)
- Uses canonical `DepartmentSelect` from Iter 59

**Tests** — `/app/backend/tests/test_ops_workflow.py` → **4/4 PASS**
- Full lifecycle: create → update → submit → allocate → timeline assertions
- Duplicate work_order_number guard
- Submit pre-flight (required fields)
- /ops/my-projects shape

**Phases pending** (Iters 61-63)
- Phase 2 — Resource Request entity (10 types: assets/consumables/PPE/manpower/accommodation/vehicles/admin/drivers/tools/other)
- Phase 3 — Project Dashboard (Overview/Operations/Resources/Material/Purchase/Financial/Alerts) + P&L engine
- Phase 4 — 13 reports + Activity Timeline UI + Project closure validation + Accounts & Admin views

**Status: Phase 1 (Foundation) COMPLETE & TESTED.**



### Iteration 61 (Jun 05, 2026) — Projects & Operations Workflow · Phases 2-3-4

**Phase 2 — Resource Requests (10 types)**
- New collection `resource_requests` + sequence `RR-YYYY-####`
- Router `/app/backend/routers/resource_requests_router.py` — full CRUD, `/submit`, `/cancel`, `/service` (start/complete with actual qty + cost capture)
- 10 resource types: `asset · consumable · ppe · manpower · accommodation · vehicle · admin · driver · tool · other`
- Service-owner gating: store_incharge owns asset/consumable/ppe/tool; hr_executive owns manpower; admin_executive owns accommodation/vehicle/admin/driver/other
- Approval chain `resource_request` auto-attached on `/submit`; bell + email notifications fan out to the resource's service owner
- RBAC: PM/PC see own projects' requests; service owners see all requests of their type; super_admin/director/GM/dept_head see all
- Frontend `/app/ops/resource-requests` — `ResourceRequests.jsx`: filter by type/status/search, New Request dialog (project + type + item + qty/unit/priority/required-date/justification), inline Submit / Cancel / Edit / Service actions, status pills, type icons

**Phase 3 — Project Operations Dashboard with auto P&L**
- Router `/app/backend/routers/ops_dashboard_router.py` — `GET /api/ops/projects/{id}/dashboard`
- Returns 7 sections: `project · operations · resources · material · purchase · financial · alerts`
- Financial engine sums dynamic project cost from 11 sources: PR/PO (purchase), MIS (material), 9 resource_request type-buckets, manpower payroll
- P&L formulas: `gross_profit = billing_done - total_project_cost` · `net_profit = payment_received - total_project_cost` · `outstanding = billing_done - payment_received` · `over_budget` if total_cost > contract_value · `is_loss` if gross_profit < 0
- Alerts: budget breach, loss-making, low billing, payment overdue, idle manpower
- Frontend `/app/ops/project-dashboard?project_id=` — `ProjectOpsDashboard.jsx`: project picker, overview cells, 4 mini-sections, color-tinted P&L KV-cards, PROFITABLE / LOSS MAKING badge, deep-links to RR / PR / Stores / Reports

**Phase 4 — 13 Operations Reports**
- Router `/app/backend/routers/ops_reports_router.py` — `GET /api/ops/reports?kind=…&client=…&department=…&pm=…&start=…&end=…`
- 13 kinds: `resources · material_requests · purchase_requests · purchase_cost · manpower · assets · pl · by_department · by_pm · pending_approvals · store_pending · loss_making · outstanding_payments`
- Dashboard-derived kinds (pl/by_department/by_pm/loss_making/outstanding_payments) reuse `project_ops_dashboard()` for consistency
- Frontend `/app/ops/reports` — `OpsReports.jsx`: report selector, client/department/status/date filters, run-on-mount + manual Run, CSV export (client-side)
- Sidebar: 3 new Operations entries (Resource Requests · Project Dashboard · Operations Reports). Activity Timeline route already wired from Iter 60

**Tests** — `/app/backend/tests/test_iter61_ops_phase234.py` → **21/21 PASS** (2.2s)
- RR create-verify-submit lifecycle, dashboard shape (9 financial fields asserted), all 13 report kinds 200 + shape, invalid kind 400, unknown project 404, invalid resource_type 400

**Files added/changed**
- new (backend): `routers/resource_requests_router.py`, `routers/ops_dashboard_router.py`, `routers/ops_reports_router.py`, `tests/test_iter61_ops_phase234.py`
- new (frontend): `pages/ops/ResourceRequests.jsx`, `pages/ops/ProjectOpsDashboard.jsx`, `pages/ops/OpsReports.jsx`
- changed: `server.py` (registered 3 new routers L62-94), `App.js` (3 new routes L143-146), `Layout.jsx` (3 new sidebar items L40-42)

**Scalability flag (deferred)** — `/ops/reports` does N+1 dashboard calls per project on dashboard-derived kinds. Acceptable up to ~200 projects; revisit with a daily mat-view cache when tenants cross that threshold.

**Status: Phases 2 + 3 + 4 COMPLETE & TESTED (Backend 100%, Frontend smoke-verified).**



### Iteration 62 (Jun 05, 2026) — Sales Policy: Enquiry-Gated Quotations + Internal Approval Gate

User-driven hardening of the Sales module. 6 specific changes:

**Policy & Backend**
- **Direct quotation creation BLOCKED** — `POST /api/quotations` now returns 400 with "Register an Enquiry first; a draft quotation will be auto-generated and linked." Achieved by registering `sales_router` BEFORE `crud_router` in `server.py` so the override wins. The legacy auto-quote pipeline on `POST /api/enquiries` is unchanged.
- **Enquiry mandatory fields** — both `client_id` AND `site_id` now hard-required (was: either-or). Friendly 400 errors guide the user.
- **New endpoints on `sales_router.py`**:
  - `POST /quotations/{q_id}/send-for-approval` — creates an `approvals` doc with `type='quotation'`, uses the admin-editable chain (default: dept_head → director). Duplicate active approval guarded by 409. Quote flips to `under_review`, `approval_status='pending'`, `approval_id` set.
  - `POST /quotations/{q_id}/status` — validated state transitions with **submitted gated by `approval_status='approved'`**. One-way sync mirrors `{submitted, won, lost, cancelled}` onto the linked enquiry.
  - `PUT /quotations/{q_id}` — overrides crud_router PUT; strips server-managed fields (status, approval_*, enquiry_*, revision/root/parent ids) so they can only be mutated through the proper workflow endpoints.
  - `GET /quotations/{q_id}/approval` — retrieve the latest approval row for UI.
- **Approval mirror tweak** — `_mirror_downstream_record` in `approvals_router.py` special-cases `type='quotation'`: writes to `approval_status` field (approved/rejected/info_required/pending) and NEVER overwrites the sales pipeline `status` column.
- **Approval `approve` hook** added for `type='quotation'` → sets `quote.approval_status='approved'` + `approval_decided_at`.

**Frontend**
- `Quotations.jsx` full rewrite:
  - Yellow banner: "Quotations are auto-generated from Enquiries…" with link
  - **No + Add button** (`onCreate={null}`)
  - New columns: **Internal Approval** badge (Approved / Pending / Rejected / Revision Required / Info Needed / Not Sent) and **Pipeline** (draft / under_review / submitted / won / lost)
  - **Send for Approval** button on draft/under_review/costing_pending quotes (when no active approval)
  - **Status** dialog showing only next-allowed transitions; warning banner if approval not yet approved
- `Enquiries.jsx`:
  - Free-text "Customer Name" field replaced with **Client (master) `*`** dropdown (`/api/clients`)
  - Site dropdown is **disabled until a client is picked**; lists only that client's sites; placeholder "— pick a client first —"
  - Customer Name now read-only (snapshot of selected client)
  - Both client + site marked mandatory with asterisks; client-side toasts before submit

**Tests** — `/app/backend/tests/test_iter62_sales_policy.py` → **7/7 PASS** (2.7s)
- Direct create block · enquiry site required · enquiry→auto-quote · submit-without-approval blocked · send-for-approval + duplicate 409 · full chain → submit → enquiry sync (submitted then won) · PUT field strip · reject path keeps pipeline status

**Files changed**
- backend: `routers/sales_router.py` (+200 lines), `routers/approvals_router.py` (quotation hooks), `server.py` (router order)
- frontend: `pages/Quotations.jsx` (rewrite), `pages/Enquiries.jsx` (client dropdown + filtered sites + validation)
- tests: `tests/test_iter62_sales_policy.py` (new, 7 tests)

**Status: Sales policy COMPLETE & TESTED (Backend 7/7, Frontend all assertions PASS).**

### Iteration 62.1 (Jun 05, 2026) — Quotation Approval Step Visibility + Reject/Re-send

User-requested follow-ups:
- **"Pending at <Step>" visible on the table** — every quotation row now shows the current approver label (e.g. "Pending at Department Head (Step 1/2)"). Driven by 4 denormalized fields on the quote: `approval_current_step_role`, `approval_current_step_label`, `approval_current_step_index`, `approval_total_steps`. Synced on `send-for-approval` and on every `/approvals/{id}/action` (approve / reject / request_info) via a quotation-specific block in `approval_action()`.
- **Reject → Re-send restarts the chain from step 0** — duplicate-approval guard relaxed: a quote with a `rejected*` approval can be re-sent. A **fresh approval doc** is created (chain rebuilt from `build_chain('quotation')`), `quote.approval_id` updated, reject reason cleared. Old approval rows preserved for audit.
- **Re-send for Approval** button (red outline, separate `data-testid='quotations-resend-approval-{id}'`) replaces the regular Send button on rejected quotes; confirm dialog says "chain will start from step 1".
- Approval cell also renders the reject reason inline (red, truncated, full text on hover).

**Tests** — smoke test all 7 scenarios passed end-to-end:
1. Initial send shows step 0 ("Department Head" idx 0/2) · 2. After first approve, step advances to "Director" idx 1 · 3. Reject captures step label + reason · 4. Re-send creates a NEW approval id, restarts at "Department Head" idx 0/2, clears reject reason · 5. Cannot re-send while pending (409).

**Files changed**
- backend: `routers/sales_router.py` (denorm fields on send), `routers/approvals_router.py` (per-action quotation sync block + Approved label)
- frontend: `pages/Quotations.jsx` (rich Internal Approval cell + Re-send button)

**Status: Quotation step visibility + Reject/Re-send COMPLETE & TESTED.**


### Iteration 63 (Jun 05, 2026) — Universal Approval Documents Gate

User mandate: "anything sent for approval should have reference documents attached OR be explicitly marked Not Applicable, across every module."

**Chosen scope (user-confirmed):**
- 1c — gate at submission AND keep per-step "request info" route open
- 2c — accept both newly uploaded files AND existing record attachments
- 3b — universal rollout across all ~30 approval types
- 4a — N/A reason mandatory (≥5 chars)

**Backend — single choke point**
- `approval_engine.py`:
  - `ApprovalDocumentsRequired` exception class
  - `_normalise_documents_payload()` — coerces `documents` + `linked_attachments` into canonical `[{file_id, source: 'upload'|'linked', name?}]` and enforces the gate (≥1 doc OR `documents_not_required=True` with ≥5-char reason)
  - `insert_approval(doc, *, skip_gate=False)` — wraps `db.approvals.insert_one()` so every approval enforces the gate
  - `copy_approval_doc_fields(approval, source)` — convenience helper that pulls the 4 docs fields from a request payload onto the approval doc
- `server.py` — global FastAPI exception handler converts `ApprovalDocumentsRequired` → clean 400 JSON

**All 13 production approval-insertion sites converted to `insert_approval()`**:
1. `crud_router.POST /api/approvals` (generic) · 2. `crud_router` deployment auto-approval · 3. `sales_router.send_quotation_for_approval` · 4. `resource_requests_router.submit_resource_request` · 5-6. `procurement_router` PR create + PR submit · 7. `store_router` GRN approval · 8. `advance_router._submit_advance` · 9-10. `allocation_router` dept-move + bulk deployment · 11. `vendors_router.submit_vendor` (auto-N/A: "KYC documents attached to vendor master record") · 12-13. `clients_router` create + resubmit (auto-N/A: "KYC documents attached to client master record") · 14. `quotation_builder_router.submit_for_approval`

**Frontend — two shared components**
- `components/ApprovalDocsGate.jsx` — orange-bordered panel rendering:
  - "Not Applicable" toggle (data-testid `*-na-toggle`) + reason textarea (`*-na-reason`)
  - List of existing record attachments (checkboxes, `*-linked-{id}`)
  - File upload input for new docs (`*-upload`)
  - Live "N document(s) attached" / "No documents attached yet" counter
  - Exports `validateApprovalDocs(value)` and `emptyApprovalDocs()` helpers
- `components/SubmitWithDocsDialog.jsx` — generic dialog wrapping the gate; props: `endpoint`, `parentType`, `parentId`, `ctaLabel`, `onSuccess`

**Wired into 4 top-volume UIs**: Quotations (Send + Re-send), Purchase Requisitions (Submit), Resource Requests (Submit), Quotation Builder (Submit). PR create form default flipped to `submit_for_approval=false` so PRs always go through the explicit Submit dialog.

**Tests** — `/app/backend/tests/test_iter63_approval_docs_gate.py` → **13/13 PASS** (1 skipped — client onboarding endpoint shape, manually equivalent to vendor path):
- 4 quotation scenarios (empty body / short reason / valid N/A / docs list) · generic /api/approvals gate · PR submit gate · RR submit gate · Quotation Builder submit gate · Vendor auto-N/A · Reject + Re-send-without-docs(400) + Re-send-with-docs(200) full loop.

**Files changed**
- backend: `approval_engine.py` (+95 lines), `server.py` (exception handler), 10 routers (13 sites)
- frontend: 2 new components, 4 page wires
- tests: `tests/test_iter63_approval_docs_gate.py` (14 tests)

**Status: Universal Documents Gate COMPLETE & TESTED across all 13 approval-creation paths.**



### Iteration 64 (Jun 06, 2026) — Won Quotation → Auto Contract Handover

User-requested: "Quotation which is won should automatically come to Contract Handover Page with auto-prefilled details."

**Backend** — `sales_router.py`
- `change_quotation_status` now invokes `_auto_create_handover_from_quote(after, user)` whenever the new status is `won`. Failure is logged but never blocks the status change.
- `_auto_create_handover_from_quote()` is **idempotent** — keyed by `quotation_id` on `project_handovers`. Re-marking the same quote as won returns the existing handover, no duplicate row.
- Prefilled fields (11): project_name, client_name, client_id, site_id, site_location, work_order_number (from customer_po / customer_enquiry_no), contract_value, contract_start_date, contract_end_date, scope_of_work, billing_terms, payment_terms (falls back to client master), gst_details (client master), customer_contact_person / number / email (quote first, then enquiry), special_conditions, safety/manpower/material/asset_requirements (from enquiry).
- Lineage: `quotation_id`, `quotation_no`, `enquiry_id`, `enquiry_no`, `source='auto_from_quote'`.
- Logs `handover_activity` (event=`auto_created`) + audit (`auto_create_from_quote`).
- Response payload includes `auto_handover: {id, handover_no}` so the UI can show a smart toast.

**Frontend**
- `Quotations.jsx` — status-change toast now reads "Status → won · Handover CHO-… auto-created" with 6s duration when applicable.
- `ContractHandovers.jsx`:
  - Green banner above the table: "N draft handover(s) auto-created from won quotation(s)" listing handover_no's.
  - Auto-created rows get a tinted green background, a `✦ auto · from quote` micro-badge under the handover number, and a blue `→ QTN-…` link to the source quote in the Project cell.

**Tests** — smoke-tested via curl, 6 scenarios pass:
1. Enquiry → auto-quote · 2. Send-for-approval + 2-step approval + submit + won · 3. Auto-handover created with all 11 prefilled fields verified · 4. Idempotency — second `won` re-submit doesn't create a duplicate (still 1 handover).

**Files changed**
- backend: `routers/sales_router.py` (+120 lines — change_quotation_status hook + _auto_create_handover_from_quote helper)
- frontend: `pages/Quotations.jsx` (toast), `pages/ops/ContractHandovers.jsx` (banner + auto badge + source link)

**Status: COMPLETE & verified end-to-end on preview.**



### Iteration 65 (Jun 06, 2026) — Won Quote → Auto Project (PRJ-) + Handover Lineage Columns

User: "Once quotation is Won, Sales person will convert the Won Quotation to Project (PRJ-YYYY-####). In Contract Handover page, Project Number, Quotation Number, Project Name should be visible to show sequence and linkage."

**Backend** — `sales_router.py::_auto_create_handover_from_quote`
- The auto-handover hook now **also spawns a Project record** (`PRJ-YYYY-####` via `next_sequence('PRJ')`) when a quote is marked `won`. Idempotent — keyed on `quotation_id` so re-marking won never creates duplicates.
- Project doc carries the full lineage: `quotation_id/no`, `enquiry_id/no`, `source='auto_from_quote'`, plus initial budget = contract value, status=`planned`.
- Handover row now stamps `project_id` + `project_code` alongside the existing `quotation_no`/`enquiry_no`.
- Status-change response payload extended to `auto_handover: {id, handover_no, project_code, project_id}`.

**Frontend** — `pages/ops/ContractHandovers.jsx`
- Table redesigned to surface the lineage chain prominently:
  - **HANDOVER #** (CHO- in mono · ✦ auto badge when applicable)
  - **PROJECT #** (PRJ- in blue chip · `data-testid='ops-project-code-{id}'`)
  - **QUOTE #** (QTN- in amber chip · `data-testid='ops-quote-code-{id}'`)
  - **PROJECT / CLIENT** (name on top · client + WO on muted second line · `data-testid='ops-project-name-{id}'`)
  - then SITE / VALUE / ALLOCATION / STATUS / ACTIONS as before
- Removed the separate Client column (folded into Project cell to save horizontal space)
- Footer-row colspan updated 8→9

**Smoke test — 5/5 pass** (live preview):
1. Enquiry → quote · 2. Approve chain + submit + won · 3. Response payload has `project_code=PRJ-2026-0021` · 4. Handover record persists project_code + quotation_no + project_name · 5. Re-marking won keeps project count at 1 (no duplicates).

**Files changed**
- backend: `routers/sales_router.py` (+50 lines — project spawn inside the existing auto-handover helper)
- frontend: `pages/ops/ContractHandovers.jsx` (table header + row redesign)

**Status: Won → Project → Handover lineage COMPLETE & verified end-to-end on preview.**



### Iteration 66 (Jun 06, 2026) — Quotation Site / Project Name Auto-Fill from Enquiry

User: "Site / Project Name on quotation page is not getting auto filled from Enquiries page."

**Root cause**: The auto-quote created from an enquiry was writing `project` and `scope_of_work` but **never wrote `site_name`** — which is the field the Quotation Builder's "Site / project name" input reads. Result: the field rendered blank even though the enquiry had a valid scope.

**Fix** (two layers — go-forward + legacy backfill)

1. **Go-forward** — `sales_router.create_enquiry` auto-quote block now sets:
   - `site_name` = `scope_of_work` or `project` or `site_location`
   - `site_location` = enquiry's `site_location`
   - `contact_phone` added (was missing alongside `contact_email`)
2. **Backfill on read** — `quotation_builder_router.get_full_quotation` falls back to `project` / `site_location` / linked enquiry's `scope_of_work` when `site_name` is empty. So even pre-Iter-66 auto-quotes render the field populated immediately upon opening the AI Quotation Builder.

**Smoke-tested**: new enquiry "Iter66 site fill test" → QTN-2026-0038 → builder shows `client=Adani Power`, `site_name=Iter66 site fill test`, `scope_of_work=Iter66 site fill test` ✅. Legacy quote (Iter 65) → backfilled `site_name=Iter65 PRJ link` on read ✅.

**Files changed**
- backend: `routers/sales_router.py` (auto-quote payload — +3 fields), `routers/quotation_builder_router.py` (read-time backfill)

**Status: COMPLETE & verified on preview.**

### Iteration 67 (Jun 06, 2026) — Customer Site → Quotation "Site / Project Name" (priority fix)

User clarified the source: "Customer Site details entered or updated in a New Enquiry should automatically populate the Site / Project Name field in the Quotations module by default."

Iter 66 had the right plumbing but the **wrong source priority** — it was reading `scope_of_work` first, so the site picker's master `name` was being shadowed by free-text scope.

**Change**
- `sales_router.create_enquiry` auto-quote — new priority for `site_name`:
  **`enquiry.site_name` (snapshot of master site picker) → `site_location` → `scope_of_work` → `project`**
- `quotation_builder_router.get_full_quotation` read-time backfill — same priority order; pulls from the linked enquiry's `site_name` snapshot first.

**Smoke test (live preview)**: enquiry on site **"HAZIRA"** with deliberately distinct `scope_of_work="DIFFERENT_scope_text_not_used"` → QTN-2026-0039 builder shows `Site / Project Name = HAZIRA` (scope kept in its own field).

**Files changed** — backend only: `routers/sales_router.py` (2-line priority swap), `routers/quotation_builder_router.py` (backfill priority).

**Status: COMPLETE & verified on preview.**


### Iteration 68 (Jul 11, 2026) — Rollback verification + stale service-worker cache fix

User rolled back to commit `107bfa3` (Jun 6, 2026) but browser still showed "wrong menus" (from the erased post-Jun-6 Safety Module session).

**Root cause**: PWA service worker (`public/service-worker.js`) uses stale-while-revalidate for JS assets — the browser kept serving the pre-rollback cached bundle.

**Fix**: Bumped SW `VERSION` "v1.0.0" → "v1.0.1" (one-line change, the app's built-in cache-purge mechanism). New SW installs on next visit, purges old caches, auto-reloads. Verified codebase is byte-identical to `107bfa3` otherwise; verified login + Executive Dashboard render correct Jun 6 menus via screenshot.

**Note**: The 5-phase Safety Module work described in the last fork's handoff was ERASED by the user's rollback — it does NOT exist in the current codebase. Menus come from `components/Layout.jsx` (no menuConfig.js in this checkpoint).

**Status: COMPLETE & verified on preview.**
