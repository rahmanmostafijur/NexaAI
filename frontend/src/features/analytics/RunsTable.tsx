import { RoutePill } from '@/components/RoutePill';
import { languageLabel } from '@/features/inspector/inspectorData';
import type { RunSummary } from '@/types/api';
import { formatDuration, formatPercent, formatRelativeTime } from '@/utils/format';
import { RunStatusBadge } from './RunStatusBadge';

export function RunsTable({
  runs,
  onSelect,
}: {
  runs: RunSummary[];
  onSelect: (id: string) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full min-w-[680px] text-left text-sm">
        <thead className="border-b border-line bg-surface-2 text-xs text-fg-muted">
          <tr>
            <th scope="col" className="px-4 py-2.5 font-medium">
              When
            </th>
            <th scope="col" className="px-3 py-2.5 font-medium">
              Route
            </th>
            <th scope="col" className="px-3 py-2.5 font-medium">
              Language
            </th>
            <th scope="col" className="px-3 py-2.5 text-right font-medium">
              Confidence
            </th>
            <th scope="col" className="px-3 py-2.5 font-medium">
              Tools
            </th>
            <th scope="col" className="px-3 py-2.5 text-right font-medium">
              Latency
            </th>
            <th scope="col" className="px-3 py-2.5 font-medium">
              Status
            </th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id} className="border-b border-line last:border-b-0 hover:bg-surface-2/50">
              <td className="px-4 py-2">
                <button
                  type="button"
                  onClick={() => onSelect(run.id)}
                  className="text-left font-medium whitespace-nowrap text-accent hover:underline"
                  aria-label={`Open run details from ${formatRelativeTime(run.created_at)}`}
                >
                  {formatRelativeTime(run.created_at)}
                </button>
              </td>
              <td className="px-3 py-2">{run.route ? <RoutePill route={run.route} /> : '—'}</td>
              <td className="px-3 py-2 text-fg-muted">
                {run.language ? languageLabel(run.language) : '—'}
              </td>
              <td className="px-3 py-2 text-right text-fg-muted tabular-nums">
                {run.confidence !== null ? formatPercent(run.confidence) : '—'}
              </td>
              <td className="px-3 py-2 font-mono text-xs text-fg-muted">
                {run.tools_used.join(', ') || '—'}
              </td>
              <td className="px-3 py-2 text-right whitespace-nowrap text-fg-muted tabular-nums">
                {formatDuration(run.total_ms)}
              </td>
              <td className="px-3 py-2">
                <RunStatusBadge status={run.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
