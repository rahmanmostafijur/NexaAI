import type {
  Analysis,
  MessageDetails,
  PlanStep,
  SqlResult,
  Source,
  StatusEvent,
  StreamErrorEvent,
} from '@/types/api';

/** Transient, client-side state of an assistant message that is (or was) being streamed. */
export interface LiveState {
  streaming: boolean;
  stopped: boolean;
  runId: string | null;
  status: StatusEvent | null;
  analysis: Analysis | null;
  plan: PlanStep[];
  sql: SqlResult[];
  sources: Source[];
  error: StreamErrorEvent | null;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
  details: MessageDetails | null;
  /** Present only for messages produced in this session and not yet finalised by `done`. */
  live: LiveState | null;
}

export type StreamPhase = 'idle' | 'streaming' | 'done' | 'error';
