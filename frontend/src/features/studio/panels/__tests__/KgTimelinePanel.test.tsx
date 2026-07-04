// 14_kg_panels.md Phase B — KgTimelinePanel: thin wrapper over `TimelineTab` (DOCK-2), K4 shared
// capability with optional scope. Stubs TimelineTab so this test stays about the panel's OWN
// wiring (registration + self-title + params passthrough), not TimelineTab's internals.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/features/knowledge/components/TimelineTab', () => ({
  TimelineTab: ({ scopedProjectId }: { scopedProjectId?: string }) => (
    <div data-testid="timeline-tab-stub">{scopedProjectId ?? 'GLOBAL'}</div>
  ),
}));

import { KgTimelinePanel } from '../KgTimelinePanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps(params?: Record<string, unknown>) {
  return { api: { setTitle: vi.fn() }, params } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  return render(<StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>);
}

describe('KgTimelinePanel', () => {
  beforeEach(() => {
    hostRef = null;
  });

  it('registers with the host as an openable studio tool tagged with the kg_ MCP prefix', () => {
    withHost('b1', <KgTimelinePanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('kg-timeline')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('kg-timeline')!.commandId).toBe(
      'studio.openPanel.kg-timeline',
    );
    expect(hostRef!.getRegisteredTool('kg-timeline')!.mcpToolPrefixes).toEqual(['kg_']);
  });

  it('self-titles the dock tab on mount', () => {
    const props = dockProps();
    withHost('b1', <KgTimelinePanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('passes params.scopedProjectId through to TimelineTab when present (book-scoped mode)', () => {
    withHost('b1', <KgTimelinePanel {...dockProps({ scopedProjectId: 'proj-42' })} />);
    expect(screen.getByTestId('timeline-tab-stub')).toHaveTextContent('proj-42');
  });

  it('renders TimelineTab with scopedProjectId undefined (global mode) when the param is absent', () => {
    withHost('b1', <KgTimelinePanel {...dockProps()} />);
    expect(screen.getByTestId('timeline-tab-stub')).toHaveTextContent('GLOBAL');
  });
});
