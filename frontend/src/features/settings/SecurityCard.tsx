import { useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { useToast } from '@/components/ui/toast';
import { useAuth } from '@/features/auth/authContext';
import { errorMessage, isApiError } from '@/services/http';

const MIN_PASSWORD = 8;

export function SecurityCard() {
  const { changePassword, logoutAll } = useAuth();
  const { notify } = useToast();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await changePassword({ current_password: current, new_password: next });
      setCurrent('');
      setNext('');
      notify({
        tone: 'success',
        title: 'Password changed',
        description: 'Your other devices have been signed out.',
      });
    } catch (err) {
      setError(
        isApiError(err) && err.status === 401
          ? 'Your current password is incorrect.'
          : errorMessage(err),
      );
    } finally {
      setBusy(false);
    }
  }

  async function onSignOutEverywhere() {
    try {
      await logoutAll();
    } catch (err) {
      notify({
        tone: 'error',
        title: 'Could not sign out everywhere',
        description: errorMessage(err),
      });
    }
  }

  return (
    <Card className="p-5">
      <h2 className="text-sm font-semibold text-fg">Security</h2>
      <p className="mt-0.5 text-sm text-fg-muted">
        Change your password or end every active session.
      </p>
      <form onSubmit={onSubmit} className="mt-4 grid max-w-sm gap-3">
        <label className="grid gap-1.5 text-sm font-medium text-fg">
          Current password
          <input
            type="password"
            required
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            className="h-10 rounded-lg border border-line bg-surface px-3 text-sm font-normal text-fg focus:border-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
          />
        </label>
        <label className="grid gap-1.5 text-sm font-medium text-fg">
          New password
          <input
            type="password"
            required
            minLength={MIN_PASSWORD}
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            className="h-10 rounded-lg border border-line bg-surface px-3 text-sm font-normal text-fg focus:border-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
          />
          <span className="text-xs font-normal text-fg-subtle">
            At least {MIN_PASSWORD} characters, with a letter and a number.
          </span>
        </label>
        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={busy}>
            Change password
          </Button>
          <Button type="button" variant="secondary" onClick={() => void onSignOutEverywhere()}>
            Sign out of all devices
          </Button>
        </div>
      </form>
    </Card>
  );
}
