from datetime import date, datetime, timezone
from sqlalchemy import String, Integer, Float, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20))  # Active | Expiring | Suspended
    certifications: Mapped[str] = mapped_column(String(200), default="")  # CSV
    otd_pct: Mapped[float] = mapped_column(Float, default=0.0)
    contract_expiry: Mapped[date] = mapped_column(Date)
    contract_value_sgd: Mapped[float] = mapped_column(Float, default=0.0)
    risk_flags: Mapped[str] = mapped_column(String(200), default="")  # CSV; empty if none
    notes: Mapped[str] = mapped_column(String(500), default="")

    pos: Mapped[list["PurchaseOrder"]] = relationship(back_populates="supplier")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "certifications": [c.strip() for c in self.certifications.split(",") if c.strip()],
            "otd_pct": self.otd_pct,
            "contract_expiry": self.contract_expiry.isoformat(),
            "contract_value_sgd": self.contract_value_sgd,
            "risk_flags": [r.strip() for r in self.risk_flags.split(",") if r.strip()],
            "notes": self.notes,
        }


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    part_number: Mapped[str] = mapped_column(String(60))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_sgd: Mapped[float] = mapped_column(Float)
    total_sgd: Mapped[float] = mapped_column(Float)
    delivery_date: Mapped[date] = mapped_column(Date)
    approval_tier: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30))  # Raised | PendingApproval | Blocked
    created_by: Mapped[str] = mapped_column(String(80), default="chat-user")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    supplier: Mapped[Supplier] = relationship(back_populates="pos")

    def to_dict(self) -> dict:
        return {
            "po_number": self.po_number,
            "supplier": self.supplier.name if self.supplier else None,
            "part_number": self.part_number,
            "quantity": self.quantity,
            "unit_price_sgd": self.unit_price_sgd,
            "total_sgd": self.total_sgd,
            "delivery_date": self.delivery_date.isoformat(),
            "approval_tier": self.approval_tier,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # chat | tool_call | po_action | email
    payload: Mapped[str] = mapped_column(Text)
