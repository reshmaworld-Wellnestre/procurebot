from datetime import date
from sqlalchemy.orm import Session

from .db import SessionLocal, init_db
from .models import Supplier

SUPPLIERS = [
    {
        "name": "AeroTech Components",
        "status": "Active",
        "certifications": "ISO 9001, AS9100D",
        "otd_pct": 96.0,
        "contract_expiry": date(2027, 4, 30),
        "contract_value_sgd": 2_400_000.0,
        "risk_flags": "",
        "notes": "Tier-1 hydraulics and structural parts. Preferred supplier.",
    },
    {
        "name": "Omega Fluid Systems",
        "status": "Suspended",
        "certifications": "ISO 9001",
        "otd_pct": 71.0,
        "contract_expiry": date(2026, 9, 15),
        "contract_value_sgd": 850_000.0,
        "risk_flags": "QC failures Q1 2026, suspension under review",
        "notes": "Suspended by Head of Procurement pending QC remediation.",
    },
    {
        "name": "Global Avionics",
        "status": "Active",
        "certifications": "ISO 9001, AS9100D, NADCAP",
        "otd_pct": 94.0,
        "contract_expiry": date(2028, 1, 31),
        "contract_value_sgd": 5_100_000.0,
        "risk_flags": "",
        "notes": "Avionics control modules and instrumentation.",
    },
    {
        "name": "Precision Hydraulics",
        "status": "Expiring",
        "certifications": "ISO 9001",
        "otd_pct": 89.0,
        "contract_expiry": date(2026, 6, 30),
        "contract_value_sgd": 620_000.0,
        "risk_flags": "Contract expires within 60 days",
        "notes": "Renewal under negotiation.",
    },
    {
        "name": "Single-Source Bearings",
        "status": "Active",
        "certifications": "ISO 9001",
        "otd_pct": 92.0,
        "contract_expiry": date(2027, 11, 30),
        "contract_value_sgd": 410_000.0,
        "risk_flags": "Single-source for SKF-7203 series",
        "notes": "Sole supplier — flag risk on every PO.",
    },
    {
        "name": "Sentinel Fasteners",
        "status": "Active",
        "certifications": "ISO 9001",
        "otd_pct": 98.0,
        "contract_expiry": date(2027, 8, 1),
        "contract_value_sgd": 180_000.0,
        "risk_flags": "",
        "notes": "Bolts, nuts, fasteners.",
    },
    {
        "name": "Helix Wire & Cable",
        "status": "Active",
        "certifications": "ISO 9001, UL",
        "otd_pct": 91.0,
        "contract_expiry": date(2027, 2, 28),
        "contract_value_sgd": 295_000.0,
        "risk_flags": "",
        "notes": "Electrical wire, harnesses.",
    },
    {
        "name": "Apex Composites",
        "status": "Active",
        "certifications": "AS9100D",
        "otd_pct": 88.0,
        "contract_expiry": date(2026, 12, 31),
        "contract_value_sgd": 770_000.0,
        "risk_flags": "",
        "notes": "Carbon-fibre and composite panels.",
    },
]


def seed(db: Session | None = None) -> int:
    """Idempotent seed. Returns the number of suppliers inserted."""
    init_db()
    own = db is None
    if own:
        db = SessionLocal()
    try:
        inserted = 0
        for row in SUPPLIERS:
            existing = db.query(Supplier).filter_by(name=row["name"]).one_or_none()
            if existing:
                continue
            db.add(Supplier(**row))
            inserted += 1
        db.commit()
        return inserted
    finally:
        if own:
            db.close()


if __name__ == "__main__":
    n = seed()
    print(f"Seeded {n} new suppliers.")
