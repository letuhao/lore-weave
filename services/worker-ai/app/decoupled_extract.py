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
        # recovery + filter fan-out sets are seeded by begin_recovery / begin_filter
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


# ── recovery (FAN-OUT over Tier-3 classifier batches) ──────────────────────────
# WX-T2c discovery: recovery isn't a single call — Tier-1+2 (glossary, no LLM) runs
# inline in the shell (prepare_recovery), then the remaining names are classified in
# N Tier-3 batches. Those fan out like the trio. The shell applies each batch's
# verdicts (apply_recovery_batch) into the rs accumulators; the SM only tracks
# completion + the stage advance. After all fold → the shell finalize_recovery's.

def begin_recovery(rs: dict[str, Any], recovery_jobs: dict[str, str]) -> dict[str, Any]:
    """Enter recovery as a fan-out of {batch_key: provider_job_id}. Empty (no Tier-3
    names — all resolved by Tier-1+2 inline) ⇒ skip to filter/persist."""
    out = dict(rs)
    out["recovery_jobs"] = dict(recovery_jobs)
    out["recovery_folded"] = []
    if not recovery_jobs:
        out["stage"] = FILTER if rs["has_filter"] else PERSIST
    return out


def recovery_task_for_job(rs: dict[str, Any], provider_job_id: str) -> str | None:
    for key, jid in rs.get("recovery_jobs", {}).items():
        if str(jid) == str(provider_job_id):
            return key
    return None


def fold_recovery_task(
    rs: dict[str, Any], task_key: str, *, entities: list, relations: list,
) -> dict[str, Any]:
    """Fold one recovery batch — the shell has applied its verdicts into the running
    entities/relations (promote + abstract-drop). Idempotent on a dup. Advance to
    filter/persist when all batches folded."""
    if task_key not in rs.get("recovery_jobs", {}) or task_key in rs["recovery_folded"]:
        return rs
    out = dict(rs)
    out["entities"] = list(entities)
    out["relations"] = list(relations)
    out["recovery_folded"] = [*rs["recovery_folded"], task_key]
    if set(out["recovery_folded"]) >= set(rs["recovery_jobs"].keys()):
        out["stage"] = FILTER if rs["has_filter"] else PERSIST
    return out


def recovery_complete(rs: dict[str, Any]) -> bool:
    return set(rs.get("recovery_folded", [])) >= set(rs.get("recovery_jobs", {}).keys())


# ── filter (FAN-OUT over category × batch tasks) ───────────────────────────────
# WX-T2c discovery: filter is concurrent-category × sequential-batch. The decoupled
# stage fans out ALL (category, batch) tasks at once; each folds its per-item
# verdicts into a {category: {global_idx: verdict}} accumulator; when all fold, the
# shell computes kept-sets (compute_filter_kept) + stitches the filtered lists.

def begin_filter(rs: dict[str, Any], filter_jobs: dict[str, str]) -> dict[str, Any]:
    """Enter filter as a fan-out of {task_key: provider_job_id} (task_key encodes
    category+batch). Empty ⇒ persist."""
    out = dict(rs)
    out["filter_jobs"] = dict(filter_jobs)
    out["filter_folded"] = []
    out["filter_verdicts"] = {}  # {category: {global_idx: verdict}}
    out["stage"] = FILTER if filter_jobs else PERSIST
    return out


def filter_task_for_job(rs: dict[str, Any], provider_job_id: str) -> str | None:
    for key, jid in rs.get("filter_jobs", {}).items():
        if str(jid) == str(provider_job_id):
            return key
    return None


def fold_filter_task(
    rs: dict[str, Any], task_key: str, category: str, verdicts: dict,
) -> dict[str, Any]:
    """Fold one filter task's verdicts (global_idx → verdict) into the category
    accumulator. Idempotent on a dup. Advance to persist when all tasks folded."""
    if task_key not in rs.get("filter_jobs", {}) or task_key in rs["filter_folded"]:
        return rs
    out = dict(rs)
    fv = {k: dict(v) for k, v in rs["filter_verdicts"].items()}
    fv.setdefault(category, {}).update({str(k): v for k, v in verdicts.items()})
    out["filter_verdicts"] = fv
    out["filter_folded"] = [*rs["filter_folded"], task_key]
    if set(out["filter_folded"]) >= set(rs["filter_jobs"].keys()):
        out["stage"] = PERSIST
    return out


def filter_complete(rs: dict[str, Any]) -> bool:
    return set(rs.get("filter_folded", [])) >= set(rs.get("filter_jobs", {}).keys())


# ── candidates view ───────────────────────────────────────────────────────────

def candidates_dict(rs: dict[str, Any]) -> dict[str, list]:
    """The accumulated Pass2Candidates payload at persist time."""
    return {
        "entities": rs["entities"],
        "relations": rs["relations"],
        "events": rs["events"],
        "facts": rs["facts"],
    }
