import { ShieldAlert } from 'lucide-react';
import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { EmptyState } from '@/components/ui/EmptyState';
import { useAuth } from './authContext';

export function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <>{children}</>;
}

export function RequireAdmin({ children }: { children: ReactNode }) {
  const { isAdmin } = useAuth();
  if (!isAdmin) {
    return (
      <EmptyState
        icon={<ShieldAlert className="size-5" aria-hidden />}
        title="Admin access required"
        description="This section is only available to administrators."
      />
    );
  }
  return <>{children}</>;
}
