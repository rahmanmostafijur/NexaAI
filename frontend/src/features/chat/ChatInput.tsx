import { ArrowUp, Square } from 'lucide-react';
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { cn } from '@/utils/cn';
import { langFor } from '@/utils/script';

export const MAX_MESSAGE_LENGTH = 4000;
const COUNTER_THRESHOLD = 3200;
const MAX_HEIGHT_PX = 220;

export function ChatInput({
  onSend,
  onStop,
  streaming,
  autoFocus = false,
}: {
  onSend: (text: string) => void;
  onStop: () => void;
  streaming: boolean;
  autoFocus?: boolean;
}) {
  const [value, setValue] = useState('');
  const textarea = useRef<HTMLTextAreaElement>(null);
  const counterId = useId();
  const trimmed = value.trim();
  const canSend = !streaming && trimmed.length > 0 && value.length <= MAX_MESSAGE_LENGTH;

  useEffect(() => {
    const node = textarea.current;
    if (!node) return;
    node.style.height = 'auto';
    node.style.height = `${Math.min(node.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, [value]);

  useEffect(() => {
    if (!streaming && autoFocus) textarea.current?.focus();
  }, [streaming, autoFocus]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!canSend) return;
    onSend(trimmed);
    setValue('');
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto w-full max-w-3xl px-4 pb-4 sm:px-6">
      <div className="relative rounded-2xl border border-line bg-surface shadow-soft transition-colors focus-within:border-accent/60">
        <label htmlFor={`${counterId}-input`} className="sr-only">
          Message
        </label>
        <textarea
          id={`${counterId}-input`}
          ref={textarea}
          rows={1}
          value={value}
          lang={langFor(value)}
          disabled={streaming}
          maxLength={MAX_MESSAGE_LENGTH}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          aria-describedby={counterId}
          placeholder={
            streaming
              ? 'Waiting for the answer...'
              : 'Ask about sales, customers, or policies — in English or বাংলা'
          }
          className="block max-h-[220px] w-full resize-none bg-transparent py-3.5 pr-14 pl-4 text-[15px] leading-relaxed text-fg placeholder:text-fg-subtle focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
        />
        <div className="absolute right-2 bottom-2">
          {streaming ? (
            <button
              type="button"
              onClick={onStop}
              aria-label="Stop generating"
              className="flex size-9 items-center justify-center rounded-xl bg-fg text-canvas hover:opacity-90"
            >
              <Square className="size-3.5 fill-current" aria-hidden />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!canSend}
              aria-label="Send message"
              className="flex size-9 items-center justify-center rounded-xl bg-accent text-accent-fg transition-opacity hover:bg-accent-hover disabled:opacity-35"
            >
              <ArrowUp className="size-4" aria-hidden />
            </button>
          )}
        </div>
      </div>
      <div className="mt-1.5 flex justify-between px-1 text-[11px] text-fg-subtle">
        <span className="hidden sm:inline">Enter to send · Shift+Enter for a new line</span>
        <span
          id={counterId}
          className={cn(
            'ml-auto tabular-nums',
            value.length < COUNTER_THRESHOLD && 'sr-only',
            value.length >= MAX_MESSAGE_LENGTH && 'text-danger',
          )}
        >
          {value.length} / {MAX_MESSAGE_LENGTH}
        </span>
      </div>
    </form>
  );
}
