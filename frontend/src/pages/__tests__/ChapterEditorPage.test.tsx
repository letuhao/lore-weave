// A2-S4b: regression-lock the amber "unchecked" chip wire-up in ChapterEditorPage.
// The pure publishGateMessages function is tested in usePublishGate.test.tsx;
// this file covers only the page-level render path: hook result → conditional chip.
import { forwardRef } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// vi.hoisted so the fns are in-scope inside vi.mock factory closures (vitest hoisting rule)
const { mockUseGate, mockGuardedNavigate } = vi.hoisted(() => ({
  mockUseGate: vi.fn(),
  mockGuardedNavigate: vi.fn(),
}));

vi.mock('react-router-dom', async (orig) => {
  const m = await orig<typeof import('react-router-dom')>();
  return { ...m, useParams: () => ({ bookId: 'b1', chapterId: 'c1' }) };
});
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('@/api', () => ({ apiBase: () => 'http://localhost:3123' }));
vi.mock('@/hooks/useEditorPanels', () => ({
  useEditorPanels: () => ({
    left: false, right: false,
    toggleLeft: vi.fn(), toggleRight: vi.fn(),
    leftWidth: 300, rightWidth: 320,
    setLeftWidth: vi.fn(), setRightWidth: vi.fn(),
  }),
}));
vi.mock('@/contexts/EditorDirtyContext', () => ({
  useEditorDirty: () => ({
    setIsDirty: vi.fn(), guardedNavigate: mockGuardedNavigate,
    pendingNavigation: null, confirmNavigation: vi.fn(), cancelNavigation: vi.fn(),
  }),
}));
vi.mock('@/hooks/useEditorMode', () => ({ useEditorMode: () => ['classic', vi.fn()] }));
vi.mock('@/hooks/useGrammarCheck', () => ({ useGrammarEnabled: () => [false, vi.fn()] }));
vi.mock('@/features/books/api', () => ({
  booksApi: {
    getDraft: () => Promise.resolve({ body: null, text_content: '', draft_version: 1 }),
    getChapter: () => Promise.resolve({ title: 'Ch 1', editorial_status: 'draft' }),
    listChapters: () => Promise.resolve({ items: [] }),
    getOriginalContent: () => Promise.resolve(''),
  },
}));
vi.mock('@/features/glossary/api', () => ({
  glossaryApi: { listEntityNames: () => Promise.resolve([]) },
}));
// Spread the real module so publishGateMessages runs normally; only override the hook.
vi.mock('@/features/composition/hooks/usePublishGate', async (orig) => {
  const m = await orig<typeof import('@/features/composition/hooks/usePublishGate')>();
  return { ...m, useChapterPublishGate: (...a: unknown[]) => mockUseGate(...a) };
});

// Stub heavy components that would crash in jsdom or pull in excessive deps
vi.mock('@/components/editor/TiptapEditor', () => ({
  TiptapEditor: forwardRef((_props: any, _ref: any) => <div data-testid="tiptap-stub" />),
}));
vi.mock('@/components/editor/RevisionHistory', () => ({ RevisionHistory: () => null }));
vi.mock('@/components/editor/VersionHistoryPanel', () => ({ VersionHistoryPanel: () => null }));
vi.mock('@/components/editor/GlossaryTooltip', () => ({ GlossaryTooltip: () => null }));
vi.mock('@/components/editor/GlossaryAutocomplete', () => ({ GlossaryAutocomplete: () => null }));
vi.mock('@/components/editor/GlossaryPanel', () => ({ GlossaryPanel: () => null }));
vi.mock('@/features/books/components/PublishControl', () => ({
  PublishControl: (props: any) => (
    <button data-testid="publish-ctrl" disabled={!!props.blockedReason}>Publish</button>
  ),
}));
vi.mock('@/features/chat/Chat', () => ({ Chat: () => null }));
vi.mock('@/features/composition/components/CompositionPanel', () => ({
  CompositionPanel: () => null,
}));
// The Translate workmode embeds the full translation workspace; stub it so the page test
// doesn't pull the translation feature's deps (it only asserts the centre swaps to it).
vi.mock('@/features/translation/components/ChapterTranslationsPanel', () => ({
  ChapterTranslationsPanel: () => <div data-testid="xl-panel-stub" />,
}));
vi.mock('@/features/chat/context/sendToChat', () => ({ fireSendToChat: vi.fn() }));
vi.mock('@/features/chat/context/editorBridge', () => ({ registerEditorTarget: vi.fn() }));
// T3.2: the page resolves the co-writer Work for the editor Selection Tools; stub
// both Work hooks to "no work" so the page renders the no-co-writer path.
vi.mock('@/features/composition/hooks/useWork', () => ({
  useWorkResolution: () => ({ data: undefined }),
  useChapterScenes: () => ({ data: undefined }),
}));
// C17: the page lists chat models via react-query; stub the API to an empty set.
vi.mock('@/features/ai-models/api', () => ({
  aiModelsApi: { listUserModels: () => Promise.resolve({ items: [] }) },
}));

import { ChapterEditorPage } from '../ChapterEditorPage';
import type { ChapterPublishGate } from '@/features/composition/hooks/usePublishGate';

function renderPage() {
  // The page uses react-query (chat-models, publish gate); provide a client so the
  // render path doesn't throw "No QueryClient set".
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ChapterEditorPage />
    </QueryClientProvider>,
  );
}

const baseGate: ChapterPublishGate = {
  blocked: false, scenesTotal: 3, scenesDone: 3,
  canonBlocked: false, canonUnresolvedScenes: 0, canonUncheckedScenes: 0,
};

beforeEach(() => { mockUseGate.mockReset(); mockGuardedNavigate.mockReset(); localStorage.clear(); });

describe('A2-S4b — ChapterEditorPage: publish-gate unchecked chip', () => {
  it('renders the amber chip when canonUncheckedScenes > 0', async () => {
    mockUseGate.mockReturnValue({ ...baseGate, canonUncheckedScenes: 2 });
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('publish-canon-unchecked')).toBeTruthy();
    });
  });

  it('does NOT render the chip when canonUncheckedScenes === 0', async () => {
    mockUseGate.mockReturnValue(baseGate);
    renderPage();
    // Wait for TiptapEditor stub to confirm initial render settled, then assert absence
    await screen.findByTestId('tiptap-stub');
    expect(screen.queryByTestId('publish-canon-unchecked')).toBeNull();
  });
});

describe('ChapterEditorPage: Workmode switch', () => {
  // The old scatter (classic/AI toggle, Co-write bridge, one-off Translate + Translations
  // buttons) is folded into one Write/Translate/Read/Compose dropdown.
  it('opening Read guarded-navigates to the reader route', async () => {
    mockUseGate.mockReturnValue(baseGate);
    renderPage();
    fireEvent.click(await screen.findByTestId('workmode-switcher'));
    fireEvent.click(screen.getByTestId('workmode-item-read'));
    expect(mockGuardedNavigate).toHaveBeenCalledWith('/books/b1/chapters/c1/read');
  });

  it('switching to Translate swaps the centre to the translation workspace', async () => {
    mockUseGate.mockReturnValue(baseGate);
    renderPage();
    // Default workmode is Write → the editor is shown, not the translation panel.
    await screen.findByTestId('tiptap-stub');
    expect(screen.queryByTestId('xl-panel-stub')).toBeNull();
    fireEvent.click(screen.getByTestId('workmode-switcher'));
    fireEvent.click(screen.getByTestId('workmode-item-translate'));
    expect(await screen.findByTestId('xl-panel-stub')).toBeTruthy();
    // The manuscript editor is no longer mounted in Translate mode.
    expect(screen.queryByTestId('tiptap-stub')).toBeNull();
  });

  it('keeps the manuscript editor mounted in Compose mode', async () => {
    // Regression guard: the co-writer studio inserts generated prose into the editor via
    // its ref (onAccept / onApplyPolish). If Compose unmounted the editor, those writes
    // would silently no-op — so the editor must stay mounted beside the studio.
    mockUseGate.mockReturnValue(baseGate);
    renderPage();
    await screen.findByTestId('tiptap-stub');
    fireEvent.click(screen.getByTestId('workmode-switcher'));
    fireEvent.click(screen.getByTestId('workmode-item-compose'));
    expect(screen.getByTestId('tiptap-stub')).toBeTruthy();
  });
});
