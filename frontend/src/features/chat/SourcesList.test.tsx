import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { Source } from '@/types/api';
import { sourceLabel } from './sourceLabel';
import { SourcesList } from './SourcesList';

const DB: Source = {
  id: 'DB1',
  type: 'database',
  title: 'Sales DB',
  tables: ['orders', 'products'],
};
const PAGED: Source = {
  id: 'S1',
  type: 'document',
  title: 'Return Policy',
  document_id: 'd1',
  filename: 'returns.pdf',
  page: 3,
  section: 'Electronics',
  snippet: 'Electronics can be returned within 7 days.',
  score: 0.92,
};
const SECTIONED: Source = {
  ...PAGED,
  id: 'S2',
  title: 'FAQ',
  page: null,
  section: 'Shipping',
  snippet: '',
};

describe('SourcesList', () => {
  it('renders database and document sources', () => {
    render(<SourcesList sources={[DB, PAGED, SECTIONED]} messageId="m1" />);
    const region = screen.getByRole('region', { name: 'Sources' });

    const db = within(region).getByTestId('source-DB1');
    expect(db).toHaveTextContent('PostgreSQL');
    expect(db).toHaveTextContent('Tables: orders, products');

    const doc = within(region).getByTestId('source-S1');
    expect(doc).toHaveTextContent('Return Policy');
    expect(doc).toHaveTextContent('Page 3');
    expect(doc).toHaveTextContent('Electronics can be returned within 7 days.');

    expect(within(region).getByTestId('source-S2')).toHaveTextContent('Shipping');
  });

  it('renders nothing when there are no sources', () => {
    const { container } = render(<SourcesList sources={[]} messageId="m1" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('builds human labels', () => {
    expect(sourceLabel(DB)).toBe('PostgreSQL · orders, products');
    expect(sourceLabel(PAGED)).toBe('Return Policy · Page 3');
    expect(sourceLabel(SECTIONED)).toBe('FAQ · Shipping');
  });
});
