// 15_chapter_browser.md B1 — Title-mode view: sort/filter/grouping/multi-select/translate-wiring.
// `useChapterBrowserGroups` (another agent's hook) and `TranslateModal` (existing, heavy — its own
// model/coverage fetches) are mocked so this stays a focused unit test of ChapterBrowserTitleView's
// own logic, not a re-test of those dependencies.
import { act, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const listChapters = vi.fn();
const bulkUpdateChapterStatus = vi.fn();
const bulkExportChaptersZip = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: {
    listChapters: (...a: unknown[]) => listChapters(...a),
    bulkUpdateChapterStatus: (...a: unknown[]) => bulkUpdateChapterStatus(...a),
    bulkExportChaptersZip: (...a: unknown[]) => bulkExportChaptersZip(...a),
  },
}));

const groupsMock = vi.fn();
vi.mock('@/features/books/hooks/useChapterBrowserGroups', () => ({
  useChapterBrowserGroups: (...a: unknown[]) => groupsMock(...a),
}));

const translateModalSpy = vi.fn();
vi.mock('@/pages/book-tabs/TranslateModal', () => ({
  TranslateModal: (props: { open: boolean; preselectedChapterIds?: string[] }) => {
    translateModalSpy(props);
    return props.open ? <div data-testid="mock-translate-modal">{JSON.stringify(props.preselectedChapterIds)}</div> : null;
  },
}));

const toastInfo = vi.fn();
const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    info: (...a: unknown[]) => toastInfo(...a),
    success: (...a: unknown[]) => toastSuccess(...a),
    error: (...a: unknown[]) => toastError(...a),
  },
}));

import { ChapterBrowserTitleView } from '../ChapterBrowserTitleView';

function chap(id: string, order: number, title: string, extra: Record<string, unknown> = {}) {
  return {
    chapter_id: id, book_id: 'b', original_filename: `${order}.txt`, original_language: 'en',
    content_type: 'text', byte_size: 1, sort_order: order, lifecycle_state: 'active',
    editorial_status: 'published', title, updated_at: '2026-06-01T00:00:00Z', word_count: 100 * order,
    ...extra,
  };
}

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function renderView() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <StudioHostProvider bookId="b">
        <HostProbe />
        <ChapterBrowserTitleView bookId="b" />
      </StudioHostProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  hostRef = null;
  listChapters.mockReset();
  bulkUpdateChapterStatus.mockReset();
  bulkExportChaptersZip.mockReset();
  translateModalSpy.mockReset();
  toastInfo.mockReset();
  toastSuccess.mockReset();
  toastError.mockReset();
  listChapters.mockResolvedValue({
    items: [chap('c1', 1, 'Alpha'), chap('c2', 2, 'Beta')],
    total: 2,
  });
  groupsMock.mockReturnValue({ hasWork: false, loading: false, groups: [], arcIdForChapter: () => undefined });
});

describe('ChapterBrowserTitleView', () => {
  it('renders the fetched chapters with a word-count column (graceful "—" when absent)', async () => {
    listChapters.mockResolvedValueOnce({
      items: [chap('c1', 1, 'Alpha', { word_count: undefined })],
      total: 1,
    });
    renderView();
    await waitFor(() => expect(screen.getAllByTestId('chapter-browser-row').length).toBe(1));
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('sort dropdown passes `sort` through to booksApi.listChapters (forward-compatible, BE may ignore it)', async () => {
    renderView();
    await waitFor(() => expect(listChapters).toHaveBeenCalled());
    act(() => {
      (screen.getByTestId('chapter-browser-sort-select') as HTMLSelectElement).value = 'word_count';
      screen.getByTestId('chapter-browser-sort-select').dispatchEvent(new Event('change', { bubbles: true }));
    });
    await waitFor(() => {
      const called = listChapters.mock.calls.some((c) => (c[2] as { sort?: string })?.sort === 'word_count');
      expect(called).toBe(true);
    });
  });

  it('status filter chip drives editorial_status + lifecycle_state', async () => {
    renderView();
    await waitFor(() => expect(listChapters).toHaveBeenCalled());
    act(() => { screen.getByTestId('chapter-browser-status-draft').click(); });
    await waitFor(() => {
      const params = listChapters.mock.calls.at(-1)![2] as { editorial_status?: string; lifecycle_state?: string };
      expect(params.editorial_status).toBe('draft');
      expect(params.lifecycle_state).toBe('active');
    });
  });

  it('trashed status chip sets lifecycle_state=trashed', async () => {
    renderView();
    await waitFor(() => expect(listChapters).toHaveBeenCalled());
    act(() => { screen.getByTestId('chapter-browser-status-trashed').click(); });
    await waitFor(() => {
      const params = listChapters.mock.calls.at(-1)![2] as { lifecycle_state?: string };
      expect(params.lifecycle_state).toBe('trashed');
    });
  });

  it('"Group by arc" toggle is absent when useChapterBrowserGroups reports hasWork:false', async () => {
    renderView();
    await waitFor(() => expect(screen.getAllByTestId('chapter-browser-row').length).toBe(2));
    expect(screen.queryByTestId('chapter-browser-view-grouped')).not.toBeInTheDocument();
  });

  it('grouped view renders a group header when hasWork:true and an arc is resolved', async () => {
    groupsMock.mockReturnValue({
      hasWork: true,
      loading: false,
      groups: [{ arcId: 'arc-1', label: 'The Crimson Court', romanNumeral: 'II', chapterIds: new Set(['c1', 'c2']), chapterCount: 2 }],
      arcIdForChapter: (id: string) => (id === 'c1' || id === 'c2' ? 'arc-1' : undefined),
    });
    renderView();
    await waitFor(() => expect(screen.getAllByTestId('chapter-browser-row').length).toBe(2));
    act(() => { screen.getByTestId('chapter-browser-view-grouped').click(); });
    await waitFor(() => expect(screen.getByTestId('chapter-browser-group-header')).toHaveTextContent('The Crimson Court'));
  });

  it('multi-select: checking a row shows the bulk-action bar with the right count', async () => {
    renderView();
    await waitFor(() => expect(screen.getAllByTestId('chapter-browser-row').length).toBe(2));
    const rows = screen.getAllByTestId('chapter-browser-row');
    const checkbox = rows[0].querySelector('input[type=checkbox]')!;
    act(() => { checkbox.dispatchEvent(new Event('click', { bubbles: true })); (checkbox as HTMLInputElement).click(); });
    await waitFor(() => expect(screen.getByTestId('chapter-browser-bulk-bar')).toBeInTheDocument());
  });

  it('Translate is fully wired: selection flows into TranslateModal as preselectedChapterIds', async () => {
    renderView();
    await waitFor(() => expect(screen.getAllByTestId('chapter-browser-row').length).toBe(2));
    const rows = screen.getAllByTestId('chapter-browser-row');
    const checkbox = rows[0].querySelector('input[type=checkbox]') as HTMLInputElement;
    act(() => { checkbox.click(); });
    await waitFor(() => expect(screen.getByTestId('chapter-browser-bulk-translate')).toBeInTheDocument());
    act(() => { screen.getByTestId('chapter-browser-bulk-translate').click(); });
    await waitFor(() => expect(screen.getByTestId('mock-translate-modal')).toHaveTextContent('c1'));
  });

  it('Set status calls bulkUpdateChapterStatus("active") and reports the real per-id outcome', async () => {
    bulkUpdateChapterStatus.mockResolvedValue({ results: [{ chapter_id: 'c1', ok: true }] });
    renderView();
    await waitFor(() => expect(screen.getAllByTestId('chapter-browser-row').length).toBe(2));
    const rows = screen.getAllByTestId('chapter-browser-row');
    const checkbox = rows[0].querySelector('input[type=checkbox]') as HTMLInputElement;
    act(() => { checkbox.click(); });
    await waitFor(() => expect(screen.getByTestId('chapter-browser-bulk-status')).toBeInTheDocument());
    await act(async () => { screen.getByTestId('chapter-browser-bulk-status').click(); });
    await waitFor(() => expect(bulkUpdateChapterStatus).toHaveBeenCalledWith('tok', 'b', ['c1'], 'active'));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
  });

  it('Set status reports a PARTIAL failure honestly, never a silent all-ok', async () => {
    bulkUpdateChapterStatus.mockResolvedValue({ results: [{ chapter_id: 'c1', ok: false, error: 'not found' }] });
    renderView();
    await waitFor(() => expect(screen.getAllByTestId('chapter-browser-row').length).toBe(2));
    const rows = screen.getAllByTestId('chapter-browser-row');
    act(() => { (rows[0].querySelector('input[type=checkbox]') as HTMLInputElement).click(); });
    await waitFor(() => expect(screen.getByTestId('chapter-browser-bulk-status')).toBeInTheDocument());
    await act(async () => { screen.getByTestId('chapter-browser-bulk-status').click(); });
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('Trash asks for confirmation, then calls bulkUpdateChapterStatus("trashed") — cancel does nothing', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderView();
    await waitFor(() => expect(screen.getAllByTestId('chapter-browser-row').length).toBe(2));
    const rows = screen.getAllByTestId('chapter-browser-row');
    act(() => { (rows[0].querySelector('input[type=checkbox]') as HTMLInputElement).click(); });
    await waitFor(() => expect(screen.getByTestId('chapter-browser-bulk-trash')).toBeInTheDocument());
    await act(async () => { screen.getByTestId('chapter-browser-bulk-trash').click(); });
    expect(confirmSpy).toHaveBeenCalled();
    expect(bulkUpdateChapterStatus).not.toHaveBeenCalled();

    bulkUpdateChapterStatus.mockResolvedValue({ results: [{ chapter_id: 'c1', ok: true }] });
    confirmSpy.mockReturnValue(true);
    await act(async () => { screen.getByTestId('chapter-browser-bulk-trash').click(); });
    await waitFor(() => expect(bulkUpdateChapterStatus).toHaveBeenCalledWith('tok', 'b', ['c1'], 'trashed'));
    confirmSpy.mockRestore();
  });

  it('Export calls bulkExportChaptersZip and triggers a browser download of the returned blob', async () => {
    const blob = new Blob(['zip-bytes']);
    bulkExportChaptersZip.mockResolvedValue(blob);
    const clickSpy = vi.fn();
    const origCreate = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = origCreate(tag);
      if (tag === 'a') el.click = clickSpy;
      return el;
    });
    const createObjectURL = vi.fn().mockReturnValue('blob:mock');
    const revokeObjectURL = vi.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });

    renderView();
    await waitFor(() => expect(screen.getAllByTestId('chapter-browser-row').length).toBe(2));
    const rows = screen.getAllByTestId('chapter-browser-row');
    act(() => { (rows[0].querySelector('input[type=checkbox]') as HTMLInputElement).click(); });
    await waitFor(() => expect(screen.getByTestId('chapter-browser-bulk-export')).toBeInTheDocument());
    await act(async () => { screen.getByTestId('chapter-browser-bulk-export').click(); });
    await waitFor(() => expect(bulkExportChaptersZip).toHaveBeenCalledWith('tok', 'b', ['c1']));
    expect(createObjectURL).toHaveBeenCalledWith(blob);
    expect(clickSpy).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:mock');

    vi.restoreAllMocks();
  });

  it('row click opens the chapter via host.focusManuscriptUnit — never a route navigation (DOCK-7)', async () => {
    renderView();
    await waitFor(() => expect(screen.getAllByTestId('chapter-browser-row').length).toBe(2));
    const focus = vi.spyOn(hostRef!, 'focusManuscriptUnit');
    act(() => { screen.getAllByTestId('chapter-browser-row')[0].click(); });
    expect(focus).toHaveBeenCalledWith('c1');
  });
});
