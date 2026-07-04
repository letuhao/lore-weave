// 14_utility_panels.md Phase C4 — BookReaderPanel: params-retargeting singleton (SkillEditorPanel
// precedent). Covers: empty-param placeholder, bootstrapping a missing chapterId to the first
// active chapter, rendering via useBookReaderContent (C3), and that chapter navigation retargets
// the panel's OWN params (props.api.updateParameters) instead of ever route-navigating (DOCK-7).
import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const booksApiMocks = vi.hoisted(() => ({
  listChapters: vi.fn(),
}));
vi.mock('@/features/books/api', () => ({ booksApi: booksApiMocks }));

vi.mock('@/providers/ThemeProvider', () => ({
  useReaderTheme: () => ({ cssVars: {}, theme: { bg: '#111', fg: '#eee' } }),
}));

const ttsState = { status: 'idle' as const, activeBlockId: null as string | null };
vi.mock('@/hooks/useTTS', () => ({
  useTTSState: () => ttsState,
  useTTSControls: () => ({ start: vi.fn(), stop: vi.fn(), seekBlock: vi.fn() }),
}));
vi.mock('@/hooks/useReadingTracker', () => ({ useReadingTracker: () => ({ current: null }) }));
vi.mock('@/lib/audio-utils', () => ({ extractSpeakableBlocks: () => [] }));

vi.mock('@/components/reader/ContentRenderer', () => ({
  ContentRenderer: ({ blocks }: { blocks: unknown[] }) => <div data-testid="stub-content" data-blocks={blocks.length} />,
}));
vi.mock('@/components/reader/ThemeCustomizer', () => ({ ThemeCustomizer: () => <div data-testid="stub-theme" /> }));
vi.mock('@/components/reader/TTSBar', () => ({ TTSBar: () => <div data-testid="stub-ttsbar" /> }));
vi.mock('@/components/reader/TTSSettings', () => ({ TTSSettings: () => <div data-testid="stub-ttssettings" /> }));
vi.mock('@/components/reader/TOCSidebar', () => ({
  TOCSidebar: ({ onNavigateChapter }: { onNavigateChapter?: (id: string) => void }) => (
    <button data-testid="stub-toc-nav" onClick={() => onNavigateChapter?.('ch-2')}>toc-nav</button>
  ),
}));

const hookMocks = vi.hoisted(() => ({
  useBookReaderContent: vi.fn(),
  computeReadingStats: vi.fn(() => ({ count: '10', unit: 'words', minutes: 1 })),
}));
vi.mock('@/features/books/hooks/useBookReaderContent', () => hookMocks);

import { BookReaderPanel } from '../BookReaderPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockStub(params?: Record<string, unknown>) {
  const listeners = new Set<(p: Record<string, unknown>) => void>();
  const updateParameters = vi.fn();
  const props = {
    api: {
      setTitle: vi.fn(),
      updateParameters,
      onDidParametersChange: (cb: (p: Record<string, unknown>) => void) => {
        listeners.add(cb);
        return { dispose: () => listeners.delete(cb) };
      },
    },
    params,
  } as unknown as IDockviewPanelProps;
  const fireParams = (p: Record<string, unknown>) => listeners.forEach((l) => l(p));
  return { props, updateParameters, fireParams };
}

function withHost(ui: ReactNode) {
  return render(<StudioHostProvider bookId="active-book"><HostProbe />{ui}</StudioHostProvider>);
}

const CONTENT = {
  book: { book_id: 'other-book', title: 'Other Book', original_language: 'en' },
  chapters: [
    { chapter_id: 'ch-1', title: 'One', sort_order: 1, original_language: 'en' },
    { chapter_id: 'ch-2', title: 'Two', sort_order: 2, original_language: 'en' },
  ],
  chapter: { chapter_id: 'ch-1', title: 'One', original_filename: 'ch1.txt', original_language: 'en' },
  blocks: [{ type: 'paragraph', content: [{ type: 'text', text: 'hi' }] }],
  languages: [{ code: 'en', isOriginal: true }],
  activeLanguage: 'en',
  langLoading: false,
  readProgress: [],
  loading: false,
  handleLanguageChange: vi.fn(),
  currentIdx: 0,
  prevCh: null,
  nextCh: { chapter_id: 'ch-2', title: 'Two' },
  progress: 50,
};

beforeEach(() => {
  hostRef = null;
  booksApiMocks.listChapters.mockReset();
  hookMocks.useBookReaderContent.mockReset();
  hookMocks.useBookReaderContent.mockReturnValue(CONTENT);
});

describe('BookReaderPanel', () => {
  it('registers with the host and titles its dock tab', () => {
    const { props } = dockStub({ bookId: 'other-book', chapterId: 'ch-1' });
    withHost(<BookReaderPanel {...props} />);
    expect(hostRef!.getRegisteredTool('book-reader')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('book-reader')!.commandId).toBe('studio.openPanel.book-reader');
  });

  it('shows a placeholder when opened with no bookId (F1 empty-param case)', () => {
    const { props } = dockStub();
    withHost(<BookReaderPanel {...props} />);
    expect(screen.getByTestId('studio-book-reader-panel')).toHaveTextContent(/Open a book/i);
    expect(hookMocks.useBookReaderContent).toHaveBeenCalledWith('', '');
  });

  it('renders chapter content once a (bookId, chapterId) pair resolves', () => {
    const { props } = dockStub({ bookId: 'other-book', chapterId: 'ch-1' });
    withHost(<BookReaderPanel {...props} />);
    expect(hookMocks.useBookReaderContent).toHaveBeenCalledWith('other-book', 'ch-1');
    expect(screen.getByTestId('stub-content').getAttribute('data-blocks')).toBe('1');
  });

  it('bootstraps a missing chapterId to the first active chapter by sort_order, then retargets its own params', async () => {
    booksApiMocks.listChapters.mockResolvedValue({
      items: [
        { chapter_id: 'ch-b', sort_order: 2 },
        { chapter_id: 'ch-a', sort_order: 1 },
      ],
      total: 2,
    });
    const { props, updateParameters } = dockStub({ bookId: 'other-book' });
    withHost(<BookReaderPanel {...props} />);
    await waitFor(() => expect(updateParameters).toHaveBeenCalledWith({ bookId: 'other-book', chapterId: 'ch-a' }));
  });

  it('does NOT bootstrap-fetch chapters when a chapterId is already given', () => {
    const { props } = dockStub({ bookId: 'other-book', chapterId: 'ch-1' });
    withHost(<BookReaderPanel {...props} />);
    expect(booksApiMocks.listChapters).not.toHaveBeenCalled();
  });

  it('next-chapter button retargets params via updateParameters, never a route push', () => {
    const { props, updateParameters } = dockStub({ bookId: 'other-book', chapterId: 'ch-1' });
    withHost(<BookReaderPanel {...props} />);
    act(() => { screen.getByTestId('book-reader-next-chapter').click(); });
    expect(updateParameters).toHaveBeenCalledWith({ bookId: 'other-book', chapterId: 'ch-2' });
  });

  it('TOC chapter click retargets params via the injected onNavigateChapter callback (DOCK-7)', () => {
    const { props, updateParameters } = dockStub({ bookId: 'other-book', chapterId: 'ch-1' });
    withHost(<BookReaderPanel {...props} />);
    act(() => { screen.getByTestId('stub-toc-nav').click(); });
    expect(updateParameters).toHaveBeenCalledWith({ bookId: 'other-book', chapterId: 'ch-2' });
  });

  it('an updateParameters event from the host (re-open with a different chapter) is followed', () => {
    const { props, fireParams } = dockStub({ bookId: 'other-book', chapterId: 'ch-1' });
    withHost(<BookReaderPanel {...props} />);
    act(() => { fireParams({ bookId: 'other-book', chapterId: 'ch-2' }); });
    expect(hookMocks.useBookReaderContent).toHaveBeenCalledWith('other-book', 'ch-2');
  });
});
