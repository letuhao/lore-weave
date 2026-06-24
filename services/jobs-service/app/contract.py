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
#   - extraction  — knowledge re-runs the failed extraction_jobs row through the full start
#                   core (re-validates the K17.9 benchmark + budget gates, emits 'running');
#                   the row carries every StartJobRequest field (D-JOBS-P4-RETRY-KNOWLEDGE)
#   - video_gen   — video-gen reconstructs the GenerateRequest from the row's request_json
#                   JSONB (which already persists prompt/model/duration/aspect/style) and
#                   re-runs the decoupled submit → new row + 'running' (D-JOBS-P4-RETRY-VIDEOGEN;
#                   NO migration — the params were on the row all along)
#   - enrichment_job — lore re-drives the SAME failed job over the live async path (resume
#                   stream → redrive_one), skipping already-done gaps (UNIQUE(job_id,gap_ref)
#                   + skip_gap_refs = no re-spend) and re-running the rest; flips failed→running
#                   + emits 'running'. Safe under concurrency via the M1 per-job advisory claim
#                   (a retry-while-running is a no-op) (D-JOBS-P4-RETRY-LORE; NO migration —
#                   the job request row already persists every re-drive field).
# NOT a kind-based entry: composition retry is PER-JOB, not per-kind — a composition job's
# `kind` is its free-form operation ("draft_scene", "rewrite", …), IDENTICAL for the
# server-reconstructable worker path and the non-reconstructable inline/streamed path. So
# composition is gated on the per-job `retryable` flag (params.retryable, emitted by the
# producer) passed to derive_control_caps, NOT this allowlist (D-JOBS-P4-RETRY-COMPOSITION).
_RETRYABLE_KINDS: frozenset[str] = frozenset(
    {"translation", "extraction", "video_gen", "enrichment_job"}
)

# VIEW-ONLY kinds — visible on the unified Jobs screen but with NO unified control surface,
# so we offer no caps. book_import is fire-and-forget (book-service has no control endpoint;
# a running import can't be stopped) — D-JOBS-BOOK-IMPORT-UNWIRED.
_VIEW_ONLY_KINDS: frozenset[str] = frozenset({"book_import"})

# SECONDARY kinds now control-wired in the unified plane (D-JOBS-SECONDARY-KIND-CONTROL) —
# the owning service's control endpoint dispatches BY KIND to the right job table. Caps match
# each producer's NATIVE control exactly (offering more would 404/409 downstream):
#   - glossary_extraction / glossary_translation — translation cancel core (pending|running).
#     Multi-unit but the native endpoints only CANCEL (no pause/resume) → cancel-only.
#   - wiki_gen — knowledge: cancel a NOT-yet-running job (pending|paused) + resume (paused).
#     A *running* wiki job is NOT cancellable (the orchestrator doesn't poll mid-loop;
#     D-WIKI-M7B-RUNNING-CANCEL) → running offers nothing.
_CANCEL_ONLY_KINDS: frozenset[str] = frozenset({"glossary_extraction", "glossary_translation"})


def _is_multi_unit(kind: str) -> bool:
    return kind in _MULTI_UNIT_KINDS


def derive_control_caps(
    status: "JobStatus | str", kind: str, *, retryable: bool | None = None
) -> list[ControlCap]:
    """Return the control actions valid for a job in its CURRENT status.

    - a VIEW-ONLY kind (no unified control surface) → none
    - a CANCEL-ONLY secondary kind → cancel when pending|running, else none
    - `wiki_gen` → resume+cancel when paused, cancel when pending, else none (no running-cancel)
    - `failed` → retry (kind in _RETRYABLE_KINDS OR the PER-JOB `retryable` flag is True), else none
    - terminal (completed/cancelled) or `cancelling` (already in-flight) → none
    - `paused` → resume + cancel
    - `pending` → cancel
    - `running` → cancel (+ pause iff the kind is multi-unit)

    `retryable` is the producer-emitted per-job signal (projection params.retryable),
    used for kinds whose retryability is per-job not per-kind (composition: the worker
    path is reconstructable, the inline/streamed path is not — same `kind` for both).
    None (most callers / most kinds) ⇒ kind-based decision only.
    """
    if kind in _VIEW_ONLY_KINDS:  # no control endpoint → offer nothing
        return []
    s = status if isinstance(status, JobStatus) else JobStatus(status)
    # Secondary kinds with restricted native control (match the producer exactly).
    if kind in _CANCEL_ONLY_KINDS:
        return [ControlCap.CANCEL] if s in (JobStatus.PENDING, JobStatus.RUNNING) else []
    if kind == "wiki_gen":
        if s == JobStatus.PAUSED:
            return [ControlCap.RESUME, ControlCap.CANCEL]
        if s == JobStatus.PENDING:
            return [ControlCap.CANCEL]
        if s == JobStatus.RUNNING:
            # D-WIKI-M7B: a running wiki-gen job IS now cancellable — the orchestrator
            # polls status between entities and stops promptly (no pause: a wiki-gen
            # pause is budget-driven/auto, not an offered manual control).
            return [ControlCap.CANCEL]
        return []  # terminal/cancelling → none
    if s == JobStatus.FAILED:
        # A failed job is terminal but RE-SUBMITTABLE when the owner honors it
        # (D-JOBS-P4-RETRY): either the kind is unconditionally retryable, or this
        # specific job carries the per-job `retryable` flag (composition). Retry
        # creates a NEW job; the failed row stays as history.
        return [ControlCap.RETRY] if (kind in _RETRYABLE_KINDS or retryable is True) else []
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
