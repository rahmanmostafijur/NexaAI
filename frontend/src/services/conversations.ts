import type { ConversationDetail, ConversationSummary } from '@/types/api';
import { request } from './http';

export function listConversations(): Promise<ConversationSummary[]> {
  return request<ConversationSummary[]>('/conversations');
}

export function getConversation(id: string, signal?: AbortSignal): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/conversations/${encodeURIComponent(id)}`, { signal });
}

export function renameConversation(id: string, title: string): Promise<ConversationSummary> {
  return request<ConversationSummary>(`/conversations/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    json: { title },
  });
}

export function deleteConversation(id: string): Promise<void> {
  return request<void>(`/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' });
}
