// 14_kg_panels.md Phase B — KgGraphPanel: thin wrapper around ProjectGraphView (DOCK-2),
// resolving the book's knowledge project via useBookKnowledgeProject (A1/K5). Stubs both
// useBookKnowledgeProject and ProjectGraphView (a heavy SVG canvas) so this test stays about
// the panel's OWN wiring — registration, self-title, loading/empty states, and prop-passing.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

const useBookKnowledgeProjectMock = vi.fn();
vi.mock('@/features/knowledge/hooks/useBookKnowledgeProject', () => ({
  useBookKnowledgeProject: (bookId: string) => useBookKnowledgeProjectMock(bookId),
}));

vi.mock('@/features/knowledge/components/ProjectGraphView', () => ({
  ProjectGraphView: ({ projectId, bookId }: { projectId: string | null; bookId: string | null }) => (
    <div data-testid="project-graph-view-stub" data-project-id={projectId ?? ''} data-book-id={bookId ?? ''} />
  ),
}));

import { KgGraphPanel } from '../KgGraphPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: React.ReactNode) {
  return render(<StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>);
}

describe('KgGraphPanel', () => {
  beforeEach(() => {
    hostRef = null;
    useBookKnowledgeProjectMock.mockReset();
  });

  it('registers with the host as an openable studio tool tagged with the kg_ MCP prefix', () => {
    useBookKnowledgeProjectMock.mockReturnValue({ project: null, projectId: null, isLoading: true });
    withHost('b1', <KgGraphPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('kg-graph')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('kg-graph')!.commandId).toBe('studio.openPanel.kg-graph');
    expect(hostRef!.getRegisteredTool('kg-graph')!.mcpToolPrefixes).toEqual(['kg_']);
  });

  it('self-titles the dock tab on mount', () => {
    useBookKnowledgeProjectMock.mockReturnValue({ project: null, projectId: null, isLoading: true });
    const props = dockProps();
    withHost('b1', <KgGraphPanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('shows a loading state while the book knowledge project resolves', () => {
    useBookKnowledgeProjectMock.mockReturnValue({ project: null, projectId: null, isLoading: true });
    withHost('b1', <KgGraphPanel {...dockProps()} />);
    expect(screen.getByTestId('kg-graph-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('project-graph-view-stub')).not.toBeInTheDocument();
  });

  it('shows the no-project empty state when the book has no linked knowledge project', () => {
    useBookKnowledgeProjectMock.mockReturnValue({ project: null, projectId: null, isLoading: false });
    withHost('b1', <KgGraphPanel {...dockProps()} />);
    expect(screen.getByTestId('kg-ontology-no-project')).toBeInTheDocument();
    expect(screen.queryByTestId('project-graph-view-stub')).not.toBeInTheDocument();
  });

  it('renders ProjectGraphView with the resolved projectId and the host bookId once the project exists', () => {
    useBookKnowledgeProjectMock.mockReturnValue({
      project: { project_id: 'proj-9', book_id: 'b1' },
      projectId: 'proj-9',
      isLoading: false,
    });
    withHost('b1', <KgGraphPanel {...dockProps()} />);
    const stub = screen.getByTestId('project-graph-view-stub');
    expect(stub).toHaveAttribute('data-project-id', 'proj-9');
    expect(stub).toHaveAttribute('data-book-id', 'b1');
  });

  it('resolves the project via the host bookId (doubles as ProjectGraphView bookId prop)', () => {
    useBookKnowledgeProjectMock.mockReturnValue({ project: null, projectId: null, isLoading: true });
    withHost('book-42', <KgGraphPanel {...dockProps()} />);
    expect(useBookKnowledgeProjectMock).toHaveBeenCalledWith('book-42');
  });
});
