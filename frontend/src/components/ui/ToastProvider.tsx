import { CheckCircle2, Info, X, XCircle } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { cn } from '@/utils/cn';
import { ToastContext, type ToastApi, type ToastInput, type ToastTone } from './toast';

const TOAST_TTL_MS = 4500;
const MAX_TOASTS = 4;

interface ToastItem extends ToastInput {
  id: number;
}

const ICONS: Record<ToastTone, ReactNode> = {
  info: <Info className="size-4 text-accent" aria-hidden />,
  success: <CheckCircle2 className="size-4 text-success" aria-hidden />,
  error: <XCircle className="size-4 text-danger" aria-hidden />,
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, number>());

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((t) => t.id !== id));
    window.clearTimeout(timers.current.get(id));
    timers.current.delete(id);
  }, []);

  const notify = useCallback(
    (toast: ToastInput) => {
      const id = nextId.current++;
      setToasts((current) => [...current.slice(-(MAX_TOASTS - 1)), { ...toast, id }]);
      timers.current.set(
        id,
        window.setTimeout(() => dismiss(id), TOAST_TTL_MS),
      );
    },
    [dismiss],
  );

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((timer) => window.clearTimeout(timer));
  }, []);

  const api = useMemo<ToastApi>(() => ({ notify }), [notify]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        aria-relevant="additions"
        className="pointer-events-none fixed inset-x-0 bottom-4 z-[60] flex flex-col items-center gap-2 px-4 sm:items-end sm:right-4 sm:left-auto"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role={toast.tone === 'error' ? 'alert' : 'status'}
            className={cn(
              'pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-xl border border-line bg-surface px-4 py-3 shadow-pop animate-fade-in',
            )}
          >
            <span className="mt-0.5">{ICONS[toast.tone ?? 'info']}</span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-fg">{toast.title}</p>
              {toast.description && (
                <p className="mt-0.5 text-sm break-words text-fg-muted">{toast.description}</p>
              )}
            </div>
            <button
              type="button"
              aria-label="Dismiss notification"
              onClick={() => dismiss(toast.id)}
              className="rounded p-0.5 text-fg-subtle hover:text-fg"
            >
              <X className="size-4" aria-hidden />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
