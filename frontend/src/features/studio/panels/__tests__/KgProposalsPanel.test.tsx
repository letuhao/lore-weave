// 14_kg_panels.md Phase B — KgProposalsPanel: book-scoped (host.bookId feeds
// ProposalsInboxTab's bookId prop directly), reuses ProposalsInboxTab AS-IS
// (DOCK-2) and wires its onOpenRow through the studio link resolver (DOCK-7)
// instead of the raw <Link> it used to render. Stubs ProposalsInboxTab so this
// test stays about the panel's OWN wiring (host.bookId passthrough + F3 wiring).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';
import type { ProposalInboxRow } from '@/features/knowledge/lib/proposalsInbox';

let lastProps: { bookId: string | null; onOpenRow: (row: ProposalInboxRow) => void } | null = null;

vi.mock('@/features/knowledge/components/ProposalsInboxTab', () => ({
  ProposalsInboxTab: (props: { bookId: string | null; onOpenRow: (row: ProposalInboxRow) => void }) => {
    lastProps = props;
    return (
      <button
        data-testid="open-row-e1"
        onClick={() =>
          props.onOpenRow({
            id: 'e1',
            origin: 'glossary',
            title: 'Entity 1',
            deepLinkUrl: '/books/b1/glossary',
          })
        }
      >
        open
      </button>
    );
  },
}));

import { KgProposalsPanel } from '../KgProposalsPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  return render(<StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>);
}

describe('KgProposalsPanel', () => {
  beforeEach(() => {
    hostRef = null;
    lastProps = null;
  });

  it('registers with the host as an openable studio tool tagged with the kg_ MCP prefix', () => {
    withHost('b1', <KgProposalsPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('kg-proposals')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('kg-proposals')!.commandId).toBe('studio.openPanel.kg-proposals');
    expect(hostRef!.getRegisteredTool('kg-proposals')!.mcpToolPrefixes).toEqual(['kg_']);
  });

  it('self-titles the dock tab on mount', () => {
    const props = dockProps();
    withHost('b1', <KgProposalsPanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('renders ProposalsInboxTab with host.bookId as its bookId prop', () => {
    withHost('book-42', <KgProposalsPanel {...dockProps()} />);
    expect(lastProps!.bookId).toBe('book-42');
  });

  it('opening a proposal row goes through the studio link resolver, not navigate()', () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    try {
      withHost('b1', <KgProposalsPanel {...dockProps()} />);
      fireEvent.click(screen.getByTestId('open-row-e1'));
      // `/books/b1/glossary` is an unmapped app path in studioLinks.ts today — F3
      // falls through to "external", a new tab on the classic route, never a
      // silent no-op and never a route hop away from the studio.
      expect(openSpy).toHaveBeenCalledWith(
        '/books/b1/glossary',
        '_blank',
        'noopener,noreferrer',
      );
    } finally {
      openSpy.mockRestore();
    }
  });
});
