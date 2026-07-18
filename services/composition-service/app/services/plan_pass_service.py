"""27 V2-C1 — the PASS REGISTRY, the input fingerprint, and the DERIVED freshness view.

This is the compiler's contracts table (27 §170) expressed as code: for each of the seven passes,
what it consumes, what artifact kind it emits, and whether a human blocks on it.

Three laws live here, and each exists because the obvious alternative rots:

1. **Inputs resolve by POINTER, never by latest-kind lookup** (PF-3). Each pass records the
   `artifact_id` it produced; a downstream pass reads *that id*, not "the newest artifact of kind
   X". Pass 7 (`self_heal`) writes a NEW `scene_plan` — under a latest-by-kind rule it would become
   its own input and stale itself against its own output, forever.

2. **Freshness is DERIVED, never stored** (PF-3/DA-7). A pass is fresh iff the fingerprint it
   recorded still equals the fingerprint recomputed from its inputs' CURRENT pointers. So re-running
   a pass needs ZERO invalidation writes: its new artifact id changes every downstream fingerprint,
   and they go stale by derivation. This is `make`. A stored dirty-flag is a second source of truth
   that drifts the moment anything writes around it.

3. **`model_ref` is EXCLUDED from the fingerprint** (PF-3, explicit). Changing the default model
   must not silently stale a whole plan the user has already reviewed and accepted.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from app.db.models import PASS_ORDER, PlanArtifactKind, PlanPassId, PlanRun

CheckpointClass = Literal["blocking", "advisory"]


@dataclass(frozen=True)
class PassSpec:
    """One row of 27 §170's pass table."""

    pass_id: PlanPassId
    #: Artifact kinds produced by EARLIER passes that this pass consumes, resolved by pointer.
    depends_on: tuple[PlanPassId, ...]
    #: True ⇒ this pass also reads the run's `planning_package` (the compile output), not just
    #: upstream pass artifacts. Not a pass, so it cannot be a `depends_on`.
    reads_package: bool
    output_kind: PlanArtifactKind
    #: BLOCKING ⇒ the pass completes with `decision:"pending"` and the runner STOPS until a human
    #: reviews it (PF-6, ratified P-8). The human blocks exactly where the human is the only oracle:
    #: who the characters ARE (pass 2), and what shape the story takes (pass 4).
    checkpoint: CheckpointClass


#: The registry. ORDER IS THE DEPENDENCY ORDER — `pass_cursor` walks it, and a pass may never run
#: before its inputs are resolved (PF-1: "anonymous characters were uses of undeclared identifiers").
PASS_REGISTRY: dict[str, PassSpec] = {
    "motifs": PassSpec(
        pass_id="motifs", depends_on=(), reads_package=True,
        output_kind="motif_plan", checkpoint="advisory",
    ),
    "cast": PassSpec(
        pass_id="cast", depends_on=(), reads_package=True,
        output_kind="cast_plan", checkpoint="blocking",   # who the characters ARE
    ),
    "world": PassSpec(
        pass_id="world", depends_on=("cast",), reads_package=True,
        output_kind="world_plan", checkpoint="advisory",
    ),
    "beats": PassSpec(
        pass_id="beats", depends_on=("motifs",), reads_package=True,
        output_kind="beat_plan", checkpoint="blocking",   # what SHAPE the story takes
    ),
    "character_arcs": PassSpec(
        pass_id="character_arcs", depends_on=("cast", "beats"), reads_package=False,
        output_kind="char_arc_plan", checkpoint="advisory",
    ),
    "scenes": PassSpec(
        pass_id="scenes",
        depends_on=("cast", "motifs", "beats", "character_arcs"), reads_package=True,
        output_kind="scene_plan", checkpoint="advisory",
    ),
    "self_heal": PassSpec(
        pass_id="self_heal", depends_on=("scenes", "cast"), reads_package=False,
        # Pass 7 emits a NEW `scene_plan` (the healed one) — which is exactly why inputs must
        # resolve by POINTER: under a latest-by-kind rule it would read its own output as its input.
        output_kind="scene_plan", checkpoint="advisory",
    ),
}

assert tuple(PASS_REGISTRY) == PASS_ORDER, "registry order must equal the declared pass order"


#: The artifact kind `compile()` writes the planning package under. ONE name, ONE home.
#:
#: I first wrote `"planning_package"` here — which is not a member of `PlanArtifactKind` at all, so
#: the lookup could never match, and EVERY package-reading pass was unrunnable with a message that
#: blamed the user ("compile first") for something they had already done. Only the live smoke could
#: see it: the type is a `Literal`, but at runtime it is just a string, and no unit test ran the
#: worker against a real row. That is the same closed-set drift as DR-06, twice in one run — hence
#: the constant, and the test that pins it to the Literal.
PACKAGE_KIND: PlanArtifactKind = "package"


def package_body(artifact_content: dict[str, Any]) -> dict[str, Any]:
    """The planning package itself, out of the `package` artifact that WRAPS it.

    `compile()` stores `{"planning_package": {...}, <other compiled keys>}` — so the artifact's
    content is NOT the package; the package is one key inside it. An adapter handed the wrapper
    would read every field as absent and plan a book with no premise, no arc, and no chapters —
    and, being degrade-safe, would report that as a perfectly successful empty plan.
    """
    inner = artifact_content.get("planning_package")
    return inner if isinstance(inner, dict) else {}


class UpstreamStale(Exception):
    """A pass was asked to run while an upstream pass is stale or unaccepted (PF-5).

    The runner refuses rather than producing an artifact built on inputs the user has not seen —
    that is how a plan silently becomes internally inconsistent. `force` overrides; nothing else.
    """

    def __init__(self, pass_id: str, blockers: list[str]) -> None:
        super().__init__(
            f"pass '{pass_id}' cannot run: upstream {blockers} is stale or not accepted"
        )
        self.pass_id = pass_id
        self.blockers = blockers


def _canonical(value: Any) -> str:
    """Stable JSON — sorted keys, no incidental whitespace. A fingerprint that changed with dict
    ordering would stale the whole plan on a Python upgrade."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(
    *,
    input_artifact_ids: list[UUID | str],
    params: dict[str, Any] | None = None,
) -> str:
    """PF-3: `sha256(ordered input artifact ids + explicit pass params)`.

    ORDERED, not sorted: the order is the registry's `depends_on` order, so it is stable across
    runs and machines. `model_ref` is deliberately NOT an input — changing the default model must
    not silently stale a plan the user already accepted.
    """
    payload = _canonical(
        {"inputs": [str(i) for i in input_artifact_ids], "params": params or {}}
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _entry(run: PlanRun, pass_id: str) -> dict[str, Any]:
    e = run.pass_state.get(pass_id)
    if e is None:
        return {}
    # `pass_state` round-trips through JSONB, so an entry may be a plain dict OR a PassEntry
    # depending on whether it came from the DB or was just written in-process. Normalise.
    return e.model_dump(mode="json") if hasattr(e, "model_dump") else dict(e)


def input_pointers(
    run: PlanRun, pass_id: str, *, package_artifact_id: UUID | str | None = None,
) -> list[str]:
    """The artifact ids this pass's inputs currently resolve to — BY POINTER (PF-3).

    An upstream pass that has never completed contributes the empty string rather than being
    skipped: its ABSENCE must change the fingerprint, or a pass that ran before its upstream
    existed would look fresh forever.

    The `planning_package` is a REAL INPUT for the 5 passes that read it, and leaving it out was a
    bug: `motifs` and `cast` have no pass dependencies, so their fingerprint was a CONSTANT — once
    completed they were fresh forever, including after the user re-compiled with a different arc or
    genre and a brand-new package artifact. That is exactly the "a plan silently becomes internally
    inconsistent" failure PF-5 exists to prevent, and it was invisible because freshness derives
    from a set that omitted the input.
    """
    spec = PASS_REGISTRY[pass_id]
    out: list[str] = []
    if spec.reads_package:
        out.append(str(package_artifact_id or ""))
    for dep in spec.depends_on:
        out.append(str(_entry(run, dep).get("artifact_id") or ""))
    return out


def is_fresh(
    run: PlanRun, pass_id: str, *, package_artifact_id: UUID | str | None = None,
) -> bool:
    """Fresh iff the fingerprint the pass RECORDED still matches the one its inputs produce NOW.

    A pass that never completed is not fresh (there is nothing to be fresh about). This is the whole
    invalidation mechanism: no dirty flags, no invalidation writes, nothing to drift.

    The pass's PARAMS come from its OWN recorded entry, not from the caller. An earlier version took
    `params` as an argument, which meant `derive_view`/`pass_cursor` (which have no params to pass)
    recomputed every param-carrying pass's fingerprint with `params=None` — so any pass that ran
    with params read as permanently STALE and blocked everything downstream. The params a pass ran
    with are a property of that pass, so they live on its entry.
    """
    e = _entry(run, pass_id)
    if e.get("status") != "completed" or not e.get("input_fingerprint"):
        return False
    current = fingerprint(
        input_artifact_ids=input_pointers(
            run, pass_id, package_artifact_id=package_artifact_id
        ),
        params=e.get("params") or {},
    )
    return e["input_fingerprint"] == current


def is_accepted(run: PlanRun, pass_id: str) -> bool:
    """A pass counts as settled when a human accepted it, or when it auto-accepted (advisory).

    `pending` on a BLOCKING pass is precisely the stop signal (PF-6) — it is not "nearly done".
    """
    return _entry(run, pass_id).get("decision") in ("accepted", "auto")


def blockers_for(
    run: PlanRun, pass_id: str, *, package_artifact_id: UUID | str | None = None,
) -> list[str]:
    """Upstream passes that are stale or unaccepted — i.e. why `pass_id` may not run yet (PF-5).

    Note there is no `params` argument. An earlier version forwarded the CALLER's params into the
    upstream deps' freshness check — computing an upstream pass's fingerprint from a downstream
    pass's params, which is wrong under any reading. Each pass's params live on its own entry.
    """
    out: list[str] = []
    for dep in PASS_REGISTRY[pass_id].depends_on:
        if not is_fresh(run, dep, package_artifact_id=package_artifact_id) or not is_accepted(
            run, dep
        ):
            out.append(dep)
    return out


def assert_runnable(
    run: PlanRun,
    pass_id: str,
    *,
    force: bool = False,
    package_artifact_id: UUID | str | None = None,
) -> None:
    """PF-5's gate. Raises `UpstreamStale` unless every upstream is fresh AND accepted.

    `force` is the only escape, and it is an explicit per-call argument — never an env flag
    (Settings & Configuration Boundary: two users would want different values, so it is a choice,
    not platform config).
    """
    if force:
        return
    blockers = blockers_for(run, pass_id, package_artifact_id=package_artifact_id)
    if blockers:
        raise UpstreamStale(pass_id, blockers)


def pass_cursor(run: PlanRun, *, package_artifact_id: UUID | str | None = None) -> int:
    """The number of passes completed CONTIGUOUSLY from the start, each fresh AND accepted (PF-3).

    Contiguous, not counted: a run with passes 1,2,3 done and 4 blocking has cursor 3 even if
    someone force-ran pass 5. The cursor answers "how far can the compiler proceed unattended",
    which a total count would answer wrongly.

    DERIVED at serialization. Never stored.
    """
    n = 0
    for pid in PASS_ORDER:
        if is_fresh(run, pid, package_artifact_id=package_artifact_id) and is_accepted(run, pid):
            n += 1
        else:
            break
    return n


def blocked_at(run: PlanRun) -> str | None:
    """The first pass that is waiting on a human (BLOCKING + completed + decision pending).

    None ⇒ nothing is waiting on the user. This is what the Pass Rail renders, and what tells an
    autonomous run whether it may proceed.
    """
    for pid in PASS_ORDER:
        e = _entry(run, pid)
        if (
            PASS_REGISTRY[pid].checkpoint == "blocking"
            and e.get("status") == "completed"
            and e.get("decision") == "pending"
        ):
            return pid
    return None


def derive_view(
    run: PlanRun, *, package_artifact_id: UUID | str | None = None,
) -> dict[str, Any]:
    """The serialized pass view (PF-3): per-pass state + the DERIVED fields.

    `fresh`, `pass_cursor` and `blocked_at` are computed HERE, at serialization, and are never
    columns. That is the point: they cannot go stale, because they do not persist.
    """
    passes = []
    for pid in PASS_ORDER:
        spec = PASS_REGISTRY[pid]
        e = _entry(run, pid)
        passes.append({
            "pass_id": pid,
            "checkpoint": spec.checkpoint,
            "output_kind": spec.output_kind,
            "depends_on": list(spec.depends_on),
            "status": e.get("status", "pending"),
            "decision": e.get("decision", "pending"),
            "artifact_id": e.get("artifact_id"),
            "job_id": e.get("job_id"),
            # BE-20 · PF-7 — the glossary seed proposal this pass is waiting on. RETURNED, because
            # `_assert_seed_applied` refuses to accept `cast` until this proposal is `applied`, and
            # the ONLY route to it is GET /plan/bootstrap/{proposal_id} — which needs an id the
            # client could not otherwise see. A stored field the gate reads but no transport returns
            # is a permanent, unclearable 409 (the "cannot advance past cast" bug).
            "bootstrap_proposal_id": e.get("bootstrap_proposal_id"),
            "decided_by": e.get("decided_by"),
            "decided_at": e.get("decided_at"),
            # DERIVED — not stored:
            "fresh": is_fresh(run, pid, package_artifact_id=package_artifact_id),
            "blockers": blockers_for(run, pid, package_artifact_id=package_artifact_id),
        })
    return {
        "passes": passes,
        "pass_cursor": pass_cursor(run, package_artifact_id=package_artifact_id),
        "blocked_at": blocked_at(run),
    }


def record_pass(
    run: PlanRun,
    pass_id: str,
    *,
    #: OPTIONAL, like every other field — the docstring below always said "fields left None are
    #: UNTOUCHED", but `status` was required, which made a DECISION-ONLY write impossible: accepting
    #: a pass at its checkpoint changes the decision, not the status, and there was no honest value
    #: to pass. The live smoke found it as a 500 on the accept.
    status: str | None = None,
    artifact_id: UUID | str | None = None,
    job_id: UUID | str | None = None,
    input_fingerprint: str | None = None,
    #: The params this pass RAN with. Stored, because freshness recomputes the fingerprint and must
    #: use the same params — a caller that has to remember them would eventually forget.
    params: dict[str, Any] | None = None,
    bootstrap_proposal_id: UUID | str | None = None,
    decision: str | None = None,
    decided_by: str | None = None,
    decided_at: str | None = None,
) -> dict[str, Any]:
    """Return the NEW `pass_state` dict with `pass_id`'s entry merged in.

    Pure — it does not write. The caller persists it, so the whole ledger update is one UPDATE and
    cannot half-apply. Fields left `None` are UNTOUCHED, not cleared: a status write must not wipe
    the artifact pointer a previous write recorded (that pointer is what every downstream pass
    resolves through).
    """
    state = {
        k: (v.model_dump(mode="json") if hasattr(v, "model_dump") else dict(v))
        for k, v in run.pass_state.items()
    }
    e = dict(state.get(pass_id, {}))
    if status is not None:
        e["status"] = status
    if artifact_id is not None:
        e["artifact_id"] = str(artifact_id)
    if job_id is not None:
        e["job_id"] = str(job_id)
    if input_fingerprint is not None:
        e["input_fingerprint"] = input_fingerprint
    if params is not None:
        e["params"] = params
    if bootstrap_proposal_id is not None:
        e["bootstrap_proposal_id"] = str(bootstrap_proposal_id)
    if decision is not None:
        e["decision"] = decision
    if decided_by is not None:
        e["decided_by"] = decided_by
    if decided_at is not None:
        e["decided_at"] = decided_at
    state[pass_id] = e
    return state


def default_decision(pass_id: str) -> str:
    """What a pass's decision becomes the moment it COMPLETES.

    Advisory ⇒ `auto` (accepted without asking, but still reviewable and re-runnable after the
    fact). Blocking ⇒ `pending` — and THAT is the stop signal; the runner reads it and halts.
    """
    return "pending" if PASS_REGISTRY[pass_id].checkpoint == "blocking" else "auto"
