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

# C12 — map the plural contract target names to the singular decoupled op
# names. `entities`/`summaries` are not trio ops (entity is its own stage;
# summaries is orchestrator-gated on the persist side).
_PLURAL_TO_OP = {"relations": "relation", "events": "event", "facts": "fact"}


def _resolve_trio_targets(targets: "list[str] | None") -> list[str]:
    """C12 — the requested trio op subset (singular), in canonical order.
    None / empty ⇒ ALL three (back-compat). Order-stable on TRIO_OPS."""
    if not targets:
        return list(TRIO_OPS)
    requested = {_PLURAL_TO_OP[t] for t in targets if t in _PLURAL_TO_OP}
    return [op for op in TRIO_OPS if op in requested]

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
    targets: "list[str] | None" = None,
) -> dict[str, Any]:
    """Seed state for one chunk. `has_recovery`/`has_filter` reflect the project's
    resolved config (eff_recovery / eff_filter is not None in the runner).

    C12 — `targets` (the job's plural pass subset, None ⇒ all) is reduced to
    the requested trio op set (`trio_targets`). When EMPTY (no R/E/F
    requested — e.g. an entities-only build) the entity stage short-circuits
    straight to recovery/filter/persist; the trio is skipped entirely. The
    fan-in completes against `trio_targets`, NOT the full TRIO_OPS, so a
    subset job advances correctly."""
    return {
        "mode": "extract",
        "chunk_text": chunk_text,
        "known_entities": list(known_entities),
        "has_recovery": has_recovery,
        "has_filter": has_filter,
        # C12 — the requested trio ops (singular). None/empty ⇒ all three.
        "trio_targets": _resolve_trio_targets(targets),
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

def _requested_trio_ops(rs: dict[str, Any]) -> list[str]:
    """C12 — the trio op subset for this rs. Back-compat: a legacy rs without
    `trio_targets` (pre-C12 resume blob) ⇒ all three."""
    tt = rs.get("trio_targets")
    return list(tt) if tt is not None else list(TRIO_OPS)


def apply_entity_result(rs: dict[str, Any], entities: list) -> dict[str, Any]:
    """Fold the entity stage. Returns new rs with entities set + the stage advanced:
    no entities ⇒ go straight to persist (Pass2Candidates short-circuit — nothing to
    anchor relations/events/facts to). C12 — if NO trio op is requested (an
    entities-only build), skip the trio and go to recovery/filter/persist
    directly; else ⇒ trio."""
    out = dict(rs)
    out["entities"] = list(entities)
    if not entities:
        out["stage"] = PERSIST
    elif _requested_trio_ops(out):
        out["stage"] = TRIO
    else:
        # entities-only build — no R/E/F to anchor; advance past trio.
        out["stage"] = _after_trio(out)
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
    # C12 — complete when the REQUESTED trio subset is folded (not all three),
    # so a subset job (e.g. events-only) advances instead of hanging in trio.
    if set(out["trio_folded"]) >= set(_requested_trio_ops(out)):
        out["stage"] = _after_trio(out)
    return out


def trio_complete(rs: dict[str, Any]) -> bool:
    return set(rs.get("trio_folded", [])) >= set(_requested_trio_ops(rs))


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
    """The accumulated Pass2Candidates payload (SERIALIZED dicts) at persist time."""
    return {
        "entities": rs["entities"],
        "relations": rs["relations"],
        "events": rs["events"],
        "facts": rs["facts"],
    }


# ── shell: submit-assembly + fold-dispatch over the WX-T2 seams ────────────────
# WX-T3b. Bridges the pure SM + the SDK extractor seams. Candidates are pydantic
# models → stored SERIALIZED (model_dump) in resume_state JSONB, reconstructed where
# the SDK needs objects (the trio postprocess anchors to entity objects; persist_pass2
# takes objects). Imports are local to keep the pure-SM section import-free + dodge
# any import cycle. ENTITY→TRIO only for this increment (recovery/filter-configured
# projects fall back to the synchronous extract_pass2 in the runner branch).


def _ser(items: list) -> list[dict]:
    return [it.model_dump(mode="json") for it in items]


def reconstruct_entities(rs: dict[str, Any]) -> list:
    from loreweave_extraction.extractors.entity import LLMEntityCandidate
    return [LLMEntityCandidate.model_validate(d) for d in rs.get("entities", [])]


def reconstruct_candidates(rs: dict[str, Any]):
    """Rebuild a Pass2Candidates from the serialized accumulators (for persist)."""
    from loreweave_extraction.extractors.entity import LLMEntityCandidate
    from loreweave_extraction.extractors.event import LLMEventCandidate
    from loreweave_extraction.extractors.fact import LLMFactCandidate
    from loreweave_extraction.extractors.relation import LLMRelationCandidate
    from loreweave_extraction.pass2 import Pass2Candidates
    return Pass2Candidates(
        entities=[LLMEntityCandidate.model_validate(d) for d in rs.get("entities", [])],
        relations=[LLMRelationCandidate.model_validate(d) for d in rs.get("relations", [])],
        events=[LLMEventCandidate.model_validate(d) for d in rs.get("events", [])],
        facts=[LLMFactCandidate.model_validate(d) for d in rs.get("facts", [])],
    )


def _schema_from(rs: dict[str, Any]):
    """L7 (Milestone B) — rebuild the ADVISORY ExtractionSchema stashed in
    resume_state (None when the project has no resolved schema). The stashed dict
    has allow_free_edges=True, so the SDK injects the vocab as a prompt hint but
    never pre-drops an off-vocab predicate — /persist-pass2 stays the sole
    enforce+park point (the R3 reconciliation)."""
    raw = rs.get("_schema")
    if not raw:
        return None
    from loreweave_extraction.schema_projection import ExtractionSchema
    return ExtractionSchema.from_resolved(raw)


def assemble_entity_submit(rs: dict[str, Any]) -> dict:
    """Submit kwargs for the entity stage (build_entity_system + build_entity_submit_kwargs).
    context_budget=None matches worker-ai's extract_pass2 call (chunk_size=15)."""
    from loreweave_extraction.extractors.entity import (
        build_entity_submit_kwargs, build_entity_system,
    )
    po = rs.get("prompt_overrides") or {}
    system = build_entity_system(rs["known_entities"], po.get("entity"), schema=_schema_from(rs))
    return build_entity_submit_kwargs(
        system_prompt=system, text=rs["chunk_text"],
        model_source=rs["model_source"], model_ref=rs["model_ref"],
        project_id=rs["project_id"], context_budget=None,
        # D-KG-WORKER-GRADED-EFFORT — graded effort stashed in resume_state by
        # _start_decoupled_chunk. Default "none" (legacy/pre-effort blob) ⇒ off.
        reasoning_effort=rs.get("reasoning_effort", "none"),
    )


def fold_entity_job(rs: dict[str, Any], job, on_dropped=None) -> dict[str, Any]:
    """Apply the entity terminal Job → serialize → advance the SM. Also computes
    all_known (known ∪ entity names) for the trio, exactly as extract_pass2 does."""
    from loreweave_extraction.extractors.entity import apply_entity_job
    entities = apply_entity_job(
        job, on_dropped=on_dropped, user_id=rs["user_id"],
        project_id=rs["project_id"], known_entities=rs["known_entities"],
    )
    out = apply_entity_result(rs, _ser(entities))
    out["all_known"] = list(set(list(rs["known_entities"]) + [e.name for e in entities]))
    return out


def assemble_trio_submits(rs: dict[str, Any]) -> dict[str, dict]:
    """{op: submit_kwargs} for the 3 concurrent trio jobs (relation/event/fact),
    anchored to all_known (= known ∪ entity names), matching extract_pass2."""
    from loreweave_extraction.extractors import event, fact, relation
    po = rs.get("prompt_overrides") or {}
    known = rs["all_known"]
    common = dict(
        text=rs["chunk_text"], model_source=rs["model_source"],
        model_ref=rs["model_ref"], project_id=rs["project_id"], context_budget=None,
        # D-KG-WORKER-GRADED-EFFORT — same graded effort as the entity submit
        # (stashed in resume_state). Default "none" (legacy blob) ⇒ off.
        reasoning_effort=rs.get("reasoning_effort", "none"),
    )
    # C12 — build the submit-dict CONDITIONALLY for only the requested trio
    # ops. begin_trio records exactly these job ids, and the fan-in completes
    # against the same subset (trio_complete uses _requested_trio_ops).
    requested = set(_requested_trio_ops(rs))
    sch = _schema_from(rs)  # L7 (Milestone B) — advisory vocab hint (None ⇒ static)
    builders = {
        "relation": lambda: relation.build_relation_submit_kwargs(
            system_prompt=relation.build_relation_system(known, po.get("relation"), schema=sch), **common),
        "event": lambda: event.build_event_submit_kwargs(
            system_prompt=event.build_event_system(known, po.get("event"), schema=sch), **common),
        "fact": lambda: fact.build_fact_submit_kwargs(
            system_prompt=fact.build_fact_system(known, po.get("fact"), schema=sch), **common),
    }
    return {op: build() for op, build in builders.items() if op in requested}


def fold_trio_job(rs: dict[str, Any], op: str, job, on_dropped=None) -> dict[str, Any]:
    """Apply one trio op's terminal Job (anchored to the reconstructed entities) →
    serialize → fold into the fan-in. Advances when all 3 ops have folded."""
    from loreweave_extraction.extractors import event, fact, relation
    entities = reconstruct_entities(rs)
    known = rs["all_known"]
    if op == "relation":
        items = relation.apply_relation_job(
            job, on_dropped=on_dropped, entities=entities, known_entities=known,
            user_id=rs["user_id"], project_id=rs["project_id"])
    elif op == "event":
        items = event.apply_event_job(
            job, on_dropped=on_dropped, entities=entities, known_entities=known,
            user_id=rs["user_id"])
    elif op == "fact":
        items = fact.apply_fact_job(
            job, on_dropped=on_dropped, entities=entities, known_entities=known,
            user_id=rs["user_id"])
    else:
        return rs
    return fold_trio_op(rs, op, _ser(items))


# ── recovery shell (WX Wave 4) — Tier-3 LLM classifier fan-out ──────────────────
# Tier-1+2 (glossary/hints, no LLM) runs inline in assemble_recovery; worker-ai has no
# glossary access so known_entity_kinds is empty ⇒ every unmatched name goes to Tier-3.
# Each Tier-3 batch is a fire-and-forget submit; on its terminal the verdicts are applied
# into the (promoted, name_verdict) accumulators and finalize_recovery recomputes
# entities/relations from the immutable post-trio base (idempotent/monotonic each fold).


def _recovery_config(rs: dict[str, Any]):
    from loreweave_extraction.entity_recovery import EntityRecoveryConfig
    c = rs["_recovery_cfg"]
    return EntityRecoveryConfig(
        model_ref=c["model_ref"],
        model_source=c.get("model_source", "user_model"),
        max_items_per_batch=c.get("max_items_per_batch", 5),
        transient_retry_budget=c.get("transient_retry_budget", 1),
        known_entity_kinds=dict(c.get("known_entity_kinds") or {}),
    )


def _candidates_from(entities_ser: list, relations_ser: list):
    """Minimal Pass2Candidates (entities + relations only) for finalize_recovery."""
    from loreweave_extraction.extractors.entity import LLMEntityCandidate
    from loreweave_extraction.extractors.relation import LLMRelationCandidate
    from loreweave_extraction.pass2 import Pass2Candidates
    return Pass2Candidates(
        entities=[LLMEntityCandidate.model_validate(d) for d in entities_ser],
        relations=[LLMRelationCandidate.model_validate(d) for d in relations_ser],
    )


def assemble_recovery(rs: dict[str, Any]) -> tuple[dict[str, dict], dict[str, Any]]:
    """Run Tier-1+2 inline + build the Tier-3 LLM batch submits. Returns
    ({batch_key: submit_kwargs}, rs2) with the recovery accumulators seeded (immutable
    base snapshot + promoted/name_verdict + batch→names map). An empty map ⇒ no Tier-3
    work (Tier-1+2 already finalized into entities/relations); the dispatcher then calls
    begin_recovery({}) to advance to filter/persist."""
    from loreweave_extraction.entity_recovery import (
        build_recovery_batches, build_recovery_submit_kwargs,
        finalize_recovery, prepare_recovery,
    )
    cfg = _recovery_config(rs)
    cands = reconstruct_candidates(rs)
    promoted, name_verdict, still_unmatched, unmatched = prepare_recovery(
        cands, config=cfg, user_id=rs["user_id"],
        project_id=rs.get("project_id"), on_decision=None,
    )
    out = dict(rs)
    out["recovery_base_entities"] = list(rs["entities"])
    out["recovery_base_relations"] = list(rs["relations"])
    out["recovery_promoted"] = _ser(promoted)
    out["recovery_name_verdict"] = dict(name_verdict)
    out["recovery_batch_names"] = {}
    if not unmatched or not still_unmatched:
        # Nothing for the LLM (no unmatched, or all resolved by Tier-1+2). Apply the
        # promote/abstract-drop now so the stage's effect still lands, then no submits.
        final = finalize_recovery(cands, promoted, name_verdict)
        out["entities"] = _ser(final.entities)
        out["relations"] = _ser(final.relations)
        return {}, out
    system, batches = build_recovery_batches(still_unmatched, rs["chunk_text"], cfg)
    submits: dict[str, dict] = {}
    for user_msg, n_items, batch_start in batches:
        key = f"r{batch_start}"
        out["recovery_batch_names"][key] = still_unmatched[batch_start:batch_start + n_items]
        submits[key] = build_recovery_submit_kwargs(
            config=cfg, system=system, user=user_msg, n_items=n_items,
        )
    return submits, out


def fold_recovery_terminal(rs: dict[str, Any], batch_key: str, job) -> dict[str, Any]:
    """Apply one Tier-3 recovery batch terminal → accumulate promoted/name_verdict →
    recompute entities/relations via finalize_recovery (from the immutable base) → SM
    fold_recovery_task. Idempotent on a dup terminal for an already-folded batch."""
    from loreweave_extraction.entity_recovery import (
        _parse_decisions, apply_recovery_batch, finalize_recovery, parse_recovery_job,
    )
    from loreweave_extraction.extractors.entity import LLMEntityCandidate
    if batch_key not in rs.get("recovery_batch_names", {}):
        return rs  # unknown job (superseded/foreign)
    if batch_key in rs.get("recovery_folded", []):
        return rs  # already folded — don't re-apply the verdicts (idempotent)
    batch = rs["recovery_batch_names"][batch_key]
    try:
        decisions = _parse_decisions(parse_recovery_job(job))
    except Exception:  # noqa: BLE001 — a bad/empty batch degrades to all-unjudged
        decisions = {}
    promoted = [LLMEntityCandidate.model_validate(d) for d in rs.get("recovery_promoted", [])]
    name_verdict = dict(rs.get("recovery_name_verdict", {}))
    apply_recovery_batch(
        batch, decisions, promoted_out=promoted, name_verdict_out=name_verdict,
        user_id=rs["user_id"], project_id=rs.get("project_id"), on_decision=None,
    )
    base = _candidates_from(rs["recovery_base_entities"], rs["recovery_base_relations"])
    final = finalize_recovery(base, promoted, name_verdict)
    out = dict(rs)
    out["recovery_promoted"] = _ser(promoted)
    out["recovery_name_verdict"] = name_verdict
    return fold_recovery_task(
        out, batch_key, entities=_ser(final.entities), relations=_ser(final.relations),
    )


# ── filter shell (WX Wave 4) — category × batch fan-out ─────────────────────────
# Each (category, batch) is a fire-and-forget submit; on its terminal the per-item
# verdicts fold into the {category: {global_idx: verdict}} accumulator. When all fold,
# finalize_filter computes the kept set per category (compute_filter_kept) + stitches
# the surviving items back into entities/relations/events (facts unfiltered).


def _filter_config(rs: dict[str, Any]):
    from loreweave_extraction.pass2_filter import PrecisionFilterConfig
    c = rs["_filter_cfg"]
    return PrecisionFilterConfig(
        model_ref=c["model_ref"],
        model_source=c.get("model_source", "user_model"),
        partial_policy=c.get("partial_policy", "keep"),
        categories=tuple(c.get("categories") or ("entity", "relation", "event")),
        max_items_per_batch=c.get("max_items_per_batch", 3),
        transient_retry_budget=c.get("transient_retry_budget", 1),
    )


def _filter_cat_items(rs: dict[str, Any]) -> dict[str, list]:
    cands = reconstruct_candidates(rs)
    return {"entity": cands.entities, "relation": cands.relations, "event": cands.events}


def assemble_filter(rs: dict[str, Any]) -> tuple[dict[str, dict], dict[str, Any]]:
    """Build the per-(category, batch) filter submits over the post-recovery candidates.
    Returns ({task_key: submit_kwargs}, rs2) with filter_batch_meta + filter_n_input
    seeded. Empty map ⇒ no items in any configured category (dispatcher → persist)."""
    from loreweave_extraction.pass2_filter import (
        build_filter_category_batches, build_filter_submit_kwargs,
    )
    cfg = _filter_config(rs)
    cat_items = _filter_cat_items(rs)
    out = dict(rs)
    out["filter_batch_meta"] = {}
    out["filter_n_input"] = {}
    submits: dict[str, dict] = {}
    for category in cfg.categories:
        items = cat_items.get(category, [])
        out["filter_n_input"][category] = len(items)
        if not items:
            continue
        system, batches = build_filter_category_batches(
            category, items, rs["chunk_text"], cfg,
        )
        for user_msg, n_items, batch_start in batches:
            key = f"f:{category}:{batch_start}"
            out["filter_batch_meta"][key] = {
                "category": category, "batch_start": batch_start, "n_items": n_items,
            }
            submits[key] = build_filter_submit_kwargs(
                config=cfg, system=system, user=user_msg, n_items=n_items,
            )
    return submits, out


def fold_filter_terminal(rs: dict[str, Any], task_key: str, job) -> dict[str, Any]:
    """Apply one filter batch terminal → parse per-item verdicts → map local→global idx
    → SM fold_filter_task. Idempotent on a dup for an already-folded task."""
    from loreweave_extraction.pass2_filter import _parse_verdicts, parse_filter_job
    meta = rs.get("filter_batch_meta", {}).get(task_key)
    if meta is None:
        return rs
    if task_key in rs.get("filter_folded", []):
        return rs
    try:
        local = _parse_verdicts(parse_filter_job(job), meta["n_items"])
    except Exception:  # noqa: BLE001 — a bad batch degrades to all-unjudged
        local = {}
    verdicts = {meta["batch_start"] + k: v for k, v in local.items()}
    return fold_filter_task(rs, task_key, meta["category"], verdicts)


def finalize_filter(rs: dict[str, Any]) -> dict[str, Any]:
    """Compute the kept set per category (compute_filter_kept) + stitch the surviving
    items back into entities/relations/events. Facts are never filtered. Applied once,
    when the filter fan-in completes (SM stage → persist)."""
    from loreweave_extraction.pass2_filter import compute_filter_kept
    cfg = _filter_config(rs)
    cat_items = _filter_cat_items(rs)
    fv = rs.get("filter_verdicts", {})
    out = dict(rs)
    rs_key = {"entity": "entities", "relation": "relations", "event": "events"}
    for category in cfg.categories:
        items = cat_items[category]
        n_input = rs.get("filter_n_input", {}).get(category, len(items))
        verdicts_by_idx = {int(k): v for k, v in fv.get(category, {}).items()}
        kept, _coverage = compute_filter_kept(category, n_input, verdicts_by_idx, cfg, None)
        out[rs_key[category]] = _ser([items[i] for i in kept])
    return out
