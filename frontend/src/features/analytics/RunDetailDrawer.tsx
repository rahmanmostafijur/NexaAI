import { useQuery } from '@tanstack/react-query';
import { RoutePill } from '@/components/RoutePill';
import { ErrorState } from '@/components/ui/ErrorState';
import { Drawer } from '@/components/ui/Overlay';
import { SkeletonLines } from '@/components/ui/Skeleton';
import { languageLabel } from '@/features/inspector/inspectorData';
import { getRun } from '@/services/agentRuns';
import { errorMessage } from '@/services/http';
import { queryKeys } from '@/services/queryKeys';
import type { RunDetail } from '@/types/api';
import { cn } from '@/utils/cn';
import { formatDateTime, formatDuration, formatNumber, formatPercent } from '@/utils/format';
import { RunStatusBadge } from './RunStatusBadge';

function dotClass(status: string): string {
  if (status === 'completed' || status === 'success') return 'bg-success';
  if (status === 'failed' || status === 'error') return 'bg-danger';
  if (status === 'skipped') return 'bg-fg-subtle';
  return 'bg-accent';
}

function RunBody({ run }: { run: RunDetail }) {
  return (
    <div className="space-y-6">
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-xs text-fg-subtle">Status</dt>
          <dd className="mt-0.5">
            <RunStatusBadge status={run.status} />
          </dd>
        </div>
        <div>
          <dt className="text-xs text-fg-subtle">Route</dt>
          <dd className="mt-0.5">{run.route ? <RoutePill route={run.route} /> : '—'}</dd>
        </div>
        <div>
          <dt className="text-xs text-fg-subtle">Language</dt>
          <dd className="mt-0.5 text-fg">{run.language ? languageLabel(run.language) : '—'}</dd>
        </div>
        <div>
          <dt className="text-xs text-fg-subtle">Confidence</dt>
          <dd className="mt-0.5 text-fg">
            {run.confidence !== null ? formatPercent(run.confidence) : '—'}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-fg-subtle">Total time</dt>
          <dd className="mt-0.5 text-fg">{formatDuration(run.total_ms)}</dd>
        </div>
        <div>
          <dt className="text-xs text-fg-subtle">Started</dt>
          <dd className="mt-0.5 text-fg">{formatDateTime(run.created_at)}</dd>
        </div>
      </dl>

      {(run.error_code || run.error_message) && (
        <div role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">
          {run.error_code && <p className="font-mono text-xs font-semibold">{run.error_code}</p>}
          {run.error_message && <p className="mt-0.5">{run.error_message}</p>}
        </div>
      )}

      <section>
        <h3 className="mb-2 text-xs font-semibold tracking-wide text-fg-subtle uppercase">
          Token usage
        </h3>
        {run.token_usage ? (
          <dl className="grid grid-cols-3 gap-2 text-center">
            {(
              [
                ['Prompt', run.token_usage.prompt_tokens],
                ['Completion', run.token_usage.completion_tokens],
                ['Total', run.token_usage.total_tokens],
              ] as const
            ).map(([label, value]) => (
              <div key={label} className="rounded-lg bg-surface-2 px-2 py-2">
                <dt className="text-[11px] text-fg-subtle">{label}</dt>
                <dd className="text-sm font-semibold text-fg tabular-nums">
                  {formatNumber(value)}
                </dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="text-sm text-fg-subtle">Not recorded.</p>
        )}
      </section>

      <section>
        <h3 className="mb-3 text-xs font-semibold tracking-wide text-fg-subtle uppercase">
          Execution trace
        </h3>
        {run.trace.length === 0 ? (
          <p className="text-sm text-fg-subtle">No trace recorded.</p>
        ) : (
          <ol className="relative ml-1.5 border-l border-line">
            {run.trace.map((entry, i) => (
              <li key={`${entry.name}-${i}`} className="relative pb-4 pl-5 last:pb-0">
                <span
                  className={cn(
                    'absolute top-1.5 -left-[5px] size-2.5 rounded-full ring-2 ring-surface',
                    dotClass(entry.status),
                  )}
                  aria-hidden
                />
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="text-sm font-medium text-fg">{entry.name}</p>
                  <span className="text-xs text-fg-muted tabular-nums">
                    {formatDuration(entry.duration_ms)}
                  </span>
                </div>
                <p className="text-xs text-fg-subtle">{entry.status}</p>
                {entry.detail && (
                  <p className="mt-0.5 text-xs break-words text-fg-muted">{entry.detail}</p>
                )}
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

function RunLoader({ id }: { id: string }) {
  const query = useQuery({ queryKey: queryKeys.run(id), queryFn: () => getRun(id) });
  if (query.isPending) return <SkeletonLines lines={8} />;
  if (query.isError)
    return <ErrorState message={errorMessage(query.error)} onRetry={() => void query.refetch()} />;
  return <RunBody run={query.data} />;
}

export function RunDetailDrawer({ runId, onClose }: { runId: string | null; onClose: () => void }) {
  return (
    <Drawer
      open={runId !== null}
      onClose={onClose}
      title="Run details"
      description={runId ?? undefined}
    >
      {runId && <RunLoader key={runId} id={runId} />}
    </Drawer>
  );
}
