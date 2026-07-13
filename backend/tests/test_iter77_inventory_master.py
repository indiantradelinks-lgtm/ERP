"""Iter 77 — Store & Inventory Phase 1: master data + opening stock + dashboard.

These tests exercise the pure-Python validation rules and seed-defaults helper
without standing up the full HTTP layer (covered separately by curl smoke tests).
"""
from __future__ import annotations


def test_store_types_whitelist():
    from routers.inventory_master_router import STORE_TYPES
    assert set(STORE_TYPES) == {"main_store", "site_store", "project_store", "scrap_yard", "damaged_stock"}


def test_opening_stock_statuses():
    from routers.inventory_master_router import OS_STATUSES, OS_CONDITIONS
    assert "approved" in OS_STATUSES and "pending_approval" in OS_STATUSES
    assert "rejected" in OS_STATUSES and "draft" in OS_STATUSES and "cancelled" in OS_STATUSES
    assert OS_CONDITIONS == ("new", "good", "used", "damaged", "scrap")


def test_default_settings_keys_complete():
    from routers.inventory_master_router import DEFAULT_SETTINGS
    required_keys = {
        "issue_threshold_default", "opening_stock_approval_value",
        "default_category_id", "default_unit_id", "default_store_id",
        "block_negative_stock", "require_batch_on_receipt",
        "ppe_inspection_days", "tool_calibration_warning_days",
    }
    assert required_keys.issubset(set(DEFAULT_SETTINGS.keys()))


def test_itl_categories_have_required_service_lines():
    """The 12 default ITL categories must cover the 7 service lines explicitly."""
    from routers.inventory_master_router import ITL_CATEGORIES
    codes = {c["code"] for c in ITL_CATEGORIES}
    # Must include the 5 service-line categories
    for must in ("SCAFFOLD", "PAINT", "ROOF", "ROPE", "PPE", "TOOLS", "CONSUM", "MACHINE",
                  "VEHICLE", "OFFICE", "SCRAP", "MISC"):
        assert must in codes, f"Default category {must} missing"
    # Sub-categories for SCAFFOLD must include all 10 named in the spec
    scaf = next(c for c in ITL_CATEGORIES if c["code"] == "SCAFFOLD")
    for sub in ("Pipe", "Cuplock Vertical", "Cuplock Horizontal", "Base Jack", "U Jack",
                 "Joint Pin", "Walkway Plank", "Clamp", "Coupler", "Ladder"):
        assert sub in scaf["sub_categories"], f"SCAFFOLD missing sub {sub}"


def test_itl_units_include_metric_imperial_conversions():
    from routers.inventory_master_router import ITL_UNITS
    by_code = {u["code"]: u for u in ITL_UNITS}
    assert "KG" in by_code and "G" in by_code
    assert by_code["G"]["base_unit"] == "KG"
    assert by_code["G"]["conversion_factor"] == 0.001
    assert "FT" in by_code and by_code["FT"]["base_unit"] == "M"
    assert 0.30 < by_code["FT"]["conversion_factor"] < 0.31


def test_dashboard_endpoint_registered():
    """Sanity-check: the router is importable and exposes the dashboard route."""
    from routers.inventory_master_router import router
    paths = {r.path for r in router.routes}
    assert "/inv/dashboard" in paths
    assert "/inv/stock-balance" in paths
    assert "/inv/seed-defaults" in paths
    assert "/inv/opening-stock" in paths
    assert "/inv/opening-stock/{os_id}/approve" in paths
    assert "/inv/opening-stock/{os_id}/reject" in paths


def test_master_crud_endpoints_present():
    from routers.inventory_master_router import router
    paths = {r.path for r in router.routes}
    for collection in ("categories", "units", "stores", "site-stores", "bins"):
        assert f"/inv/{collection}" in paths, f"List endpoint missing for {collection}"
