import { useCallback, useEffect, useRef, useState } from 'react';
import { streamChat } from '@/services/chat';
import { isAbortError, isApiError } from '@/services/http';
import type { ChatStreamEvent, StreamErrorEvent } from '@/types/api';
import { applyStreamEvent, emptyLiveState } from '../chatState';
import type { ChatMessage, StreamPhase } from '../types';

export interface UseChatStreamOptions {
  conversationId: string | null;
  initialMessages: ChatMessage[];
  /** Called once when the server assigns an id to a brand-new conversation. */
  onConversationCreated?: (id: string) => void;
  /** Called after every finished stream (success or error). */
  onSettled?: (conversationId: string | null) => void;
}

export interface ChatStream {
  messages: ChatMessage[];
  phase: StreamPhase;
  conversationId: string | null;
  send: (text: string) => void;
  stop: () => void;
  retry: () => void;
}

let localCounter = 0;
function localId(prefix: string): string {
  localCounter += 1;
  return `${prefix}-${Date.now().toString(36)}-${localCounter}`;
}

function toStreamError(err: unknown): StreamErrorEvent {
  if (isApiError(err)) {
    return {
      code: err.code,
      message: err.message,
      retryable: err.status === 0 || err.status >= 429,
    };
  }
  return {
    code: 'stream_failed',
    message: 'The connection was interrupted before the answer finished.',
    retryable: true,
  };
}

const INCOMPLETE_ERROR: StreamErrorEvent = {
  code: 'incomplete_response',
  message: 'The response ended unexpectedly. Please try again.',
  retryable: true,
};

/**
 * Streaming chat state machine: idle → streaming → done | error.
 * Accumulates token deltas and agent events into the in-flight assistant message.
 */
export function useChatStream({
  conversationId: initialConversationId,
  initialMessages,
  onConversationCreated,
  onSettled,
}: UseChatStreamOptions): ChatStream {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [phase, setPhase] = useState<StreamPhase>('idle');
  const [conversationId, setConversationId] = useState<string | null>(initialConversationId);
  const conversationRef = useRef<string | null>(initialConversationId);
  const controllerRef = useRef<AbortController | null>(null);
  const lastUserText = useRef<string | null>(null);
  const callbacks = useRef({ onConversationCreated, onSettled });

  useEffect(() => {
    callbacks.current = { onConversationCreated, onSettled };
  }, [onConversationCreated, onSettled]);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const patchAssistant = useCallback((id: string, fn: (m: ChatMessage) => ChatMessage) => {
    setMessages((current) => current.map((m) => (m.id === id ? fn(m) : m)));
  }, []);

  const handleEvent = useCallback(
    (assistantId: string, event: ChatStreamEvent) => {
      if (event.event === 'meta' && conversationRef.current === null) {
        conversationRef.current = event.data.conversation_id;
        setConversationId(event.data.conversation_id);
        callbacks.current.onConversationCreated?.(event.data.conversation_id);
      }
      patchAssistant(assistantId, (m) => applyStreamEvent(m, event));
    },
    [patchAssistant],
  );

  const run = useCallback(
    async (text: string) => {
      const controller = new AbortController();
      controllerRef.current = controller;
      lastUserText.current = text;
      const now = new Date().toISOString();
      const assistantId = localId('assistant');
      setMessages((current) => [
        ...current,
        {
          id: localId('user'),
          role: 'user',
          content: text,
          createdAt: now,
          details: null,
          live: null,
        },
        {
          id: assistantId,
          role: 'assistant',
          content: '',
          createdAt: now,
          details: null,
          live: emptyLiveState(),
        },
      ]);
      setPhase('streaming');

      let outcome: 'done' | 'error' | 'stopped' | null = null;
      try {
        const body = conversationRef.current
          ? { message: text, conversation_id: conversationRef.current }
          : { message: text };
        for await (const event of streamChat(body, controller.signal)) {
          handleEvent(assistantId, event);
          if (event.event === 'done') outcome = 'done';
          if (event.event === 'error') outcome = 'error';
          if (outcome) break;
        }
        if (!outcome) {
          outcome = 'error';
          handleEvent(assistantId, { event: 'error', data: INCOMPLETE_ERROR });
        }
      } catch (err) {
        if (controller.signal.aborted || isAbortError(err)) {
          outcome = 'stopped';
          patchAssistant(assistantId, (m) => ({
            ...m,
            live: m.live ? { ...m.live, streaming: false, stopped: true } : null,
          }));
        } else {
          outcome = 'error';
          handleEvent(assistantId, { event: 'error', data: toStreamError(err) });
        }
      } finally {
        if (controllerRef.current === controller) controllerRef.current = null;
      }
      setPhase(outcome === 'done' ? 'done' : outcome === 'error' ? 'error' : 'idle');
      callbacks.current.onSettled?.(conversationRef.current);
    },
    [handleEvent, patchAssistant],
  );

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || controllerRef.current) return;
      void run(trimmed);
    },
    [run],
  );

  const stop = useCallback(() => controllerRef.current?.abort(), []);

  const retry = useCallback(() => {
    const text = lastUserText.current;
    if (!text || controllerRef.current) return;
    // Drop the failed assistant bubble and its user prompt; `run` re-adds the prompt.
    setMessages((current) => {
      const lastUser = current.map((m) => m.role).lastIndexOf('user');
      return lastUser === -1 ? current : current.slice(0, lastUser);
    });
    void run(text);
  }, [run]);

  return { messages, phase, conversationId, send, stop, retry };
}
