"""Slide-26 deck scenarios, end-to-end through the agent loop with a fake LLM.

The fake Claude is scripted to call exactly the tools we expect. Each scenario
asserts:
  1. the right tools were called with the right arguments
  2. the tool results match deck expectations
  3. the final assistant reply contains the right user-facing wording
"""
from procurebot import agent
from procurebot.models import PurchaseOrder

from .fake_anthropic import FakeAnthropic


# ---------------------------------------------------------------------------
# Test 1 — Knowledge lookup
# ---------------------------------------------------------------------------

def test_t1_knowledge_lookup(db_session):
    fake = FakeAnthropic().script(
        [("tool_use", {"name": "lookup_supplier", "input": {"name": "AeroTech Components"}})],
        "According to the Approved Supplier Register, AeroTech Components is Active "
        "(ISO 9001, AS9100D), OTD 96%, contract expires 2027-04-30.",
    )
    out = agent.chat(db_session, user_message="Is AeroTech Components an approved supplier?", client=fake)

    names = [c["name"] for c in out["tool_calls"]]
    assert names == ["lookup_supplier"]
    assert out["tool_calls"][0]["result"]["found"] is True
    assert "AeroTech" in out["reply"]
    assert "Active" in out["reply"]


# ---------------------------------------------------------------------------
# Test 2 — Risk flag (Suspended supplier)
# ---------------------------------------------------------------------------

def test_t2_risk_flag_suspended(db_session):
    fake = FakeAnthropic().script(
        [("tool_use", {"name": "lookup_supplier", "input": {"name": "Omega Fluid Systems"}})],
        "Omega Fluid Systems is currently Suspended and cannot receive POs. "
        "Please contact the Head of Procurement.",
    )
    out = agent.chat(db_session, user_message="Can I raise a PO for Omega Fluid Systems?", client=fake)

    assert out["tool_calls"][0]["result"]["supplier"]["status"] == "Suspended"
    # Crucial: bot must NOT have called create_po
    assert all(c["name"] != "create_po" for c in out["tool_calls"])
    assert "Suspended" in out["reply"] or "suspended" in out["reply"]
    assert "Head of Procurement" in out["reply"]


# ---------------------------------------------------------------------------
# Test 3 — Raise PO under threshold (50 x SGD 1,200 = SGD 60,000)
# ---------------------------------------------------------------------------

def test_t3_raise_po_under_threshold(db_session):
    fake = FakeAnthropic().script(
        # 1) lookup
        [("tool_use", {"name": "lookup_supplier", "input": {"name": "AeroTech Components"}})],
        # 2) calculate
        [("tool_use", {"name": "calculate_po_total", "input": {"quantity": 50, "unit_price_sgd": 1200}})],
        # 3) approval tier
        [("tool_use", {"name": "get_approval_tier", "input": {"total_sgd": 60000}})],
        # 4) confirm with user (text only) — in real life user replies; here we
        #    just script the next turn assuming the user has confirmed
        "Total SGD 60,000. Tier: Head of Procurement. Shall I raise this PO now?",
    )
    out = agent.chat(
        db_session,
        user_message=(
            "I need to raise a PO for 50 units of HYD-7742-A from AeroTech at "
            "SGD 1,200 each, delivery by 2026-06-30."
        ),
        client=fake,
    )
    names = [c["name"] for c in out["tool_calls"]]
    assert names == ["lookup_supplier", "calculate_po_total", "get_approval_tier"]
    assert out["tool_calls"][1]["result"]["total_sgd"] == 60_000
    assert out["tool_calls"][2]["result"]["tier"] == "Head of Procurement"

    # Now the user confirms. Script the create_po + email + final reply.
    fake.script(
        [
            (
                "tool_use",
                {
                    "name": "create_po",
                    "input": {
                        "supplier_name": "AeroTech Components",
                        "part_number": "HYD-7742-A",
                        "quantity": 50,
                        "unit_price_sgd": 1200,
                        "delivery_date": "2026-06-30",
                    },
                },
            )
        ],
        [
            (
                "tool_use",
                {
                    "name": "send_confirmation_email",
                    "input": {
                        "po_number": "PO-PLACEHOLDER",  # the agent should use the real one returned
                        "recipient": "user@example.com",
                    },
                },
            )
        ],
        "PO raised successfully. A confirmation email has been sent.",
    )
    out2 = agent.chat(db_session, user_message="Yes, please raise it.", session_id=out["session_id"], client=fake)
    create_calls = [c for c in out2["tool_calls"] if c["name"] == "create_po"]
    assert create_calls and create_calls[0]["result"]["ok"] is True

    # Verify the row landed in the DB
    pos = db_session.query(PurchaseOrder).all()
    assert len(pos) == 1
    assert pos[0].total_sgd == 60_000
    assert pos[0].approval_tier == "Head of Procurement"


# ---------------------------------------------------------------------------
# Test 4 — Over threshold (200 x SGD 8,500 = SGD 1,700,000)
# ---------------------------------------------------------------------------

def test_t4_over_threshold_blocked(db_session):
    fake = FakeAnthropic().script(
        [("tool_use", {"name": "lookup_supplier", "input": {"name": "Global Avionics"}})],
        [("tool_use", {"name": "calculate_po_total", "input": {"quantity": 200, "unit_price_sgd": 8500}})],
        [("tool_use", {"name": "get_approval_tier", "input": {"total_sgd": 1700000}})],
        "Total SGD 1,700,000 — this exceeds the SGD 100,000 threshold. "
        "I cannot raise this PO. Please submit an emergency approval form to the "
        "CFO and Head of Procurement.",
    )
    out = agent.chat(
        db_session,
        user_message=(
            "I need to raise a PO for 200 units of Avionics Control Module from "
            "Global Avionics at SGD 8,500 each."
        ),
        client=fake,
    )
    tier = out["tool_calls"][2]["result"]
    assert tier["tier"] == "CFO + Head of Procurement"
    assert tier["can_raise"] is False
    # Bot must NOT call create_po
    assert all(c["name"] != "create_po" for c in out["tool_calls"])
    assert "CFO" in out["reply"] or "emergency" in out["reply"].lower()
    # And no PO row was created
    assert db_session.query(PurchaseOrder).count() == 0


# ---------------------------------------------------------------------------
# Test 5 — Unknown supplier
# ---------------------------------------------------------------------------

def test_t5_unknown_supplier(db_session):
    fake = FakeAnthropic().script(
        [("tool_use", {"name": "lookup_supplier", "input": {"name": "FastParts Co."}})],
        "FastParts Co. is not in the Approved Supplier Register. Please contact "
        "the procurement team.",
    )
    out = agent.chat(db_session, user_message="Can I order from FastParts Co.?", client=fake)
    assert out["tool_calls"][0]["result"]["found"] is False
    assert "procurement team" in out["reply"].lower()
    assert all(c["name"] != "create_po" for c in out["tool_calls"])
