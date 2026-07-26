import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));

// ProjectRow has heavy dialog deps; stub it — but expose an edit trigger so the
// KN pen-button wiring (onEdit opens the form modal in the detail shell) is testable.
vi.mock('../../ProjectRow', () => ({
  ProjectRow: ({ onEdit }: { onEdit: () => void }) => (
    <button data-testid="stub-row-edit" onClick={onEdit}>edit</button>
  ),
}));

// ProjectFormModal is stubbed to a marker that echoes its open/mode props.
vi.mock('../../ProjectFormModal', () => ({
  ProjectFormModal: ({ open, mode }: { open: boolean; mode: string }) =>
    open ? <div data-testid="stub-form-modal">{mode}</div> : null,
}));

const updateProject = vi.fn();
const createProject = vi.fn();
vi.mock('../../../hooks/useProjects', () => ({
  useProjects: () => ({ createProject, updateProject }),
}));

const backlinks = vi.fn();
vi.mock('../../../hooks/useProjectBacklinks', () => ({
  useProjectBacklinks: () => backlinks(),
}));

import { OverviewSection } from '../OverviewSection';
import type { Project } from '../../../types';

const project = { project_id: 'p1', book_id: 'b1', embedding_model: null, rerank_model: null, extraction_enabled: true } as unknown as Project;

function renderOverview(
  p: Project | null,
  opts?: { onOpenBook?: (bookId: string) => void; onOpenWorld?: (worldId: string) => void },
) {
  render(
    <OverviewSection
      project={p}
      onExploreGraph={vi.fn()}
      onOpenBook={opts?.onOpenBook ?? vi.fn()}
      onOpenWorld={opts?.onOpenWorld ?? vi.fn()}
    />,
  );
}

beforeEach(() => backlinks.mockReset());

describe('OverviewSection triage nudge (S-05 deep-link IN)', () => {
  it('shows the nudge and opens triage ONLY when count > 0 and the callback is given', () => {
    backlinks.mockReturnValue({ bookTitle: 'B', worldId: null });
    const onOpenTriage = vi.fn();
    render(
      <OverviewSection
        project={project}
        onExploreGraph={vi.fn()}
        onOpenBook={vi.fn()}
        onOpenWorld={vi.fn()}
        triageCount={3}
        onOpenTriage={onOpenTriage}
      />,
    );
    const nudge = screen.getByTestId('shell-overview-triage-nudge');
    fireEvent.click(nudge);
    expect(onOpenTriage).toHaveBeenCalledTimes(1);
  });

  it('hides the nudge when the count is 0 (no clutter on a clean graph)', () => {
    backlinks.mockReturnValue({ bookTitle: 'B', worldId: null });
    render(
      <OverviewSection
        project={project}
        onExploreGraph={vi.fn()}
        onOpenBook={vi.fn()}
        onOpenWorld={vi.fn()}
        triageCount={0}
        onOpenTriage={vi.fn()}
      />,
    );
    expect(screen.queryByTestId('shell-overview-triage-nudge')).not.toBeInTheDocument();
  });

  it('hides the nudge on the classic route (no onOpenTriage)', () => {
    backlinks.mockReturnValue({ bookTitle: 'B', worldId: null });
    renderOverview(project);
    expect(screen.queryByTestId('shell-overview-triage-nudge')).not.toBeInTheDocument();
  });
});

describe('OverviewSection backlinks (D-WORLD-PROJECT-BACKLINK)', () => {
  it('links to the book by title and to the world when grouped (DOCK-7: via callback, not <Link>)', () => {
    backlinks.mockReturnValue({ bookTitle: 'Cradle', worldId: 'w1', worldName: 'Aethyr', isLoading: false });
    const onOpenBook = vi.fn();
    const onOpenWorld = vi.fn();
    renderOverview(project, { onOpenBook, onOpenWorld });
    const bookLink = screen.getByTestId('overview-book-link');
    expect(bookLink).toHaveTextContent('Cradle');
    fireEvent.click(bookLink);
    expect(onOpenBook).toHaveBeenCalledWith('b1');
    const worldLink = screen.getByTestId('overview-world-link');
    expect(worldLink).toHaveTextContent('Aethyr');
    fireEvent.click(worldLink);
    expect(onOpenWorld).toHaveBeenCalledWith('w1');
  });

  it('omits the world link when the book is standalone', () => {
    backlinks.mockReturnValue({ bookTitle: 'Standalone', worldId: null, worldName: null, isLoading: false });
    renderOverview(project);
    expect(screen.getByTestId('overview-book-link')).toBeInTheDocument();
    expect(screen.queryByTestId('overview-world-link')).toBeNull();
  });

  it('falls back to the book id when the title has not resolved yet', () => {
    backlinks.mockReturnValue({ bookTitle: null, worldId: null, worldName: null, isLoading: true });
    renderOverview(project);
    expect(screen.getByTestId('overview-book-link')).toHaveTextContent('b1');
  });
});

describe('OverviewSection edit affordance (KN — dead pen button fix)', () => {
  beforeEach(() => {
    backlinks.mockReturnValue({ bookTitle: 'Cradle', worldId: null, worldName: null, isLoading: false });
    updateProject.mockReset();
    createProject.mockReset();
  });

  it('the pen (onEdit) opens the project form modal in edit mode — no longer a no-op', () => {
    renderOverview(project);
    expect(screen.queryByTestId('stub-form-modal')).toBeNull();
    fireEvent.click(screen.getByTestId('stub-row-edit'));
    const modal = screen.getByTestId('stub-form-modal');
    expect(modal).toBeInTheDocument();
    expect(modal).toHaveTextContent('edit');
  });
});
