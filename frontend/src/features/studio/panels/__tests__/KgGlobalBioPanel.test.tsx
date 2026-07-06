// 14_kg_panels.md Phase B — KgGlobalBioPanel: user-scoped launcher for the global bio editor
// (DOCK-1/3/5). GlobalBioTab owns its own data layer (useSummaries) and dialogs; this test
// stubs it out so the assertions stay about the panel's OWN wiring (registration + title),
// same shape as KnowledgeHubPanel.test.tsx stubbing ProjectsBrowser.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/features/knowledge/components/GlobalBioTab', () => ({
  GlobalBioTab: () => <div data-testid="global-bio-tab-stub">global bio</div>,
}));

import { KgGlobalBioPanel } from '../KgGlobalBioPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  return render(<StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>);
}

describe('KgGlobalBioPanel', () => {
  beforeEach(() => {
    hostRef = null;
  });

  it('registers with the host as an openable studio tool tagged with the kg_ MCP prefix', () => {
    withHost('b1', <KgGlobalBioPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('kg-bio')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('kg-bio')!.commandId).toBe('studio.openPanel.kg-bio');
    expect(hostRef!.getRegisteredTool('kg-bio')!.mcpToolPrefixes).toEqual(['kg_']);
  });

  it('self-titles the dock tab on mount', () => {
    const props = dockProps();
    withHost('b1', <KgGlobalBioPanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('renders GlobalBioTab', () => {
    withHost('b1', <KgGlobalBioPanel {...dockProps()} />);
    expect(screen.getByTestId('global-bio-tab-stub')).toBeInTheDocument();
  });
});
