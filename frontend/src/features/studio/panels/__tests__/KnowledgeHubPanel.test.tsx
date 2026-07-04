// 14_kg_panels.md A2 — KnowledgeHubPanel: a launcher only (DOCK-8), reuses ProjectsBrowser
// AS-IS (DOCK-2) and opens a project through the studio link resolver (DOCK-7) instead of
// navigate(). Stubs ProjectsBrowser so this test stays about the panel's OWN wiring.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';
import type { Project } from '@/features/knowledge/types';

vi.mock('@/features/knowledge/components/ProjectsBrowser', () => ({
  ProjectsBrowser: ({ onOpen }: { onOpen: (p: Project) => void }) => (
    <button
      data-testid="open-proj-9"
      onClick={() => onOpen({ project_id: 'proj-9', name: 'Proj' } as Project)}
    >
      open
    </button>
  ),
}));

import { KnowledgeHubPanel } from '../KnowledgeHubPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  return render(<StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>);
}

describe('KnowledgeHubPanel', () => {
  beforeEach(() => {
    hostRef = null;
  });

  it('registers with the host as an openable studio tool tagged with the kg_ MCP prefix', () => {
    withHost('b1', <KnowledgeHubPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('knowledge')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('knowledge')!.commandId).toBe('studio.openPanel.knowledge');
    expect(hostRef!.getRegisteredTool('knowledge')!.mcpToolPrefixes).toEqual(['kg_']);
  });

  it('self-titles the dock tab on mount', () => {
    const props = dockProps();
    withHost('b1', <KnowledgeHubPanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('opening a project goes through the studio link resolver, not navigate()', () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    try {
      withHost('b1', <KnowledgeHubPanel {...dockProps()} />);
      fireEvent.click(screen.getByTestId('open-proj-9'));
      // No kg-overview panel exists yet (Phase B) — F3 falls through to "external", a new
      // tab on the classic route, never a silent no-op and never a route hop away from studio.
      expect(openSpy).toHaveBeenCalledWith(
        '/knowledge/projects/proj-9/overview',
        '_blank',
        'noopener,noreferrer',
      );
    } finally {
      openSpy.mockRestore();
    }
  });
});
