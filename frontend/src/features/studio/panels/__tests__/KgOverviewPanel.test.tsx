// 14_kg_panels.md Phase B — KgOverviewPanel: resolves the book's KG project via
// useBookKnowledgeProject (A1/K5), self-titles, registers with the kg_ MCP prefix, shows
// loading/empty states, and routes explore-graph + the book/world backlinks through the host
// / studio link resolver instead of navigate() (DOCK-7). Stubs OverviewSection + the hook so
// this test stays about the panel's OWN wiring, not OverviewSection's internals (separately
// tested in OverviewSection.backlinks.test.tsx).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';
import type { Project } from '@/features/knowledge/types';

const useBookKnowledgeProject = vi.fn();
vi.mock('@/features/knowledge/hooks/useBookKnowledgeProject', () => ({
  useBookKnowledgeProject: (bookId: string) => useBookKnowledgeProject(bookId),
}));

// S-05 — the panel now reads a triage count for the deep-link nudge; stub it so
// this stays a panel-wiring test (the queue itself is tested in TriageQueue.test).
vi.mock('@/features/knowledge/hooks/useTriageQueue', () => ({
  useTriageQueue: () => ({ groups: [], isLoading: false, error: null }),
}));

// KgNoProjectState (D-KG-NO-CREATE-CTA) owns the real empty-state copy + create-project
// flow now, tested on its own in KgNoProjectState.test.tsx (it needs auth/react-query
// providers this panel-wiring test doesn't otherwise set up). Stubbed here so this stays
// a test of the panel's OWN loading/empty/loaded branch selection.
vi.mock('@/features/knowledge/components/shell/KgNoProjectState', () => ({
  KgNoProjectState: ({ testId }: { testId: string }) => <div data-testid={testId}>stub-no-project</div>,
}));

vi.mock('@/features/knowledge/components/shell/OverviewSection', () => ({
  OverviewSection: ({
    project,
    onExploreGraph,
    onOpenBook,
    onOpenWorld,
  }: {
    project: Project | null;
    onExploreGraph: () => void;
    onOpenBook: (bookId: string) => void;
    onOpenWorld: (worldId: string) => void;
  }) => (
    <div data-testid="stub-overview-section" data-project={project?.project_id ?? ''}>
      <button onClick={onExploreGraph}>explore-graph</button>
      <button onClick={() => onOpenBook('bk1')}>open-book</button>
      <button onClick={() => onOpenWorld('w1')}>open-world</button>
    </div>
  ),
}));

const followStudioLink = vi.fn();
vi.mock('../../host/studioLinks', () => ({
  followStudioLink: (...args: unknown[]) => followStudioLink(...args),
}));

import { KgOverviewPanel } from '../KgOverviewPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  return render(<StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>);
}

beforeEach(() => {
  hostRef = null;
  useBookKnowledgeProject.mockReset();
  followStudioLink.mockReset();
});

describe('KgOverviewPanel', () => {
  it('registers with the host as an openable studio tool tagged with the kg_ MCP prefix', () => {
    useBookKnowledgeProject.mockReturnValue({ project: null, projectId: null, isLoading: true });
    withHost('b1', <KgOverviewPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('kg-overview')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('kg-overview')!.commandId).toBe('studio.openPanel.kg-overview');
    expect(hostRef!.getRegisteredTool('kg-overview')!.mcpToolPrefixes).toEqual(['kg_']);
  });

  it('self-titles the dock tab on mount', () => {
    useBookKnowledgeProject.mockReturnValue({ project: null, projectId: null, isLoading: true });
    const props = dockProps();
    withHost('b1', <KgOverviewPanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('resolves the project via useBookKnowledgeProject scoped to the host book id', () => {
    useBookKnowledgeProject.mockReturnValue({ project: null, projectId: null, isLoading: true });
    withHost('the-book', <KgOverviewPanel {...dockProps()} />);
    expect(useBookKnowledgeProject).toHaveBeenCalledWith('the-book');
  });

  it('shows a loading state while the project is resolving', () => {
    useBookKnowledgeProject.mockReturnValue({ project: null, projectId: null, isLoading: true });
    withHost('b1', <KgOverviewPanel {...dockProps()} />);
    expect(screen.getByTestId('kg-overview-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('stub-overview-section')).toBeNull();
  });

  it('shows an empty state when the book has no linked KG project', () => {
    useBookKnowledgeProject.mockReturnValue({ project: null, projectId: null, isLoading: false });
    withHost('b1', <KgOverviewPanel {...dockProps()} />);
    expect(screen.getByTestId('kg-overview-no-project')).toBeInTheDocument();
    expect(screen.queryByTestId('stub-overview-section')).toBeNull();
  });

  it('renders OverviewSection once a project resolves', () => {
    const project = { project_id: 'proj-1', book_id: 'b1' } as unknown as Project;
    useBookKnowledgeProject.mockReturnValue({ project, projectId: 'proj-1', isLoading: false });
    withHost('b1', <KgOverviewPanel {...dockProps()} />);
    expect(screen.getByTestId('stub-overview-section')).toHaveAttribute('data-project', 'proj-1');
  });

  it('explore-graph opens the kg-entities panel scoped to this project via the host, not navigate()', () => {
    const project = { project_id: 'proj-1', book_id: 'b1' } as unknown as Project;
    useBookKnowledgeProject.mockReturnValue({ project, projectId: 'proj-1', isLoading: false });
    withHost('b1', <KgOverviewPanel {...dockProps()} />);
    const openPanelSpy = vi.spyOn(hostRef!, 'openPanel');
    fireEvent.click(screen.getByText('explore-graph'));
    expect(openPanelSpy).toHaveBeenCalledWith('kg-entities', { params: { scopedProjectId: 'proj-1' } });
  });

  it('the book/world backlinks go through the studio link resolver, not navigate()', () => {
    const project = { project_id: 'proj-1', book_id: 'b1' } as unknown as Project;
    useBookKnowledgeProject.mockReturnValue({ project, projectId: 'proj-1', isLoading: false });
    withHost('b1', <KgOverviewPanel {...dockProps()} />);

    fireEvent.click(screen.getByText('open-book'));
    expect(followStudioLink).toHaveBeenCalledWith('/books/bk1', hostRef, { bookId: 'b1' });

    fireEvent.click(screen.getByText('open-world'));
    expect(followStudioLink).toHaveBeenCalledWith('/worlds/w1', hostRef, { bookId: 'b1' });
  });
});
