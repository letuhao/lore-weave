# Runbook — Canary Auto-Abort + Rollback

> **Layer:** L7.K.12 (RAID cycle 38) · **Spec:** SR05 §12AH.4
> **Audience:** SRE on-call (paged by the canary-controller on auto-abort)
> **Severity profile:** SEV1 (escalates to SEV0 if the bad code already reached a large cohort)

## When this fires

The `canary-controller` auto-aborts a `major`-class deploy and pages you when a
canary stage's cohort SLI burn exceeds **baseline × 2** (§12AH.4), or when the
stage-0 internal error rate is non-zero. The page carries:

- `deploy_id` — the `deploy_audit` row
- the stage at abort (0=internal · 1=1% · 2=10% · 3=50% · 4=100%)
- the observed `cohort SLI burn` and the `baseline × 2` threshold it breached
- `rolled_back=true` + the rollback reason (already written to `deploy_audit`)

The controller has **already triggered the rollback** before paging — your job
is to confirm the rollback completed and the SLI recovered, then investigate.

## Quick triage (5 min)

1. Open dashboard `deploy-progress` (uid `deploy-progress`). Confirm:
   - "Current canary stage" dropped back (rollback in progress / done)
   - "Cohort SLI burn vs baseline" stat is recovering below 2×
   - "Auto-aborts last 24h" incremented by 1
2. Read the `deploy_audit` row: `rolled_back`, `rollback_reason`, `canary_stage`,
   `canary_history`. The history shows which stages passed before the abort.
3. Confirm the rollback actually shifted traffic back: the affected cohorts
   (per `reality_registry.deploy_cohort`, rolled 0→99 in order) should be on the
   prior image again. If the SLI is NOT recovering after the rollback, this is
   a SEV0 — the rollback itself failed; go to "Rollback did not recover" below.

## Confirm recovery

- The cohort SLI burn must fall back under baseline within one monitor window.
- `lw_canary_sli_cohort{stage,service}` should return to the pre-deploy band.
- If only a subset of cohorts was live (stage 1/2), only those realities were
  ever exposed — blast radius is bounded by design.

## Investigate root cause (after recovery)

1. Diff the aborted deploy (`git_commit_sha` in `deploy_audit`) against the prior.
2. Map the burning SLI to its hot-path service (see `runbooks/slo/burn-rate-spike.md`
   "Per-SLI hot paths" table).
3. Decide rollback-vs-fix-forward per §12AH.8 (rollback-first bias — we already
   rolled back, so fix-forward requires explicit justification).
4. Open / update the incident if user impact was active (cohort 2+ = ≥10%).

## Rollback did not recover (SEV0 escalation)

If the SLI keeps burning AFTER the auto-rollback:

1. Escalate to SEV0 immediately (declare incident, page tech lead).
2. Manually force the prior image on ALL cohorts via the deploy tooling
   (do not wait for the controller).
3. Set a scheduled freeze: `admin ops deploy-freeze --scope global --reason "<id>"`.
4. The non-recovering signal usually means the bad change is NOT in the rolled-
   back artifact (e.g. a migration already applied, or an external dependency).
   Treat as a schema/data incident, not a code rollback.

## Re-deploy after fix

- The freeze (if set) must be lifted: `admin ops deploy-thaw ...`.
- A re-deploy is a fresh `major` deploy → starts at stage 0 again.
- If the burn was a one-off (provider blip), a manual early-proceed is allowed
  with tech-lead risk acknowledgment (§12AH.4 "manual early-proceed").

## Related

- `runbooks/deploy/freeze_override.md` — break-glass during a freeze
- `runbooks/slo/burn-rate-spike.md` — per-SLI burn triage
- Dashboard `deploy-progress` · `services/canary-controller/`
