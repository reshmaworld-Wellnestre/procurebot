"""Exercise the DemoClient through the agent loop — no API calls.

These tests are what CI uses to prove that anyone can clone the repo and run
the bot in DEMO_MODE without an Anthropic API key.
"""
from procurebot import agent
from procurebot.demo_client import DemoClient
from procurebot.models import PurchaseOrder


def _chat(db, msg, session_id=None):
    return agent.chat(db, user_message=msg, session_id=session_id, client=DemoClient())


def test_demo_supplier_lookup(db_session):
    out = _chat(db_session, "Is AeroTech Components an approved supplier?")
    names = [c["name"] for c in out["tool_calls"]]
    assert "lookup_supplier" in names
    assert "AeroTech" in out["reply"]
    assert "Active" in out["reply"]


def test_demo_suspended_refuses(db_session):
    out = _chat(db_session, "Can I raise a PO for Omega Fluid Systems?")
    names = [c["name"] for c in out["tool_calls"]]
    assert "lookup_supplier" in names
    assert "create_po" not in names
    assert "Suspended" in out["reply"]
    assert "Head of Procurement" in out["reply"]


def test_demo_unknown_supplier(db_session):
    out = _chat(db_session, "Can I order from FastParts Co.?")
    assert "couldn't find" in out["reply"].lower() or "not found" in out["reply"].lower()
    assert "procurement team" in out["reply"].lower()


def test_demo_over_threshold(db_session):
    out = _chat(
        db_session,
        "I need to raise a PO for 200 units of Avionics Control Module from "
        "Global Avionics at SGD 8,500 each, delivery 2026-08-01.",
    )
    tier_calls = [c for c in out["tool_calls"] if c["name"] == "get_approval_tier"]
    assert tier_calls and tier_calls[0]["result"]["can_raise"] is False
    assert "create_po" not in [c["name"] for c in out["tool_calls"]]
    assert "100,000" in out["reply"] or "emergency" in out["reply"].lower()
    assert db_session.query(PurchaseOrder).count() == 0


def test_demo_full_po_flow(db_session):
    out = _chat(
        db_session,
        "I need to raise a PO for 50 units of HYD-7742-A from AeroTech at "
        "SGD 1,200 each, delivery by 2026-06-30.",
    )
    names = [c["name"] for c in out["tool_calls"]]
    assert names[:3] == ["lookup_supplier", "calculate_po_total", "get_approval_tier"]
    assert out["tool_calls"][1]["result"]["total_sgd"] == 60_000
    assert "Shall I raise" in out["reply"]

    # User confirms — same session
    out2 = _chat(db_session, "Yes please raise it.", session_id=out["session_id"])
    names2 = [c["name"] for c in out2["tool_calls"]]
    assert "create_po" in names2
    assert "send_confirmation_email" in names2

    rows = db_session.query(PurchaseOrder).all()
    assert len(rows) == 1
    assert rows[0].total_sgd == 60_000
    assert rows[0].approval_tier == "Head of Procurement"
    assert rows[0].po_number in out2["reply"]


def test_demo_default_help(db_session):
    out = _chat(db_session, "Tell me a joke")
    assert "demo mode" in out["reply"].lower()
    assert "AeroTech" in out["reply"]
    assert out["tool_calls"] == []
