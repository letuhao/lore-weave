/** G3 — derive the monitor's live run stats (elapsed / throughput / ETA / in-progress)
 *  from existing data (started_at + progress counts). Pure (now passed in) so the
 *  math is unit-testable. ETA is omitted (—) once terminal or when throughput is 0. */

export interface RunStats {
  elapsed: string;     // "3h12m" | "45m" | "—"
  throughput: string;  // "7.8 ch/min" | "—"
  eta: string;         // remaining time "1h20m" | "—"
  inProgress: number;  // chapters mid-flight (sum of per-stage in_progress)
}

function hms(sec: number): string {
  if (!isFinite(sec) || sec <= 0) return '0m';
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  return h > 0 ? `${h}h${String(m).padStart(2, '0')}m` : `${m}m`;
}

export function deriveRunStats(a: {
  startedAt: string | null;
  finishedAt: string | null;
  terminal: boolean;
  total: number;
  translationDone: number;  // the deliverable unit for throughput/ETA
  inProgress: number;
  nowMs: number;
}): RunStats {
  if (!a.startedAt) {
    return { elapsed: '—', throughput: '—', eta: '—', inProgress: a.inProgress };
  }
  const startMs = Date.parse(a.startedAt);
  const endMs = a.finishedAt ? Date.parse(a.finishedAt) : a.nowMs;
  const elapsedSec = Math.max(0, (endMs - startMs) / 1000);
  const perMin = elapsedSec > 0 ? a.translationDone / (elapsedSec / 60) : 0;
  const remaining = Math.max(0, a.total - a.translationDone);
  const etaSec = !a.terminal && perMin > 0 && remaining > 0 ? (remaining / perMin) * 60 : null;
  return {
    elapsed: hms(elapsedSec),
    throughput: perMin > 0 ? `${perMin.toFixed(1)} ch/min` : '—',
    eta: a.terminal || etaSec == null ? '—' : hms(etaSec),
    inProgress: a.inProgress,
  };
}
