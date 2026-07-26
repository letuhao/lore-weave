import { render, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { IDockviewPanelProps } from 'dockview-react';

// S1 · chapter-assemble homes the legacy assemble sub-tab (CompositionPanel-solo) as a dock panel
// and reuses the SAME accept→editor handoff as scene-compose (useAcceptIntoEditor). This guards the
// wiring: solo mode, provider stack, the empty state, and that accept lands in the editor.

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const editorTarget = vi.hoisted(() => ({ value: null as null | { chapterId: string; applyProposedEdit: (p: unknown) => boolean } }));
vi.mock('@/features/chat/context/editorBridge', () => ({ getEditorTarget: () => editorTarget.value }));

// Provider stack (passthrough) — assemble doesn't stream; both are context wrappers here.
vi.mock('@/features/composition/context/LiveStateContext', () => ({
  LiveStateProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('@/features/composition/context/AssembleStateContext', () => ({
  AssembleStateProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const compositionProps = vi.hoisted(() => ({ value: null as null | Record<string, unknown> }));
vi.mock('@/features/composition/components/CompositionPanel', () => ({
  CompositionPanel: (props: Record<string, unknown>) => {
    compositionProps.value = props;
    const onAccept = props.onAccept as (t: string, m?: { model?: string }) => void;
    return <button data-testid="fake-accept" onClick={() => onAccept('STITCHED CHAPTER')}>accept</button>;
  },
}));

const meta = vi.hoisted(() => ({ value: { projectId: 'p1', activeChapterId: 'ch1' } as { projectId: string; activeChapterId: string | null } | null }));
vi.mock('../../manuscript/unit/ManuscriptUnitProvider', () => ({ useManuscriptUnitMeta: () => meta.value }));

const focusManuscriptUnit = vi.hoisted(() => vi.fn());
vi.mock('../../host/StudioHostProvider', () => ({
  useStudioHost: () => ({ bookId: 'book-1', openPanel: vi.fn(), focusManuscriptUnit }),
  useRegisterStudioTool: () => {},
}));

import { ChapterAssemblePanel } from '../ChapterAssemblePanel';

const dockProps = { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;

beforeEach(() => {
  toast.success.mockClear(); toast.error.mockClear(); toast.info.mockClear();
  focusManuscriptUnit.mockClear();
  editorTarget.value = null;
  compositionProps.value = null;
  meta.value = { projectId: 'p1', activeChapterId: 'ch1' };
});

describe('ChapterAssemblePanel', () => {
  it('shows the empty state and does not mount the loop with no active chapter', () => {
    meta.value = { projectId: 'p1', activeChapterId: null };
    const { getByTestId, queryByTestId } = render(<ChapterAssemblePanel {...dockProps} />);
    expect(getByTestId('studio-chapter-assemble-panel')).toBeTruthy();
    expect(queryByTestId('fake-accept')).toBeNull();
  });

  it('mounts CompositionPanel in solo ASSEMBLE mode with book/chapter/token', () => {
    render(<ChapterAssemblePanel {...dockProps} />);
    expect(compositionProps.value).toMatchObject({
      bookId: 'book-1', chapterId: 'ch1', token: 'tok', soloPanel: 'assemble',
    });
  });

  it('accept inserts the assembled chapter into the editor via the shared editorBridge handoff', () => {
    const applyProposedEdit = vi.fn(() => true);
    editorTarget.value = { chapterId: 'ch1', applyProposedEdit };
    const { getByTestId } = render(<ChapterAssemblePanel {...dockProps} />);
    fireEvent.click(getByTestId('fake-accept'));
    expect(applyProposedEdit).toHaveBeenCalledTimes(1);
    expect((applyProposedEdit.mock.calls[0][0] as { text: string }).text).toBe('STITCHED CHAPTER');
    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it('refuses to insert into a different chapter (shared guard)', () => {
    const applyProposedEdit = vi.fn(() => true);
    editorTarget.value = { chapterId: 'ch-OTHER', applyProposedEdit };
    const { getByTestId } = render(<ChapterAssemblePanel {...dockProps} />);
    fireEvent.click(getByTestId('fake-accept'));
    expect(applyProposedEdit).not.toHaveBeenCalled();
    expect(focusManuscriptUnit).toHaveBeenCalledWith('ch1');
  });
});
