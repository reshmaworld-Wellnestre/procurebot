"""Multi-turn agent loop using Anthropic tool-use.

Flow per user message:
  1. Append user message to the session history.
  2. Call Anthropic with system prompt + history + tool schemas.
  3. If the response is `tool_use`, run each tool via tools.dispatch, append
     a tool_result block, and loop back to step 2.
  4. When the response is `end_turn`, append the assistant text to history
     and return it to the caller.

History is per-session, kept in memory. Every turn and every tool call is
appended to the audit_log table in the DB.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.orm import Session

from .models import AuditLog
from .prompt import SYSTEM_PROMPT
from .tools import TOOL_SCHEMAS, dispatch

logger = logging.getLogger("procurebot.agent")

DEFAULT_MODEL = os.environ.get("PROCUREBOT_MODEL", "claude-opus-4-7")
MAX_TOOL_ITERATIONS = 8


# ---------------------------------------------------------------------------
# Anthropic client protocol — lets tests inject a fake.
# ---------------------------------------------------------------------------


class AnthropicLike(Protocol):
    class messages:  # noqa: D106 — structural typing
        @staticmethod
        def create(**kwargs: Any) -> Any: ...


def _real_client():  # pragma: no cover — exercised via the live UI, not tests
    from anthropic import Anthropic
    return Anthropic()


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


@dataclass
class Session_:
    session_id: str
    history: list[dict[str, Any]] = field(default_factory=list)


_SESSIONS: dict[str, Session_] = {}


def get_or_create_session(session_id: str | None = None) -> Session_:
    sid = session_id or uuid.uuid4().hex[:12]
    if sid not in _SESSIONS:
        _SESSIONS[sid] = Session_(session_id=sid)
    return _SESSIONS[sid]


def reset_session(session_id: str) -> None:
    _SESSIONS.pop(session_id, None)


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def _audit(db: Session, session_id: str, kind: str, payload: dict[str, Any]) -> None:
    db.add(AuditLog(session_id=session_id, kind=kind, payload=json.dumps(payload, default=str)))
    db.commit()


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def chat(
    db: Session,
    *,
    user_message: str,
    session_id: str | None = None,
    client: Any | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 1024,
) -> dict[str, Any]:
    """Run one user turn. Returns {session_id, reply, tool_calls}."""
    sess = get_or_create_session(session_id)
    if client is None:
        client = _real_client()

    sess.history.append({"role": "user", "content": user_message})
    _audit(db, sess.session_id, "chat", {"role": "user", "text": user_message})

    tool_calls: list[dict[str, Any]] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=sess.history,
        )

        # Append the assistant turn (verbatim content blocks) to history.
        assistant_blocks = _normalise_content(response.content)
        sess.history.append({"role": "assistant", "content": assistant_blocks})

        # Collect any tool_use blocks.
        tool_uses = [b for b in assistant_blocks if b.get("type") == "tool_use"]

        if response.stop_reason != "tool_use" or not tool_uses:
            text = _extract_text(assistant_blocks)
            _audit(db, sess.session_id, "chat", {"role": "assistant", "text": text})
            return {
                "session_id": sess.session_id,
                "reply": text,
                "tool_calls": tool_calls,
            }

        # Execute each tool call and build tool_result blocks for the next turn.
        tool_result_blocks: list[dict[str, Any]] = []
        for tu in tool_uses:
            name = tu["name"]
            args = tu.get("input", {}) or {}
            logger.info("tool_call %s args=%s", name, args)
            result = dispatch(db, name, args)
            tool_calls.append({"name": name, "input": args, "result": result})
            _audit(
                db,
                sess.session_id,
                "tool_call",
                {"name": name, "input": args, "result": result},
            )
            tool_result_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": json.dumps(result, default=str),
                }
            )

        sess.history.append({"role": "user", "content": tool_result_blocks})

    # Safety: too many tool iterations
    fallback = (
        "I hit my tool-call limit while processing that. Please rephrase or "
        "break the request into smaller steps."
    )
    sess.history.append({"role": "assistant", "content": fallback})
    _audit(db, sess.session_id, "chat", {"role": "assistant", "text": fallback, "truncated": True})
    return {"session_id": sess.session_id, "reply": fallback, "tool_calls": tool_calls}


# ---------------------------------------------------------------------------
# Content helpers — Anthropic SDK returns objects, but tests pass plain dicts.
# ---------------------------------------------------------------------------


def _normalise_content(content: Any) -> list[dict[str, Any]]:
    """Convert Anthropic SDK content blocks (objects or dicts) into plain dicts."""
    blocks: list[dict[str, Any]] = []
    for b in content:
        if isinstance(b, dict):
            blocks.append(b)
            continue
        # SDK object — duck-type it
        block_type = getattr(b, "type", None)
        if block_type == "text":
            blocks.append({"type": "text", "text": getattr(b, "text", "")})
        elif block_type == "tool_use":
            blocks.append(
                {
                    "type": "tool_use",
                    "id": getattr(b, "id", ""),
                    "name": getattr(b, "name", ""),
                    "input": getattr(b, "input", {}) or {},
                }
            )
        else:
            # Fallback — best-effort dictify
            blocks.append({"type": block_type or "unknown", "raw": str(b)})
    return blocks


def _extract_text(blocks: list[dict[str, Any]]) -> str:
    parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
    return "\n".join(p for p in parts if p).strip()
