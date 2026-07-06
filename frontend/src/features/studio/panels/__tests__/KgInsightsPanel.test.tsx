// 14_kg_panels.md Phase B — KgInsightsPanel: a thin, global-only (user-scoped) wrapper around
// MiningInsightsTab (K7 — no scoping prop). Stubs MiningInsightsTab (heavy: 4 useQuery sections)
// so this test stays about the panel's OWN wiring (DOCK-3/DOCK-5), mirroring KnowledgeHubPanel's
// test shape.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/features/knowledge/components/MiningInsightsTab', () => ({
  MiningInsightsTab: () => <div data-testid="mining-insights-tab-stub">insights</div>,
}));

import { KgInsightsPanel } from '../KgInsightsPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: React.ReactNode) {
  return render(<StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>);
}

describe('KgInsightsPanel', () => {
  beforeEach(() => {
    hostRef = null;
  });

  it('registers with the host as an openable studio tool tagged with the kg_ MCP prefix', () => {
    withHost('b1', <KgInsightsPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('kg-insights')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('kg-insights')!.commandId).toBe('studio.openPanel.kg-insights');
    expect(hostRef!.getRegisteredTool('kg-insights')!.mcpToolPrefixes).toEqual(['kg_']);
  });

  it('self-titles the dock tab on mount', () => {
    const props = dockProps();
    withHost('b1', <KgInsightsPanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('renders MiningInsightsTab directly, with no book/project scoping', () => {
    withHost('b1', <KgInsightsPanel {...dockProps()} />);
    expect(screen.getByTestId('mining-insights-tab-stub')).toBeInTheDocument();
  });
});
