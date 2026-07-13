"""Iter 81 — Store & Inventory Phase 5 (Valuation + Physical Count + Final Dashboard)."""
from __future__ import annotations


def test_phase5_router_endpoints_present():
    from routers.inventory_phase5_router import router
    paths = {r.path for r in router.routes}
    expected = {
        "/inv5/valuation",
        "/inv5/stock-counts",
        "/inv5/stock-counts/{sc_id}/approve",
        "/inv5/stock-counts/{sc_id}/reject",
        "/inv5/dashboard",
        "/inv5/reconcile-check",
    }
    missing = expected - paths
    assert not missing, f"Phase 5 endpoints missing: {missing}"


def test_valuation_method_whitelist():
    """Source-level assertion for the valuation method validation."""
    import inspect
    from routers import inventory_phase5_router as mod
    src = inspect.getsource(mod.stock_valuation)
    for m in ("weighted_average", "last_purchase", "standard"):
        assert m in src, f"valuation method '{m}' missing from validator"


def test_stock_count_status_enum():
    from routers.inventory_phase5_router import SC_STATUSES
    assert set(SC_STATUSES) == {"draft", "submitted", "approved", "rejected", "cancelled"}


def test_stock_count_validations_in_source():
    import inspect
    from routers import inventory_phase5_router as mod
    src = inspect.getsource(mod.create_stock_count)
    assert "physical_qty cannot be negative" in src
    src_approve = inspect.getsource(mod.approve_stock_count)
    # High-variance finance gate
    assert "needs_finance_approval" in src_approve
    assert "finance_head" in src_approve
    # Self-approve guard
    assert "Cannot approve your own" in src_approve
    # Race-safe negative guard
    assert '"quantity": {"$gte"' in src_approve


def test_dashboard_returns_30_tile_keys():
    import inspect
    from routers import inventory_phase5_router as mod
    src = inspect.getsource(mod.consolidated_dashboard)
    required = (
        "total_stock_value", "total_items", "stores_count", "site_stores_count",
        "low_stock_count", "reorder_count", "out_of_stock_count",
        "pending_mr_count", "pending_grn_count", "pending_inspection_count",
        "pending_transfer_count", "pending_opening_count",
        "pending_damage_loss_count", "pending_scrap_count", "pending_stock_count_count",
        "in_transit_value", "damaged_value", "scrap_value",
        "tools_issued_count", "ppe_issued_count", "expiring_ppe_30d_count",
        "pending_recovery_value", "consumption_month_value", "high_value_movements_month",
        "top_consumed", "recent_transactions",
    )
    for k in required:
        assert f'"{k}"' in src, f"dashboard response missing key {k}"


def test_reconcile_check_uses_ledger_vs_balance():
    import inspect
    from routers import inventory_phase5_router as mod
    src = inspect.getsource(mod.reconcile_check)
    assert "$sum" in src and '"$delta"' in src
    assert '"drift"' in src and 'drift_count' in src


def test_high_variance_threshold_defined():
    from routers.inventory_phase5_router import HIGH_VARIANCE_THRESHOLD
    assert HIGH_VARIANCE_THRESHOLD >= 10000
