import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import type { ReactNode } from 'react';
import { WorldWorkspacePage } from '../pages/WorldWorkspacePage';

// C21 — the workspace is PROSE-LESS: it must render lore authoring + a read-only
// graph, and must NEVER surface the book/chapter/manuscript mechanic. These
// tests assert (a) no manuscript/editor surface, (b) the lore panel anchors to
// the bible chapter, (c) the graph is the read-only C19 reuse.

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }),
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));

// Mock the world resolver to a world WITH a bible handle.
vi.mock('../hooks/useWorld', () => ({
  useWorld: () => ({
    world: { world_id: 'w1', name: 'Cradle', description: 'a realm', bible_book_id: 'bb1', bible_chapter_id: 'bc0' },
    bibleBookId: 'bb1',
    bibleChapterId: 'bc0',
    anchorReady: true,
    isLoading: false,
    isError: false,
    error: null,
  }),
}));
// The lore hook + project resolver are exercised in their own tests — stub here.
vi.mock('../hooks/useWorldLore', () => ({
  useWorldLore: () => ({
    kinds: [{ kind_id: 'k1', code: 'character', name: 'Character' }],
    kindsLoading: false,
    authorLore: vi.fn(),
    isAuthoring: false,
    lastLink: null,
    error: null,
  }),
}));
// The world graph is now the W2 rollup (WorldRollupGraph → useWorldSubgraph);
// stub it to an empty union so the section renders a stable state here (its own
// states are covered in WorldRollupGraph.test.tsx).
vi.mock('../hooks/useWorldSubgraph', () => ({
  useWorldSubgraph: () => ({
    nodes: [], edges: [], sources: [], truncated: false,
    isLoading: false, isFetching: false, error: null, refetch: vi.fn(),
  }),
}));

function renderWorkspace() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/worlds/w1']}>
        <Routes>
          <Route path="/worlds/:worldId" element={<WorldWorkspacePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe('WorldWorkspacePage — prose-less worldbuilding', () => {
  it('renders the world workspace with the lore panel and graph section', () => {
    renderWorkspace();
    expect(screen.getByTestId('world-workspace')).toBeInTheDocument();
    expect(screen.getByTestId('world-lore-panel')).toBeInTheDocument();
    expect(screen.getByTestId('world-graph-section')).toBeInTheDocument();
  });

  it('hides the book/manuscript mechanic — no editor/chapter surface', () => {
    renderWorkspace();
    // The book mechanic is hidden: NO manuscript/editor/chapter-list SURFACE
    // (testid affordances) and no rich-text editor element. (The advisory copy
    // may *mention* "no manuscript needed" — that's messaging, not a surface,
    // so we assert on affordances, not on words.)
    expect(screen.queryByTestId('manuscript')).not.toBeInTheDocument();
    expect(screen.queryByTestId('chapter-editor')).not.toBeInTheDocument();
    expect(screen.queryByTestId('chapter-list')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    // No link routes the user into a book/chapter editor from the workspace.
    const links = Array.from(document.querySelectorAll('a[href]')).map((a) => a.getAttribute('href') ?? '');
    expect(links.some((h) => /\/books\/|\/chapters\//.test(h))).toBe(false);
  });

  it('presents the lore panel as anchored + extraction-optional', () => {
    renderWorkspace();
    // The extraction-optional advisory is shown (extraction is NOT required).
    expect(screen.getByTestId('extraction-optional-note')).toBeInTheDocument();
    // The kind picker + add control are present (authoring is available).
    expect(screen.getByTestId('world-lore-kind')).toBeInTheDocument();
    expect(screen.getByTestId('world-lore-add')).toBeInTheDocument();
    // No "anchor unavailable" warning when the bible handle is present.
    expect(screen.queryByTestId('anchor-unavailable')).not.toBeInTheDocument();
  });
});
