import type { TokenResponse } from '@/types/api';
import { clearSession, sessionFromResponse, writeSession } from './session';

export const CSRF_HEADER = 'X-Nexa-CSRF';
const REFRESH_URL = '/api/auth/refresh';
const LOCK_NAME = 'nexaai-session-refresh';
const MAX_RACE_RETRIES = 3;
const RACE_RETRY_DELAY_MS = 150;

export type RefreshOutcome = 'refreshed' | 'rejected' | 'unreachable';

function isTokenResponse(value: unknown): value is TokenResponse {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as { access_token?: unknown }).access_token === 'string'
  );
}

async function readErrorCode(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json();
    const error = (body as { error?: { code?: unknown } } | null)?.error;
    return typeof error?.code === 'string' ? error.code : null;
  } catch {
    return null;
  }
}

async function attemptRefresh(): Promise<RefreshOutcome> {
  for (let attempt = 0; attempt <= MAX_RACE_RETRIES; attempt += 1) {
    let response: Response;
    try {
      response = await fetch(REFRESH_URL, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { [CSRF_HEADER]: '1', Accept: 'application/json' },
      });
    } catch {
      return 'unreachable';
    }
    if (response.ok) {
      const body: unknown = await response.json().catch(() => null);
      if (!isTokenResponse(body)) return 'unreachable';
      writeSession(sessionFromResponse(body));
      return 'refreshed';
    }
    // Another tab rotated the cookie a moment ago; the browser now holds the new one.
    const raced =
      response.status === 409 && (await readErrorCode(response)) === 'refresh_in_progress';
    if (!raced) {
      if (response.status === 401 || response.status === 403) return 'rejected';
      return 'unreachable';
    }
    await new Promise((resolve) => setTimeout(resolve, RACE_RETRY_DELAY_MS));
  }
  return 'unreachable';
}

/** Serialises refreshes across tabs when the browser supports Web Locks. */
function withCrossTabLock(task: () => Promise<RefreshOutcome>): Promise<RefreshOutcome> {
  if (typeof navigator !== 'undefined' && navigator.locks) {
    return navigator.locks.request(LOCK_NAME, task);
  }
  return task();
}

let inFlight: Promise<RefreshOutcome> | null = null;

/**
 * Exchanges the refresh cookie for a new access token. Concurrent callers in this tab share
 * one request. A rejected refresh ends the local session; an unreachable server does not.
 */
export function refreshSession(): Promise<RefreshOutcome> {
  inFlight ??= withCrossTabLock(attemptRefresh)
    .then((outcome) => {
      if (outcome === 'rejected') clearSession();
      return outcome;
    })
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}
