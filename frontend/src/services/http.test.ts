import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { TokenResponse, User } from '@/types/api';
import { jsonResponse, requestUrl } from '@/test/utils';
import { apiFetch, request } from './http';
import { clearSession, readSession, writeSession } from './session';

const USER: User = { id: 'u-1', email: 'a@example.com', full_name: 'A', role: 'user' };

function tokenResponse(token: string, expiresIn = 900): TokenResponse {
  return { access_token: token, token_type: 'bearer', expires_in: expiresIn, user: USER };
}

function authHeader(init?: RequestInit): string | null {
  return new Headers(init?.headers).get('Authorization');
}

interface Call {
  url: string;
  init?: RequestInit;
}

function stubFetch(handler: (call: Call) => Response | Promise<Response>) {
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

const isRefresh = (call: Call) => call.url.endsWith('/auth/refresh');

describe('apiFetch session handling', () => {
  beforeEach(() => {
    writeSession({ token: 'old-token', user: USER, expiresAt: Date.now() + 10 * 60_000 });
  });
  afterEach(() => clearSession());

  it('refreshes once on 401 and retries the original request with the new token', async () => {
    const calls = stubFetch((call) => {
      if (isRefresh(call)) return jsonResponse(tokenResponse('new-token'));
      return authHeader(call.init) === 'Bearer new-token'
        ? jsonResponse({ ok: true })
        : jsonResponse({ error: { code: 'unauthorized', message: 'expired' } }, 401);
    });

    await expect(request('/system/info')).resolves.toEqual({ ok: true });

    expect(calls.map((c) => (isRefresh(c) ? 'refresh' : 'api'))).toEqual(['api', 'refresh', 'api']);
    expect(readSession()?.token).toBe('new-token');
  });

  it('sends the CSRF header and cookies with the refresh call', async () => {
    const calls = stubFetch((call) =>
      isRefresh(call) ? jsonResponse(tokenResponse('new-token')) : jsonResponse({}, 401),
    );
    await request('/x').catch(() => undefined);

    const refresh = calls.find(isRefresh);
    expect(refresh?.init?.method).toBe('POST');
    expect(new Headers(refresh?.init?.headers).get('X-Nexa-CSRF')).toBe('1');
    expect(refresh?.init?.credentials).toBe('same-origin');
  });

  it('signs the user out when the refresh is rejected', async () => {
    stubFetch((call) =>
      isRefresh(call)
        ? jsonResponse({ error: { code: 'refresh_reuse_detected', message: 'no' } }, 401)
        : jsonResponse({ error: { code: 'unauthorized', message: 'expired' } }, 401),
    );

    await expect(request('/system/info')).rejects.toMatchObject({ status: 401 });

    expect(readSession()).toBeNull();
  });

  it('does not sign out when the refresh fails because the network is down', async () => {
    stubFetch((call) => {
      if (isRefresh(call)) throw new TypeError('network down');
      return jsonResponse({ error: { code: 'unauthorized', message: 'expired' } }, 401);
    });

    await expect(request('/system/info')).rejects.toMatchObject({ status: 401 });

    expect(readSession()?.token).toBe('old-token');
  });

  it('shares one refresh between concurrent 401s', async () => {
    const calls = stubFetch(async (call) => {
      if (isRefresh(call)) {
        await new Promise((resolve) => setTimeout(resolve, 20));
        return jsonResponse(tokenResponse('new-token'));
      }
      return authHeader(call.init) === 'Bearer new-token'
        ? jsonResponse({ ok: true })
        : jsonResponse({}, 401);
    });

    await Promise.all([request('/a'), request('/b'), request('/c')]);

    expect(calls.filter(isRefresh)).toHaveLength(1);
  });

  it('retries a refresh that lost a race with another tab', async () => {
    let refreshes = 0;
    const calls = stubFetch((call) => {
      if (isRefresh(call)) {
        refreshes += 1;
        return refreshes === 1
          ? jsonResponse({ error: { code: 'refresh_in_progress', message: 'retry' } }, 409)
          : jsonResponse(tokenResponse('new-token'));
      }
      return authHeader(call.init) === 'Bearer new-token'
        ? jsonResponse({ ok: true })
        : jsonResponse({}, 401);
    });

    await expect(request('/a')).resolves.toEqual({ ok: true });
    expect(calls.filter(isRefresh)).toHaveLength(2);
  });

  it('refreshes ahead of time when the access token is about to expire', async () => {
    writeSession({ token: 'old-token', user: USER, expiresAt: Date.now() + 5_000 });
    const calls = stubFetch((call) =>
      isRefresh(call) ? jsonResponse(tokenResponse('new-token')) : jsonResponse({ ok: true }),
    );

    await apiFetch('/system/info');

    expect(calls.map((c) => (isRefresh(c) ? 'refresh' : 'api'))).toEqual(['refresh', 'api']);
    expect(authHeader(calls[1]?.init)).toBe('Bearer new-token');
  });

  it('does not refresh or sign out when the server rejects submitted credentials', async () => {
    const calls = stubFetch(() =>
      jsonResponse({ error: { code: 'invalid_credentials', message: 'wrong password' } }, 401),
    );

    await expect(
      request('/auth/change-password', { method: 'POST', json: {} }),
    ).rejects.toMatchObject({ code: 'invalid_credentials' });

    expect(calls).toHaveLength(1);
    expect(readSession()?.token).toBe('old-token');
  });

  it('never tries to refresh a login failure', async () => {
    clearSession();
    const calls = stubFetch(() => jsonResponse({}, 401));

    await expect(
      request('/auth/login', { method: 'POST', json: {}, skipAuthRedirect: true }),
    ).rejects.toMatchObject({ status: 401 });

    expect(calls).toHaveLength(1);
  });
});
