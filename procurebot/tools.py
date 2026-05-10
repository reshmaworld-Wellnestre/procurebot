"""Tool functions exposed to the Claude agent.

Each tool has:
  - a Python implementation that takes a SQLAlchemy session + JSON-able args and
    returns a JSON-able dict
  - a JSON schema entry in `TOOL_SCHEMAS` for Anthropic tool-use

Approval rules (slide 13):
  Below SGD 10,000     -> Procurement Officer        -> proceed
  SGD 10,000-50,000    -> Procurement Manager        -> confirm approver before raising
  SGD 50,001-100,000   -> Head of Procurement        -> confirm approver before raising
  Above SGD 100,000    -> CFO + Head of Procurement  -> do NOT raise (emergency form)
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from random import randint
from typing import Any

from sqlalchemy.orm import Session

from .email_stub import send_email
from .models import PurchaseOrder, Supplier

# ---------------------------------------------------------------------------
# Approval matrix
# ---------------------------------------------------------------------------

BLOCK_THRESHOLD_SGD = 100_000.0


def _approval_tier(total_sgd: float) -> dict[str, Any]:
    if total_sgd < 10_000:
        return {
            "tier": "Procurement Officer",
            "can_raise": True,
            "requires_confirmation": False,
            "action": "Proceed to raise PO",
        }
    if total_sgd <= 50_000:
        return {
            "tier": "Procurement Manager",
            "can_raise": True,
            "requires_confirmation": True,
            "action": "Confirm approver before raising",
        }
    if total_sgd <= 100_000:
        return {
            "tier": "Head of Procurement",
            "can_raise": True,
            "requires_confirmation": True,
            "action": "Confirm approver before raising",
        }
    return {
        "tier": "CFO + Head of Procurement",
        "can_raise": False,
        "requires_confirmation": True,
        "action": "Do NOT raise PO. Instruct user to submit an emergency approval form.",
    }


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def lookup_supplier(db: Session, name: str) -> dict[str, Any]:
    if not name or not name.strip():
        return {"found": False, "query": name, "message": "Supplier name is empty."}
    q = name.strip()
    # exact (case-insensitive) match first
    s = (
        db.query(Supplier)
        .filter(Supplier.name.ilike(q))
        .one_or_none()
    )
    if s is None:
        # fuzzy: substring match
        s = (
            db.query(Supplier)
            .filter(Supplier.name.ilike(f"%{q}%"))
            .first()
        )
    if s is None:
        return {
            "found": False,
            "query": q,
            "message": (
                f"Supplier '{q}' was not found in the Approved Supplier Register. "
                "Direct the user to contact the procurement team."
            ),
        }
    return {"found": True, "query": q, "supplier": s.to_dict()}


def list_suppliers(db: Session, status_filter: str | None = None) -> dict[str, Any]:
    query = db.query(Supplier)
    if status_filter:
        query = query.filter(Supplier.status.ilike(status_filter))
    rows = query.order_by(Supplier.name).all()
    return {"count": len(rows), "suppliers": [s.to_dict() for s in rows]}


def calculate_po_total(quantity: int, unit_price_sgd: float) -> dict[str, Any]:
    if quantity <= 0 or unit_price_sgd < 0:
        return {"error": "Quantity must be positive and unit price non-negative."}
    total = round(float(quantity) * float(unit_price_sgd), 2)
    return {
        "quantity": quantity,
        "unit_price_sgd": unit_price_sgd,
        "total_sgd": total,
    }


def get_approval_tier(total_sgd: float) -> dict[str, Any]:
    return {"total_sgd": float(total_sgd), **_approval_tier(float(total_sgd))}


def _next_po_number(db: Session) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = randint(1000, 9999)
    candidate = f"PO-{today}-{suffix}"
    # collision guard
    while db.query(PurchaseOrder).filter_by(po_number=candidate).first() is not None:
        suffix = randint(1000, 9999)
        candidate = f"PO-{today}-{suffix}"
    return candidate


def create_po(
    db: Session,
    *,
    supplier_name: str,
    part_number: str,
    quantity: int,
    unit_price_sgd: float,
    delivery_date: str,
) -> dict[str, Any]:
    sup_result = lookup_supplier(db, supplier_name)
    if not sup_result["found"]:
        return {
            "ok": False,
            "reason": "supplier_not_found",
            "message": sup_result["message"],
        }
    supplier = (
        db.query(Supplier)
        .filter(Supplier.name == sup_result["supplier"]["name"])
        .one()
    )
    if supplier.status == "Suspended":
        return {
            "ok": False,
            "reason": "supplier_suspended",
            "message": (
                f"{supplier.name} is Suspended and cannot receive POs. "
                "Direct the user to the Head of Procurement."
            ),
        }

    total = round(float(quantity) * float(unit_price_sgd), 2)
    tier = _approval_tier(total)
    if not tier["can_raise"]:
        return {
            "ok": False,
            "reason": "over_threshold",
            "total_sgd": total,
            "approval_tier": tier["tier"],
            "message": tier["action"],
        }

    try:
        delivery = date.fromisoformat(delivery_date)
    except ValueError:
        return {
            "ok": False,
            "reason": "bad_delivery_date",
            "message": "delivery_date must be in YYYY-MM-DD format.",
        }

    po_number = _next_po_number(db)
    po = PurchaseOrder(
        po_number=po_number,
        supplier_id=supplier.id,
        part_number=part_number,
        quantity=int(quantity),
        unit_price_sgd=float(unit_price_sgd),
        total_sgd=total,
        delivery_date=delivery,
        approval_tier=tier["tier"],
        status="Raised" if not tier["requires_confirmation"] else "PendingApproval",
    )
    db.add(po)
    db.commit()
    db.refresh(po)
    return {"ok": True, "po": po.to_dict()}


def send_confirmation_email(
    *, po_number: str, recipient: str, summary: str = ""
) -> dict[str, Any]:
    body_lines = [f"Purchase Order {po_number} has been raised."]
    if summary:
        body_lines.append("")
        body_lines.append(summary)
    payload = send_email(
        to=recipient,
        subject=f"[ProcureBot] PO {po_number} raised",
        body="\n".join(body_lines),
    )
    return {"ok": True, "email": payload}


# ---------------------------------------------------------------------------
# Anthropic tool-use schemas
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "lookup_supplier",
        "description": (
            "Look up a single supplier in the Approved Supplier Register by name. "
            "Returns status, certifications, on-time-delivery %, contract expiry, "
            "contract value, and risk flags. Call this BEFORE any PO step and "
            "whenever the user names a supplier."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Supplier name. Case-insensitive; partial matches are allowed.",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "list_suppliers",
        "description": "List suppliers in the register, optionally filtered by status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status_filter": {
                    "type": "string",
                    "enum": ["Active", "Expiring", "Suspended"],
                    "description": "Optional status filter.",
                },
            },
        },
    },
    {
        "name": "calculate_po_total",
        "description": "Multiply quantity x unit_price_sgd. Always use this instead of computing in-head.",
        "input_schema": {
            "type": "object",
            "properties": {
                "quantity": {"type": "integer", "minimum": 1},
                "unit_price_sgd": {"type": "number", "minimum": 0},
            },
            "required": ["quantity", "unit_price_sgd"],
        },
    },
    {
        "name": "get_approval_tier",
        "description": (
            "Given a PO total in SGD, return the approval tier per the procurement policy: "
            "<10k Procurement Officer, 10k-50k Procurement Manager, 50,001-100k Head of "
            "Procurement, >100k CFO + Head of Procurement (do NOT raise)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"total_sgd": {"type": "number", "minimum": 0}},
            "required": ["total_sgd"],
        },
    },
    {
        "name": "create_po",
        "description": (
            "Create a Purchase Order. Only call AFTER the user has confirmed all "
            "details. The tool refuses to raise POs over SGD 100,000 or for "
            "Suspended suppliers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "supplier_name": {"type": "string"},
                "part_number": {"type": "string"},
                "quantity": {"type": "integer", "minimum": 1},
                "unit_price_sgd": {"type": "number", "minimum": 0},
                "delivery_date": {
                    "type": "string",
                    "description": "ISO date YYYY-MM-DD",
                },
            },
            "required": [
                "supplier_name",
                "part_number",
                "quantity",
                "unit_price_sgd",
                "delivery_date",
            ],
        },
    },
    {
        "name": "send_confirmation_email",
        "description": "Send a PO confirmation email. Call after create_po succeeds.",
        "input_schema": {
            "type": "object",
            "properties": {
                "po_number": {"type": "string"},
                "recipient": {"type": "string"},
                "summary": {"type": "string"},
            },
            "required": ["po_number", "recipient"],
        },
    },
]


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch(db: Session, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run a tool call by name. Returns a JSON-able dict (never raises)."""
    try:
        if name == "lookup_supplier":
            return lookup_supplier(db, arguments.get("name", ""))
        if name == "list_suppliers":
            return list_suppliers(db, arguments.get("status_filter"))
        if name == "calculate_po_total":
            return calculate_po_total(
                int(arguments["quantity"]),
                float(arguments["unit_price_sgd"]),
            )
        if name == "get_approval_tier":
            return get_approval_tier(float(arguments["total_sgd"]))
        if name == "create_po":
            return create_po(
                db,
                supplier_name=arguments["supplier_name"],
                part_number=arguments["part_number"],
                quantity=int(arguments["quantity"]),
                unit_price_sgd=float(arguments["unit_price_sgd"]),
                delivery_date=arguments["delivery_date"],
            )
        if name == "send_confirmation_email":
            return send_confirmation_email(
                po_number=arguments["po_number"],
                recipient=arguments["recipient"],
                summary=arguments.get("summary", ""),
            )
        return {"error": f"Unknown tool: {name}"}
    except Exception as exc:  # boundary — don't crash the agent loop
        return {"error": f"{type(exc).__name__}: {exc}"}
