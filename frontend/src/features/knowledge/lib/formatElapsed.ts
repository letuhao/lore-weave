// C7 (KN-9) — render how long ago an ISO-8601 timestamp was, as a short
// "Hh Mm" / "Mm Ss" cue for a running build. Pure + null-safe: returns
// null for missing/unparseable input or a future timestamp so callers
// render nothing rather than "NaN". Uses Date.now() at call time; the
// BuildingRunningCard re-renders on each 2s poll tick, so the value
// advances without its own timer.
export function formatElapsed(
  startedAt: string | null | undefined,
  now: number = Date.now(),
): string | null {
  if (!startedAt) return null;
  const start = Date.parse(startedAt);
  if (Number.isNaN(start)) return null;
  let secs = Math.floor((now - start) / 1000);
  if (secs < 0) return null;
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  secs %= 60;
  if (mins < 60) return `${mins}m ${secs}s`;
  const hrs = Math.floor(mins / 60);
  const remMins = mins % 60;
  return `${hrs}h ${remMins}m`;
}
