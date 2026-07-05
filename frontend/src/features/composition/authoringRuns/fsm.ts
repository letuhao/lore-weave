// #20_agent_mode.md — pure FSM/derivation helpers over the REAL router transitions
// (services/composition-service/app/routers/authoring_runs.py) + D8/D9/D10/D11.
// Kept framework-free so the single most correctness-critical rule in this feature
// (D8 — Accept/Reject must be hard-disabled outside report_ready/failed/paused) is
// unit-testable without mounting React.
import type { AuthoringRunStatus, AuthoringRunUnitStatus } from './types';

/** Mirrors `_REVIEWABLE_STATUSES` (authoring_run_service.py:148) exactly. */
export const REVIEWABLE_RUN_STATUSES: AuthoringRunStatus[] = ['report_ready', 'failed', 'paused'];

/** Mirrors the partial-unique-index scope fence (one active run per book). */
export const ACTIVE_RUN_STATUSES: AuthoringRunStatus[] = ['gated', 'running', 'paused'];

/** Mirrors `_REPORTABLE_STATUSES` (authoring_run_service.py:150) — the ONLY
 * statuses where GET /{run_id}/report doesn't 409. Outside these, the unit
 * queue has no per-unit ledger to read and must be synthesized from
 * `scope`/`current_unit` alone (see MissionControlView). */
export const REPORTABLE_RUN_STATUSES: AuthoringRunStatus[] = [...REVIEWABLE_RUN_STATUSES, 'closed'];

export type RunAction = 'gate' | 'start' | 'pause' | 'resume' | 'close' | 'revert-all';

/** The FSM-legal action set per run status — cross-checked against the router's
 * actual `add_api_route`/`_transition_route` wiring (authoring_runs.py:203-212)
 * plus close()'s allowed-from list (authoring_run_service.py:751-764) and
 * revert-all's `_REVIEWABLE_STATUSES` gate. `draft` has no `/start` route (only
 * `/gate`); `closed` is terminal with none. */
export function actionsForRunStatus(status: AuthoringRunStatus): RunAction[] {
  switch (status) {
    case 'draft': return ['gate'];
    case 'gated': return ['start', 'close'];
    case 'running': return ['pause'];
    case 'paused': return ['resume', 'close', 'revert-all'];
    case 'failed': return ['close', 'revert-all'];
    case 'report_ready': return ['close', 'revert-all'];
    case 'closed': return [];
    default: return [];
  }
}

export function isReviewableRunStatus(status: AuthoringRunStatus): boolean {
  return REVIEWABLE_RUN_STATUSES.includes(status);
}

/** D8 — Accept/Reject on a specific unit requires BOTH the run to be in a
 * reviewable status AND the unit itself still be `drafted` (accept_unit/
 * reject_unit both guard `from_statuses=('drafted',)` server-side). */
export function canReviewUnit(
  runStatus: AuthoringRunStatus, unitStatus: AuthoringRunUnitStatus,
): boolean {
  return isReviewableRunStatus(runStatus) && unitStatus === 'drafted';
}

/** D11 — budget bar turns red at >=85% spent. */
export function isBudgetDanger(spentUsd: number, budgetUsd: number): boolean {
  if (!(budgetUsd > 0)) return false;
  return spentUsd / budgetUsd >= 0.85;
}

/** D11 — "exact staleness threshold ... is a BUILD-time detail" (spec, explicit
 * placeholder). The driver bumps `driver_heartbeat_at` once per unit-boundary
 * claim (authoring_run_service.py `heartbeat_claim`, called at the top of every
 * `run_driver` loop iteration) with no fixed publish interval — this constant is
 * a conservative placeholder, NOT derived from a real measured cadence. */
export const HEARTBEAT_STALE_SECS = 30;

export function isHeartbeatStale(
  status: AuthoringRunStatus,
  heartbeatAt: string | null | undefined,
  now: number = Date.now(),
): boolean {
  if (status !== 'running') return false; // only a 'running' run should have a live driver
  if (!heartbeatAt) return true; // running with no heartbeat at all = never claimed / vanished
  const ageSecs = (now - new Date(heartbeatAt).getTime()) / 1000;
  return ageSecs > HEARTBEAT_STALE_SECS;
}

export type BreakerSeverity = 'ok' | 'warn' | 'danger';

/** breaker_state is a free-form dict populated only on a trip (empty/absent =
 * healthy). `unit_failed`/`driver_crashed` are hard failures (danger); `budget`/
 * `critic_severe` are intentional breaker PAUSES pending human review (warn, not
 * a failure). Anything else present-but-unrecognized is treated as a warn (never
 * silently 'ok' on an off-contract shape). */
export function breakerSeverity(breakerState: Record<string, unknown> | null | undefined): BreakerSeverity {
  const reason = breakerState?.reason;
  if (!reason || typeof reason !== 'string') return 'ok';
  if (reason === 'unit_failed' || reason === 'driver_crashed') return 'danger';
  return 'warn';
}

/** D10 keyboard triage — resolves a keydown to an action, or null for a no-op
 * (never throws/errors on an illegal key or an illegal state). */
export type UnitReviewKey = 'accept' | 'reject' | 'next' | 'prev';

export function keyToUnitReviewAction(key: string): UnitReviewKey | null {
  switch (key) {
    case 'a': case 'A': return 'accept';
    case 'r': case 'R': return 'reject';
    case 'ArrowRight': case 'n': case 'N': return 'next';
    case 'ArrowLeft': case 'p': case 'P': return 'prev';
    default: return null;
  }
}
