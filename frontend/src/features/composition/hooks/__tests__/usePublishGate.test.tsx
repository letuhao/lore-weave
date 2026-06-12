import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const resolveWorkMock = vi.fn();
const publishGateMock = vi.fn();
vi.mock('../../api', () => ({
  compositionApi: {
    resolveWork: (...a: unknown[]) => resolveWorkMock(...a),
    publishGate: (...a: unknown[]) => publishGateMock(...a),
  },
}));

import { useChapterPublishGate, publishGateMessages, type ChapterPublishGate } from '../usePublishGate';
import type { Work } from '../../types';

// A fake t that echoes key + opts so assertions can see the interpolation args.
const fakeT = (key: string, opts?: Record<string, unknown>) =>
  opts ? `${key}:${JSON.stringify(opts)}` : key;
const baseGate: ChapterPublishGate = {
  blocked: false, scenesTotal: 3, scenesDone: 3,
  canonBlocked: false, canonUnresolvedScenes: 0, canonUncheckedScenes: 0,
};

const WORK: Work = {
  project_id: 'p1', user_id: 'u1', book_id: 'b1',
  active_template_id: null, status: 'active', settings: {}, version: 1,
};

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const render = () =>
  renderHook(() => useChapterPublishGate('b1', 'c1', 'tok'), { wrapper: Wrapper });

beforeEach(() => {
  resolveWorkMock.mockReset();
  publishGateMock.mockReset();
});

describe('useChapterPublishGate', () => {
  it('no composition Work → ungated (blocked:false), gate endpoint never called', async () => {
    // a book with a knowledge project but no marked composition_work
    resolveWorkMock.mockResolvedValue({ status: 'unmarked_single', work: null, candidates: [], book_project_id: 'p1', book_project_ids: [] });
    const { result } = render();
    await waitFor(() => expect(resolveWorkMock).toHaveBeenCalled());
    expect(result.current.blocked).toBe(false);
    expect(publishGateMock).not.toHaveBeenCalled();
  });

  it("Work + not-all-scenes-done → blocked:true with counts", async () => {
    resolveWorkMock.mockResolvedValue({ status: 'found', work: WORK, candidates: [], book_project_id: null, book_project_ids: [] });
    publishGateMock.mockResolvedValue({ chapter_id: 'c1', scenes_total: 3, scenes_done: 1, can_publish: false });
    const { result } = render();
    await waitFor(() => expect(result.current.blocked).toBe(true));
    expect(result.current.scenesTotal).toBe(3);
    expect(result.current.scenesDone).toBe(1);
    expect(publishGateMock).toHaveBeenCalledWith('p1', 'c1', 'tok');
  });

  it('Work + all-scenes-done → ungated (blocked:false)', async () => {
    resolveWorkMock.mockResolvedValue({ status: 'found', work: WORK, candidates: [], book_project_id: null, book_project_ids: [] });
    publishGateMock.mockResolvedValue({ chapter_id: 'c1', scenes_total: 2, scenes_done: 2, can_publish: true });
    const { result } = render();
    await waitFor(() => expect(publishGateMock).toHaveBeenCalled());
    await waitFor(() => expect(result.current.blocked).toBe(false));
    expect(result.current.scenesTotal).toBe(2);
  });

  it('candidates (multi-marked) → uses the first work for the gate', async () => {
    resolveWorkMock.mockResolvedValue({ status: 'candidates', work: null, candidates: [WORK], book_project_id: null, book_project_ids: [] });
    publishGateMock.mockResolvedValue({ chapter_id: 'c1', scenes_total: 1, scenes_done: 0, can_publish: false });
    const { result } = render();
    await waitFor(() => expect(result.current.blocked).toBe(true));
    expect(publishGateMock).toHaveBeenCalledWith('p1', 'c1', 'tok');
  });

  it('A2-S4b: surfaces the gate canon fields (all scenes done but canon-blocked → blocked)', async () => {
    resolveWorkMock.mockResolvedValue({ status: 'found', work: WORK, candidates: [], book_project_id: null, book_project_ids: [] });
    publishGateMock.mockResolvedValue({
      chapter_id: 'c1', scenes_total: 2, scenes_done: 2, can_publish: false,
      canon_blocked: true, canon_unresolved_scenes: 1, canon_unchecked_scenes: 2,
    });
    const { result } = render();
    await waitFor(() => expect(result.current.blocked).toBe(true));
    expect(result.current.canonBlocked).toBe(true);
    expect(result.current.canonUnresolvedScenes).toBe(1);
    expect(result.current.canonUncheckedScenes).toBe(2);
  });

  it('A2-S4b: no Work → canon fields degrade to 0/false (ungated)', async () => {
    resolveWorkMock.mockResolvedValue({ status: 'none', work: null, candidates: [], book_project_id: null, book_project_ids: [] });
    const { result } = render();
    await waitFor(() => expect(resolveWorkMock).toHaveBeenCalled());
    expect(result.current.canonBlocked).toBe(false);
    expect(result.current.canonUnresolvedScenes).toBe(0);
    expect(result.current.canonUncheckedScenes).toBe(0);
  });
});

describe('publishGateMessages (A2-S4b — toolbar reason + warning)', () => {
  it('not blocked, no unchecked → both undefined', () => {
    const r = publishGateMessages(baseGate, fakeT);
    expect(r.blockedReason).toBeUndefined();
    expect(r.uncheckedWarning).toBeUndefined();
  });

  it('pending only → just the pending message', () => {
    const r = publishGateMessages({ ...baseGate, blocked: true, scenesDone: 1 }, fakeT);
    expect(r.blockedReason).toContain('publish.gate_pending');
    expect(r.blockedReason).not.toContain('publish.gate_canon_blocked');
  });

  it('canon-blocked only (all scenes done) → just the canon message', () => {
    const r = publishGateMessages(
      { ...baseGate, blocked: true, scenesDone: 3, canonBlocked: true, canonUnresolvedScenes: 1 }, fakeT);
    expect(r.blockedReason).toContain('publish.gate_canon_blocked');
    expect(r.blockedReason).not.toContain('publish.gate_pending');
  });

  it('BOTH pending and canon-blocked → COMBINED, joined with ;', () => {
    const r = publishGateMessages(
      { ...baseGate, blocked: true, scenesDone: 1, canonBlocked: true, canonUnresolvedScenes: 2 }, fakeT);
    expect(r.blockedReason).toContain('publish.gate_pending');
    expect(r.blockedReason).toContain('publish.gate_canon_blocked');
    expect(r.blockedReason).toContain('; ');
  });

  it('no scenes → the no-scenes message (canon parts not appended)', () => {
    const r = publishGateMessages({ ...baseGate, blocked: true, scenesTotal: 0, scenesDone: 0 }, fakeT);
    expect(r.blockedReason).toBe('publish.gate_no_scenes');
  });

  it('unchecked is a NON-blocking warning, independent of blocked', () => {
    const r = publishGateMessages({ ...baseGate, canonUncheckedScenes: 3 }, fakeT);
    expect(r.blockedReason).toBeUndefined(); // not blocked
    expect(r.uncheckedWarning).toContain('publish.gate_unchecked');
    expect(r.uncheckedWarning).toContain('"count":3');
  });

  it('blocked=true + uncheckedScenes>0 → BOTH blockedReason and uncheckedWarning set', () => {
    const r = publishGateMessages(
      { ...baseGate, blocked: true, scenesDone: 1, canonUncheckedScenes: 2 }, fakeT);
    expect(r.blockedReason).toContain('publish.gate_pending');
    expect(r.uncheckedWarning).toContain('publish.gate_unchecked');
  });

  it('blocked=true with no modeled reason → degrade-open (blockedReason undefined)', () => {
    // regression-lock for the `|| undefined` fallback in publishGateMessages
    const r = publishGateMessages(
      { ...baseGate, blocked: true, scenesDone: 3, scenesTotal: 3, canonBlocked: false }, fakeT);
    expect(r.blockedReason).toBeUndefined();
  });
});
