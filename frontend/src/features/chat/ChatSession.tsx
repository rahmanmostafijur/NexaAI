import { useQueryClient } from '@tanstack/react-query';
import { PanelRight } from 'lucide-react';
import { useCallback, useMemo, useState } from 'react';
import { IconButton } from '@/components/ui/IconButton';
import { InspectorPanel } from '@/features/inspector/InspectorPanel';
import { useInspectorDefault } from '@/features/settings/preferences';
import { LARGE_SCREEN_QUERY, useMediaQuery } from '@/hooks/useMediaQuery';
import { queryKeys } from '@/services/queryKeys';
import { langFor } from '@/utils/script';
import { STAGE_LABELS } from './chatState';
import { ChatEmptyState } from './ChatEmptyState';
import { ChatInput } from './ChatInput';
import { useChatStream } from './hooks/useChatStream';
import { MessageList } from './MessageList';
import type { ChatMessage } from './types';

export interface ChatSessionProps {
  conversationId: string | null;
  initialMessages: ChatMessage[];
  title?: string;
  onConversationCreated?: (id: string) => void;
}

export function ChatSession({
  conversationId,
  initialMessages,
  title,
  onConversationCreated,
}: ChatSessionProps) {
  const queryClient = useQueryClient();
  const [inspectorDefault] = useInspectorDefault();
  const isLarge = useMediaQuery(LARGE_SCREEN_QUERY);
  const [inspectorOpen, setInspectorOpen] = useState(() => inspectorDefault && isLarge);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const onSettled = useCallback(
    (id: string | null) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.conversations, exact: true });
      void queryClient.invalidateQueries({ queryKey: queryKeys.stats });
      void queryClient.invalidateQueries({ queryKey: queryKeys.runs });
      if (id) {
        void queryClient.invalidateQueries({
          queryKey: queryKeys.conversation(id),
          refetchType: 'none',
        });
      }
    },
    [queryClient],
  );

  const chat = useChatStream({ conversationId, initialMessages, onConversationCreated, onSettled });
  const streaming = chat.phase === 'streaming';

  const lastAssistant = useMemo(
    () => [...chat.messages].reverse().find((m) => m.role === 'assistant') ?? null,
    [chat.messages],
  );
  const inspected = chat.messages.find((m) => m.id === selectedId) ?? lastAssistant;
  const liveStatus = lastAssistant?.live?.streaming
    ? (lastAssistant.live.status?.label ?? STAGE_LABELS.analyzing)
    : chat.phase === 'done'
      ? 'Answer ready'
      : '';

  const showDetails = useCallback((id: string) => {
    setSelectedId(id);
    setInspectorOpen(true);
  }, []);

  const heading = title ?? (chat.messages[0]?.content || 'New chat');

  return (
    <div className="flex h-full min-h-0">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-line bg-canvas/80 px-4 backdrop-blur sm:px-6">
          <h1
            className="min-w-0 flex-1 truncate text-sm font-semibold text-fg"
            lang={langFor(heading)}
          >
            {heading}
          </h1>
          <IconButton
            label={inspectorOpen ? 'Hide inspector' : 'Show inspector'}
            aria-pressed={inspectorOpen}
            active={inspectorOpen}
            icon={<PanelRight className="size-4" />}
            onClick={() => setInspectorOpen((o) => !o)}
          />
        </header>
        <p className="sr-only" aria-live="polite" role="status">
          {liveStatus}
        </p>
        {chat.messages.length === 0 ? (
          <div className="min-h-0 flex-1 overflow-y-auto">
            <ChatEmptyState onPick={chat.send} />
          </div>
        ) : (
          <MessageList
            messages={chat.messages}
            selectedId={inspectorOpen ? (inspected?.id ?? null) : null}
            onRetry={chat.phase === 'error' ? chat.retry : undefined}
            onShowDetails={showDetails}
          />
        )}
        <ChatInput onSend={chat.send} onStop={chat.stop} streaming={streaming} autoFocus />
      </div>
      <InspectorPanel
        message={inspected}
        open={inspectorOpen}
        onClose={() => setInspectorOpen(false)}
      />
    </div>
  );
}
