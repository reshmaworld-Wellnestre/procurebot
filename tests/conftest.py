"""Per-test in-memory SQLite + seeded suppliers.

We patch the engine in `procurebot.db` to point at an in-memory DB before any
models are imported by the code under test.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from procurebot import db as db_module
from procurebot.db import Base
from procurebot.seed import seed


@pytest.fixture(autouse=True)
def _reset_session_state():
    """Tests must not share in-memory chat sessions."""
    from procurebot import agent
    agent._SESSIONS.clear()
    yield
    agent._SESSIONS.clear()


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)

    # swap module-level engine + factory so seed() and the agent both use this DB
    orig_engine = db_module.engine
    orig_factory = db_module.SessionLocal
    db_module.engine = engine
    db_module.SessionLocal = SessionLocal

    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    seed(s)

    try:
        yield s
    finally:
        s.close()
        db_module.engine = orig_engine
        db_module.SessionLocal = orig_factory
