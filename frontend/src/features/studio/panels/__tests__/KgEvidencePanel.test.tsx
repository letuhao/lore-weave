// 14_kg_panels.md Phase B — KgEvidencePanel: thin wrapper over RawDrawersTab (K4 shared
// capability, optional scope). Stubs RawDrawersTab so this test stays about the panel's OWN
// wiring (registration + self-title + scopedProjectId pass-through), not the tab's internals.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

const rawDrawersTabSpy = vi.fn();

vi.mock('@/features/knowledge/components/RawDrawersTab', () => ({
  RawDrawersTab: (props: { scopedProjectId?: string }) => {
    rawDrawersTabSpy(props);
    return <div data-testid="raw-drawers-tab-stub">{props.scopedProjectId ?? 'GLOBAL'}</div>;
  },
}));

import { KgEvidencePanel } from '../KgEvidencePanel';

let hostRef: StudioHost | null = null;
function HostProbe() {
  hostRef = useStudioHost();
  return null;
}

function dockProps(params?: Record<string, unknown>) {
  return { api: { setTitle: vi.fn() }, params } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, props: IDockviewPanelProps) {
  return render(
    <StudioHostProvider bookId={bookId}>
      <HostProbe />
      <KgEvidencePanel {...props} />
    </StudioHostProvider>,
  );
}

describe('KgEvidencePanel', () => {
  beforeEach(() => {
    hostRef = null;
    rawDrawersTabSpy.mockClear();
  });

  it('registers with the host as an openable studio tool tagged with the kg_ MCP prefix', () => {
    withHost('b1', dockProps());
    expect(hostRef!.getRegisteredTool('kg-evidence')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('kg-evidence')!.commandId).toBe(
      'studio.openPanel.kg-evidence',
    );
    expect(hostRef!.getRegisteredTool('kg-evidence')!.mcpToolPrefixes).toEqual(['kg_']);
  });

  it('self-titles the dock tab on mount', () => {
    const props = dockProps();
    withHost('b1', props);
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('passes scopedProjectId through to RawDrawersTab when present (book-scoped mode)', () => {
    withHost('b1', dockProps({ scopedProjectId: 'proj-9' }));
    expect(screen.getByTestId('raw-drawers-tab-stub').textContent).toBe('proj-9');
    expect(rawDrawersTabSpy).toHaveBeenCalledWith(
      expect.objectContaining({ scopedProjectId: 'proj-9' }),
    );
  });

  it('renders RawDrawersTab with scopedProjectId undefined when absent (global mode)', () => {
    withHost('b1', dockProps());
    expect(screen.getByTestId('raw-drawers-tab-stub').textContent).toBe('GLOBAL');
    expect(rawDrawersTabSpy).toHaveBeenCalledWith(
      expect.objectContaining({ scopedProjectId: undefined }),
    );
  });
});
