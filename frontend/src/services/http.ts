import { clearSession, getToken } from './session';

export const API_BASE = '/api';

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId: string | null;

  constructor(params: {
    code: string;
    message: string;
    status: number;
    requestId?: string | null;
  }) {
    super(params.message);
    this.name = 'ApiError';
    this.code = params.code;
    this.status = params.status;
    this.requestId = params.requestId ?? null;
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

export function isAbortError(value: unknown): boolean {
  return value instanceof DOMException && value.name === 'AbortError';
}

/** Human-readable message for any thrown value. */
export function errorMessage(value: unknown, fallback = 'Something went wrong.'): string {
  if (value instanceof Error && value.message) return value.message;
  return fallback;
}

type QueryValue = string | number | boolean | null | undefined;

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  json?: unknown;
  formData?: FormData;
  query?: Record<string, QueryValue>;
  signal?: AbortSignal;
  headers?: Record<string, string>;
  /** Skip the global "401 ⇒ sign out" handling (used by login/register). */
  skipAuthRedirect?: boolean;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

const STATUS_CODES: Record<number, string> = {
  401: 'unauthorized',
  403: 'forbidden',
  404: 'not_found',
  413: 'payload_too_large',
  415: 'unsupported_media_type',
  422: 'validation_error',
  429: 'rate_limited',
  503: 'llm_unavailable',
};

export async function parseErrorResponse(response: Response): Promise<ApiError> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  const envelope = isRecord(body) && isRecord(body.error) ? body.error : null;
  const code =
    envelope && typeof envelope.code === 'string'
      ? envelope.code
      : (STATUS_CODES[response.status] ?? 'internal_error');
  const message =
    envelope && typeof envelope.message === 'string'
      ? envelope.message
      : `Request failed with status ${response.status}`;
  const requestId =
    envelope && typeof envelope.request_id === 'string'
      ? envelope.request_id
      : response.headers.get('x-request-id');
  return new ApiError({ code, message, status: response.status, requestId });
}

export function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const params = new URLSearchParams();
  Object.entries(query ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  });
  const qs = params.toString();
  return `${API_BASE}${path}${qs ? `?${qs}` : ''}`;
}

function buildHeaders(options: RequestOptions): Headers {
  const headers = new Headers(options.headers);
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.json !== undefined) headers.set('Content-Type', 'application/json');
  if (!headers.has('Accept')) headers.set('Accept', 'application/json');
  return headers;
}

/** Performs a request and returns the raw Response once it is known to be 2xx. */
export async function apiFetch(path: string, options: RequestOptions = {}): Promise<Response> {
  const hadToken = getToken() !== null;
  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers: buildHeaders(options),
      body:
        options.formData ?? (options.json !== undefined ? JSON.stringify(options.json) : undefined),
      signal: options.signal,
    });
  } catch (err) {
    if (isAbortError(err)) throw err;
    throw new ApiError({
      code: 'network_error',
      message: 'Unable to reach the server. Check your connection and try again.',
      status: 0,
    });
  }

  if (!response.ok) {
    const error = await parseErrorResponse(response);
    if (response.status === 401 && hadToken && !options.skipAuthRedirect) clearSession();
    throw error;
  }
  return response;
}

/** Performs a request and parses the JSON body (undefined for 204). */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await apiFetch(path, options);
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  if (!text) return undefined as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError({
      code: 'invalid_response',
      message: 'The server returned an unexpected response.',
      status: response.status,
    });
  }
}
