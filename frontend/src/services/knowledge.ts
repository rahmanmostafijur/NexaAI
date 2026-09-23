import type { SearchResponse } from '@/types/api';
import { request } from './http';

export function searchKnowledge(
  q: string,
  topK = 5,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  return request<SearchResponse>('/knowledge/search', { query: { q, top_k: topK }, signal });
}
