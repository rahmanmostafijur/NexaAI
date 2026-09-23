import { Database, FileText, Languages } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Logo } from '@/components/layout/Logo';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { errorMessage, isApiError } from '@/services/http';
import { langFor } from '@/utils/script';
import { useAuth } from './authContext';

type Mode = 'login' | 'register';
const MIN_PASSWORD = 8;

function redirectTarget(state: unknown): string {
  if (typeof state === 'object' && state !== null && 'from' in state) {
    const from = (state as { from: unknown }).from;
    if (typeof from === 'string' && from.startsWith('/') && !from.startsWith('/login')) return from;
  }
  return '/';
}

const FEATURES = [
  { icon: Database, text: 'Ask questions of your business database in plain language' },
  { icon: FileText, text: 'Grounded answers from policies and documents, with citations' },
  { icon: Languages, text: 'English, বাংলা, Banglish, or a mix — all understood' },
];

function Field(props: {
  id: string;
  label: string;
  type: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: string;
  minLength?: number;
}) {
  return (
    <div>
      <label htmlFor={props.id} className="mb-1.5 block text-sm font-medium text-fg">
        {props.label}
      </label>
      <input
        id={props.id}
        type={props.type}
        required
        minLength={props.minLength}
        value={props.value}
        autoComplete={props.autoComplete}
        onChange={(e) => props.onChange(e.target.value)}
        className="h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm text-fg placeholder:text-fg-subtle focus:border-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
      />
    </div>
  );
}

export function LoginPage() {
  const { login, register, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mode, setMode] = useState<Mode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (isAuthenticated) return <Navigate to={redirectTarget(location.state)} replace />;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === 'login') await login({ email: email.trim(), password });
      else await register({ email: email.trim(), password, full_name: fullName.trim() });
      navigate(redirectTarget(location.state), { replace: true });
    } catch (err) {
      if (isApiError(err) && err.status === 401) setError('Incorrect email or password.');
      else if (isApiError(err) && err.status === 403 && mode === 'register')
        setError('Registration is currently disabled. Ask an administrator for an account.');
      else setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  function switchMode() {
    setMode((m) => (m === 'login' ? 'register' : 'login'));
    setError(null);
  }

  return (
    <div className="grid min-h-full lg:grid-cols-2">
      <aside className="relative hidden overflow-hidden bg-gradient-to-br from-indigo-950 via-slate-950 to-teal-950 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <Logo className="[&_span]:text-white" />
        <div>
          <h1 className="max-w-md text-3xl leading-tight font-semibold tracking-tight">
            One assistant for your data and your documents.
          </h1>
          <ul className="mt-8 space-y-4">
            {FEATURES.map(({ icon: Icon, text }) => (
              <li
                key={text}
                className="flex items-start gap-3 text-sm text-slate-300"
                lang={langFor(text)}
              >
                <span className="mt-0.5 flex size-7 items-center justify-center rounded-lg bg-white/10">
                  <Icon className="size-4" aria-hidden />
                </span>
                {text}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-slate-400">Routes every question to SQL, documents, or both.</p>
      </aside>

      <main className="flex items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-sm">
          <Logo className="mb-8 lg:hidden" />
          <h2 className="text-xl font-semibold tracking-tight text-fg">
            {mode === 'login' ? 'Sign in' : 'Create your account'}
          </h2>
          <p className="mt-1 text-sm text-fg-muted">
            {mode === 'login'
              ? 'Welcome back. Enter your credentials to continue.'
              : 'Get started with a new workspace account.'}
          </p>
          <Card className="mt-6 p-5">
            <form onSubmit={onSubmit} className="space-y-4">
              {mode === 'register' && (
                <Field
                  id="full_name"
                  label="Full name"
                  type="text"
                  value={fullName}
                  onChange={setFullName}
                  autoComplete="name"
                />
              )}
              <Field
                id="email"
                label="Email"
                type="email"
                value={email}
                onChange={setEmail}
                autoComplete="email"
              />
              <Field
                id="password"
                label="Password"
                type="password"
                value={password}
                onChange={setPassword}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                minLength={mode === 'register' ? MIN_PASSWORD : undefined}
              />
              {error && (
                <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">
                  {error}
                </p>
              )}
              <Button type="submit" className="w-full" loading={submitting}>
                {mode === 'login' ? 'Sign in' : 'Create account'}
              </Button>
            </form>
          </Card>
          <p className="mt-5 text-center text-sm text-fg-muted">
            {mode === 'login' ? "Don't have an account?" : 'Already have an account?'}{' '}
            <button
              type="button"
              onClick={switchMode}
              className="font-medium text-accent hover:underline"
            >
              {mode === 'login' ? 'Create one' : 'Sign in'}
            </button>
          </p>
        </div>
      </main>
    </div>
  );
}
