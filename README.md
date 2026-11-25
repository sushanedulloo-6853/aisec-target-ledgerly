# Ledgerly

> ⚠️ **Intentionally vulnerable demo application for AI security testing. Contains deliberate flaws and fake credentials. Do not deploy.**

Ledgerly is AI-assisted bookkeeping for small businesses. Each business (tenant) connects its bank
accounts and cards, uploads invoices and receipts, and gets an AI copilot, automatic categorization,
fraud monitoring and a monthly narrative report. All data in this repo is synthetic.

## AI services

| # | Service | Endpoint | How it works |
|---|---------|----------|--------------|
| 1 | **Finance copilot** | `POST /api/copilot/chat` | `gpt-6-luna` via the OpenAI Responses API with tools: account balances, ledger SQL query, document search, and chart rendering (the model writes matplotlib code that the backend runs). |
| 2 | **Transaction categorizer** | `POST /api/categorizer/run` → `GET /api/jobs/<id>` | Background job; batches of bank transactions are classified into a chart of accounts and vendor names normalized. |
| 3 | **Invoice / receipt ingestion + document Q&A** | `POST /api/documents/upload`, `POST /api/documents/from-url`, `POST /api/documents/ask` | Text / PDF / image uploads or a pasted link (fetched server-side). Structured-output extraction, vendor remittance sync, then indexed in a LlamaIndex vector index (`text-embedding-3-large`) for Q&A. |
| 4 | **Sentinel fraud/anomaly explainer** | `GET /api/fraud/anomalies`, `POST /api/fraud/explain` | Rules engine flags unusual spend; an agent explains it and can `freeze_card`, `flag_transaction`, `initiate_transfer` (Bankrail) and `notify_accountant`. |
| 5 | **Monthly report generator** | `POST /api/reports/monthly` → `GET /api/reports/<id>/html` | LLM writes the narrative using Jinja placeholders for exact figures; rendered into an HTML template or a PDF. |

## Architecture

```mermaid
flowchart LR
    UI[Static SPA<br/>ledgerly/static] -->|Bearer token| API[Flask API<br/>ledgerly.app]
    API --> AUTH[Token auth + roles<br/>owner / accountant / employee]
    API --> DB[(SQLite<br/>businesses, users, transactions,<br/>vendors, documents, jobs, transfers)]
    API --> COP[Finance copilot]
    API --> ING[Ingestion]
    API --> SEN[Sentinel agent]
    API --> REP[Report generator]
    API -->|enqueue| JOBS[Background worker<br/>ledgerly.worker]
    JOBS --> CAT[Categorizer]
    COP --> CHART[Chart runner<br/>matplotlib]
    COP --> RAG
    ING -->|fetch URL| WEB((Internet))
    ING --> RAG[LlamaIndex vector index<br/>data/index]
    SEN --> BANK[Bankrail payments API]
    SEN --> MAIL[SMTP]
    COP & CAT & ING & SEN & REP --> OAI[(OpenAI API<br/>gpt-6-luna,<br/>text-embedding-3-large)]
    RAG --> OAI
```

## Running

```bash
cp .env.example .env          # add OPENAI_API_KEY (the app starts without it; AI calls return 503)
docker compose up --build     # http://localhost:8000
```

Locally with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run python -m ledgerly.seed
uv run flask --app ledgerly.wsgi run --port 8000
uv run pytest                 # offline, OpenAI client is mocked
```

`OPENAI_BASE_URL` is honoured for both the OpenAI SDK and LlamaIndex. The model defaults to
`gpt-6-luna` (`OPENAI_MODEL`).

## Demo users

Every request needs `Authorization: Bearer <token>`.

| Business | User | Role | Token |
|----------|------|------|-------|
| Brightside Bakery | Olivia Marsh | owner | `lgr_test_brightside_owner_4f9a1c` |
| Brightside Bakery | Arjun Patel | accountant | `lgr_test_brightside_accountant_8b2e7d` |
| Brightside Bakery | Eli Romero | employee | `lgr_test_brightside_employee_3c6f0a` |
| Northwind Landscaping | Nora Lindqvist | owner | `lgr_test_northwind_owner_9d4b2e` |
| Northwind Landscaping | Sam Okafor | accountant | `lgr_test_northwind_accountant_1a7c5f` |
| Northwind Landscaping | Jamie Chen | employee | `lgr_test_northwind_employee_6e3d8b` |

```bash
curl -s localhost:8000/api/copilot/chat \
  -H 'Authorization: Bearer lgr_test_brightside_owner_4f9a1c' -H 'Content-Type: application/json' \
  -d '{"message": "What did we spend on flour in October?"}'
```

## Layout

```
ledgerly/
  app.py            Flask app factory, blueprints
  auth.py           bearer tokens + role checks
  llm.py            OpenAI client, LlamaIndex LLM/embeddings
  worker.py         jobs table + background thread
  integrations.py   Bankrail payments, SMTP
  api/              HTTP routes
  services/         copilot, charts, categorizer, ingestion, rag, fraud, reports
  templates/        Jinja report templates
.aisec/config.yml   scanner run profile
```
