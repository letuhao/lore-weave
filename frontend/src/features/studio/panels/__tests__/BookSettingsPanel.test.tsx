// BookSettingsPanel — thin wrapper reusing the classic SettingsTab AS-IS (DOCK-2), resolving
// bookId from the studio host instead of a route param (DOCK-7). review-impl fix: the first
// version of this panel forked SettingsTab's ~400 lines of form/save/cover/genre logic instead
// of reusing it; this rewrite mirrors TranslationPanel/SharingPanel's thin-wrapper test shape —
// stub SettingsTab (its own form/save/cover/genre logic is covered by SettingsTab's own tests)
// so this test stays about THIS panel's own wiring: registration, self-titling, book resolution
// (react-query fetch + loading state), refetch wiring, and the onOpenWorld → followStudioLink
// DOCK-7 seam.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const getBook = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: {
    getBook: (...a: unknown[]) => getBook(...a),
  },
}));

vi.mock('@/pages/book-tabs/SettingsTab', () => ({
  SettingsTab: ({
    bookId,
    book,
    onReload,
    onOpenWorld,
  }: {
    bookId: string;
    book: { title: string };
    onReload: () => void;
    onOpenWorld?: (worldId: string) => void;
  }) => (
    <div data-testid="stub-settings-tab" data-book={bookId} data-title={book.title}>
      <button onClick={onReload}>reload</button>
      <button onClick={() => onOpenWorld?.('w1')}>open-world</button>
    </div>
  ),
}));

const followStudioLink = vi.fn();
vi.mock('../../host/studioLinks', () => ({
  followStudioLink: (...args: unknown[]) => followStudioLink(...args),
}));

import { BookSettingsPanel } from '../BookSettingsPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  hostRef = null;
  getBook.mockReset();
  followStudioLink.mockReset();
});

describe('BookSettingsPanel', () => {
  it('shows a loading state while the book resolves', () => {
    getBook.mockReturnValue(new Promise(() => {})); // never resolves
    withHost('b1', <BookSettingsPanel {...dockProps()} />);
    expect(screen.getByTestId('studio-book-settings-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('stub-settings-tab')).toBeNull();
  });

  it('resolves the book via react-query scoped to the host bookId and renders SettingsTab', async () => {
    getBook.mockResolvedValue({ title: 'My Book' });
    withHost('b1', <BookSettingsPanel {...dockProps()} />);
    await waitFor(() => expect(screen.getByTestId('stub-settings-tab')).toBeInTheDocument());
    expect(getBook).toHaveBeenCalledWith('tok', 'b1');
    const stub = screen.getByTestId('stub-settings-tab');
    expect(stub.getAttribute('data-book')).toBe('b1');
    expect(stub.getAttribute('data-title')).toBe('My Book');
  });

  it('self-titles the dock tab on mount', async () => {
    getBook.mockResolvedValue({ title: 'My Book' });
    const props = dockProps();
    withHost('b1', <BookSettingsPanel {...props} />);
    await waitFor(() => expect(props.api.setTitle).toHaveBeenCalled());
  });

  it('registers with the host as an openable studio tool, with no MCP tool prefixes', async () => {
    getBook.mockResolvedValue({ title: 'My Book' });
    withHost('b1', <BookSettingsPanel {...dockProps()} />);
    await waitFor(() => expect(screen.getByTestId('stub-settings-tab')).toBeInTheDocument());
    const reg = hostRef!.getRegisteredTool('book-settings');
    expect(reg).not.toBeNull();
    expect(reg!.commandId).toBe('studio.openPanel.book-settings');
    expect(reg!.mcpToolPrefixes).toBeUndefined();
  });

  it('passes onReload through to a react-query refetch', async () => {
    getBook.mockResolvedValue({ title: 'My Book' });
    withHost('b1', <BookSettingsPanel {...dockProps()} />);
    await waitFor(() => expect(screen.getByTestId('stub-settings-tab')).toBeInTheDocument());
    getBook.mockClear();
    fireEvent.click(screen.getByText('reload'));
    await waitFor(() => expect(getBook).toHaveBeenCalled());
  });

  it('DOCK-7: passes an onOpenWorld handler that routes through followStudioLink, never navigate', async () => {
    getBook.mockResolvedValue({ title: 'My Book' });
    withHost('b1', <BookSettingsPanel {...dockProps()} />);
    await waitFor(() => expect(screen.getByTestId('stub-settings-tab')).toBeInTheDocument());
    fireEvent.click(screen.getByText('open-world'));
    expect(followStudioLink).toHaveBeenCalledWith('/worlds/w1', hostRef, { bookId: 'b1' });
  });
});
