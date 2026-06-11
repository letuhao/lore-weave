"""LLM re-arch Phase 2b WX-T3a — PURE state machine for the decoupled extraction
orchestrator.

extract_pass2 is a multi-stage DAG with a concurrent fan-in:

    entity ──▶ gather(relation, event, fact) ──▶ [recovery] ──▶ [filter*] ──▶ persist
      (1)              (3 concurrent → fan-in)        (1)         (N batches)

This module is the PURE transition core (no DB / no SDK — fully unit-tested): it
decides the next stage, tracks the trio **fan-in** (3 jobs in flight; advance only
when all three have folded), and the **filter sub-loop** counter. The async shell +
the worker-ai terminal-event consumer (WX-T3b) drive the actual submit/parse/persist
over the WX-T2/T2b `build_<op>_submit_kwargs` / `parse_<op>_job` seams and own
persist + spend + cursor + the `knowledge.chapter_extracted` event.

Stages are gated on `has_recovery` / `has_filter` (the project's optional config) so
a project with neither goes entity → trio → persist.
"""

from __future__ import annotations

from typing import Any

TRIO_OPS = ("relation", "event", "fact")

# stage values
ENTITY = "entity"
TRIO = "trio"
RECOVERY = "recovery"
FILTER = "filter"
PERSIST = "persist"


def new_extract_state(
    *,
    chunk_text: str,
    known_entities: list[str],
    has_recovery: bool,
    has_filter: bool,
) -> dict[str, Any]:
    """Seed state for one chunk. `has_recovery`/`has_filter` reflect the project's
    resolved config (eff_recovery / eff_filter is not None in the runner)."""
    return {
        "mode": "extract",
        "chunk_text": chunk_text,
        "known_entities": list(known_entities),
        "has_recovery": has_recovery,
        "has_filter": has_filter,
        "stage": ENTITY,
        # accumulators (folded as each stage completes)
        "entities": [],
        "relations": [],
        "events": [],
        "facts": [],
        # trio fan-in: {op: provider_job_id} submitted, [op,...] folded
        "trio_jobs": {},
        "trio_folded": [],
        # filter sub-loop
        "filter_idx": 0,
        "filter_n": 0,
    }


# ── entity ────────────────────────────────────────────────────────────────────

def apply_entity_result(rs: dict[str, Any], entities: list) -> dict[str, Any]:
    """Fold the entity stage. Returns new rs with entities set + the stage advanced:
    no entities ⇒ go straight to persist (Pass2Candidates short-circuit — nothing to
    anchor relations/events/facts to); else ⇒ trio."""
    out = dict(rs)
    out["entities"] = list(entities)
    out["stage"] = TRIO if entities else PERSIST
    return out


# ── trio fan-in ───────────────────────────────────────────────────────────────

def begin_trio(rs: dict[str, Any], trio_jobs: dict[str, str]) -> dict[str, Any]:
    """Record the {op: provider_job_id} for the 3 concurrently-submitted trio jobs."""
    out = dict(rs)
    out["trio_jobs"] = dict(trio_jobs)
    out["trio_folded"] = []
    return out


def op_for_job(rs: dict[str, Any], provider_job_id: str) -> str | None:
    """Which trio op a terminal job_id belongs to (the consumer's fan-in lookup)."""
    for op, jid in rs.get("trio_jobs", {}).items():
        if str(jid) == str(provider_job_id):
            return op
    return None


def fold_trio_op(rs: dict[str, Any], op: str, items: list) -> dict[str, Any]:
    """Fold one trio op's result. Idempotent on a duplicate terminal event for the
    same op (already folded ⇒ unchanged). Advances to the next stage only once all
    three ops have folded."""
    if op not in TRIO_OPS or op in rs["trio_folded"]:
        return rs
    key = {"relation": "relations", "event": "events", "fact": "facts"}[op]
    out = dict(rs)
    out[key] = list(items)
    out["trio_folded"] = [*rs["trio_folded"], op]
    if set(out["trio_folded"]) >= set(TRIO_OPS):
        out["stage"] = _after_trio(out)
    return out


def trio_complete(rs: dict[str, Any]) -> bool:
    return set(rs.get("trio_folded", [])) >= set(TRIO_OPS)


def _after_trio(rs: dict[str, Any]) -> str:
    if rs["has_recovery"]:
        return RECOVERY
    if rs["has_filter"]:
        return FILTER
    return PERSIST


# ── recovery ──────────────────────────────────────────────────────────────────

def apply_recovery_result(
    rs: dict[str, Any], entities: list, relations: list,
) -> dict[str, Any]:
    """Fold the recovery stage (the shell applies verdicts → updated entities +
    pruned relations via the SDK's apply step). Advance to filter or persist."""
    out = dict(rs)
    out["entities"] = list(entities)
    out["relations"] = list(relations)
    out["stage"] = FILTER if rs["has_filter"] else PERSIST
    return out


# ── filter sub-loop ───────────────────────────────────────────────────────────

def begin_filter(rs: dict[str, Any], n_batches: int) -> dict[str, Any]:
    """Enter the filter stage with `n_batches` sequential LLM batches to run."""
    out = dict(rs)
    out["filter_n"] = n_batches
    out["filter_idx"] = 0
    out["stage"] = FILTER if n_batches > 0 else PERSIST
    return out


def apply_filter_batch(
    rs: dict[str, Any], kept: dict[str, list],
) -> dict[str, Any]:
    """Fold one filter batch's kept items (the shell applies verdicts via the SDK).
    `kept` may overwrite any of entities/relations/events/facts. Advance the batch
    cursor; the last batch → persist."""
    out = dict(rs)
    for key in ("entities", "relations", "events", "facts"):
        if key in kept:
            out[key] = list(kept[key])
    out["filter_idx"] = rs["filter_idx"] + 1
    if out["filter_idx"] >= rs["filter_n"]:
        out["stage"] = PERSIST
    return out


def filter_done(rs: dict[str, Any]) -> bool:
    return rs.get("filter_idx", 0) >= rs.get("filter_n", 0)


# ── candidates view ───────────────────────────────────────────────────────────

def candidates_dict(rs: dict[str, Any]) -> dict[str, list]:
    """The accumulated Pass2Candidates payload at persist time."""
    return {
        "entities": rs["entities"],
        "relations": rs["relations"],
        "events": rs["events"],
        "facts": rs["facts"],
    }
