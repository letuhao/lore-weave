import { forwardRef } from 'react';
import { render, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { IDockviewPanelProps } from 'dockview-react';

// #16 P1 (Lane C — spec 09) — EditorPanel must hand the Tier-4 hoist's own applyProposedEdit
// action to the editor bridge, not just the raw handle ref, so ProposeEditCard's Apply routes
// through the hoist (see ManuscriptUnitProvider.applyProposedEdit + editorBridge.ts).

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));

const registerEditorTarget = vi.fn();
vi.mock('@/features/chat/context/editorBridge', () => ({
  registerEditorTarget: (...a: unknown[]) => registerEditorTarget(...a),
}));

vi.mock('@/components/editor/TiptapEditor', () => ({ TiptapEditor: forwardRef(() => null) }));
const sceneRailSpy = vi.hoisted(() => vi.fn());
vi.mock('../../manuscript/SceneRail', () => ({ SceneRail: (...a: unknown[]) => { sceneRailSpy(...a); return null; } }));
const isMobileState = vi.hoisted(() => ({ value: false }));
vi.mock('@/hooks/useIsMobile', () => ({ useIsMobile: () => isMobileState.value }));
// #16 1.2/1.3/1.4 — out of scope for this file (which tests ONLY the P1 registration wiring);
// stub them out rather than pulling in auth/query-client providers these sections need for real.
vi.mock('../../manuscript/unit/useManuscriptCheckpoints', () => ({
  useManuscriptCheckpoints: () => ({
    applyProposedEdit, visibleCheckpoints: [], restore: vi.fn(),
  }),
}));
vi.mock('../../manuscript/unit/ManuscriptCheckpoints', () => ({ ManuscriptCheckpoints: () => null }));
vi.mock('../RevisionHistorySection', () => ({ RevisionHistorySection: () => null }));
vi.mock('../EditorPublishGate', () => ({ EditorPublishGate: () => null }));
// M3 — the empty-state "start your first chapter" door; it needs the query-client/auth providers,
// so stub it here (its own path is tested via useChapterDoor + the navigator/live QC).
vi.mock('../../manuscript/useChapterDoor', () => ({ useChapterDoor: () => ({ startNewChapter: () => {}, creating: false }) }));
// #16 Phase 2 (2.1-2.6) — same rationale: out of scope for the P1 registration test, stub every
// editor-craft addition rather than pull in the auth/query-client/glossary providers they need.
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
const toggleSpies = vi.hoisted(() => ({ setGrammarEnabled: vi.fn(), toggleFocus: vi.fn() }));
vi.mock('@/hooks/useGrammarCheck', () => ({ useGrammarEnabled: () => [true, toggleSpies.setGrammarEnabled] }));
vi.mock('@/features/composition/hooks/useFocusMode', () => ({
  useFocusMode: () => ({ focusMode: false, setFocusMode: vi.fn(), toggle: toggleSpies.toggleFocus }),
}));
vi.mock('@/features/composition/hooks/useMentionHeatmap', () => ({
  useMentionHeatmap: () => ({ data: [], isLoading: false, isError: false }),
}));
vi.mock('@/features/composition/hooks/useProvenance', () => ({
  useProvenance: () => ({ visible: true, unreviewedCount: 0, toggleVisible: vi.fn(), markAllReviewed: vi.fn() }),
}));
vi.mock('@/features/composition/components/ProvenanceToolbar', () => ({ ProvenanceToolbar: () => null }));
vi.mock('@/features/composition/components/ProvenanceTag', () => ({ ProvenanceTag: () => null }));
vi.mock('@/features/composition/components/SelectionToolbar', () => ({ SelectionToolbar: () => null }));
vi.mock('@/features/composition/components/InlineAiLayer', () => ({ InlineAiLayer: () => null }));
vi.mock('@/features/composition/hooks/useWork', () => ({ useWorkResolution: () => ({ data: undefined }) }));
vi.mock('@/features/ai-models/api', () => ({ aiModelsApi: { listUserModels: vi.fn(() => Promise.resolve({ items: [] })) } }));
vi.mock('@/features/glossary/api', () => ({ glossaryApi: { listEntityNames: vi.fn(() => Promise.resolve([])) } }));
vi.mock('@/components/editor/GlossaryTooltip', () => ({ GlossaryTooltip: () => null }));
vi.mock('@/components/editor/GlossaryAutocomplete', () => ({ GlossaryAutocomplete: () => null }));
vi.mock('@tanstack/react-query', () => ({ useQuery: () => ({ data: undefined, isLoading: false }) }));

const applyProposedEdit = vi.hoisted(() => vi.fn(() => true));
const unitState = vi.hoisted(() => ({
  chapterId: 'ch1' as string | null, scenes: [] as { id: string }[],
  isDerivative: false, forked: false,
}));
vi.mock('../../manuscript/unit/ManuscriptUnitProvider', () => ({
  useManuscriptUnit: () => ({
    state: {
      chapterId: unitState.chapterId, scenes: unitState.scenes, loadedBody: {}, saveState: 'idle',
      isDerivative: unitState.isDerivative, forked: unitState.forked,
    },
    isDirty: false,
    editorRef: { current: null },
    save: vi.fn(),
    setBody: vi.fn(),
    applyProposedEdit: vi.fn(() => true),
  }),
}));

import { EditorPanel } from '../EditorPanel';
import { firePasteToEditor } from '@/features/chat/utils/pasteToEditor';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

const dockProps = { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

describe('EditorPanel — #16 P1 hoist-action registration', () => {
  beforeEach(() => {
    registerEditorTarget.mockClear();
    unitState.chapterId = 'ch1';
  });

  it('registers the propose_edit target with the hoist applyProposedEdit action', () => {
    render(<StudioHostProvider bookId="book-1"><EditorPanel {...dockProps} /></StudioHostProvider>);
    expect(registerEditorTarget).toHaveBeenCalledWith(
      expect.objectContaining({ bookId: 'book-1', chapterId: 'ch1', applyProposedEdit }),
    );
  });

  it('does not register when no chapter is open', () => {
    unitState.chapterId = null;
    render(<StudioHostProvider bookId="book-1"><EditorPanel {...dockProps} /></StudioHostProvider>);
    expect(registerEditorTarget).not.toHaveBeenCalled();
  });

  it('clears the target on unmount', () => {
    const { unmount } = render(<StudioHostProvider bookId="book-1"><EditorPanel {...dockProps} /></StudioHostProvider>);
    registerEditorTarget.mockClear();
    unmount();
    expect(registerEditorTarget).toHaveBeenCalledWith(null);
  });
});

// #16 2.1/2.2/2.3 — editor-craft toolbar toggles. Deep behavioral proof (does grammar actually
// flag an error, does heatmap actually tint, does focus actually dim/scroll) is the live browser
// smoke per spec 16's Phase 2 gate — TiptapEditor is mocked out here, so this suite only proves
// the toggles are wired to their hooks, not the underlying ProseMirror decoration.
describe('EditorPanel — #16 2.1/2.2 editor-craft toggles', () => {
  beforeEach(() => {
    toggleSpies.setGrammarEnabled.mockClear();
    toggleSpies.toggleFocus.mockClear();
  });

  it('clicking the grammar toggle calls the persisted setter', () => {
    const { getByTestId } = render(<StudioHostProvider bookId="book-1"><EditorPanel {...dockProps} /></StudioHostProvider>);
    fireEvent.click(getByTestId('studio-editor-toggle-grammar'));
    expect(toggleSpies.setGrammarEnabled).toHaveBeenCalledWith(false); // starts true (mocked)
  });

  it('clicking the focus toggle calls the persisted toggle', () => {
    const { getByTestId } = render(<StudioHostProvider bookId="book-1"><EditorPanel {...dockProps} /></StudioHostProvider>);
    fireEvent.click(getByTestId('studio-editor-toggle-focus'));
    expect(toggleSpies.toggleFocus).toHaveBeenCalled();
  });

  it('clicking the heatmap toggle flips local state (no crash, no hook dependency)', () => {
    const { getByTestId } = render(<StudioHostProvider bookId="book-1"><EditorPanel {...dockProps} /></StudioHostProvider>);
    const btn = getByTestId('studio-editor-toggle-heatmap');
    expect(() => fireEvent.click(btn)).not.toThrow();
  });

  // #16 2.4 gap fix — glossaryEnabled existed but had no visible toolbar control before this.
  it('clicking the glossary toggle flips local state (no crash, no hook dependency)', () => {
    const { getByTestId } = render(<StudioHostProvider bookId="book-1"><EditorPanel {...dockProps} /></StudioHostProvider>);
    const btn = getByTestId('studio-editor-toggle-glossary');
    expect(() => fireEvent.click(btn)).not.toThrow();
  });
});

// #16 Phase 4 (M6) — the Scene Rail's fixed w-56 leaves too little room for prose on a narrow
// viewport (confirmed live: a real chapter's words wrapped one-per-line). The auto-default must
// stay closed on mobile even when the chapter has scenes; the toggle button still opens it.
describe('EditorPanel — #16 Phase 4 Scene Rail mobile default', () => {
  beforeEach(() => {
    sceneRailSpy.mockClear();
    unitState.scenes = [{ id: 's1' }];
    isMobileState.value = false;
  });

  it('auto-opens the Scene Rail on desktop when the chapter has scenes', () => {
    render(<StudioHostProvider bookId="book-1"><EditorPanel {...dockProps} /></StudioHostProvider>);
    expect(sceneRailSpy).toHaveBeenCalled();
  });

  it('does not auto-open the Scene Rail on mobile even when the chapter has scenes', () => {
    isMobileState.value = true;
    render(<StudioHostProvider bookId="book-1"><EditorPanel {...dockProps} /></StudioHostProvider>);
    expect(sceneRailSpy).not.toHaveBeenCalled();
  });

  it('the Scenes toggle button still opens the rail on mobile when clicked', () => {
    isMobileState.value = true;
    const { getByTestId } = render(<StudioHostProvider bookId="book-1"><EditorPanel {...dockProps} /></StudioHostProvider>);
    fireEvent.click(getByTestId('studio-editor-toggle-scenes'));
    expect(sceneRailSpy).toHaveBeenCalled();
  });
});

// D-CHAPTER-READER-MODE — the "Reader" toolbar button opens the existing book-reader
// singleton with the ACTIVE book + currently-open chapter, reusing the same host.openPanel
// seam BooksBrowserPanel uses for another book (no forked reader implementation).
describe('EditorPanel — D-CHAPTER-READER-MODE reader entry point', () => {
  beforeEach(() => { hostRef = null; unitState.chapterId = 'ch1'; });

  it('clicking Reader opens book-reader with the active book + chapter', () => {
    const { getByTestId } = render(
      <StudioHostProvider bookId="book-1"><HostProbe /><EditorPanel {...dockProps} /></StudioHostProvider>,
    );
    const openPanel = vi.spyOn(hostRef!, 'openPanel');
    fireEvent.click(getByTestId('studio-editor-open-reader'));
    expect(openPanel).toHaveBeenCalledWith('book-reader', { params: { bookId: 'book-1', chapterId: 'ch1' } });
  });
});

// D-COMPOSE-SEND-TO-EDITOR — Compose's "Send to Editor" (message menu + Output card) fired
// PASTE_TO_EDITOR_EVENT with NO listener anywhere in the codebase before this fix — a dead
// button. EditorPanel is a singleton dock panel (one hoisted unit per book), so a plain
// window-scoped listener is safe here.
describe('EditorPanel — D-COMPOSE-SEND-TO-EDITOR', () => {
  beforeEach(() => { applyProposedEdit.mockClear(); unitState.chapterId = 'ch1'; });

  it('inserts the pasted text via the checkpoint-wrapped applyProposedEdit seam', () => {
    render(<StudioHostProvider bookId="book-1"><EditorPanel {...dockProps} /></StudioHostProvider>);
    firePasteToEditor({ text: 'Some AI-generated prose.' });
    expect(applyProposedEdit).toHaveBeenCalledWith(
      expect.objectContaining({ operation: 'insert_at_cursor', text: 'Some AI-generated prose.' }),
    );
  });
});

// D-S5-DERIVATIVE-MANUSCRIPT-FORK — the fork-isolation banner + merge affordance. The banner gates
// on the hoist's isDerivative/forked (the ManuscriptUnitProvider routes the actual draft I/O — its
// own suite proves the isolation). Here we prove the EDITOR surfaces the right state + affordance.
describe('EditorPanel — dị bản fork isolation banner + merge affordance', () => {
  beforeEach(() => { unitState.chapterId = 'ch1'; unitState.isDerivative = false; unitState.forked = false; });

  it('shows NO derivative banner on the canonical Work', () => {
    unitState.isDerivative = false;
    const { queryByTestId } = render(<StudioHostProvider bookId="book-1"><EditorPanel {...dockProps} /></StudioHostProvider>);
    expect(queryByTestId('studio-editor-derivative-guard')).toBeNull();
  });

  it('on a dị bản still inheriting canon: shows the fork-state indicator, NO merge button', () => {
    unitState.isDerivative = true; unitState.forked = false;
    const { getByTestId, queryByTestId } = render(<StudioHostProvider bookId="book-1"><EditorPanel {...dockProps} /></StudioHostProvider>);
    expect(getByTestId('studio-editor-derivative-guard')).toBeTruthy();
    expect(getByTestId('studio-editor-fork-state').textContent).toMatch(/mirrors canon|FORKS it/i);
    expect(queryByTestId('studio-editor-merge-canon')).toBeNull();  // nothing to merge yet
  });

  it('on a FORKED chapter: shows the isolated state + a Merge-to-canon button (two-step confirm)', () => {
    unitState.isDerivative = true; unitState.forked = true;
    const { getByTestId } = render(<StudioHostProvider bookId="book-1"><EditorPanel {...dockProps} /></StudioHostProvider>);
    expect(getByTestId('studio-editor-fork-state').textContent).toMatch(/FORKED|isolated/i);
    const merge = getByTestId('studio-editor-merge-canon');
    expect(merge.textContent).toMatch(/merge to canon/i);
    // first click ARMS the confirm (does not merge)
    fireEvent.click(merge);
    expect(getByTestId('studio-editor-merge-canon').textContent).toMatch(/confirm/i);
  });
});
