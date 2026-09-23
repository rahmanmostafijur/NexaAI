# Developer guide

A walkthrough of the important files, in the order a request touches them.

## Repository layout

```
backend/
  app/
    main.py                  FastAPI factory: lifespan (services, admin bootstrap, warm-up), CORS, middleware
    core/                    config (pydantic-settings), errors (envelope), security (bcrypt, JWT),
                             rate_limit (sliding window), logging (JSON + redaction), middleware (request id, headers)
    db/session.py            app engine (SQLAlchemy async) + read-only asyncpg pool for Text-to-SQL
    models/                  app tables (public) and business tables (commerce) with COMMENT descriptions
    repositories/            data access: users, conversations/messages, documents, agent_runs
    schemas/                 Pydantic request/response models (the public contract)
    api/                     routers: auth, chat (SSE), conversations, documents, knowledge, schema, agent, system
    agent/                   the agent: language, heuristics, router, planner, executor, tools/, responder,
                             citations, memory, messages, trace, orchestrator, services (composition root)
    sql/                     catalog, hints, schema_retriever, validator, executor, service
    rag/                     extractors, cleaning, chunker, injection, ingestion, retriever, context
    llm/                     LLMProvider interface, OpenAI-compatible provider, structured output, usage tracking
    embeddings/              EmbeddingProvider interface, fastembed + OpenAI-compatible providers
    prompts/                 versioned prompt templates (router, sql, planner, rag, answer, common)
  migrations/                Alembic (schema, pgvector, read-only role, grants)
  scripts/seed.py            synthetic business data + knowledge-base ingestion
  scripts/build_documents.py renders Markdown sources to PDF/DOCX for the demo knowledge base
  data/knowledge_base/       source text of the 8 demo documents
  evaluation/                dataset.jsonl, holdout.jsonl, metrics.py, runner.py
  tests/                     unit/ (no services) and integration/ (real Postgres)
frontend/
  src/services/              typed API client, SSE parser, session storage
  src/features/chat/         ChatPage, streaming hook, message rendering, SQL block, tool activity
  src/features/inspector/    per-message analysis, plan, sources, SQL, timings
  src/features/knowledge-base/  documents, search and schema tabs
  src/features/analytics/    run statistics and trace timeline
  src/features/settings/, auth/, conversations/
  src/components/            layout and UI primitives
```

## Backend: the most important files

| File | Why it matters |
|---|---|
| `app/agent/orchestrator.py` | The request lifecycle. It sequences detection, routing, planning, tools, answering and validation; persists messages and runs; maps failures to `error` events. Read this first. |
| `app/agent/router.py` | Route decision: structured LLM output fused with heuristic signals, a document-relevance probe, follow-up detection and tool availability. |
| `app/agent/heuristics.py` + `app/sql/hints.py` | Explainable keyword signals in English, Bengali and Banglish, used as safeguards and as the fallback router. |
| `app/agent/planner.py` | One-step plans, or a validated LLM plan for HYBRID with a fallback. |
| `app/agent/executor.py` | Runs plan steps in dependency order, independent steps in parallel, and fills `{s1}` placeholders. |
| `app/agent/tools/*.py` | `BaseTool` and the registry; `SQLTool`, `RAGTool`, `GeneralTool`. |
| `app/agent/responder.py` | Turns evidence into a prompt or a fixed reply, and assigns citation ids `DB1`, `S1`. |
| `app/agent/citations.py` | Removes citations to sources that were never provided. |
| `app/sql/validator.py` | The SQL safety layer. |
| `app/sql/service.py` | Generate → validate → execute → correct loop. |
| `app/sql/executor.py` | Read-only transaction, timeout, bounded fetch, JSON-safe values. |
| `app/sql/catalog.py`, `app/sql/schema_retriever.py` | Schema inspection and relevant-table selection. |
| `app/rag/ingestion.py` | Upload validation, storage and the indexing pipeline. |
| `app/rag/chunker.py` | Page- and section-aware chunking with sentence overlap. |
| `app/rag/retriever.py` | Vector + keyword search, RRF, relevance threshold, optional reranker. |
| `app/llm/openai_compatible.py` | One provider for OpenAI, Groq, Gemini, OpenRouter, vLLM and Ollama: retries, streaming, usage. |
| `app/llm/structured.py` | JSON extraction plus Pydantic validation, with one error-feedback retry. |
| `app/api/chat.py` | SSE endpoint with a heartbeat and a single-pump streaming design. |
| `migrations/versions/0001_initial_schema.py` | Tables, HNSW and GIN indexes, and the hardened read-only role. |

## Frontend: the most important files

| File | Why it matters |
|---|---|
| `src/services/sse.ts` | Streaming SSE parser. It handles frames split anywhere, including inside multi-byte Bengali characters, and supports aborting. |
| `src/services/http.ts` | Fetch wrapper: bearer token, error envelope to `ApiError`, 401 handling. |
| `src/features/chat/hooks/useChatStream.ts` | Streaming state machine (idle → streaming → done or error) with stop and retry. |
| `src/features/chat/chatState.ts` | A pure reducer that applies SSE events to the in-flight message. |
| `src/features/chat/MessageBubble.tsx`, `MarkdownContent.tsx`, `CitationBadge.tsx`, `SqlBlock.tsx`, `SourcesList.tsx` | Answer rendering: markdown tables, citation badges linked to sources, collapsible SQL with a result preview. |
| `src/features/chat/ToolActivity.tsx` | Live stage labels and plan checklist. |
| `src/features/inspector/InspectorPanel.tsx` | Route, confidence, reason, plan, tools, sources, SQL and timings for any message. |
| `src/features/knowledge-base/*` | Upload with client-side validation, status polling, chunk viewer, search, schema browser. |
| `src/features/analytics/*` | Stats, route and language distribution, run trace timeline. |

## Local workflow

```bash
make install && make dev      # Windows: ./tasks.ps1 install; ./tasks.ps1 dev
make seed
make test && make lint
make evaluate                 # offline metrics
```

To create a migration after changing a model:
`cd backend && uv run alembic revision --autogenerate -m "describe change"`.

## How to add a new tool

Example: a `CALCULATION` tool.

1. **Write the tool** in `app/agent/tools/calculator_tool.py`:

   ```python
   class CalculatorTool(BaseTool):
       name = "calc"
       stage = "calculating"
       stage_label = "Calculating..."

       async def run(self, query: str, context: ToolContext) -> ToolResult:
           value = safe_evaluate(query)            # never eval() raw text
           return ToolResult("completed", f"Computed {value}", entity_text=str(value))
   ```

2. **Register it** in `AgentServices.build()`: `registry.register(CalculatorTool())`.
3. **Let the planner use it:** add `"calc"` to the `tool` literal in `_PlannedStep`
   (`app/agent/planner.py`) and describe it in `app/prompts/planner.py`.
4. **Route to it**, if it needs its own route: add a value to `Route`, describe it in
   `app/prompts/router.py`, and add a deterministic single-step plan in `Planner.plan()`.
5. **Show its evidence:** extend `ResponseGenerator.prepare()` to put the tool's evidence in the
   prompt and emit a source type if it is citable.
6. **Test it:** a unit test for the tool, and an integration test in `tests/integration/test_api_chat.py`
   using `ScriptedLLM` to force the route.

The UI needs no change for steps: tool activity renders any `step` event.

## Adding a document type

Add an extractor branch in `app/rag/extractors.py` returning `PageText` items, register the
extension in `SOURCE_TYPES`, add a signature check in `validate_upload`, and add a test to
`tests/unit/test_rag_processing.py`.

## Describing a new table to the agent

Add the model to `app/models/commerce.py` with `comment=` on the table and on each column, and
generate a migration; the comments become the descriptions the model sees. Add user phrasing for
the table to `TABLE_KEYWORDS` in `app/sql/hints.py`, in English, Bengali and Banglish.
