// #09 Lane B — authoring runs. The reconciler's header comment used to claim "authoring_run has no
// MCP tools at all, REST-only, no Studio consumer to go stale". BOTH halves were false: server.py
// registers 11 composition_authoring_run_* tools (from :1616), and the `agent-mode` panel
// (catalog.ts:258) is exactly the consumer that goes stale. An agent accept_unit/reject_unit/pause
// left Mission Control showing the PREVIOUS state until the user manually refetched.
//
// §8.0b ONE FILE PER DOMAIN: the domain is the TOOL FAMILY, not the panel that renders it — hence
// `authoringRunEffects`, not `agentModeEffects`. `compositionEffects.ts` is owned by spec 31 / Wave 1
// (canon, corrections, style, voice); two waves writing one file is the collision §8.0b prevents.
import { registerEffectHandler, type EffectContext } from '../effectRegistry';

let registered = false;

/** ⚠ INVALIDATE BY PREFIX — the result does NOT carry the ids.
 *  composition_authoring_run_accept_unit / _reject_unit return `{success, unit_index, status}`
 *  (server.py:1924, :1981) — NO run_id, NO book_id. A handler that tried to read `run_id` from the
 *  result would extract null and silently no-op (the `fe-status-default-fallback` class). Note
 *  ['authoring-run'] does NOT prefix-match ['authoring-runs', …] (different first element), so every
 *  key is listed explicitly. All 7 verified in source — a PARTIAL invalidation is a partially stale
 *  panel, which is the bug with extra steps. */
const KEYS = [
  ['authoring-runs'],              // composition/authoringRuns/hooks.ts:21
  ['authoring-run'],               // hooks.ts:38
  ['authoring-run-report'],        // hooks.ts:48
  ['authoring-unit-diff'],         // studio/panels/agentMode/DiffReviewPanel.tsx:55
  ['plan-runs-for-authoring'],     // studio/panels/agentMode/useNewRunForm.ts:20
  ['plan-run-for-authoring-gate'], // studio/panels/agentMode/useMissionControl.ts:46
  ['book-toc-for-authoring'],      // studio/panels/agentMode/useMissionControl.ts:31
] as const;

export function authoringRunEffect(ctx: EffectContext): void {
  for (const queryKey of KEYS) ctx.queryClient.invalidateQueries({ queryKey: [...queryKey] });
}

/** Idempotent — register the authoring-run effect handler once.
 *  Double-fire check (§8.0b — reproduce it whenever you add a handler): the 11 tool names were matched
 *  against every existing registration. /^book_.*(draft|chapter)/ → no (book_ prefix).
 *  /^composition_.*(prose|draft)/ → no (no authoring_run name contains `prose` or `draft` — all 11
 *  checked). /^composition_(outline_node|scene_link)_/ → no. GLOSSARY_WRITE_PATTERN /
 *  KNOWLEDGE_WRITE_PATTERN / /^translation_job_control/ → no. ⇒ DISJOINT. Safe. */
export function registerAuthoringRunEffectHandlers(): void {
  if (registered) return;
  registered = true;
  registerEffectHandler(/^composition_authoring_run_/, authoringRunEffect);
}

/** Test-only: undo the idempotency guard so a test can re-register after clearEffectHandlers(). */
export function _resetAuthoringRunEffectHandlers(): void {
  registered = false;
}
