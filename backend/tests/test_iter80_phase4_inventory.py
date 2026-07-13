"""Iter 80 — Store & Inventory Phase 4 (PPE / Damage-Loss / Scrap / Clearance / Recovery)."""
from __future__ import annotations


def test_phase4_router_endpoints_present():
    from routers.inventory_phase4_router import router
    paths = {r.path for r in router.routes}
    expected = {
        "/inv4/ppe-issues",
        "/inv4/ppe-expiry-register",
        "/inv4/ppe-inspections",
        "/inv4/damage-loss",
        "/inv4/damage-loss/{dl_id}/approve",
        "/inv4/damage-loss/{dl_id}/reject",
        "/inv4/scrap-entries",
        "/inv4/scrap-entries/{scrap_id}/approve",
        "/inv4/scrap-sales",
        "/inv4/scrap-sales/{sale_id}/approve",
        "/inv4/employee-clearance/{employee_id}",
        "/inv4/recoveries",
        "/inv4/recoveries/{rec_id}/mark-recovered",
        "/inv4/recoveries/{rec_id}/waive",
        "/inv4/transit-exceptions",
        "/inv4/tool-issue-register",
        "/inv4/employee-pending-tools/{employee_id}",
    }
    missing = expected - paths
    assert not missing, f"Phase 4 endpoints missing: {missing}"


def test_ppe_issue_type_whitelist():
    from routers.inventory_phase4_router import PPE_ISSUE_TYPES
    assert set(PPE_ISSUE_TYPES) == {"new", "replacement", "returnable", "non_returnable"}


def test_damage_loss_status_and_threshold():
    from routers.inventory_phase4_router import DL_STATUSES, HIGH_VALUE_THRESHOLD
    assert set(DL_STATUSES) == {"draft", "submitted", "approved", "rejected", "cancelled"}
    assert HIGH_VALUE_THRESHOLD >= 10000  # spec says high-value triggers Finance approval


def test_inspection_results():
    from routers.inventory_phase4_router import INSPECTION_RESULTS
    assert set(INSPECTION_RESULTS) == {"pass", "fail", "conditional"}


def test_damage_loss_validations_in_source():
    import inspect
    from routers import inventory_phase4_router as mod
    src = inspect.getsource(mod.create_damage_loss)
    # Rule 6: attachment is mandatory
    assert "attachment_url is mandatory" in src
    # Rule 6: reason is mandatory
    assert "reason is mandatory" in src
    # quantity > 0
    assert "quantity must be > 0" in src


def test_high_value_dl_needs_finance_in_approve():
    import inspect
    from routers import inventory_phase4_router as mod
    src = inspect.getsource(mod.approve_damage_loss)
    # Rule 7: high-value requires Finance/Owner
    assert "needs_finance_approval" in src
    assert "finance_head" in src
    # Self-approve guard
    assert "Cannot approve your own" in src


def test_ppe_issue_expired_check_in_source():
    import inspect
    from routers import inventory_phase4_router as mod
    src = inspect.getsource(mod.ppe_issue)
    # Rule 1: expired cannot be issued
    assert "expired" in src.lower()
    # Rule 2: damaged/unfit
    assert "damaged" in src and ("unfit" in src or "scrap" in src)
    # Race-safe stock check
    assert '"quantity": {"$gte"' in src


def test_recovery_waiver_requires_elevated_role():
    import inspect
    from routers import inventory_phase4_router as mod
    src = inspect.getsource(mod.waive_recovery)
    assert "finance_head" in src
    # Reason mandatory
    assert "Waiver reason is mandatory" in src


def test_scrap_sale_requires_approved_entries():
    import inspect
    from routers import inventory_phase4_router as mod
    src = inspect.getsource(mod.create_scrap_sale)
    assert 'status") != "approved"' in src or 'is not approved' in src


def test_employee_clearance_aggregates_all_kinds():
    import inspect
    from routers import inventory_phase4_router as mod
    src = inspect.getsource(mod.employee_clearance)
    for k in ("tool", "asset", "material", "consumable"):
        assert f'"{k}"' in src, f"clearance missing aggregation for kind={k}"
    # PPE + recoveries
    assert "ppe_issuance" in src and "recoveries" in src
    assert "can_clear" in src and "total_blockers" in src
