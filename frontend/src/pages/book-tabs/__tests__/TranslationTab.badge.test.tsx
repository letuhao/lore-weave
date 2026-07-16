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
const getBook = vi.fn().mockResolvedValue({ book_id: 'b', owner_user_id: 'u1', access_level: 'owner' });
vi.mock('@/features/books/api', () => ({
  booksApi: {
    listChapters: (...a: unknown[]) => listChapters(...a),
    getBook: (...a: unknown[]) => getBook(...a),
  },
}));

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

let drillProps: { target?: { chapterId: string; lang: string } | null } = {};
vi.mock('@/features/translation/components/SegmentDrilldownModal', () => ({
  SegmentDrilldownModal: (props: { target?: { chapterId: string; lang: string } | null }) => {
    drillProps = props;
    return props.target ? <div data-testid="drill-open" /> : null;
  },
}));

import { TranslationTab } from '../TranslationTab';

const COVERAGE = {
  book_id: 'b', known_languages: ['vi'],
  coverage: [{
    chapter_id: 'ch1',
    languages: { vi: { has_active: true, active_version_num: 1, latest_version_num: 1, latest_status: 'completed', version_count: 1, is_glossary_stale: false } },
  }],
};

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('TranslationTab — segment "changed" badge', () => {
  beforeEach(() => {
    listChapters.mockReset(); getBookCoverage.mockReset(); getSegmentCoverage.mockReset();
    drillProps = {};
    listChapters.mockResolvedValue({ items: [{ chapter_id: 'ch1', title: 'Ch 1' }], total: 1 });
    getBookCoverage.mockResolvedValue(COVERAGE);
  });

  it('shows the ↻N badge and opens the drill-down for a cell with needs>0', async () => {
    getSegmentCoverage.mockResolvedValue({
      book_id: 'b', target_language: 'vi',
      chapters: [{ chapter_id: 'ch1', segment_total: 8, translated_count: 8, dirty_count: 1, stale_count: 1, needs_count: 2 }],
    });
    wrap(<TranslationTab bookId="b" />);
    const badge = await screen.findByLabelText('matrix.cell_changed_title:2');
    fireEvent.click(badge);
    await waitFor(() => expect(drillProps.target).toMatchObject({ chapterId: 'ch1', lang: 'vi' }));
  });

  it('shows no badge when needs=0', async () => {
    getSegmentCoverage.mockResolvedValue({
      book_id: 'b', target_language: 'vi',
      chapters: [{ chapter_id: 'ch1', segment_total: 8, translated_count: 8, dirty_count: 0, stale_count: 0, needs_count: 0 }],
    });
    wrap(<TranslationTab bookId="b" />);
    await screen.findByText('Ch 1');
    expect(screen.queryByLabelText('matrix.cell_changed_title:0')).toBeNull();
  });
});
