// C7 (D-K19b.3-02) — Humanised ETA formatter.
//
// K19b.3 shipped `~{{minutes}} min remaining` with
// `Math.max(1, Math.round(minutes))`. Reads awkwardly above an hour
// ("~240 min remaining"). This util splits into hours + minutes and
// drops the "0min" suffix on exact hours so long jobs read like
// "4h remaining" instead of "4h 0min remaining".
//
// Named `formatMinutes` (not `formatDuration`) because the codebase
// already has 5 local `formatDuration` helpers that take ms or seconds
// (AudioBlock, StepResults, AudioAttachBarExtension, AudioBlockNode,
// VideoBlockNode). Explicit unit in the name prevents silent misuse.
//
// Pure; no React deps — usable from any consumer.

export function formatMinutes(minutes: number): string {
  // Defensive: null-guard is at the consumer, but Infinity / NaN / ≤ 0
  // must not leak rendered garbage. Matches the consumer's "hide when
  // null" ethos by falling back to the lowest-signal string.
  if (!Number.isFinite(minutes) || minutes <= 0) return '<1min';
  if (minutes < 1) return '<1min';

  // Pre-round to an integer so 59.6 doesn't crash through the [1, 60)
  // branch into the hours branch as "0h 60min".
  const total = Math.round(minutes);
  if (total < 60) return `${total}min`;

  const h = Math.floor(total / 60);
  const mm = total % 60;
  return mm === 0 ? `${h}h` : `${h}h ${mm}min`;
}
