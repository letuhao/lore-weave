import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const useProjectsMock = vi.fn();
vi.mock('../../../hooks/useProjects', () => ({
  useProjects: (...args: unknown[]) => useProjectsMock(...args),
}));

// BuildGraphDialog is a complex child that fires its own queries
// (ai-models, estimate). Stub it so the mobile list test doesn't
// drag in half the hook graph. Stub exposes BOTH ``onStarted`` and
// ``onOpenChange(false)`` so tests can exercise the parent's post-
// start refetch contract and close-path state reset — found in
// review-impl MED #1 and LOW #5 as silent coverage gaps.
vi.mock('../../BuildGraphDialog', () => ({
  BuildGraphDialog: ({
    open,
    project,
    onOpenChange,
    onStarted,
  }: {
    open: boolean;
    project: { project_id: string; name: string };
    onOpenChange: (o: boolean) => void;
    onStarted: () => void;
  }) =>
    open ? (
      <div
        data-testid="stub-build-graph-dialog"
        data-project-id={project.project_id}
      >
        {project.name}
        <button
          type="button"
          data-testid="stub-build-started"
          onClick={onStarted}
        >
          simulate start
        </button>
        <button
          type="button"
          data-testid="stub-build-close"
          onClick={() => onOpenChange(false)}
        >
          simulate close
        </button>
      </div>
    ) : null,
}));

import { ProjectsMobile } from '../ProjectsMobile';
import type { Project } from '../../../types';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function makeProject(overrides: Partial<Project> = {}): Project {
  return {
    project_id: 'p-1',
    user_id: 'u1',
    name: 'Crimson Echoes',
    description: 'A tale of swords and lanterns at the bridge.',
    project_type: 'book',
    book_id: null,
    instructions: '',
    extraction_enabled: true,
    extraction_status: 'ready',
    embedding_model: 'bge-m3',
    embedding_dimension: 1024,
    extraction_config: {},
    last_extracted_at: '2026-04-20T12:00:00Z',
    estimated_cost_usd: '0.00',
    actual_cost_usd: '0.00',
    is_archived: false,
    version: 1,
    created_at: '2026-04-01T00:00:00Z',
    updated_at: '2026-04-20T12:00:00Z',
    ...overrides,
  };
}

function makeHookReturn(
  overrides: Partial<ReturnType<typeof useProjectsMock>> = {},
) {
  return {
    items: [makeProject()],
    hasMore: false,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    createProject: vi.fn(),
    updateProject: vi.fn(),
    archiveProject: vi.fn(),
    deleteProject: vi.fn(),
    isMutating: false,
    ...overrides,
  };
}

describe('ProjectsMobile', () => {
  beforeEach(() => {
    useProjectsMock.mockReset();
  });

  it('excludes archived by passing includeArchived=false to useProjects', () => {
    useProjectsMock.mockReturnValue(makeHookReturn({ items: [] }));
    render(<ProjectsMobile />, { wrapper: Wrapper });
    expect(useProjectsMock).toHaveBeenCalledWith(false);
  });

  it('renders loading skeleton then cards and applies TOUCH_TARGET_CLASS to toggle', () => {
    useProjectsMock.mockReturnValueOnce(makeHookReturn({ isLoading: true }));
    const { rerender } = render(<ProjectsMobile />, { wrapper: Wrapper });
    expect(screen.getByTestId('mobile-projects-loading')).toBeTruthy();
    useProjectsMock.mockReturnValue(
      makeHookReturn({
        items: [makeProject(), makeProject({ project_id: 'p-2', name: 'Second' })],
      }),
    );
    rerender(<ProjectsMobile />);
    const cards = screen.getAllByTestId('mobile-project-card');
    expect(cards).toHaveLength(2);
    // Lock the tap-target class on the toggle button (L2 pattern).
    const toggle = screen.getAllByTestId('mobile-project-toggle')[0] as HTMLButtonElement;
    expect(toggle.className).toContain('min-h-[44px]');
  });

  it('surfaces error state', () => {
    useProjectsMock.mockReturnValue(
      makeHookReturn({
        isError: true,
        error: new Error('network down'),
        items: [],
      }),
    );
    render(<ProjectsMobile />, { wrapper: Wrapper });
    expect(screen.getByTestId('mobile-projects-error')).toBeTruthy();
  });

  it('renders empty state when no projects', () => {
    useProjectsMock.mockReturnValue(makeHookReturn({ items: [] }));
    render(<ProjectsMobile />, { wrapper: Wrapper });
    expect(screen.getByTestId('mobile-projects-empty')).toBeTruthy();
  });

  it('toggles detail on tap (single-expand) and shows description + metadata', () => {
    useProjectsMock.mockReturnValue(
      makeHookReturn({
        items: [
          makeProject(),
          makeProject({ project_id: 'p-2', name: 'Second' }),
        ],
      }),
    );
    render(<ProjectsMobile />, { wrapper: Wrapper });
    expect(screen.queryByTestId('mobile-project-detail')).toBeNull();
    const toggles = screen.getAllByTestId('mobile-project-toggle');
    fireEvent.click(toggles[0]);
    expect(screen.getAllByTestId('mobile-project-detail')).toHaveLength(1);
    // Tap again → collapses.
    fireEvent.click(toggles[0]);
    expect(screen.queryByTestId('mobile-project-detail')).toBeNull();
    // Tap different card → only one expanded at a time.
    fireEvent.click(toggles[0]);
    fireEvent.click(toggles[1]);
    expect(screen.getAllByTestId('mobile-project-detail')).toHaveLength(1);
  });

  it('Build button opens BuildGraphDialog with the right project and stopPropagation prevents collapse', () => {
    useProjectsMock.mockReturnValue(makeHookReturn());
    render(<ProjectsMobile />, { wrapper: Wrapper });
    const toggle = screen.getByTestId('mobile-project-toggle');
    fireEvent.click(toggle);
    const build = screen.getByTestId('mobile-project-build');
    expect(screen.queryByTestId('stub-build-graph-dialog')).toBeNull();
    fireEvent.click(build);
    const dialog = screen.getByTestId('stub-build-graph-dialog');
    expect(dialog.getAttribute('data-project-id')).toBe('p-1');
    // Detail should STILL be expanded — stopPropagation prevented the
    // toggle-collapse click from firing when the Build button handler
    // ran. Regression lock: without stopPropagation, the Build click
    // would bubble to the toggle's onClick and collapse the card.
    expect(screen.queryByTestId('mobile-project-detail')).toBeTruthy();
  });

  it('disables Build button while extraction_status is building', () => {
    useProjectsMock.mockReturnValue(
      makeHookReturn({
        items: [makeProject({ extraction_status: 'building' })],
      }),
    );
    render(<ProjectsMobile />, { wrapper: Wrapper });
    fireEvent.click(screen.getByTestId('mobile-project-toggle'));
    const build = screen.getByTestId('mobile-project-build') as HTMLButtonElement;
    expect(build.disabled).toBe(true);
  });

  it('disables Build button when embedding_model is null (not configured)', () => {
    useProjectsMock.mockReturnValue(
      makeHookReturn({
        items: [makeProject({ embedding_model: null })],
      }),
    );
    render(<ProjectsMobile />, { wrapper: Wrapper });
    fireEvent.click(screen.getByTestId('mobile-project-toggle'));
    const build = screen.getByTestId('mobile-project-build') as HTMLButtonElement;
    expect(build.disabled).toBe(true);
  });

  it('fires refetch() when the build dialog reports onStarted (review-impl MED)', async () => {
    // Regression lock for the `void refetch()` call inside onStarted.
    // Without it, after a user kicks off a build, the list status
    // badge would stay on the old value instead of flipping to
    // "building". Prior stub didn't expose onStarted so this
    // contract was silently uncovered.
    const refetch = vi.fn();
    useProjectsMock.mockReturnValue(makeHookReturn({ refetch }));
    render(<ProjectsMobile />, { wrapper: Wrapper });
    fireEvent.click(screen.getByTestId('mobile-project-toggle'));
    fireEvent.click(screen.getByTestId('mobile-project-build'));
    await screen.findByTestId('stub-build-graph-dialog');
    expect(refetch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('stub-build-started'));
    expect(refetch).toHaveBeenCalled();
    // Dialog also unmounts because onStarted sets buildProject=null.
    await waitFor(() => {
      expect(screen.queryByTestId('stub-build-graph-dialog')).toBeNull();
    });
  });

  it('closes the dialog when onOpenChange(false) fires (review-impl LOW #5)', async () => {
    // If a regression inverted the open-guard (`if (o)` instead of
    // `if (!o)`), clicking the dialog's close affordance would leak
    // `buildProject` state and leave the dialog mounted forever.
    useProjectsMock.mockReturnValue(makeHookReturn());
    render(<ProjectsMobile />, { wrapper: Wrapper });
    fireEvent.click(screen.getByTestId('mobile-project-toggle'));
    fireEvent.click(screen.getByTestId('mobile-project-build'));
    await screen.findByTestId('stub-build-graph-dialog');
    fireEvent.click(screen.getByTestId('stub-build-close'));
    await waitFor(() => {
      expect(screen.queryByTestId('stub-build-graph-dialog')).toBeNull();
    });
  });

  it('renders the noDescription placeholder when description is empty (review-impl LOW #3)', () => {
    useProjectsMock.mockReturnValue(
      makeHookReturn({
        items: [makeProject({ description: '' })],
      }),
    );
    render(<ProjectsMobile />, { wrapper: Wrapper });
    fireEvent.click(screen.getByTestId('mobile-project-toggle'));
    const detail = screen.getByTestId('mobile-project-detail');
    // i18n mock-bypass returns the key verbatim. The important bit
    // is that the key appears AT ALL — a regression changing the
    // ternary to accept empty-string as a real description would
    // show the empty <p> instead of this key.
    expect(detail.textContent).toContain('mobile.projects.noDescription');
  });

  it('truncates long descriptions in the collapsed preview with an ellipsis (review-impl LOW #4)', () => {
    const longDesc = 'A'.repeat(200);
    useProjectsMock.mockReturnValue(
      makeHookReturn({
        items: [makeProject({ description: longDesc })],
      }),
    );
    render(<ProjectsMobile />, { wrapper: Wrapper });
    // Card is collapsed by default — preview shows. Find the card
    // container and check its text contains the truncation
    // indicator (ellipsis char) and NOT the full 200-char string.
    const card = screen.getByTestId('mobile-project-card');
    expect(card.textContent).toContain('…');
    // Full description shouldn't appear collapsed. The 200 'A's as
    // a substring would only match if the full description rendered;
    // truncated preview is ~100 A's + ellipsis.
    expect(card.textContent).not.toContain('A'.repeat(200));
  });
});
