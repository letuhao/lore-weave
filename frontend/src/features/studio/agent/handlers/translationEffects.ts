// #16 Phase 4 (LIVE-SYNC audit, 2026-07-05) — Lane B effect handler for `translation_job_control`
// (cancel/pause execute immediately at A-tier and appear under this exact tool name in the
// tool-call stream). resume/retry re-spend money and dispatch through the shared `confirm_action`
// tool (no translation-specific result shape to route on there) — out of scope, same class as
// `composition_generate`'s confirm-then-dispatch shape (the audit found composition_generate's
// actual write already reaches the reconciler via a separately-matched tool name; translation's
// cancel/pause is the one real gap: `TranslationTab`'s coverage matrix + `ChapterTranslationsPanel`
// never refreshed after an agent cancelled/paused a job while either was open).
import { registerEffectHandler, type EffectContext } from '../effectRegistry';

let registered = false;

export function translationJobControlEffect(ctx: EffectContext): void {
  const { bookId, queryClient } = ctx;
  // TranslationTab.tsx's coverage matrix.
  queryClient.invalidateQueries({ queryKey: ['translation-coverage', bookId] });
  queryClient.invalidateQueries({ queryKey: ['segment-coverage', bookId] });
  // ChapterTranslationsPanel's own refresh-signal sentinel (it has no direct react-query
  // integration for its multi-source loadAll(); this prefix-invalidates every open chapter
  // for this book — cheap, and the exact chapter isn't in translation_job_control's result).
  queryClient.invalidateQueries({ queryKey: ['translation', 'refresh', bookId] });
}

/** Idempotent — register the translation effect handler once. */
export function registerTranslationEffectHandlers(): void {
  if (registered) return;
  registered = true;
  registerEffectHandler(/^translation_job_control/, translationJobControlEffect);
}

/** Test-only: undo the idempotency guard so a test can re-register after clearEffectHandlers(). */
export function _resetTranslationEffectHandlers(): void {
  registered = false;
}
