import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import type { Project } from '../../types';

// ── useProjects mock — drive items / pagination directly ─────────────
const loadMoreMock = vi.fn();
const useProjectsMock = vi.fn();
vi.mock('../../hooks/useProjects', () => ({
  useProjects: (...args: unknown[]) => useProjectsMock(...args),
}));

// Stub ProjectRow so the browser logic (narrowing / open callback / load-more)
// is tested in isolation, without the state-card's own queries. The stub
// exposes the name + an Open button wired to onOpen.
vi.mock('../ProjectRow', () => ({
  ProjectRow: ({ project, onOpen }: { project: Project; onOpen?: (p: Project) => void }) => (
    <div data-testid={`row-${project.project_id}`}>
      <span>{project.name}</span>
      {onOpen && (
        <button data-testid={`open-${project.project_id}`} onClick={() => onOpen(project)}>
          open
        </button>
      )}
    </div>
  ),
}));

// ProjectFormModal pulls in heavy deps; stub it to nothing.
vi.mock('../ProjectFormModal', () => ({
  ProjectFormModal: () => null,
}));

import { ProjectsBrowser } from '../ProjectsBrowser';

function mk(over: Partial<Project>): Project {
  return {
    project_id: over.project_id ?? 'p',
    name: over.name ?? 'name',
    is_archived: over.is_archived ?? false,
    extraction_status: over.extraction_status ?? 'disabled',
    book_id: over.book_id ?? null,
    updated_at: over.updated_at ?? '2026-01-01T00:00:00Z',
  } as Project;
}

function setProjects(items: Project[], extra: Record<string, unknown> = {}) {
  useProjectsMock.mockReturnValue({
    items,
    hasMore: false,
    loadMore: loadMoreMock,
    isFetchingMore: false,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    createProject: vi.fn(),
    updateProject: vi.fn(),
    archiveProject: vi.fn(),
    deleteProject: vi.fn(),
    isMutating: false,
    ...extra,
  });
}

function renderBrowser(onOpen: (p: Project) => void = vi.fn(), scopedBookId?: string) {
  return render(<ProjectsBrowser onOpen={onOpen} scopedBookId={scopedBookId} />);
}

describe('ProjectsBrowser — 14_kg_panels.md A2 (DOCK-2 extraction shared by ProjectsTab + KnowledgeHubPanel)', () => {
  beforeEach(() => {
    loadMoreMock.mockReset();
    useProjectsMock.mockReset();
  });

  it('narrows the list by search', () => {
    setProjects([
      mk({ project_id: 'a', name: 'Winds of the East' }),
      mk({ project_id: 'b', name: 'Northern Saga' }),
    ]);
    renderBrowser();
    expect(screen.getByTestId('row-a')).toBeDefined();
    expect(screen.getByTestId('row-b')).toBeDefined();

    fireEvent.change(screen.getByTestId('projects-search'), {
      target: { value: 'wind' },
    });
    expect(screen.getByTestId('row-a')).toBeDefined();
    expect(screen.queryByTestId('row-b')).toBeNull();
  });

  it('narrows by state filter', () => {
    setProjects([
      mk({ project_id: 'a', extraction_status: 'ready' }),
      mk({ project_id: 'b', extraction_status: 'failed' }),
    ]);
    renderBrowser();
    fireEvent.change(screen.getByTestId('projects-state-filter'), {
      target: { value: 'failed' },
    });
    expect(screen.queryByTestId('row-a')).toBeNull();
    expect(screen.getByTestId('row-b')).toBeDefined();
  });

  it('reorders by sort (name desc)', () => {
    setProjects([
      mk({ project_id: 'a', name: 'Alpha' }),
      mk({ project_id: 'z', name: 'Zeta' }),
    ]);
    renderBrowser();
    fireEvent.change(screen.getByTestId('projects-sort'), {
      target: { value: 'name_desc' },
    });
    const rows = screen.getAllByTestId(/^row-/);
    expect(rows[0].getAttribute('data-testid')).toBe('row-z');
    expect(rows[1].getAttribute('data-testid')).toBe('row-a');
  });

  it('calls onOpen with the clicked project — the caller decides navigate vs. studio-link', () => {
    const onOpen = vi.fn();
    setProjects([mk({ project_id: 'proj-9', name: 'Proj' })]);
    renderBrowser(onOpen);
    fireEvent.click(screen.getByTestId('open-proj-9'));
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ project_id: 'proj-9' }));
  });

  it('shows a no-matches notice when filters hide every loaded row', () => {
    setProjects([mk({ project_id: 'a', name: 'Alpha' })]);
    renderBrowser();
    fireEvent.change(screen.getByTestId('projects-search'), {
      target: { value: 'zzz-no-match' },
    });
    expect(screen.getByTestId('projects-no-matches')).toBeDefined();
  });

  it('renders a real Load more button that calls fetchNextPage', () => {
    setProjects([mk({ project_id: 'a', name: 'Alpha' })], { hasMore: true });
    renderBrowser();
    const more = screen.getByTestId('projects-load-more');
    fireEvent.click(more);
    expect(loadMoreMock).toHaveBeenCalledTimes(1);
  });

  it('hides Load more when there are no more pages', () => {
    setProjects([mk({ project_id: 'a', name: 'Alpha' })], { hasMore: false });
    renderBrowser();
    expect(screen.queryByTestId('projects-load-more')).toBeNull();
  });

  it('debounces the search term that drives the server query', () => {
    vi.useFakeTimers();
    try {
      setProjects([mk({ project_id: 'a', name: 'Alpha' })]);
      renderBrowser();
      useProjectsMock.mockClear();

      const input = screen.getByTestId('projects-search');
      // Rapid keystrokes — each fires synchronously, none should reach
      // useProjects with a non-empty `search` until the debounce settles.
      fireEvent.change(input, { target: { value: 'c' } });
      fireEvent.change(input, { target: { value: 'cr' } });
      fireEvent.change(input, { target: { value: 'cra' } });
      fireEvent.change(input, { target: { value: 'crad' } });

      // Before the debounce window elapses, every useProjects call still
      // carries the pre-typing (empty) search term — no per-keystroke fetch.
      const midCalls = useProjectsMock.mock.calls.map((c) => c[0].search);
      expect(midCalls.every((s) => !s)).toBe(true);

      // Advance past the debounce; the LATEST term reaches the query once.
      act(() => {
        vi.advanceTimersByTime(400);
      });
      const lastCall = useProjectsMock.mock.calls.at(-1)![0];
      expect(lastCall.search).toBe('crad');
    } finally {
      vi.useRealTimers();
    }
  });

  // D-KG-HUB-BOOK-SCOPE
  describe('scopedBookId (opened from a book\'s studio)', () => {
    it('omits the toggle and never book-scopes the query when scopedBookId is absent (classic /knowledge route)', () => {
      setProjects([mk({ project_id: 'a' })]);
      renderBrowser();
      expect(screen.queryByTestId('projects-book-scope-toggle')).toBeNull();
      expect(useProjectsMock.mock.calls.at(-1)![0].bookId).toBeUndefined();
    });

    it('defaults to book-scoped when scopedBookId is provided', () => {
      setProjects([mk({ project_id: 'a' })]);
      renderBrowser(vi.fn(), 'book-42');
      expect(screen.getByTestId('projects-book-scope-toggle')).toBeInTheDocument();
      expect(useProjectsMock.mock.calls.at(-1)![0].bookId).toBe('book-42');
    });

    it('toggling switches to all-books (bookId undefined) and back, never silently stuck', () => {
      setProjects([mk({ project_id: 'a' })]);
      renderBrowser(vi.fn(), 'book-42');
      const toggle = screen.getByTestId('projects-book-scope-toggle');

      fireEvent.click(toggle);
      expect(useProjectsMock.mock.calls.at(-1)![0].bookId).toBeUndefined();

      fireEvent.click(toggle);
      expect(useProjectsMock.mock.calls.at(-1)![0].bookId).toBe('book-42');
    });
  });
});
