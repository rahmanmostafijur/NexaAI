import { useQuery, useQueryClient } from '@tanstack/react-query';
import { MessageSquareOff } from 'lucide-react';
import { useCallback, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { SkeletonLines } from '@/components/ui/Skeleton';
import { getConversation, listConversations } from '@/services/conversations';
import { errorMessage, isApiError } from '@/services/http';
import { queryKeys } from '@/services/queryKeys';
import { fromServerMessage } from './chatState';
import { ChatSession } from './ChatSession';

function ConversationLoader({ id, sessionKey }: { id: string; sessionKey: string }) {
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: queryKeys.conversation(id),
    queryFn: ({ signal }) => getConversation(id, signal),
    retry: (count, err) => !(isApiError(err) && err.status === 404) && count < 2,
    // The live session owns its messages after mount, so always start from fresh data.
    refetchOnMount: 'always',
    refetchOnWindowFocus: false,
  });
  const messages = useMemo(() => query.data?.messages.map(fromServerMessage) ?? [], [query.data]);

  if (query.isPending || (query.isFetching && !query.isFetchedAfterMount)) {
    return (
      <div className="mx-auto w-full max-w-3xl space-y-8 px-6 py-10">
        <SkeletonLines lines={2} className="ml-auto w-1/2" />
        <SkeletonLines lines={4} />
      </div>
    );
  }
  if (query.isError) {
    if (isApiError(query.error) && query.error.status === 404) {
      return (
        <EmptyState
          className="h-full"
          icon={<MessageSquareOff className="size-5" aria-hidden />}
          title="Conversation not found"
          description="It may have been deleted."
          action={
            <Button variant="secondary" onClick={() => navigate('/')}>
              Start a new chat
            </Button>
          }
        />
      );
    }
    return (
      <ErrorState
        className="h-full"
        title="Couldn't load this conversation"
        message={errorMessage(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }
  return (
    <ChatSession
      key={sessionKey}
      conversationId={id}
      title={query.data.title}
      initialMessages={messages}
    />
  );
}

interface SessionTrack {
  routeId: string | undefined;
  key: string;
  ownedId: string | null;
  nonce: number;
}

/**
 * Chat route. A brand-new chat keeps its live session (and stream) when the URL
 * switches to /c/:id after the server assigns the conversation id.
 */
export function ChatPage() {
  const { conversationId: routeId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const summaries = useQuery({ queryKey: queryKeys.conversations, queryFn: listConversations });
  const [track, setTrack] = useState<SessionTrack>({
    routeId,
    key: routeId ?? 'new-0',
    ownedId: null,
    nonce: 0,
  });

  if (track.routeId !== routeId) {
    const keep = routeId !== undefined && routeId === track.ownedId;
    const nonce = track.nonce + 1;
    setTrack({
      routeId,
      nonce,
      key: keep ? track.key : (routeId ?? `new-${nonce}`),
      ownedId: keep ? track.ownedId : null,
    });
  }

  const onCreated = useCallback(
    (id: string) => {
      setTrack((t) => ({ ...t, ownedId: id }));
      void queryClient.invalidateQueries({ queryKey: queryKeys.conversations, exact: true });
      navigate(`/c/${id}`, { replace: true });
    },
    [navigate, queryClient],
  );

  if (routeId && routeId !== track.ownedId) {
    return <ConversationLoader key={track.key} id={routeId} sessionKey={track.key} />;
  }

  const title = routeId ? summaries.data?.find((c) => c.id === routeId)?.title : undefined;
  return (
    <ChatSession
      key={track.key}
      conversationId={routeId ?? null}
      title={title}
      initialMessages={[]}
      onConversationCreated={onCreated}
    />
  );
}
