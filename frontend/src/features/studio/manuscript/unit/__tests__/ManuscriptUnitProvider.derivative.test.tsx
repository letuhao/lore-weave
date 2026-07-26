// D-S5-DERIVATIVE-MANUSCRIPT-FORK — the hoist's WORK-SCOPED draft path. When the active Work is a
// dị bản, load/save route to the composition work-draft store (fork), NOT the shared book draft —
// so editing a derivative NEVER touches canon (the isolation guarantee). This suite proves that
// branch in isolation (the sibling suite covers the canonical path with a null Work).
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, render } from '@testing-library/react';

// A MUTABLE active-Work so a test can flip canonical→derivative mid-run (the deep-link/first-paint
// race the fork reload fixes). Default: the dị bản.
const activeWork = vi.hoisted(() => ({ current: { project_id: 'proj-d', source_work_id: 'src-w' } as { project_id: string; source_work_id?: string } | null }));

const getDraft = vi.fn();
const patchDraft = vi.fn();
vi.mock('@/features/books/api', () => ({ booksApi: { getDraft: (...a: unknown[]) => getDraft(...a), patchDraft: (...a: unknown[]) => patchDraft(...a) } }));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 't' }) }));
vi.mock('@/lib/tiptap-utils', () => ({ addTextSnapshots: (d: unknown) => d, extractText: () => '' }));

// The active Work is a DERIVATIVE (source_work_id set) → the hoist takes the work-draft path.
vi.mock('@/features/composition/hooks/useWork', () => ({ useWorkResolution: () => ({ data: { status: 'ok', work: null, candidates: [] } }) }));
vi.mock('@/features/composition/hooks/useActiveWork', () => ({ useActiveWorkId: () => ({ data: 'proj-d' }) }));
vi.mock('@/features/composition/workSelect', () => ({
  resolveActiveWork: () => activeWork.current,
}));

const progressSpies = vi.hoisted(() => ({ reportProgress: vi.fn(), ensureBaseline: vi.fn() }));
vi.mock('@/features/composition/hooks/useProgress', () => ({
  useReportProgress: () => progressSpies.reportProgress,
  useEnsureBaseline: () => progressSpies.ensureBaseline,
}));

const gwcd = vi.fn();
const pwcd = vi.fn();
vi.mock('@/features/composition/api', () => ({
  compositionApi: {
    listChapterScenes: vi.fn(async () => ({ items: [] })),
    patchNode: vi.fn(),
    getWorkChapterDraft: (...a: unknown[]) => gwcd(...a),
    patchWorkChapterDraft: (...a: unknown[]) => pwcd(...a),
  },
}));
vi.mock('../../../host/StudioHostProvider', () => ({
  useStudioHost: () => ({ bookId: 'b1' }),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  useStudioBusSelector: (sel: any) => sel({ activeChapterId: undefined }),
}));

import { ManuscriptUnitProvider, useManuscriptUnit, type ManuscriptUnitApi } from '../ManuscriptUnitProvider';

const doc = (t: string) => ({ type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: t }] }] });

let api: ManuscriptUnitApi | null = null;
function Consumer() { api = useManuscriptUnit(); return null; }
const renderHoist = () => render(<ManuscriptUnitProvider bookId="b1"><Consumer /></ManuscriptUnitProvider>);

beforeEach(() => {
  getDraft.mockReset(); patchDraft.mockReset(); gwcd.mockReset(); pwcd.mockReset();
  progressSpies.reportProgress.mockReset();
  activeWork.current = { project_id: 'proj-d', source_work_id: 'src-w' };
  api = null;
});

describe('useManuscriptUnit — dị bản work-scoped draft (fork isolation)', () => {
  it('loads the WORK draft (read-through canon), never the book draft', async () => {
    gwcd.mockResolvedValue({ forked: false, inherited: true, body: doc('canon'), draft_version: 0, draft_format: 'json' });
    renderHoist();
    await act(async () => { await api!.openUnit('ch1'); });
    expect(gwcd).toHaveBeenCalledWith('proj-d', 'ch1', 't');
    expect(getDraft).not.toHaveBeenCalled();       // canon read path NOT taken
    expect(api!.state.isDerivative).toBe(true);
    expect(api!.state.forked).toBe(false);          // still inheriting canon
    expect(api!.state.version).toBe(0);             // 0 = the fork token
  });

  it('the FIRST edit FORKS via the work-draft PATCH (expected_version 0) and NEVER touches canon', async () => {
    gwcd.mockResolvedValue({ forked: false, inherited: true, body: doc('canon'), draft_version: 0, draft_format: 'json' });
    pwcd.mockResolvedValue({ forked: true, body: doc('edited'), draft_version: 1 });
    renderHoist();
    await act(async () => { await api!.openUnit('ch1'); });
    act(() => api!.setBody(doc('edited'), 'edited'));
    await act(async () => { await api!.save(); });
    expect(pwcd).toHaveBeenCalledWith('proj-d', 'ch1', expect.objectContaining({ expected_version: 0 }), 't');
    expect(patchDraft).not.toHaveBeenCalled();      // THE ISOLATION GUARANTEE — canon untouched
    expect(api!.state.forked).toBe(true);
    expect(api!.state.version).toBe(1);
  });

  it('an already-forked chapter saves under OCC against its own version', async () => {
    gwcd.mockResolvedValue({ forked: true, inherited: false, body: doc('branch'), draft_version: 5, draft_format: 'json' });
    pwcd.mockResolvedValue({ forked: true, body: doc('edited'), draft_version: 6 });
    renderHoist();
    await act(async () => { await api!.openUnit('ch1'); });
    act(() => api!.setBody(doc('edited'), 'edited'));
    await act(async () => { await api!.save(); });
    expect(pwcd).toHaveBeenCalledWith('proj-d', 'ch1', expect.objectContaining({ expected_version: 5 }), 't');
    expect(patchDraft).not.toHaveBeenCalled();
    expect(api!.state.version).toBe(6);
  });

  it('reloads from the work-draft when the active Work flips canonical→dị bản after load (the race)', async () => {
    // Canonical first — the active-work pref has not resolved yet, so the chapter auto-loads canon.
    activeWork.current = { project_id: 'proj-c' };
    getDraft.mockResolvedValue({ chapter_id: 'ch1', body: doc('canon'), draft_version: 4, text_content: '' });
    gwcd.mockResolvedValue({ forked: false, inherited: true, body: doc('inherit'), draft_version: 0, draft_format: 'json' });
    const { rerender } = render(<ManuscriptUnitProvider bookId="b1"><Consumer /></ManuscriptUnitProvider>);
    await act(async () => { await api!.openUnit('ch1'); });
    expect(getDraft).toHaveBeenCalled();          // loaded canon first
    expect(api!.state.isDerivative).toBe(false);
    expect(gwcd).not.toHaveBeenCalled();
    // The pref resolves → the active Work is now the dị bản. A mount-normalize false-dirty must NOT
    // block the reload (no real text edit happened) — the work-draft is read + the unit switches.
    activeWork.current = { project_id: 'proj-d', source_work_id: 'src-w' };
    await act(async () => {
      rerender(<ManuscriptUnitProvider bookId="b1"><Consumer /></ManuscriptUnitProvider>);
      await Promise.resolve();
    });
    expect(gwcd).toHaveBeenCalledWith('proj-d', 'ch1', 't');
    expect(api!.state.isDerivative).toBe(true);
  });

  it('does NOT reload (and would lose no edits) when the identity flips but a real edit is pending', async () => {
    activeWork.current = { project_id: 'proj-c' };
    getDraft.mockResolvedValue({ chapter_id: 'ch1', body: doc('canon'), draft_version: 4, text_content: '' });
    const { rerender } = render(<ManuscriptUnitProvider bookId="b1"><Consumer /></ManuscriptUnitProvider>);
    await act(async () => { await api!.openUnit('ch1'); });
    // a REAL user edit (text changes from the loaded '' to 'typed')
    act(() => api!.setBody(doc('typed'), 'typed'));
    activeWork.current = { project_id: 'proj-d', source_work_id: 'src-w' };
    await act(async () => {
      rerender(<ManuscriptUnitProvider bookId="b1"><Consumer /></ManuscriptUnitProvider>);
      await Promise.resolve();
    });
    expect(gwcd).not.toHaveBeenCalled();          // the pending edit is preserved, not clobbered
  });

  it('a stale-version save refetches the fork and retries with the fresh version', async () => {
    gwcd.mockResolvedValue({ forked: true, inherited: false, body: doc('branch'), draft_version: 5, draft_format: 'json' });
    pwcd
      .mockRejectedValueOnce(Object.assign(new Error('stale'), { status: 412 }))
      .mockResolvedValueOnce({ forked: true, body: doc('edited'), draft_version: 9 });
    // the refetch after the 412 returns the current version 8
    renderHoist();
    await act(async () => { await api!.openUnit('ch1'); });
    gwcd.mockResolvedValueOnce({ forked: true, inherited: false, body: doc('branch'), draft_version: 8, draft_format: 'json' });
    act(() => api!.setBody(doc('edited'), 'edited'));
    await act(async () => { await api!.save(); });
    expect(pwcd).toHaveBeenCalledTimes(2);
    expect(pwcd.mock.calls[1][2]).toEqual(expect.objectContaining({ expected_version: 8 }));
    expect(api!.state.version).toBe(9);
  });
});
