# Test Plan — PM sync retest 141

No relevant testing skill found.

User-reported bug: Project Manager (Projects & Operations) assigned in Contract Handovers must automatically sync, save, and display in Projects Master → Manager and related modules.

Focused scope:
- Exact remaining failure from prior run: target handover `4a16236b-68bd-45d4-b0a3-6b08f54d98ec` must return/display `project_manager_label: Test PM`, not truncated id `f4abf0`.
- Fresh re-allocation of that handover to user `f4abf031-9eaa-4fdb-bba8-8828fdc4f467` must persist `project_manager_label` on `project_handovers` and sync `project_manager_name` on project `147f9689-ff9d-421a-9f7b-69e5dae8800e`.
- Legacy hydration: list endpoint must not return existing user assignee ids without labels.
- Quick regression: admin sees all projects with manager names; `test_pm` sees only assigned projects; UI `/app/ops/handovers` and `/app/projects` display `Test PM`.

Changed files inspected:
- `backend/routers/projects_ops_router.py` has uncommitted changes: `allocate_handover` persists `*_label` fields and syncs `project_manager_name`; `list_handovers` hydrates missing labels.
- `frontend/src/pages/ops/ContractHandovers.jsx` renders `project_manager_label || truncated id`.
- `frontend/src/pages/Projects.jsx` renders `project_manager_name || manager`.

Proof needed for fixed verdict:
- API assertions pass for target row label, direct Mongo persistence, related project manager name, and PM/admin project visibility.
- UI automation confirms target handover row contains `PM: Test PM` and not `PM: f4abf0`; Projects page row contains `Test PM`.
