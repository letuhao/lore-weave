// 14_utility_panels.md Phase C2 — BooksBrowserPanel: registration/self-title chrome (wave1
// precedent) + the one behavior that must differ from BooksPage — a row click opens the
// `book-reader` dock panel via the studio host instead of a <Link> route push (DOCK-7).
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const booksApiMocks = vi.hoisted(() => ({
  listBooks: vi.fn(),
  createBook: vi.fn(),
	startNewFB2Import: vi.fn(),
	getImportJob: vi.fn(),
}));
vi.mock('@/features/books/api', () => ({ booksApi: booksApiMocks }));

const translationMocks = vi.hoisted(() => ({ getBookCoverage: vi.fn() }));
vi.mock('@/features/translation/api', () => ({ translationApi: translationMocks }));

import { BooksBrowserPanel } from '../BooksBrowserPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(ui: ReactNode) {
  return render(<StudioHostProvider bookId="active-book"><HostProbe />{ui}</StudioHostProvider>);
}

beforeEach(() => {
  hostRef = null;
  booksApiMocks.listBooks.mockReset();
  booksApiMocks.createBook.mockReset();
	booksApiMocks.startNewFB2Import.mockReset();
	booksApiMocks.getImportJob.mockReset();
  translationMocks.getBookCoverage.mockReset();
  booksApiMocks.listBooks.mockResolvedValue({
    items: [{
      book_id: 'other-book', owner_user_id: 'u1', title: 'Other Book',
      original_language: 'en', chapter_count: 3, genre_tags: [], lifecycle_state: 'active',
    }],
    total: 1,
  });
  translationMocks.getBookCoverage.mockResolvedValue({ known_languages: [] });
});

describe('BooksBrowserPanel', () => {
  it('registers with the host and titles its dock tab', () => {
    const props = dockProps();
    withHost(<BooksBrowserPanel {...props} />);
    expect(hostRef!.getRegisteredTool('books')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('books')!.commandId).toBe('studio.openPanel.books');
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('renders the SAME book list useBooksList produces (thin view, no fork)', async () => {
    withHost(<BooksBrowserPanel {...dockProps()} />);
    await waitFor(() => expect(screen.getByTestId('book-row')).toHaveTextContent('Other Book'));
  });

  it('a row click opens book-reader via the studio host, never a route navigation', async () => {
    withHost(<BooksBrowserPanel {...dockProps()} />);
    const row = await screen.findByTestId('book-row');
    const openPanel = vi.spyOn(hostRef!, 'openPanel');
    act(() => { row.click(); });
    expect(openPanel).toHaveBeenCalledWith('book-reader', { params: { bookId: 'other-book' } });
  });

  it('the create dialog opens via FormDialog (DOCK-9 reuse, not a hand-rolled overlay)', async () => {
    withHost(<BooksBrowserPanel {...dockProps()} />);
    await waitFor(() => expect(screen.getByTestId('book-create-button')).toBeInTheDocument());
    act(() => { screen.getByTestId('book-create-button').click(); });
    expect(await screen.findByTestId('book-title-input')).toBeInTheDocument();
  });

	it('routes a selected FB2 through the create-and-import client operation', async () => {
		booksApiMocks.startNewFB2Import.mockResolvedValue({ id: 'job-1', book_id: 'fb2-book', status: 'pending', chapters_created: 0 });
		booksApiMocks.getImportJob.mockResolvedValue({ id: 'job-1', book_id: 'fb2-book', status: 'processing', chapters_created: 0 });
		withHost(<BooksBrowserPanel {...dockProps()} />);
		await waitFor(() => expect(screen.getByTestId('book-create-button')).toBeInTheDocument());
		act(() => { screen.getByTestId('book-create-button').click(); });
		const file = new File(['<FictionBook/>'], 'book.fb2', { type: 'application/x-fictionbook+xml' });
		fireEvent.change(await screen.findByTestId('book-fb2-import-input'), { target: { files: [file] } });
		act(() => { screen.getByTestId('book-create-submit').click(); });
		await waitFor(() => expect(booksApiMocks.startNewFB2Import).toHaveBeenCalledWith('tok', file, undefined, expect.any(Function)));
		expect(await screen.findByText('Processing FB2… 0 chapters created so far')).toBeInTheDocument();
	});
});
