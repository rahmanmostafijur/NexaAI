import type { ChatRequest, ChatStreamEvent } from '@/types/api';
import { ApiError, apiFetch } from './http';
import { parseSse } from './sse';

const EVENT_NAMES: ReadonlySet<ChatStreamEvent['event']> = new Set([
  'meta',
  'status',
  'analysis',
  'plan',
  'step',
  'sql',
  'sources',
  'token',
  'done',
  'error',
]);

function isChatEventName(name: string): name is ChatStreamEvent['event'] {
  return EVENT_NAMES.has(name as ChatStreamEvent['event']);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Opens `POST /api/chat/stream` and yields typed agent events.
 * Unknown event names and non-object payloads are ignored.
 */
export async function* streamChat(
  body: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<ChatStreamEvent, void, undefined> {
  const response = await apiFetch('/chat/stream', {
    method: 'POST',
    json: body,
    signal,
    headers: { Accept: 'text/event-stream' },
  });
  if (!response.body) {
    throw new ApiError({
      code: 'invalid_response',
      message: 'The server did not return a stream.',
      status: response.status,
    });
  }
  for await (const message of parseSse(response.body, { signal })) {
    if (!isChatEventName(message.event) || !isRecord(message.data)) continue;
    // Payload shape is defined by the API contract for each event name.
    yield { event: message.event, data: message.data } as unknown as ChatStreamEvent;
  }
}
