import type { Source } from '@/types/api';

/** Short human label: "PostgreSQL · orders, customers" or "Return Policy · Page 3". */
export function sourceLabel(source: Source): string {
  if (source.type === 'database') {
    return source.tables.length > 0 ? `PostgreSQL · ${source.tables.join(', ')}` : 'PostgreSQL';
  }
  if (source.page !== null) return `${source.title} · Page ${source.page}`;
  if (source.section) return `${source.title} · ${source.section}`;
  return source.title;
}
