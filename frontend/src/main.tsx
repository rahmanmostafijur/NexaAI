import '@fontsource-variable/inter';
import '@fontsource/noto-sans-bengali/400.css';
import '@fontsource/noto-sans-bengali/500.css';
import '@fontsource/noto-sans-bengali/600.css';
import 'highlight.js/styles/github-dark.css';
import './index.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { THEME_KEY, applyTheme, isThemePreference } from './features/settings/preferences';
import { readStoredValue } from './hooks/useLocalStorage';

// Apply the stored theme before first paint to avoid a flash of the wrong theme.
applyTheme(
  readStoredValue(THEME_KEY, 'system', isThemePreference),
  window.matchMedia('(prefers-color-scheme: dark)').matches,
);

const container = document.getElementById('root');
if (!container) throw new Error('Root element #root not found');

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
