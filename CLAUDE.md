# CLAUDE.md — ProcureBot

This file binds future Claude Code sessions to the project's spec. Read this
first before changing code.

## Source of truth

The training deck at `docs/Copilot_AI_Builder_Power_Automate.pptx`. Specifically:
- **Slides 11–14** — the ProcureBot system prompt (Role, Raise-PO workflow,
  Behaviour Rules, Escalation, Welcome).
- **Slide 13** — the 4-tier approval matrix.
- **Slide 26** — the 5 acceptance test cases.

If the deck and the code disagree, **the deck wins**. Update `procurebot/prompt.py`
and `tests/test_scenarios.py` together — never one without the other.

## Binding rules (do not relax these)

1. **Supplier check first.** The agent must call `lookup_supplier` before any
   PO step. Tests 1, 2, 3, 4, 5 all assert this.
2. **Suspended → refuse.** Never call `create_po` for a Suspended supplier.
   `tools.create_po` enforces this server-side as a defence-in-depth.
3. **Over SGD 100,000 → refuse.** `tools.create_po` returns
   `{ok: False, reason: "over_threshold"}` for totals over 100k. The agent
   must direct the user to the emergency approval form (CFO + Head of
   Procurement).
4. **Cite the register.** When answering from supplier data, the bot says
   "According to the Approved Supplier Register…".
5. **Stay in scope.** Out-of-scope questions get the canned redirect from the
   deck.

## Architecture (one-liner per layer)

| Layer    | File(s)                            | Purpose                                  |
|----------|------------------------------------|------------------------------------------|
| Data     | `db.py`, `models.py`, `seed.py`    | SQLite + Supplier/PO/AuditLog tables     |
| Tools    | `tools.py`, `email_stub.py`        | 6 tool functions + Anthropic schemas     |
| Brain    | `prompt.py`, `agent.py`            | System prompt + Claude tool-use loop     |
| Surface  | `main.py`, `static/`               | FastAPI + browser chat UI                |
| Tests    | `tests/`                           | Tool tests + 5 deck scenarios            |

The Anthropic client is injected into `agent.chat(...)` as `client=`. Tests pass
`tests/fake_anthropic.FakeAnthropic` so they run with no API key.

## Conventions

- Money is SGD. Always store and display floats; never integers.
- Dates are ISO `YYYY-MM-DD` at the API boundary; SQLAlchemy `Date` internally.
- New tools: add to `tools.TOOL_SCHEMAS`, add a branch in `tools.dispatch`,
  and add a tool-level test in `tests/test_tools.py`.
- Keep `prompt.SYSTEM_PROMPT` close to the deck wording. The "Tool Use" addendum
  at the bottom is the only block we may freely edit.

## Run

```sh
.venv/bin/pytest                                           # all tests, no key needed
.venv/bin/uvicorn procurebot.main:app --reload --port 8000 # live UI, needs ANTHROPIC_API_KEY
```
