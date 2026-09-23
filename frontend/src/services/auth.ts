import type { LoginRequest, RegisterRequest, TokenResponse, User } from '@/types/api';
import { request } from './http';

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
