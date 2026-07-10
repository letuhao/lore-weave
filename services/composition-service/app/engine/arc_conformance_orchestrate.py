"""Shared arc-conformance orchestration (D-W10-ARC-CONFORMANCE-DEEP-JOB).

``compute_arc_report`` is the ONE place that turns a resolved arc (the durable SPEC
``structure_node`` OR an ``arc_template``) + its materialized bindings into the coarse
report (+ the optional deep, realized-from-PROSE overlay). It is called from:

  * the synchronous ``GET …/conformance?scope=arc`` (spec path, ``by_structure=True``) and
    ``?scope=arc_template_drift`` (the split-out template-drift path, ``by_structure=False``)
    — small books / tests, and
  * the Tier-W ``run_conformance_run`` worker (the production path for the deep overlay —
    the deep+model_ref tagging fires ~tag-threads+tag-motifs+causal-edges over the whole
    book, a storm that times out on a GET; the job is its sanctioned home).

BA4 (23_book_architecture): ``by_structure`` selects the binding-provenance axis. True reads
``motif_application`` by the ``structure_node_id`` column Deploy 1 added (the spec is what the
prose is measured against — "did the prose realize *my plan*"). False reads the legacy
``annotations->>'arc_template_id'`` (the template-drift path). The two are otherwise identical.

It takes its ``reader`` / ``mrepo`` / ``knowledge`` collaborators INJECTED (duck-typed) so
this module imports only the pure builders — no router import, no import cycle. The caller is
responsible for resolving + H13-guarding the arc; this function trusts the passed ``arc``.

Provider-gateway invariant: the deep tagging routes through the knowledge client with the
caller-supplied ``model_ref``/``model_source`` (BYOK) — NO provider SDK / model literal here.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.engine.arc_conformance import (arc_layout, arc_threads,
                                        build_arc_conformance, build_deep_report)


async def compute_arc_report(
    *,
    reader: Any,
    mrepo: Any,
    knowledge: Any,
    user_id: UUID,
    project_id: UUID,
    book_id: UUID,
    arc: Any,
    by_structure: bool = False,
    deep: bool = False,
    model_ref: str | None = None,
    model_source: str | None = None,
    llm: Any = None,
) -> dict[str, Any]:
    """Coarse arc-conformance (+ optional deep overlay). ``arc`` must already be resolved and
    visibility-checked by the caller. ``by_structure`` (BA4): True reads the bindings by
    ``structure_node_id`` (``arc`` is a ``structure_node``, ``arc.id`` its id); False reads the
    legacy ``annotations->>'arc_template_id'`` (``arc`` is an ``arc_template``). ``deep`` adds the
    realized-from-PROSE overlay; when a ``model_ref`` is supplied it FIRST tags the book's events
    into the arc's thread + placement vocab and infers causal edges (the expensive path), else the
    overlay is pacing-only over any pre-existing tags. Returns the report dict.

    ``llm`` (the composition LLM client) is the EXTRA the Tier-W job passes that the synchronous
    GET does not: with it (+ model_ref) the deepest succession signal runs — the entailment judge
    over the placement motifs' effects/preconditions (D-SUCCESSION-ENTAILMENT-JUDGE). Without it
    the deep overlay is structural + causal only (the GET's lighter path)."""
    # Coarse — the materialized bindings vs the plan (no LLM). BA4: read by structure_node_id
    # (spec) or the legacy arc_template_id annotation (template-drift).
    rows = await (reader.arc_bindings_by_structure(project_id, arc.id) if by_structure
                  else reader.arc_bindings(project_id, arc.id))
    order: dict[Any, int] = {}
    for r in rows:
        ch = r["chapter_id"]
        if ch not in order:
            order[ch] = len(order) + 1
    realized = [{
        "motif_id": str(r["motif_id"]) if r["motif_id"] else None,
        "motif_code": r["motif_code"],
        "thread": (r["annotations"] or {}).get("thread"),
        "chapter_index": order[r["chapter_id"]],
        "tension": r["tension"],
    } for r in rows]
    realized_ids = [UUID(x["motif_id"]) for x in realized if x["motif_id"]]
    succ_map = await mrepo.successors_by_ids(realized_ids)
    precedes_pairs = {(frm, s["id"]) for frm, lst in succ_map.items() for s in lst}
    report = build_arc_conformance(arc=arc, realized=realized, precedes_pairs=precedes_pairs)

    if not deep:
        return report

    # DEEP overlay — the realized-from-PROSE diff (cross-service, motif_beat extractor).
    # BA4: the template path draws the tag vocab from the planned `layout`; the spec path has
    # NO layout (BA5), so its vocab is the realized bindings' motif codes (what actually bound).
    layout = arc_layout(arc)
    placement_codes = sorted(
        {p.get("motif_code") for p in layout if p.get("motif_code")} if layout
        else {r["motif_code"] for r in realized if r.get("motif_code")}
    )
    placement_motifs = await mrepo.get_by_codes(user_id, placement_codes)
    id_to_code = {str(m.id): m.code for m in placement_motifs.values()}
    if model_ref:
        ms = model_source or "user_model"
        # Tag the book's events into the arc's thread vocab (→ thread-progression) AND its
        # placement-motif vocab (→ succession), then infer causal edges (→ causal-verify).
        await knowledge.tag_threads(
            user_id, book_id=book_id, threads=arc_threads(arc),
            model_source=ms, model_ref=model_ref)
        await knowledge.tag_motifs(
            user_id, book_id=book_id,
            motifs=[{"code": m.code, "name": m.name, "summary": m.summary}
                    for m in placement_motifs.values()],
            model_source=ms, model_ref=model_ref)
        await knowledge.infer_causal_edges(
            user_id, book_id=book_id, model_source=ms, model_ref=model_ref)
    seqs = await knowledge.get_motif_beat_sequences(user_id, book_id=book_id)
    # the precedes graph over the placement motifs, keyed by CODE (the realized axis).
    succ_map = await mrepo.successors_by_ids([m.id for m in placement_motifs.values()])
    precedes_code_pairs = {(id_to_code[frm], id_to_code[s["id"]])
                           for frm, lst in succ_map.items() for s in lst
                           if frm in id_to_code and s["id"] in id_to_code}
    causal_code_pairs = set(await knowledge.causal_motif_pairs(user_id, book_id=book_id))
    # D-SUCCESSION-ENTAILMENT-JUDGE — does A's effects entail B's preconditions over each legal
    # precedes edge? Advisory LLM judge over the resolved placement motifs' JSONB. Only the Tier-W
    # job passes `llm` (the GET stays structural+causal); degrades to structural-only on failure.
    entailed_code_pairs: set[tuple[str, str]] = set()
    if llm is not None and model_ref:
        from app.engine.succession_entailment import judge_entailments
        edges = []
        for fc, tc in precedes_code_pairs:
            fm, tm = placement_motifs.get(fc), placement_motifs.get(tc)
            if fm is None or tm is None:
                continue
            edges.append({"from_code": fc, "to_code": tc,
                          "from_name": getattr(fm, "name", fc), "to_name": getattr(tm, "name", tc),
                          "from_effects": getattr(fm, "effects", None),
                          "to_preconditions": getattr(tm, "preconditions", None)})
        entailed_code_pairs = await judge_entailments(
            llm, user_id=str(user_id), model_source=(model_source or "user_model"),
            model_ref=model_ref, edges=edges)
    report["deep"] = build_deep_report(
        sequences=seqs or [],
        chapter_index_by_id={str(ch): idx for ch, idx in order.items()},
        planned_by_index={pt["chapter_index"]: pt["avg_tension"]
                          for pt in report["pacing"]["realized"]},
        arc_threads=arc_threads(arc),
        precedes_code_pairs=precedes_code_pairs,
        causal_code_pairs=causal_code_pairs,
        entailed_code_pairs=entailed_code_pairs,
    )
    return report
