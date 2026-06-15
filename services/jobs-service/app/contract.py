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

# Kinds that run as multiple dispatched units → support pause/resume. Conservative
# allowlist; anything else is cancel-only. `composition.*` single ops, `video_gen`,
# `enrichment_job`, `composition.generate` etc. are single-call → not listed.
_MULTI_UNIT_KINDS: frozenset[str] = frozenset({"extraction", "translation", "campaign"})


def _is_multi_unit(kind: str) -> bool:
    return kind in _MULTI_UNIT_KINDS


def derive_control_caps(status: "JobStatus | str", kind: str) -> list[ControlCap]:
    """Return the control actions valid for a job in its CURRENT status.

    - terminal (completed/failed/cancelled) or `cancelling` (already in-flight) → none
    - `paused` → resume + cancel
    - `pending` → cancel
    - `running` → cancel (+ pause iff the kind is multi-unit)
    """
    s = status if isinstance(status, JobStatus) else JobStatus(status)
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
