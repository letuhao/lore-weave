// 14_kg_panels.md Phase B — KgPrivacyPanel: thin wrapper (DOCK-2) over PrivacyTab, a
// user-scoped GDPR export/delete surface (K1 — same tenancy tier as Settings/Usage).
// PrivacyTab itself needs auth + react-query context to render for real (it calls
// useAuth/useQueryClient), which is orthogonal to what THIS panel is responsible for —
// stub it so this test stays about the panel's own registration/title/render wiring,
// mirroring KnowledgeHubPanel.test.tsx's ProjectsBrowser stub.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/features/knowledge/components/PrivacyTab', () => ({
  PrivacyTab: () => <div data-testid="privacy-tab-stub">privacy tab</div>,
}));

import { KgPrivacyPanel } from '../KgPrivacyPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  return render(<StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>);
}

describe('KgPrivacyPanel', () => {
  beforeEach(() => {
    hostRef = null;
  });

  it('registers with the host as an openable studio tool tagged with the kg_ MCP prefix', () => {
    withHost('b1', <KgPrivacyPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('kg-privacy')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('kg-privacy')!.commandId).toBe('studio.openPanel.kg-privacy');
    expect(hostRef!.getRegisteredTool('kg-privacy')!.mcpToolPrefixes).toEqual(['kg_']);
  });

  it('self-titles the dock tab on mount', () => {
    const props = dockProps();
    withHost('b1', <KgPrivacyPanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('renders PrivacyTab', () => {
    withHost('b1', <KgPrivacyPanel {...dockProps()} />);
    expect(screen.getByTestId('privacy-tab-stub')).toBeInTheDocument();
  });
});
