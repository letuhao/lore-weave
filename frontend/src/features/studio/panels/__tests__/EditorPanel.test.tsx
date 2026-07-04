import { forwardRef } from 'react';
import { render } from '@testing-library/react';
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
