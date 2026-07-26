// LOOM Composition · Q1+Q2 Quality Report (controller) — owns the read-only report state.
//
// Runs the two advisory judges (4-dim critic + promise audit) for the open chapter and holds
// the resulting report. This is DIAGNOSTIC: unlike the self-heal proposals there is no
// acceptance set and no apply — the author reads it and decides. The view only renders + calls run.
import { useCallback, useState } from 'react';

import { compositionApi, type QualityReport } from '../api';

export function useQualityReport(
  projectId: string | null,
  chapterId: string | null,
  token: string | null,
  modelRef: string,
) {
  const [report, setReport] = useState<QualityReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ran, setRan] = useState(false);

  const run = useCallback(async () => {
    if (!projectId || !chapterId || !token || !modelRef) return;
    setLoading(true);
    setError(null);
    try {
      const r = await compositionApi.qualityReport(projectId, { chapterId, modelRef }, token);
      setReport(r.report ?? null);
      setRan(true);
    } catch (e) {
      setError((e as Error).message || 'Quality analysis failed');
    } finally {
      setLoading(false);
    }
  }, [projectId, chapterId, token, modelRef]);

  return { report, loading, error, ran, run };
}
