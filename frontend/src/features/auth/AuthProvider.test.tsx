import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { SESSION_HINT_KEY, readSession } from '@/services/session';
import { TEST_ADMIN, jsonResponse, renderWithProviders, requestUrl, signIn } from '@/test/utils';
import { useAuth } from './authContext';

function tokenBody(token: string) {
  return { access_token: token, token_type: 'bearer', expires_in: 900, user: TEST_ADMIN };
}

function Probe() {
  const auth = useAuth();
  if (auth.isLoading) return <p>loading</p>;
  return (
    <div>
      <p>{auth.isAuthenticated ? `signed in as ${auth.user?.email}` : 'signed out'}</p>
      <button onClick={() => void auth.logout()}>logout</button>
      <button onClick={() => void auth.logoutAll()}>logout all</button>
      <button
        onClick={() =>
          void auth.changePassword({ current_password: 'old-pass-1', new_password: 'new-pass-2' })
        }
      >
        change password
      </button>
    </div>
  );
}

interface Call {
  url: string;
  init?: RequestInit;
}

function stubApi(handler: (call: Call) => Response) {
  const calls: Call[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const call = { url: requestUrl(input), init };
      calls.push(call);
      return handler(call);
    }),
  );
  return calls;
}

const header = (call: Call | undefined, name: string) => new Headers(call?.init?.headers).get(name);

describe('AuthProvider', () => {
  it('restores the session from the refresh cookie after a reload', async () => {
    window.localStorage.setItem(SESSION_HINT_KEY, '1');
    const calls = stubApi((call) =>
      call.url.endsWith('/auth/refresh')
        ? jsonResponse(tokenBody('restored-token'))
        : jsonResponse(TEST_ADMIN),
    );

    renderWithProviders(<Probe />);

    expect(screen.getByText('loading')).toBeInTheDocument();
    expect(await screen.findByText('signed in as admin@example.com')).toBeInTheDocument();
    expect(calls[0]?.url).toContain('/auth/refresh');
    expect(readSession()?.token).toBe('restored-token');
  });

  it('shows signed out when the refresh cookie is no longer valid', async () => {
    window.localStorage.setItem(SESSION_HINT_KEY, '1');
    stubApi(() => jsonResponse({ error: { code: 'invalid_refresh_token', message: 'x' } }, 401));

    renderWithProviders(<Probe />);

    expect(await screen.findByText('signed out')).toBeInTheDocument();
    expect(window.localStorage.getItem(SESSION_HINT_KEY)).toBeNull();
  });

  it('does not contact the server for a first-time visitor', async () => {
    const calls = stubApi(() => jsonResponse({}, 500));

    renderWithProviders(<Probe />);

    expect(await screen.findByText('signed out')).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it('logout revokes the server session and clears local state', async () => {
    signIn();
    const calls = stubApi((call) =>
      call.url.endsWith('/auth/logout')
        ? new Response(null, { status: 204 })
        : jsonResponse(TEST_ADMIN),
    );
    renderWithProviders(<Probe />);

    await userEvent.click(await screen.findByRole('button', { name: 'logout' }));

    await waitFor(() => expect(screen.getByText('signed out')).toBeInTheDocument());
    const logout = calls.find((c) => c.url.endsWith('/auth/logout'));
    expect(logout?.init?.method).toBe('POST');
    expect(header(logout, 'X-Nexa-CSRF')).toBe('1');
    expect(readSession()).toBeNull();
  });

  it('still signs out locally when the server cannot be reached', async () => {
    signIn();
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        if (requestUrl(input).endsWith('/auth/logout')) throw new TypeError('offline');
        return jsonResponse(TEST_ADMIN);
      }),
    );
    renderWithProviders(<Probe />);

    await userEvent.click(await screen.findByRole('button', { name: 'logout' }));

    await waitFor(() => expect(screen.getByText('signed out')).toBeInTheDocument());
  });

  it('logout everywhere sends the bearer token and clears local state', async () => {
    signIn();
    const calls = stubApi((call) =>
      call.url.endsWith('/auth/logout-all')
        ? new Response(null, { status: 204 })
        : jsonResponse(TEST_ADMIN),
    );
    renderWithProviders(<Probe />);

    await userEvent.click(await screen.findByRole('button', { name: 'logout all' }));

    await waitFor(() => expect(screen.getByText('signed out')).toBeInTheDocument());
    const call = calls.find((c) => c.url.endsWith('/auth/logout-all'));
    expect(header(call, 'Authorization')).toBe('Bearer test-token');
    expect(header(call, 'X-Nexa-CSRF')).toBe('1');
  });

  it('changing the password replaces the access token', async () => {
    signIn();
    const calls = stubApi((call) =>
      call.url.endsWith('/auth/change-password')
        ? jsonResponse(tokenBody('token-after-change'))
        : jsonResponse(TEST_ADMIN),
    );
    renderWithProviders(<Probe />);

    await userEvent.click(await screen.findByRole('button', { name: 'change password' }));

    await waitFor(() => expect(readSession()?.token).toBe('token-after-change'));
    const call = calls.find((c) => c.url.endsWith('/auth/change-password'));
    expect(JSON.parse(String(call?.init?.body))).toEqual({
      current_password: 'old-pass-1',
      new_password: 'new-pass-2',
    });
  });
});
