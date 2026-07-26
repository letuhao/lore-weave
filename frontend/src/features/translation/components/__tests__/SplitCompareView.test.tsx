// S6 (spec 29) — a failed getDraft used to leave the original pane BLANK (the translation pane
// had a fallback, this one didn't). It must now show the same "unavailable" copy.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: Record<string, unknown>) => (o && 'lang' in o ? `${k}:${o.lang}` : k) }),
}));
vi.mock('@/components/reader/ContentRenderer', () => ({ ContentRenderer: () => <div data-testid="content" /> }));

const getDraft = vi.fn();
const getChapterVersion = vi.fn();
vi.mock('@/features/books/api', () => ({ booksApi: { getDraft: (...a: unknown[]) => getDraft(...a) } }));
vi.mock('../../api', () => ({ versionsApi: { getChapterVersion: (...a: unknown[]) => getChapterVersion(...a) } }));

import { SplitCompareView } from '../SplitCompareView';

beforeEach(() => { getDraft.mockReset(); getChapterVersion.mockReset(); });

describe('SplitCompareView — S6 original-pane fallback', () => {
  it('renders the "original unavailable" fallback when getDraft fails, not a blank pane', async () => {
    getDraft.mockRejectedValue(new Error('proxy down'));            // → caught to null
    getChapterVersion.mockResolvedValue({ translated_body: 'Bản dịch', translated_body_format: 'text' });
    render(<SplitCompareView bookId="b" chapterId="c" versionId="v" originalLanguage="en" targetLanguage="vi" />);
    expect(await screen.findByText('compare.original_unavailable')).toBeInTheDocument();
    // the translation pane still shows its content (only the original failed)
    expect(screen.getByText('Bản dịch')).toBeInTheDocument();
  });

  it('renders the original text when getDraft succeeds (no fallback)', async () => {
    getDraft.mockResolvedValue({ text_content: 'The original prose', body: null });
    getChapterVersion.mockResolvedValue({ translated_body: 'X', translated_body_format: 'text' });
    render(<SplitCompareView bookId="b" chapterId="c" versionId="v" originalLanguage="en" targetLanguage="vi" />);
    expect(await screen.findByText('The original prose')).toBeInTheDocument();
    expect(screen.queryByText('compare.original_unavailable')).toBeNull();
  });
});
