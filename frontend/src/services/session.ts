import type { TokenResponse, User } from '@/types/api';

/**
 * The access token lives in memory only, so a script injected into the page cannot read it
 * from storage. The long-lived credential is the httpOnly refresh cookie managed by the
 * server. A non-secret hint in localStorage tells a reloaded tab that a silent refresh is
 * worth attempting, and lets other tabs notice sign-in/sign-out.
 */
export const SESSION_HINT_KEY = 'nexaai.signedIn';
export const LEGACY_STORAGE_KEY = 'nexaai.session';
export const SESSION_CHANGED_EVENT = 'nexaai:session-changed';

export interface Session {
  token: string;
  user: User;
  /** Epoch ms when the access token expires; null disables proactive refresh. */
  expiresAt: number | null;
}

let current: Session | null = null;

function notify(): void {
  window.dispatchEvent(new Event(SESSION_CHANGED_EVENT));
}

function setHint(present: boolean): void {
  try {
    if (present) window.localStorage.setItem(SESSION_HINT_KEY, '1');
    else window.localStorage.removeItem(SESSION_HINT_KEY);
  } catch {
    // Storage can be unavailable (private mode); the in-memory session still works.
  }
}

/** Older versions stored the bearer token in localStorage; never leave one behind. */
export function purgeLegacySession(): void {
  try {
    window.localStorage.removeItem(LEGACY_STORAGE_KEY);
  } catch {
    // ignore
  }
}

purgeLegacySession();

export function sessionFromResponse(response: TokenResponse): Session {
  const expiresAt = response.expires_in > 0 ? Date.now() + response.expires_in * 1000 : null;
  return { token: response.access_token, user: response.user, expiresAt };
}

export function readSession(): Session | null {
  return current;
}

export function writeSession(session: Session): void {
  current = session;
  setHint(true);
  notify();
}

export function clearSession(): void {
  current = null;
  setHint(false);
  notify();
}

export function getToken(): string | null {
  return current?.token ?? null;
}

export function hasSessionHint(): boolean {
  try {
    return window.localStorage.getItem(SESSION_HINT_KEY) !== null;
  } catch {
    return false;
  }
}
