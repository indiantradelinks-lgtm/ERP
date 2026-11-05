# ERP Performance & Storage — Root-Cause Analysis (pre-implementation)

Measured on the preview environment (same code/image as production). Production tier: tier_0 — 250m CPU, 512 Mi RAM per backend pod, 2 replicas (from deployer RCA 69c8ff12).

## 1. Root causes of "Memory 100% used" (ranked by impact)

| # | Finding | Evidence | Impact on a 512 Mi pod |
|---|---------|----------|------------------------|
| 1 | **AI library (litellm) is loaded into the API process the first time ANY AI feature is used and never released** — Challan OCR, HR document AI, AI Quotation, Attendance AI, Email actions | `import emergentintegrations.llm.chat` → **+160 MB RSS**, permanent | 233 MB idle + 160 MB = ~395 MB steady → any PDF/Excel export (+10–40 MB) or 2 concurrent users exporting → **OOMKill (exit 137)** → Cloudflare 520 + "Memory 100%" |
| 2 | **Idle footprint is 233 MB before the first request** — 129 routers, 3,837 Python modules imported eagerly: WeasyPrint 38 MB, PyMuPDF 31 MB, openpyxl 17 MB, reportlab/PIL/msal/google libs loaded even though most requests never need them | `import server` → 233 MB | Only ~280 MB of working headroom per pod; two replicas = the whole app fleet has <600 MB usable |
| 3 | **No frontend code-splitting** — the entire ERP (82,800 lines, 213 page components) ships as **one 4.76 MB JavaScript file** (`main.*.js`) | `yarn build` → single chunk, 0 `React.lazy` routes | Every login/refresh downloads and parses 4.7 MB; slow pages on site/mobile networks; perceived "ERP is slow" |
| 4 | **Un-paginated list endpoints return whole collections** — e.g. `/api/approvals` = 678 KB JSON in preview (production is several × larger); 39 queries use `to_list(10000–100000)` | curl measurements | CPU + memory spike per page open; on 250m CPU each big list serialises in ~1 s and blocks other users |
| 5 | **CPU quota 250m (¼ core)** — a PR PDF renders in 0.43 s on a full core here; at ¼ core that is ~1.7 s, during which the pod can serve little else | offload timing logs | Explains residual slowness even after the earlier loop-offload fix; **cannot be fully fixed in code** |
| 6 | Background jobs: OneDrive push every 2 min keeps retrying a queue whose Graph auth is failing (`AADSTS7000215: Invalid client secret`), 69 items pending | `db.settings.onedrive.last_test_error` | Wasted CPU/network every 2 min; documents NOT being mirrored since the secret rotated |
| 7 | Technical log collections grow without retention: `audit_logs` 13k, `notifications` 12k, `login_activity` 4.2k rows (no TTL); only `module_visits` has TTL | collStats | DB growth + slower admin pages; not business data |

What is **not** the problem: server disk (27 % used; documents are not on the pod disk), Mongo pool/connection handling (already bounded in Iter 218), WeasyPrint/openpyxl blocking the loop (already offloaded in Iter 218 — 4 concurrent PDFs now finish in 0.4–0.9 s with +7 MB RSS).

## 2. Where documents actually live (important for item 2 of the request)

- All ERP attachments (103 active files / 10.8 MB in preview; 181 incl. soft-deleted) are in **Emergent object storage**, registered in one collection `db.files` (+ Scaffolding challan PDFs on `scaf_transfers`). They are **not on the ERP server disk**, so migrating them frees RAM/CPU only indirectly (less data passing through the pod) — it does **not** free server disk.
- A OneDrive integration already exists (app-only Graph, push queue, nightly DB backup): 153 files pushed, 69 pending, 78 skipped. It is **one-way mirror only**: no integrity verification, no OneDrive-first reads, and it is currently blocked by the expired Azure client secret.
- Emergent object storage has **no delete API** — "remove local copy" can only mean: verified on OneDrive → read path switches to OneDrive → object-store reference released/marked `archived`. Bytes in the object store cannot be physically deleted by the app; this is stated plainly so expectations are correct.

## 3. Proposed technical solution

### A. Memory (fixes #1, #2) — biggest win, zero functional change
1. Run every AI/OCR call (challan, HR docs, AI quotation, attendance AI, email actions) in a **short-lived worker subprocess** (`ai_worker.py`) with concurrency cap 1. litellm's 160 MB lives only for the ~20 s of the call and is returned to the OS. API process stays at ~235 MB regardless of AI usage.
2. **Lazy-import** PyMuPDF, openpyxl, reportlab, pandas-free paths; keep WeasyPrint eager (used by all PDFs). Expected idle: 233 → ~175 MB.
3. Add `gc.freeze()` after startup + `MALLOC_ARENA_MAX=2` to reduce fragmentation growth in the long-lived process.
   **Target: steady-state ≤ 240 MB per pod under full feature use (vs. 395–512 MB today).**

### B. Frontend (fixes #3)
4. Route-level `React.lazy` + `Suspense` for all 213 pages, grouped per module chunk. Target initial JS ≤ 1.2 MB (−75 %), module chunks load on demand and are cached.

### C. API & DB (fixes #4, #7)
5. Server-side pagination defaults on the heaviest list endpoints (approvals, quotations, inventory, my-inbox, files, audit-logs); cap `to_list(…)` scans; projection to drop unused large sub-documents.
6. Slow-request middleware (>1.5 s logged with path/user) feeding the health dashboard so remaining slow queries are identified from real production traffic.
7. Retention policy (approval needed, technical data only): `login_activity` 180 d, read `notifications` 90 d, `request_fingerprints` already TTL, `onedrive_queue` pushed rows 90 d, `email_outbox` bodies 180 d (headers kept). **No business/transaction records, audit_logs or files are deleted.**

### D. OneDrive as primary document store (request item 2)
8. Re-authenticate Graph (new client secret entered in Admin → OneDrive settings; stored Fernet-encrypted in DB as today).
9. Migration job (scheduler-leader only, 25 files/tick, off-peak): object store → OneDrive `ITL-ERP-Backups/<Module>/<Record>/…`, then **verify**: size match + download-back from OneDrive + SHA-256 == stored `sha256`. Only after verification: `files.storage_tier = "onedrive"`, `migrated_at`, `verified_sha256`. Original object-store reference retained (`storage_path_archived`) for rollback — never cleared.
10. Read path: `storage_tier == onedrive` → stream from OneDrive (short-lived cached Graph download URL), fallback to object store if OneDrive is unreachable. Same `/api/files/{id}/download` URL, same permissions, same parent links — **no frontend or link changes**.
11. New uploads: continue to land in object store (fast, synchronous), then migrate via the same verified pipeline within minutes.
12. Admin "Document Storage" page: counts/bytes per tier, migration progress, verification failures, manual retry; "Storage audit" report before starting (exact production numbers).

### E. Automatic server storage management (request item 3)
13. Daily housekeeping job (leader only): purge WeasyPrint/PyMuPDF temp files >1 h, rotate `/tmp` exports, prune expired `cleanup_archive`, pushed `onedrive_queue` rows. Configurable thresholds in Admin: warn at 75 %/critical 90 % for disk, RSS, DB size → in-app + email alert to admins.

### F. Permanent monitoring (request item 5)
14. `/api/admin/system-health`: process RSS/CPU, event-loop lag, Mongo dataSize/indexSize/connections, disk %, slow-request top-20 (24 h), scheduler leader, OneDrive queue health. Rendered in Admin → System Health with 30-day history (one sample / 5 min, TTL 30 d).

## 4. Implementation plan (each step independently testable)

| Step | Scope | Test |
|------|-------|------|
| 0 | Backup: trigger existing `POST /api/onedrive/backup-now` (DB dump → OneDrive) + object-store manifest export (`files` collection JSON) | backup file present + checksum logged |
| 1 | A1 AI subprocess worker (challan first, then 4 other AI call-sites) | challan extraction returns same 29 rows; API RSS unchanged after call |
| 2 | A2/A3 lazy imports, gc.freeze, arena cap | idle RSS, full regression tests (scaffolding/exports) |
| 3 | C6 + F14 slow-request log, system-health API & Admin page | page renders live numbers |
| 4 | B4 route code-splitting | bundle sizes before/after; smoke every module route |
| 5 | C5 pagination/projection on 6 heaviest endpoints | response size/time before/after; frontend lists still correct |
| 6 | D8–D12 OneDrive verified migration + OneDrive-first reads (dry-run mode first, then approval to run) | migrate 1 file → verify → download via ERP → rollback flag works |
| 7 | E13 housekeeping + alerts; C7 retention (after approval) | job runs, thresholds trigger test alert |
| 8 | Before/after report: RSS, CPU, disk, DB, 10 representative API/page timings | shared with you |

Estimated effort: steps 0–3 first (they remove the OOM cause), then 4–5, then 6–8.

## 5. Risks & dependencies
- **Dependency:** a valid Azure AD app client secret for `backup@indiantradelinks.in` (current one rejected by Microsoft). Migration cannot start without it.
- **Dependency (production):** OneDrive quota — production file volume to be confirmed by the storage audit (preview is 10.8 MB; production expected tens of GB at most for 1 TB OneDrive for Business).
- **Risk:** Graph throttling (429) during bulk migration → mitigated by 25 files/tick with backoff (already implemented pattern).
- **Risk:** OneDrive-first downloads add ~300–800 ms latency vs object store → mitigated by streaming + fallback; recent files (<30 d) can be kept object-store-first.
- **Risk:** code-splitting changes load order; a mistyped lazy path = blank page → every route smoke-tested by testing agent before deploy.
- **Limitation (honest):** Emergent object storage cannot be deleted by the app; "removal" = reference release after verification. Pod CPU remains 250m; if after steps 1–5 PDF generation still exceeds ~1.5 s under load, a tier upgrade will be the *justified* recommendation, backed by the health dashboard data — not before.

## 6. Estimated recovery
- **RAM:** ~160 MB per pod avoided (AI library) + ~55 MB idle (lazy imports) ≈ **−45 % steady-state memory**; OOMKills eliminated as the AI-driven growth is the proven trigger.
- **Frontend:** initial download 4.76 MB → ~1.2 MB (**−75 %**).
- **Server disk:** no change (documents are not on disk; pod disk at 27 %).
- **Object storage:** 100 % of eligible historical files (preview: 103 files/10.8 MB; production: measured by storage audit in step 6) become OneDrive-primary; object-store copies retained as rollback until you approve release.
- **DB:** ~30 % of technical-log rows eligible for retention after approval; no business data affected.

## 8. Implemented (Iter 226, approved) — before / after on the preview (same image as production)

| Metric | Before | After |
|---|---|---|
| Backend RSS idle | 245 MB | **208–221 MB** |
| Backend RSS growth after first AI call | **+160 MB, permanent** (litellm in-process) | **+2 MB** — AI runs in a child process (`ai_worker.py`, peak 208 MB, exits after reply) |
| RSS after 4 concurrent PDF renders | +7 MB, kept | +6 MB then `malloc_trim` returns pages (227 MB) |
| First-load JavaScript | 1 file, **4.76 MB** (1.01 MB gzip) | **686 KB** main (203 KB gzip) + 240 on-demand chunks (−86 %) |
| PR PDF render | 0.43 s | 0.44 s (unchanged — already offloaded) |
| List APIs (admin, 50 rows) | 0.11–0.22 s | 0.11–0.15 s (unchanged; main grids were already server-paged — RCA item #4 applies to ad-hoc callers only, now tracked by the slow-request log) |
| Visibility | none in-app | Admin → System Health: RSS/CPU/loop-lag/disk/DB/p95, slow-request log, 30-day history, thresholds + in-app/email alerts |
| Housekeeping | none | daily 20:30 UTC: temp files > 2 h, login_activity > 180 d, read notifications > 90 d, email bodies > 180 d (headers kept); configurable; business data untouched |
| Documents | one-way mirror, no verification | verified OneDrive-primary tier (size + download-back + SHA-256), object-store copy kept as fallback/rollback; storage audit per module; `primary_reads` switch |

CPU quota (250m) is unchanged and remains the ceiling for PDF-heavy minutes; the System Health history will show whether a tier upgrade is justified after a week of production data.

Still blocked on the user: a valid Azure client secret (verification/pushes currently fail with `AADSTS7000215` in preview).

## 7. Baseline captured before implementation (preview)
- Backend idle RSS: 245 MB (uvicorn --reload); after `import server`: 233 MB; +160 MB after first AI import.
- PR PDF: 0.43 s, +11 MB; 4 concurrent PDFs: 0.44–0.87 s, +7 MB.
- List APIs (admin): /projects 0.15 s 30 KB; /employees 0.11 s 29 KB; /my-inbox 0.18 s 113 KB; /quotations 0.17 s 266 KB; /inventory 0.14 s 114 KB; /approvals 0.22 s 678 KB.
- Frontend production bundle: 1 × 4.76 MB JS.
- DB: 380 collections, 797 indexes, 24 MB data / 26 MB index (preview).
