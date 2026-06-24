import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

// ── Mocks ────────────────────────────────────────────────────────────────
// useProjects supplies the route-resolved project from cache (no new BE).
const useProjectsMock = vi.fn();
vi.mock('@/features/knowledge/hooks/useProjects', () => ({
  useProjects: () => useProjectsMock(),
}));

// Heavy scoped tabs are stubbed so this test stays a SHELL test. Each
// stub echoes the scopedProjectId it received so we can assert the route
// param is threaded down (not a select-box).
vi.mock('@/features/knowledge/components/EntitiesTab', () => ({
  EntitiesTab: ({ scopedProjectId }: { scopedProjectId?: string }) => (
    <div data-testid="entities-stub">entities:{scopedProjectId}</div>
  ),
}));
vi.mock('@/features/knowledge/components/TimelineTab', () => ({
  TimelineTab: ({ scopedProjectId }: { scopedProjectId?: string }) => (
    <div data-testid="timeline-stub">timeline:{scopedProjectId}</div>
  ),
}));
vi.mock('@/features/knowledge/components/RawDrawersTab', () => ({
  RawDrawersTab: ({ scopedProjectId }: { scopedProjectId?: string }) => (
    <div data-testid="evidence-stub">evidence:{scopedProjectId}</div>
  ),
}));
vi.mock('@/features/knowledge/components/MiningInsightsTab', () => ({
  MiningInsightsTab: () => <div data-testid="insights-stub" />,
}));
vi.mock('@/features/knowledge/components/shell/OverviewSection', () => ({
  OverviewSection: ({ onExploreGraph }: { onExploreGraph: () => void }) => (
    <button data-testid="overview-stub" onClick={onExploreGraph}>
      overview
    </button>
  ),
}));

import { ProjectDetailShell } from '../ProjectDetailShell';

const PROJECT = {
  project_id: 'p-1',
  name: 'Nine Realms',
  embedding_model: 'text-embed',
  rerank_model: null,
  extraction_enabled: true,
  book_id: null,
};

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/knowledge/projects/:projectId/:section"
          element={<ProjectDetailShell />}
        />
        <Route
          path="/knowledge/projects/:projectId"
          element={<div data-testid="bare-project" />}
        />
        <Route path="/knowledge/projects" element={<div data-testid="browser" />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ProjectDetailShell', () => {
  beforeEach(() => {
    useProjectsMock.mockReset();
    useProjectsMock.mockReturnValue({ items: [PROJECT], isLoading: false });
  });

  it('resolves the shell + project from the :projectId route param', () => {
    renderAt('/knowledge/projects/p-1/overview');
    expect(screen.getByTestId('project-detail-shell')).toBeInTheDocument();
    expect(screen.getByTestId('shell-project-name')).toHaveTextContent(
      'Nine Realms',
    );
  });

  it('derives the active sub-tab from :section and threads projectId into the scoped Entities tab (no select)', () => {
    renderAt('/knowledge/projects/p-1/entities');
    expect(screen.getByTestId('shell-tab-entities')).toHaveAttribute(
      'aria-selected',
      'true',
    );
    // Scope comes from the ROUTE, not a dropdown.
    expect(screen.getByTestId('entities-stub')).toHaveTextContent(
      'entities:p-1',
    );
  });

  it('Evidence sub-tab renders RawDrawers scoped to the route project', () => {
    renderAt('/knowledge/projects/p-1/evidence');
    expect(screen.getByTestId('evidence-stub')).toHaveTextContent(
      'evidence:p-1',
    );
  });

  it('Explore-graph CTA navigates into the shell entities section', () => {
    renderAt('/knowledge/projects/p-1/overview');
    fireEvent.click(screen.getByTestId('overview-stub'));
    // After the deep-link nav the entities section is active + scoped.
    expect(screen.getByTestId('entities-stub')).toHaveTextContent(
      'entities:p-1',
    );
  });

  it('canonicalizes an unknown section to overview', () => {
    renderAt('/knowledge/projects/p-1/bogus');
    expect(screen.getByTestId('overview-stub')).toBeInTheDocument();
  });
});
