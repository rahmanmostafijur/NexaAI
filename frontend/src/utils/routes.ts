import type { Route } from '@/types/api';

interface RouteMeta {
  label: string;
  description: string;
  /** Tailwind classes for the pill */
  pill: string;
  /** Tailwind class for bars/dots */
  bar: string;
}

export const ROUTE_META: Record<Route, RouteMeta> = {
  SQL: {
    label: 'SQL',
    description: 'Answered from the business database',
    pill: 'bg-sky-500/12 text-sky-700 ring-sky-500/30 dark:text-sky-300',
    bar: 'bg-sky-500',
  },
  RAG: {
    label: 'Knowledge',
    description: 'Answered from the document knowledge base',
    pill: 'bg-emerald-500/12 text-emerald-700 ring-emerald-500/30 dark:text-emerald-300',
    bar: 'bg-emerald-500',
  },
  HYBRID: {
    label: 'Hybrid',
    description: 'Combined database and documents',
    pill: 'bg-violet-500/12 text-violet-700 ring-violet-500/30 dark:text-violet-300',
    bar: 'bg-violet-500',
  },
  GENERAL: {
    label: 'General',
    description: 'General knowledge answer',
    pill: 'bg-slate-500/12 text-slate-700 ring-slate-500/30 dark:text-slate-300',
    bar: 'bg-slate-500',
  },
};

export function isRoute(value: string | null | undefined): value is Route {
  return value === 'SQL' || value === 'RAG' || value === 'HYBRID' || value === 'GENERAL';
}
