import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const { autoMutate, critiqueMutate } = vi.hoisted(() => ({ autoMutate: vi.fn(), critiqueMutate: vi.fn() }));
vi.mock('../useAutoGenerate', () => ({
  useAutoGenerate: () => ({ mutate: autoMutate, isPending: false }),
  useCorrection: () => ({ mutate: vi.fn() }),
}));
vi.mock('../useCritique', () => ({
  useCritique: () => ({ critique: { mutate: critiqueMutate }, dismiss: { mutate: vi.fn() } }),
}));

import { useWhatIfTakes } from '../useWhatIfTakes';

beforeEach(() => { autoMutate.mockReset(); critiqueMutate.mockReset(); });

describe('useWhatIfTakes (WS-B3 M2 — generate + judge orchestration)', () => {
  it('generateTake: diverge on the anchor (canon) → ghost → judge, writing each stage to updateAlt', () => {
    const judge = { coherence: 7, voice_match: 6, pacing: 5, canon_consistency: 8, violations: [] };
    autoMutate.mockImplementation((_v, opts) => opts.onSuccess({ job_id: 'j1', text: 'ALT PROSE' }));
    critiqueMutate.mockImplementation((_v, opts) => opts.onSuccess({ critic: judge }));
    const updateAlt = vi.fn();
    const { result } = renderHook(() => useWhatIfTakes({ projectId: 'proj', token: 't', updateAlt }));

    act(() => result.current.generateTake('a1', 'scene-1', { modelRef: 'm1', modelKind: 'openai', modelName: 'gpt' }));

    // generate runs the auto (diverge→converge) path on the ANCHOR scene, on the CANON
    // project, with the REAL 'draft_scene' op (the K candidates are the divergence).
    expect(autoMutate.mock.calls[0][0]).toMatchObject({
      projectId: 'proj', outlineNodeId: 'scene-1', operation: 'draft_scene', modelRef: 'm1',
    });
    // stage 1: generating (clears any prior take); stage 2: ready + ghost (judge null);
    // stage 3: judge folded in
    expect(updateAlt).toHaveBeenNthCalledWith(1, 'a1', { status: 'generating', take: undefined });
    expect(updateAlt).toHaveBeenNthCalledWith(2, 'a1', { status: 'ready', take: { ghost: 'ALT PROSE', jobId: 'j1', judge: null } });
    expect(updateAlt).toHaveBeenNthCalledWith(3, 'a1', { take: { ghost: 'ALT PROSE', jobId: 'j1', judge } });
  });

  it('generateTake with no model is a no-op (never calls the generator)', () => {
    const updateAlt = vi.fn();
    const { result } = renderHook(() => useWhatIfTakes({ projectId: 'proj', token: 't', updateAlt }));
    act(() => result.current.generateTake('a1', 'scene-1', { modelRef: '' }));
    expect(autoMutate).not.toHaveBeenCalled();
    expect(updateAlt).not.toHaveBeenCalled();
  });

  it('a generation error sets the alt to error', () => {
    autoMutate.mockImplementation((_v, opts) => opts.onError(new Error('boom')));
    const updateAlt = vi.fn();
    const { result } = renderHook(() => useWhatIfTakes({ projectId: 'proj', token: 't', updateAlt }));
    act(() => result.current.generateTake('a1', 'scene-1', { modelRef: 'm1' }));
    expect(updateAlt).toHaveBeenLastCalledWith('a1', { status: 'error' });
  });
});
