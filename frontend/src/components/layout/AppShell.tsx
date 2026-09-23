import { Menu } from 'lucide-react';
import { Suspense, useState } from 'react';
import { Link, Outlet } from 'react-router-dom';
import { LARGE_SCREEN_QUERY, useMediaQuery } from '@/hooks/useMediaQuery';
import { IconButton } from '../ui/IconButton';
import { Spinner } from '../ui/Spinner';
import { Drawer } from '../ui/Overlay';
import { Logo } from './Logo';
import { SidebarContent } from './Sidebar';

export function AppShell() {
  const isLarge = useMediaQuery(LARGE_SCREEN_QUERY);
  const [mobileOpen, setMobileOpen] = useState(false);
  const closeMobile = () => setMobileOpen(false);

  return (
    <div className="flex h-dvh min-h-0 bg-canvas">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-surface px-3 py-2 text-sm focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to content
      </a>
      {isLarge ? (
        <aside className="w-72 shrink-0 border-r border-line bg-surface/60">
          <SidebarContent />
        </aside>
      ) : (
        <Drawer open={mobileOpen} onClose={closeMobile} side="left" title="Navigation">
          <div className="-mx-5 -my-4 h-[calc(100dvh-4.5rem)]">
            <SidebarContent onNavigate={closeMobile} />
          </div>
        </Drawer>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        {!isLarge && (
          <div className="flex h-12 shrink-0 items-center gap-2 border-b border-line bg-surface px-2">
            <IconButton
              label="Open navigation"
              icon={<Menu className="size-5" />}
              onClick={() => setMobileOpen(true)}
            />
            <Link to="/" className="rounded-md">
              <Logo />
            </Link>
          </div>
        )}
        <main id="main" className="min-h-0 flex-1 overflow-hidden">
          <Suspense
            fallback={
              <div className="flex h-full items-center justify-center text-fg-subtle">
                <Spinner size="lg" label="Loading page" />
              </div>
            }
          >
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}
