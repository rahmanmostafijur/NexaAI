import { describe, expect, it } from 'vitest';
import type { User } from '@/types/api';
import {
  LEGACY_STORAGE_KEY,
  clearSession,
  hasSessionHint,
  purgeLegacySession,
  readSession,
  writeSession,
} from './session';

const USER: User = { id: 'u-1', email: 'a@example.com', full_name: 'A', role: 'user' };

describe('session store', () => {
  it('keeps the access token in memory only', () => {
    writeSession({ token: 'secret-access-token', user: USER, expiresAt: null });

    expect(readSession()?.token).toBe('secret-access-token');
    const stored = JSON.stringify({ ...window.localStorage });
    expect(stored).not.toContain('secret-access-token');
  });

  it('leaves a non-secret hint so a reload knows to try a silent refresh', () => {
    expect(hasSessionHint()).toBe(false);
    writeSession({ token: 't', user: USER, expiresAt: null });
    expect(hasSessionHint()).toBe(true);
    clearSession();
    expect(hasSessionHint()).toBe(false);
    expect(readSession()).toBeNull();
  });

  it('removes a token left in localStorage by an older version', () => {
    window.localStorage.setItem(LEGACY_STORAGE_KEY, JSON.stringify({ token: 'old' }));

    purgeLegacySession();

    expect(window.localStorage.getItem(LEGACY_STORAGE_KEY)).toBeNull();
  });
});
