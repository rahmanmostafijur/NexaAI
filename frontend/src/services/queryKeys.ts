export const queryKeys = {
  me: ['auth', 'me'] as const,
  conversations: ['conversations'] as const,
  conversation: (id: string) => ['conversations', id] as const,
  documents: ['documents'] as const,
  chunks: (id: string, offset: number) => ['documents', id, 'chunks', offset] as const,
  search: (q: string) => ['knowledge', 'search', q] as const,
  schema: ['schema'] as const,
  runs: ['agent', 'runs'] as const,
  run: (id: string) => ['agent', 'runs', id] as const,
  stats: ['agent', 'stats'] as const,
  systemInfo: ['system', 'info'] as const,
};
