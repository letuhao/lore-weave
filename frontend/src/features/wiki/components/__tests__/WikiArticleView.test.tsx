// 15_wiki_panels.md B1a (DOCK-7) + B8 — Edit/History must not navigate() the whole app away
// from a mounted studio; both branch on useOptionalStudioHost() (StepConfig.tsx precedent).
// History was previously a DEAD button (no onClick at all) — B8 wires it to the editor's
// history tab.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { StudioHostProvider } from '@/features/studio/host/StudioHostProvider';
import type { WikiArticleDetail } from '../../types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('@/components/reader/ContentRenderer', () => ({ ContentRenderer: () => <div /> }));
vi.mock('@/components/reader/CitationContext', () => ({ CitationProvider: ({ children }: { children: React.ReactNode }) => <>{children}</> }));

const article: WikiArticleDetail = {
  article_id: 'a1', entity_id: 'e1', book_id: 'b1', display_name: 'Mina',
  kind: { kind_id: 'k', code: 'character', name: 'Character', icon: '', color: '#abc' },
  status: 'published', template_code: null, revision_count: 2,
  updated_at: '2026-06-11T00:00:00Z', body_json: { content: [] },
  spoiler_chapters: [], infobox: [], created_at: '2026-06-11T00:00:00Z',
};

const navigateMock = vi.fn();
vi.mock('react-router-dom', async (orig) => ({
  ...(await orig<typeof import('react-router-dom')>()),
  useNavigate: () => navigateMock,
}));

vi.mock('@tanstack/react-query', () => ({
  useQuery: ({ queryKey }: { queryKey: unknown[] }) =>
    queryKey[0] === 'wiki-article' ? { data: article, isLoading: false } : { data: { items: [] } },
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

import { WikiArticleView } from '../WikiWorkspace';

function setup(insideStudio: boolean) {
  const tree = (
    <MemoryRouter>
      <WikiArticleView bookId="b1" articleId="a1" onRegenerate={() => {}} />
    </MemoryRouter>
  );
  return render(insideStudio ? <StudioHostProvider bookId="b1">{tree}</StudioHostProvider> : tree);
}

describe('WikiArticleView — Edit/History DOCK-7 branch', () => {
  beforeEach(() => { navigateMock.mockClear(); });

  it('outside the studio, Edit navigates to the classic edit route', () => {
    setup(false);
    fireEvent.click(screen.getByText('edit'));
    expect(navigateMock).toHaveBeenCalledWith('/books/b1/wiki/a1/edit');
  });

  it('inside the studio, Edit opens the wiki-editor panel instead of navigating', async () => {
    setup(true);
    fireEvent.click(screen.getByText('edit'));
    await waitFor(() => expect(navigateMock).not.toHaveBeenCalled());
  });

  // B8 — History was a dead button before this migration (no onClick at all).
  it('outside the studio, History falls back to the plain edit route (no query-param seam)', () => {
    setup(false);
    fireEvent.click(screen.getByTestId('wiki-history'));
    expect(navigateMock).toHaveBeenCalledWith('/books/b1/wiki/a1/edit');
  });

  it('inside the studio, History opens wiki-editor pre-targeted at the history tab', async () => {
    setup(true);
    fireEvent.click(screen.getByTestId('wiki-history'));
    await waitFor(() => expect(navigateMock).not.toHaveBeenCalled());
  });
});
