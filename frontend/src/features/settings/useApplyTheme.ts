import { useEffect } from 'react';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { applyTheme, useThemePreference } from './preferences';

/** Keeps the `dark` class on <html> in sync with the preference and OS setting. */
export function useApplyTheme(): void {
  const [theme] = useThemePreference();
  const systemDark = useMediaQuery('(prefers-color-scheme: dark)');
  useEffect(() => applyTheme(theme, systemDark), [theme, systemDark]);
}
