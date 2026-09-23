import { X } from 'lucide-react';
import { useEffect, useId, useRef, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '@/utils/cn';
import { IconButton } from './IconButton';

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function useDialogBehaviour(
  open: boolean,
  onClose: () => void,
  panel: RefObject<HTMLElement | null>,
) {
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return undefined;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const node = panel.current;
    const first = node?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? node)?.focus();
    const { overflow } = document.body.style;
    document.body.style.overflow = 'hidden';

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab' || !node) return;
      const items = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (items.length === 0) return;
      const firstItem = items[0];
      const lastItem = items[items.length - 1];
      if (event.shiftKey && document.activeElement === firstItem) {
        event.preventDefault();
        lastItem?.focus();
      } else if (!event.shiftKey && document.activeElement === lastItem) {
        event.preventDefault();
        firstItem?.focus();
      }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = overflow;
      previouslyFocused?.focus?.();
    };
  }, [open, panel]);
}

interface OverlayProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}

interface InternalProps extends OverlayProps {
  variant: 'modal' | 'drawer-right' | 'drawer-left';
  role?: 'dialog' | 'alertdialog';
}

function OverlayBase({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  className,
  variant,
  role = 'dialog',
}: InternalProps) {
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descId = useId();
  useDialogBehaviour(open, onClose, panel);
  if (!open) return null;

  const panelClass = {
    modal:
      'relative m-auto w-[calc(100%-2rem)] max-w-lg max-h-[calc(100dvh-2rem)] rounded-2xl animate-fade-in',
    'drawer-right': 'ml-auto h-full w-full max-w-xl animate-slide-in-right',
    'drawer-left': 'mr-auto h-full w-[85%] max-w-xs animate-slide-in-left',
  }[variant];

  return createPortal(
    <div className="fixed inset-0 z-50 flex">
      <div
        className="absolute inset-0 bg-slate-950/40 backdrop-blur-[2px] animate-fade-in"
        aria-hidden
        onClick={onClose}
      />
      <div
        ref={panel}
        role={role}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        tabIndex={-1}
        className={cn(
          'relative flex flex-col border border-line bg-surface shadow-pop outline-none',
          panelClass,
          className,
        )}
      >
        <div className="flex items-start gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="truncate text-base font-semibold text-fg">
              {title}
            </h2>
            {description && (
              <p id={descId} className="mt-0.5 text-sm text-fg-muted">
                {description}
              </p>
            )}
          </div>
          <IconButton label="Close" size="sm" icon={<X className="size-4" />} onClick={onClose} />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>
        )}
      </div>
    </div>,
    document.body,
  );
}

export function Modal(props: OverlayProps & { role?: 'dialog' | 'alertdialog' }) {
  return <OverlayBase {...props} variant="modal" />;
}

export function Drawer({ side = 'right', ...props }: OverlayProps & { side?: 'left' | 'right' }) {
  return <OverlayBase {...props} variant={side === 'right' ? 'drawer-right' : 'drawer-left'} />;
}
