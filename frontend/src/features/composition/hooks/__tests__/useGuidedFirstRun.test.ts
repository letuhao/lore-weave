import { renderHook, act } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useGuidedFirstRun } from '../useGuidedFirstRun';

// C17 (WG-4) — guided first-run. On a fresh book the writer is dropped into an
// empty Compose with three empty dropdowns and no next step. This hook turns that
// into a primed Generate: auto-pick the chat model ONLY when exactly one is
// registered, derive whether a first scene must be created, and expose an EXPLICIT
// runGuided() action (NO useEffect-for-events) that creates that first scene once.

type Model = { user_model_id: string; is_active: boolean };

function models(ids: string[]): Model[] {
  return ids.map((id) => ({ user_model_id: id, is_active: true }));
}

describe('useGuidedFirstRun (C17 WG-4)', () => {
  it('auto-picks the chat model ONLY when exactly one is registered', () => {
    const { result } = renderHook(() =>
      useGuidedFirstRun({
        workReady: true,
        scenes: [{ id: 's1' }],
        scenesLoading: false,
        models: models(['m1']),
        modelsLoading: false,
        createScene: vi.fn(),
        chapterId: 'c1',
        newSceneTitle: 'New scene',
      }),
    );
    expect(result.current.soleModelId).toBe('m1');
  });

  it('does NOT auto-pick when ZERO chat models are registered', () => {
    const { result } = renderHook(() =>
      useGuidedFirstRun({
        workReady: true,
        scenes: [{ id: 's1' }],
        scenesLoading: false,
        models: models([]),
        modelsLoading: false,
        createScene: vi.fn(),
        chapterId: 'c1',
        newSceneTitle: 'New scene',
      }),
    );
    expect(result.current.soleModelId).toBeUndefined();
  });

  it('does NOT auto-pick when TWO OR MORE chat models are registered', () => {
    const { result } = renderHook(() =>
      useGuidedFirstRun({
        workReady: true,
        scenes: [{ id: 's1' }],
        scenesLoading: false,
        models: models(['m1', 'm2']),
        modelsLoading: false,
        createScene: vi.fn(),
        chapterId: 'c1',
        newSceneTitle: 'New scene',
      }),
    );
    expect(result.current.soleModelId).toBeUndefined();
  });

  it('flags needsFirstScene when the Work exists with zero scenes', () => {
    const { result } = renderHook(() =>
      useGuidedFirstRun({
        workReady: true,
        scenes: [],
        scenesLoading: false,
        models: models(['m1']),
        modelsLoading: false,
        createScene: vi.fn(),
        chapterId: 'c1',
        newSceneTitle: 'New scene',
      }),
    );
    expect(result.current.needsFirstScene).toBe(true);
  });

  it('does NOT flag needsFirstScene while scenes are still loading or already exist', () => {
    const loading = renderHook(() =>
      useGuidedFirstRun({
        workReady: true, scenes: [], scenesLoading: true,
        models: models(['m1']), modelsLoading: false,
        createScene: vi.fn(), chapterId: 'c1', newSceneTitle: 'New scene',
      }),
    );
    expect(loading.result.current.needsFirstScene).toBe(false);

    const hasScene = renderHook(() =>
      useGuidedFirstRun({
        workReady: true, scenes: [{ id: 's1' }], scenesLoading: false,
        models: models(['m1']), modelsLoading: false,
        createScene: vi.fn(), chapterId: 'c1', newSceneTitle: 'New scene',
      }),
    );
    expect(hasScene.result.current.needsFirstScene).toBe(false);
  });

  it('runGuided() creates exactly ONE first scene and is idempotent (ref-guard, no double-create)', () => {
    const createScene = vi.fn();
    const { result } = renderHook(() =>
      useGuidedFirstRun({
        workReady: true,
        scenes: [],
        scenesLoading: false,
        models: models(['m1']),
        modelsLoading: false,
        createScene,
        chapterId: 'c1',
        newSceneTitle: 'New scene',
      }),
    );
    act(() => result.current.runGuided());
    act(() => result.current.runGuided()); // a 2nd call must NOT create another scene
    expect(createScene).toHaveBeenCalledTimes(1);
    expect(createScene).toHaveBeenCalledWith({ chapter_id: 'c1', title: 'New scene' });
  });

  it('runGuided() does nothing when a scene already exists (never duplicates the writer’s scene)', () => {
    const createScene = vi.fn();
    const { result } = renderHook(() =>
      useGuidedFirstRun({
        workReady: true,
        scenes: [{ id: 's1' }],
        scenesLoading: false,
        models: models(['m1']),
        modelsLoading: false,
        createScene,
        chapterId: 'c1',
        newSceneTitle: 'New scene',
      }),
    );
    act(() => result.current.runGuided());
    expect(createScene).not.toHaveBeenCalled();
  });

  it('markFired() claims the guard so a subsequent runGuided() does NOT create a second scene (double-create race fix)', () => {
    const createScene = vi.fn();
    const { result } = renderHook(() =>
      useGuidedFirstRun({
        workReady: true,
        scenes: [],
        scenesLoading: false,
        models: models(['m1']),
        modelsLoading: false,
        createScene,
        chapterId: 'c1',
        newSceneTitle: 'New scene',
      }),
    );
    // The setup-success path created the scene itself and claims the guard.
    act(() => result.current.markFired());
    // The cue button's runGuided must now no-op (no second "Opening scene").
    act(() => result.current.runGuided());
    expect(createScene).not.toHaveBeenCalled();
  });

  it('resets the one-shot guard when the chapter changes (a fresh chapter can be primed again)', () => {
    const createScene = vi.fn();
    const { result, rerender } = renderHook(
      ({ chapterId }: { chapterId: string }) =>
        useGuidedFirstRun({
          workReady: true,
          scenes: [],
          scenesLoading: false,
          models: models(['m1']),
          modelsLoading: false,
          createScene,
          chapterId,
          newSceneTitle: 'New scene',
        }),
      { initialProps: { chapterId: 'c1' } },
    );
    act(() => result.current.runGuided());
    expect(createScene).toHaveBeenCalledTimes(1);
    // Switch to a new empty chapter — the guard must reset so it can fire again.
    rerender({ chapterId: 'c2' });
    expect(result.current.sceneFired).toBe(false);
    act(() => result.current.runGuided());
    expect(createScene).toHaveBeenCalledTimes(2);
  });

  it('exposes guidedCue=true only once primed (a model is resolvable AND a scene exists or is being created)', () => {
    const primed = renderHook(() =>
      useGuidedFirstRun({
        workReady: true, scenes: [{ id: 's1' }], scenesLoading: false,
        models: models(['m1']), modelsLoading: false,
        createScene: vi.fn(), chapterId: 'c1', newSceneTitle: 'New scene',
      }),
    );
    expect(primed.result.current.guidedCue).toBe(true);

    // No model registered → not primed (the writer must register one first, C15 CTA).
    const noModel = renderHook(() =>
      useGuidedFirstRun({
        workReady: true, scenes: [{ id: 's1' }], scenesLoading: false,
        models: models([]), modelsLoading: false,
        createScene: vi.fn(), chapterId: 'c1', newSceneTitle: 'New scene',
      }),
    );
    expect(noModel.result.current.guidedCue).toBe(false);
  });
});
