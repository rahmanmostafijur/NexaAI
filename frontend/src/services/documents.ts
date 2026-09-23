import type { Chunk, KbDocument, Paginated } from '@/types/api';
import { request } from './http';

export function listDocuments(): Promise<Paginated<KbDocument>> {
  return request<Paginated<KbDocument>>('/documents');
}

export function uploadDocument(file: File, title?: string): Promise<KbDocument> {
  const form = new FormData();
  form.append('file', file);
  if (title) form.append('title', title);
  return request<KbDocument>('/documents', { method: 'POST', formData: form });
}

export function deleteDocument(id: string): Promise<void> {
  return request<void>(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export function reindexDocument(id: string): Promise<KbDocument> {
  return request<KbDocument>(`/documents/${encodeURIComponent(id)}/reindex`, { method: 'POST' });
}

export function listChunks(id: string, limit: number, offset: number): Promise<Paginated<Chunk>> {
  return request<Paginated<Chunk>>(`/documents/${encodeURIComponent(id)}/chunks`, {
    query: { limit, offset },
  });
}
