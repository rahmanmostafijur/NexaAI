import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { MessagesSquare } from 'lucide-react';
import { useState } from 'react';
import { useMatch, useNavigate } from 'react-router-dom';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { ErrorState } from '@/components/ui/ErrorState';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/toast';
import {
  deleteConversation,
  listConversations,
  renameConversation,
} from '@/services/conversations';
import { errorMessage } from '@/services/http';
import { queryKeys } from '@/services/queryKeys';
import type { ConversationSummary } from '@/types/api';
import { ConversationItem } from './ConversationItem';

export function ConversationList({ onNavigate }: { onNavigate?: () => void }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const match = useMatch('/c/:conversationId');
  const { notify } = useToast();
  const [pendingDelete, setPendingDelete] = useState<ConversationSummary | null>(null);
  const query = useQuery({ queryKey: queryKeys.conversations, queryFn: listConversations });

  const rename = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => renameConversation(id, title),
    onSuccess: (updated) => {
      queryClient.setQueryData<ConversationSummary[]>(queryKeys.conversations, (list) =>
        list?.map((c) => (c.id === updated.id ? updated : c)),
      );
    },
    onError: (err) =>
      notify({ tone: 'error', title: 'Rename failed', description: errorMessage(err) }),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteConversation(id),
    onSuccess: (_data, id) => {
      queryClient.setQueryData<ConversationSummary[]>(queryKeys.conversations, (list) =>
        list?.filter((c) => c.id !== id),
      );
      queryClient.removeQueries({ queryKey: queryKeys.conversation(id) });
      if (match?.params.conversationId === id) navigate('/', { replace: true });
      setPendingDelete(null);
      notify({ tone: 'success', title: 'Conversation deleted' });
    },
    onError: (err) =>
      notify({ tone: 'error', title: 'Delete failed', description: errorMessage(err) }),
  });

  let body;
  if (query.isPending) {
    body = (
      <div className="space-y-2 px-3" role="status" aria-label="Loading conversations">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    );
  } else if (query.isError) {
    body = (
      <ErrorState
        className="py-6"
        title="Couldn't load chats"
        message={errorMessage(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  } else if (query.data.length === 0) {
    body = (
      <div className="flex flex-col items-center px-4 py-8 text-center text-fg-subtle">
        <MessagesSquare className="mb-2 size-5" aria-hidden />
        <p className="text-xs">No conversations yet</p>
      </div>
    );
  } else {
    body = (
      <ul className="space-y-0.5 px-2">
        {query.data.map((c) => (
          <ConversationItem
            key={c.id}
            conversation={c}
            onNavigate={onNavigate}
            onDelete={setPendingDelete}
            onRename={async (id, title) => {
              await rename.mutateAsync({ id, title });
            }}
          />
        ))}
      </ul>
    );
  }

  return (
    <nav aria-label="Conversations" className="min-h-0 flex-1 overflow-y-auto pb-2">
      <h2 className="px-5 pt-2 pb-1.5 text-[11px] font-semibold tracking-wide text-fg-subtle uppercase">
        Recent
      </h2>
      {body}
      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete conversation?"
        description={
          <>“{pendingDelete?.title}” and all of its messages will be permanently deleted.</>
        }
        confirmLabel="Delete"
        destructive
        loading={remove.isPending}
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => pendingDelete && remove.mutate(pendingDelete.id)}
      />
    </nav>
  );
}
