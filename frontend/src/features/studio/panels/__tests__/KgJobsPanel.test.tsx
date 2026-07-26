// 14_kg_panels.md Phase B — KgJobsPanel: thin wrapper (DOCK-2) around
// `ExtractionJobsTab`, user-scoped (cross-project extraction jobs), no book/project
// scoping. Stubs `ExtractionJobsTab` since it pulls in polling hooks/dialogs unrelated
// to this panel's own wiring (registration/title/render), same rationale as
// `KnowledgeHubPanel.test.tsx` stubbing `ProjectsBrowser`.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';
import type { IDockviewPanelProps } from 'dockview-react';

vi.mock('@/features/knowledge/components/ExtractionJobsTab', () => ({
  ExtractionJobsTab: () => <div data-testid="extraction-jobs-tab-stub" />,
}));

import { KgJobsPanel } from '../KgJobsPanel';

let hostRef: StudioHost | null = null;
function HostProbe() {
  hostRef = useStudioHost();
  return null;
}

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: React.ReactNode) {
  return render(
    <StudioHostProvider bookId={bookId}>
      <HostProbe />
      {ui}
    </StudioHostProvider>,
  );
}

describe('KgJobsPanel', () => {
  beforeEach(() => {
    hostRef = null;
  });

  it('registers with the host as an openable studio tool tagged with the kg_ MCP prefix', () => {
    withHost('b1', <KgJobsPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('kg-jobs')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('kg-jobs')!.commandId).toBe('studio.openPanel.kg-jobs');
    expect(hostRef!.getRegisteredTool('kg-jobs')!.mcpToolPrefixes).toEqual(['kg_']);
  });

  it('self-titles the dock tab on mount', () => {
    const props = dockProps();
    withHost('b1', <KgJobsPanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('renders ExtractionJobsTab', () => {
    withHost('b1', <KgJobsPanel {...dockProps()} />);
    expect(screen.getByTestId('extraction-jobs-tab-stub')).toBeInTheDocument();
  });
});
