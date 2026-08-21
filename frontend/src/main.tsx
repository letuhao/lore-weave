import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { registerServiceWorker } from './pwa/registerSW';
import './i18n';
import './index.css';
import { installFetchTracker } from './lib/operationTracker';
import { installGlobalErrorLogging } from './lib/clientErrorReporter';
import { AppErrorBoundary } from './components/shared/AppErrorBoundary';

installFetchTracker();
installGlobalErrorLogging();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppErrorBoundary><App /></AppErrorBoundary>
  </StrictMode>,
);

// PWA (M4) — register the service worker (prod-only; dev uses MSW + HMR).
registerServiceWorker();
