"""Stand-in Anthropic client for PROCUREBOT_DEMO_MODE=1.

Goal: let someone clone the repo and chat with the bot in a browser without
needing an Anthropic API key. The chat UI is identical to the live version —
same tool calls, same audit log, same `[tool]` boxes — but every "Claude"
response is computed by code in this file.

Scenarios it recognises (driven by keywords in the user's message):
  1. supplier_lookup  — "Is AeroTech an approved supplier?"
  2. suspended        — anything about Omega Fluid Systems
  3. initial_po       — "raise a PO for 50 units of … at SGD 1,200 each"
  4. confirm_po       — "yes please raise it" (after initial_po)
  5. over_threshold   — Global Avionics / Avionics Control Module
  6. unknown_supplier — anything about FastParts Co.
Anything else gets a friendly "demo mode" hint listing the 5 scenarios.

The agent loop in `agent.py` calls `client.messages.create()` once per turn of
its tool-use loop. We compute the next response dynamically from the full
message history each time, rather than pre-scripting, so the final reply can
reference real tool results (e.g. the actual PO number returned by create_po).
"""
from __future__ import annotations

import itertools
import json
import re
from dataclasses import dataclass
from typing import Any

_id_counter = itertools.count(1)


def _new_id() -> str:
    return f"toolu_demo_{next(_id_counter):04d}"


@dataclass
class _FakeResponse:
    content: list[dict[str, Any]]
    stop_reason: str


# ---------------------------------------------------------------------------
# History inspection helpers
# ---------------------------------------------------------------------------


def _first_user_text(history: list[dict]) -> str:
    for msg in history:
        if msg.get("role") == "user" and isinstance(msg.get("content"), str):
            return msg["content"]
    return ""


def _last_user_text(history: list[dict]) -> str:
    for msg in reversed(history):
        if msg.get("role") == "user" and isinstance(msg.get("content"), str):
            return msg["content"]
    return ""


def _all_user_texts(history: list[dict]) -> list[str]:
    return [
        m["content"]
        for m in history
        if m.get("role") == "user" and isinstance(m.get("content"), str)
    ]


def _completed_tool_calls(history: list[dict]) -> list[tuple[str, dict]]:
    """List of (tool_name, parsed_result) for every tool that has already run."""
    out: list[tuple[str, dict]] = []
    tool_use_by_id: dict[str, str] = {}
    for msg in history:
        if msg.get("role") == "assistant" and isinstance(msg.get("content"), list):
            for blk in msg["content"]:
                if blk.get("type") == "tool_use":
                    tool_use_by_id[blk["id"]] = blk["name"]
        elif msg.get("role") == "user" and isinstance(msg.get("content"), list):
            for blk in msg["content"]:
                if blk.get("type") == "tool_result":
                    name = tool_use_by_id.get(blk["tool_use_id"], "?")
                    try:
                        result = json.loads(blk.get("content", "{}"))
                    except Exception:
                        result = {}
                    out.append((name, result))
    return out


def _names_called(history: list[dict]) -> set[str]:
    return {name for name, _ in _completed_tool_calls(history)}


def _result_for(history: list[dict], tool_name: str) -> dict | None:
    """Return the most recent result for a given tool, if any."""
    for name, result in reversed(_completed_tool_calls(history)):
        if name == tool_name:
            return result
    return None


# ---------------------------------------------------------------------------
# Natural-language parsing
# ---------------------------------------------------------------------------


def _classify(text: str) -> str:
    t = text.lower()
    if "fastparts" in t:
        return "unknown_supplier"
    if "omega" in t:
        return "suspended"
    if "global avionics" in t or "avionics control module" in t:
        return "over_threshold"
    if re.search(
        r"\b(yes|confirm|raise it|go ahead|do it|proceed|sure|ok|okay|please raise|raise the po|raise it now)\b",
        t,
    ):
        return "confirm_po"
    if (
        re.search(r"\b\d+\s*units?\b", t)
        or "raise a po" in t
        or "raise po" in t
        or "purchase order" in t
        or "create a po" in t
        or "create po" in t
        or ("po for" in t and re.search(r"\d", t))
    ):
        return "initial_po"
    if "aerotech" in t:
        return "supplier_lookup_aerotech"
    if "supplier" in t and "list" in t:
        return "list_suppliers"
    return "default"


def _supplier_in_text(text: str) -> str:
    t = text.lower()
    if "aerotech" in t:
        return "AeroTech Components"
    if "omega" in t:
        return "Omega Fluid Systems"
    if "global avionics" in t:
        return "Global Avionics"
    if "fastparts" in t:
        return "FastParts Co."
    if "precision hydraulics" in t:
        return "Precision Hydraulics"
    return "AeroTech Components"


def _extract_po(text: str) -> dict:
    qty = 50
    unit = 1200.0
    part = "HYD-7742-A"
    delivery = "2026-06-30"

    m = re.search(r"(\d+)\s*units?\b", text, re.I)
    if m:
        qty = int(m.group(1))

    m = re.search(r"sgd\s*([\d,]+(?:\.\d+)?)", text, re.I)
    if m:
        unit = float(m.group(1).replace(",", ""))
    else:
        m = re.search(r"at\s*\$?\s*([\d,]+(?:\.\d+)?)\s*(?:each|per|sgd)?", text, re.I)
        if m:
            unit = float(m.group(1).replace(",", ""))

    m = re.search(r"\b([A-Z]{2,}-?\d{3,}[A-Z\d\-]*)\b", text)
    if m:
        part = m.group(1)

    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if m:
        delivery = m.group(1)

    return {
        "quantity": qty,
        "unit_price_sgd": unit,
        "part_number": part,
        "delivery_date": delivery,
    }


def _tier_name(total: float) -> str:
    if total < 10_000:
        return "Procurement Officer"
    if total <= 50_000:
        return "Procurement Manager"
    if total <= 100_000:
        return "Head of Procurement"
    return "CFO + Head of Procurement"


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------


def _tool(name: str, args: dict) -> dict:
    return {
        "content": [
            {"type": "tool_use", "id": _new_id(), "name": name, "input": args}
        ],
        "stop_reason": "tool_use",
    }


def _text(t: str) -> dict:
    return {
        "content": [{"type": "text", "text": t}],
        "stop_reason": "end_turn",
    }


def _lookup_reply(result: dict, opener: str = "") -> str:
    if not result or not result.get("found"):
        return (
            f"{opener}\n\n"
            "I couldn't find that supplier in the Approved Supplier Register. "
            "Please contact the procurement team for onboarding."
        ).strip()
    s = result["supplier"]
    certs = ", ".join(s.get("certifications") or []) or "—"
    risks = ", ".join(s.get("risk_flags") or []) or "none"
    return (
        f"{opener}\n\n"
        f"**According to the Approved Supplier Register:**\n"
        f"- Supplier: **{s['name']}**\n"
        f"- Status: **{s['status']}**\n"
        f"- Certifications: {certs}\n"
        f"- On-time delivery: {s['otd_pct']:.0f}%\n"
        f"- Contract expiry: {s['contract_expiry']}\n"
        f"- Contract value: SGD {s['contract_value_sgd']:,.0f}\n"
        f"- Risk flags: {risks}"
    ).strip()


def _default_help() -> str:
    return (
        "**Demo mode is active** — try one of these prompts:\n\n"
        "1. *Is AeroTech Components an approved supplier?*\n"
        "2. *Can I raise a PO for Omega Fluid Systems?*\n"
        "3. *Raise a PO for 50 units of HYD-7742-A from AeroTech at SGD 1,200 each, delivery 2026-06-30*\n"
        "4. *200 units of Avionics Control Module from Global Avionics at SGD 8,500 each*\n"
        "5. *Can I order from FastParts Co.?*"
    )


# ---------------------------------------------------------------------------
# Scenario dispatch
# ---------------------------------------------------------------------------


def _next_response(history: list[dict]) -> dict:
    # Classify on the MOST RECENT user message so confirmations etc. are picked
    # up on turn 2. Earlier messages are still scanned by individual scenarios
    # that need to recover context (e.g. confirm_po reads the prior PO details).
    user_text = _last_user_text(history)
    scenario = _classify(user_text)
    called = _names_called(history)

    # ---- supplier lookup (AeroTech) ----
    if scenario == "supplier_lookup_aerotech":
        if "lookup_supplier" not in called:
            return _tool("lookup_supplier", {"name": _supplier_in_text(user_text)})
        return _text(_lookup_reply(_result_for(history, "lookup_supplier")))

    # ---- suspended (Omega) ----
    if scenario == "suspended":
        if "lookup_supplier" not in called:
            return _tool("lookup_supplier", {"name": "Omega Fluid Systems"})
        result = _result_for(history, "lookup_supplier") or {}
        sup = (result.get("supplier") or {}).get("name", "Omega Fluid Systems")
        return _text(
            f"⚠️ **{sup} is currently Suspended** and cannot receive Purchase Orders.\n\n"
            "According to the Approved Supplier Register, the suspension was triggered by QC failures and is under review.\n\n"
            "Please contact the **Head of Procurement** before proceeding."
        )

    # ---- unknown supplier (FastParts) ----
    if scenario == "unknown_supplier":
        if "lookup_supplier" not in called:
            return _tool("lookup_supplier", {"name": "FastParts Co."})
        return _text(
            "I couldn't find **FastParts Co.** in the Approved Supplier Register.\n\n"
            "Please contact the **procurement team** to begin supplier onboarding before any orders can be placed."
        )

    # ---- over-threshold (Global Avionics) ----
    if scenario == "over_threshold":
        details = _extract_po(user_text)
        if details["quantity"] == 50:
            details["quantity"] = 200
        if details["unit_price_sgd"] == 1200.0:
            details["unit_price_sgd"] = 8500.0
        total = details["quantity"] * details["unit_price_sgd"]

        if "lookup_supplier" not in called:
            return _tool("lookup_supplier", {"name": "Global Avionics"})
        if "calculate_po_total" not in called:
            return _tool(
                "calculate_po_total",
                {"quantity": details["quantity"], "unit_price_sgd": details["unit_price_sgd"]},
            )
        if "get_approval_tier" not in called:
            return _tool("get_approval_tier", {"total_sgd": total})
        return _text(
            f"The total PO value is **SGD {total:,.0f}**, which exceeds the **SGD 100,000** threshold.\n\n"
            "I cannot raise this PO. Please submit an **emergency approval form** to the **CFO and Head of Procurement** for review."
        )

    # ---- initial PO (collect, calculate, confirm) ----
    if scenario == "initial_po":
        details = _extract_po(user_text)
        sup = _supplier_in_text(user_text)
        total = details["quantity"] * details["unit_price_sgd"]

        if "lookup_supplier" not in called:
            return _tool("lookup_supplier", {"name": sup})
        if "calculate_po_total" not in called:
            return _tool(
                "calculate_po_total",
                {"quantity": details["quantity"], "unit_price_sgd": details["unit_price_sgd"]},
            )
        if "get_approval_tier" not in called:
            return _tool("get_approval_tier", {"total_sgd": total})

        return _text(
            f"According to the Approved Supplier Register, **{sup}** is **Active** and ready to receive orders.\n\n"
            f"**Purchase Order Summary**\n"
            f"- Supplier: {sup}\n"
            f"- Part: {details['part_number']}\n"
            f"- Quantity: {details['quantity']}\n"
            f"- Unit price: SGD {details['unit_price_sgd']:,.2f}\n"
            f"- Delivery: {details['delivery_date']}\n"
            f"- **Total: SGD {total:,.2f}**\n\n"
            f"Approval required: **{_tier_name(total)}**.\n\n"
            "Shall I raise this PO now? Reply *yes* to confirm."
        )

    # ---- confirmation (raise the PO) ----
    if scenario == "confirm_po":
        # Recover details from the user's earlier initial_po message
        prior = next(
            (
                t
                for t in _all_user_texts(history)
                if re.search(r"\b\d+\s*units?\b", t, re.I)
            ),
            None,
        )
        if not prior:
            return _text(
                "I don't have a pending PO to raise yet. Could you describe what you'd like to order?\n\n"
                + _default_help()
            )
        details = _extract_po(prior)
        sup = _supplier_in_text(prior)

        if "create_po" not in called:
            return _tool(
                "create_po",
                {"supplier_name": sup, **details},
            )

        create_result = _result_for(history, "create_po") or {}
        po = create_result.get("po") or {}
        po_number = po.get("po_number", "PO-DEMO")

        if "send_confirmation_email" not in called:
            return _tool(
                "send_confirmation_email",
                {
                    "po_number": po_number,
                    "recipient": "procurement@example.com",
                    "summary": f"{details['quantity']} x {details['part_number']} from {sup}",
                },
            )

        return _text(
            f"✅ **Purchase Order {po_number} raised successfully.**\n\n"
            f"- Supplier: {sup}\n"
            f"- Part: {details['part_number']}\n"
            f"- Quantity: {details['quantity']}\n"
            f"- Total: SGD {po.get('total_sgd', 0):,.2f}\n"
            f"- Approval tier: {po.get('approval_tier', '—')}\n\n"
            "A confirmation email has been sent."
        )

    # ---- fallback ----
    return _text(_default_help())


# ---------------------------------------------------------------------------
# Public API — duck-types `anthropic.Anthropic`
# ---------------------------------------------------------------------------


class _Messages:
    def __init__(self, parent: "DemoClient") -> None:
        self.parent = parent

    def create(self, **kwargs: Any) -> _FakeResponse:
        history = kwargs.get("messages", [])
        decision = _next_response(history)
        return _FakeResponse(
            content=decision["content"],
            stop_reason=decision["stop_reason"],
        )


class DemoClient:
    """Drop-in replacement for `anthropic.Anthropic` in demo mode."""

    def __init__(self) -> None:
        self.messages = _Messages(self)
