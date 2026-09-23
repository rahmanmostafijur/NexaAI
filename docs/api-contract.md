# NexaAI Agent — API Contract

All endpoints are served under `/api`. Every endpoint except `/api/health`,
`/api/auth/login` and `/api/auth/register` requires `Authorization: Bearer <token>`.

## Error envelope

Every non-2xx response has the same shape:

```json
{ "error": { "code": "not_found", "message": "Conversation not found", "request_id": "3f1c…" } }
```

Common codes: `validation_error` (422), `unauthorized` (401), `forbidden` (403),
`not_found` (404), `rate_limited` (429), `payload_too_large` (413),
`unsupported_media_type` (415), `llm_unavailable` (503), `internal_error` (500).

## Auth

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/api/auth/login` | `{email, password}` | `TokenResponse` |
| POST | `/api/auth/register` | `{email, password, full_name}` | `TokenResponse` (403 if registration disabled) |
| GET | `/api/auth/me` | — | `User` |

```ts
type User = { id: string; email: string; full_name: string; role: "admin" | "user" };
type TokenResponse = { access_token: string; token_type: "bearer"; expires_in: number; user: User };
```

## Chat

### `POST /api/chat/stream` — Server-Sent Events

Request: `{ "message": string (1..4000 chars), "conversation_id"?: string }`

The response is `text/event-stream`. Each event has an `event:` name and a JSON `data:` line.

| event | data |
|---|---|
| `meta` | `{ conversation_id, run_id, user_message_id }` |
| `status` | `{ stage: Stage, label: string }` |
| `analysis` | `Analysis` |
| `plan` | `{ steps: PlanStep[] }` |
| `step` | `{ id, status: "running" \| "completed" \| "failed" \| "skipped", summary?: string, duration_ms?: number }` |
| `sql` | `SqlResult` |
| `sources` | `{ sources: Source[] }` |
| `token` | `{ delta: string }` |
| `done` | `{ message: Message }` — final, validated message; replaces streamed text |
| `error` | `{ code: string, message: string, retryable: boolean }` |

```ts
type Stage = "analyzing" | "routing" | "planning" | "querying_database"
           | "searching_documents" | "generating" | "validating";

type Route = "SQL" | "RAG" | "HYBRID" | "GENERAL";

type Analysis = {
  language: { code: "en" | "bn" | "banglish" | "mixed"; label: string };
  route: Route;
  confidence: number;          // 0..1
  reason: string;
  requires_database: boolean;
  requires_documents: boolean;
  standalone_query: string;    // query after resolving conversation references
};

type PlanStep = {
  id: string;                  // "s1", "s2", …
  tool: "sql" | "rag" | "general";
  description: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  summary?: string;
  duration_ms?: number;
};

type SqlResult = {
  step_id: string;
  sql: string;
  columns: string[];
  rows: (string | number | boolean | null)[][];
  row_count: number;
  truncated: boolean;
  attempts: number;
};

type Source =
  | { id: string; type: "database"; title: string; tables: string[] }                // id "DB1"
  | { id: string; type: "document"; title: string; document_id: string; filename: string;
      page: number | null; section: string | null; snippet: string; score: number }; // id "S1"

type Message = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;             // markdown; may contain citation markers like [S1] or [DB1]
  created_at: string;          // ISO 8601
  details: MessageDetails | null;  // only for assistant messages
};

type MessageDetails = {
  run_id: string;
  route: Route;
  confidence: number;
  reason: string;
  language: string;
  plan: PlanStep[];
  sql: SqlResult[];
  sources: Source[];
  timings: { total_ms: number; stages: { name: string; duration_ms: number }[] };
  grounded: boolean;
  warnings: string[];
};
```

### `POST /api/chat` — non-streaming

Same request. Response: `{ conversation_id: string, message: Message }`.

## Conversations

| Method | Path | Response |
|---|---|---|
| GET | `/api/conversations` | `ConversationSummary[]` (newest first) |
| GET | `/api/conversations/{id}` | `{ id, title, created_at, updated_at, messages: Message[] }` |
| PATCH | `/api/conversations/{id}` | body `{ title }` → `ConversationSummary` |
| DELETE | `/api/conversations/{id}` | 204 |

```ts
type ConversationSummary = { id: string; title: string; created_at: string; updated_at: string; message_count: number };
```

## Documents (upload/delete/reindex require role `admin`)

| Method | Path | Notes |
|---|---|---|
| POST | `/api/documents` | multipart, field `file`, optional field `title` → `Document` (status `pending`) |
| GET | `/api/documents` | `{ items: Document[], total: number }` |
| GET | `/api/documents/{id}` | `Document` |
| GET | `/api/documents/{id}/chunks?limit=&offset=` | `{ items: Chunk[], total: number }` |
| DELETE | `/api/documents/{id}` | 204 |
| POST | `/api/documents/{id}/reindex` | `Document` (status `pending`) |

```ts
type Document = {
  id: string; title: string; filename: string; content_type: string;
  source_type: "pdf" | "docx" | "txt" | "markdown" | "csv";
  size_bytes: number; status: "pending" | "processing" | "indexed" | "failed";
  chunk_count: number; page_count: number | null; error: string | null;
  created_at: string; updated_at: string; indexed_at: string | null;
};
type Chunk = { id: string; chunk_index: number; page: number | null; section: string | null; content: string; token_estimate: number };
```

Allowed extensions: `.pdf .docx .txt .md .markdown .csv`; max size from `/api/system/info`.

## Knowledge search

`GET /api/knowledge/search?q=...&top_k=5&document_id=...`

```ts
type SearchResponse = { query: string; results: {
  chunk_id: string; document_id: string; title: string; filename: string;
  page: number | null; section: string | null; content: string;
  score: number; vector_score: number | null; keyword_score: number | null; }[] };
```

## Schema (role `admin`)

| Method | Path | Response |
|---|---|---|
| GET | `/api/schema` | `{ schema: string, tables: Table[] }` |
| GET | `/api/schema/tables` | `{ name, description, column_count, row_estimate }[]` |

```ts
type Table = { name: string; description: string | null; row_estimate: number;
  columns: { name: string; type: string; nullable: boolean; description: string | null;
             is_primary_key: boolean; foreign_key: { table: string; column: string } | null }[];
  indexes: { name: string; columns: string[]; unique: boolean }[] };
```

## Agent runs (observability)

Users see their own runs; admins see all.

| Method | Path | Response |
|---|---|---|
| GET | `/api/agent/runs?limit=50` | `RunSummary[]` |
| GET | `/api/agent/runs/{id}` | `RunDetail` |
| GET | `/api/agent/stats` | `Stats` |

```ts
type RunSummary = { id: string; conversation_id: string | null; created_at: string; route: Route | null;
  language: string | null; confidence: number | null; status: "running" | "success" | "failed";
  total_ms: number | null; tools_used: string[] };
type RunDetail = RunSummary & { error_code: string | null; error_message: string | null;
  token_usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number } | null;
  trace: { name: string; duration_ms: number; status: string; detail?: string }[] };
type Stats = { total_runs: number; success_rate: number; avg_latency_ms: number; p95_latency_ms: number;
  routes: Record<string, number>; languages: Record<string, number> };
```

## System

| Method | Path | Response |
|---|---|---|
| GET | `/api/health` | `{ status: "ok" \| "degraded", database: boolean, llm_configured: boolean }` |
| GET | `/api/system/info` | `{ app_name, version, llm_provider, llm_model, embedding_provider, embedding_model, max_upload_mb, allowed_extensions: string[] }` |
