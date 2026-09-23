import { BarChart3, Library, LogOut, Plus, Settings } from 'lucide-react';
import { Link, NavLink } from 'react-router-dom';
import { useAuth } from '@/features/auth/authContext';
import { ConversationList } from '@/features/conversations/ConversationList';
import { cn } from '@/utils/cn';
import { Badge } from '../ui/Badge';
import { IconButton } from '../ui/IconButton';
import { Logo } from './Logo';

const NAV = [
  { to: '/knowledge', label: 'Knowledge Base', icon: Library },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/settings', label: 'Settings', icon: Settings },
];

function initials(name: string, email: string): string {
  const source = name.trim() || email;
  const parts = source.split(/[\s@._-]+/).filter(Boolean);
  return (parts[0]?.[0] ?? '?').toUpperCase() + (parts[1]?.[0] ?? '').toUpperCase();
}

function UserMenu() {
  const { user, logout, isAdmin } = useAuth();
  if (!user) return null;
  return (
    <div className="flex items-center gap-2.5 border-t border-line px-3 py-3">
      <span
        aria-hidden
        className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent"
      >
        {initials(user.full_name, user.email)}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-fg">{user.full_name || user.email}</p>
        <div className="flex items-center gap-1.5">
          <p className="truncate text-xs text-fg-subtle">{user.email}</p>
          {isAdmin && <Badge tone="accent">Admin</Badge>}
        </div>
      </div>
      <IconButton
        label="Sign out"
        size="sm"
        icon={<LogOut className="size-4" />}
        onClick={logout}
      />
    </div>
  );
}

export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex h-14 shrink-0 items-center px-4">
        <Link to="/" onClick={onNavigate} aria-label="NexaAI Agent home" className="rounded-md">
          <Logo />
        </Link>
      </div>
      <div className="px-3 pb-3">
        <Link
          to="/"
          onClick={onNavigate}
          className="flex h-9 w-full items-center justify-center gap-2 rounded-lg border border-line bg-surface text-sm font-medium text-fg shadow-sm transition-colors hover:border-line-strong hover:bg-surface-2"
        >
          <Plus className="size-4" aria-hidden /> New chat
        </Link>
      </div>
      <ConversationList onNavigate={onNavigate} />
      <nav aria-label="Main" className="border-t border-line px-2 py-2">
        <ul className="space-y-0.5">
          {NAV.map(({ to, label, icon: Icon }) => (
            <li key={to}>
              <NavLink
                to={to}
                onClick={onNavigate}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors',
                    isActive
                      ? 'bg-surface-3 font-medium text-fg'
                      : 'text-fg-muted hover:bg-surface-2 hover:text-fg',
                  )
                }
              >
                <Icon className="size-4" aria-hidden />
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <UserMenu />
    </div>
  );
}
