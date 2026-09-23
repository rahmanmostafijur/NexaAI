import { Check, Copy } from 'lucide-react';
import type { ReactNode } from 'react';
import { useCopyToClipboard } from '@/hooks/useCopyToClipboard';

/** A fenced code block with a language label and a copy button. */
export function CodeBlock({
  code,
  language,
  children,
}: {
  code: string;
  language: string | null;
  children: ReactNode;
}) {
  const { copied, copy } = useCopyToClipboard();
  return (
    <div className="group/code relative my-3 overflow-hidden rounded-lg border border-slate-800 bg-[#0d1117] text-slate-100">
      <div className="flex items-center justify-between border-b border-white/10 px-3 py-1.5 text-[11px] text-slate-400">
        <span className="font-mono uppercase tracking-wide">{language ?? 'code'}</span>
        <button
          type="button"
          onClick={() => void copy(code)}
          aria-label={copied ? 'Copied' : 'Copy code'}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-white/10 hover:text-slate-100"
        >
          {copied ? (
            <Check className="size-3.5" aria-hidden />
          ) : (
            <Copy className="size-3.5" aria-hidden />
          )}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="overflow-x-auto p-3 font-mono text-[13px] leading-relaxed">{children}</pre>
    </div>
  );
}
