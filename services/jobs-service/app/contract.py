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
#   - translation     — stop-dispatch pause/resume (B2): pause leaves new chapters undispatched
#                       (the worker drops paused units at its start gate); resume re-drives the
#                       un-done chapters from the stored job row (D-JOBS-P3-TRANSLATION-PAUSE).
# Cancel-only (NOT listed): composition `generate`/`compose_draft`, `video_gen`, and the
# lore-enrichment one-shot compose tasks — each a single LLM call with no units to pause.
_MULTI_UNIT_KINDS: frozenset[str] = frozenset({"extraction", "campaign", "enrichment_job", "translation"})

# Kinds whose owning service can RE-SUBMIT a failed job as a fresh job (D-JOBS-P4-RETRY).
# Conservative allowlist gated on a working retry endpoint — offering a retry the owner
# can't honor is worse than not offering it. Honored today:
#   - translation — re-creates from the stored translation_jobs params (standalone re-run)
# NOT yet (tracked): composition (D-JOBS-P4-RETRY-COMPOSITION), knowledge (needs stored
# model-ref UUIDs — D-JOBS-P4-RETRY-KNOWLEDGE), video_gen (D-JOBS-P4-RETRY-VIDEOGEN),
# lore-enrichment (sync in-process — incompatible with the deferred control contract;
# D-JOBS-P4-RETRY-LORE).
_RETRYABLE_KINDS: frozenset[str] = frozenset({"translation"})

# VIEW-ONLY kinds — visible on the unified Jobs screen (their producer emits +
# reconciles) but NOT yet control-wired in the unified plane, so we offer NO control
# caps (a Cancel/Resume button that 404s is worse than none). These are SECONDARY kinds
# whose owning service's P3 control endpoint handles only its PRIMARY job table:
#   - glossary_extraction — translation control endpoint handles `translation_jobs`, not
#                            `extraction_jobs` (Slice A — D-JOBS-GLOSSARY-EXTRACT-UNWIRED).
#   - wiki_gen            — knowledge control endpoint handles `extraction_jobs`, not
#                            `wiki_gen_jobs` (Slice C — D-JOBS-WIKI-GEN-UNWIRED).
# Users control these via their native panels (extraction wizard / wiki panel) today;
# unified-plane control wiring is tracked (D-JOBS-SECONDARY-KIND-CONTROL).
_VIEW_ONLY_KINDS: frozenset[str] = frozenset({"glossary_extraction", "wiki_gen"})


def _is_multi_unit(kind: str) -> bool:
    return kind in _MULTI_UNIT_KINDS


def derive_control_caps(status: "JobStatus | str", kind: str) -> list[ControlCap]:
    """Return the control actions valid for a job in its CURRENT status.

    - a VIEW-ONLY kind (not yet control-wired in the unified plane) → none
    - `failed` → retry (only for a retry-supported kind), else none
    - terminal (completed/cancelled) or `cancelling` (already in-flight) → none
    - `paused` → resume + cancel
    - `pending` → cancel
    - `running` → cancel (+ pause iff the kind is multi-unit)
    """
    if kind in _VIEW_ONLY_KINDS:  # visible but control routes nowhere → offer nothing
        return []
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
