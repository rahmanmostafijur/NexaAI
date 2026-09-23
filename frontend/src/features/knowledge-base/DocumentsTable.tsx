import { Layers, RefreshCw, Trash2 } from 'lucide-react';
import { IconButton } from '@/components/ui/IconButton';
import type { KbDocument } from '@/types/api';
import { formatBytes, formatNumber, formatRelativeTime } from '@/utils/format';
import { langFor } from '@/utils/script';
import { DocumentStatusBadge } from './DocumentStatusBadge';

export function DocumentsTable({
  documents,
  canManage,
  onReindex,
  onDelete,
  onViewChunks,
  busyId,
}: {
  documents: KbDocument[];
  canManage: boolean;
  onReindex: (doc: KbDocument) => void;
  onDelete: (doc: KbDocument) => void;
  onViewChunks: (doc: KbDocument) => void;
  busyId: string | null;
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full min-w-[720px] text-left text-sm">
        <thead className="border-b border-line bg-surface-2 text-xs text-fg-muted">
          <tr>
            <th scope="col" className="px-4 py-2.5 font-medium">
              Title
            </th>
            <th scope="col" className="px-3 py-2.5 font-medium">
              Type
            </th>
            <th scope="col" className="px-3 py-2.5 font-medium">
              Size
            </th>
            <th scope="col" className="px-3 py-2.5 font-medium">
              Status
            </th>
            <th scope="col" className="px-3 py-2.5 text-right font-medium">
              Chunks
            </th>
            <th scope="col" className="px-3 py-2.5 text-right font-medium">
              Pages
            </th>
            <th scope="col" className="px-3 py-2.5 font-medium">
              Updated
            </th>
            <th scope="col" className="px-3 py-2.5 text-right font-medium">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.id} className="border-b border-line last:border-b-0 hover:bg-surface-2/40">
              <td className="max-w-[260px] px-4 py-2.5">
                <p className="truncate font-medium text-fg" lang={langFor(doc.title)}>
                  {doc.title}
                </p>
                <p className="truncate text-xs text-fg-subtle">{doc.filename}</p>
              </td>
              <td className="px-3 py-2.5 text-xs font-medium text-fg-muted uppercase">
                {doc.source_type}
              </td>
              <td className="px-3 py-2.5 whitespace-nowrap text-fg-muted">
                {formatBytes(doc.size_bytes)}
              </td>
              <td className="px-3 py-2.5">
                <DocumentStatusBadge doc={doc} />
              </td>
              <td className="px-3 py-2.5 text-right text-fg-muted tabular-nums">
                {formatNumber(doc.chunk_count)}
              </td>
              <td className="px-3 py-2.5 text-right text-fg-muted tabular-nums">
                {doc.page_count !== null ? formatNumber(doc.page_count) : '—'}
              </td>
              <td className="px-3 py-2.5 whitespace-nowrap text-fg-muted">
                {formatRelativeTime(doc.updated_at)}
              </td>
              <td className="px-3 py-2.5">
                <div className="flex justify-end gap-0.5">
                  <IconButton
                    size="sm"
                    label={`View chunks of ${doc.title}`}
                    icon={<Layers className="size-3.5" />}
                    disabled={doc.chunk_count === 0}
                    onClick={() => onViewChunks(doc)}
                  />
                  {canManage && (
                    <>
                      <IconButton
                        size="sm"
                        label={`Reindex ${doc.title}`}
                        icon={<RefreshCw className="size-3.5" />}
                        disabled={busyId === doc.id || doc.status === 'processing'}
                        onClick={() => onReindex(doc)}
                      />
                      <IconButton
                        size="sm"
                        label={`Delete ${doc.title}`}
                        icon={<Trash2 className="size-3.5" />}
                        disabled={busyId === doc.id}
                        onClick={() => onDelete(doc)}
                      />
                    </>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
