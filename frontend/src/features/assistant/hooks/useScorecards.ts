// R2 (D-COACHING-SCORECARD-MOUNT) — the coaching-scorecard controller (CLAUDE.md MVC: logic here,
// CoachingScorecard only renders). Fetches the user's persisted scorecards (chat_outputs 'scorecard'
// rows) via the BFF and normalizes each card. SD-7 is fail-closed here: a stored card that somehow
// lacks `quarantine` is treated as quarantine=TRUE, so a malformed/legacy row can never accidentally
// be trended. The trend gate (scorecardTrend) then excludes every quarantine card.
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { assistantApi } from '../api';
import type { Scorecard, ScorecardItem } from '../types';
import { canShowTrend } from '../scorecardTrend';

function normalizeCard(raw: unknown): Scorecard {
  const c = (raw ?? {}) as Partial<Scorecard>;
  return {
    overall_score: typeof c.overall_score === 'number' ? c.overall_score : null,
    summary: typeof c.summary === 'string' ? c.summary : null,
    // SD-7 fail-closed: default to quarantine when the flag is missing/non-boolean — never trend by accident.
    quarantine: c.quarantine === false ? false : true,
    dimensions: Array.isArray(c.dimensions) ? c.dimensions : [],
  };
}

export function useScorecards() {
  const { accessToken } = useAuth();
  const [items, setItems] = useState<ScorecardItem[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const res = await assistantApi.getScorecards(accessToken).catch(() => ({ scorecards: [] }));
      setItems((res.scorecards ?? []).map((s) => ({ ...s, card: normalizeCard(s.card) })));
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const latest = items[0] ?? null; // newest-first from the server
  // SD-7: a trend may be drawn only from ≥2 NON-quarantine cards — today always false (all quarantine).
  const showTrend = canShowTrend(items.map((i) => i.card));

  return { items, latest, showTrend, loading, refresh };
}
