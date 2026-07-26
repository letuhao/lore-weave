// LOOM Composition (WS-B3 M4) — vs-canon judge delta.
//
// The what-if take badge shows each critic dim RELATIVE to the canon baseline (the
// anchor scene's CHAPTER draft prose), not just the take's own score. The take is
// already judged by useWhatIfTakes; this hook additionally judges the canon baseline
// and the badge renders delta = take − canon, per dim.
//
// Hazards handled (per the M4 contract + edge-case hardening):
//  - COALESCE clobber: the critique endpoint REPLACES the job's `critic` column on
//    each call (engine.py:1466-1478). The take verdict is already captured in client
//    state (alt.take.judge), so we read the canon verdict from the MUTATION RESPONSE
//    and never re-read the job — no double round-trip expecting both to persist.
//  - Cost: judge canon at most once per (chapter_id, draft_version) — a chapter edit
//    bumps draft_version and re-judges; keying on chapter_id alone would serve a stale
//    delta. Only fires while a take is previewed (the "chosen take" gate).
//  - Degrade-safe: empty/absent canon draft → baselineAvailable=false (badge shows the
//    absolute take score + "no canon baseline", never a fabricated 0-delta).
import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { booksApi } from '../../books/api';
import { useCritique } from './useCritique';
import type { Critic } from '../types';

export const CRITIC_DIMS = ['coherence', 'voice_match', 'pacing', 'canon_consistency'] as const;
export type CriticDim = (typeof CRITIC_DIMS)[number];

/** Single-letter glyph per dim (matches the legacy C·V·P·K badge). */
export const DIM_LETTER: Record<CriticDim, string> = {
  coherence: 'C',
  voice_match: 'V',
  pacing: 'P',
  canon_consistency: 'K',
};

export type DimDelta = {
  dim: CriticDim;
  take: number | null;
  canon: number | null;
  /** take − canon; null when either side is null (degrade) or no canon baseline. */
  delta: number | null;
};

/** Pure: per-dim delta of take vs canon. `canon === null` (no baseline / not yet
 *  judged) yields delta=null for every dim, so the caller falls back to absolutes. */
export function vsCanonDeltas(take: Critic, canon: Critic | null): DimDelta[] {
  return CRITIC_DIMS.map((dim) => {
    const t = take?.[dim] ?? null;
    const c = canon?.[dim] ?? null;
    const delta = t !== null && c !== null ? t - c : null;
    return { dim, take: t, canon: c, delta };
  });
}

/** ▲ (better) / ▼ (worse) / = (same) / – (unavailable) for a delta. */
export function deltaGlyph(delta: number | null): string {
  if (delta === null) return '–';
  if (delta > 0) return '▲';
  if (delta < 0) return '▼';
  return '=';
}

export type VsCanonState = {
  /** The canon baseline verdict (null until judged / when no baseline). */
  canon: Critic | null;
  /** True once a non-empty canon draft exists for the anchor chapter. */
  baselineAvailable: boolean;
  /** True while the canon verdict is being computed (baseline present, not yet judged). */
  judging: boolean;
};

export function useVsCanonDelta(opts: {
  bookId: string;
  token: string | null;
  /** The anchor scene's chapter_id — the canon baseline source. */
  chapterId: string | null;
  /** The previewed take's job (the critique call needs a job id). */
  jobId: string | null;
  /** Only judge while a generated take is actually being previewed. */
  enabled: boolean;
}): VsCanonState {
  const { bookId, token, chapterId, jobId, enabled } = opts;

  // 1. The canon baseline draft (memoized by chapter_id; carries draft_version).
  const draftQ = useQuery({
    queryKey: ['composition', 'canon-draft', bookId, chapterId],
    queryFn: () => booksApi.getDraft(token!, bookId, chapterId!),
    enabled: !!token && !!bookId && !!chapterId && enabled,
    // A chapter with no draft yet → 404; treat as "no baseline", don't spam retries.
    retry: false,
  });
  const baselineText = (draftQ.data?.text_content ?? '').trim();
  const draftVersion = draftQ.data?.draft_version ?? null;
  const baselineAvailable = !!draftQ.data && baselineText.length > 0;

  // 2. Critique the canon baseline, memoized by (chapter_id, draft_version). Manual
  //    cache (not react-query) because the verdict is read from the mutation response.
  const cacheKey = chapterId && draftVersion != null ? `${chapterId}:${draftVersion}` : null;
  const [canonCache, setCanonCache] = useState<Record<string, Critic>>({});
  const inFlightRef = useRef<Set<string>>(new Set());
  const { critique } = useCritique(token);
  const canon = cacheKey ? (canonCache[cacheKey] ?? null) : null;

  useEffect(() => {
    if (!enabled || !cacheKey || !jobId || !baselineAvailable) return;
    if (canonCache[cacheKey] || inFlightRef.current.has(cacheKey)) return; // memoized / in-flight
    inFlightRef.current.add(cacheKey);
    critique.mutate(
      { jobId, passage: baselineText },
      {
        onSuccess: (res) => {
          if (res.critic) setCanonCache((c) => ({ ...c, [cacheKey]: res.critic as Critic }));
        },
        onSettled: () => { inFlightRef.current.delete(cacheKey); },
      },
    );
    // critique is a stable mutation object; baselineText is derived from cacheKey.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, cacheKey, jobId, baselineAvailable]);

  const judging = enabled && baselineAvailable && canon === null;
  return { canon, baselineAvailable, judging };
}
