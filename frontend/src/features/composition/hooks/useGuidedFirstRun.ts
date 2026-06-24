// LOOM Composition (C17 / WG-4) — guided first-run controller.
//
// Setup ("Set up co-writer") used to drop the writer into an empty Compose with
// three empty dropdowns and no next step. This hook turns that into a primed
// Generate so a fresh book reaches a first draft in ≤2 clicks:
//   • auto-pick the chat model ONLY when EXACTLY ONE is registered (never 0/≥2 —
//     auto-selecting the wrong model, or silently picking among several, is worse
//     than asking). The id is read from the registered-model list passed in — there
//     is NO hardcoded model name here (provider invariant).
//   • derive whether a first scene must be created (Work exists, scenes resolved,
//     none yet);
//   • expose an EXPLICIT runGuided() action that creates that one first scene. It is
//     called from the action origin (the "Set up co-writer" success handler / a
//     primed "Start writing" click) — NOT from a useEffect reacting to state
//     (CLAUDE.md: no useEffect-for-events).
//
// ONE-SHOT GUARD (the scene-creation is idempotent across BOTH origins):
//   The two first-scene origins — the setup-success chain and the "Start writing"
//   button — share a single `firedRef`. After a setup that already created the
//   scene, the success handler calls markFired(): the still-live cue button then
//   sees `sceneFired` and no-ops, so the brief window before the outline refetch
//   lands can never produce a SECOND "Opening scene". The guard resets when the
//   chapter changes (a new chapter legitimately needs its own first scene) — done
//   via the explicit chapterId-keyed reset below (a guard reset is synchronization,
//   not event-handling, so a useEffect would be correct; we reset inline in the
//   returned actions instead to keep it effect-free and deterministic).
import { useCallback, useRef } from 'react';

type SceneLike = { id: string };
type ModelLike = { user_model_id: string };

type Opts = {
  /** The co-writer Work has resolved/been created (a project_id exists). */
  workReady: boolean;
  scenes: SceneLike[];
  scenesLoading: boolean;
  /** The user's registered chat models (already filtered to capability=chat, active). */
  models: ModelLike[];
  modelsLoading: boolean;
  createScene: (payload: { chapter_id: string; title: string }) => void;
  chapterId: string;
  newSceneTitle: string;
};

export function useGuidedFirstRun(opts: Opts) {
  const { workReady, scenes, scenesLoading, models, modelsLoading, createScene, chapterId, newSceneTitle } = opts;

  // Auto-pick ONLY the sole registered model. 0 → nothing to pick; ≥2 → ambiguous,
  // let the writer choose (never guess). Purely derived — no effect.
  const soleModelId = !modelsLoading && models.length === 1 ? models[0].user_model_id : undefined;

  const hasModel = models.length > 0;
  // A fresh Work with no scene yet → the guided run should create the first one.
  const needsFirstScene = workReady && !scenesLoading && scenes.length === 0;

  // Primed = the writer can draft now: a chat model is available AND a scene exists
  // (or is about to be created). Drives the contextual "write your opening, then
  // Generate / Continue" cue.
  const guidedCue = workReady && hasModel && (scenes.length > 0 || needsFirstScene);

  // One-shot guard, keyed by chapter: at most one guided first scene per chapter,
  // shared across the setup-success chain and the "Start writing" button. Reset
  // (effect-free) the instant the chapter changes so a fresh chapter can be primed.
  const firedRef = useRef(false);
  const firedForChapterRef = useRef<string | null>(null);
  if (firedForChapterRef.current !== chapterId) {
    firedForChapterRef.current = chapterId;
    firedRef.current = false;
  }

  // The setup-success path created the scene itself (it had the just-returned
  // project_id; the hook's bound mutation can't, the Work hasn't resolved yet).
  // It calls markFired() to claim the guard so the cue's button can't double-create.
  const markFired = useCallback(() => { firedRef.current = true; }, []);

  const runGuided = useCallback(() => {
    if (firedRef.current) return;
    if (!workReady || scenesLoading || scenes.length > 0) return;
    firedRef.current = true;
    createScene({ chapter_id: chapterId, title: newSceneTitle });
  }, [workReady, scenesLoading, scenes.length, createScene, chapterId, newSceneTitle]);

  return { soleModelId, needsFirstScene, guidedCue, runGuided, markFired, sceneFired: firedRef.current };
}
