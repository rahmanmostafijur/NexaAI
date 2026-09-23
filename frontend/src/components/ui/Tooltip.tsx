import { useId, type ReactElement, type ReactNode } from 'react';
import { cn } from '@/utils/cn';

/**
 * Lightweight CSS tooltip, visible on hover and on keyboard focus within the trigger.
 * The render prop receives the tooltip id to wire up `aria-describedby`.
 */
export function Tooltip({
  content,
  children,
  side = 'top',
  className,
}: {
  content: ReactNode;
  children: (describedBy: string) => ReactElement;
  side?: 'top' | 'bottom';
  className?: string;
}) {
  const id = useId();
  return (
    <span className={cn('group/tip relative inline-flex', className)}>
      {children(id)}
      <span
        id={id}
        role="tooltip"
        className={cn(
          'pointer-events-none absolute left-1/2 z-50 w-max max-w-64 -translate-x-1/2 rounded-md bg-fg px-2 py-1 text-xs leading-snug font-normal whitespace-normal text-canvas opacity-0 shadow-pop transition-opacity',
          'group-focus-within/tip:opacity-100 group-hover/tip:opacity-100',
          side === 'top' ? 'bottom-full mb-1.5' : 'top-full mt-1.5',
        )}
      >
        {content}
      </span>
    </span>
  );
}
