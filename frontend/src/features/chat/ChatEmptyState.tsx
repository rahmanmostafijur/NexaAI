import { LogoMark } from '@/components/layout/Logo';
import { langFor } from '@/utils/script';

const EXAMPLE_PROMPTS: { tag: string; text: string }[] = [
  { tag: 'বাংলা · Database', text: 'গত ৩ মাসে কোন category সবচেয়ে বেশি revenue generate করেছে?' },
  { tag: 'English · Documents', text: 'What is our return policy for electronics?' },
  { tag: 'Banglish · Database', text: 'Kon product shobcheye beshi sell hoise last month?' },
  {
    tag: 'Hybrid · Data + Documents',
    text: 'Which customer spent the most this year and what membership benefits do they get?',
  },
  { tag: 'General', text: 'Explain what a database index is.' },
];

export function ChatEmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col items-center px-4 pt-10 pb-6 text-center sm:px-6 sm:pt-16">
      <LogoMark className="size-11" />
      <h1 className="mt-4 text-2xl font-semibold tracking-tight text-fg">How can I help today?</h1>
      <p className="mt-2 max-w-md text-sm text-fg-muted">
        Ask about your sales data, customers, or company documents. Write in English, বাংলা,
        Banglish, or a mix.
      </p>
      <ul className="mt-8 grid w-full gap-2.5 text-left sm:grid-cols-2">
        {EXAMPLE_PROMPTS.map((prompt) => (
          <li key={prompt.text}>
            <button
              type="button"
              onClick={() => onPick(prompt.text)}
              className="group h-full w-full rounded-xl border border-line bg-surface px-4 py-3 text-left transition-colors hover:border-accent/50 hover:bg-accent-soft/40"
            >
              <span className="block text-[11px] font-medium text-fg-subtle">{prompt.tag}</span>
              <span lang={langFor(prompt.text)} className="mt-1 block text-sm text-fg">
                {prompt.text}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
