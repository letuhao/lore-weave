// #16 Phase 1, task 1.2 — port of the legacy `useTurnCheckpoints.test.tsx` assertions onto the
// Studio seam. The legacy hook captured at 3 page-owned seams (onAccept/applyPolish/popout-relay);
// Studio has ONE hoist-owned seam (`ManuscriptUnitApi.applyProposedEdit`), so these tests drive
// `result.current.applyProposedEdit(...)` instead of a bare `capture(...)` call, plus new
// coverage for the G7 dirty-guard on restore (not present in the legacy hook — Studio's
// `isChapterDirty` didn't exist yet when the legacy hook was written).
import { renderHook, act, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ManuscriptUnitApi } from '../ManuscriptUnitProvider';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const listRevisions = vi.fn();
const restoreRevision = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: {
    listRevisions: (...a: unknown[]) => listRevisions(...a),
    restoreRevision: (...a: unknown[]) => restoreRevision(...a),
  },
}));

import { useManuscriptCheckpoints } from '../useManuscriptCheckpoints';

const BOOK = 'b1';
const CH = 'c1';

function makeUnit(overrides: Partial<{
  chapterId: string | null;
  saveState: ManuscriptUnitApi['state']['saveState'];
  applyProposedEditImpl: (p: unknown) => boolean;
  isChapterDirty: (chapterId: string) => boolean;
  reload: () => Promise<void>;
}> = {}): ManuscriptUnitApi {
  const applyProposedEditImpl = overrides.applyProposedEditImpl ?? (() => true);
  return {
    state: {
      chapterId: overrides.chapterId ?? CH,
      loadedBody: { type: 'doc', content: [] },
      savedBody: { type: 'doc', content: [] },
      workingBody: null,
      version: 1,
      textContent: '',
      saveState: overrides.saveState ?? 'idle',
      error: null,
      scenes: [],
      sceneChapterNodeId: null,
    },
    isDirty: false,
    editorRef: { current: null },
    openUnit: vi.fn(),
    setBody: vi.fn(),
    save: vi.fn(),
    revert: vi.fn(),
    reload: overrides.reload ?? vi.fn(async () => {}),
    reloadScenes: vi.fn(),
    isChapterDirty: overrides.isChapterDirty ?? (() => false),
    jumpToScene: vi.fn(() => false),
    anchorScenes: vi.fn(() => null),
    applyProposedEdit: vi.fn(applyProposedEditImpl),
  } as unknown as ManuscriptUnitApi;
}

describe('useManuscriptCheckpoints (#16 1.2)', () => {
  beforeEach(() => {
    listRevisions.mockReset();
    restoreRevision.mockReset();
  });

  it('captures the pre-edit revision as the restore point when applyProposedEdit succeeds', async () => {
    listRevisions.mockResolvedValue({ items: [{ revision_id: 'rev-A' }] });
    const unit = makeUnit();
    const { result } = renderHook(() => useManuscriptCheckpoints(BOOK, unit));
    await waitFor(() => expect(listRevisions).toHaveBeenCalledTimes(1));

    act(() => {
      const ok = result.current.applyProposedEdit({ operation: 'insert_at_cursor', text: 'Once upon a time' });
      expect(ok).toBe(true);
    });

    expect(result.current.checkpoints).toHaveLength(1);
    expect(result.current.checkpoints[0]).toMatchObject({
      chapterId: CH, preRevisionId: 'rev-A', kind: 'insert', count: 1,
    });
    expect(unit.applyProposedEdit).toHaveBeenCalledWith(
      expect.objectContaining({ operation: 'insert_at_cursor', text: 'Once upon a time' }),
    );
  });

  it('does not capture when the underlying applyProposedEdit fails (no live editor)', async () => {
    listRevisions.mockResolvedValue({ items: [{ revision_id: 'rev-A' }] });
    const unit = makeUnit({ applyProposedEditImpl: () => false });
    const { result } = renderHook(() => useManuscriptCheckpoints(BOOK, unit));
    await waitFor(() => expect(listRevisions).toHaveBeenCalledTimes(1));

    act(() => {
      const ok = result.current.applyProposedEdit({ operation: 'insert_at_cursor', text: 'x' });
      expect(ok).toBe(false);
    });

    expect(result.current.checkpoints).toHaveLength(0);
  });

  it('folds consecutive edits that share the same pre-revision (no save committed between them)', async () => {
    listRevisions.mockResolvedValue({ items: [{ revision_id: 'rev-A' }] });
    const unit = makeUnit();
    const { result } = renderHook(() => useManuscriptCheckpoints(BOOK, unit));
    await waitFor(() => expect(listRevisions).toHaveBeenCalledTimes(1));

    act(() => {
      result.current.applyProposedEdit({ operation: 'insert_at_cursor', text: 'first' });
      result.current.applyProposedEdit({ operation: 'insert_at_cursor', text: 'second' });
    });

    expect(result.current.checkpoints).toHaveLength(1);
    expect(result.current.checkpoints[0].count).toBe(2);
    // Fold keeps the FIRST edit's snippet — Restore reverts to before it, not the newest.
    expect(result.current.checkpoints[0].snippet).toBe('first');
  });

  it('replace_selection captures kind "replace"', async () => {
    listRevisions.mockResolvedValue({ items: [{ revision_id: 'rev-A' }] });
    const unit = makeUnit();
    const { result } = renderHook(() => useManuscriptCheckpoints(BOOK, unit));
    await waitFor(() => expect(listRevisions).toHaveBeenCalledTimes(1));

    act(() => {
      result.current.applyProposedEdit({ operation: 'replace_selection', text: 'rewritten' });
    });

    expect(result.current.checkpoints[0].kind).toBe('replace');
  });

  it('visibleCheckpoints only surfaces the currently-open chapter, checkpoints keeps every chapter', async () => {
    listRevisions.mockResolvedValue({ items: [{ revision_id: 'rev-A' }] });
    const unit = makeUnit({ chapterId: CH });
    const { result, rerender } = renderHook(
      ({ u }: { u: ManuscriptUnitApi }) => useManuscriptCheckpoints(BOOK, u),
      { initialProps: { u: unit } },
    );
    await waitFor(() => expect(listRevisions).toHaveBeenCalledTimes(1));
    act(() => { result.current.applyProposedEdit({ operation: 'insert_at_cursor', text: 'ch1 edit' }); });
    expect(result.current.visibleCheckpoints).toHaveLength(1);

    const CH2 = 'c2';
    listRevisions.mockResolvedValue({ items: [{ revision_id: 'rev-B' }] });
    const unit2 = makeUnit({ chapterId: CH2 });
    rerender({ u: unit2 });
    await waitFor(() => expect(listRevisions).toHaveBeenCalledTimes(2));
    act(() => { result.current.applyProposedEdit({ operation: 'insert_at_cursor', text: 'ch2 edit' }); });

    // NOTE: applyProposedEdit reads the LATEST `unit` via an internal ref (updated every render,
    // see the integration fix below), not by rebuilding the callback — the second call still
    // correctly targets ch2 even though the returned `applyProposedEdit` reference never changed.
    expect(result.current.checkpoints).toHaveLength(2);
    expect(result.current.visibleCheckpoints).toHaveLength(1);
    expect(result.current.visibleCheckpoints[0].chapterId).toBe(CH2);
  });

  // Integration fix (caught while wiring #16 1.2 into EditorPanel.tsx): EditorPanel hands
  // `checkpoints.applyProposedEdit` to a registerEditorTarget useEffect specifically engineered
  // (#16 P1 review) to stay stable across keystrokes — a NEW `applyProposedEdit` reference every
  // render would re-fire that effect (unregister+register) on every keystroke. `unit` itself is a
  // new object every hoist state change, so the wrapper must read it via a ref, not close over it.
  it('applyProposedEdit keeps the SAME reference across a chapter switch (EditorPanel effect stability)', () => {
    const unit = makeUnit({ chapterId: CH });
    const { result, rerender } = renderHook(
      ({ u }: { u: ManuscriptUnitApi }) => useManuscriptCheckpoints(BOOK, u),
      { initialProps: { u: unit } },
    );
    const first = result.current.applyProposedEdit;
    // A new `unit` object (as the real hoist produces on every state change), same chapter.
    rerender({ u: makeUnit({ chapterId: CH }) });
    expect(result.current.applyProposedEdit).toBe(first);
  });

  it('restore calls the API, reloads the hoist, and drops the checkpoint when the chapter is clean', async () => {
    listRevisions.mockResolvedValue({ items: [{ revision_id: 'rev-A' }] });
    restoreRevision.mockResolvedValue({});
    const reload = vi.fn(async () => {});
    const unit = makeUnit({ isChapterDirty: () => false, reload });
    const { result } = renderHook(() => useManuscriptCheckpoints(BOOK, unit));
    await waitFor(() => expect(listRevisions).toHaveBeenCalledTimes(1));

    act(() => { result.current.applyProposedEdit({ operation: 'insert_at_cursor', text: 'edit' }); });
    const cpId = result.current.checkpoints[0].id;

    let outcome: Awaited<ReturnType<typeof result.current.restore>> | undefined;
    await act(async () => { outcome = await result.current.restore(cpId); });

    expect(outcome).toEqual({ ok: true });
    expect(restoreRevision).toHaveBeenCalledWith('tok', BOOK, CH, 'rev-A');
    expect(reload).toHaveBeenCalledTimes(1);
    expect(result.current.checkpoints).toHaveLength(0);
  });

  it('G7 — restore is blocked (no API call, checkpoint kept) when the hoist is dirty', async () => {
    listRevisions.mockResolvedValue({ items: [{ revision_id: 'rev-A' }] });
    const reload = vi.fn(async () => {});
    const unit = makeUnit({ isChapterDirty: () => true, reload });
    const { result } = renderHook(() => useManuscriptCheckpoints(BOOK, unit));
    await waitFor(() => expect(listRevisions).toHaveBeenCalledTimes(1));

    act(() => { result.current.applyProposedEdit({ operation: 'insert_at_cursor', text: 'edit' }); });
    const cpId = result.current.checkpoints[0].id;

    let outcome: Awaited<ReturnType<typeof result.current.restore>> | undefined;
    await act(async () => { outcome = await result.current.restore(cpId); });

    expect(outcome).toMatchObject({ ok: false, reason: 'dirty' });
    expect(restoreRevision).not.toHaveBeenCalled();
    expect(reload).not.toHaveBeenCalled();
    expect(result.current.checkpoints).toHaveLength(1);
  });

  it('restore reports no-restore-point when the checkpoint has no restore point (preRevisionId null)', async () => {
    listRevisions.mockResolvedValue({ items: [] }); // no revisions yet
    const unit = makeUnit();
    const { result } = renderHook(() => useManuscriptCheckpoints(BOOK, unit));
    await waitFor(() => expect(listRevisions).toHaveBeenCalledTimes(1));

    act(() => { result.current.applyProposedEdit({ operation: 'insert_at_cursor', text: 'edit' }); });
    const cpId = result.current.checkpoints[0].id;
    expect(result.current.checkpoints[0].preRevisionId).toBeNull();

    let outcome: Awaited<ReturnType<typeof result.current.restore>> | undefined;
    await act(async () => { outcome = await result.current.restore(cpId); });

    expect(outcome).toMatchObject({ ok: false, reason: 'no-restore-point' });
    expect(restoreRevision).not.toHaveBeenCalled();
  });

  it('restore reports not-found for an unknown checkpoint id (defensive)', async () => {
    listRevisions.mockResolvedValue({ items: [{ revision_id: 'rev-A' }] });
    const unit = makeUnit();
    const { result } = renderHook(() => useManuscriptCheckpoints(BOOK, unit));
    await waitFor(() => expect(listRevisions).toHaveBeenCalledTimes(1));

    let outcome: Awaited<ReturnType<typeof result.current.restore>> | undefined;
    await act(async () => { outcome = await result.current.restore('does-not-exist'); });

    expect(outcome).toEqual({ ok: false, reason: 'not-found' });
    expect(restoreRevision).not.toHaveBeenCalled();
  });
});
