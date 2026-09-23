import type { ReactNode } from 'react';

/** Scrollable page wrapper with a consistent header for non-chat pages. */
export function PageContainer({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:py-8">
        <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-fg">{title}</h1>
            {description && <p className="mt-1 text-sm text-fg-muted">{description}</p>}
          </div>
          {actions}
        </header>
        {children}
      </div>
    </div>
  );
}
