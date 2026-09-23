import type { Route } from '@/types/api';
import { cn } from '@/utils/cn';
import { ROUTE_META } from '@/utils/routes';

export function RoutePill({ route, className }: { route: Route; className?: string }) {
  const meta = ROUTE_META[route];
  return (
    <span
      title={meta.description}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] leading-4 font-semibold ring-1 ring-inset',
        meta.pill,
        className,
      )}
    >
      <span className={cn('size-1.5 rounded-full', meta.bar)} aria-hidden />
      {meta.label}
    </span>
  );
}
