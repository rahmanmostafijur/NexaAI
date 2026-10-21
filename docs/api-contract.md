# NexaAI Agent — API Contract

All endpoints are served under `/api`. Every endpoint except `/api/health` and the
`/api/auth/*` session endpoints (`login`, `register`, `refresh`, `logout`) requires
`Authorization: Bearer <access token>`.

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
| POST | `/api/auth/refresh` | — (refresh cookie) | `TokenResponse`; rotates the cookie |
| POST | `/api/auth/logout` | — (refresh cookie) | `204`; revokes this session, clears the cookie, idempotent |
| POST | `/api/auth/logout-all` | — (bearer) | `204`; revokes every session of the user |
| POST | `/api/auth/change-password` | `{current_password, new_password}` | `TokenResponse` for a new session; all other sessions are revoked |
| GET | `/api/auth/me` | — | `User` |

```ts
type User = { id: string; email: string; full_name: string; role: "admin" | "user" };
type TokenResponse = { access_token: string; token_type: "bearer"; expires_in: number; user: User };
```

### Session model

- `login`, `register`, `refresh` and `change-password` set the cookie `nexa_refresh`
  (`HttpOnly`, `SameSite=Strict`, `Path=/api/auth`, `Secure` in production). The refresh token
  is never in a response body. `access_token` is a JWT valid for `expires_in` seconds (default
  15 minutes), carries the session id (`sid`), and must be sent as `Authorization: Bearer`.
  Clients keep it in memory only.
- Every request re-checks that the access token's session is not revoked or expired.
- A refresh token works once. Presenting a used one returns `401 refresh_reuse_detected` and
  revokes the whole session. If it was used less than `REFRESH_REUSE_GRACE_SECONDS` ago the
  response is `409 refresh_in_progress` (retry; nothing is revoked), which covers two tabs
  refreshing at once.
- `refresh`, `logout` and `logout-all` require the header `X-Nexa-CSRF: 1`, and reject an
  `Origin` header that is neither the request host nor one of `CORS_ORIGINS` (`403 csrf_failed`).
- `invalid_credentials` (401) means a submitted password was wrong; unlike a plain
  `unauthorized` it must not trigger a token refresh.
- Auth error codes: `unauthorized`, `invalid_credentials`, `invalid_refresh_token`,
  `no_refresh_token`, `refresh_reuse_detected`, `refresh_in_progress` (409), `csrf_failed` (403).

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

Indexing is asynchronous: poll `GET /api/documents/{id}` until `status` is `indexed` or `failed`.
A transient failure (for example the embedding service being down) puts the document back to
`pending` with a "Will retry" note and retries with exponential backoff; a document that is
orphaned by a crash or restart is re-queued automatically, and is marked `failed` after
`INGESTION_MAX_ATTEMPTS` interrupted attempts (use re-index to try again).

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
| GET | `/api/health` | Liveness: `{ status: "ok" \| "degraded", database: boolean, llm_configured: boolean }`. Always 200 while the process is up. |
| GET | `/api/ready` | Readiness: `{ status: "ready" \| "not_ready", checks: { database, migrations, redis } }`. `migrations` is true when the database is at the newest revision; `redis` is `null` when `REDIS_URL` is unset. Returns 503 when not ready. No authentication, no connection details. |
| GET | `/api/system/info` | `{ app_name, version, llm_provider, llm_model, embedding_provider, embedding_model, max_upload_mb, allowed_extensions: string[] }` |
