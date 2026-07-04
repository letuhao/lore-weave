// #16 1.5 — ChaptersTab's row-click, pencil icon, and post-create navigation all used to land on
// the legacy /chapters/:id/edit route; spec 16 M3 flips them to the Writing Studio (Phase 1 data-
// safety parity reached, so Studio is no longer strictly worse). The legacy route itself is
// untouched (still reachable by direct URL) — only these three entry points changed target.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string; count?: number }) => o?.defaultValue ?? k }),
}));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('@/features/extraction/ExtractionWizard', () => ({ ExtractionWizard: () => null }));

const navigate = vi.fn();
vi.mock('react-router-dom', async (orig) => {
  const m = await orig<typeof import('react-router-dom')>();
  return { ...m, useNavigate: () => navigate };
});

const listChapters = vi.fn();
const createChapterEditor = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: {
    listChapters: (...a: unknown[]) => listChapters(...a),
    createChapterEditor: (...a: unknown[]) => createChapterEditor(...a),
  },
}));

import { ChaptersTab } from '../ChaptersTab';

const CHAPTER = {
  chapter_id: 'ch-1', title: 'Chapter One', original_language: 'en', lifecycle_state: 'active',
  sort_order: 1, draft_updated_at: null, original_filename: 'ch1.txt',
};

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ChaptersTab bookId="b1" />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  navigate.mockClear();
  listChapters.mockReset().mockResolvedValue({ items: [CHAPTER], total: 1 });
  createChapterEditor.mockReset();
});

describe('ChaptersTab — #16 1.5 route switch', () => {
  it('row click opens the Writing Studio focused on that chapter, not the legacy editor', async () => {
    renderTab();
    const cell = await screen.findByTestId('chapter-title-cell');
    fireEvent.click(cell);
    expect(navigate).toHaveBeenCalledWith('/books/b1/studio?chapter=ch-1');
  });

  it('the pencil icon links to the Writing Studio, not the legacy editor route', async () => {
    renderTab();
    const pencil = await screen.findByTitle('chapters.action.edit');
    expect(pencil).toHaveAttribute('href', '/books/b1/studio?chapter=ch-1');
  });

  it('creating a new chapter opens it in the Writing Studio', async () => {
    createChapterEditor.mockResolvedValue({ chapter_id: 'ch-new' });
    renderTab();
    fireEvent.click(await screen.findByTestId('chapter-add-button'));
    fireEvent.change(screen.getByTestId('chapter-language-input'), { target: { value: 'en' } });
    fireEvent.click(screen.getByTestId('chapter-create-submit'));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/books/b1/studio?chapter=ch-new'));
  });
});
