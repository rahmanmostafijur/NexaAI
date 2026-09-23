import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import type { Source } from '@/types/api';
import { MessageBubble } from './MessageBubble';
import type { ChatMessage } from './types';

const SOURCES: Source[] = [
  {
    id: 'S1',
    type: 'document',
    title: 'Membership Guide',
    document_id: 'd1',
    filename: 'membership.md',
    page: null,
    section: 'Gold tier',
    snippet: 'Gold members get free delivery.',
    score: 0.8,
  },
  { id: 'DB1', type: 'database', title: 'Sales', tables: ['customers', 'orders'] },
];

function assistant(content: string, sources: Source[] = []): ChatMessage {
  return {
    id: 'm1',
    role: 'assistant',
    content,
    createdAt: '2026-01-01T00:00:00Z',
    live: null,
    details: {
      run_id: 'r1',
      route: 'RAG',
      confidence: 0.9,
      reason: 'policy',
      language: 'en',
      plan: [],
      sql: [],
      sources,
      timings: { total_ms: 10, stages: [] },
      grounded: true,
      warnings: [],
    },
  };
}

describe('MessageBubble', () => {
  it('renders a markdown table as an HTML table', () => {
    const md = '| Product | Units |\n|---|---|\n| Laptop | 42 |\n| Phone | 17 |';
    render(<MessageBubble message={assistant(md)} />);
    const table = screen.getByRole('table');
    expect(table).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Product' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'Laptop' })).toBeInTheDocument();
  });

  it('renders citation markers as badges with source tooltips', async () => {
    render(
      <MessageBubble
        message={assistant('Gold members get free delivery [S1] and spend more [DB1].', SOURCES)}
      />,
    );
    const s1 = screen.getByRole('button', { name: 'Citation S1: Membership Guide · Gold tier' });
    expect(s1).toHaveTextContent('S1');
    expect(
      screen.getByRole('button', { name: 'Citation DB1: PostgreSQL · customers, orders' }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/\[S1\]/)).not.toBeInTheDocument();

    await userEvent.setup().click(s1);
    expect(screen.getByTestId('source-S1')).toHaveClass('animate-flash');
  });

  it('does not render raw HTML from content', () => {
    render(<MessageBubble message={assistant('Hello <img src=x onerror="alert(1)"> world')} />);
    expect(document.querySelector('img')).toBeNull();
  });

  it('sets lang="bn" on Bengali content', () => {
    const { container } = render(<MessageBubble message={assistant('গত মাসে বিক্রি বেড়েছে।')} />);
    expect(container.querySelector('[lang="bn"]')).toHaveTextContent('গত মাসে বিক্রি বেড়েছে।');
  });

  it('does not set lang on Latin-script content', () => {
    const { container } = render(<MessageBubble message={assistant('Sales went up.')} />);
    expect(container.querySelector('[lang="bn"]')).toBeNull();
  });

  it('copies content without citation markers', async () => {
    const user = userEvent.setup();
    render(<MessageBubble message={assistant('Free delivery [S1].', SOURCES)} />);
    await user.click(screen.getByRole('button', { name: 'Copy' }));
    expect(await navigator.clipboard.readText()).toBe('Free delivery.');
  });
});
