# Adoption Guide: running NexaAI Agent on your own platform

This guide is for teams that want to use NexaAI Agent with **their own data and documents**. It
covers installing, connecting your database, loading your knowledge base, managing users,
integrating the agent into your own applications, and running it in production.

> **In one sentence:** you point NexaAI Agent at a PostgreSQL schema and a set of documents, and
> your staff can then ask questions like "গত মাসে কত বিক্রি হয়েছে?" or "What is our leave
> policy?" in English, Bangla or Banglish. They get answers with the SQL used and the sources cited.

---

## Contents

1. [What you get](#1-what-you-get)
2. [Is it a fit?](#2-is-it-a-fit)
3. [Who does what](#3-who-does-what)
4. [Step 1: Install](#4-step-1-install)
5. [Step 2: Configure](#5-step-2-configure)
6. [Step 3: Connect your database](#6-step-3-connect-your-database)
7. [Step 4: Teach the agent your business vocabulary](#7-step-4-teach-the-agent-your-business-vocabulary)
8. [Step 5: Load your knowledge base](#8-step-5-load-your-knowledge-base)
9. [Step 6: Set up users and access](#9-step-6-set-up-users-and-access)
10. [Step 7: Test with your own questions](#10-step-7-test-with-your-own-questions)
11. [Step 8: Go live](#11-step-8-go-live)
12. [Integrating with your platform (API)](#12-integrating-with-your-platform-api)
13. [Guide for end users](#13-guide-for-end-users)
14. [Operating the system](#14-operating-the-system)
15. [Data privacy: what leaves your server](#15-data-privacy-what-leaves-your-server)
16. [Troubleshooting](#16-troubleshooting)
17. [FAQ](#17-faq)

---

## 1. What you get

| Capability | What it means for you |
|---|---|
| **Ask your database** | Plain-language questions become safe, read-only SQL. The answer shows the numbers, the SQL and a result table. |
| **Ask your documents** | Upload PDFs, Word files, Markdown, text or CSV. Answers quote and cite the exact document, page or section. |
| **Both at once** | "Which product had the most returns, and what does our return policy say?" is answered from the database and the policy together. |
| **Multilingual** | English, বাংলা, Banglish and mixed Bangla–English questions. Answers come back in the same style. |
| **Honest answers** | If the data or document isn't there, it says so instead of guessing. |
| **Admin tools** | A web UI for documents, schema browsing, search testing and usage analytics. |
| **API** | REST and streaming endpoints for building it into your own website, CRM, helpdesk or chat bot. |

The same deployment serves a web app (for staff) and an API (for your other systems).

## 2. Is it a fit?

NexaAI Agent works well if most of these are true:

- ✅ Your business data is in **PostgreSQL**, or can be copied into it (see [Option C](#option-c-other-databases-mysql-sql-server-excel)).
- ✅ The questions people ask are answerable from **tables**: sales, orders, customers, stock, tickets, payments, bookings, and so on.
- ✅ You have **written policies, manuals or FAQs** that staff keep asking about.
- ✅ Users ask in **English and/or Bangla**.
- ✅ You can use an **LLM provider** (OpenAI, Groq, Gemini, OpenRouter…) or run a local model.

It is **not** designed for:

- ❌ Changing data. It is strictly read-only by design.
- ❌ Scanned image PDFs. They contain no extractable text; run OCR first.
- ❌ Row-level permissions per user out of the box. Every user can query the same business schema, so expose only what all users may see (see [§6](#6-step-3-connect-your-database)).

## 3. Who does what

| Role | Responsibilities |
|---|---|
| **IT / DevOps** | Install, configure `.env`, set up HTTPS, backups and the LLM key. |
| **Data owner / analyst** | Decide which tables the agent may read; create views; write column descriptions and vocabulary. |
| **Knowledge manager** | Upload and maintain policy documents; remove outdated ones. |
| **Administrator (in the app)** | Manage documents, check analytics, review failed questions. |
| **End users** | Ask questions in the web app, or through your integrated tools. |

In a small company one person can do all of this in a day.

---

## 4. Step 1: Install

**Requirements:** a Linux or Windows server (or VM) with **Docker**. That means 2+ CPU cores,
4 GB RAM or more (8 GB recommended), and about 5 GB of disk.

```bash
git clone <your-copy-of-the-repository> nexa-agent
cd nexa-agent
cp .env.example .env         # configure it in Step 2
docker compose up --build -d
```

| URL | What |
|---|---|
| `http://<server>:3000` | Web app |
| `http://<server>:8000/api/docs` | Interactive API documentation (disabled when `ENVIRONMENT=production`) |

On first start, the backend:
- applies database migrations;
- creates the read-only database role the AI uses;
- loads the embedding model (~220 MB, downloaded once);
- if `SEED_ON_STARTUP=true`, loads the demo data.

> Try it first with the demo data to see how it behaves, then continue with your own data.

## 5. Step 2: Configure

Edit `.env` and restart with `docker compose up -d`. These are the settings you **must** review:

```ini
# --- Your organisation --------------------------------------------------
COMPANY_NAME=Acme Retail Ltd           # used in every prompt ("assistant for Acme Retail Ltd")
CURRENCY_CODE=BDT                      # e.g. BDT, USD, INR
CURRENCY_SYMBOL=৳                      # e.g. ৳, $, ₹

# --- Security (required for production) ---------------------------------
ENVIRONMENT=production
JWT_SECRET=<python -c "import secrets; print(secrets.token_urlsafe(48))">
SQL_READONLY_PASSWORD=<another long random value>
POSTGRES_PASSWORD=<database password>
ADMIN_EMAIL=it@acme.example
ADMIN_PASSWORD=<strong password>
ALLOW_REGISTRATION=false               # only admins create accounts
CORS_ORIGINS=https://assistant.acme.example

# --- Language model --------------------------------------------------------
LLM_BASE_URL=https://api.groq.com/openai/v1     # any OpenAI-compatible API
LLM_API_KEY=<your key>
LLM_MODEL=openai/gpt-oss-120b
LLM_REASONING_EFFORT=low               # only for reasoning models such as gpt-oss

# --- Demo data -------------------------------------------------------------
SEED_ON_STARTUP=false                  # do not load the demo company once you use your own data
```

**Choosing an LLM:**

| Provider | Base URL | Notes |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | Paid, very reliable (`gpt-4o-mini` is a good default). |
| Groq | `https://api.groq.com/openai/v1` | Very fast. The free tier is limited (~200k tokens/day per model), so use a paid tier for teams. |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | Has a free tier. |
| OpenRouter | `https://openrouter.ai/api/v1` | One key, many models. |
| Ollama (local) | `http://ollama:11434/v1` | No data leaves your server. Needs a strong machine: 7B+ models need 16 GB RAM or a GPU for good results. |

A typical question uses **2,000–6,500 tokens**: about 2.7k for a document question, 4k for a
database question and 6.4k for a combined one. Use this to estimate cost and pick a plan.

## 6. Step 3: Connect your database

The agent can only query the PostgreSQL schema named **`commerce`**. A dedicated role
(`SQL_READONLY_USER`) runs every AI-generated query. That role:

- can read **only** the `commerce` schema;
- runs in read-only transactions, with a per-query timeout and a row cap;
- can never read the app's own tables (users, conversations and so on).

So "connecting your data" means **putting what the agent may see into `commerce`**, and nothing
more.

### First, remove the demo tables

```sql
-- connect as the database owner (POSTGRES_USER)
DROP TABLE IF EXISTS commerce.reviews, commerce.returns, commerce.payments, commerce.order_items,
  commerce.inventory, commerce.orders, commerce.customers, commerce.products,
  commerce.categories CASCADE;
```

Then delete the demo documents in **Knowledge Base → Documents**, and keep
`SEED_ON_STARTUP=false`.

### Option A: your data is already in the same PostgreSQL server (recommended)

Put your real tables in their own schema (for example `shop`) and expose **views** in `commerce`.
Views let you choose exactly which columns the AI can see, hide personal data, and rename
confusing columns. A view runs with its owner's rights, so the read-only role never needs access
to your real tables.

```sql
-- Only what the assistant should know. No phone numbers, no emails.
CREATE VIEW commerce.customers AS
SELECT id, full_name, city, country, loyalty_level AS membership_tier, created_at
FROM shop.customer_master
WHERE is_test = false;

CREATE VIEW commerce.orders AS
SELECT order_id AS id, customer_id, placed_at AS order_date, status,
       grand_total AS total_amount, channel
FROM shop.sales_orders;
```

### Option B: your data is on another PostgreSQL server

Use PostgreSQL's `postgres_fdw` to create **foreign tables** in `commerce`. The agent treats them
like normal tables.

```sql
CREATE EXTENSION IF NOT EXISTS postgres_fdw;
CREATE SERVER erp FOREIGN DATA WRAPPER postgres_fdw
  OPTIONS (host 'erp-db.internal', dbname 'erp', port '5432');
-- A read-only account on the ERP side; PUBLIC lets the AI's role use it.
CREATE USER MAPPING FOR PUBLIC SERVER erp OPTIONS (user 'report_reader', password '...');
IMPORT FOREIGN SCHEMA public LIMIT TO (orders, customers, products)
  FROM SERVER erp INTO commerce;
```

### Option C: other databases (MySQL, SQL Server, Excel)

Copy the data into PostgreSQL on a schedule (nightly, or hourly). You can use
[pgloader](https://pgloader.io) for MySQL and SQL Server, `COPY` for CSV exports, or your usual
ETL tool. Load it into `shop` and expose views as in Option A.

### Describe everything (this matters most)

The AI understands your data **through descriptions**. Write them as you would explain the table
to a new analyst: units, allowed values, and how to calculate your key figures.

```sql
COMMENT ON VIEW   commerce.orders IS 'Customer orders. Revenue = SUM(total_amount) where status <> ''cancelled''.';
COMMENT ON COLUMN commerce.orders.status IS 'One of: pending, paid, shipped, delivered, cancelled.';
COMMENT ON COLUMN commerce.orders.total_amount IS 'Amount charged to the customer in BDT, after discounts.';
COMMENT ON COLUMN commerce.orders.order_date IS 'When the order was placed (Asia/Dhaka time).';
```

Good descriptions are the single biggest factor in SQL accuracy.

### Grants and refresh

```sql
-- Tables and views created by the database owner are readable automatically (default
-- privileges). For objects created by another role, grant explicitly:
GRANT SELECT ON ALL TABLES IN SCHEMA commerce TO nexa_readonly;
```

The backend caches the schema, so restart it after schema changes:
`docker compose restart backend`. Then check **Knowledge Base → Database Schema**. It shows
exactly what the AI sees, including your descriptions.

## 7. Step 4: Teach the agent your business vocabulary

These optional code-level edits noticeably improve accuracy. Rebuild afterwards with
`docker compose up -d --build backend`.

1. **Words people use for each table:** `backend/app/sql/hints.py` → `TABLE_KEYWORDS`. Add
   English, Bangla and Banglish words.

   ```python
   "tickets": ["ticket", "complaint", "issue", "অভিযোগ", "টিকেট", "complain"],
   "bookings": ["booking", "reservation", "appointment", "বুকিং", "সিরিয়াল", "booking koto"],
   ```

   These words help pick the right tables and help the router tell data questions from policy
   questions.

2. **Your business rules:** `backend/app/prompts/sql.py` has a rule list with definitions such as
   what "revenue" means and how "last month" is calculated. Replace the retail-specific rules and
   the two worked examples with yours, for example:
   - "Active customer = at least one order in the last 90 days."
   - "Fiscal year starts on July 1."

3. **Router examples:** `backend/app/prompts/router.py` describes what the database and the
   documents contain. Adjust the example questions to your domain.

## 8. Step 5: Load your knowledge base

Log in as admin, go to **Knowledge Base → Documents**, and drag in your files.

| Supported | Limit |
|---|---|
| PDF (text-based), DOCX, TXT, Markdown, CSV | `MAX_UPLOAD_MB` (default 10 MB) per file |

Each file is validated, then split into sections and pages, indexed, and becomes searchable
within seconds. The status goes from `pending` to `indexed`, or to `failed` with a reason.

**Tips for good answers:**

- **Use clear headings** ("Refund Timelines", "Annual Leave"). They become the section names in citations.
- **Keep one topic per document** where possible, and give files meaningful titles; the title appears in every citation.
- **Remove outdated versions.** Two conflicting policies produce hedged answers.
- **Test in Knowledge Base → Search.** Type a question and see which passages come back.
- **Reindex** after replacing a file's content, or upload the new version and delete the old one.

Documents are treated strictly as **information, never as instructions**. A document containing
"ignore your rules" is flagged and quoted, not obeyed.

## 9. Step 6: Set up users and access

| Role | Can do |
|---|---|
| `admin` | Everything, plus upload, delete and reindex documents, view the database schema, and see all users' analytics. |
| `user` | Chat; see own conversations and own analytics; search documents. |

- **The first admin** is created from `ADMIN_EMAIL` / `ADMIN_PASSWORD` on first start.
- **Adding staff:** temporarily set `ALLOW_REGISTRATION=true`, let staff register at the login
  page, then set it back to `false`. You can also create accounts through the API
  (`POST /api/auth/register`) from your onboarding script while registration is enabled.
- **Promoting someone to admin:** there's no UI toggle yet; run
  `UPDATE users SET role = 'admin' WHERE email = 'name@acme.example';`.
- **Privacy:** conversations are private per user. Users cannot see each other's chats.

## 10. Step 7: Test with your own questions

Before rollout, collect 30–50 real questions from staff and measure how the agent does on them.

1. Create `backend/evaluation/my_questions.jsonl`, one JSON object per line:

   ```json
   {"id": "q1", "category": "sql", "question": "How many tickets were opened last week?", "expected_route": "SQL", "gold_sql": "SELECT COUNT(*) FROM tickets WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'"}
   {"id": "q2", "category": "rag", "question": "What is the SLA for priority-1 tickets?", "expected_route": "RAG", "expected_sources": ["Support_SLA.pdf"], "must_include": [["4 hours", "৪ ঘণ্টা"]]}
   ```

2. Register it in `DATASETS` in `backend/evaluation/runner.py`, then run:

   ```bash
   cd backend
   uv run python evaluate_agent.py --mode full --dataset my_questions --pause 10
   ```

3. You'll get routing accuracy, SQL execution accuracy, retrieval quality, citation correctness,
   answer correctness and latency, plus a JSON report for every question in
   `evaluation/results/`.
4. Fix the weak spots, usually with better column descriptions, vocabulary or documents, and run
   it again.

## 11. Step 8: Go live

**Production checklist:**

- [ ] `ENVIRONMENT=production`. This disables the API docs and refuses default secrets.
- [ ] Strong, unique `JWT_SECRET`, `POSTGRES_PASSWORD`, `SQL_READONLY_PASSWORD` and `ADMIN_PASSWORD`.
- [ ] `ALLOW_REGISTRATION=false`, and `CORS_ORIGINS` set to your real domain.
- [ ] **HTTPS:** put a reverse proxy (Caddy, nginx, Traefik, or a cloud load balancer) in front of port 3000. Only expose 443 publicly; keep 5434 and 8000 private.
- [ ] A **paid LLM plan**, sized for your traffic (see token estimates in [§5](#5-step-2-configure)).
- [ ] **Backups** of the `postgres_data` volume (for example a daily `pg_dump`). Uploaded files live in the `backend_data` volume.
- [ ] **Limits:** review `RATE_LIMIT_*`, `SQL_STATEMENT_TIMEOUT_MS` and `MAX_UPLOAD_MB`.
- [ ] Run your evaluation set once and record the baseline.

A minimal Caddy example for HTTPS:

```
assistant.acme.example {
    reverse_proxy localhost:3000
}
```

**Scaling note:** one backend instance comfortably serves a small or medium team. Rate limiting
and document indexing currently run in-process, so running several backend replicas requires
moving them to Redis and a job queue (see "Future improvements" in the README).

---

## 12. Integrating with your platform (API)

Everything the web app does is available over REST. The base URL is your deployment plus `/api`.
The full contract is in [api-contract.md](api-contract.md).

### 12.1 Authenticate

Create a dedicated **service account** (a normal `user`) for each integration, and log in to get
a token. Tokens are valid for `JWT_EXPIRE_MINUTES`, which defaults to 12 hours. When a call
returns **401**, log in again.

```bash
curl -s -X POST https://assistant.acme.example/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"crm-bot@acme.example","password":"..."}'
# → {"access_token":"eyJ...","token_type":"bearer","expires_in":43200,"user":{...}}
```

### 12.2 Ask a question (simple, non-streaming)

```bash
curl -s -X POST https://assistant.acme.example/api/chat \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message":"গত মাসে কতগুলো অর্ডার হয়েছে?"}'
```

The response is the final message:

```json
{
  "conversation_id": "…",
  "message": {
    "content": "গত মাসে মোট ১০৭টি অর্ডার হয়েছে [DB1]।",
    "details": {
      "route": "SQL", "confidence": 0.99, "language": "bn",
      "sql": [{"sql": "SELECT COUNT(*) …", "columns": ["total_orders"], "rows": [[107]]}],
      "sources": [{"id": "DB1", "type": "database", "title": "PostgreSQL", "tables": ["orders"]}],
      "grounded": true, "warnings": []
    }
  }
}
```

To ask a **follow-up in the same conversation**, send the `conversation_id` back:
`{"message": "How many of them were cancelled?", "conversation_id": "…"}`.

### 12.3 Python example

```python
import httpx

BASE = "https://assistant.acme.example/api"

class NexaClient:
    def __init__(self, email: str, password: str) -> None:
        self._credentials = {"email": email, "password": password}
        self._http = httpx.Client(base_url=BASE, timeout=120)
        self._login()

    def _login(self) -> None:
        token = self._http.post("/auth/login", json=self._credentials).json()["access_token"]
        self._http.headers["Authorization"] = f"Bearer {token}"

    def ask(self, question: str, conversation_id: str | None = None) -> dict:
        body = {"message": question, "conversation_id": conversation_id}
        response = self._http.post("/chat", json=body)
        if response.status_code == 401:          # token expired
            self._login()
            response = self._http.post("/chat", json=body)
        response.raise_for_status()
        return response.json()

client = NexaClient("crm-bot@acme.example", "...")
answer = client.ask("Which customer spent the most this year?")
print(answer["message"]["content"])
```

### 12.4 Streaming answers (for chat widgets)

`POST /api/chat/stream` returns **Server-Sent Events**, so you can show progress ("Running
database query…") and the answer word by word. It uses `POST` with a bearer header, so read the
stream with `fetch` rather than `EventSource`:

```javascript
async function ask(question, token, onEvent) {
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ message: question }),
  });
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop();                      // keep the incomplete frame
    for (const frame of frames) {
      const name = frame.match(/^event: (.*)$/m)?.[1];
      const data = frame.match(/^data: (.*)$/m)?.[1];
      if (name && data) onEvent(name, JSON.parse(data));
    }
  }
}

// Events: meta, status, analysis, plan, step, sql, sources, token, done, error
ask("What is our refund policy?", token, (name, data) => {
  if (name === "status") showProgress(data.label);
  if (name === "token") appendText(data.delta);
  if (name === "done") replaceWithFinal(data.message.content, data.message.details.sources);
  if (name === "error") showError(data.message);
});
```

If you call the API **from a browser on another domain**, add that domain to `CORS_ORIGINS`. For
public-facing products, it's usually better to call NexaAI from **your own backend**, so the
token never reaches the browser.

### 12.5 Common integration patterns

| Pattern | How |
|---|---|
| **Helpdesk / CRM sidebar** | Your backend calls `POST /api/chat` with the agent's question. Show the answer and its `sources` next to the ticket. |
| **Slack or Microsoft Teams bot** | A small bot service receives the message, calls `/api/chat` with a per-channel `conversation_id`, and posts `message.content` back. |
| **Internal website widget** | Embed a chat box that proxies to `/api/chat/stream` through your backend. |
| **Scheduled reports** | A cron job asks fixed questions ("Yesterday's revenue by category") and emails the answer and the result table (`details.sql[0].rows`). |
| **Syncing policies** | When a policy changes in your CMS, upload it with `POST /api/documents` (multipart, admin token) and delete the old version with `DELETE /api/documents/{id}`. |

Other useful endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /api/knowledge/search?q=...` | Document search without an LLM, e.g. for a "related policies" box. |
| `GET /api/documents` | Document status. |
| `GET /api/agent/stats` | Usage statistics. |
| `GET /api/health` | Monitoring. |

### 12.6 Handling errors in your integration

Every error returns `{"error": {"code", "message", "request_id"}}`.

| HTTP / code | Meaning | What to do |
|---|---|---|
| 401 `unauthorized` | Token missing or expired | Log in again. |
| 403 `forbidden` | Not allowed (e.g. a non-admin uploading) | Use the right account. |
| 422 `validation_error` | Bad input (empty message, over 4,000 characters) | Fix the request. |
| 429 `rate_limited` | Too many requests from this user | Wait for `Retry-After` seconds. |
| 503 `llm_unavailable` | LLM down or quota used up (the message says how long) | Retry later; consider a higher plan. |

Include `request_id` when reporting problems. It appears in the server logs.

---

## 13. Guide for end users

*Share this section with your staff.*

**Asking questions**

- **Write naturally.** Any of these work: "How many orders last month?", "গত মাসে কত অর্ডার হয়েছে?",
  "last month e koto order hoise?"
- **Be specific about time and scope:** "this year", "last 3 months", "in Dhaka", "for Electronics".
- **Ask follow-ups in the same chat:** "And how many of them were cancelled?"
- **Combine questions:** "Which product had the most returns, and what does the return policy say?"

**Reading an answer**

- The **coloured tag** shows where the answer came from: **SQL** (database), **Knowledge**
  (documents), **Hybrid** (both) or **General** (general knowledge).
- **Citation badges** like `[S1]` link to the exact document passage. `[DB1]` means the number
  came from the database.
- **Generated SQL** (click to expand) shows the exact query and result table, so analysts can verify it.
- **Details** opens the inspector: how the question was understood, how confident the agent is,
  the steps it took and the time each took.
- A **"Not grounded"** warning means the answer didn't cite a source. Double-check it.

**What it will and won't do**

- It only **reads** data. It can't change orders, prices or anything else.
- If the information isn't in the database or the documents, it says so. That's a feature, not a bug.
- It knows only what's in the connected data and uploaded documents. It has no access to email,
  the internet or other systems.

## 14. Operating the system

| Task | Where / how |
|---|---|
| Watch usage and failures | **Analytics** page: success rate, latency, route and language mix, and each run's step-by-step trace. |
| Investigate a bad answer | Open the conversation, then **Details**: check the route, the SQL and the sources. Fix descriptions, vocabulary or documents accordingly. |
| Update a policy | Upload the new file, then delete the old one (or replace it and **Reindex**). |
| Change the schema | Update views and comments, then `docker compose restart backend`. |
| Logs | `docker compose logs -f backend`. JSON lines with a `request_id`; secrets are redacted. |
| Backups | `docker compose exec postgres pg_dump -U nexa nexa > backup.sql` |
| Update the software | `git pull && docker compose up -d --build`. Migrations run automatically. |

## 15. Data privacy: what leaves your server

The database, documents, embeddings, users and conversations all stay on **your server**.
Embeddings are computed locally by default.

What **is sent to the LLM provider** for each question:

- the question and a short recent conversation history;
- descriptions of the relevant tables (names, columns and your comments), **not** the full table contents;
- the **query result** (up to 50 rows) when the question needs the database;
- the relevant **document excerpts** (up to 8 passages) when the question needs documents.

To keep everything in-house, use a **local model through Ollama** (`LLM_BASE_URL=http://ollama:11434/v1`),
or a provider with a no-retention agreement. Views are the easiest way to avoid exposing personal
data in the first place (see [§6](#6-step-3-connect-your-database)).

## 16. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "No language model is configured" | `LLM_*` missing in `.env` | Set `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY`, then `docker compose up -d backend`. |
| "usage quota is used up" | Provider limit reached (common on free tiers) | Wait, switch `LLM_MODEL`, or upgrade the plan. |
| "The configured language model was not found" | Model name changed or unavailable | Copy a current model id from the provider's model list. |
| Answers use the demo company's data | Demo tables or documents still present | Drop the demo tables, delete the demo documents, set `SEED_ON_STARTUP=false`. |
| "The database does not contain enough information" | Table not in `commerce`, or unclear descriptions | Check **Database Schema**; add views and comments; restart the backend. |
| Wrong numbers | Business rule not described | Add the definition to the column comment and to the rules in `prompts/sql.py`. |
| "I couldn't find this information in the documents" | Document missing, scanned, or the wording differs | Test in **Knowledge Base → Search**; upload a text-based version; use clear headings. |
| Document status `failed` | Encrypted, scanned or corrupted file | Check the error tooltip; re-export as text PDF or DOCX. |
| Policy questions answered from the database (or vice versa) | Vocabulary overlap | Add words to `hints.py` (§7) and example questions to the router prompt. |
| Slow answers | Provider latency or a large model | Use a faster model or provider; set `LLM_REASONING_EFFORT=low` for reasoning models. |

## 17. FAQ

**Can it modify or delete my data?**
No. It uses a database role that can only read the `commerce` schema, every query runs in a
read-only transaction, and generated SQL is checked before it runs. Write statements are rejected
at three separate layers.

**Which languages does it support?**
English, Bangla (বাংলা), Banglish (Bangla in Latin letters) and mixed text. Documents can be in
English or Bangla; a Bangla question can find an English policy.

**Do I need a GPU?**
No, if you use a cloud LLM. The embedding model runs on a CPU. You only need a GPU to run a
strong local LLM.

**How much does it cost to run?**
Server costs are small (one modest VM). LLM cost scales with usage, at roughly 2,000–6,500 tokens
per question. Multiply by your expected questions per day and your provider's price per token.

**Can different departments see different data?**
Not per user yet. All users can query the same `commerce` schema. For separation today, run one
deployment per department, each with its own `commerce` views.

**Can I rename it or change the look?**
Yes. `COMPANY_NAME` changes how the assistant introduces itself in its answers. The web app's
name and logo live in `frontend/src/components/layout/Logo.tsx` and `frontend/index.html`.
