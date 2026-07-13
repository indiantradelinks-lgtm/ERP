"""Iter 79 — Store & Inventory Phase 3 (Material Request + Transfer + Site/Project)."""
from __future__ import annotations


def test_phase3_router_endpoints_present():
    from routers.inventory_phase3_router import router
    paths = {r.path for r in router.routes}
    expected = {
        "/inv3/material-requests",
        "/inv3/material-requests/{mr_id}/approve",
        "/inv3/material-requests/{mr_id}/reject",
        "/inv3/material-requests/{mr_id}/issue",
        "/inv3/transfers",
        "/inv3/transfers/{transfer_id}/receive",
        "/inv3/in-transit-stock",
        "/inv3/site-stock",
        "/inv3/project-stock",
        "/inv3/project-consumption",
        "/inv3/pending-returnable",
        "/inv3/project-closure-check/{project_code}",
    }
    missing = expected - paths
    assert not missing, f"Phase 3 endpoints missing: {missing}"


def test_mr_status_and_priority_enums():
    from routers.inventory_phase3_router import MR_STATUSES, MR_PRIORITIES
    assert set(MR_STATUSES) == {"draft", "submitted", "approved", "partially_issued",
                                  "issued", "rejected", "cancelled"}
    assert set(MR_PRIORITIES) == {"normal", "urgent", "emergency"}


def test_transfer_status_enum():
    from routers.inventory_phase3_router import TRANSFER_STATUSES
    assert set(TRANSFER_STATUSES) == {"draft", "dispatched", "in_transit", "received",
                                        "received_with_exception", "cancelled"}


def test_material_request_validators():
    """MaterialRequestIn must mandate project_code and have a non-empty lines list."""
    from routers.inventory_phase3_router import MaterialRequestIn, MRLine
    # Empty lines should raise (min_length=1)
    try:
        MaterialRequestIn(project_code="P1", lines=[])
    except Exception:
        pass
    else:
        raise AssertionError("Empty lines should have failed Pydantic validation")
    # Valid construction
    mr = MaterialRequestIn(project_code="P1", lines=[MRLine(item_id="i1", required_qty=1.0)])
    assert mr.project_code == "P1"
    assert mr.priority == "normal"


def test_transfer_input_validators():
    """Transfer must have at least one line."""
    from routers.inventory_phase3_router import TransferIn, TransferLine
    try:
        TransferIn(from_store_id="A", to_store_id="B", lines=[])
    except Exception:
        pass
    else:
        raise AssertionError("Empty transfer lines should have failed validation")
    trf = TransferIn(from_store_id="A", to_store_id="B",
                       lines=[TransferLine(item_id="i1", quantity=1.0)])
    assert trf.from_store_id == "A"


def test_handlers_check_required_business_rules():
    """Source-level assertions for rules that don't have direct Pydantic enforcement."""
    import inspect
    from routers import inventory_phase3_router as mod
    src_create_trf = inspect.getsource(mod.create_transfer)
    # Rule 6: source ≠ destination
    assert "from_store_id == payload.to_store_id" in src_create_trf
    # Rule 4: race-safe debit (negative-stock guard)
    assert '"quantity": {"$gte"' in src_create_trf
    # Rule 7: dest stock only on receive
    assert '"in_transit"' in src_create_trf

    src_receive = inspect.getsource(mod.receive_transfer)
    # Rule 9: damaged/lost must have reason or attachment
    assert "damage_attachment_url" in src_receive and "received_remarks" in src_receive
    assert "$inc" in src_receive  # credits destination

    src_issue = inspect.getsource(mod.issue_from_mr)
    # Rule 2: issue qty <= approved balance
    assert "approved-balance" in src_issue or "approved_balance" in src_issue or "approved-balance" in src_issue.replace("_", "-")
    # Rule 3 & 4: negative-stock guard
    assert '"quantity": {"$gte"' in src_issue


def test_closure_check_blockers_logic():
    """Project closure must surface 3 categories of blockers."""
    import inspect
    from routers import inventory_phase3_router as mod
    src = inspect.getsource(mod.project_closure_check)
    for k in ("pending_returnable_count", "in_transit_count", "pending_mr_count", "can_close", "blockers"):
        assert f'"{k}"' in src, f"closure-check response missing {k}"
