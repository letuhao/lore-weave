import { render, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { IDockviewPanelProps } from 'dockview-react';

// S1 · scene-compose is a THIN wrapper: it homes the legacy compose loop (CompositionPanel-solo)
// as a studio dock panel and wires the ONE studio-specific seam — accept→editor via editorBridge.
// This test guards that seam + the no-silent-fail guard + the no-chapter empty state, WITHOUT
// mounting the heavy CompositionPanel (mocked) or the real providers.

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('sonner', () => ({ toast }));

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

// getEditorTarget is the module-singleton the studio EditorPanel registers; drive it per test.
// It carries the chapterId the editor currently holds — the wrapper must refuse to insert into a
// chapter other than the scene's active one.
const editorTarget = vi.hoisted(() => ({ value: null as null | { chapterId: string; applyProposedEdit: (p: unknown) => boolean } }));
vi.mock('@/features/chat/context/editorBridge', () => ({
  getEditorTarget: () => editorTarget.value,
}));

// LiveStateProvider must wrap CompositionPanel (ComposeView.useLiveStream throws without it) —
// here a passthrough; the point tested is that the wrapper mounts the loop, not the stream itself.
vi.mock('@/features/composition/context/LiveStateContext', () => ({
  LiveStateProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// Capture the props the wrapper hands the composition loop + expose an Accept trigger.
const compositionProps = vi.hoisted(() => ({ value: null as null | Record<string, unknown> }));
vi.mock('@/features/composition/components/CompositionPanel', () => ({
  CompositionPanel: (props: Record<string, unknown>) => {
    compositionProps.value = props;
    const onAccept = props.onAccept as (t: string, m?: { model?: string }) => void;
    return <button data-testid="fake-accept" onClick={() => onAccept('DRAFT PROSE', { model: 'qwen' })}>accept</button>;
  },
}));

const meta = vi.hoisted(() => ({ value: { projectId: 'p1', activeChapterId: 'ch1' } as { projectId: string; activeChapterId: string | null } | null }));
vi.mock('../../manuscript/unit/ManuscriptUnitProvider', () => ({
  useManuscriptUnitMeta: () => meta.value,
}));

const openPanel = vi.hoisted(() => vi.fn());
const focusManuscriptUnit = vi.hoisted(() => vi.fn());
vi.mock('../../host/StudioHostProvider', () => ({
  useStudioHost: () => ({ bookId: 'book-1', openPanel, focusManuscriptUnit }),
  useRegisterStudioTool: () => {},
}));

import { SceneComposePanel } from '../SceneComposePanel';

const dockProps = { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;

beforeEach(() => {
  toast.success.mockClear(); toast.error.mockClear(); toast.info.mockClear();
  openPanel.mockClear(); focusManuscriptUnit.mockClear();
  editorTarget.value = null;
  compositionProps.value = null;
  meta.value = { projectId: 'p1', activeChapterId: 'ch1' };
});

describe('SceneComposePanel', () => {
  it('shows the "pick a chapter" empty state and does NOT mount the compose loop when no chapter is active', () => {
    meta.value = { projectId: 'p1', activeChapterId: null };
    const { getByTestId, queryByTestId } = render(<SceneComposePanel {...dockProps} />);
    expect(getByTestId('studio-scene-compose-panel')).toBeTruthy();
    expect(queryByTestId('fake-accept')).toBeNull(); // CompositionPanel not mounted
  });

  it('mounts CompositionPanel in solo compose mode with book/chapter/token when a chapter is active', () => {
    render(<SceneComposePanel {...dockProps} />);
    expect(compositionProps.value).toMatchObject({
      bookId: 'book-1', chapterId: 'ch1', token: 'tok', soloPanel: 'compose',
    });
  });

  it('accept inserts the prose into the editor via editorBridge (insert_at_cursor + AI provenance)', () => {
    const applyProposedEdit = vi.fn(() => true);
    editorTarget.value = { chapterId: 'ch1', applyProposedEdit }; // editor is on the SAME chapter
    const { getByTestId } = render(<SceneComposePanel {...dockProps} />);
    fireEvent.click(getByTestId('fake-accept'));
    expect(applyProposedEdit).toHaveBeenCalledTimes(1);
    const arg = applyProposedEdit.mock.calls[0][0] as { operation: string; text: string; provenance: { source: string; model: string | null } };
    expect(arg.operation).toBe('insert_at_cursor');
    expect(arg.text).toBe('DRAFT PROSE');
    expect(arg.provenance.source).toBe('ai');
    expect(arg.provenance.model).toBe('qwen');
    expect(toast.success).toHaveBeenCalledTimes(1);
    expect(focusManuscriptUnit).not.toHaveBeenCalled();
  });

  it('accept with NO editor open never silently drops the prose — focuses this chapter and tells the user', () => {
    editorTarget.value = null; // no chapter open in the editor
    const { getByTestId } = render(<SceneComposePanel {...dockProps} />);
    fireEvent.click(getByTestId('fake-accept'));
    expect(focusManuscriptUnit).toHaveBeenCalledWith('ch1');
    expect(toast.info).toHaveBeenCalledTimes(1);
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('refuses to insert into a DIFFERENT chapter (never corrupts the wrong manuscript)', () => {
    const applyProposedEdit = vi.fn(() => true);
    editorTarget.value = { chapterId: 'ch-OTHER', applyProposedEdit }; // editor drifted to another chapter
    const { getByTestId } = render(<SceneComposePanel {...dockProps} />);
    fireEvent.click(getByTestId('fake-accept'));
    expect(applyProposedEdit).not.toHaveBeenCalled(); // did NOT write into ch-OTHER
    expect(focusManuscriptUnit).toHaveBeenCalledWith('ch1');
    expect(toast.info).toHaveBeenCalledTimes(1);
  });

  it('surfaces an error (no silent fail) when the editor rejects the insert', () => {
    editorTarget.value = { chapterId: 'ch1', applyProposedEdit: vi.fn(() => false) };
    const { getByTestId } = render(<SceneComposePanel {...dockProps} />);
    fireEvent.click(getByTestId('fake-accept'));
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.success).not.toHaveBeenCalled();
  });
});
