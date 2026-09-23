import { Database, FileText } from 'lucide-react';
import type { Source } from '@/types/api';
import { sourceAnchorId } from '@/utils/citations';
import { cn } from '@/utils/cn';
import { langFor } from '@/utils/script';

export interface HighlightedSource {
  id: string;
  nonce: number;
}

function SourceItem({
  source,
  messageId,
  highlighted,
}: {
  source: Source;
  messageId: string;
  highlighted: HighlightedSource | null;
}) {
  const active = highlighted?.id === source.id;
  const Icon = source.type === 'database' ? Database : FileText;
  const locator =
    source.type === 'database'
      ? source.tables.length > 0
        ? source.tables.join(', ')
        : null
      : source.page !== null
        ? `Page ${source.page}`
        : source.section;

  return (
    <li
      id={sourceAnchorId(messageId, source.id)}
      data-testid={`source-${source.id}`}
      className={cn(
        'flex min-w-0 items-start gap-2.5 rounded-lg border border-line bg-surface px-3 py-2',
        active && 'animate-flash',
      )}
    >
      <span className="mt-0.5 rounded bg-surface-2 px-1.5 font-mono text-[10.5px] leading-5 font-semibold text-fg-muted">
        {source.id}
      </span>
      <Icon className="mt-1 size-3.5 shrink-0 text-fg-subtle" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-fg" lang={langFor(source.title)}>
          {source.type === 'database' ? 'PostgreSQL' : source.title}
        </p>
        {locator && (
          <p className="truncate text-xs text-fg-muted">
            {source.type === 'database' ? `Tables: ${locator}` : locator}
          </p>
        )}
        {source.type === 'document' && source.snippet && (
          <p className="mt-1 line-clamp-2 text-xs text-fg-subtle" lang={langFor(source.snippet)}>
            {source.snippet}
          </p>
        )}
      </div>
    </li>
  );
}

export function SourcesList({
  sources,
  messageId,
  highlighted = null,
}: {
  sources: Source[];
  messageId: string;
  highlighted?: HighlightedSource | null;
}) {
  if (sources.length === 0) return null;
  return (
    <section aria-label="Sources" className="mt-3">
      <h4 className="mb-1.5 text-[11px] font-semibold tracking-wide text-fg-subtle uppercase">
        Sources
      </h4>
      <ul className="grid gap-1.5 sm:grid-cols-2">
        {sources.map((source) => (
          <SourceItem
            key={highlighted?.id === source.id ? `${source.id}-${highlighted.nonce}` : source.id}
            source={source}
            messageId={messageId}
            highlighted={highlighted}
          />
        ))}
      </ul>
    </section>
  );
}
