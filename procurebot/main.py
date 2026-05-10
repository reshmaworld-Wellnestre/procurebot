"""FastAPI app — chat endpoint + static UI mount."""
from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent
from .db import SessionLocal, init_db
from .prompt import WELCOME_MESSAGE
from .seed import seed

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"

app = FastAPI(title="ProcureBot")


@app.on_event("startup")
def _startup() -> None:
    init_db()
    inserted = seed()
    logging.getLogger("procurebot").info("startup: seeded %d new suppliers", inserted)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


class ChatIn(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None


class ChatOut(BaseModel):
    session_id: str
    reply: str
    tool_calls: list[dict] = []


@app.post("/api/chat", response_model=ChatOut)
def api_chat(payload: ChatIn) -> ChatOut:
    db = SessionLocal()
    try:
        result = agent.chat(
            db,
            user_message=payload.message,
            session_id=payload.session_id,
        )
        return ChatOut(**result)
    except Exception as exc:  # pragma: no cover
        logging.exception("chat failed")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        db.close()


@app.get("/api/welcome")
def api_welcome() -> dict:
    return {"message": WELCOME_MESSAGE}


@app.get("/api/suppliers")
def api_suppliers() -> dict:
    """Read-only — handy for the UI to show a list. Not used by the agent."""
    from .models import Supplier
    db = SessionLocal()
    try:
        rows = db.query(Supplier).order_by(Supplier.name).all()
        return {"suppliers": [s.to_dict() for s in rows]}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def root() -> FileResponse:
    index = STATIC_DIR / "index.html"
    if not index.exists():  # pragma: no cover
        raise HTTPException(status_code=404, detail="UI not built")
    return FileResponse(index)
