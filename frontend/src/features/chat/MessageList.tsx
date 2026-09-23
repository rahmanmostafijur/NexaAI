import { useEffect, useRef, type ReactNode } from 'react';
import { MessageBubble } from './MessageBubble';
import type { ChatMessage } from './types';

const PIN_THRESHOLD_PX = 120;

export function MessageList({
  messages,
  selectedId,
  onRetry,
  onShowDetails,
  footer,
}: {
  messages: ChatMessage[];
  selectedId: string | null;
  onRetry?: () => void;
  onShowDetails?: (messageId: string) => void;
  footer?: ReactNode;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);

  useEffect(() => {
    const node = scroller.current;
    if (node && pinned.current) node.scrollTop = node.scrollHeight;
  }, [messages]);

  function onScroll() {
    const node = scroller.current;
    if (!node) return;
    pinned.current = node.scrollHeight - node.scrollTop - node.clientHeight < PIN_THRESHOLD_PX;
  }

  const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant');

  return (
    <div ref={scroller} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6 sm:px-6">
        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            selected={message.id === selectedId}
            onRetry={message.id === lastAssistant?.id ? onRetry : undefined}
            onShowDetails={onShowDetails}
          />
        ))}
        {footer}
      </div>
    </div>
  );
}
