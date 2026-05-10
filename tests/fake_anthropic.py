"""A scriptable fake Anthropic client for tests.

You construct one with a list of canned responses. Each `messages.create` call
pops the next response. A response is either:
  - a string  -> a single text block, stop_reason='end_turn'
  - a list of (kind, payload) tuples, where kind is 'text' or 'tool_use'
    'text'     payload = the string
    'tool_use' payload = dict with keys 'name', 'input', and optional 'id'
    If any tool_use blocks are present, stop_reason='tool_use'; otherwise 'end_turn'.

The fake records every call's `messages` argument so tests can assert what
was sent (e.g., that tool_result blocks made it back into the conversation).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any


_id_counter = itertools.count(1)


def _new_id() -> str:
    return f"toolu_{next(_id_counter):04d}"


@dataclass
class FakeResponse:
    content: list[dict[str, Any]]
    stop_reason: str


@dataclass
class FakeMessages:
    parent: "FakeAnthropic"

    def create(self, **kwargs: Any) -> FakeResponse:
        self.parent.calls.append(kwargs)
        if not self.parent.scripted:
            raise AssertionError("FakeAnthropic ran out of scripted responses")
        spec = self.parent.scripted.pop(0)

        if isinstance(spec, str):
            return FakeResponse(
                content=[{"type": "text", "text": spec}],
                stop_reason="end_turn",
            )

        blocks: list[dict[str, Any]] = []
        any_tool = False
        for kind, payload in spec:
            if kind == "text":
                blocks.append({"type": "text", "text": payload})
            elif kind == "tool_use":
                any_tool = True
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": payload.get("id") or _new_id(),
                        "name": payload["name"],
                        "input": payload.get("input", {}),
                    }
                )
            else:
                raise ValueError(f"unknown block kind {kind!r}")
        return FakeResponse(
            content=blocks,
            stop_reason="tool_use" if any_tool else "end_turn",
        )


@dataclass
class FakeAnthropic:
    scripted: list[Any] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.messages = FakeMessages(parent=self)

    def script(self, *responses: Any) -> "FakeAnthropic":
        self.scripted.extend(responses)
        return self
