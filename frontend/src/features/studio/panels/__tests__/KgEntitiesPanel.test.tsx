// 14_kg_panels.md Phase B — KgEntitiesPanel: thin wrapper over `EntitiesTab` (DOCK-2), K4 shared
// capability with optional scope. Stubs EntitiesTab so this test stays about the panel's OWN
// wiring (registration + self-title + params passthrough), not EntitiesTab's internals.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/features/knowledge/components/EntitiesTab', () => ({
  EntitiesTab: ({ scopedProjectId }: { scopedProjectId?: string }) => (
    <div data-testid="entities-tab-stub">{scopedProjectId ?? 'GLOBAL'}</div>
  ),
}));

import { KgEntitiesPanel } from '../KgEntitiesPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps(params?: Record<string, unknown>) {
  return { api: { setTitle: vi.fn() }, params } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  return render(<StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>);
}

describe('KgEntitiesPanel', () => {
  beforeEach(() => {
    hostRef = null;
  });

  it('registers with the host as an openable studio tool tagged with the kg_ MCP prefix', () => {
    withHost('b1', <KgEntitiesPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('kg-entities')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('kg-entities')!.commandId).toBe(
      'studio.openPanel.kg-entities',
    );
    expect(hostRef!.getRegisteredTool('kg-entities')!.mcpToolPrefixes).toEqual(['kg_']);
  });

  it('self-titles the dock tab on mount', () => {
    const props = dockProps();
    withHost('b1', <KgEntitiesPanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('passes params.scopedProjectId through to EntitiesTab when present (book-scoped mode)', () => {
    withHost('b1', <KgEntitiesPanel {...dockProps({ scopedProjectId: 'proj-42' })} />);
    expect(screen.getByTestId('entities-tab-stub')).toHaveTextContent('proj-42');
  });

  it('renders EntitiesTab with scopedProjectId undefined (global mode) when the param is absent', () => {
    withHost('b1', <KgEntitiesPanel {...dockProps()} />);
    expect(screen.getByTestId('entities-tab-stub')).toHaveTextContent('GLOBAL');
  });
});
