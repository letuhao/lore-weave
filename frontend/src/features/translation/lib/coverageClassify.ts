// Per-chapter translation status derived from the book coverage report, for a
// single target language. Drives the translate wizard's classification, summary
// counts, and the "translate everything that needs it" default selection.
//
// The backend idempotency gate (translation-service jobs.py) skips any chapter
// that already has a FRESH completed version (status='completed' AND not
// glossary-stale). So submitting the union {untranslated ∪ stale ∪ failed} with
// force_retranslate=false translates exactly the chapters that need work —
// "translated" and "running" are correctly left alone.
import type { BookCoverageResponse, CoverageCell } from '../api';

export type ChapterTxStatus = 'untranslated' | 'translated' | 'stale' | 'failed' | 'running';

// Statuses that the idempotency gate will actually (re)translate.
export const NEEDS_STATUSES: ReadonlySet<ChapterTxStatus> = new Set<ChapterTxStatus>([
  'untranslated',
  'stale',
  'failed',
]);

/** Build a chapter_id → coverage-cell lookup for one language from the report. */
export function coverageMapFor(
  coverage: BookCoverageResponse | null,
  lang: string,
): Map<string, CoverageCell> {
  const map = new Map<string, CoverageCell>();
  if (!coverage || !lang) return map;
  for (const row of coverage.coverage) {
    const cell = row.languages?.[lang];
    if (cell) map.set(row.chapter_id, cell);
  }
  return map;
}

/**
 * Classify one chapter for the selected language.
 * - absent cell → never translated for this language → 'untranslated'
 * - latest attempt pending/running → 'running' (already in flight, leave alone)
 * - has a fresh active version → 'translated'; if the glossary moved → 'stale'
 * - no active version, latest attempt failed → 'failed'
 * - otherwise (no active, no terminal attempt) → 'untranslated'
 *
 * In-flight precedence matters: the idempotency gate (jobs.py) only skips
 * chapters with a *completed* non-stale row — it does NOT skip pending/running.
 * So an in-flight chapter must never land in the needs-set, or the primary
 * "translate what needs it" action would queue a duplicate job for it.
 */
export function classifyCell(cell: CoverageCell | undefined): ChapterTxStatus {
  if (!cell) return 'untranslated';
  if (cell.latest_status === 'running' || cell.latest_status === 'pending') return 'running';
  if (cell.has_active) {
    return cell.is_glossary_stale ? 'stale' : 'translated';
  }
  if (cell.latest_status === 'failed') return 'failed';
  return 'untranslated';
}

export type StatusCounts = Record<ChapterTxStatus, number> & { total: number };

/** Status for every chapter id + aggregate counts, in one pass. */
export function classifyChapters(
  chapterIds: string[],
  cells: Map<string, CoverageCell>,
): { byId: Map<string, ChapterTxStatus>; counts: StatusCounts } {
  const byId = new Map<string, ChapterTxStatus>();
  const counts: StatusCounts = {
    total: chapterIds.length,
    untranslated: 0,
    translated: 0,
    stale: 0,
    failed: 0,
    running: 0,
  };
  for (const id of chapterIds) {
    const status = classifyCell(cells.get(id));
    byId.set(id, status);
    counts[status] += 1;
  }
  return { byId, counts };
}

/** Chapter ids the gate would actually translate (untranslated ∪ stale ∪ failed). */
export function needsIds(byId: Map<string, ChapterTxStatus>): string[] {
  const ids: string[] = [];
  for (const [id, status] of byId) {
    if (NEEDS_STATUSES.has(status)) ids.push(id);
  }
  return ids;
}
