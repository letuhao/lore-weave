// C13 — pure helpers for the build-wizard Step-2 glossary-pinning dual-list.
// View/logic separation: the component renders, these functions decide.

import type { GlossaryEntityStat } from '../api';

// Auto-pin heuristic thresholds (tunable). A "sparse-but-long-reaching" entity
// — low coverage yet a wide first→last span — is the one extraction would drop
// in the chapters between its appearances, so it's the prime pin candidate.
export const AUTOPIN_MAX_COVERAGE = 0.15; // sparse: appears in ≤15% of chapters
export const AUTOPIN_MIN_SPAN_RATIO = 0.5; // long-reaching: spans ≥50% of book

// ~50 prompt tokens per pinned entity per window (matches BE
// _TOKENS_PER_PINNED_ENTITY). Used for the per-window budget hint.
export const TOKENS_PER_PINNED_ENTITY = 50;

/** Span (in chapters) an entity reaches across, inclusive of both ends. null
 * chapter indices ⇒ 0 (no measurable span). */
export function entitySpan(stat: GlossaryEntityStat): number {
  if (stat.first_chapter_index == null || stat.last_chapter_index == null) {
    return 0;
  }
  return stat.last_chapter_index - stat.first_chapter_index + 1;
}

/** Is this entity a sparse-but-long-reaching auto-pin candidate? coverage_pct
 * ≤ AUTOPIN_MAX_COVERAGE AND span ≥ AUTOPIN_MIN_SPAN_RATIO × chapter_count. */
export function isAutoPinCandidate(
  stat: GlossaryEntityStat,
  chapterCount: number,
): boolean {
  if (chapterCount <= 0) return false;
  if (stat.coverage_pct > AUTOPIN_MAX_COVERAGE) return false;
  const span = entitySpan(stat);
  return span >= AUTOPIN_MIN_SPAN_RATIO * chapterCount;
}

/** The auto-pin suggestion set: every candidate's entity_id. */
export function autoPinSuggestions(
  stats: GlossaryEntityStat[],
  chapterCount: number,
): string[] {
  return stats
    .filter((s) => isAutoPinCandidate(s, chapterCount))
    .map((s) => s.entity_id);
}

export interface EntityFilter {
  search: string; // case-insensitive name substring
  kind: string; // '' = all kinds
  minMentions: number; // frequency floor (0 = no floor)
}

/** Apply the available-list filters (search / kind / frequency). Pure. */
export function filterEntities(
  stats: GlossaryEntityStat[],
  filter: EntityFilter,
): GlossaryEntityStat[] {
  const q = filter.search.trim().toLowerCase();
  return stats.filter((s) => {
    if (q && !s.name.toLowerCase().includes(q)) return false;
    if (filter.kind && s.kind !== filter.kind) return false;
    if (s.mention_count < filter.minMentions) return false;
    return true;
  });
}

/** Distinct kinds present in the stats, sorted, for the kind filter dropdown. */
export function distinctKinds(stats: GlossaryEntityStat[]): string[] {
  return Array.from(new Set(stats.map((s) => s.kind).filter(Boolean))).sort();
}

/** Per-window added token budget for the current pinned set. */
export function pinnedWindowTokens(pinnedCount: number): number {
  return pinnedCount * TOKENS_PER_PINNED_ENTITY;
}
