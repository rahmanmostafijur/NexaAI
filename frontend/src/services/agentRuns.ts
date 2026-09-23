import type { RunDetail, RunSummary, Stats } from '@/types/api';
import { request } from './http';

export function listRuns(limit = 50): Promise<RunSummary[]> {
  return request<RunSummary[]>('/agent/runs', { query: { limit } });
}

export function getRun(id: string): Promise<RunDetail> {
  return request<RunDetail>(`/agent/runs/${encodeURIComponent(id)}`);
}

export function getStats(): Promise<Stats> {
  return request<Stats>('/agent/stats');
}
