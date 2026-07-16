// Spec 29 Phase A — T4/T10/D9: a coverage OR chapter-list failure is surfaced as a TYPED
// error (retryable vs forbidden vs notfound), never as a raw proxy string (T4) and never as an
// empty book (T10). A 403 offers no Retry (retrying would just 403 again); a 5xx/network does.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
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
vi.mock('../TranslateModal', () => ({ TranslateModal: () => null }));
vi.mock('@/features/extraction/ExtractionWizard', () => ({ ExtractionWizard: () => null }));
vi.mock('@/features/translation/components/SegmentDrilldownModal', () => ({ SegmentDrilldownModal: () => null }));

import { TranslationTab } from '../TranslationTab';

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const httpError = (status: number) => Object.assign(new Error('Error occurred while trying to proxy: …'), { status });

beforeEach(() => {
  listChapters.mockReset(); getBookCoverage.mockReset(); getSegmentCoverage.mockReset();
  getSegmentCoverage.mockResolvedValue({ book_id: 'b', target_language: 'vi', chapters: [] });
  listChapters.mockResolvedValue({ items: [{ chapter_id: 'ch1', title: 'Ch 1', sort_order: 0 }], total: 1 });
});

describe('TranslationTab — T4/D9 coverage failure', () => {
  it('renders a typed RETRYABLE error with a Retry for a 5xx, not the raw proxy string', async () => {
    getBookCoverage.mockRejectedValue(httpError(500));
    wrap(<TranslationTab bookId="b" />);
    const box = await screen.findByTestId('translation-error');
    expect(box.getAttribute('data-kind')).toBe('retryable');
    expect(screen.getByTestId('translation-error-retry')).toBeInTheDocument();
    // the raw proxy message is never rendered
    expect(screen.queryByText(/trying to proxy/)).toBeNull();
  });

  it('renders a FORBIDDEN error with NO Retry for a 403', async () => {
    getBookCoverage.mockRejectedValue(httpError(403));
    wrap(<TranslationTab bookId="b" />);
    const box = await screen.findByTestId('translation-error');
    expect(box.getAttribute('data-kind')).toBe('forbidden');
    expect(screen.queryByTestId('translation-error-retry')).toBeNull();
  });

  it('shows a labelled loading state (not a textless skeleton) while coverage loads', async () => {
    let resolve!: (v: unknown) => void;
    getBookCoverage.mockReturnValue(new Promise((r) => { resolve = r; }));
    wrap(<TranslationTab bookId="b" />);
    expect(await screen.findByTestId('matrix-loading')).toBeInTheDocument();
    expect(screen.getByText('matrix.loading')).toBeInTheDocument();
    resolve({ book_id: 'b', known_languages: ['vi'], coverage: [] });
  });
});

describe('TranslationTab — T10 chapter-list failure', () => {
  it('surfaces a chapter-list failure as a typed error, not an empty book', async () => {
    getBookCoverage.mockResolvedValue({ book_id: 'b', known_languages: ['vi'], coverage: [] });
    listChapters.mockRejectedValue(httpError(503));
    wrap(<TranslationTab bookId="b" />);
    const box = await screen.findByTestId('translation-error');
    expect(box.getAttribute('data-kind')).toBe('retryable');
    // the "no chapters" empty state must NOT be what the user sees on a real fetch failure
    expect(screen.queryByText('matrix.no_chapters_title')).toBeNull();
  });
});
