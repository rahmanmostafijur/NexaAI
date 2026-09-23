import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, type RenderResult } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '@/components/ui/ToastProvider';
import { AuthProvider } from '@/features/auth/AuthProvider';
import { writeSession } from '@/services/session';
import type { User } from '@/types/api';

export const TEST_ADMIN: User = {
  id: 'u-1',
  email: 'admin@example.com',
  full_name: 'Test Admin',
  role: 'admin',
};

export function signIn(user: User = TEST_ADMIN): void {
  writeSession({ token: 'test-token', user, expiresAt: null });
}

export function renderWithProviders(
  ui: ReactElement,
  { route = '/' }: { route?: string } = {},
): RenderResult & { queryClient: QueryClient } {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const result = render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={[route]}>
          <AuthProvider>{ui}</AuthProvider>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { ...result, queryClient };
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

export function sseFrame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** A text/event-stream body whose chunks are pushed manually by the test. */
export function controllableStream() {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const stream = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  return {
    response: () =>
      new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
    push: (event: string, data: unknown) =>
      controller.enqueue(encoder.encode(sseFrame(event, data))),
    close: () => controller.close(),
  };
}

export function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}
