/** Types mirroring the NexaAI Agent API contract (docs/api-contract.md). */

export type Role = 'admin' | 'user';

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
}

export interface TokenResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  user: User;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest extends LoginRequest {
  full_name: string;
}

export interface ErrorEnvelope {
  error: { code: string; message: string; request_id?: string };
}

export type Stage =
  | 'analyzing'
  | 'routing'
  | 'planning'
  | 'querying_database'
  | 'searching_documents'
  | 'generating'
  | 'validating';

export type Route = 'SQL' | 'RAG' | 'HYBRID' | 'GENERAL';

export type LanguageCode = 'en' | 'bn' | 'banglish' | 'mixed';

export interface Analysis {
  language: { code: LanguageCode; label: string };
  route: Route;
  confidence: number;
  reason: string;
  requires_database: boolean;
  requires_documents: boolean;
  standalone_query: string;
}

export type StepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

export interface PlanStep {
  id: string;
  tool: 'sql' | 'rag' | 'general';
  description: string;
  status: StepStatus;
  summary?: string;
  duration_ms?: number;
}

export type SqlCell = string | number | boolean | null;

export interface SqlResult {
  step_id: string;
  sql: string;
  columns: string[];
  rows: SqlCell[][];
  row_count: number;
  truncated: boolean;
  attempts: number;
}

export interface DatabaseSource {
  id: string;
  type: 'database';
  title: string;
  tables: string[];
}

export interface DocumentSource {
  id: string;
  type: 'document';
  title: string;
  document_id: string;
  filename: string;
  page: number | null;
  section: string | null;
  snippet: string;
  score: number;
}

export type Source = DatabaseSource | DocumentSource;

export interface StageTiming {
  name: string;
  duration_ms: number;
}

export interface MessageDetails {
  run_id: string;
  route: Route;
  confidence: number;
  reason: string;
  language: string;
  plan: PlanStep[];
  sql: SqlResult[];
  sources: Source[];
  timings: { total_ms: number; stages: StageTiming[] };
  grounded: boolean;
  warnings: string[];
}

export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  details: MessageDetails | null;
}

export interface ChatRequest {
  message: string;
  conversation_id?: string;
}

/* ---- SSE event payloads ---- */

export interface MetaEvent {
  conversation_id: string;
  run_id: string;
  user_message_id: string;
}

export interface StatusEvent {
  stage: Stage;
  label: string;
}

export interface PlanEvent {
  steps: PlanStep[];
}

export interface StepEvent {
  id: string;
  status: Exclude<StepStatus, 'pending'>;
  summary?: string;
  duration_ms?: number;
}

export interface SourcesEvent {
  sources: Source[];
}

export interface TokenEvent {
  delta: string;
}

export interface DoneEvent {
  message: Message;
}

export interface StreamErrorEvent {
  code: string;
  message: string;
  retryable: boolean;
}

export type ChatStreamEvent =
  | { event: 'meta'; data: MetaEvent }
  | { event: 'status'; data: StatusEvent }
  | { event: 'analysis'; data: Analysis }
  | { event: 'plan'; data: PlanEvent }
  | { event: 'step'; data: StepEvent }
  | { event: 'sql'; data: SqlResult }
  | { event: 'sources'; data: SourcesEvent }
  | { event: 'token'; data: TokenEvent }
  | { event: 'done'; data: DoneEvent }
  | { event: 'error'; data: StreamErrorEvent };

/* ---- Conversations ---- */

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ConversationDetail {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: Message[];
}

/* ---- Documents ---- */

export type DocumentStatus = 'pending' | 'processing' | 'indexed' | 'failed';
export type SourceType = 'pdf' | 'docx' | 'txt' | 'markdown' | 'csv';

export interface KbDocument {
  id: string;
  title: string;
  filename: string;
  content_type: string;
  source_type: SourceType;
  size_bytes: number;
  status: DocumentStatus;
  chunk_count: number;
  page_count: number | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  indexed_at: string | null;
}

export interface Chunk {
  id: string;
  chunk_index: number;
  page: number | null;
  section: string | null;
  content: string;
  token_estimate: number;
}

export interface Paginated<T> {
  items: T[];
  total: number;
}

/* ---- Knowledge search ---- */

export interface SearchResult {
  chunk_id: string;
  document_id: string;
  title: string;
  filename: string;
  page: number | null;
  section: string | null;
  content: string;
  score: number;
  vector_score: number | null;
  keyword_score: number | null;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
}

/* ---- Schema ---- */

export interface TableColumn {
  name: string;
  type: string;
  nullable: boolean;
  description: string | null;
  is_primary_key: boolean;
  foreign_key: { table: string; column: string } | null;
}

export interface TableIndex {
  name: string;
  columns: string[];
  unique: boolean;
}

export interface Table {
  name: string;
  description: string | null;
  row_estimate: number;
  columns: TableColumn[];
  indexes: TableIndex[];
}

export interface SchemaResponse {
  schema: string;
  tables: Table[];
}

/* ---- Agent runs ---- */

export type RunStatus = 'running' | 'success' | 'failed';

export interface RunSummary {
  id: string;
  conversation_id: string | null;
  created_at: string;
  route: Route | null;
  language: string | null;
  confidence: number | null;
  status: RunStatus;
  total_ms: number | null;
  tools_used: string[];
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface TraceEntry {
  name: string;
  duration_ms: number;
  status: string;
  detail?: string;
}

export interface RunDetail extends RunSummary {
  error_code: string | null;
  error_message: string | null;
  token_usage: TokenUsage | null;
  trace: TraceEntry[];
}

export interface Stats {
  total_runs: number;
  success_rate: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  routes: Record<string, number>;
  languages: Record<string, number>;
}

/* ---- System ---- */

export interface SystemInfo {
  app_name: string;
  version: string;
  llm_provider: string;
  llm_model: string;
  embedding_provider: string;
  embedding_model: string;
  max_upload_mb: number;
  allowed_extensions: string[];
}
