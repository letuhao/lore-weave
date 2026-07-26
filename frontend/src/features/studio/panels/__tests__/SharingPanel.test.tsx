// SharingPanel — thin wrapper reusing the classic SharingTab AS-IS (DOCK-2), resolving book_id
// from the studio host instead of a route param (DOCK-7). Stubs CollaboratorsPanel (its own
// invite/role-change/remove wiring is covered by useCollaborators/CollaboratorsPanel's own
// tests) and the booksApi sharing calls so this test stays about THIS panel's own wiring —
// registration, self-titling, book_id resolution — plus a real exercise of the visibility-change
// capability SharingTab renders directly (not extracted into a heavy sub-component to stub).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const getSharing = vi.fn();
const patchSharing = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: {
    getSharing: (...a: unknown[]) => getSharing(...a),
    patchSharing: (...a: unknown[]) => patchSharing(...a),
  },
}));

vi.mock('@/features/books/components/CollaboratorsPanel', () => ({
  CollaboratorsPanel: ({ bookId }: { bookId: string }) => (
    <div data-testid="stub-collaborators-panel" data-book={bookId} />
  ),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { SharingPanel } from '../SharingPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  return render(
    <StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>,
  );
}

beforeEach(() => {
  hostRef = null;
  getSharing.mockReset();
  patchSharing.mockReset();
  getSharing.mockResolvedValue({ visibility: 'private', unlisted_access_token: null });
  patchSharing.mockResolvedValue({ visibility: 'public', unlisted_access_token: null });
});

describe('SharingPanel', () => {
  it('resolves book_id from the host, loads sharing data for that book, and renders the collaborators sub-panel', async () => {
    withHost('b1', <SharingPanel {...dockProps()} />);
    await waitFor(() => expect(getSharing).toHaveBeenCalledWith('tok', 'b1'));
    const stub = await screen.findByTestId('stub-collaborators-panel');
    expect(stub.getAttribute('data-book')).toBe('b1');
  });

  it('self-titles the dock tab on mount', () => {
    const props = dockProps();
    withHost('b1', <SharingPanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('registers with the host as an openable studio tool, with no MCP tool prefixes (sharing has no MCP tools)', () => {
    withHost('b1', <SharingPanel {...dockProps()} />);
    const reg = hostRef!.getRegisteredTool('sharing');
    expect(reg).not.toBeNull();
    expect(reg!.commandId).toBe('studio.openPanel.sharing');
    expect(reg!.mcpToolPrefixes).toBeUndefined();
  });

  it('wires the real visibility-change capability through to booksApi.patchSharing for the host-resolved book', async () => {
    withHost('b1', <SharingPanel {...dockProps()} />);
    await waitFor(() => expect(getSharing).toHaveBeenCalled());
    fireEvent.click(await screen.findByText('sharing.options.public.label'));
    await waitFor(() => expect(patchSharing).toHaveBeenCalledWith('tok', 'b1', { visibility: 'public' }));
  });
});
