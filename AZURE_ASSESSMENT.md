# AZURE ARCHITECTURE ASSESSMENT DATA SHEET
## INDIAN TRADE LINKS ERP ("WorkSite Command")

**Prepared:** June 2026 · **Source:** Direct inspection of the Emergent preview environment + application configuration
**Legend:** ✅ CURRENT/AVAILABLE (verified) · ⚙ CONFIGURED (set in app/env) · ❓ TO BE CONFIRMED (not visible from the project)

> Production runs on the Emergent managed platform (https://worksite-command.emergent.host). The values below are verified from the development/preview pod and the application codebase; production-plane infrastructure internals are managed by Emergent and marked TO BE CONFIRMED where not visible.

---

## 1. EXISTING INFRASTRUCTURE

| Item | Value | Status |
|---|---|---|
| Hosting platform | Emergent managed platform — Kubernetes cluster (containerized pods); Preview pod + separate Production deployment | ✅ |
| Application server OS | Debian GNU/Linux 12 (bookworm), containerized | ✅ (preview pod) |
| Preview pod resources | 4 vCPU · 16 GB RAM (shared pod running backend + frontend dev server + MongoDB) | ✅ (preview pod) |
| Production pod/VM specifications | Managed by Emergent platform | ❓ TO BE CONFIRMED with Emergent |
| Runtime versions | Python 3.11.16 (FastAPI/uvicorn) · Node.js 20.20.2 (React build) | ✅ |
| Application instances/replicas | Preview: 1 backend instance (uvicorn on 0.0.0.0:8001), 1 frontend (port 3000), supervised by supervisord. Production replica count | ✅ preview · ❓ production TO BE CONFIRMED |
| Load balancer / Ingress | Kubernetes Ingress: path-based routing — `/api/*` → backend :8001, `/*` → frontend :3000; TLS terminated at ingress (HTTPS) | ✅ |
| Process management | supervisord (backend, frontend, MongoDB, code-server) with auto-restart | ✅ (preview) |
| Autoscaling | None visible at application level | ❓ TO BE CONFIRMED with Emergent |

## 2. DATABASE

| Item | Value | Status |
|---|---|---|
| Engine | MongoDB (accessed via Motor async driver); connection via `MONGO_URL` env | ✅ |
| MongoDB version / topology (standalone vs replica set) | Preview: local single-node instance. Production topology | ❓ TO BE CONFIRMED |
| Database size (preview, measured) | Data: ~15.3 MB · Storage: ~14.5 MB · Indexes: ~12.6 MB · 347 collections · ~27,183 documents | ✅ (preview; production size ❓ TO BE CONFIRMED) |
| Monthly/yearly growth rate | Not measured — application is newly in production | ❓ TO BE CONFIRMED (recommend baselining after 2–3 months of production use) |
| Backup schedule | Application-level: nightly DB backup pushed to OneDrive at 18:30 IST (APScheduler cron `onedrive_backup`); OneDrive document push queue every 2 minutes | ⚙ CONFIGURED (requires OneDrive connection to be active) |
| Backup retention | No retention policy defined in application | ❓ TO BE CONFIRMED (define with Azure team) |
| Platform-level DB backups/snapshots | Managed by Emergent | ❓ TO BE CONFIRMED |
| Transaction/request volume | Not instrumented (no APM). Current scale indicators: 25 application users, 51 employees, ~1,100+ employee records planned (payroll preflight showed 1,167 employees in production), interactive OLTP-style workload (forms, approvals, reports) with low write volume and periodic batch jobs (payroll runs, exports, email queue) | ❓ TO BE CONFIRMED (recommend enabling request metrics before sizing) |
| Workload characteristics | Read-heavy dashboards & registers; small writes (documents ≤ few KB); nightly/scheduled batch jobs; Excel/PDF generation on demand | ✅ (from code) |

## 3. FILE STORAGE

| Item | Value | Status |
|---|---|---|
| Application upload storage (preview, measured) | 138 files ≈ 9.8 MB tracked in `files` collection (invoices, payslips, attachments, Tally invoices) | ✅ preview · ❓ production TO BE CONFIRMED |
| Primary object storage | Emergent-managed object storage via `/api/uploads` (folder allow-list, per-parent-type linkage) | ✅ |
| OneDrive usage | Microsoft Graph integration: push queue for all uploads (every 2 min) + nightly DB backup (18:30). Collections `onedrive_queue`, `onedrive_backups`, `onedrive_token_cache` present; connection status in preview: not currently connected | ⚙ CONFIGURED (production connection status ❓ TO BE CONFIRMED) |
| Monthly growth | Not measured | ❓ TO BE CONFIRMED |
| Document retention requirements | Not defined in application (no auto-purge) — all documents retained indefinitely | ❓ TO BE CONFIRMED (business/compliance decision) |

## 4. HIGH AVAILABILITY & DISASTER RECOVERY

| Item | Value | Status |
|---|---|---|
| Availability / SLA | No SLA defined at application level; platform SLA per Emergent plan | ❓ TO BE CONFIRMED |
| RPO | Not formally defined. Effective application-level RPO ≈ 24 h (nightly OneDrive DB backup, when connected) | ⚙ partial · ❓ formal target TO BE CONFIRMED |
| RTO | Not defined | ❓ TO BE CONFIRMED |
| Multi-region | Single-region deployment (Emergent managed); no multi-region logic in application | ✅ current · ❓ Azure target TO BE CONFIRMED |
| Backup & recovery process | App: nightly Mongo dump → OneDrive; documents mirrored to OneDrive via push queue. Restore procedure: manual (no automated restore tooling) | ⚙ CONFIGURED · restore runbook ❓ TO BE CONFIRMED |
| Platform snapshots / rollback | Emergent provides code checkpoints & rollback per deployment | ✅ |

## 5. SECURITY & ACCESS

| Item | Value | Status |
|---|---|---|
| Authentication | Custom JWT auth (httpOnly cookies, access + refresh tokens); optional email OTP login; admin impersonation with audit | ✅ |
| Credential storage | bcrypt-hashed passwords; JWT_SECRET, M365_FERNET_KEY (encrypts mailbox app-passwords), SMTP passwords, EMERGENT_LLM_KEY, RESEND_API_KEY — **CONFIGURED – SECRET VALUES NOT DISCLOSED** (env vars / platform Secrets tab) | ✅ |
| RBAC | Dynamic role/permission matrix stored in DB (resource × action); built-in + custom roles (e.g. `manager_o_p`); enforced server-side (`require_permission`) and mirrored in frontend RouteGuard; row-level scoping by project (PM scope) and department | ✅ |
| Microsoft Entra ID / Azure AD integration | NOT integrated (auth is application-native). M365 used only for SMTP + OneDrive Graph API | ✅ current = No · ❓ Azure AD migration scope TO BE CONFIRMED |
| SSO | Not implemented | ✅ current = No |
| MFA | Partial: email OTP login option exists; no TOTP/enforced MFA | ⚙ · enforcement policy ❓ TO BE CONFIRMED |
| Audit & compliance controls | Full audit log (who/when/before/after/IP) on sensitive mutations; PII masking in exports for non-privileged roles; upload type/size restrictions | ✅ |
| Regulatory requirements | Indian statutory contexts present in app (GST, PF/ESI/PT/TDS payroll). Formal compliance scope (ISO/SOC/data-residency) | ❓ TO BE CONFIRMED with business |

## 6. NETWORK & CONNECTIVITY

| Item | Value | Status |
|---|---|---|
| Access model | Public HTTPS (internet-facing) — no IP allow-listing at app level | ✅ |
| Production URL | https://worksite-command.emergent.host | ✅ |
| Preview URL | https://worksite-command.preview.emergentagent.com | ✅ |
| Custom domain / DNS | Using Emergent-provided subdomains; custom company domain (indiantradelinks.in) used only for email sender identities | ✅ · custom app domain plan ❓ TO BE CONFIRMED |
| VPN | None (no VPN/private link configured) | ✅ current = None |
| Branch/remote connectivity | Users access via public internet from office/site locations; no site-to-site connectivity | ✅ · future needs ❓ TO BE CONFIRMED |
| Ingress architecture | K8s ingress path routing (`/api` → 8001, rest → 3000); CORS controlled via `CORS_ORIGINS` env | ✅ |
| Outbound dependencies | smtp.office365.com:587 (M365 SMTP), Microsoft Graph API (OneDrive), Emergent LLM endpoint, Emergent object storage | ✅ |

## 7. APPLICATION DOCUMENTATION

| Item | Value | Status |
|---|---|---|
| Solution architecture document | `/app/ARCHITECTURE.md` (full architecture: layers, module map, data model, workflows) | ✅ AVAILABLE |
| Requirements & changelog | `/app/memory/PRD.md` (living PRD with dated change log) | ✅ AVAILABLE |
| Application stack | React 18 (CRA/CRACO, Shadcn/UI, Tailwind) SPA → FastAPI (119 routers, Python 3.11) → MongoDB (Motor); in-process APScheduler for cron jobs | ✅ |
| Dependency architecture | Backend: fastapi, motor/pymongo, pydantic v2, reportlab, openpyxl, apscheduler, emergentintegrations, cryptography (Fernet), passlib/bcrypt. Frontend: react, axios, shadcn/radix, lucide-react, sonner. Full lists: `/app/backend/requirements.txt`, `/app/frontend/package.json` | ✅ |
| Deployment architecture | Two environments: Preview (dev pod, hot reload) and Production (Emergent deploy with Secrets tab for env vars; redeploy to promote). Supervisord manages processes; `/api` prefix contract for routing | ✅ |
| External integrations | 1) Microsoft 365 SMTP — system mailboxes (noreply@indiantradelinks.in) + per-user app passwords (Fernet-encrypted). 2) OneDrive (MS Graph) — document sync + DB backups. 3) Emergent LLM key (`emergentintegrations`) — AI quotation & bulk parsing. 4) Emergent object storage — file uploads. 5) Resend API key present in env (legacy/secondary email) | ✅ |
| Scheduled jobs | Daily 07:30 shortage scan · 08:00 approval reminders · 08:15 vendor payment due · 08:30 enquiry reminders · 08:45 action-item overdue · 09:00 expiry scan · 09:30 billing reminders · Mon 09:00 invoice reminders · Mon 09:15 GMC review · every 10 min email retry · every 2 min OneDrive push · 18:30 OneDrive DB backup | ✅ |
| Vendor / technical contacts | Platform: Emergent (support via platform). Application owner/IT contact at INDIAN TRADE LINKS | ❓ TO BE CONFIRMED (no contact registry stored in project) |

---

## SUMMARY FOR AZURE TEAM — SUGGESTED TARGET MAPPING (indicative only)

| Current Component | Azure Candidate |
|---|---|
| K8s pods (FastAPI + React) | Azure Kubernetes Service (AKS) or Azure App Service / Container Apps |
| MongoDB | Azure Cosmos DB for MongoDB (vCore) or self-managed MongoDB on AKS / Atlas on Azure |
| Object storage + OneDrive sync | Azure Blob Storage (+ keep OneDrive mirror if business requires) |
| Ingress | Azure Application Gateway / Front Door |
| Secrets (env vars) | Azure Key Vault |
| Auth (custom JWT) | Retain, or migrate to Microsoft Entra ID (SSO/MFA) — scoping required |
| APScheduler jobs | Retain in-process, or Azure Functions / Container Apps jobs |

**Key gaps to close before migration sizing:** production pod specs & replica counts, production DB size & growth baseline, formal RPO/RTO & SLA targets, backup retention policy, compliance scope, custom-domain/DNS plan, and Entra ID/SSO decision.

*No passwords, keys, tokens or secret values are included in this document.*
