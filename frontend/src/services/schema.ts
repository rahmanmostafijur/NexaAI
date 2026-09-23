import type { SchemaResponse } from '@/types/api';
import { request } from './http';

export function getSchema(): Promise<SchemaResponse> {
  return request<SchemaResponse>('/schema');
}
