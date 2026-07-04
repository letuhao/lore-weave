// 15_wiki_panels.md B3 (DOCK-9) + B1a (DOCK-7) — hand-rolled `fixed inset-0` replaced with
// FormDialog; the empty-state Glossary link branches on useOptionalStudioHost() so it never
// navigate()s the studio away from itself.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StudioHostProvider } from '@/features/studio/host/StudioHostProvider';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const listEntities = vi.fn();
vi.mock('@/features/glossary/api', () => ({
  glossaryApi: { listEntities: (...a: unknown[]) => listEntities(...a) },
}));
const listArticles = vi.fn();
const createArticle = vi.fn();
vi.mock('../../api', () => ({
  wikiApi: {
    listArticles: (...a: unknown[]) => listArticles(...a),
    createArticle: (...a: unknown[]) => createArticle(...a),
  },
}));

import { CreateArticleDialog } from '../CreateArticleDialog';

beforeEach(() => {
  vi.clearAllMocks();
  listEntities.mockResolvedValue({ items: [], total: 0 });
  listArticles.mockResolvedValue({ items: [] });
});

function setup(insideStudio: boolean, onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = (
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CreateArticleDialog bookId="b1" open onClose={onClose} />
      </MemoryRouter>
    </QueryClientProvider>
  );
  const utils = render(insideStudio ? <StudioHostProvider bookId="b1">{tree}</StudioHostProvider> : tree);
  return { ...utils, onClose };
}

describe('CreateArticleDialog', () => {
  it('renders as a real Radix dialog (role=dialog), not a hand-rolled overlay', async () => {
    setup(false);
    await waitFor(() => expect(screen.getByRole('dialog')).toBeTruthy());
  });

  it('Escape closes via onOpenChange(false) (Radix default — no manual keydown listener)', async () => {
    const { onClose } = setup(false);
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('outside the studio, the empty-state Glossary link is a real <Link>', async () => {
    setup(false);
    await waitFor(() => expect(screen.getByText('Go to Glossary')).toBeTruthy());
    const link = screen.getByText('Go to Glossary');
    expect(link.tagName).toBe('A');
    expect(link.getAttribute('href')).toBe('/books/b1/glossary');
  });

  it('inside the studio, the empty-state Glossary link is a button that opens the panel instead of navigating', async () => {
    setup(true);
    await waitFor(() => expect(screen.getByText('Go to Glossary')).toBeTruthy());
    const trigger = screen.getByText('Go to Glossary');
    expect(trigger.tagName).toBe('BUTTON');
    expect(() => fireEvent.click(trigger)).not.toThrow();
  });
});
