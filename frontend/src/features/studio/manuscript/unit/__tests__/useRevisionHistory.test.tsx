// #16 Phase 1, task 1.3 — useRevisionHistory. Mounts the REAL ManuscriptUnitProvider (not a
// hand-rolled mock unit) so "restore updates the hoist" is proven against the actual
// reload()/state.version machinery, not a stubbed call — the brief's "reuse the hoist's existing
// load/reload machinery, don't invent a second state-update path" is only verified this way.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, render, waitFor } from '@testing-library/react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 't' }) }));

const getDraft = vi.fn();
const patchDraft = vi.fn();
const listRevisions = vi.fn();
const restoreRevision = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: {
    getDraft: (...a: unknown[]) => getDraft(...a),
    patchDraft: (...a: unknown[]) => patchDraft(...a),
    listRevisions: (...a: unknown[]) => listRevisions(...a),
    restoreRevision: (...a: unknown[]) => restoreRevision(...a),
  },
}));
vi.mock('@/lib/tiptap-utils', () => ({ addTextSnapshots: (d: unknown) => d, extractText: () => '' }));
vi.mock('@/features/composition/hooks/useWork', () => ({ useWorkResolution: () => ({ data: null }) }));
// Resolve the active-work pref synchronously (null = canonical) so loadChapter never defers (D-S5).
vi.mock('@/features/composition/hooks/useActiveWork', () => ({ useActiveWorkId: () => ({ data: null }) }));
vi.mock('@/features/composition/hooks/useProgress', () => ({
  useReportProgress: () => vi.fn(),
  useEnsureBaseline: () => vi.fn(),
}));
vi.mock('@/features/composition/api', () => ({
  compositionApi: { listChapterScenes: vi.fn(async () => ({ items: [] })), patchNode: vi.fn() },
}));
const bus = vi.hoisted(() => ({ activeChapterId: undefined as string | undefined }));
vi.mock('../../../host/StudioHostProvider', () => ({
  useStudioHost: () => ({ bookId: 'b1' }),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  useStudioBusSelector: (sel: any) => sel({ activeChapterId: bus.activeChapterId }),
}));

import { ManuscriptUnitProvider, useManuscriptUnit, type ManuscriptUnitApi } from '../ManuscriptUnitProvider';
import { useRevisionHistory } from '../useRevisionHistory';

const doc = (t: string) => ({ type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: t }] }] });

type RevisionHistoryHook = ReturnType<typeof useRevisionHistory>;

let unitApi: ManuscriptUnitApi | null = null;
let revApi: RevisionHistoryHook | null = null;

function Harness() {
  const unit = useManuscriptUnit();
  unitApi = unit;
  revApi = useRevisionHistory(unit, 'b1');
  return null;
}
const renderHoist = () => render(<ManuscriptUnitProvider bookId="b1"><Harness /></ManuscriptUnitProvider>);

const REVISIONS_V2 = { items: [
  { revision_id: 'rev-2', created_at: '2026-01-02' },
  { revision_id: 'rev-1', created_at: '2026-01-01' },
], total: 2 };

beforeEach(() => {
  getDraft.mockReset();
  patchDraft.mockReset();
  listRevisions.mockReset();
  restoreRevision.mockReset();
  bus.activeChapterId = undefined;
  unitApi = null;
  revApi = null;
  getDraft.mockResolvedValue({ chapter_id: 'ch1', body: doc('server'), draft_version: 3, text_content: 'server' });
  listRevisions.mockResolvedValue(REVISIONS_V2);
});

describe('useRevisionHistory', () => {
  it('lists revisions for the active chapter (paginated per the existing API shape)', async () => {
    renderHoist();
    await act(async () => { await unitApi!.openUnit('ch1'); });
    await waitFor(() => expect(revApi!.revisions).toHaveLength(2));
    expect(listRevisions).toHaveBeenCalledWith('t', 'b1', 'ch1', { limit: 20, offset: 0 });
    expect(revApi!.total).toBe(2);
    expect(revApi!.hasMore).toBe(false);
  });

  it('re-lists when the active chapter changes', async () => {
    renderHoist();
    await act(async () => { await unitApi!.openUnit('ch1'); });
    await waitFor(() => expect(listRevisions).toHaveBeenCalledWith('t', 'b1', 'ch1', { limit: 20, offset: 0 }));
    listRevisions.mockResolvedValue({ items: [{ revision_id: 'rev-9', created_at: '2026-02-01' }], total: 1 });
    await act(async () => { await unitApi!.openUnit('ch2'); });
    await waitFor(() => expect(listRevisions).toHaveBeenCalledWith('t', 'b1', 'ch2', { limit: 20, offset: 0 }));
    await waitFor(() => expect(revApi!.revisions).toHaveLength(1));
  });

  it('restore-when-clean: calls restoreRevision, then reuses the hoist reload() — version/loadedBody update', async () => {
    restoreRevision.mockResolvedValue({});
    // First getDraft is the initial openUnit load; second is the post-restore reload().
    getDraft
      .mockResolvedValueOnce({ chapter_id: 'ch1', body: doc('server'), draft_version: 3, text_content: 'server' })
      .mockResolvedValueOnce({ chapter_id: 'ch1', body: doc('restored'), draft_version: 4, text_content: 'restored' });
    renderHoist();
    await act(async () => { await unitApi!.openUnit('ch1'); });
    await waitFor(() => expect(revApi!.revisions).toHaveLength(2));
    expect(unitApi!.isDirty).toBe(false);

    let result: Awaited<ReturnType<RevisionHistoryHook['restore']>> | undefined;
    await act(async () => { result = await revApi!.restore('rev-1'); });

    expect(result).toEqual({ ok: true });
    expect(restoreRevision).toHaveBeenCalledWith('t', 'b1', 'ch1', 'rev-1');
    // The hoist's OWN reload machinery ran (getDraft called again) — version/loadedBody now
    // reflect the restored revision, proving there's no separate/parallel state-update path.
    expect(getDraft).toHaveBeenCalledTimes(2);
    expect(unitApi!.state.version).toBe(4);
    expect(unitApi!.state.loadedBody).toEqual(doc('restored'));
    // The list itself was also refreshed post-restore.
    expect(listRevisions).toHaveBeenCalledTimes(2);
  });

  it('restore-blocked-when-dirty: refuses to call the API or the hoist reload, surfaces a blocked signal', async () => {
    renderHoist();
    await act(async () => { await unitApi!.openUnit('ch1'); });
    await waitFor(() => expect(revApi!.revisions).toHaveLength(2));

    act(() => { unitApi!.setBody(doc('unsaved edit'), 'unsaved edit'); });
    expect(unitApi!.isChapterDirty('ch1')).toBe(true);

    let result: Awaited<ReturnType<RevisionHistoryHook['restore']>> | undefined;
    await act(async () => { result = await revApi!.restore('rev-1'); });

    expect(result).toEqual({ ok: false, reason: 'dirty' });
    expect(restoreRevision).not.toHaveBeenCalled();
    expect(getDraft).toHaveBeenCalledTimes(1); // only the initial openUnit load — no reload
    expect(revApi!.blocked).toEqual({ revisionId: 'rev-1', reason: 'dirty' });
    // The unsaved edit is still intact — never clobbered.
    expect(unitApi!.isDirty).toBe(true);
    expect(unitApi!.state.textContent).toBe('unsaved edit');
  });

  it('the blocked banner clears once the hoist becomes clean again (e.g. after a save)', async () => {
    patchDraft.mockResolvedValue(undefined);
    getDraft
      .mockResolvedValueOnce({ chapter_id: 'ch1', body: doc('server'), draft_version: 3, text_content: 'server' })
      .mockResolvedValueOnce({ chapter_id: 'ch1', body: doc('unsaved edit'), draft_version: 4, text_content: 'unsaved edit' });
    renderHoist();
    await act(async () => { await unitApi!.openUnit('ch1'); });
    await waitFor(() => expect(revApi!.revisions).toHaveLength(2));

    act(() => { unitApi!.setBody(doc('unsaved edit'), 'unsaved edit'); });
    await act(async () => { await revApi!.restore('rev-1'); });
    expect(revApi!.blocked).not.toBeNull();

    await act(async () => { await unitApi!.save(); });
    expect(unitApi!.isDirty).toBe(false);
    await waitFor(() => expect(revApi!.blocked).toBeNull());
  });

  it('loadMore accumulates pages using the offset/limit shape listRevisions already exposes', async () => {
    listRevisions.mockImplementation((_t: string, _b: string, _c: string, params: { offset?: number }) => {
      const all = [
        { revision_id: 'rev-3', created_at: '2026-01-03' },
        { revision_id: 'rev-2', created_at: '2026-01-02' },
        { revision_id: 'rev-1', created_at: '2026-01-01' },
      ];
      const offset = params?.offset ?? 0;
      return Promise.resolve({ items: all.slice(offset, offset + 2), total: 3 });
    });
    renderHoist();
    await act(async () => { await unitApi!.openUnit('ch1'); });
    await waitFor(() => expect(revApi!.revisions).toHaveLength(2));
    expect(revApi!.hasMore).toBe(true);

    await act(async () => { await revApi!.loadMore(); });
    await waitFor(() => expect(revApi!.revisions).toHaveLength(3));
    expect(revApi!.hasMore).toBe(false);
    expect(listRevisions).toHaveBeenLastCalledWith('t', 'b1', 'ch1', { limit: 20, offset: 2 });
  });

  it('surfaces an error from restoreRevision without leaving restoringId stuck', async () => {
    restoreRevision.mockRejectedValue(new Error('server exploded'));
    renderHoist();
    await act(async () => { await unitApi!.openUnit('ch1'); });
    await waitFor(() => expect(revApi!.revisions).toHaveLength(2));

    let result: Awaited<ReturnType<RevisionHistoryHook['restore']>> | undefined;
    await act(async () => { result = await revApi!.restore('rev-1'); });

    expect(result).toEqual({ ok: false, reason: 'error', message: 'server exploded' });
    expect(revApi!.error).toBe('server exploded');
    expect(revApi!.restoringId).toBeNull();
  });
});
