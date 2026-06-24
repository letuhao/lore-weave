// C12 — pure helpers for the build-wizard Step-1 target picker. Mirrors the
// knowledge-service StartJobRequest validator so the UI reflects the same
// dependent-auto-include behaviour BEFORE posting (no surprise BE rewrite).

import type { ExtractionTarget } from '../api';

// Canonical order = the BE DEFAULT_TARGETS order. Used to render the picker
// and to normalise the posted set deterministically.
export const ALL_TARGETS: ExtractionTarget[] = [
  'entities',
  'relations',
  'events',
  'facts',
  'summaries',
];

// Requesting any of these auto-includes `entities` (they anchor to entity
// names). Mirrors loreweave_extraction.pass2.TRIO_TARGETS + the BE validator.
const DEPENDENT_TARGETS: ReadonlySet<ExtractionTarget> = new Set<ExtractionTarget>([
  'relations',
  'events',
  'facts',
]);

/**
 * Dedupe + canonicalise the user's RAW selection WITHOUT auto-including
 * `entities`. This is what the FE POSTS: the BE/SDK add `entities` at runtime
 * (mandatory anchor pass) and key the recovery/filter-disable LOCK off the
 * user's explicit request — so the wire payload must carry the raw intent, not
 * an entities-injected set. Empty selection returns [] (caller omits `targets`
 * ⇒ BE runs all passes = back-compat).
 */
export function canonicalTargets(
  selected: Iterable<ExtractionTarget>,
): ExtractionTarget[] {
  const set = new Set<ExtractionTarget>(selected);
  if (set.size === 0) return [];
  return ALL_TARGETS.filter((t) => set.has(t));
}

/**
 * Resolve the EFFECTIVE target set the runtime will run (entities auto-included
 * for dependent targets). Used for UI display/preview only — NOT for the wire
 * payload (see `canonicalTargets`). Mirrors the SDK `normalize_targets`.
 */
export function resolveTargets(
  selected: Iterable<ExtractionTarget>,
): ExtractionTarget[] {
  const set = new Set<ExtractionTarget>(selected);
  if (set.size === 0) return [];
  for (const t of set) {
    if (DEPENDENT_TARGETS.has(t)) {
      set.add('entities');
      break;
    }
  }
  return ALL_TARGETS.filter((t) => set.has(t));
}

/**
 * Whether a target is FORCED on by the current selection (a dependent target
 * is selected, so `entities` is implied even if not directly checked). Drives
 * the picker's "auto-included" disabled-checked state for `entities`.
 */
export function isAutoIncluded(
  target: ExtractionTarget,
  selected: Iterable<ExtractionTarget>,
): boolean {
  if (target !== 'entities') return false;
  const set = new Set<ExtractionTarget>(selected);
  if (set.has('entities')) return false; // explicitly chosen, not "auto"
  for (const t of set) {
    if (DEPENDENT_TARGETS.has(t)) return true;
  }
  return false;
}

/**
 * Whether recovery/precision-filter would run for this selection. They
 * auto-disable when `entities` was not explicitly requested (LOCK). Drives a
 * UI hint only; the BE/SDK enforce it. Empty selection ⇒ all ⇒ enabled.
 */
export function entitiesExplicitlyRequested(
  selected: Iterable<ExtractionTarget>,
): boolean {
  const set = new Set<ExtractionTarget>(selected);
  if (set.size === 0) return true; // empty ⇒ all passes
  return set.has('entities');
}
