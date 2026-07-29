import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { initI18n } from '@loreweave/i18n';
import App from './App';
import { SessionProvider } from './store/session-context';
import './styles/globals.css';

// Bootstrap translations BEFORE the first render. `useTranslation` would
// otherwise render one frame against an uninitialised instance and flash raw
// key names at the user.
initI18n();

const rootEl = document.getElementById('root');
if (!rootEl) {
  throw new Error('Root element #root not found in index.html');
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(rootEl).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        {/* basename tracks vite's `base`, so the app routes correctly whether
            it is served standalone at '/' or under '/game/' behind the shared
            origin. Hardcoding '/' here would break every route in the latter. */}
        <BrowserRouter basename={import.meta.env.BASE_URL}>
          <App />
        </BrowserRouter>
      </SessionProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
