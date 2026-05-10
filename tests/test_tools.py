"""Tool-level tests — these don't touch Claude at all."""
from procurebot import tools


def test_lookup_supplier_active(db_session):
    out = tools.lookup_supplier(db_session, "AeroTech Components")
    assert out["found"] is True
    assert out["supplier"]["status"] == "Active"
    assert "AS9100D" in out["supplier"]["certifications"]


def test_lookup_supplier_unknown(db_session):
    out = tools.lookup_supplier(db_session, "FastParts Co.")
    assert out["found"] is False
    assert "not found" in out["message"].lower()


def test_lookup_supplier_partial_match(db_session):
    out = tools.lookup_supplier(db_session, "aerotech")
    assert out["found"] is True
    assert out["supplier"]["name"] == "AeroTech Components"


def test_calculate_po_total():
    out = tools.calculate_po_total(50, 1200)
    assert out["total_sgd"] == 60_000


def test_approval_tier_below_10k():
    assert tools.get_approval_tier(9_999)["tier"] == "Procurement Officer"
    assert tools.get_approval_tier(9_999)["can_raise"] is True


def test_approval_tier_manager():
    assert tools.get_approval_tier(10_000)["tier"] == "Procurement Manager"
    assert tools.get_approval_tier(50_000)["tier"] == "Procurement Manager"


def test_approval_tier_head():
    assert tools.get_approval_tier(50_001)["tier"] == "Head of Procurement"
    assert tools.get_approval_tier(100_000)["tier"] == "Head of Procurement"


def test_approval_tier_blocked():
    out = tools.get_approval_tier(100_001)
    assert out["tier"] == "CFO + Head of Procurement"
    assert out["can_raise"] is False


def test_create_po_blocks_suspended(db_session):
    out = tools.create_po(
        db_session,
        supplier_name="Omega Fluid Systems",
        part_number="X-1",
        quantity=1,
        unit_price_sgd=10,
        delivery_date="2026-09-01",
    )
    assert out["ok"] is False
    assert out["reason"] == "supplier_suspended"


def test_create_po_blocks_over_threshold(db_session):
    out = tools.create_po(
        db_session,
        supplier_name="Global Avionics",
        part_number="ACM-1",
        quantity=200,
        unit_price_sgd=8_500,
        delivery_date="2026-08-01",
    )
    assert out["ok"] is False
    assert out["reason"] == "over_threshold"
    assert out["total_sgd"] == 1_700_000


def test_create_po_success(db_session):
    out = tools.create_po(
        db_session,
        supplier_name="AeroTech Components",
        part_number="HYD-7742-A",
        quantity=50,
        unit_price_sgd=1_200,
        delivery_date="2026-06-30",
    )
    assert out["ok"] is True
    assert out["po"]["total_sgd"] == 60_000
    assert out["po"]["approval_tier"] == "Head of Procurement"
    assert out["po"]["po_number"].startswith("PO-")
