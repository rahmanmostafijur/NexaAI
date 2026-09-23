import type { ChatStreamEvent, Message, PlanStep, Stage } from '@/types/api';
import type { ChatMessage, LiveState } from './types';

export const STAGE_LABELS: Record<Stage, string> = {
  analyzing: 'Analyzing request...',
  routing: 'Selecting data source...',
  planning: 'Planning steps...',
  querying_database: 'Running database query...',
  searching_documents: 'Searching knowledge base...',
  generating: 'Generating answer...',
  validating: 'Checking the answer...',
};

export function emptyLiveState(): LiveState {
  return {
    streaming: true,
    stopped: false,
    runId: null,
    status: null,
    analysis: null,
    plan: [],
    sql: [],
    sources: [],
    error: null,
  };
}

export function fromServerMessage(message: Message): ChatMessage {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    createdAt: message.created_at,
    details: message.details,
    live: null,
  };
}

function updateStep(plan: PlanStep[], event: Extract<ChatStreamEvent, { event: 'step' }>['data']) {
  return plan.map((step) =>
    step.id === event.id
      ? {
          ...step,
          status: event.status,
          summary: event.summary ?? step.summary,
          duration_ms: event.duration_ms ?? step.duration_ms,
        }
      : step,
  );
}

/**
 * Pure reducer applying a streamed agent event to the in-flight assistant message.
 * `meta`, `done` and `error` phase transitions are handled by the caller.
 */
export function applyStreamEvent(message: ChatMessage, event: ChatStreamEvent): ChatMessage {
  const live = message.live ?? emptyLiveState();
  switch (event.event) {
    case 'meta':
      return { ...message, live: { ...live, runId: event.data.run_id } };
    case 'status':
      return { ...message, live: { ...live, status: event.data } };
    case 'analysis':
      return { ...message, live: { ...live, analysis: event.data } };
    case 'plan':
      return { ...message, live: { ...live, plan: event.data.steps } };
    case 'step':
      return { ...message, live: { ...live, plan: updateStep(live.plan, event.data) } };
    case 'sql':
      return {
        ...message,
        live: {
          ...live,
          sql: [...live.sql.filter((s) => s.step_id !== event.data.step_id), event.data],
        },
      };
    case 'sources':
      return { ...message, live: { ...live, sources: event.data.sources } };
    case 'token':
      return { ...message, content: message.content + event.data.delta };
    case 'done':
      return fromServerMessage(event.data.message);
    case 'error':
      return { ...message, live: { ...live, streaming: false, error: event.data } };
    default:
      return message;
  }
}
