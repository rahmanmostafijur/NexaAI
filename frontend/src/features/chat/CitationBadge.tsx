import { Tooltip } from '@/components/ui/Tooltip';
import type { Source } from '@/types/api';
import { cn } from '@/utils/cn';
import { sourceLabel } from './sourceLabel';

export function CitationBadge({
  sourceId,
  source,
  onActivate,
}: {
  sourceId: string;
  source: Source | undefined;
  onActivate?: (sourceId: string) => void;
}) {
  const label = source ? sourceLabel(source) : `Source ${sourceId}`;
  const isDb = sourceId.startsWith('DB');
  return (
    <Tooltip content={label}>
      {(describedBy) => (
        <button
          type="button"
          aria-describedby={describedBy}
          aria-label={`Citation ${sourceId}: ${label}`}
          onClick={() => onActivate?.(sourceId)}
          className={cn(
            'mx-0.5 inline-flex h-[18px] -translate-y-px items-center rounded-md px-1.5 align-middle font-mono text-[10.5px] font-semibold ring-1 ring-inset transition-colors',
            isDb
              ? 'bg-sky-500/10 text-sky-700 ring-sky-500/30 hover:bg-sky-500/20 dark:text-sky-300'
              : 'bg-accent-soft text-accent ring-accent/25 hover:bg-accent/15',
          )}
        >
          {sourceId}
        </button>
      )}
    </Tooltip>
  );
}
