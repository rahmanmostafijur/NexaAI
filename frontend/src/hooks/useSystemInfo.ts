import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/services/queryKeys';
import { getSystemInfo } from '@/services/system';

export function useSystemInfo() {
  return useQuery({
    queryKey: queryKeys.systemInfo,
    queryFn: getSystemInfo,
    staleTime: 10 * 60_000,
  });
}
