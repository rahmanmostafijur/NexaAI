import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FileText, ShieldAlert } from 'lucide-react';
import { useState } from 'react';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/toast';
import { useAuth } from '@/features/auth/authContext';
import { deleteDocument, listDocuments, reindexDocument } from '@/services/documents';
import { errorMessage } from '@/services/http';
import { queryKeys } from '@/services/queryKeys';
import type { KbDocument, Paginated } from '@/types/api';
import { ChunksDrawer } from './ChunksDrawer';
import { DocumentsTable } from './DocumentsTable';
import { DocumentUpload } from './DocumentUpload';

export const POLL_INTERVAL_MS = 3000;

function isInFlight(doc: KbDocument): boolean {
  return doc.status === 'pending' || doc.status === 'processing';
}

export function DocumentsTab() {
  const { isAdmin } = useAuth();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [toDelete, setToDelete] = useState<KbDocument | null>(null);
  const [viewing, setViewing] = useState<KbDocument | null>(null);

  const query = useQuery({
    queryKey: queryKeys.documents,
    queryFn: listDocuments,
    refetchInterval: (q) => (q.state.data?.items.some(isInFlight) ? POLL_INTERVAL_MS : false),
  });

  const replaceDoc = (updated: KbDocument) =>
    queryClient.setQueryData<Paginated<KbDocument>>(queryKeys.documents, (data) =>
      data ? { ...data, items: data.items.map((d) => (d.id === updated.id ? updated : d)) } : data,
    );

  const reindex = useMutation({
    mutationFn: (doc: KbDocument) => reindexDocument(doc.id),
    onSuccess: (updated) => {
      replaceDoc(updated);
      notify({ tone: 'success', title: 'Reindex queued', description: updated.title });
    },
    onError: (err) =>
      notify({ tone: 'error', title: 'Reindex failed', description: errorMessage(err) }),
  });

  const remove = useMutation({
    mutationFn: (doc: KbDocument) => deleteDocument(doc.id),
    onSuccess: (_d, doc) => {
      queryClient.setQueryData<Paginated<KbDocument>>(queryKeys.documents, (data) =>
        data
          ? { items: data.items.filter((d) => d.id !== doc.id), total: Math.max(0, data.total - 1) }
          : data,
      );
      setToDelete(null);
      notify({ tone: 'success', title: 'Document deleted', description: doc.title });
    },
    onError: (err) =>
      notify({ tone: 'error', title: 'Delete failed', description: errorMessage(err) }),
  });

  const busyId = reindex.isPending
    ? (reindex.variables?.id ?? null)
    : remove.isPending
      ? (remove.variables?.id ?? null)
      : null;

  return (
    <div className="space-y-5">
      {isAdmin ? (
        <DocumentUpload />
      ) : (
        <p className="flex items-center gap-2 rounded-lg border border-line bg-surface-2/60 px-3 py-2.5 text-sm text-fg-muted">
          <ShieldAlert className="size-4 shrink-0" aria-hidden />
          You can browse documents. Uploading, reindexing and deleting require the admin role.
        </p>
      )}

      {query.isPending ? (
        <div className="space-y-2" role="status" aria-label="Loading documents">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : query.isError ? (
        <ErrorState
          title="Couldn't load documents"
          message={errorMessage(query.error)}
          onRetry={() => void query.refetch()}
        />
      ) : query.data.items.length === 0 ? (
        <EmptyState
          icon={<FileText className="size-5" aria-hidden />}
          title="No documents yet"
          description={
            isAdmin
              ? 'Upload policies, manuals, or FAQs to ground answers in your own content.'
              : 'An administrator has not uploaded any documents yet.'
          }
        />
      ) : (
        <DocumentsTable
          documents={query.data.items}
          canManage={isAdmin}
          busyId={busyId}
          onReindex={(doc) => reindex.mutate(doc)}
          onDelete={setToDelete}
          onViewChunks={setViewing}
        />
      )}

      <ConfirmDialog
        open={toDelete !== null}
        title="Delete document?"
        description={
          <>“{toDelete?.title}” and its indexed chunks will be removed from the knowledge base.</>
        }
        confirmLabel="Delete"
        destructive
        loading={remove.isPending}
        onCancel={() => setToDelete(null)}
        onConfirm={() => toDelete && remove.mutate(toDelete)}
      />
      <ChunksDrawer doc={viewing} onClose={() => setViewing(null)} />
    </div>
  );
}
