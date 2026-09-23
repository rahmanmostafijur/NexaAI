import { useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { useState, type FormEvent, type ReactNode } from 'react';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { SkeletonLines } from '@/components/ui/Skeleton';
import { errorMessage } from '@/services/http';
import { searchKnowledge } from '@/services/knowledge';
import { queryKeys } from '@/services/queryKeys';
import { langFor } from '@/utils/script';

const TOP_K = 5;
const SNIPPET_CHARS = 420;

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Wraps query terms found in `text` with <mark>, without using raw HTML. */
function highlightTerms(text: string, query: string): ReactNode[] {
  const terms = query
    .split(/\s+/)
    .map((t) => t.trim())
    .filter((t) => t.length > 1)
    .map(escapeRegExp);
  if (terms.length === 0) return [text];
  const re = new RegExp(`(${terms.join('|')})`, 'giu');
  return text.split(re).map((part, i) =>
    i % 2 === 1 ? (
      <mark key={i} className="rounded bg-warning-soft px-0.5 text-fg">
        {part}
      </mark>
    ) : (
      part
    ),
  );
}

function snippet(content: string): string {
  return content.length > SNIPPET_CHARS ? `${content.slice(0, SNIPPET_CHARS).trimEnd()}…` : content;
}

export function SearchTab() {
  const [draft, setDraft] = useState('');
  const [submitted, setSubmitted] = useState('');
  const query = useQuery({
    queryKey: queryKeys.search(submitted),
    queryFn: ({ signal }) => searchKnowledge(submitted, TOP_K, signal),
    enabled: submitted.length > 0,
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitted(draft.trim());
  }

  let results: ReactNode;
  if (!submitted) {
    results = (
      <EmptyState
        icon={<Search className="size-5" aria-hidden />}
        title="Search the knowledge base"
        description="Test what the agent retrieves for a question, with relevance scores."
      />
    );
  } else if (query.isPending) {
    results = <SkeletonLines lines={6} />;
  } else if (query.isError) {
    results = (
      <ErrorState
        title="Search failed"
        message={errorMessage(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  } else if (query.data.results.length === 0) {
    results = (
      <EmptyState
        title="No matches"
        description="Try different wording or upload more documents."
      />
    );
  } else {
    results = (
      <ol className="space-y-3" aria-label="Search results">
        {query.data.results.map((r) => (
          <li key={r.chunk_id} className="rounded-xl border border-line bg-surface p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="font-medium text-fg" lang={langFor(r.title)}>
                {r.title}
                <span className="ml-2 text-xs font-normal text-fg-subtle">
                  {[r.page !== null ? `Page ${r.page}` : null, r.section]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </p>
              <span className="text-xs text-fg-muted tabular-nums">
                score {r.score.toFixed(3)}
                {r.vector_score !== null && ` · vector ${r.vector_score.toFixed(3)}`}
                {r.keyword_score !== null && ` · keyword ${r.keyword_score.toFixed(3)}`}
              </span>
            </div>
            <p
              className="mt-2 text-sm leading-relaxed whitespace-pre-wrap text-fg-muted"
              lang={langFor(r.content)}
            >
              {highlightTerms(snippet(r.content), submitted)}
            </p>
          </li>
        ))}
      </ol>
    );
  }

  return (
    <div className="space-y-5">
      <form onSubmit={onSubmit} role="search" className="flex gap-2">
        <label htmlFor="kb-search" className="sr-only">
          Search query
        </label>
        <input
          id="kb-search"
          type="search"
          value={draft}
          lang={langFor(draft)}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="e.g. warranty period for laptops"
          className="h-10 min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 text-sm text-fg placeholder:text-fg-subtle focus:border-accent focus:outline-none"
        />
        <Button
          type="submit"
          disabled={!draft.trim()}
          icon={<Search className="size-4" aria-hidden />}
        >
          Search
        </Button>
      </form>
      {results}
    </div>
  );
}
