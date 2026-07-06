// 14_kg_panels.md Phase B — KgGapReportPanel: thin wrapper around GapReportTab (DOCK-2), book-
// scoped ONLY via useBookKnowledgeProject (DOCK-7 — no route param). Stubs both the project
// hook and GapReportTab so this test stays about the panel's OWN wiring, mirroring
// KnowledgeHubPanel.test.tsx's stub pattern.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

const useBookKnowledgeProjectMock = vi.fn();

vi.mock('@/features/knowledge/hooks/useBookKnowledgeProject', () => ({
  useBookKnowledgeProject: (bookId: string) => useBookKnowledgeProjectMock(bookId),
}));

vi.mock('@/features/knowledge/components/GapReportTab', () => ({
  GapReportTab: ({ scopedProjectId }: { scopedProjectId: string }) => (
    <div data-testid="stub-gap-report-tab">{scopedProjectId}</div>
  ),
}));

// KgNoProjectState (D-KG-NO-CREATE-CTA) owns the real empty-state + create-project flow,
// tested on its own in KgNoProjectState.test.tsx. Stubbed here so this stays a test of the
// panel's own loading/empty/loaded branch selection.
vi.mock('@/features/knowledge/components/shell/KgNoProjectState', () => ({
  KgNoProjectState: ({ testId }: { testId: string }) => <div data-testid={testId}>stub-no-project</div>,
}));

import { KgGapReportPanel } from '../KgGapReportPanel';

let hostRef: StudioHost | null = null;
function HostProbe() {
  hostRef = useStudioHost();
  return null;
}

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  return render(
    <StudioHostProvider bookId={bookId}>
      <HostProbe />
      {ui}
    </StudioHostProvider>,
  );
}

describe('KgGapReportPanel', () => {
  beforeEach(() => {
    hostRef = null;
    useBookKnowledgeProjectMock.mockReset();
  });

  it('registers with the host tagged with the kg_ MCP prefix', () => {
    useBookKnowledgeProjectMock.mockReturnValue({
      project: null,
      projectId: null,
      isLoading: true,
    });
    withHost('book-1', <KgGapReportPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('kg-gap')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('kg-gap')!.commandId).toBe('studio.openPanel.kg-gap');
    expect(hostRef!.getRegisteredTool('kg-gap')!.mcpToolPrefixes).toEqual(['kg_']);
  });

  it('self-titles the dock tab on mount', () => {
    useBookKnowledgeProjectMock.mockReturnValue({
      project: null,
      projectId: null,
      isLoading: true,
    });
    const props = dockProps();
    withHost('book-1', <KgGapReportPanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('shows a loading state while the book project resolves', () => {
    useBookKnowledgeProjectMock.mockReturnValue({
      project: null,
      projectId: null,
      isLoading: true,
    });
    withHost('book-1', <KgGapReportPanel {...dockProps()} />);
    expect(screen.getByTestId('kg-gap-panel-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('stub-gap-report-tab')).not.toBeInTheDocument();
  });

  it('shows an empty state when the book has no linked KG project', () => {
    useBookKnowledgeProjectMock.mockReturnValue({
      project: null,
      projectId: null,
      isLoading: false,
    });
    withHost('book-1', <KgGapReportPanel {...dockProps()} />);
    expect(screen.getByTestId('kg-gap-no-project')).toBeInTheDocument();
    expect(screen.queryByTestId('stub-gap-report-tab')).not.toBeInTheDocument();
  });

  it('renders GapReportTab with the resolved projectId when a project is linked', () => {
    useBookKnowledgeProjectMock.mockReturnValue({
      project: { project_id: 'proj-42', name: 'Proj 42' },
      projectId: 'proj-42',
      isLoading: false,
    });
    withHost('book-1', <KgGapReportPanel {...dockProps()} />);
    expect(useBookKnowledgeProjectMock).toHaveBeenCalledWith('book-1');
    expect(screen.getByTestId('studio-kg-gap-panel')).toBeInTheDocument();
    expect(screen.getByTestId('stub-gap-report-tab')).toHaveTextContent('proj-42');
  });
});
