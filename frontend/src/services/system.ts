import type { SystemInfo } from '@/types/api';
import { request } from './http';

export function getSystemInfo(): Promise<SystemInfo> {
  return request<SystemInfo>('/system/info');
}
