import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const listChaptersMock = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: { listChapters: (...a: unknown[]) => listChaptersMock(...a) },
}));

import { ChapterSelectionPicker } from '../ChapterSelectionPicker';

const EMBEDS = [{ user_model_id: 'm1', alias: 'bge', provider_model_name: 'bge-m3' }];

function renderPicker(onGround = vi.fn().mockResolvedValue({ chapters_ingested: 1 })) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  render(
    <Wrapper>
      <ChapterSelectionPicker bookId="book-1" embeds={EMBEDS} onGround={onGround} busy={false} />
    </Wrapper>,
  );
  return { onGround };
}

beforeEach(() => {
  listChaptersMock.mockReset();
  listChaptersMock.mockResolvedValue({
    items: [
      { chapter_id: 'c2', title: '第二回', sort_order: 2 },
      { chapter_id: 'c1', title: '第一回', sort_order: 1 },
    ],
    total: 2,
  });
});

describe('ChapterSelectionPicker', () => {
  it('lists the book chapters (sorted by sort_order)', async () => {
    renderPicker();
    await waitFor(() => expect(screen.getByTestId('ground-chapter-c1')).toBeInTheDocument());
    expect(listChaptersMock).toHaveBeenCalledWith('tok', 'book-1', { lifecycle_state: 'active', limit: 100 });
    const labels = screen.getAllByText(/第.回/).map((e) => e.textContent);
    expect(labels).toEqual(['第一回', '第二回']); // sorted #1 then #2
  });

  it('the ground button is disabled until a chapter + model are chosen', async () => {
    renderPicker();
    await waitFor(() => expect(screen.getByTestId('ground-chapter-c1')).toBeInTheDocument());
    expect(screen.getByTestId('ground-submit')).toBeDisabled();
    fireEvent.click(screen.getByTestId('ground-chapter-c1')); // select a chapter, still no model
    expect(screen.getByTestId('ground-submit')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('sources.embed_model'), { target: { value: 'm1' } });
    expect(screen.getByTestId('ground-submit')).not.toBeDisabled();
  });

  it('submitting calls onGround with the selected chapter_ids + model, then clears selection', async () => {
    const { onGround } = renderPicker();
    await waitFor(() => expect(screen.getByTestId('ground-chapter-c1')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('ground-chapter-c1'));
    fireEvent.click(screen.getByTestId('ground-chapter-c2'));
    fireEvent.change(screen.getByLabelText('sources.embed_model'), { target: { value: 'm1' } });
    fireEvent.click(screen.getByTestId('ground-submit'));
    expect(onGround).toHaveBeenCalledWith({ embedding_model_ref: 'm1', chapter_ids: ['c1', 'c2'] });
    // selection cleared on success → button disabled again
    await waitFor(() => expect(screen.getByTestId('ground-submit')).toBeDisabled());
  });

  it('shows the empty-state when the book has no chapters', async () => {
    listChaptersMock.mockResolvedValue({ items: [], total: 0 });
    renderPicker();
    await waitFor(() => expect(screen.getByText('ground.no_chapters')).toBeInTheDocument());
  });

  it('surfaces a truncation notice when the book has more chapters than returned (no silent cap)', async () => {
    // review #1: book-service caps the page at 100; a larger book must NOT silently
    // hide the rest — show "showing N of total".
    listChaptersMock.mockResolvedValue({
      items: [{ chapter_id: 'c1', title: '第一回', sort_order: 1 }],
      total: 5000,
    });
    renderPicker();
    await waitFor(() => expect(screen.getByTestId('ground-truncated')).toBeInTheDocument());
  });

  it('no truncation notice when all chapters fit', async () => {
    renderPicker(); // default mock: 2 items, total 2
    await waitFor(() => expect(screen.getByTestId('ground-chapter-c1')).toBeInTheDocument());
    expect(screen.queryByTestId('ground-truncated')).toBeNull();
  });
});
