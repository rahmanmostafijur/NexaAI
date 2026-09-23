import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  TEST_ADMIN,
  controllableStream,
  jsonResponse,
  renderWithProviders,
  requestUrl,
  signIn,
} from '@/test/utils';
import type { Message, SqlResult, Source } from '@/types/api';
import { ChatPage } from './ChatPage';

const SQL: SqlResult = {
  step_id: 's1',
  sql: 'SELECT category, SUM(total) AS revenue FROM orders GROUP BY category',
  columns: ['category', 'revenue'],
  rows: [
    ['Electronics', 125000],
    ['Grocery', 64000],
  ],
  row_count: 2,
  truncated: false,
  attempts: 1,
};

const SOURCES: Source[] = [
  { id: 'DB1', type: 'database', title: 'Sales database', tables: ['orders'] },
  {
    id: 'S1',
    type: 'document',
    title: 'Return Policy',
    document_id: 'd1',
    filename: 'returns.pdf',
    page: 4,
    section: null,
    snippet: 'Electronics may be returned within 7 days.',
    score: 0.91,
  },
];

const FINAL: Message = {
  id: 'm-2',
  conversation_id: 'conv-1',
  role: 'assistant',
  content: 'Electronics led revenue [DB1]. Returns are accepted within 7 days [S1].',
  created_at: '2026-01-01T00:00:00Z',
  details: {
    run_id: 'run-1',
    route: 'HYBRID',
    confidence: 0.87,
    reason: 'Needs sales data and policy text',
    language: 'en',
    plan: [
      {
        id: 's1',
        tool: 'sql',
        description: 'Query revenue',
        status: 'completed',
        duration_ms: 120,
      },
    ],
    sql: [SQL],
    sources: SOURCES,
    timings: { total_ms: 1500, stages: [{ name: 'sql', duration_ms: 120 }] },
    grounded: true,
    warnings: [],
  },
};

type StreamHandle = ReturnType<typeof controllableStream>;

function setupFetch(streams: StreamHandle[]) {
  const chatBodies: unknown[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input);
    if (url.startsWith('/api/chat/stream')) {
      chatBodies.push(JSON.parse(String(init?.body)));
      const next = streams.shift();
      if (!next) throw new Error('No stream prepared');
      return next.response();
    }
    if (url.startsWith('/api/auth/me')) return jsonResponse(TEST_ADMIN);
    if (url.startsWith('/api/conversations')) return jsonResponse([]);
    return jsonResponse({ error: { code: 'not_found', message: 'nope' } }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  return { fetchMock, chatBodies };
}

function renderChat() {
  return renderWithProviders(
    <Routes>
      <Route path="/" element={<ChatPage />} />
      <Route path="/c/:conversationId" element={<ChatPage />} />
    </Routes>,
  );
}

async function ask(text: string) {
  const user = userEvent.setup();
  const input = await screen.findByRole('textbox', { name: 'Message' });
  await user.type(input, `${text}{Enter}`);
  return user;
}

describe('ChatPage streaming', () => {
  beforeEach(() => signIn());

  it('streams agent events and tokens progressively, then renders the final message', async () => {
    const stream = controllableStream();
    const { chatBodies } = setupFetch([stream]);
    renderChat();
    const user = await ask('Which category earned most, and what is the return policy?');

    expect(chatBodies[0]).toEqual({
      message: 'Which category earned most, and what is the return policy?',
    });
    expect(await screen.findByRole('article', { name: 'Your message' })).toHaveTextContent(
      'Which category earned most, and what is the return policy?',
    );
    expect(screen.getByRole('textbox', { name: 'Message' })).toBeDisabled();

    stream.push('meta', { conversation_id: 'conv-1', run_id: 'run-1', user_message_id: 'm-1' });
    stream.push('status', { stage: 'querying_database', label: 'Running database query...' });
    stream.push('analysis', {
      language: { code: 'en', label: 'English' },
      route: 'HYBRID',
      confidence: 0.87,
      reason: 'Needs both',
      requires_database: true,
      requires_documents: true,
      standalone_query: 'q',
    });
    stream.push('plan', {
      steps: [
        { id: 's1', tool: 'sql', description: 'Query revenue by category', status: 'running' },
        { id: 's2', tool: 'rag', description: 'Find return policy', status: 'pending' },
      ],
    });
    stream.push('step', { id: 's1', status: 'completed', duration_ms: 120 });

    const activity = await screen.findByTestId('tool-activity');
    expect(within(activity).getAllByText('Running database query...').length).toBeGreaterThan(0);
    expect(within(activity).getByText('Query revenue by category')).toBeInTheDocument();
    expect(await within(activity).findByText('120 ms')).toBeInTheDocument();

    stream.push('sql', SQL);
    stream.push('sources', { sources: SOURCES });
    stream.push('token', { delta: 'Electronics ' });
    expect(
      await screen.findByText(/^Electronics$/, { selector: '.md-content p' }),
    ).toBeInTheDocument();

    stream.push('token', { delta: 'led revenue' });
    expect(
      await screen.findByText('Electronics led revenue', { selector: '.md-content p' }),
    ).toBeInTheDocument();

    stream.push('done', { message: FINAL });
    stream.close();

    expect(await screen.findByText(/Returns are accepted within 7 days/)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId('tool-activity')).not.toBeInTheDocument());
    expect(screen.getByRole('textbox', { name: 'Message' })).toBeEnabled();

    // Sources render with database and document labels.
    const sources = screen.getByRole('region', { name: 'Sources' });
    expect(within(sources).getByText('PostgreSQL')).toBeInTheDocument();
    expect(within(sources).getByText('Page 4')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Citation S1: Return Policy · Page 4/ }),
    ).toBeInTheDocument();

    // SQL block is collapsed by default and expands on click.
    const toggle = screen.getByRole('button', { name: 'Generated SQL' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByText('Electronics', { selector: 'td span' })).toBeInTheDocument();
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const code = await screen.findByText(
      (_, el) => el?.tagName === 'CODE' && (el.textContent ?? '').includes('GROUP BY category'),
    );
    expect(code).toHaveClass('language-sql');
  });

  it('shows an error bubble with Retry that re-sends the last message', async () => {
    const failing = controllableStream();
    const succeeding = controllableStream();
    const { chatBodies } = setupFetch([failing, succeeding]);
    renderChat();
    const user = await ask('Kon product shobcheye beshi sell hoise?');

    failing.push('meta', { conversation_id: 'conv-1', run_id: 'run-1', user_message_id: 'm-1' });
    failing.push('error', {
      code: 'llm_unavailable',
      message: 'The language model is unavailable.',
      retryable: true,
    });
    failing.close();

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('The language model is unavailable.')).toBeInTheDocument();

    await user.click(within(alert).getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(chatBodies).toHaveLength(2));
    // Retry resends the same text within the conversation created by the first attempt.
    expect(chatBodies[1]).toEqual({
      message: 'Kon product shobcheye beshi sell hoise?',
      conversation_id: 'conv-1',
    });
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(screen.getAllByRole('article', { name: 'Your message' })).toHaveLength(1);

    succeeding.push('done', { message: { ...FINAL, content: 'Laptops sold the most.' } });
    succeeding.close();
    expect(await screen.findByText('Laptops sold the most.')).toBeInTheDocument();
  });

  it('stops streaming when the Stop button is pressed', async () => {
    const stream = controllableStream();
    setupFetch([stream]);
    renderChat();
    const user = await ask('Explain what a database index is.');
    stream.push('token', { delta: 'An index is' });
    expect(await screen.findByText('An index is')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Stop generating' }));
    expect(await screen.findByText('Response stopped')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Message' })).toBeEnabled();
  });
});
