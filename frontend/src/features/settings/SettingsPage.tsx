import { LogOut, Monitor, Moon, Sun } from 'lucide-react';
import type { ReactNode } from 'react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ErrorState } from '@/components/ui/ErrorState';
import { SkeletonLines } from '@/components/ui/Skeleton';
import { useAuth } from '@/features/auth/authContext';
import { useSystemInfo } from '@/hooks/useSystemInfo';
import { errorMessage } from '@/services/http';
import { cn } from '@/utils/cn';
import { useInspectorDefault, useThemePreference, type ThemePreference } from './preferences';

const THEMES: { id: ThemePreference; label: string; icon: ReactNode }[] = [
  { id: 'system', label: 'System', icon: <Monitor className="size-4" aria-hidden /> },
  { id: 'light', label: 'Light', icon: <Sun className="size-4" aria-hidden /> },
  { id: 'dark', label: 'Dark', icon: <Moon className="size-4" aria-hidden /> },
];

function SettingsCard({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <Card className="p-5">
      <h2 className="text-sm font-semibold text-fg">{title}</h2>
      {description && <p className="mt-0.5 text-sm text-fg-muted">{description}</p>}
      <div className="mt-4">{children}</div>
    </Card>
  );
}

function InfoRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-line py-2 text-sm last:border-b-0">
      <dt className="text-fg-muted">{label}</dt>
      <dd className="min-w-0 truncate text-right font-medium text-fg">{value}</dd>
    </div>
  );
}

function SystemInfoCard() {
  const info = useSystemInfo();
  return (
    <SettingsCard title="System" description="Configuration reported by the server.">
      {info.isPending ? (
        <SkeletonLines lines={5} />
      ) : info.isError ? (
        <ErrorState
          className="py-4"
          message={errorMessage(info.error)}
          onRetry={() => void info.refetch()}
        />
      ) : (
        <dl>
          <InfoRow label="Application" value={`${info.data.app_name} ${info.data.version}`} />
          <InfoRow
            label="Language model"
            value={`${info.data.llm_provider} · ${info.data.llm_model}`}
          />
          <InfoRow
            label="Embeddings"
            value={`${info.data.embedding_provider} · ${info.data.embedding_model}`}
          />
          <InfoRow label="Max upload size" value={`${info.data.max_upload_mb} MB`} />
          <InfoRow label="Allowed file types" value={info.data.allowed_extensions.join(' ')} />
        </dl>
      )}
    </SettingsCard>
  );
}

export function SettingsPage() {
  const [theme, setTheme] = useThemePreference();
  const [showInspector, setShowInspector] = useInspectorDefault();
  const { user, logout } = useAuth();

  return (
    <PageContainer title="Settings" description="Personal preferences are stored in this browser.">
      <div className="grid max-w-3xl gap-4">
        <SettingsCard title="Appearance">
          <div
            role="radiogroup"
            aria-label="Theme"
            className="inline-flex rounded-lg border border-line bg-surface-2 p-1"
          >
            {THEMES.map((t) => (
              <button
                key={t.id}
                type="button"
                role="radio"
                aria-checked={theme === t.id}
                onClick={() => setTheme(t.id)}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors',
                  theme === t.id
                    ? 'bg-surface font-medium text-fg shadow-sm'
                    : 'text-fg-muted hover:text-fg',
                )}
              >
                {t.icon}
                {t.label}
              </button>
            ))}
          </div>
          <label className="mt-5 flex cursor-pointer items-start justify-between gap-4">
            <span>
              <span className="block text-sm font-medium text-fg">Show inspector by default</span>
              <span className="block text-sm text-fg-muted">
                Open the execution inspector next to chats on large screens.
              </span>
            </span>
            <input
              type="checkbox"
              role="switch"
              checked={showInspector}
              onChange={(e) => setShowInspector(e.target.checked)}
              className="mt-1 size-4 accent-[var(--accent)]"
            />
          </label>
        </SettingsCard>

        <SettingsCard title="Account">
          {user && (
            <dl>
              <InfoRow label="Name" value={user.full_name || '—'} />
              <InfoRow label="Email" value={user.email} />
              <InfoRow
                label="Role"
                value={
                  <Badge tone={user.role === 'admin' ? 'accent' : 'neutral'}>{user.role}</Badge>
                }
              />
            </dl>
          )}
          <Button
            variant="secondary"
            className="mt-4"
            onClick={logout}
            icon={<LogOut className="size-4" aria-hidden />}
          >
            Sign out
          </Button>
        </SettingsCard>

        <SystemInfoCard />
      </div>
    </PageContainer>
  );
}
