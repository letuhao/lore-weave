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
vi.mock('../../manuscript/SceneRail', () => ({ SceneRail: () => null }));
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
const unitState = vi.hoisted(() => ({ chapterId: 'ch1' as string | null }));
vi.mock('../../manuscript/unit/ManuscriptUnitProvider', () => ({
  useManuscriptUnit: () => ({
    state: { chapterId: unitState.chapterId, scenes: [], loadedBody: {}, saveState: 'idle' },
    isDirty: false,
    editorRef: { current: null },
    save: vi.fn(),
    setBody: vi.fn(),
    applyProposedEdit: vi.fn(() => true),
  }),
}));

import { EditorPanel } from '../EditorPanel';
import { StudioHostProvider } from '../../host/StudioHostProvider';

const dockProps = { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;

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
});
