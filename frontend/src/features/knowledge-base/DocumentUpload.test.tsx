import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TEST_ADMIN, jsonResponse, renderWithProviders, requestUrl, signIn } from '@/test/utils';
import type { KbDocument, SystemInfo } from '@/types/api';
import { DocumentUpload } from './DocumentUpload';
import { validateUpload } from './uploadValidation';

const INFO: SystemInfo = {
  app_name: 'NexaAI Agent',
  version: '1.0.0',
  llm_provider: 'provider',
  llm_model: 'model',
  embedding_provider: 'provider',
  embedding_model: 'embed',
  max_upload_mb: 1,
  allowed_extensions: ['.pdf', '.docx', '.txt', '.md', '.markdown', '.csv'],
};

const CREATED: KbDocument = {
  id: 'd1',
  title: 'policy',
  filename: 'policy.pdf',
  content_type: 'application/pdf',
  source_type: 'pdf',
  size_bytes: 12,
  status: 'pending',
  chunk_count: 0,
  page_count: null,
  error: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  indexed_at: null,
};

function setupFetch() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input);
    if (url.startsWith('/api/system/info')) return jsonResponse(INFO);
    if (url.startsWith('/api/auth/me')) return jsonResponse(TEST_ADMIN);
    if (url.startsWith('/api/documents') && init?.method === 'POST')
      return jsonResponse(CREATED, 201);
    return jsonResponse({ items: [], total: 0 });
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function uploadCalls(fetchMock: ReturnType<typeof setupFetch>) {
  return fetchMock.mock.calls.filter(
    ([input, init]) => requestUrl(input).startsWith('/api/documents') && init?.method === 'POST',
  );
}

async function renderUpload() {
  const fetchMock = setupFetch();
  renderWithProviders(<DocumentUpload />);
  // Wait until the server limit (1 MB) is applied.
  expect(await screen.findByText(/up to 1 MB each/)).toBeInTheDocument();
  return { fetchMock, user: userEvent.setup({ applyAccept: false }) };
}

describe('DocumentUpload', () => {
  beforeEach(() => signIn());

  it('rejects a disallowed extension without calling the API', async () => {
    const { fetchMock, user } = await renderUpload();
    await user.upload(screen.getByLabelText('Upload documents'), new File(['MZ'], 'malware.exe'));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '“malware.exe” is not a supported file type',
    );
    expect(uploadCalls(fetchMock)).toHaveLength(0);
  });

  it('rejects an oversize file without calling the API', async () => {
    const { fetchMock, user } = await renderUpload();
    const big = new File([new Uint8Array(2 * 1024 * 1024)], 'big.pdf', { type: 'application/pdf' });
    await user.upload(screen.getByLabelText('Upload documents'), big);
    expect(await screen.findByRole('alert')).toHaveTextContent('exceeds the 1 MB limit');
    expect(uploadCalls(fetchMock)).toHaveLength(0);
  });

  it('uploads a valid file as multipart FormData', async () => {
    const { fetchMock, user } = await renderUpload();
    const file = new File(['%PDF-1.7 content'], 'policy.pdf', { type: 'application/pdf' });
    await user.upload(screen.getByLabelText('Upload documents'), file);

    await waitFor(() => expect(uploadCalls(fetchMock)).toHaveLength(1));
    const [, init] = uploadCalls(fetchMock)[0] ?? [];
    expect(init?.body).toBeInstanceOf(FormData);
    const sent = (init?.body as FormData).get('file');
    expect(sent).toBeInstanceOf(File);
    expect((sent as File).name).toBe('policy.pdf');
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer test-token');
    expect(await screen.findByText('Upload started')).toBeInTheDocument();
  });
});

describe('validateUpload', () => {
  it('accepts allowed types case-insensitively and falls back to defaults', () => {
    expect(validateUpload(new File(['x'], 'NOTES.MD'), 10)).toBeNull();
    expect(validateUpload(new File(['x'], 'data.csv'))).toBeNull();
    expect(validateUpload(new File([''], 'empty.txt'))).toMatch(/empty/);
    expect(validateUpload(new File(['x'], 'noext'))).toMatch(/not a supported file type/);
  });
});
