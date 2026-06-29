import type { ReactElement } from 'react';
import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// bug #41 — the chat confirm cards (ConfirmActionCard / ConfirmCard / BatchConfirmCard)
// now call useQueryClient() to invalidate the viewing-page caches after a commit, so any
// test that renders them must provide a QueryClientProvider. A fresh client per render
// (retry off) keeps tests isolated and synchronous.
export function renderWithClient(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(ui, {
    wrapper: ({ children }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>,
  });
}
