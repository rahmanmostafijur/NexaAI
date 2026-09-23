import { useQuery } from '@tanstack/react-query';
import { ChevronRight, Database, KeyRound, Link2 } from 'lucide-react';
import { useId, useState } from 'react';
import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { SkeletonLines } from '@/components/ui/Skeleton';
import { RequireAdmin } from '@/features/auth/RequireAuth';
import { errorMessage } from '@/services/http';
import { queryKeys } from '@/services/queryKeys';
import { getSchema } from '@/services/schema';
import type { Table } from '@/types/api';
import { cn } from '@/utils/cn';
import { formatNumber } from '@/utils/format';

function TableCard({ table }: { table: Table }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  return (
    <li className="rounded-xl border border-line bg-surface">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-start gap-3 px-4 py-3 text-left"
      >
        <ChevronRight
          className={cn(
            'mt-0.5 size-4 shrink-0 text-fg-subtle transition-transform',
            open && 'rotate-90',
          )}
          aria-hidden
        />
        <div className="min-w-0 flex-1">
          <p className="font-mono text-sm font-semibold text-fg">{table.name}</p>
          {table.description && <p className="mt-0.5 text-sm text-fg-muted">{table.description}</p>}
        </div>
        <span className="shrink-0 text-xs text-fg-subtle">
          {table.columns.length} cols · ~{formatNumber(table.row_estimate)} rows
        </span>
      </button>
      <div id={panelId} hidden={!open} className="border-t border-line px-4 py-3">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-left text-sm">
            <thead className="text-xs text-fg-subtle">
              <tr>
                <th scope="col" className="py-1.5 pr-3 font-medium">
                  Column
                </th>
                <th scope="col" className="py-1.5 pr-3 font-medium">
                  Type
                </th>
                <th scope="col" className="py-1.5 pr-3 font-medium">
                  Keys
                </th>
                <th scope="col" className="py-1.5 font-medium">
                  Description
                </th>
              </tr>
            </thead>
            <tbody>
              {table.columns.map((col) => (
                <tr key={col.name} className="border-t border-line">
                  <td className="py-1.5 pr-3 font-mono text-[13px] text-fg">
                    {col.name}
                    {!col.nullable && (
                      <span className="ml-1 text-[10px] text-fg-subtle">NOT NULL</span>
                    )}
                  </td>
                  <td className="py-1.5 pr-3 font-mono text-xs text-fg-muted">{col.type}</td>
                  <td className="py-1.5 pr-3">
                    <div className="flex flex-wrap gap-1">
                      {col.is_primary_key && (
                        <Badge tone="warning">
                          <KeyRound className="size-3" aria-hidden /> PK
                        </Badge>
                      )}
                      {col.foreign_key && (
                        <Badge tone="accent">
                          <Link2 className="size-3" aria-hidden /> FK → {col.foreign_key.table}.
                          {col.foreign_key.column}
                        </Badge>
                      )}
                    </div>
                  </td>
                  <td className="py-1.5 text-fg-muted">{col.description ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {table.indexes.length > 0 && (
          <div className="mt-3">
            <p className="mb-1 text-xs font-semibold text-fg-subtle">Indexes</p>
            <ul className="space-y-0.5">
              {table.indexes.map((idx) => (
                <li key={idx.name} className="font-mono text-xs text-fg-muted">
                  {idx.name} ({idx.columns.join(', ')})
                  {idx.unique && <Badge className="ml-1.5">unique</Badge>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </li>
  );
}

function SchemaList() {
  const query = useQuery({ queryKey: queryKeys.schema, queryFn: getSchema, staleTime: 5 * 60_000 });
  if (query.isPending) return <SkeletonLines lines={6} />;
  if (query.isError) {
    return (
      <ErrorState
        title="Couldn't load the schema"
        message={errorMessage(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }
  if (query.data.tables.length === 0) {
    return (
      <EmptyState icon={<Database className="size-5" aria-hidden />} title="No tables found" />
    );
  }
  return (
    <ul className="space-y-2.5">
      {query.data.tables.map((t) => (
        <TableCard key={t.name} table={t} />
      ))}
    </ul>
  );
}

export function SchemaTab() {
  return (
    <RequireAdmin>
      <SchemaList />
    </RequireAdmin>
  );
}
