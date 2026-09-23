/**
 * Server-Sent Events parsing for `text/event-stream` bodies.
 *
 * - Bytes are decoded with a streaming TextDecoder, so multi-byte UTF-8
 *   characters (e.g. Bengali script) split across chunks decode correctly.
 * - Lines may end with `\n`, `\r\n` or `\r`, and terminators may be split across chunks.
 * - `event:` sets the event name (default `message`); repeated `data:` lines are joined with `\n`.
 * - Lines starting with `:` are comments / keep-alives and are ignored.
 * - Events without any `data:` line are not dispatched.
 * - A final event not followed by a blank line is still dispatched when the stream ends.
 *
 * Malformed JSON: the event is SKIPPED (not yielded) and reported through the
 * optional `onParseError` callback, so one corrupt frame never aborts a stream.
 */

export interface RawSseEvent {
  event: string;
  data: string;
  id?: string;
}

export interface SseMessage {
  event: string;
  data: unknown;
  id?: string;
}

export interface ParseSseOptions {
  onParseError?: (raw: RawSseEvent, error: unknown) => void;
  /** Aborting cancels the underlying reader and makes the generator throw an AbortError. */
  signal?: AbortSignal;
}

export class SseLineDecoder {
  private buffer = '';
  private eventName = '';
  private dataLines: string[] = [];
  private lastId: string | undefined;
  private hasData = false;

  /** Feeds decoded text; returns every event completed by this chunk. */
  push(text: string): RawSseEvent[] {
    this.buffer += text;
    const events: RawSseEvent[] = [];
    let start = 0;
    for (let i = 0; i < this.buffer.length; i += 1) {
      const ch = this.buffer[i];
      if (ch !== '\n' && ch !== '\r') continue;
      if (ch === '\r' && i === this.buffer.length - 1) break; // may be the first half of \r\n
      const line = this.buffer.slice(start, i);
      if (ch === '\r' && this.buffer[i + 1] === '\n') i += 1;
      start = i + 1;
      const event = this.processLine(line);
      if (event) events.push(event);
    }
    this.buffer = this.buffer.slice(start);
    return events;
  }

  /** Called at end of stream: processes any trailing line and pending event. */
  flush(): RawSseEvent[] {
    const events: RawSseEvent[] = [];
    const rest = this.buffer.replace(/\r$/, '');
    this.buffer = '';
    if (rest) {
      const event = this.processLine(rest);
      if (event) events.push(event);
    }
    const pending = this.dispatch();
    if (pending) events.push(pending);
    return events;
  }

  private processLine(line: string): RawSseEvent | null {
    if (line === '') return this.dispatch();
    if (line.startsWith(':')) return null;
    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'event') this.eventName = value;
    else if (field === 'data') {
      this.dataLines.push(value);
      this.hasData = true;
    } else if (field === 'id' && !value.includes('\0')) this.lastId = value;
    return null;
  }

  private dispatch(): RawSseEvent | null {
    const event: RawSseEvent | null = this.hasData
      ? {
          event: this.eventName || 'message',
          data: this.dataLines.join('\n'),
          ...(this.lastId !== undefined ? { id: this.lastId } : {}),
        }
      : null;
    this.eventName = '';
    this.dataLines = [];
    this.hasData = false;
    return event;
  }
}

function toMessage(raw: RawSseEvent, options: ParseSseOptions): SseMessage | null {
  try {
    const data: unknown = JSON.parse(raw.data);
    return { event: raw.event, data, ...(raw.id !== undefined ? { id: raw.id } : {}) };
  } catch (error) {
    options.onParseError?.(raw, error);
    return null;
  }
}

/** Parses a byte stream into JSON-decoded SSE messages. */
export async function* parseSse(
  stream: ReadableStream<Uint8Array>,
  options: ParseSseOptions = {},
): AsyncGenerator<SseMessage, void, undefined> {
  const reader = stream.getReader();
  const decoder = new TextDecoder('utf-8');
  const lines = new SseLineDecoder();
  const { signal } = options;
  const onAbort = () => void reader.cancel().catch(() => undefined);
  signal?.addEventListener('abort', onAbort, { once: true });
  try {
    while (true) {
      if (signal?.aborted) throw new DOMException('The stream was aborted.', 'AbortError');
      const { value, done } = await reader.read();
      if (signal?.aborted) throw new DOMException('The stream was aborted.', 'AbortError');
      if (done) break;
      for (const raw of lines.push(decoder.decode(value, { stream: true }))) {
        const message = toMessage(raw, options);
        if (message) yield message;
      }
    }
    const tail = decoder.decode();
    const remaining = [...(tail ? lines.push(tail) : []), ...lines.flush()];
    for (const raw of remaining) {
      const message = toMessage(raw, options);
      if (message) yield message;
    }
  } finally {
    signal?.removeEventListener('abort', onAbort);
    reader.releaseLock();
  }
}
