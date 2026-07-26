// LOOM Composition · Q3 Book-level promise coverage (controller).
//
// Runs the book-level promise audit (v2): derives a stable promise set from the outline
// spec and scores the whole book against it. Read-only/diagnostic — no accept/apply. The
// view only renders + calls run. Book-scoped (no chapter), so it lives in the project-scoped
// Quality dashboard, not the per-chapter Polish gate.
import { useCallback, useState } from 'react';

import { compositionApi, type PromiseCoverage } from '../api';

export function useBookPromiseCoverage(
  projectId: string | null,
  token: string | null,
  modelRef: string,
) {
  const [coverage, setCoverage] = useState<PromiseCoverage | null>(null);
  const [chapters, setChapters] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ran, setRan] = useState(false);

  const run = useCallback(async () => {
    if (!projectId || !token || !modelRef) return;
    setLoading(true);
    setError(null);
    try {
      const r = await compositionApi.promiseCoverage(projectId, { modelRef }, token);
      setCoverage(r.coverage ?? null);
      setChapters(r.chapters ?? null);
      setRan(true);
    } catch (e) {
      setError((e as Error).message || 'Promise coverage failed');
    } finally {
      setLoading(false);
    }
  }, [projectId, token, modelRef]);

  return { coverage, chapters, loading, error, ran, run };
}
