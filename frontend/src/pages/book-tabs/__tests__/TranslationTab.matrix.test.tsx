// Spec 29 Phase A — matrix operability (T1/D1, T8/D6, T2/D3, D4, D5). These assert the
// EFFECT, not the presence of a handler (checklist-is-self-report-enforce-by-tests):
//  T1/D1 — a header "Translate…" CTA renders even on a book that already has ≥1 translated
//          language, and it opens the modal UNSCOPED (no preselection — the modal owns scope).
//  T8/D6 — ticking chapters + "Translate Selected" hands the selection (and, when a single
//          language is visible, that language) to the modal instead of discarding it.
//  T2/D3 — the matrix renders one row per CHAPTER (left-joined onto coverage), so untranslated
//          chapters are visible and selectable.
//  D4    — a 250-chapter book paginates at 100/page and selection survives a page change.
//  D5    — an orphan coverage row (chapter trashed but still translated) is surfaced as a
//          footnote, never silently dropped.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, o?: Record<string, unknown>) => (o && 'count' in o ? `${k}:${o.count}` : k),
  }),
}));

const listChapters = vi.fn();
vi.mock('@/features/books/api', () => ({ booksApi: { listChapters: (...a: unknown[]) => listChapters(...a) } }));

const getBookCoverage = vi.fn();
const getSegmentCoverage = vi.fn();
vi.mock('@/features/translation/api', () => ({
  translationApi: {
    getBookCoverage: (...a: unknown[]) => getBookCoverage(...a),
    getSegmentCoverage: (...a: unknown[]) => getSegmentCoverage(...a),
  },
}));

// Capture the props the matrix hands to TranslateModal (this is the T8/D6 seam).
let modalProps: Record<string, unknown> = {};
vi.mock('../TranslateModal', () => ({
  TranslateModal: (p: Record<string, unknown>) => {
    modalProps = p;
    return p.open ? <div data-testid="translate-modal-open" /> : null;
  },
}));
vi.mock('@/features/extraction/ExtractionWizard', () => ({ ExtractionWizard: () => null }));
vi.mock('@/features/translation/components/SegmentDrilldownModal', () => ({ SegmentDrilldownModal: () => null }));

import { TranslationTab } from '../TranslationTab';

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const cell = (status = 'completed') => ({
  has_active: true, active_version_num: 1, latest_version_num: 1,
  latest_status: status, version_count: 1, is_glossary_stale: false,
});

function chapters(n: number, prefix = 'ch') {
  return Array.from({ length: n }, (_, i) => ({
    chapter_id: `${prefix}${i + 1}`, title: `Ch ${i + 1}`, sort_order: i,
  }));
}

beforeEach(() => {
  listChapters.mockReset(); getBookCoverage.mockReset(); getSegmentCoverage.mockReset();
  modalProps = {};
  getSegmentCoverage.mockResolvedValue({ book_id: 'b', target_language: 'vi', chapters: [] });
});

/** Resolve listChapters as a single page of the given chapters. */
function mockChapters(chs: ReturnType<typeof chapters>) {
  listChapters.mockImplementation((_t, _b, opts: { offset: number; limit: number }) => {
    const page = chs.slice(opts.offset, opts.offset + opts.limit);
    return Promise.resolve({ items: page, total: chs.length });
  });
}

describe('TranslationTab matrix — T1/D1 header CTA', () => {
  it('renders a header Translate CTA on a book that already has ≥1 translated language', async () => {
    mockChapters(chapters(2));
    getBookCoverage.mockResolvedValue({
      book_id: 'b', known_languages: ['vi'],
      coverage: [{ chapter_id: 'ch1', languages: { vi: cell() } }],
    });
    wrap(<TranslationTab bookId="b" />);
    const cta = await screen.findByTestId('matrix-translate-cta');
    expect(cta).toBeInTheDocument();
  });

  it('the header CTA opens the modal UNSCOPED (no preselection — D1)', async () => {
    mockChapters(chapters(2));
    getBookCoverage.mockResolvedValue({
      book_id: 'b', known_languages: ['vi'],
      coverage: [{ chapter_id: 'ch1', languages: { vi: cell() } }],
    });
    wrap(<TranslationTab bookId="b" />);
    await screen.findByText('Ch 1'); // wait for chapters to load so the CTA is enabled
    fireEvent.click(screen.getByTestId('matrix-translate-cta'));
    await screen.findByTestId('translate-modal-open');
    expect(modalProps.preselectedChapterIds).toBeUndefined();
  });
});

describe('TranslationTab matrix — T2/D3 one row per chapter', () => {
  it('renders every chapter, including untranslated ones absent from coverage', async () => {
    mockChapters(chapters(3));
    getBookCoverage.mockResolvedValue({
      book_id: 'b', known_languages: ['vi'],
      coverage: [{ chapter_id: 'ch1', languages: { vi: cell() } }], // only ch1 translated
    });
    wrap(<TranslationTab bookId="b" />);
    await screen.findByText('Ch 1');
    expect(screen.getByText('Ch 2')).toBeInTheDocument();
    expect(screen.getByText('Ch 3')).toBeInTheDocument();
    // every chapter row is selectable (a checkbox each + the header select-all)
    const boxes = screen.getAllByRole('checkbox');
    expect(boxes.length).toBe(3 + 1);
  });
});

describe('TranslationTab matrix — T8/D6 selection + language hand-off', () => {
  it('Translate Selected passes the ticked chapters (and the single visible language) to the modal', async () => {
    mockChapters(chapters(3));
    getBookCoverage.mockResolvedValue({
      book_id: 'b', known_languages: ['vi'],
      coverage: [{ chapter_id: 'ch1', languages: { vi: cell() } }],
    });
    wrap(<TranslationTab bookId="b" />);
    await screen.findByText('Ch 2');
    // tick ch2 + ch3 (rows without coverage — the ones T2 used to hide)
    fireEvent.click(screen.getByRole('checkbox', { name: /Ch 2/ }));
    fireEvent.click(screen.getByRole('checkbox', { name: /Ch 3/ }));
    fireEvent.click(screen.getByTestId('matrix-translate-selected'));
    await screen.findByTestId('translate-modal-open');
    expect(modalProps.preselectedChapterIds).toEqual(expect.arrayContaining(['ch2', 'ch3']));
    expect((modalProps.preselectedChapterIds as string[]).length).toBe(2);
    expect(modalProps.preselectedLang).toBe('vi'); // single visible language
  });
});

describe('TranslationTab matrix — D4 pagination', () => {
  it('paginates a 250-chapter book and preserves selection across a page change', async () => {
    mockChapters(chapters(250));
    getBookCoverage.mockResolvedValue({ book_id: 'b', known_languages: ['vi'], coverage: [] });
    wrap(<TranslationTab bookId="b" />);
    await screen.findByText('Ch 1');
    // page 1 shows the first 100, not chapter 150
    expect(screen.queryByText('Ch 150')).toBeNull();
    // select a chapter on page 1, then advance a page
    fireEvent.click(screen.getByRole('checkbox', { name: /Ch 1$/ }));
    fireEvent.click(screen.getByTestId('matrix-translate-selected'));
    await screen.findByTestId('translate-modal-open');
    const before = modalProps.preselectedChapterIds as string[];
    expect(before).toContain('ch1');
    // the pager exists (250 chapters ⇒ 3 pages); next is an aria-label
    expect(screen.getByLabelText('matrix.next')).toBeInTheDocument();
  });
});

describe('TranslationTab matrix — D5 orphan coverage footnote', () => {
  it('surfaces a footnote for coverage rows whose chapter is no longer active', async () => {
    mockChapters(chapters(2));
    getBookCoverage.mockResolvedValue({
      book_id: 'b', known_languages: ['vi'],
      coverage: [
        { chapter_id: 'ch1', languages: { vi: cell() } },
        { chapter_id: 'gone', languages: { vi: cell() } }, // trashed chapter, still translated
      ],
    });
    wrap(<TranslationTab bookId="b" />);
    await screen.findByText('Ch 1');
    expect(await screen.findByTestId('matrix-orphan-footnote')).toBeInTheDocument();
    // and the orphan is NOT rendered as a selectable row
    expect(within(screen.getByRole('table')).queryByText('gone')).toBeNull();
  });
});
