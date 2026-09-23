import { cn } from '@/utils/cn';
import { formatNumber, formatPercent } from '@/utils/format';

export interface BarDatum {
  key: string;
  label: string;
  value: number;
  barClass?: string;
}

/** Accessible horizontal bar chart built from plain elements. */
export function BarList({ title, data }: { title: string; data: BarDatum[] }) {
  const total = data.reduce((sum, d) => sum + d.value, 0);
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <figure>
      <figcaption className="mb-3 text-sm font-semibold text-fg">{title}</figcaption>
      {data.length === 0 ? (
        <p className="text-sm text-fg-subtle">No data yet.</p>
      ) : (
        <ul className="space-y-2.5">
          {data.map((d) => (
            <li key={d.key}>
              <div className="mb-1 flex justify-between text-xs">
                <span className="font-medium text-fg">{d.label}</span>
                <span className="text-fg-muted tabular-nums">
                  {formatNumber(d.value)} · {formatPercent(total ? d.value / total : 0)}
                </span>
              </div>
              <div
                className="h-2 overflow-hidden rounded-full bg-surface-3"
                role="meter"
                aria-label={`${d.label}: ${formatNumber(d.value)} runs`}
                aria-valuemin={0}
                aria-valuemax={total}
                aria-valuenow={d.value}
              >
                <div
                  className={cn('h-full rounded-full', d.barClass ?? 'bg-accent')}
                  style={{ width: `${(d.value / max) * 100}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </figure>
  );
}
