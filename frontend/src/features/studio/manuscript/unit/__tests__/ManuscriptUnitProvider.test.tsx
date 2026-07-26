import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { act, render, waitFor } from '@testing-library/react';

// Mock the manuscript I/O stack + the studio host/bus (the hoist reuses these AS-IS).
const getDraft = vi.fn();
const patchDraft = vi.fn();
vi.mock('@/features/books/api', () => ({ booksApi: { getDraft: (...a: unknown[]) => getDraft(...a), patchDraft: (...a: unknown[]) => patchDraft(...a) } }));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 't' }) }));
vi.mock('@/lib/tiptap-utils', () => ({ addTextSnapshots: (d: unknown) => d, extractText: () => '' })); // identity for the test
// #12 — the hoist now resolves the composition Work for scenes[]; this suite exercises the
// body path, so the book has NO Work (scenes stay []) and react-query is bypassed entirely.
vi.mock('@/features/composition/hooks/useWork', () => ({ useWorkResolution: () => ({ data: null }) }));
// Resolve the active-work pref synchronously (null = canonical) so loadChapter never defers (D-S5).
vi.mock('@/features/composition/hooks/useActiveWork', () => ({ useActiveWorkId: () => ({ data: null }) }));
// #16 2.10 — progress-reporting is a best-effort side effect of save()/loadChapter(); this suite
// has no Work (projectId null) so the real hooks would no-op anyway, but they still call
// react-query's useQueryClient() internally — stub them out rather than add a QueryClientProvider.
// Stable spies (vi.hoisted, not a fresh vi.fn() per render) so tests can assert call args.
const progressSpies = vi.hoisted(() => ({ reportProgress: vi.fn(), ensureBaseline: vi.fn() }));
vi.mock('@/features/composition/hooks/useProgress', () => ({
  useReportProgress: () => progressSpies.reportProgress,
  useEnsureBaseline: () => progressSpies.ensureBaseline,
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

const doc = (t: string) => ({ type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: t }] }] });

let api: ManuscriptUnitApi | null = null;
function Consumer() { api = useManuscriptUnit(); return null; }
const renderHoist = () => render(<ManuscriptUnitProvider bookId="b1"><Consumer /></ManuscriptUnitProvider>);

beforeEach(() => {
  getDraft.mockReset();
  patchDraft.mockReset();
  progressSpies.reportProgress.mockReset();
  progressSpies.ensureBaseline.mockReset();
  bus.activeChapterId = undefined;
  api = null;
  getDraft.mockResolvedValue({ chapter_id: 'ch1', body: doc('server'), draft_version: 3, text_content: 'server' });
});

describe('useManuscriptUnit (Tier-4 hoist)', () => {
  it('openUnit loads the draft; not dirty; version captured', async () => {
    renderHoist();
    await act(async () => { await api!.openUnit('ch1'); });
    expect(getDraft).toHaveBeenCalledWith('t', 'b1', 'ch1');
    expect(api!.state.chapterId).toBe('ch1');
    expect(api!.state.version).toBe(3);
    expect(api!.isDirty).toBe(false);
  });

  it('setBody marks dirty; isChapterDirty is scoped to the active chapter', async () => {
    renderHoist();
    await act(async () => { await api!.openUnit('ch1'); });
    act(() => { api!.setBody(doc('edited'), 'edited'); });
    expect(api!.isDirty).toBe(true);
    expect(api!.isChapterDirty('ch1')).toBe(true);
    expect(api!.isChapterDirty('other')).toBe(false); // only the active unit
  });

  it('save PATCHes with expected_draft_version, then re-syncs; clean after', async () => {
    patchDraft.mockResolvedValue(undefined);
    getDraft.mockResolvedValueOnce({ chapter_id: 'ch1', body: doc('server'), draft_version: 3, text_content: 'server' })
            .mockResolvedValueOnce({ chapter_id: 'ch1', body: doc('edited'), draft_version: 4, text_content: 'edited' });
    renderHoist();
    await act(async () => { await api!.openUnit('ch1'); });
    act(() => { api!.setBody(doc('edited'), 'edited'); });
    await act(async () => { await api!.save(); });
    expect(patchDraft).toHaveBeenCalledWith('t', 'b1', 'ch1', expect.objectContaining({ expected_draft_version: 3 }));
    expect(api!.isDirty).toBe(false);
    expect(api!.state.version).toBe(4); // re-synced from the post-save getDraft
  });

  it('save on a 409 conflict retries WITHOUT the version (last-write-wins)', async () => {
    patchDraft
      .mockRejectedValueOnce(Object.assign(new Error('conflict'), { code: 'CHAPTER_DRAFT_CONFLICT', status: 409 }))
      .mockResolvedValueOnce(undefined);
    renderHoist();
    await act(async () => { await api!.openUnit('ch1'); });
    act(() => { api!.setBody(doc('edited'), 'edited'); });
    await act(async () => { await api!.save(); });
    expect(patchDraft).toHaveBeenCalledTimes(2);
    expect(patchDraft.mock.calls[1][3]).not.toHaveProperty('expected_draft_version');
  });

  it('dirty-flush: switching chapter while dirty SAVES first, then loads the new chapter', async () => {
    patchDraft.mockResolvedValue(undefined);
    renderHoist();
    await act(async () => { await api!.openUnit('ch1'); });
    act(() => { api!.setBody(doc('edited'), 'edited'); }); // dirty
    await act(async () => { await api!.openUnit('ch2'); });
    expect(patchDraft).toHaveBeenCalled();          // flushed ch1
    expect(api!.state.chapterId).toBe('ch2');        // now on ch2
  });

  it('bus-driven: an activeChapterId change opens that chapter (navigator/focus seam)', async () => {
    const { rerender } = renderHoist();
    bus.activeChapterId = 'ch9';
    rerender(<ManuscriptUnitProvider bookId="b1"><Consumer /></ManuscriptUnitProvider>);
    await waitFor(() => expect(api!.state.chapterId).toBe('ch9'));
    expect(getDraft).toHaveBeenCalledWith('t', 'b1', 'ch9');
  });

  // #16 P1 (Lane C — spec 09) — applyProposedEdit is the hoist-owned write action ProposeEditCard
  // now prefers over reaching into a raw editorRef via the global editorBridge singleton.
  describe('applyProposedEdit (#16 P1)', () => {
    it('delegates to the live editorRef.replaceSelection for a replace_selection proposal', async () => {
      renderHoist();
      await act(async () => { await api!.openUnit('ch1'); });
      const replaceSelection = vi.fn(() => true);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      api!.editorRef.current = { replaceSelection, insertAtCursor: vi.fn(() => false) } as any;
      const prov = { source: 'ai' as const, status: 'unreviewed' as const, ts: 'now' };
      const ok = api!.applyProposedEdit({ operation: 'replace_selection', text: 'new text', provenance: prov });
      expect(ok).toBe(true);
      expect(replaceSelection).toHaveBeenCalledWith('new text', prov);
    });

    it('delegates to the live editorRef.insertAtCursor for an insert_at_cursor proposal', async () => {
      renderHoist();
      await act(async () => { await api!.openUnit('ch1'); });
      const insertAtCursor = vi.fn(() => true);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      api!.editorRef.current = { replaceSelection: vi.fn(() => false), insertAtCursor } as any;
      const ok = api!.applyProposedEdit({ operation: 'insert_at_cursor', text: 'inserted' });
      expect(ok).toBe(true);
      expect(insertAtCursor).toHaveBeenCalledWith('inserted', undefined);
    });

    it('returns false with no live editor mounted (never throws)', async () => {
      renderHoist();
      await act(async () => { await api!.openUnit('ch1'); });
      api!.editorRef.current = null;
      expect(api!.applyProposedEdit({ operation: 'insert_at_cursor', text: 'x' })).toBe(false);
    });
  });

  // #16 2.9 — auto-save: a debounced 5-minute idle-save while dirty.
  describe('auto-save (#16 2.9)', () => {
    beforeEach(() => { vi.useFakeTimers(); });
    afterEach(() => { vi.useRealTimers(); });

    it('fires save() after the debounce window while dirty', async () => {
      patchDraft.mockResolvedValue(undefined);
      renderHoist();
      await act(async () => { await api!.openUnit('ch1'); });
      act(() => { api!.setBody(doc('edited'), 'edited'); });
      expect(patchDraft).not.toHaveBeenCalled();
      await act(async () => { await vi.advanceTimersByTimeAsync(300_000); });
      expect(patchDraft).toHaveBeenCalled();
    });

    it('a manual save cancels the pending auto-save timer (no double-save)', async () => {
      patchDraft.mockResolvedValue(undefined);
      renderHoist();
      await act(async () => { await api!.openUnit('ch1'); });
      act(() => { api!.setBody(doc('edited'), 'edited'); });
      await act(async () => { await api!.save(); });
      patchDraft.mockClear();
      await act(async () => { await vi.advanceTimersByTimeAsync(300_000); });
      expect(patchDraft).not.toHaveBeenCalled(); // already clean — nothing to auto-save
    });

    it('does not fire when the doc is clean', async () => {
      renderHoist();
      await act(async () => { await api!.openUnit('ch1'); });
      await act(async () => { await vi.advanceTimersByTimeAsync(300_000); });
      expect(patchDraft).not.toHaveBeenCalled();
    });
  });

  // #16 2.10 — progress-reporting + baseline: a Tier-4 side effect of save()/loadChapter().
  describe('progress-reporting (#16 2.10)', () => {
    it('reports the post-save word count after a successful save', async () => {
      patchDraft.mockResolvedValue(undefined);
      getDraft.mockResolvedValueOnce({ chapter_id: 'ch1', body: doc('server'), draft_version: 3, text_content: 'server' })
              .mockResolvedValueOnce({ chapter_id: 'ch1', body: doc('edited'), draft_version: 4, text_content: 'two words' });
      renderHoist();
      await act(async () => { await api!.openUnit('ch1'); });
      act(() => { api!.setBody(doc('two words'), 'two words'); });
      await act(async () => { await api!.save(); });
      expect(progressSpies.reportProgress).toHaveBeenCalledWith('ch1', 2);
    });

    it('does not report progress when save is a no-op (not dirty)', async () => {
      renderHoist();
      await act(async () => { await api!.openUnit('ch1'); });
      await act(async () => { await api!.save(); });
      expect(progressSpies.reportProgress).not.toHaveBeenCalled();
    });
  });
});
