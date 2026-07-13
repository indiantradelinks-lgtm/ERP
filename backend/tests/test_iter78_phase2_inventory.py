"""Iter 78 — Store & Inventory Phase 2: Procurement / Accounts / Finance integration.

Pure-Python tests (route discovery + business-rule constants).
HTTP-layer behaviour is covered by curl smoke + testing-agent suite.
"""
from __future__ import annotations


def test_phase2_router_endpoints_present():
    from routers.inventory_phase2_router import router
    paths = {r.path for r in router.routes}
    expected = {
        "/inv2/pr-from-stock",
        "/inv2/stock-shortage-suggestions",
        "/inv2/pending-pos-for-grn",
        "/inv2/stock-inward-report",
        "/inv2/grn-pending-invoice",
        "/inv2/accounts-grn-visibility",
        "/inv2/inspection-hold",
        "/inv2/procurement-pipeline",
    }
    missing = expected - paths
    assert not missing, f"Phase 2 endpoints missing: {missing}"


def test_pr_priority_whitelist_enforced():
    """The PRFromStockIn validator should reject any priority not in
    {normal, urgent, emergency}. We assert the enum via the handler constant."""
    # Handler checks `if payload.priority not in ('normal', 'urgent', 'emergency')`
    import inspect
    from routers import inventory_phase2_router as mod
    src = inspect.getsource(mod.create_pr_from_stock)
    assert "'normal', 'urgent', 'emergency'" in src or '"normal", "urgent", "emergency"' in src


def test_grn_model_has_phase2_fields():
    """The existing GRNIn model must now accept the Phase 2 enrichment fields
    (vehicle_number, transporter_name, vendor_invoice_no, attachment_url, ...)
    without breaking back-compat (everything Optional)."""
    from routers.procurement_router import GRNIn
    fields = set(GRNIn.model_fields.keys())
    phase2_required = {
        "vendor_invoice_no", "vendor_invoice_date", "vendor_invoice_value",
        "vehicle_number", "transporter_name", "transporter_lr_no",
        "attachment_url", "attachment_urls", "project_code",
        "inspection_required", "manual_grn",
    }
    missing = phase2_required - fields
    assert not missing, f"GRNIn missing Phase 2 fields: {missing}"
    # Backward-compat: all phase-2 fields default to None / False
    instance = GRNIn(po_id="x", items=[])
    for f in phase2_required - {"manual_grn", "attachment_urls"}:
        assert getattr(instance, f) is None, f"{f} should default to None"
    assert instance.manual_grn is False


def test_pipeline_response_shape_constants():
    """Sanity-check that the pipeline endpoint includes the keys used by
    the Finance dashboard tile."""
    import inspect
    from routers import inventory_phase2_router as mod
    src = inspect.getsource(mod.procurement_pipeline)
    for k in ("pr_pending_count", "pr_pending_value", "po_pending_count",
              "po_pending_value", "grn_30d_count", "grn_30d_value",
              "emergency_pr_count"):
        assert f'"{k}"' in src, f"pipeline response missing key {k}"
