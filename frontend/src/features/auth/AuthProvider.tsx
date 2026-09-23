import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import * as authApi from '@/services/auth';
import { queryKeys } from '@/services/queryKeys';
import {
  SESSION_CHANGED_EVENT,
  clearSession,
  readSession,
  writeSession,
  type Session,
} from '@/services/session';
import type { LoginRequest, RegisterRequest, TokenResponse } from '@/types/api';
import { AuthContext, type AuthState } from './authContext';

function toSession(response: TokenResponse): Session {
  const expiresAt = response.expires_in > 0 ? Date.now() + response.expires_in * 1000 : null;
  return { token: response.access_token, user: response.user, expiresAt };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<Session | null>(() => readSession());

  useEffect(() => {
    const sync = () => setSession(readSession());
    window.addEventListener(SESSION_CHANGED_EVENT, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(SESSION_CHANGED_EVENT, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  useEffect(() => {
    if (!session) queryClient.clear();
  }, [session, queryClient]);

  // Refresh the profile (e.g. role changes) whenever a token is present.
  const me = useQuery({
    queryKey: [...queryKeys.me, session?.token],
    queryFn: authApi.fetchMe,
    enabled: session !== null,
    staleTime: 5 * 60_000,
    retry: false,
  });

  const login = useCallback(async (body: LoginRequest) => {
    writeSession(toSession(await authApi.login(body)));
  }, []);

  const register = useCallback(async (body: RegisterRequest) => {
    writeSession(toSession(await authApi.register(body)));
  }, []);

  const logout = useCallback(() => clearSession(), []);

  const value = useMemo<AuthState>(() => {
    const user = session ? (me.data ?? session.user) : null;
    return {
      user,
      isAuthenticated: user !== null,
      isAdmin: user?.role === 'admin',
      login,
      register,
      logout,
    };
  }, [session, me.data, login, register, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
