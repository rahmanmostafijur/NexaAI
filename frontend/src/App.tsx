import { QueryClientProvider } from '@tanstack/react-query';
import { lazy, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from '@/components/layout/AppShell';
import { ToastProvider } from '@/components/ui/ToastProvider';
import { AuthProvider } from '@/features/auth/AuthProvider';
import { LoginPage } from '@/features/auth/LoginPage';
import { RequireAuth } from '@/features/auth/RequireAuth';
import { useApplyTheme } from '@/features/settings/useApplyTheme';
import { createQueryClient } from '@/queryClient';

const ChatPage = lazy(() =>
  import('@/features/chat/ChatPage').then((m) => ({ default: m.ChatPage })),
);
const KnowledgeBasePage = lazy(() =>
  import('@/features/knowledge-base/KnowledgeBasePage').then((m) => ({
    default: m.KnowledgeBasePage,
  })),
);
const AnalyticsPage = lazy(() =>
  import('@/features/analytics/AnalyticsPage').then((m) => ({ default: m.AnalyticsPage })),
);
const SettingsPage = lazy(() =>
  import('@/features/settings/SettingsPage').then((m) => ({ default: m.SettingsPage })),
);

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<ChatPage />} />
        <Route path="c/:conversationId" element={<ChatPage />} />
        <Route path="knowledge" element={<KnowledgeBasePage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  const [queryClient] = useState(createQueryClient);
  useApplyTheme();
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <AuthProvider>
            <AppRoutes />
          </AuthProvider>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}
