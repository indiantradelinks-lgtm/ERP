# APPLICATION ASSESSMENT REPORT — WorkSite Command ERP
## INDIAN TRADE LINKS · Prepared for Noventiq Global AI Solutions

**Prepared:** 25 November 2026
**Source:** Direct inspection of the live source code, the development/preview environment and the application's own configuration APIs.
**Scope note:** Production infrastructure internals are managed by the Emergent platform and are not visible from the application; such items are marked **TO BE CONFIRMED**.
**No passwords, API keys, tokens or secret values are contained in this document.** Secret *names* are listed so the receiving team knows what must be provisioned; the values must be obtained from the ERP administrator.

---

## 1. FRONTEND & BACKEND REPOSITORY DETAILS AND ACCESS REQUIREMENTS

| Item | Finding | Status |
|---|---|---|
| Repository model | **Single mono-repo** containing both tiers: `/app/frontend` (React SPA) and `/app/backend` (FastAPI). There is no separate frontend/backend repository. | Verified |
| Version control | Git is initialised in the workspace — branch `main`, **330 commits**, latest commit `242a068` dated 19 Nov 2026. | Verified |
| GitHub remote | **No GitHub remote is configured** (`git remote -v` returns nothing). The code currently lives inside the Emergent workspace, which commits a checkpoint after every change. | Verified |
| How to obtain the code on GitHub | The ERP owner can use the Emergent platform's **"Save to GitHub"** action, which creates/pushes the mono-repo into a GitHub organisation of the company's choice. Until that is done there is no repository URL to share. | Action required by ERP owner |
| Repository access requirements | After the push: a GitHub organisation/repo owned by INDIAN TRADE LINKS, with collaborator (read) access granted to the Noventiq assessment team. Branch protection / PR policy to be agreed. | TO BE CONFIRMED |
| Code size | Backend: 133 router modules + ~45 service modules. Frontend: 245 page components, 242 routes. | Verified |
| Excluded from version control | `node_modules/`, build output, `.env` files (secrets are injected from the platform) — see `/app/.gitignore`. | Verified |
| Existing in-repo documentation | `ARCHITECTURE.md`, `AZURE_ASSESSMENT.md`, `CHANGES.md`, `memory/PRD.md` (living requirements + change log), `memory/test_credentials.md`. | Verified |

**Requires developer/administrator action:** creating the GitHub repository (via "Save to GitHub"), granting Noventiq read access, and deciding the branching/CI policy.

---

## 2. DEVELOPMENT MONGODB DATABASE — DETAILS AND ACCESS REQUIREMENTS

| Item | Finding | Status |
|---|---|---|
| Engine / version | MongoDB **7.0.45**, accessed with the async **Motor 3.3.1 / PyMongo 4.5.0** driver | Verified |
| Topology (development) | **Standalone** single node, running inside the development pod under supervisord (`mongod --bind_ip_all`) | Verified |
| Connection | Supplied to the application only through the `MONGO_URL` environment variable; the development instance is `mongodb://localhost:27017` — **pod-local, not reachable from outside the container** | Verified |
| Database name | `erp_database` (env var `DB_NAME`) | Verified |
| Authentication | The development instance runs without credentials because it is bound to the pod only. Production credentials live in the platform Secrets store. | Verified / production TO BE CONFIRMED |
| Size (development, measured 25 Nov 2026) | **384 collections**, 38,028 documents, data 24.9 MB, storage 18.7 MB, indexes 25.8 MB across **803 indexes** | Verified |
| Representative record volumes (dev) | users 25 · employees 55 · projects 28 · purchase_orders 28 · vendor_bills 33 · ra_bills 14 · attendance 448 · files 183 · approvals 391 · journal_entries 244 | Verified |
| Production database size & growth | Not visible from the application. Production attendance alone holds ~134,000 rows and ~1,167 employees, so production is materially larger than development. | TO BE CONFIRMED (platform/administrator) |
| Access requirements for an external team | A read-only database user + a network path (connection string from the platform Secrets tab, or a `mongodump` archive). Neither can be issued from inside the application. | Requires administrator access |
| Available export | A verified archive dump exists in-repo: `/app/backups/erp_database-20261105-101030.archive.gz` (4.8 MB) with a `files-manifest.json`. | Verified |

---

## 3. ERP TEST USER ACCOUNTS, ROLES AND PERMISSIONS

### 3.1 Role catalogue (live, from `/api/admin/role-catalog` — 23 roles)

| Role key | Label | Type | Users (dev) |
|---|---|---|---|
| super_admin | Super Admin | built-in | 1 |
| director | Director | built-in | 1 |
| general_manager | General Manager | built-in | 1 |
| dept_head | Department Head | built-in | 2 |
| project_manager | Project Manager | built-in | 3 |
| project_coordinator | Project Coordinator | built-in | 0 |
| site_engineer | Site Engineer | built-in | 1 |
| site_team | Site Team | built-in | 0 |
| supervisor | Data Entry Operator | built-in | 2 |
| store_incharge | Store In-charge | built-in | 1 |
| accounts_executive | Accounts Executive | built-in | 1 |
| hr_executive | HR Executive | built-in | 4 |
| admin_executive | Admin Executive | built-in | 0 |
| safety_officer | Safety Officer | built-in | 1 |
| purchase_officer | Purchase Officer | built-in | 1 |
| sales_executive | Sales Executive | built-in | 1 |
| billing_executive | Billing Executive | built-in | 0 |
| client_rep | Client Representative | built-in | 0 |
| vendor | Vendor (External) | built-in | 2 |
| manager_o_p | Manager O P | custom | 1 |
| manager_pnv | Manager PNV | custom | 1 |
| manager_log | Manager LOG | custom | 1 |
| pro_coor | Project CoorDinator | custom | 0 |

### 3.2 Permission model

- **Resource × action matrix**: **92 resources** and **276 resource-action pairs** are governed (live values from `/api/admin/role-register`). Code defaults live in `backend/rbac.py`; Super Admin can override any pair from **Admin → Role Register** and the override is stored in the database.
- **Server-side enforcement**: every route is wrapped in `require_permission(resource, action)`; `super_admin` bypasses the matrix. The frontend `RouteGuard` mirrors the same permissions, so the UI hides what the API would refuse.
- **Row-level scoping** (in addition to the matrix):
  - *Global visibility*: super_admin, director, general_manager, hr_executive
  - *Department-scoped*: dept_head (only their department's records)
  - *Project-scoped*: project_manager, site_engineer, supervisor, safety_officer, store_incharge (only projects they are deployed/allocated to)
- **Approval chains**: configurable per workflow (e.g. Project Manager → Dept Head → GM → Director), maintained in the Approvals Matrix; certain roles are allowed to bypass specific chains.
- **Other controls**: PII masking in exports for non-privileged roles, admin impersonation (audited), and a full audit log (who / when / before / after / IP).

### 3.3 Test accounts

- A maintained register of one test account per role exists at **`/app/memory/test_credentials.md`** (emails, roles, department, modules each role sees, plus a verification walkthrough).
- The development database currently contains **25 user accounts spanning 17 distinct roles**.
- **Passwords are deliberately not reproduced in this report.** The ERP administrator (Super Admin) should either share that register directly or create dedicated assessment logins from **Admin → Users → Add User**, which is the recommended approach so the accounts can be revoked afterwards.
- Passwords are stored as **bcrypt hashes**; no plaintext password exists anywhere in the system, and none can be recovered — only reset.

---

## 4. LOCAL ENVIRONMENT CONFIGURATION AND SETUP REQUIREMENTS

### 4.1 Runtime prerequisites (as measured in the working environment)

| Component | Version in use |
|---|---|
| Python | 3.11.18 |
| Node.js | 24.19.2 (React 19 / CRA 5 tool-chain) |
| Yarn | 1.22.22 (**yarn only** — npm is not used, lockfile is `yarn.lock`) |
| MongoDB | 7.0.45 (local standalone is sufficient for development) |
| Process manager | supervisord (backend, frontend, mongod) |
| OS base | Debian 12 (bookworm) container image |

### 4.2 Install & run

```
# backend
cd backend && pip install -r requirements.txt            # 170+ pinned packages
uvicorn server:app --host 0.0.0.0 --port 8001 --reload   # supervisord does this in the pod

# frontend
cd frontend && yarn install
yarn start      # CRACO dev server on port 3000
yarn build      # production bundle
yarn lint       # eslint (react, hooks, import, jsx-a11y)
```

### 4.3 Configuration contract (must be respected on any host)

- `frontend/.env` → `REACT_APP_BACKEND_URL` (the public base URL; the app always calls `${REACT_APP_BACKEND_URL}/api/...`), `WDS_SOCKET_PORT`, `ENABLE_HEALTH_CHECK`.
- `backend/.env` → `MONGO_URL`, `DB_NAME`, `CORS_ORIGINS`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `FRONTEND_URL`, `APP_NAME`, `EMERGENT_LLM_KEY`, `RESEND_API_KEY`, `SENDER_EMAIL`, `M365_SMTP_HOST`, `M365_SMTP_PORT`, `M365_SMTP_SHARED_USERNAME`, `M365_SMTP_SHARED_PASSWORD`, `M365_SMTP_SHARED_DISPLAY_NAME`, `M365_FERNET_KEY`, `WEBHOOK_CRON_SECRET`.
  *(names only — values are held in the platform Secrets store / administrator custody)*
- **Routing rule:** every backend route is prefixed `/api`; the ingress sends `/api/*` to port 8001 and everything else to port 3000. A local reverse proxy must reproduce this.
- No value is hard-coded in the source: all URLs, ports, database names and credentials come from environment variables, and the app fails fast if one is missing.
- Native libraries required by the PDF engine (WeasyPrint/ReportLab: cairo, pango, gdk-pixbuf) and `pymupdf` are part of the container base image and must be installed on any other host.

**Requires administrator access:** the actual secret values (JWT secret, Microsoft 365 app passwords, Fernet key, LLM key, cron webhook secret) and the production `MONGO_URL`.

---

## 5. CURRENT HOSTING, SERVER AND DEPLOYMENT DETAILS

| Item | Finding | Status |
|---|---|---|
| Hosting platform | **Emergent managed platform** — containerised Kubernetes pods | Verified |
| Production URL | `https://worksite-command.emergent.host` (TLS terminated at ingress) | Verified |
| Development/preview URL | `https://worksite-command.preview.emergentagent.com` | Verified |
| Environments | Two: **Preview** (hot-reload development pod) and **Production** (promoted only by an explicit *Deploy/Redeploy*) | Verified |
| Application servers | Backend: uvicorn, 1 worker, `0.0.0.0:8001`. Frontend: static React build served on `:3000`. Both under supervisord with auto-restart. | Verified |
| Routing | Kubernetes ingress, path-based: `/api/*` → backend 8001, `/*` → frontend 3000. CORS governed by `CORS_ORIGINS`. | Verified |
| Current resource envelope (dev pod, live reading) | CPU quota 2 cores (0.2 % in use), memory limit 8,192 MB with backend RSS 250.8 MB (3.1 %), event-loop lag 0.7 ms avg, disk `/app` 2.85 GB of 10.46 GB (27 %) | Verified |
| Production pod size / replica count / autoscaling | Not visible from the application. **Note:** the production backend was previously OOM-killed on the 512 MB tier, so the production memory tier should be reviewed. | TO BE CONFIRMED (platform) |
| Release process | Platform "Deploy"; environment variables maintained in the platform **Secrets** tab; code checkpoints allow rollback to any earlier build. No external CI/CD pipeline is configured. | Verified |
| Scheduled/cron infrastructure | In-process APScheduler (21 jobs) plus one platform-managed cron declared in `.emergent/crons.yml` (`monthly-service-payments`, 02:30 IST on the 1st, Asia/Kolkata) | Verified |
| Monitoring | Built-in `/api/admin/system-health` (memory, CPU, event-loop lag, disk, DB size, request p50/p95, 5xx count, history sampled every 5 min) and an admin System Health dashboard. No external APM. | Verified |
| Custom domain / DNS / VPN | Emergent subdomains in use; `indiantradelinks.in` is used only for email sender identities. No VPN, no IP allow-listing, no private link. | Verified |

---

## 6. ERP TECHNICAL ARCHITECTURE, STACK, API, INTEGRATIONS, DATABASE, BACKUP & STORAGE

### 6.1 Architecture

Three-tier SPA: **React browser client → FastAPI REST API (`/api`) → MongoDB**, with an in-process scheduler for recurring work and four external services (Microsoft 365 SMTP, OneDrive via Microsoft Graph, Emergent object storage, Emergent LLM). Authoritative diagram and module map: `/app/ARCHITECTURE.md`.

### 6.2 Technology stack

| Layer | Technology |
|---|---|
| Frontend | React 19, CRA 5 + CRACO, Tailwind CSS, Shadcn/UI (Radix), Axios, lucide-react, sonner, recharts, react-leaflet, react-hook-form + zod, react-router 7 |
| Backend | FastAPI 0.110, Python 3.11, Pydantic v2, Motor 3.3 (async MongoDB), uvicorn, APScheduler 3.11 |
| Documents | ReportLab 4.5 + WeasyPrint 68 (PDF), openpyxl 3.1 (Excel), python-docx/docxtpl, pymupdf (PDF text extraction) |
| Security | PyJWT / python-jose, passlib + bcrypt, cryptography (Fernet for mailbox app-passwords) |
| AI | `emergentintegrations` + litellm / openai / google-genai (AI quotation builder, challan OCR extraction, bulk beneficiary parsing) |
| Email | Microsoft 365 SMTP (aiosmtplib), Resend SDK (secondary) |
| Cloud/Graph | msal + boto3 (object storage), Microsoft Graph REST for OneDrive |

### 6.3 API documentation

- **Live, auto-generated OpenAPI 3** — `GET /openapi.json`, interactive Swagger UI at `/docs`, ReDoc at `/redoc` (served by the backend; no separate hand-written API document exists).
- Current surface: **1,332 paths / 1,693 operations**, grouped into **127 functional tags** (hr, procurement, service-workflow, projects-ops, accounts, vendor billing, logistics, store-inventory, safety, sales, approvals, exports, admin…).
- Conventions: all paths prefixed `/api`; JSON only; UUID *string* identifiers (MongoDB ObjectIds are never exposed); JWT in httpOnly cookies with Bearer fallback; list endpoints support shared pagination/filter/export parameters.

### 6.4 Integrations

| Integration | Purpose | Credential type |
|---|---|---|
| Microsoft 365 SMTP (`smtp.office365.com:587`) | Payslips, billing/approval reminders, system notifications from `noreply@indiantradelinks.in`; per-user mailboxes with Fernet-encrypted app passwords | SMTP app passwords + Fernet key |
| OneDrive (Microsoft Graph) | Central document mirror (push queue every 2 min) and nightly database backup; storage-audit and hash verification endpoints | Graph app registration / token cache |
| Emergent object storage | Primary file store behind `/api/uploads` and `/api/files/{id}/download` | Platform-managed |
| Emergent LLM (universal key) | AI quotation drafting, delivery-challan OCR extraction, bulk beneficiary parsing | `EMERGENT_LLM_KEY` |
| Google Sheets (public link read) | Monthly site attendance sheet synchronisation (unlimited connections, 15-minute sync) | Public "anyone with the link" sheets |
| Resend | Secondary/legacy transactional email | `RESEND_API_KEY` |
| Stripe SDK | Present in dependencies; **not wired into any live workflow** | n/a |

### 6.5 Database structure

- Document store, **384 collections**, **803 indexes**, UUID string primary keys (`id`), ISO-8601 UTC timestamps, soft relationships by code/id rather than joins (`$lookup` only in reports).
- Functional groupings: *Identity* (users, role_register, audit_log) · *HR* (employees, attendance, payroll_master, payslips, employee_advances) · *Sales* (enquiries, quotations, orders, clients) · *Projects* (project_handovers, projects, project_requests, dprs, measurements, ra_bills) · *Procurement* (purchase_requisitions, rfqs, purchase_orders, grn, vendors, vendor_bills) · *Finance* (client_invoices, payment_verifications, journal_entries, chart_of_accounts) · *Store & Logistics* (inventory, stock_transactions, challans, dispatches) · *Safety* (hira, jsa, incidents, permits, trainings) · *Platform* (files, approvals, notifications, email_outbox, onedrive_queue, system_health_samples).
- Index strategy is centralised in `backend/indexes.py` + `perf_indexes.py` and (re)applied at startup; uniqueness is enforced where business rules demand it (e.g. `payroll_master` by employee, attendance by employee+date).

### 6.6 Backup & storage

| Item | Finding | Status |
|---|---|---|
| Database backup | Application-level nightly `mongodump` pushed to OneDrive at **18:30 IST** (APScheduler job `onedrive_backup`); on-demand backup available at `/api/admin/onedrive/backup-now`; backup register at `/api/admin/onedrive/backups` | Configured (needs an active OneDrive connection) |
| Latest in-repo archive | `/app/backups/erp_database-20261105-101030.archive.gz` (4.8 MB) + `files-manifest.json` | Verified |
| Document storage | Primary: Emergent object storage via `/api/uploads`. Mirror: OneDrive push queue — current dev queue 187 items (28 pushed, 112 pending, 0 failed). Hash verification and a storage audit screen exist before any file is served from OneDrive. | Verified |
| Retention | **No retention or auto-purge policy** — documents and backups are kept indefinitely; a 20:30 housekeeping job only trims transient/system data under explicit retention settings | Verified — business policy TO BE CONFIRMED |
| Restore procedure | Manual (`mongorestore` from the archive); no automated restore tooling or tested runbook | Gap — TO BE CONFIRMED |
| RPO / RTO / SLA | Not formally defined; effective application-level RPO ≈ 24 h from the nightly backup | TO BE CONFIRMED with business |
| Platform-level snapshots | Emergent keeps code checkpoints with rollback; platform database snapshot policy is not visible to the application | TO BE CONFIRMED (platform) |

---

## 7. ITEMS THAT CANNOT BE EXTRACTED FROM THE APPLICATION

These require the ERP owner, the platform administrator or Emergent support:

1. **GitHub repository URL and access** — no remote is configured yet; the repo must first be pushed via "Save to GitHub".
2. **Production database connection string, credentials, size, growth rate and topology** (replica set vs standalone).
3. **Production pod specification, replica count and autoscaling policy**; the memory tier should be reviewed after the earlier OOM events.
4. **All secret values** (JWT secret, Microsoft 365 app passwords, Fernet key, LLM key, cron webhook secret, Resend key) — names are listed above; values are never printed by the application and are not in this report.
5. **Test-account passwords** — only the Super Admin can share the register or issue fresh assessment logins.
6. **Platform-level backup/snapshot policy, SLA, RPO/RTO targets and backup retention** — contractual/business decisions, not application settings.
7. **Production OneDrive and Microsoft 365 connection status**, mailbox inventory and Graph app-registration details.
8. **Compliance scope** (ISO/SOC/data residency), custom-domain/DNS plan, and any Entra ID / SSO / MFA direction.
9. **Named technical and vendor contacts** — no contact registry is stored in the project.

---

*Prepared from a read-only inspection on 25 November 2026. Nothing in the ERP was modified while producing this report. Companion documents available on request: `ARCHITECTURE.md` (solution architecture), `AZURE_ASSESSMENT.md` (infrastructure data sheet), `memory/PRD.md` (requirements and dated change log).*
