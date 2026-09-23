import { AlertCircle, Check, Copy, PanelRight, RotateCcw, Square } from 'lucide-react';
import { memo, useCallback, useState } from 'react';
import { LogoMark } from '@/components/layout/Logo';
import { RoutePill } from '@/components/RoutePill';
import { Button } from '@/components/ui/Button';
import { useCopyToClipboard } from '@/hooks/useCopyToClipboard';
import { sourceAnchorId, stripCitations } from '@/utils/citations';
import { cn } from '@/utils/cn';
import { langFor } from '@/utils/script';
import { MarkdownContent } from './MarkdownContent';
import { SourcesList, type HighlightedSource } from './SourcesList';
import { SqlBlock } from './SqlBlock';
import { ToolActivity } from './ToolActivity';
import type { ChatMessage } from './types';

export interface MessageBubbleProps {
  message: ChatMessage;
  selected?: boolean;
  onRetry?: () => void;
  onShowDetails?: (messageId: string) => void;
}

function UserBubble({ message }: { message: ChatMessage }) {
  return (
    <div className="flex justify-end">
      <div
        lang={langFor(message.content)}
        className="max-w-[85%] rounded-2xl rounded-br-md bg-accent-soft px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap text-fg sm:max-w-[75%]"
      >
        {message.content}
      </div>
    </div>
  );
}

function AssistantFooter({
  message,
  selected,
  onShowDetails,
}: Pick<MessageBubbleProps, 'message' | 'selected' | 'onShowDetails'>) {
  const { copied, copy } = useCopyToClipboard();
  const route = message.details?.route ?? message.live?.analysis?.route;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-1">
      {route && <RoutePill route={route} className="mr-1" />}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => void copy(stripCitations(message.content))}
        icon={
          copied ? (
            <Check className="size-3.5" aria-hidden />
          ) : (
            <Copy className="size-3.5" aria-hidden />
          )
        }
      >
        {copied ? 'Copied' : 'Copy'}
      </Button>
      {onShowDetails && (
        <Button
          variant="ghost"
          size="sm"
          aria-pressed={selected}
          onClick={() => onShowDetails(message.id)}
          icon={<PanelRight className="size-3.5" aria-hidden />}
        >
          Details
        </Button>
      )}
    </div>
  );
}

function AssistantBubble({ message, selected, onRetry, onShowDetails }: MessageBubbleProps) {
  const [highlighted, setHighlighted] = useState<HighlightedSource | null>(null);
  const live = message.live;
  const sources = message.details?.sources ?? live?.sources ?? [];
  const sql = message.details?.sql ?? live?.sql ?? [];
  const streaming = live?.streaming ?? false;
  const error = live?.error ?? null;

  const onCitation = useCallback(
    (sourceId: string) => {
      setHighlighted((prev) => ({ id: sourceId, nonce: (prev?.nonce ?? 0) + 1 }));
      document
        .getElementById(sourceAnchorId(message.id, sourceId))
        ?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    },
    [message.id],
  );

  return (
    <div className="flex gap-3">
      <LogoMark className="mt-0.5 size-7" />
      <div className="min-w-0 flex-1">
        {streaming && <ToolActivity status={live?.status ?? null} plan={live?.plan ?? []} />}
        {message.content && (
          <div lang={langFor(message.content)} className="text-fg">
            <MarkdownContent
              content={message.content}
              sources={sources}
              onCitation={onCitation}
              className={cn(streaming && 'md-streaming')}
            />
          </div>
        )}
        {sql.map((result) => (
          <SqlBlock key={result.step_id} result={result} />
        ))}
        <SourcesList sources={sources} messageId={message.id} highlighted={highlighted} />
        {live?.stopped && (
          <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-fg-subtle">
            <Square className="size-3" aria-hidden /> Response stopped
          </p>
        )}
        {error && (
          <div
            role="alert"
            className="mt-2 rounded-xl border border-danger/30 bg-danger-soft px-3.5 py-3 text-sm"
          >
            <p className="flex items-center gap-2 font-medium text-danger">
              <AlertCircle className="size-4" aria-hidden />
              {error.message || 'The answer could not be generated.'}
            </p>
            {onRetry && (
              <Button
                variant="secondary"
                size="sm"
                className="mt-2.5"
                onClick={onRetry}
                icon={<RotateCcw className="size-3.5" aria-hidden />}
              >
                Retry
              </Button>
            )}
          </div>
        )}
        {!streaming && !error && message.content && (
          <AssistantFooter message={message} selected={selected} onShowDetails={onShowDetails} />
        )}
      </div>
    </div>
  );
}

export const MessageBubble = memo(function MessageBubble(props: MessageBubbleProps) {
  return (
    <article
      aria-label={props.message.role === 'user' ? 'Your message' : 'Assistant message'}
      className="animate-fade-in"
    >
      {props.message.role === 'user' ? (
        <UserBubble message={props.message} />
      ) : (
        <AssistantBubble {...props} />
      )}
    </article>
  );
});
