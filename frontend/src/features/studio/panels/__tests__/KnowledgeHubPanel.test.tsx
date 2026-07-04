// 14_kg_panels.md A2 — KnowledgeHubPanel: a launcher only (DOCK-8), reuses ProjectsBrowser
// AS-IS (DOCK-2). D-KG-HUB-EXTERNAL-OPEN: opening a project belonging to THIS studio's book
// opens the in-studio kg-overview panel directly; a different book's project still opens
// through the studio link resolver (DOCK-7, never navigate()) as an external new tab.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';
import type { Project } from '@/features/knowledge/types';

let mockProject: Partial<Project> = { project_id: 'proj-9', name: 'Proj' };

vi.mock('@/features/knowledge/components/ProjectsBrowser', () => ({
  ProjectsBrowser: ({ onOpen }: { onOpen: (p: Project) => void }) => (
    <button
      data-testid="open-proj-9"
      onClick={() => onOpen(mockProject as Project)}
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
    mockProject = { project_id: 'proj-9', name: 'Proj' };
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

  it('opening a DIFFERENT book\'s project goes through the studio link resolver, not navigate()', () => {
    mockProject = { project_id: 'proj-9', name: 'Proj', book_id: 'some-other-book' };
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    try {
      withHost('b1', <KnowledgeHubPanel {...dockProps()} />);
      fireEvent.click(screen.getByTestId('open-proj-9'));
      // A project belonging to a book OTHER than this studio's — no in-studio equivalent
      // (this studio IS one book), external new tab, never a route hop away from studio.
      expect(openSpy).toHaveBeenCalledWith(
        '/knowledge/projects/proj-9/overview',
        '_blank',
        'noopener,noreferrer',
      );
    } finally {
      openSpy.mockRestore();
    }
  });

  it('opening THIS book\'s own project opens the in-studio kg-overview panel, never a new tab', () => {
    mockProject = { project_id: 'proj-9', name: 'Proj', book_id: 'b1' };
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    try {
      withHost('b1', <KnowledgeHubPanel {...dockProps()} />);
      fireEvent.click(screen.getByTestId('open-proj-9'));
      expect(openSpy).not.toHaveBeenCalled();
    } finally {
      openSpy.mockRestore();
    }
  });
});
