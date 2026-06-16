"""State-aware control-capability derivation (spec M5).

`control_caps` are NOT stored on the projection row — they are derived at read
time from `(status, kind)` so they always reflect the job's CURRENT state. The
GUI gates its cancel/pause/resume buttons on these. Control ROUTING (forwarding
the action to the owning service) is P3; this only computes what is *offered*.

Pause is per-kind: a multi-unit job (extraction over chapters, a campaign, a
multi-chapter translation) can pause = stop dispatching new units + drain
in-flight. A single-LLM-call job (video_gen, one compose call) is cancel-only —
there is nothing to "pause". Unknown kinds default to cancel-only (conservative:
never offer a pause the owner can't honor).
"""

from __future__ import annotations

from loreweave_jobs import ControlCap, JobStatus, TERMINAL

# Kinds that run as multiple dispatched units AND expose a REAL pause/resume → offer it.
# Conservative allowlist gated on what the owning service actually HONORS, not just on
# whether the job is multi-unit: a kind here must have a working pause endpoint (offering
# an un-honored pause button is worse than not offering it). Honored today:
#   - extraction      — knowledge K16.4 pause/resume
#   - campaign        — campaign saga pause/resume + monitor
#   - enrichment_job  — lore-enrichment C8 manual pause/resume (re-arms the re-drive worker, P3-3)
# Cancel-only (NOT listed): composition `generate`/`compose_draft`, `video_gen`,
# lore-enrichment one-shot compose tasks, and `translation` — translation IS multi-chapter
# but has no pause impl yet (its workers honor only cancel); real stop-dispatch pause/resume
# is tracked as D-JOBS-P3-TRANSLATION-PAUSE (re-add here when it ships, P3-4).
_MULTI_UNIT_KINDS: frozenset[str] = frozenset({"extraction", "campaign", "enrichment_job"})

# Kinds whose owning service can RE-SUBMIT a failed job as a fresh job (D-JOBS-P4-RETRY).
# Conservative allowlist gated on a working retry endpoint — offering a retry the owner
# can't honor is worse than not offering it. Honored today:
#   - translation — re-creates from the stored translation_jobs params (standalone re-run)
# NOT yet (tracked): composition (D-JOBS-P4-RETRY-COMPOSITION), knowledge (needs stored
# model-ref UUIDs — D-JOBS-P4-RETRY-KNOWLEDGE), video_gen (D-JOBS-P4-RETRY-VIDEOGEN),
# lore-enrichment (sync in-process — incompatible with the deferred control contract;
# D-JOBS-P4-RETRY-LORE).
_RETRYABLE_KINDS: frozenset[str] = frozenset({"translation"})


def _is_multi_unit(kind: str) -> bool:
    return kind in _MULTI_UNIT_KINDS


def derive_control_caps(status: "JobStatus | str", kind: str) -> list[ControlCap]:
    """Return the control actions valid for a job in its CURRENT status.

    - `failed` → retry (only for a retry-supported kind), else none
    - terminal (completed/cancelled) or `cancelling` (already in-flight) → none
    - `paused` → resume + cancel
    - `pending` → cancel
    - `running` → cancel (+ pause iff the kind is multi-unit)
    """
    s = status if isinstance(status, JobStatus) else JobStatus(status)
    if s == JobStatus.FAILED:
        # A failed job is terminal but RE-SUBMITTABLE for the kinds whose owner honors it
        # (D-JOBS-P4-RETRY). Retry creates a NEW job; the failed row stays as history.
        return [ControlCap.RETRY] if kind in _RETRYABLE_KINDS else []
    if s in TERMINAL or s == JobStatus.CANCELLING:
        return []
    if s == JobStatus.PAUSED:
        return [ControlCap.RESUME, ControlCap.CANCEL]
    if s == JobStatus.PENDING:
        return [ControlCap.CANCEL]
    if s == JobStatus.RUNNING:
        caps: list[ControlCap] = []
        if _is_multi_unit(kind):
            caps.append(ControlCap.PAUSE)
        caps.append(ControlCap.CANCEL)
        return caps
    return []
