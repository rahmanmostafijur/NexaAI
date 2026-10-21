import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import * as authApi from '@/services/auth';
import { queryKeys } from '@/services/queryKeys';
import {
  SESSION_CHANGED_EVENT,
  SESSION_HINT_KEY,
  clearSession,
  hasSessionHint,
  readSession,
  sessionFromResponse,
  writeSession,
  type Session,
} from '@/services/session';
import { refreshSession } from '@/services/sessionRefresh';
import type { ChangePasswordRequest, LoginRequest, RegisterRequest } from '@/types/api';
import { AuthContext, type AuthState } from './authContext';

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<Session | null>(() => readSession());
  // A reloaded tab has no in-memory token yet; it tries a silent refresh before deciding.
  const [isLoading, setIsLoading] = useState(() => readSession() === null && hasSessionHint());

  useEffect(() => {
    if (!isLoading) return;
    let active = true;
    void refreshSession().finally(() => {
      if (!active) return;
      setSession(readSession());
      setIsLoading(false);
    });
    return () => {
      active = false;
    };
  }, [isLoading]);

  useEffect(() => {
    const sync = () => setSession(readSession());
    // Another tab signed out or in: the hint key is the cross-tab signal.
    const onStorage = (event: StorageEvent) => {
      if (event.key !== SESSION_HINT_KEY && event.key !== null) return;
      if (!hasSessionHint()) clearSession();
      else if (readSession() === null) setIsLoading(true);
    };
    window.addEventListener(SESSION_CHANGED_EVENT, sync);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener(SESSION_CHANGED_EVENT, sync);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  useEffect(() => {
    if (!session && !isLoading) queryClient.clear();
  }, [session, isLoading, queryClient]);

  // Refresh the profile (e.g. role changes) whenever a token is present.
  const me = useQuery({
    queryKey: [...queryKeys.me, session?.user.id],
    queryFn: authApi.fetchMe,
    enabled: session !== null,
    staleTime: 5 * 60_000,
    retry: false,
  });

  const login = useCallback(async (body: LoginRequest) => {
    writeSession(sessionFromResponse(await authApi.login(body)));
  }, []);

  const register = useCallback(async (body: RegisterRequest) => {
    writeSession(sessionFromResponse(await authApi.register(body)));
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout();
    clearSession();
  }, []);

  const logoutAll = useCallback(async () => {
    await authApi.logoutAll();
    clearSession();
  }, []);

  const changePassword = useCallback(async (body: ChangePasswordRequest) => {
    writeSession(sessionFromResponse(await authApi.changePassword(body)));
  }, []);

  const value = useMemo<AuthState>(() => {
    const user = session ? (me.data ?? session.user) : null;
    return {
      user,
      isAuthenticated: user !== null,
      isAdmin: user?.role === 'admin',
      isLoading,
      login,
      register,
      logout,
      logoutAll,
      changePassword,
    };
  }, [session, me.data, isLoading, login, register, logout, logoutAll, changePassword]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
