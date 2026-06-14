import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ChapterRangeStep } from '../ChapterRangeStep';
import type { WizardForm } from '../../../hooks/useCampaignWizard';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const listChapters = vi.fn();
vi.mock('../../../../books/api', () => ({
  booksApi: { listChapters: (...a: unknown[]) => listChapters(...a) },
}));

function chap(sort: number, editorial: string) {
  return {
    chapter_id: `c${sort}`, book_id: 'b', original_filename: `${sort}.txt`,
    original_language: 'zh', content_type: 'text', byte_size: 1, sort_order: sort,
    lifecycle_state: 'active', editorial_status: editorial, title: `Ch ${sort}`,
  };
}

function renderStep() {
  const form = { bookId: 'b', chapterFrom: null, chapterTo: null, gatingMode: 'phase_barrier' } as unknown as WizardForm;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ChapterRangeStep form={form} setField={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe('ChapterRangeStep', () => {
  beforeEach(() => listChapters.mockReset());

  it('loop-fetches every page so published chapters past the first 100 are not missed', async () => {
    // Page 1 (offset 0): 100 DRAFT chapters — a single capped fetch would stop here
    // and falsely report "no published chapters". Page 2 (offset 100): 50 published.
    listChapters.mockImplementation((_t: unknown, _b: unknown, params: { offset?: number }) => {
      const off = params?.offset ?? 0;
      if (off === 0) {
        return Promise.resolve({ items: Array.from({ length: 100 }, (_, i) => chap(i + 1, 'draft')), total: 150 });
      }
      if (off === 100) {
        return Promise.resolve({ items: Array.from({ length: 50 }, (_, i) => chap(i + 101, 'published')), total: 150 });
      }
      return Promise.resolve({ items: [], total: 150 });
    });

    renderStep();

    // Both pages fetched (offset 0 + offset 100).
    await waitFor(() => {
      const offsets = listChapters.mock.calls.map((c) => (c[2] as { offset?: number })?.offset);
      expect(offsets).toContain(0);
      expect(offsets).toContain(100);
    });
    // The page-2 published chapters were accumulated → the "no published" warning is absent.
    await waitFor(() => {
      expect(screen.queryByText('range.nonekPublished')).toBeNull();
    });
  });

  it('stops after the last partial page (no runaway fetch)', async () => {
    listChapters.mockResolvedValue({ items: [chap(1, 'published'), chap(2, 'published')], total: 2 });
    renderStep();
    await waitFor(() => expect(listChapters).toHaveBeenCalled());
    // A single partial page (<100) terminates the loop — exactly one request.
    await waitFor(() => expect(listChapters).toHaveBeenCalledTimes(1));
  });
});
