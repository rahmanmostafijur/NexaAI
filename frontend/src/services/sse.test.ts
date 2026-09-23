import { describe, expect, it, vi } from 'vitest';
import { parseSse, type SseMessage } from './sse';

function streamOf(chunks: Uint8Array[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      chunks.forEach((c) => controller.enqueue(c));
      controller.close();
    },
  });
}

/** Splits bytes into chunks at the given byte offsets. */
function splitAt(bytes: Uint8Array, offsets: number[]): Uint8Array[] {
  const chunks: Uint8Array[] = [];
  let start = 0;
  for (const offset of [...offsets, bytes.length]) {
    chunks.push(bytes.slice(start, offset));
    start = offset;
  }
  return chunks;
}

async function collect(stream: ReadableStream<Uint8Array>, onParseError?: () => void) {
  const out: SseMessage[] = [];
  for await (const message of parseSse(stream, { onParseError })) out.push(message);
  return out;
}

const encoder = new TextEncoder();
const BENGALI = 'গত ৩ মাসে কোন category সবচেয়ে বেশি revenue?';
const PAYLOAD =
  `event: meta\ndata: {"conversation_id":"c1"}\n\n` +
  `event: token\ndata: ${JSON.stringify({ delta: BENGALI })}\n\n` +
  `event: done\ndata: {"ok":true}\n\n`;
const EXPECTED: SseMessage[] = [
  { event: 'meta', data: { conversation_id: 'c1' } },
  { event: 'token', data: { delta: BENGALI } },
  { event: 'done', data: { ok: true } },
];

describe('parseSse', () => {
  it('parses a single-chunk stream with multiple events', async () => {
    expect(await collect(streamOf([encoder.encode(PAYLOAD)]))).toEqual(EXPECTED);
  });

  it('decodes Bengali text split inside a multi-byte UTF-8 character', async () => {
    const bytes = encoder.encode(PAYLOAD);
    const bengaliStart = encoder.encode(PAYLOAD.slice(0, PAYLOAD.indexOf('গ'))).length;
    // 'গ' is 3 bytes long: split after its first and second byte.
    const chunks = splitAt(bytes, [bengaliStart + 1, bengaliStart + 2, bengaliStart + 7]);
    expect(await collect(streamOf(chunks))).toEqual(EXPECTED);
  });

  it('produces identical output for every possible single split point', async () => {
    const bytes = encoder.encode(PAYLOAD);
    for (let i = 1; i < bytes.length; i += 1) {
      expect(await collect(streamOf(splitAt(bytes, [i])))).toEqual(EXPECTED);
    }
  });

  it('handles one byte per chunk', async () => {
    const bytes = encoder.encode(PAYLOAD);
    const chunks = Array.from(bytes, (_, i) => bytes.slice(i, i + 1));
    expect(await collect(streamOf(chunks))).toEqual(EXPECTED);
  });

  it('ignores comment and keep-alive lines', async () => {
    const text = `: keep-alive\n\n:ping\nevent: status\n: inline comment\ndata: {"stage":"routing"}\n\n`;
    expect(await collect(streamOf([encoder.encode(text)]))).toEqual([
      { event: 'status', data: { stage: 'routing' } },
    ]);
  });

  it('joins multi-line data with newlines and supports CRLF line endings', async () => {
    const text = 'event: plan\r\ndata: {"steps":\r\ndata: []}\r\n\r\n';
    const bytes = encoder.encode(text);
    // Split between \r and \n to exercise the pending-CR path.
    const crIndex = text.indexOf('\r');
    expect(await collect(streamOf(splitAt(bytes, [crIndex + 1])))).toEqual([
      { event: 'plan', data: { steps: [] } },
    ]);
  });

  it('defaults the event name to "message" and flushes a trailing event without blank line', async () => {
    const text = 'data: {"a":1}';
    expect(await collect(streamOf([encoder.encode(text)]))).toEqual([
      { event: 'message', data: { a: 1 } },
    ]);
  });

  it('skips events with malformed JSON and reports them via onParseError', async () => {
    const onParseError = vi.fn();
    const text = `event: token\ndata: {not json}\n\nevent: token\ndata: {"delta":"ok"}\n\n`;
    const out = await collect(streamOf([encoder.encode(text)]), onParseError);
    expect(out).toEqual([{ event: 'token', data: { delta: 'ok' } }]);
    expect(onParseError).toHaveBeenCalledTimes(1);
    expect(onParseError.mock.calls[0]?.[0]).toEqual({ event: 'token', data: '{not json}' });
  });

  it('does not dispatch events that carry no data line', async () => {
    const text = 'event: meta\n\nevent: token\ndata: {"delta":"x"}\n\n';
    expect(await collect(streamOf([encoder.encode(text)]))).toEqual([
      { event: 'token', data: { delta: 'x' } },
    ]);
  });
});
