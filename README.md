# 🛒 ProcureBot — AI Procurement Assistant

![tests](https://github.com/reshmaworld-Wellnestre/procurebot/actions/workflows/test.yml/badge.svg)
![python](https://img.shields.io/badge/python-3.11%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

> A working procurement chatbot built with **Anthropic Claude tool-use**, **FastAPI**,
> and **SQLite**. It looks up approved suppliers, applies a 4-tier approval matrix,
> raises Purchase Orders, and refuses anything risky — all from a chat window.

This project is a **standalone Python implementation** of a procurement bot
specified in a Microsoft Copilot Studio training deck. The deck describes a
no-code Microsoft build (Copilot Studio + SharePoint + Power Automate); this
repo demonstrates how to deliver the same business logic with code, so you
can run it anywhere — laptop, cloud, container — and reuse the pattern for
other internal AI agents.

### What it demonstrates

- **Tool-use / function-calling** with Claude (the model never invents data — it
  calls real Python functions and cites results)
- **Layered architecture** — data, tools, agent, API, UI as separate concerns
- **Policy enforcement in code** — defence-in-depth so the bot can't be jailbroken
  into raising a PO it shouldn't (Suspended supplier, > SGD 100,000)
- **Audit trail** — every chat turn and tool call logged for compliance
- **Test discipline** — the 5 deck acceptance scenarios run as automated tests
  with a fake Claude client, so the suite passes with no API key

### Quick demo

```sh
git clone https://github.com/reshmaworld-Wellnestre/procurebot.git
cd procurebot
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -v               # 22/22 pass — no API key needed
```

### Try it in the browser — two modes

**🎬 Demo mode** — no API key, works offline, uses canned responses:
```sh
PROCUREBOT_DEMO_MODE=1 .venv/bin/uvicorn procurebot.main:app --reload --port 8000
```

**🤖 Live mode** — real Claude responses:
```sh
cp .env.example .env              # then edit .env and paste ANTHROPIC_API_KEY=sk-ant-...
.venv/bin/uvicorn procurebot.main:app --reload --port 8000
```

Open <http://localhost:8000>.

### Try the 5 deck scenarios

| # | Type into the chat | Expected behaviour |
|---|---|---|
| 1 | "Is AeroTech Components an approved supplier?" | Bot reads the register, replies with status + certs + OTD% |
| 2 | "Can I raise a PO for Omega Fluid Systems?" | Refuses — Suspended → redirects to Head of Procurement |
| 3 | "Raise a PO for 50 × HYD-7742-A from AeroTech at SGD 1,200, delivery 2026-06-30" | Calculates SGD 60,000 → confirms → creates PO → returns PO number |
| 4 | "200 × Avionics Control Module from Global Avionics at SGD 8,500" | Calculates SGD 1,700,000 → refuses → emergency form (CFO + Head) |
| 5 | "Can I order from FastParts Co.?" | Not found → redirects to procurement team |

---

## Detailed setup

ProcureBot:
- Looks up suppliers in an Approved Supplier Register (SQLite)
- Calculates PO totals and applies a 4-tier approval matrix
- Raises POs (records to DB) for tiers ≤ Head of Procurement
- Refuses Suspended suppliers and POs > SGD 100,000
- Speaks via FastAPI + a small browser chat UI, powered by Claude tool-use

## Setup

```sh
cd ~/procurebot
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

Python 3.11+ required.

## Run the chat UI

```sh
.venv/bin/uvicorn procurebot.main:app --reload --port 8000
```

Open <http://localhost:8000>. The DB is auto-created and seeded on first run.

## Run the tests (no API key needed)

```sh
.venv/bin/pytest -v
```

The test suite uses a fake Anthropic client and a fresh in-memory SQLite per test.

## Project layout

```
procurebot/
├── docs/                                  training deck (source of truth)
├── procurebot/
│   ├── db.py        SQLAlchemy engine + session factory
│   ├── models.py    Supplier, PurchaseOrder, AuditLog
│   ├── seed.py      idempotent seed (8 suppliers covering all 5 deck tests)
│   ├── prompt.py    SYSTEM_PROMPT — verbatim slides 11–14 + tool-use addendum
│   ├── tools.py     6 tool functions + Anthropic JSON schemas + dispatch()
│   ├── agent.py     multi-turn Anthropic chat loop with tool dispatch
│   ├── email_stub.py local email logger (not real SMTP)
│   └── main.py      FastAPI app: /api/chat, /api/welcome, /api/suppliers, /
├── static/          minimal HTML/CSS/JS chat UI
└── tests/           tool-level + 5 deck scenarios via fake Claude
```

## Approval matrix (slide 13)

| PO value (SGD)        | Approver                  | Action                                    |
|-----------------------|---------------------------|-------------------------------------------|
| < 10,000              | Procurement Officer       | Proceed                                   |
| 10,000 – 50,000       | Procurement Manager       | Confirm approver before raising           |
| 50,001 – 100,000      | Head of Procurement       | Confirm approver before raising           |
| > 100,000             | CFO + Head of Procurement | **Do NOT raise** — emergency form         |

## Seeded suppliers (covers slide-26 test cases)

| Supplier               | Status     | Used in        |
|------------------------|------------|----------------|
| AeroTech Components    | Active     | Test 1, Test 3 |
| Omega Fluid Systems    | Suspended  | Test 2         |
| Global Avionics        | Active     | Test 4         |
| Precision Hydraulics   | Expiring   | Expiring branch|
| Single-Source Bearings | Active     | Risk-flag branch|
| Sentinel Fasteners     | Active     | filler         |
| Helix Wire & Cable     | Active     | filler         |
| Apex Composites        | Active     | filler         |

`FastParts Co.` is intentionally **not** seeded — Test 5 expects "not found".

## Notes

- Email is stubbed — `email_stub.py` logs to stdout and to `audit_log`.
  Swap to real SMTP or Microsoft Graph in one place when needed.
- Sessions are kept in memory; every turn and every tool call is also
  written to `audit_log` so you can replay any conversation from disk.
