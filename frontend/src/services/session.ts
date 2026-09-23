import type { User } from '@/types/api';

const STORAGE_KEY = 'nexaai.session';
export const SESSION_CHANGED_EVENT = 'nexaai:session-changed';

export interface Session {
  token: string;
  user: User;
  expiresAt: number | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function isUser(value: unknown): value is User {
  return (
    isRecord(value) &&
    typeof value.id === 'string' &&
    typeof value.email === 'string' &&
    typeof value.full_name === 'string' &&
    (value.role === 'admin' || value.role === 'user')
  );
}

function parseSession(raw: string | null): Session | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed) || typeof parsed.token !== 'string' || !isUser(parsed.user)) {
      return null;
    }
    const expiresAt = typeof parsed.expiresAt === 'number' ? parsed.expiresAt : null;
    if (expiresAt !== null && expiresAt <= Date.now()) return null;
    return { token: parsed.token, user: parsed.user, expiresAt };
  } catch {
    return null;
  }
}

function notify(): void {
  window.dispatchEvent(new Event(SESSION_CHANGED_EVENT));
}

export function readSession(): Session | null {
  try {
    return parseSession(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    return null;
  }
}

export function writeSession(session: Session): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } finally {
    notify();
  }
}

export function clearSession(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } finally {
    notify();
  }
}

export function getToken(): string | null {
  return readSession()?.token ?? null;
}
