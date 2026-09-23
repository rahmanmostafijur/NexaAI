import type { Element, ElementContent } from 'hast';
import { memo, useMemo } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkGfm from 'remark-gfm';
import type { Source } from '@/types/api';
import { cn } from '@/utils/cn';
import { CitationBadge } from './CitationBadge';
import { CodeBlock } from './CodeBlock';
import { CITATION_TAG, remarkCitations } from './remarkCitations';

function textOf(node: ElementContent | Element): string {
  if (node.type === 'text') return node.value;
  if (node.type === 'element') return node.children.map(textOf).join('');
  return '';
}

function languageOf(node: Element | undefined): string | null {
  const code = node?.children.find(
    (child): child is Element => child.type === 'element' && child.tagName === 'code',
  );
  const classes = code?.properties.className;
  const list = Array.isArray(classes) ? classes.map(String) : [];
  const lang = list.find((c) => c.startsWith('language-'));
  return lang ? lang.slice('language-'.length) : null;
}

export interface MarkdownContentProps {
  content: string;
  sources?: Source[];
  onCitation?: (sourceId: string) => void;
  className?: string;
}

/**
 * Renders assistant markdown (GFM + syntax highlighting). Raw HTML is never rendered.
 * Citation markers like [S1] / [DB1] become interactive badges.
 */
export const MarkdownContent = memo(function MarkdownContent({
  content,
  sources,
  onCitation,
  className,
}: MarkdownContentProps) {
  const components = useMemo<Components>(() => {
    const byId = new Map((sources ?? []).map((s) => [s.id, s]));
    return {
      [CITATION_TAG]: ({ node }: { node?: Element }) => {
        const id = String(node?.properties.dataSourceId ?? '');
        return <CitationBadge sourceId={id} source={byId.get(id)} onActivate={onCitation} />;
      },
      pre: ({ node, children }) => (
        <CodeBlock code={node ? textOf(node).replace(/\n$/, '') : ''} language={languageOf(node)}>
          {children}
        </CodeBlock>
      ),
      table: ({ children }) => (
        <div className="md-table-wrap">
          <table>{children}</table>
        </div>
      ),
      a: ({ href, children }) => (
        <a href={href} target="_blank" rel="noopener noreferrer">
          {children}
        </a>
      ),
    };
  }, [sources, onCitation]);

  return (
    <div className={cn('md-content', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkCitations]}
        rehypePlugins={[[rehypeHighlight, { detect: false }]]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});
