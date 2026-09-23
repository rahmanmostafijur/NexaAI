# Architecture and design decisions

This document explains *why* NexaAI Agent is built the way it is. For *what* each file does, see
[developer-guide.md](developer-guide.md).

## 1. Principles

1. **Choose the source of truth before answering.** The expensive part of a business assistant is
   not generating text but knowing whether the answer lives in the database, in a document, in
   both, or nowhere.
2. **Never trust model output.** Generated SQL, routing decisions, plans and citations are all
   validated by deterministic code before they have effects.
3. **Prefer honest failure to plausible fiction.** If there is no evidence, the user gets a fixed
   "couldn't find" message. The model is not invited to guess.
4. **Components behind small interfaces.** `LLMProvider`, `EmbeddingProvider` and `BaseTool` make
   providers and capabilities swappable without touching the orchestrator.

## 2. Key decisions

### D1: A separate business schema and a read-only role
Business tables live in the `commerce` schema. The Text-to-SQL executor connects as
`nexa_readonly`, which has `USAGE` on `commerce`, `SELECT` on its tables, no rights on `public`,
`default_transaction_read_only = on`, a role-level `statement_timeout` and a connection limit. The
migration creates this role.

*Why:* validation can have bugs, but database privileges are enforced by PostgreSQL itself. Even
a validator bypass cannot write data or read users, conversations or documents. Integration tests
execute raw `INSERT`, `DELETE` and `SELECT * FROM public.users` through the executor to prove it.

### D2: AST validation rather than regex
The SQL is parsed with sqlglot and the syntax tree is inspected. A string such as `'DROP TABLE x'`
inside a literal is harmless, while `WITH x AS (DELETE …) SELECT …` is caught because the check
walks the whole tree. The validator re-renders the SQL, which strips comments, and that rendered
SQL is what gets executed.

*Trade-off:* the column check is intentionally conservative. It verifies qualified columns and
simple unqualified ones, and leaves complex derived-table cases to PostgreSQL. The resulting
database errors flow into the correction loop.

### D3: Schema retrieval instead of sending the whole schema
Tables are ranked by multilingual keyword hits plus embedding similarity against short table
descriptions ("cards"). The selection is then closed under foreign-key paths, so the model always
receives the join tables it needs.

*Why:* smaller prompts are cheaper and faster, and they reduce hallucinated columns. The same
vocabulary also feeds the heuristic router.

### D4: Self-correction with a hard bound, and only for correctable errors
Unknown table or column, syntax and database errors are sent back to the model with the failing SQL,
at most `SQL_MAX_CORRECTION_ATTEMPTS` (default 2) times. Safety violations (DML, blocked functions,
system tables) and timeouts are *not* retried: they end the attempt immediately.

### D5: Deterministic language detection
Bengali script is identified by its Unicode block. Banglish is identified by a lexicon of very
common romanised words (`koto`, `kon`, `shobcheye`, `hoise`…). Text with both scripts is `mixed`.

*Why:* it is instant, free, testable and accurate for this problem. The LLM gets the result as an
instruction ("respond in Bengali, keep English business terms…").

### D6: The router is an LLM *plus* deterministic safeguards
The LLM returns structured JSON: route, confidence, reason, a standalone English rewrite, and
sub-questions for each tool. Independent signals then check it:

- **Heuristic signals:** analytics vocabulary, table vocabulary, policy vocabulary. One rule uses
  them to switch SQL or HYBRID to RAG when a question names business entities but asks about
  rules, with no aggregation words, and a policy document matches.
- **Document-relevance probe:** the best vector similarity in the knowledge base.
- **Tool availability:** for example, an empty knowledge base means HYBRID degrades to SQL.
- **Follow-up detection:** "them", "ওগুলো" and similar words inherit the previous question's subject.

These signals can correct a clear misroute, such as GENERAL for "What is our refund policy?", and
they adjust confidence up when they agree with the LLM and down when they disagree. If the LLM
fails, the heuristics route alone, with confidence capped at 0.7.

*Evidence:* on held-out questions the heuristics alone reach **70.8%** routing accuracy, versus
98.8% on the set they were tuned on. They are useful as a safety net but overfit as a primary
router. That is why the LLM leads.

### D7: Planner only where planning adds value
SQL, RAG and GENERAL get a deterministic one-step plan with no extra LLM call. HYBRID uses an LLM
planner whose output is validated: known tools only, dependencies must refer to earlier steps, at
most 4 steps, and the plan must use both tools. If validation fails, a deterministic `sql → rag`
plan is used. Dependent steps use `{s1}` placeholders that the executor fills with labels from the
previous result, for example "Electronics".

### D8: Hybrid retrieval with a relevance threshold
Vector search catches meaning, including cross-lingual matches such as a Bengali question against
an English policy. The `simple` full-text configuration catches exact tokens (bKash, EMI, policy
names) and works for Bengali because it does no stemming. Reciprocal Rank Fusion merges both
lists across query variants, the original wording and the English rewrite.

A cosine-similarity threshold then removes chunks that are merely "the nearest". That is why
"What is FastAPI?" retrieves nothing instead of three irrelevant policy excerpts.

### D9: Local multilingual embeddings by default
The default embedding model is `paraphrase-multilingual-MiniLM-L12-v2`, run through fastembed on
ONNX: 384 dimensions, about 220 MB, and no API key. It places Bengali, Banglish and English in one
vector space; the measured similarity for Bengali questions against English passages is 0.46–0.66,
compared with under 0.25 for unrelated text. An OpenAI-compatible embedding provider is available
too. Changing the dimension requires reindexing.

### D10: Page- and section-aware chunks
A chunk never crosses a page, so citations like "Warranty Policy, Page 4" stay exact, and it never
crosses a section, so each chunk covers one topic. PDFs have no markup, so headings are detected
heuristically: short, Title Case, no terminal punctuation. Lines wrapped by the PDF layout are
re-joined. DOCX headings come from paragraph styles.

### D11: Evidence first, then a fixed answer or a prompted answer
`ResponseGenerator.prepare()` decides from the evidence alone:

- no passages for a RAG question → the fixed "not found" message, in the user's language;
- no SQL result → the fixed "no data" or "unsafe" message;
- otherwise → a route-specific prompt.

The model never sees an empty context with an instruction to "answer anyway".

### D12: Prompt-injection isolation
Retrieved documents and database values are placed inside tags whose closing tags are escaped, so
content cannot close them early. System prompts declare tagged content to be data. Chunks that
match injection patterns are flagged at ingestion time and labelled in the prompt. Citations the
model makes up (`[S99]`) are removed and reported as warnings.

### D13: Streaming through a single pump task
The orchestrator is an async generator of typed events. The SSE layer consumes it in one task and
relays the frames through a queue, sending `: keep-alive` comments while idle.

*Why:* a first design advanced the generator from a new task on each step. Each asyncio task has
its own copied context, so the context variable used for token accounting was set in one context
and reset in another. An integration test caught this, and the single-pump design fixed it. The
same design lets a client disconnect cancel the pipeline and record the run as interrupted.

### D14: Observability without sensitive data
`agent_runs` stores route, confidence, language, tools, per-stage durations, token usage, status
and error codes. It stores the generated SQL (which is useful for debugging) but **not prompts** and
not model reasoning. Users see their own runs; admins see all.

### D15: Failure semantics
If a run fails (LLM down, internal error, client disconnect), the unanswered user message is
deleted, so a retry does not duplicate it. The conversation row is kept so the client can retry
with the same id; conversations with no messages are hidden from the sidebar.

## 3. Evaluation results

Offline metrics, which need no LLM, are listed in the README. Full-agent metrics depend on the
model and are produced by `python evaluate_agent.py --mode full`; each run writes a JSON report
with per-item details to `backend/evaluation/results/`.

### `openai/gpt-oss-120b` on Groq's free tier (report `…184814Z-main-full.json`)

| Metric | Main set (80) |
|---|---|
| Routing accuracy | 98.8% (100% for Bangla, Banglish, general, RAG and hybrid; 95% for SQL) |
| SQL execution accuracy | 82.1% (n=39) |
| Retrieval hit rate / precision | 95.0% / 89.4% |
| Citation correctness | 95.0% |
| Answer correctness | 90.9% (n=44) |
| Hybrid success | 58.3% (n=12) |
| Latency p50 / p95 | 15.1 s / 35.2 s |
| Errors | 1 (rate limit) |

Hybrid misses were mostly ambiguous readings rather than failures: "most returns" measured as
units instead of requests, and "বেশি বিক্রি" read as revenue instead of units. The metric only
counts a hybrid answer as a success when the SQL, the retrieval and the route are all correct.

The held-out run with this model could not be completed on the free tier. The daily quota is
200,000 tokens, and the main run used it up. It is re-runnable with
`python evaluate_agent.py --mode full --dataset holdout --pause 25`.

### `qwen2.5:1.5b-instruct` running locally on CPU through Ollama

Recorded runs. It is
deliberately tiny, so the numbers below are a pessimistic lower bound for the pipeline and should
not be read as its ceiling.

| Metric | Main set, full run (80) | RAG category after safeguard 3 (20) | Held-out, after safeguard 3 (24) |
|---|---|---|---|
| Routing accuracy | 75.0% | 95.0% | 66.7% |
| SQL execution accuracy | 28.9% (n=38) | – | – |
| Retrieval hit rate (cited/listed sources) | 72.5% | 100% | 58.3% |
| Retrieval precision | 51.7% | 71.0% | 47.9% |
| Citation correctness | 2.5% | 0% | 0% |
| Answer correctness (required facts) | 54.5% (n=44) | 85.0% | – |
| Hybrid success rate | 25.0% (n=12) | – | – |
| Latency p50 / p95 | 46.7 s / 158.9 s | 38.1 s / 54.9 s | 41.9 s / 129.4 s |
| Errors | 2 (invalid JSON from the model) | 0 | 1 |

What the runs showed, and what changed as a result:

- **Routing (the main set):** the small router sent 10 of 20 policy questions to SQL, because they
  mention business nouns ("refund", "members"). Safeguard 3 in D6 was added for this error
  class: SQL or HYBRID is switched to RAG when there is no aggregation intent and a policy
  document matches. On the RAG category, routing rose from 40% to 95%.
- **SQL:** the 1.5B model often returns `sql: null` or a query that differs slightly from gold,
  for example a missing upper date bound. The validator and read-only execution kept every
  attempt safe. The weak spot is accuracy, not safety.
- **Citations:** the small model almost never emits `[S#]` markers. The citation validator
  reports this honestly: answers are marked "not grounded", with a warning. It does not attach
  citations automatically, because that would fabricate them.
- **Result files:** `backend/evaluation/results/20260923T170721Z-main-full.json`,
  `…172159Z-main-rag-full.json` and `…174633Z-holdout-full.json`.

Re-run these with a production model (for example `LLM_MODEL=gpt-4o-mini` or a 7B+ local
model) using `make evaluate-full` to measure the system at its intended capacity.

## 4. Known limitations

- Rate limiting and background ingestion run in-process, which suits one backend instance. Scaling
  out needs Redis and a job queue.
- Answer-correctness checks are deterministic fact matches, not semantic judgements.
- The heuristic vocabulary is hand-written. Adding a table requires adding its keywords to
  `app/sql/hints.py` for the best results, although embedding similarity still works without them.
- Small local models, around 1–2B parameters, follow the SQL rules well enough to exercise the
  pipeline but make ranking and language-style mistakes. A 7B+ or hosted model is recommended
  for real use.
