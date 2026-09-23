import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Drawer } from '@/components/ui/Overlay';
import { SkeletonLines } from '@/components/ui/Skeleton';
import { listChunks } from '@/services/documents';
import { errorMessage } from '@/services/http';
import { queryKeys } from '@/services/queryKeys';
import type { KbDocument } from '@/types/api';
import { formatNumber } from '@/utils/format';
import { langFor } from '@/utils/script';

const PAGE_SIZE = 20;

function ChunkPages({ doc }: { doc: KbDocument }) {
  const [offset, setOffset] = useState(0);
  const query = useQuery({
    queryKey: queryKeys.chunks(doc.id, offset),
    queryFn: () => listChunks(doc.id, PAGE_SIZE, offset),
    placeholderData: keepPreviousData,
  });

  if (query.isPending) return <SkeletonLines lines={6} />;
  if (query.isError) {
    return <ErrorState message={errorMessage(query.error)} onRetry={() => void query.refetch()} />;
  }
  const { items, total } = query.data;
  if (items.length === 0)
    return <EmptyState title="No chunks" description="This document has no indexed chunks yet." />;

  return (
    <div>
      <p className="mb-3 text-xs text-fg-subtle">
        Showing {offset + 1}–{offset + items.length} of {formatNumber(total)} chunks
      </p>
      <ol className="space-y-3">
        {items.map((chunk) => (
          <li key={chunk.id} className="rounded-lg border border-line bg-surface-2/50 p-3">
            <div className="mb-1.5 flex flex-wrap gap-x-3 text-[11px] font-medium text-fg-subtle">
              <span>#{chunk.chunk_index}</span>
              {chunk.page !== null && <span>Page {chunk.page}</span>}
              {chunk.section && <span className="truncate">{chunk.section}</span>}
              <span>~{formatNumber(chunk.token_estimate)} tokens</span>
            </div>
            <p className="text-sm whitespace-pre-wrap text-fg" lang={langFor(chunk.content)}>
              {chunk.content}
            </p>
          </li>
        ))}
      </ol>
      <div className="mt-4 flex justify-between">
        <Button
          variant="secondary"
          size="sm"
          disabled={offset === 0}
          onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
        >
          Previous
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={offset + PAGE_SIZE >= total}
          onClick={() => setOffset((o) => o + PAGE_SIZE)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}

export function ChunksDrawer({ doc, onClose }: { doc: KbDocument | null; onClose: () => void }) {
  return (
    <Drawer
      open={doc !== null}
      onClose={onClose}
      title={doc?.title ?? 'Chunks'}
      description={doc?.filename}
    >
      {doc && <ChunkPages key={doc.id} doc={doc} />}
    </Drawer>
  );
}
