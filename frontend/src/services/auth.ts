import type {
  ChangePasswordRequest,
  LoginRequest,
  RegisterRequest,
  TokenResponse,
  User,
} from '@/types/api';
import { request } from './http';
import { CSRF_HEADER } from './sessionRefresh';

export function login(body: LoginRequest): Promise<TokenResponse> {
  return request<TokenResponse>('/auth/login', {
    method: 'POST',
    json: body,
    skipAuthRedirect: true,
  });
}

export function register(body: RegisterRequest): Promise<TokenResponse> {
  return request<TokenResponse>('/auth/register', {
    method: 'POST',
    json: body,
    skipAuthRedirect: true,
  });
}

export function fetchMe(): Promise<User> {
  return request<User>('/auth/me');
}

/** Ends this browser's server session. Best effort: local sign-out must not depend on it. */
export async function logout(): Promise<void> {
  try {
    await request<void>('/auth/logout', {
      method: 'POST',
      headers: { [CSRF_HEADER]: '1' },
      skipAuthRedirect: true,
    });
  } catch {
    // The refresh cookie expires on its own; the caller clears local state regardless.
  }
}

export function logoutAll(): Promise<void> {
  return request<void>('/auth/logout-all', { method: 'POST', headers: { [CSRF_HEADER]: '1' } });
}

export function changePassword(body: ChangePasswordRequest): Promise<TokenResponse> {
  return request<TokenResponse>('/auth/change-password', { method: 'POST', json: body });
}
