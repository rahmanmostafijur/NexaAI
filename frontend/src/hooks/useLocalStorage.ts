import { useCallback, useMemo, useSyncExternalStore } from 'react';

const LOCAL_EVENT = 'nexaai:local-storage';

function readRaw(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function subscribe(callback: () => void): () => void {
  window.addEventListener('storage', callback);
  window.addEventListener(LOCAL_EVENT, callback);
  return () => {
    window.removeEventListener('storage', callback);
    window.removeEventListener(LOCAL_EVENT, callback);
  };
}

export function readStoredValue<T>(key: string, fallback: T, isValid: (v: unknown) => v is T): T {
  const raw = readRaw(key);
  if (raw === null) return fallback;
  try {
    const parsed: unknown = JSON.parse(raw);
    return isValid(parsed) ? parsed : fallback;
  } catch {
    return fallback;
  }
}

/**
 * JSON value persisted in localStorage, synchronised across components and tabs.
 * Falls back to `fallback` when storage is unavailable or the stored value is invalid.
 */
export function useLocalStorage<T>(
  key: string,
  fallback: T,
  isValid: (v: unknown) => v is T,
): [T, (value: T) => void] {
  const raw = useSyncExternalStore(
    subscribe,
    () => readRaw(key),
    () => null,
  );

  const value = useMemo<T>(() => {
    if (raw === null) return fallback;
    try {
      const parsed: unknown = JSON.parse(raw);
      return isValid(parsed) ? parsed : fallback;
    } catch {
      return fallback;
    }
  }, [raw, fallback, isValid]);

  const setValue = useCallback(
    (next: T) => {
      try {
        window.localStorage.setItem(key, JSON.stringify(next));
      } catch {
        // Storage may be unavailable (private mode); the change simply won't persist.
      }
      window.dispatchEvent(new Event(LOCAL_EVENT));
    },
    [key],
  );

  return [value, setValue];
}
