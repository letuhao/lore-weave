// Spec 29 T6 — a versions/chapters load failure must surface a typed error banner + Retry,
// not a structurally-fine, factually-empty workspace whose only signal was a long-gone toast.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('react-router-dom', () => ({ Link: (p: { children: React.ReactNode }) => <>{p.children}</> }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

const listChapters = vi.fn();
const getDraft = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: { listChapters: (...a: unknown[]) => listChapters(...a), getDraft: (...a: unknown[]) => getDraft(...a) },
}));

const listChapterVersions = vi.fn();
const getBookSettings = vi.fn();
vi.mock('@/features/translation/api', () => ({
  versionsApi: { listChapterVersions: (...a: unknown[]) => listChapterVersions(...a) },
  translationApi: { getBookSettings: (...a: unknown[]) => getBookSettings(...a) },
}));

// Heavy children are covered by their own tests — stub them so this stays about the error state.
vi.mock('@/features/translation/components/VersionSidebar', () => ({ VersionSidebar: () => <div data-testid="sidebar" /> }));
vi.mock('@/features/translation/components/TranslationViewer', () => ({ TranslationViewer: () => null }));
vi.mock('@/features/translation/components/SplitCompareView', () => ({ SplitCompareView: () => null }));
vi.mock('@/pages/book-tabs/TranslateModal', () => ({ TranslateModal: () => null }));

import { ChapterTranslationsPanel } from '../ChapterTranslationsPanel';

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  listChapters.mockReset(); getDraft.mockReset(); listChapterVersions.mockReset(); getBookSettings.mockReset();
  listChapters.mockResolvedValue({ items: [{ chapter_id: 'ch1', title: 'Ch 1', sort_order: 0 }] });
  getBookSettings.mockResolvedValue(null);
  getDraft.mockResolvedValue({ text_content: 'original text', body: 'original text' });
});

describe('ChapterTranslationsPanel — T6 degraded mode', () => {
  it('renders a typed error + Retry when the versions load fails, not an empty workspace', async () => {
    listChapterVersions.mockRejectedValue(Object.assign(new Error('proxy leak'), { status: 503 }));
    wrap(<ChapterTranslationsPanel bookId="b" chapterId="ch1" />);
    const box = await screen.findByTestId('translation-error');
    expect(box.getAttribute('data-kind')).toBe('retryable');
    expect(screen.getByTestId('translation-error-retry')).toBeInTheDocument();
    // the sidebar (empty workspace) is NOT shown on a hard load failure
    expect(screen.queryByTestId('sidebar')).toBeNull();
    expect(screen.queryByText(/proxy leak/)).toBeNull();
  });

  it('renders the workspace normally when the versions load succeeds', async () => {
    listChapterVersions.mockResolvedValue({ chapter_id: 'ch1', languages: [] });
    wrap(<ChapterTranslationsPanel bookId="b" chapterId="ch1" />);
    expect(await screen.findByTestId('sidebar')).toBeInTheDocument();
    expect(screen.queryByTestId('translation-error')).toBeNull();
  });
});
