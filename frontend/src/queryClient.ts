import { QueryClient } from '@tanstack/react-query';
import { isApiError } from '@/services/http';

const MAX_RETRIES = 2;

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        refetchOnWindowFocus: false,
        retry: (count, error) =>
          count < MAX_RETRIES && !(isApiError(error) && error.status >= 400 && error.status < 500),
      },
    },
  });
}
