import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// S1 correction-capture seam: the inline "Continue from cursor" ghost must feed the flywheel —
// Discard = reject, Regenerate = regenerate; Accept/Edit are NOT corrections (H2). This test
// guards those exact signals against the correction mutation.

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));

const streamState = vi.hoisted(() => ({ jobId: 'job-1' as string | null, ghost: 'ghost prose' }));
const streamFns = vi.hoisted(() => ({ start: vi.fn(), stop: vi.fn(), clearGhost: vi.fn() }));
vi.mock('../useCompositionStream', () => ({
  useCompositionStream: () => ({
    get jobId() { return streamState.jobId; },
    get ghost() { return streamState.ghost; },
    streaming: false, error: null, ...streamFns,
  }),
}));
vi.mock('../useCritique', () => ({ useCritique: () => ({ critique: { mutate: vi.fn() } }) }));

const correctionMutate = vi.hoisted(() => vi.fn());
vi.mock('../useAutoGenerate', () => ({ useCorrection: () => ({ mutate: correctionMutate }) }));

vi.mock('../../../../components/editor/TrackedPositions', () => ({
  trackPosition: () => ({ current: () => 5, release: vi.fn() }),
}));

import { useInlineGhost } from '../useInlineGhost';

// A minimal Tiptap editor stub — enough for continueDraft to anchor + commit to insert.
function makeEditor() {
  const run = vi.fn();
  return {
    state: { selection: { from: 5 }, doc: { content: { size: 100 } } },
    view: { coordsAtPos: () => ({ top: 10, bottom: 12, left: 4 }) },
    chain: () => ({ focus: () => ({ insertContentAt: () => ({ run }) }) }),
  } as never;
}

const opts = { projectId: 'p1', sceneId: 's1', modelRef: 'm1', token: 't' };

beforeEach(() => {
  correctionMutate.mockReset();
  streamFns.start.mockReset(); streamFns.stop.mockReset(); streamFns.clearGhost.mockReset();
  streamState.jobId = 'job-1';
});

describe('useInlineGhost — correction capture (S1 flywheel)', () => {
  it('Discard captures a REJECT correction on the current job', () => {
    const { result } = renderHook(() => useInlineGhost(makeEditor(), opts));
    act(() => result.current.continueDraft()); // anchors + starts a stream (jobId job-1)
    act(() => result.current.discard());
    expect(correctionMutate).toHaveBeenCalledWith({ jobId: 'job-1', body: { kind: 'reject' } });
    expect(streamFns.stop).toHaveBeenCalled();
  });

  it('Regenerate captures a REGENERATE correction BEFORE re-streaming', () => {
    const { result } = renderHook(() => useInlineGhost(makeEditor(), opts));
    act(() => result.current.continueDraft());
    streamFns.start.mockClear();
    act(() => result.current.regenerate());
    expect(correctionMutate).toHaveBeenCalledWith({ jobId: 'job-1', body: { kind: 'regenerate' } });
    expect(streamFns.start).toHaveBeenCalled(); // re-streamed after capturing
  });

  it('Accept and Edit are NOT corrections (H2 self-reinforcement guard)', () => {
    const { result } = renderHook(() => useInlineGhost(makeEditor(), opts));
    act(() => result.current.continueDraft());
    act(() => result.current.accept());
    act(() => result.current.edit());
    expect(correctionMutate).not.toHaveBeenCalled();
  });

  it('never fires a correction when there is no generation job', () => {
    streamState.jobId = null;
    const { result } = renderHook(() => useInlineGhost(makeEditor(), opts));
    act(() => result.current.continueDraft());
    act(() => result.current.discard());
    expect(correctionMutate).not.toHaveBeenCalled();
  });
});
