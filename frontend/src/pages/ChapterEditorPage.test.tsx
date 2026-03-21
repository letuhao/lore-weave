import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ChapterEditorPage } from './ChapterEditorPage';

const getDraft = vi.fn();
const listRevisions = vi.fn();
const patchDraft = vi.fn();
const restoreRevision = vi.fn();

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'token-1' }),
}));

vi.mock('@/features/books/api', () => ({
  booksApi: {
    getDraft: (...args: unknown[]) => getDraft(...args),
    listRevisions: (...args: unknown[]) => listRevisions(...args),
    patchDraft: (...args: unknown[]) => patchDraft(...args),
    restoreRevision: (...args: unknown[]) => restoreRevision(...args),
  },
}));

describe('ChapterEditorPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    cleanup();
  });

  function renderPage() {
    return render(
      <MemoryRouter initialEntries={['/books/b1/chapters/c1/edit']}>
        <Routes>
          <Route path="/books/:bookId/chapters/:chapterId/edit" element={<ChapterEditorPage />} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it('loads draft and revision history', async () => {
    getDraft.mockResolvedValueOnce({
      chapter_id: 'c1',
      body: 'draft body',
      draft_format: 'plain',
      draft_updated_at: '2026-01-01T00:00:00Z',
      draft_version: 2,
    });
    listRevisions.mockResolvedValueOnce({
      items: [{ revision_id: 'r1', created_at: '2026-01-01T00:00:00Z', message: 'seed' }],
      total: 1,
    });

    renderPage();
    expect(await screen.findByDisplayValue('draft body')).toBeInTheDocument();
    expect(await screen.findByText(/seed/)).toBeInTheDocument();
  });

  it('saves draft with optimistic version and restores revision', async () => {
    getDraft.mockResolvedValue({
      chapter_id: 'c1',
      body: 'draft body',
      draft_format: 'plain',
      draft_updated_at: '2026-01-01T00:00:00Z',
      draft_version: 3,
    });
    listRevisions.mockResolvedValue({
      items: [{ revision_id: 'r1', created_at: '2026-01-01T00:00:00Z', message: 'seed' }],
      total: 1,
    });
    patchDraft.mockResolvedValue({});
    restoreRevision.mockResolvedValue({});

    renderPage();
    await screen.findByDisplayValue('draft body');

    fireEvent.change(screen.getByPlaceholderText('Commit message (optional)'), {
      target: { value: 'update chapter' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));

    await waitFor(() =>
      expect(patchDraft).toHaveBeenCalledWith('token-1', 'b1', 'c1', {
        body: 'draft body',
        commit_message: 'update chapter',
        expected_draft_version: 3,
      }),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Restore' }));
    await waitFor(() => expect(restoreRevision).toHaveBeenCalledWith('token-1', 'b1', 'c1', 'r1'));
  });
});
