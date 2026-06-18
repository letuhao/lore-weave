import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { Project } from '../../types';

// ── Navigation spy ───────────────────────────────────────────────────
const navigateMock = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock };
});

// ── useProjects mock — drive items / pagination directly ─────────────
const loadMoreMock = vi.fn();
const useProjectsMock = vi.fn();
vi.mock('../../hooks/useProjects', () => ({
  useProjects: (...args: unknown[]) => useProjectsMock(...args),
}));

// Stub ProjectRow so the browser logic (narrowing / routing / load-more)
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

import { ProjectsTab } from '../ProjectsTab';

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

function renderTab() {
  return render(
    <MemoryRouter>
      <ProjectsTab />
    </MemoryRouter>,
  );
}

describe('ProjectsTab — HOME browser', () => {
  beforeEach(() => {
    navigateMock.mockReset();
    loadMoreMock.mockReset();
    useProjectsMock.mockReset();
  });

  it('narrows the list by search', () => {
    setProjects([
      mk({ project_id: 'a', name: 'Winds of the East' }),
      mk({ project_id: 'b', name: 'Northern Saga' }),
    ]);
    renderTab();
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
    renderTab();
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
    renderTab();
    fireEvent.change(screen.getByTestId('projects-sort'), {
      target: { value: 'name_desc' },
    });
    const rows = screen.getAllByTestId(/^row-/);
    expect(rows[0].getAttribute('data-testid')).toBe('row-z');
    expect(rows[1].getAttribute('data-testid')).toBe('row-a');
  });

  it('routes a row INTO the C6 detail shell', () => {
    setProjects([mk({ project_id: 'proj-9', name: 'Proj' })]);
    renderTab();
    fireEvent.click(screen.getByTestId('open-proj-9'));
    expect(navigateMock).toHaveBeenCalledWith(
      '/knowledge/projects/proj-9/overview',
    );
  });

  it('shows a no-matches notice when filters hide every loaded row', () => {
    setProjects([mk({ project_id: 'a', name: 'Alpha' })]);
    renderTab();
    fireEvent.change(screen.getByTestId('projects-search'), {
      target: { value: 'zzz-no-match' },
    });
    expect(screen.getByTestId('projects-no-matches')).toBeDefined();
  });

  it('renders a real Load more button that calls fetchNextPage', () => {
    setProjects([mk({ project_id: 'a', name: 'Alpha' })], { hasMore: true });
    renderTab();
    const more = screen.getByTestId('projects-load-more');
    fireEvent.click(more);
    expect(loadMoreMock).toHaveBeenCalledTimes(1);
  });

  it('hides Load more when there are no more pages', () => {
    setProjects([mk({ project_id: 'a', name: 'Alpha' })], { hasMore: false });
    renderTab();
    expect(screen.queryByTestId('projects-load-more')).toBeNull();
  });

  it('debounces the search term that drives the server query', () => {
    vi.useFakeTimers();
    try {
      setProjects([mk({ project_id: 'a', name: 'Alpha' })]);
      renderTab();
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
});
