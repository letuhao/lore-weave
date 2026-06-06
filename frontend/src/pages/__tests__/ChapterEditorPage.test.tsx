// A2-S4b: regression-lock the amber "unchecked" chip wire-up in ChapterEditorPage.
// The pure publishGateMessages function is tested in usePublishGate.test.tsx;
// this file covers only the page-level render path: hook result → conditional chip.
import { forwardRef } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// vi.hoisted so the fn is in-scope inside vi.mock factory closures (vitest hoisting rule)
const { mockUseGate } = vi.hoisted(() => ({ mockUseGate: vi.fn() }));

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
    setIsDirty: vi.fn(), guardedNavigate: vi.fn(),
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
vi.mock('@/components/editor/ImageBlockNode', () => ({
  setImageUploadContext: vi.fn(), setOnOpenHistory: vi.fn(),
}));
vi.mock('@/components/editor/VideoBlockNode', () => ({ setOnOpenVideoHistory: vi.fn() }));
vi.mock('@/features/books/components/PublishControl', () => ({
  PublishControl: (props: any) => (
    <button data-testid="publish-ctrl" disabled={!!props.blockedReason}>Publish</button>
  ),
}));
vi.mock('@/features/chat/Chat', () => ({ Chat: () => null }));
vi.mock('@/features/composition/components/CompositionPanel', () => ({
  CompositionPanel: () => null,
}));
vi.mock('@/features/chat/context/sendToChat', () => ({ fireSendToChat: vi.fn() }));
vi.mock('@/features/chat/context/editorBridge', () => ({ registerEditorTarget: vi.fn() }));

import { ChapterEditorPage } from '../ChapterEditorPage';
import type { ChapterPublishGate } from '@/features/composition/hooks/usePublishGate';

const baseGate: ChapterPublishGate = {
  blocked: false, scenesTotal: 3, scenesDone: 3,
  canonBlocked: false, canonUnresolvedScenes: 0, canonUncheckedScenes: 0,
};

beforeEach(() => mockUseGate.mockReset());

describe('A2-S4b — ChapterEditorPage: publish-gate unchecked chip', () => {
  it('renders the amber chip when canonUncheckedScenes > 0', async () => {
    mockUseGate.mockReturnValue({ ...baseGate, canonUncheckedScenes: 2 });
    render(<ChapterEditorPage />);
    await waitFor(() => {
      expect(screen.getByTestId('publish-canon-unchecked')).toBeTruthy();
    });
  });

  it('does NOT render the chip when canonUncheckedScenes === 0', async () => {
    mockUseGate.mockReturnValue(baseGate);
    render(<ChapterEditorPage />);
    // Wait for TiptapEditor stub to confirm initial render settled, then assert absence
    await screen.findByTestId('tiptap-stub');
    expect(screen.queryByTestId('publish-canon-unchecked')).toBeNull();
  });
});
