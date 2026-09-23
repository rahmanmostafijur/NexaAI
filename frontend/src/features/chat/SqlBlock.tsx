import { ChevronRight, Database } from 'lucide-react';
import { useId, useState } from 'react';
import { Badge } from '@/components/ui/Badge';
import type { SqlCell, SqlResult } from '@/types/api';
import { cn } from '@/utils/cn';
import { formatNumber } from '@/utils/format';
import { langFor } from '@/utils/script';
import { MarkdownContent } from './MarkdownContent';

export const PREVIEW_ROWS = 10;

function fence(code: string): string {
  const longest = Math.max(2, ...Array.from(code.matchAll(/`+/g), (m) => m[0].length));
  const ticks = '`'.repeat(longest + 1);
  return `${ticks}sql\n${code}\n${ticks}`;
}

function Cell({ value }: { value: SqlCell }) {
  if (value === null) return <span className="text-fg-subtle italic">NULL</span>;
  if (typeof value === 'boolean') return <>{value ? 'true' : 'false'}</>;
  if (typeof value === 'number') return <span className="tabular-nums">{formatNumber(value)}</span>;
  return <span lang={langFor(value)}>{value}</span>;
}

export function ResultTable({ result }: { result: SqlResult }) {
  const rows = result.rows.slice(0, PREVIEW_ROWS);
  const hiddenRows = Math.max(result.row_count - rows.length, 0);
  if (result.columns.length === 0) return null;
  return (
    <div>
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full text-left text-[13px]">
          <thead className="bg-surface-2 text-fg-muted">
            <tr>
              {result.columns.map((col) => (
                <th key={col} scope="col" className="px-3 py-2 font-semibold whitespace-nowrap">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, r) => (
              <tr key={r} className="border-t border-line">
                {result.columns.map((col, c) => (
                  <td key={col} className="px-3 py-1.5 whitespace-nowrap text-fg">
                    <Cell value={row[c] ?? null} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1.5 text-xs text-fg-subtle">
        {formatNumber(result.row_count)} {result.row_count === 1 ? 'row' : 'rows'}
        {hiddenRows > 0 && ` · showing first ${rows.length}`}
        {result.truncated && ' · result truncated by the server row limit'}
      </p>
    </div>
  );
}

/** Generated SQL (collapsed by default) plus a preview of its result set. */
export function SqlBlock({
  result,
  defaultOpen = false,
}: {
  result: SqlResult;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();
  return (
    <div className="mt-3 rounded-xl border border-line bg-surface-2/50 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((o) => !o)}
          className="inline-flex items-center gap-1.5 rounded-md py-0.5 pr-1.5 text-sm font-medium text-fg hover:text-accent"
        >
          <ChevronRight
            className={cn('size-4 transition-transform', open && 'rotate-90')}
            aria-hidden
          />
          <Database className="size-3.5 text-fg-subtle" aria-hidden />
          Generated SQL
        </button>
        {result.attempts > 1 && <Badge tone="warning">{result.attempts} attempts</Badge>}
      </div>
      <div id={panelId} hidden={!open}>
        {open && <MarkdownContent content={fence(result.sql)} className="-my-1" />}
      </div>
      <div className="mt-2">
        <ResultTable result={result} />
      </div>
    </div>
  );
}
