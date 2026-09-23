import { useLocalStorage } from '@/hooks/useLocalStorage';

export type ThemePreference = 'system' | 'light' | 'dark';

export const THEME_KEY = 'nexaai.theme';
export const INSPECTOR_KEY = 'nexaai.showInspector';

export function isThemePreference(value: unknown): value is ThemePreference {
  return value === 'system' || value === 'light' || value === 'dark';
}

export function isBoolean(value: unknown): value is boolean {
  return typeof value === 'boolean';
}

export function useThemePreference() {
  return useLocalStorage<ThemePreference>(THEME_KEY, 'system', isThemePreference);
}

export function useInspectorDefault() {
  return useLocalStorage<boolean>(INSPECTOR_KEY, false, isBoolean);
}

export function applyTheme(preference: ThemePreference, systemPrefersDark: boolean): void {
  const dark = preference === 'dark' || (preference === 'system' && systemPrefersDark);
  document.documentElement.classList.toggle('dark', dark);
}
