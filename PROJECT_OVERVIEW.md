# ProcureBot — One-Page Overview

## What we built

A working **procurement chatbot**, in plain Python, that does what your
training deck describes: helps procurement staff look up suppliers, follow
procurement rules, and raise Purchase Orders — all from a chat window.

You can run it on your laptop. You type a question in a browser. The bot
answers using a real database, follows real rules, and creates real PO records.

## How it works (in one paragraph)

A user types a message. The Python code sends it to Claude (the AI model)
along with a list of **tools** Claude is allowed to call: things like
"look up a supplier" or "calculate a PO total". Claude doesn't make up
answers — instead, it asks the Python code to run a tool, reads the real
result, and writes a reply. Every step is recorded in an audit log.

## What's in the folder

```
~/procurebot/
├── docs/                  the training deck (the spec)
├── pyproject.toml         list of Python libraries we need
├── .env.example           shows where the Claude API key goes
├── README.md              setup + how to run
├── CLAUDE.md              binding rules for future edits
├── PROJECT_OVERVIEW.md    this file
├── procurebot/            the bot's code
│   ├── db.py              connects to the SQLite database
│   ├── models.py          3 tables: Suppliers, PurchaseOrders, AuditLog
│   ├── seed.py            fills the Suppliers table with 8 test suppliers
│   ├── prompt.py          the bot's instructions (taken from your slides)
│   ├── tools.py           the 6 actions the bot can take
│   ├── email_stub.py      a fake "send email" (logs instead)
│   ├── agent.py           the back-and-forth loop with Claude
│   └── main.py            the web server (FastAPI)
├── static/                the chat web page (HTML/CSS/JS)
└── tests/                 16 automated tests
```

## The 6 tools the bot can call

| Tool | What it does |
|---|---|
| `lookup_supplier` | Finds one supplier by name |
| `list_suppliers` | Lists suppliers, optionally filtered by status |
| `calculate_po_total` | quantity × unit price |
| `get_approval_tier` | Tells you which approver is needed for a given total |
| `create_po` | Saves a Purchase Order to the database |
| `send_confirmation_email` | "Sends" the confirmation (just logs it for now) |

## The rules the bot follows (from slide 13)

| PO value (SGD)        | Approver                  | Action                                 |
|-----------------------|---------------------------|----------------------------------------|
| Below 10,000          | Procurement Officer       | Proceed                                |
| 10,000 – 50,000       | Procurement Manager       | Confirm before raising                 |
| 50,001 – 100,000      | Head of Procurement       | Confirm before raising                 |
| Above 100,000         | CFO + Head of Procurement | Don't raise — emergency form           |

## What we tested

All 5 deck test cases pass automatically, plus 11 lower-level tool tests
(16 total):

1. ✅ "Is AeroTech an approved supplier?" — returns real data
2. ✅ "Can I order from Omega Fluid Systems?" — refuses (Suspended)
3. ✅ "Raise a PO for 50 × HYD-7742-A from AeroTech at SGD 1,200" — creates a PO for SGD 60,000, Head of Procurement tier
4. ✅ "200 × Avionics Control Module from Global Avionics at SGD 8,500" — refuses (SGD 1.7M, over threshold)
5. ✅ "Order from FastParts Co.?" — not found, redirects to procurement team

## What's different from the deck's Microsoft version

The deck builds this in Microsoft Copilot Studio with SharePoint and Power
Automate. We built the **same bot** in plain Python:

| Deck (Microsoft) | This build (Python) |
|---|---|
| SharePoint Approved Supplier Register | SQLite `suppliers` table |
| Power Automate "Create item" | `create_po` Python function |
| Outlook "Send email" | `email_stub.py` (logs) |
| Copilot Studio chat UI | FastAPI + a small HTML page |
| Built-in knowledge | Verbatim system prompt from slides 11–14 |

If you ever want to deploy the deck's *real* Microsoft version, the code we
wrote is a complete reference — every rule and tool maps 1-to-1.
