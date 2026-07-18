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

import hashlib
import json
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


# ═══════════════════════════════════════════════════════════════════════════════
# 26 IX-8/IX-9/IX-14 — durable, input-pinned conformance snapshots + the ONE
# staleness read contract. The SAME member/binding/fingerprint helpers assemble the
# manifest at PERSIST time (compute_arc_report's two callers) AND recompute the
# comparison at READ time (the status route + MCP tool), so persist and read can
# never disagree about what "the book moved" means (reconcile-by-truth: one
# computation, not two). This module imports only repos (no router import), so both
# the router and the MCP server compose it without an import cycle.
# ═══════════════════════════════════════════════════════════════════════════════


async def _member_chapter_rows(pool: Any, book_id: UUID, arc_id: UUID) -> list[Any]:
    """The arc's member outline nodes for the spec fingerprint + the manifest's
    chapter list. Member chapters are the arc SUBTREE's chapter-kind nodes
    (`outline_node.structure_node_id` in subtree(arc) — BA6), and this returns those
    chapters PLUS their scenes (the fingerprint must move when a scene's planned
    tension/order/beat_role changes, or a scene-plan edit would false-CLEAN a report).
    Book-scoped (defense-in-depth) and DETERMINISTICALLY ordered so the hash is stable."""
    async with pool.acquire() as c:
        return await c.fetch(
            """
            WITH RECURSIVE subtree AS (
              SELECT id FROM structure_node WHERE id = $1
              UNION
              SELECT s.id FROM structure_node s JOIN subtree t ON s.parent_id = t.id
            ),
            member_chapters AS (
              SELECT DISTINCT chapter_id FROM outline_node
              WHERE structure_node_id IN (SELECT id FROM subtree)
                AND kind = 'chapter' AND NOT is_archived
                AND book_id = $2 AND chapter_id IS NOT NULL
            )
            SELECT id, chapter_id, version, tension, story_order, beat_role, kind
            FROM outline_node
            WHERE book_id = $2 AND NOT is_archived
              AND kind IN ('chapter', 'scene')
              AND chapter_id IN (SELECT chapter_id FROM member_chapters)
            ORDER BY chapter_id, story_order NULLS LAST, id
            """,
            arc_id, book_id,
        )


async def _binding_rows(pool: Any, book_id: UUID, arc_id: UUID) -> list[Any]:
    """The arc's realized bindings for the bindings fingerprint — keyed on
    `motif_application.structure_node_id = arc_id` (EXACTLY the axis
    ``arc_bindings_by_structure`` measures conformance over, BA4), book-scoped.
    Ordered by id for a stable hash."""
    async with pool.acquire() as c:
        return await c.fetch(
            """
            SELECT id, motif_version, outline_node_id
            FROM motif_application
            WHERE structure_node_id = $1 AND book_id = $2
            ORDER BY id
            """,
            arc_id, book_id,
        )


def _sha(material: Any) -> str:
    """Stable sha256 over a JSON-serialized value (sorted keys, str fallback)."""
    return "sha256:" + hashlib.sha256(
        json.dumps(material, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _spec_fingerprints(arc: Any, member_rows: list[Any], binding_rows: list[Any]) -> dict[str, Any]:
    """The manifest's `spec` block (IX-8): `structure_node_version` + a coarse
    `outline_fingerprint` (ordered member nodes' id/version/tension/story_order/
    beat_role) + a `bindings_fingerprint` (the arc's motif_application rows'
    id/motif_version/outline_node_id). Hashes VALUES, never timestamps, so a no-op
    touch cannot false-dirty (and a false-clean is impossible — every conformance
    input is covered). ALL leaf values are JSON scalars (int/str/None) so a JSONB
    round-trip compares equal to a freshly-computed dict."""
    outline_material = [
        [str(r["id"]), r["version"], r["tension"], r["story_order"], r["beat_role"]]
        for r in member_rows
    ]
    bindings_material = [
        [str(r["id"]), r["motif_version"],
         str(r["outline_node_id"]) if r["outline_node_id"] is not None else None]
        for r in binding_rows
    ]
    return {
        "structure_node_version": int(getattr(arc, "version", 0) or 0),
        "outline_fingerprint": _sha(outline_material),
        "bindings_fingerprint": _sha(bindings_material),
    }


async def assemble_input_manifest(
    *, pool: Any, book_client: Any, book_id: UUID, arc: Any,
) -> dict[str, Any]:
    """Build the IX-8 `input_manifest` — `{v:1, chapters:[...], spec:{...}}` — from the
    SAME reads the compute just did, so the report and its manifest describe one book
    state. `chapters` carries every member chapter's canon markers (published_revision_id
    + the IX-4 chapter-scalar parse_version) AS READ AT COMPUTE TIME through IX-9's batch
    route; `spec` is the fingerprint block. A degraded canon-markers read (book-service
    down → {}) yields null markers here — erring conservative (a later status read then
    sees prose_drift), never a crash."""
    member_rows = await _member_chapter_rows(pool, book_id, arc.id)
    binding_rows = await _binding_rows(pool, book_id, arc.id)
    chapter_ids = list(dict.fromkeys(
        r["chapter_id"] for r in member_rows if r["chapter_id"] is not None))
    markers: dict[str, Any] = {}
    if chapter_ids:
        markers = await book_client.canon_markers(book_id, chapter_ids)
    chapters = []
    for cid in chapter_ids:
        m = markers.get(str(cid)) or {}
        chapters.append({
            "chapter_id": str(cid),
            # WS-0.7: kg_indexed_revision_id is what _dirty_reasons compares against
            # (the revision the scenes the report binds to were parsed from). It MUST be
            # recorded here — record only published_revision_id and every subsequent
            # status poll would compare a present marker against an absent record and
            # report prose_drift forever, re-running the token-costly conformance job.
            # published_revision_id stays for provenance/back-compat with old readers.
            "kg_indexed_revision_id": m.get("kg_indexed_revision_id"),
            "published_revision_id": m.get("published_revision_id"),
            "parse_version": m.get("parse_version"),
        })
    return {"v": 1, "chapters": chapters,
            "spec": _spec_fingerprints(arc, member_rows, binding_rows)}


async def persist_conformance_state(
    *, pool: Any, book_client: Any, book_id: UUID, arc: Any,
    report: dict[str, Any], deep: bool, generation_job_id: str | UUID | None = None,
) -> dict[str, Any]:
    """IX-8 — the ONE persist seam. Assemble the manifest, then UPSERT-latest the
    (report, manifest, deep, provenance) snapshot for this arc. Called by BOTH
    `compute_arc_report` callers immediately after compute; only the durable-SPEC arc
    path (a `structure_node`) persists — the template-drift path (an `arc_template`)
    never reaches here. Returns the manifest (for tests/callers). Not itself
    fail-soft: the CALLER wraps it best-effort so a snapshot-write failure never holds
    the primary report hostage (OQ-1 philosophy)."""
    from app.db.repositories.conformance_state import ConformanceStateRepo

    manifest = await assemble_input_manifest(
        pool=pool, book_client=book_client, book_id=book_id, arc=arc)
    await ConformanceStateRepo(pool).upsert(
        book_id=book_id, structure_node_id=arc.id,
        report=report, input_manifest=manifest, deep=bool(deep),
        generation_job_id=generation_job_id)
    return manifest


# ── IX-9 dirty predicate (poll-on-read) + IX-14 status computation ──────────────

# The closed set of dirty reasons (IX-9). Surfaced through the status route/tool;
# the output vocabulary is asserted by the contract snapshot test.
DIRTY_REASONS = ("never_run", "prose_drift", "spec_drift", "index_stale")


def _norm(v: Any) -> str | None:
    """Normalize a revision-id marker to a comparable form — a cross-boundary value
    (markers are JSON strings; recorded manifest values are strings) reconciled to str,
    None preserved (the cross-service-normalization-bug-class guard)."""
    return None if v is None else str(v)


def _dirty_reasons(
    *, snap: Any, arc: Any, member_rows: list[Any], binding_rows: list[Any],
    chapter_ids: list[Any], markers: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Compute an arc's dirty reasons + its stale chapter ids from the snapshot's
    manifest vs the current markers + recomputed fingerprints (IX-9). Never writes."""
    manifest = snap.input_manifest or {}
    reasons: list[str] = []

    # WS-0.7 — both drift signals are re-keyed onto kg_indexed_revision_id (the revision
    # the knowledge layer + the scene index reflect), NOT published_revision_id.
    # Spec: docs/specs/2026-07-11-publish-independent-kg-indexing.md §3.6 (red-team P0-3).
    #
    # Why: the conformance report binds motifs to SCENES, and scenes are now parsed from
    # the INDEXED revision (which may be a draft the user explicitly indexed). Keying the
    # drift signals on published_revision_id would report against a revision the report
    # was never computed from.
    #
    # LEGACY MANIFEST FALLBACK (cost-motivated, deliberate): snapshots written before
    # WS-0.7 recorded only `published_revision_id`. If the new key is ABSENT we fall back
    # to it. For every pre-WS-0.7 chapter that is legitimate: the WS-0.2 migration seeded
    # kg_indexed_revision_id := published_revision_id, so the two are equal on the legacy
    # corpus and the comparison is identical. Without this fallback every existing arc
    # would read as drifted on first status poll and re-run its LLM-judged, token-costly
    # conformance job — a mass spend event triggered by a deploy.
    def _recorded_kg(c: dict) -> Any:
        if "kg_indexed_revision_id" in c:
            return c.get("kg_indexed_revision_id")
        return c.get("published_revision_id")  # legacy snapshot

    recorded = {str(c.get("chapter_id")): _recorded_kg(c)
                for c in (manifest.get("chapters") or [])}

    # prose_drift ⇔ ∃ recorded member chapter whose current kg_indexed_revision_id
    # differs (a publish, a re-index, an unpublish, an exclusion, or a delete since the
    # snapshot). COMP-STALE-1: collect the drifted chapters (do NOT break) — the
    # scene-inspector chip is `arc.dirty AND chapter IN stale_chapters` (IX-14), so a
    # prose-drifted chapter must be IN stale_chapters or it renders false-fresh.
    drifted: list[str] = []
    for cid_str, rec_kg in recorded.items():
        cur = markers.get(cid_str) or {}
        if _norm(cur.get("kg_indexed_revision_id")) != _norm(rec_kg):
            drifted.append(cid_str)
    if drifted:
        reasons.append("prose_drift")

    # spec_drift ⇔ current fingerprints ≠ the snapshot's (recompute both, compare).
    if _spec_fingerprints(arc, member_rows, binding_rows) != (manifest.get("spec") or {}):
        reasons.append("spec_drift")

    # index_stale ⇔ ∃ member chapter whose scene index lags the revision the knowledge
    # layer reflects. This REPEATS THE SWEEPER'S OWN (post-WS-0.5) PREDICATE, so the badge
    # can never fire on a chapter the sweeper is unable to heal — the invariant this block
    # has always been about, now stated against the right pointer.
    #
    # The old form (`editorial_status == 'published' AND last_parsed != published_rev`)
    # produced a PERMANENTLY-STUCK badge once indexing decoupled from publishing:
    # publish@A → index draft@B ⇒ composition saw `published AND last_parsed(B) !=
    # published(A)` ⇒ stale, while the sweeper saw `last_parsed(B) == kg_indexed(B)` ⇒
    # nothing to heal. The arc's conformance report stayed dirty forever.
    #
    # kg_exclude'd chapters are NOT stale: the sweeper skips them by design, so a badge
    # firing on one could never clear either.
    index_stale: list[str] = []
    for cid in chapter_ids:
        m = markers.get(str(cid)) or {}
        kg_rev = m.get("kg_indexed_revision_id")
        if kg_rev is None or m.get("kg_exclude"):
            continue
        if _norm(m.get("last_parsed_revision_id")) != _norm(kg_rev):
            index_stale.append(str(cid))
    if index_stale:
        reasons.append("index_stale")

    # Per-arc stale_chapters = every chapter the inspector should chip (prose-drift ∪
    # index-stale). The index-stale set is returned separately so the book-level
    # `stale_chapter_count` rollup stays keyed on index staleness only (the two are
    # distinct concepts — a fresh-index but canon-moved chapter is dirty, not stale).
    stale_chapters = sorted(set(drifted) | set(index_stale))
    return reasons, stale_chapters, index_stale


def _summary_projection(report: dict[str, Any]) -> dict[str, Any]:
    """The fixed status `summary` projection of the stored report (OUT-1 reference-
    first — the full body is fetched per-arc via the existing conformance GET / job,
    not dumped in the status list). Tolerant of a coarse-only or deep report."""
    tp = report.get("thread_progress") or []
    planned = sum(int(t.get("planned") or 0) for t in tp if isinstance(t, dict))
    covered = sum(int(t.get("covered") or 0) for t in tp if isinstance(t, dict))
    succ = report.get("succession") or {}
    violations = sum(len(t.get("violations") or [])
                     for t in (succ.get("threads") or []) if isinstance(t, dict))
    return {
        "thread_progress": round(covered / planned, 2) if planned else 0.0,
        "pacing_drift": (report.get("pacing") or {}).get("max_drift"),
        "succession_violations": violations,
        "unmaterialized": len(report.get("unmaterialized") or []),
    }


async def compute_conformance_status(
    *, pool: Any, book_client: Any, book_id: UUID, arc_id: UUID | None = None,
) -> dict[str, Any]:
    """The IX-14 read contract (the ONE staleness computation). Returns per-arc
    freshness state + an `index.stale_chapter_count` rollup, cheap: `arc_conformance_
    state` + ONE canon-markers batch (across every snapshotted arc's member chapters)
    + in-DB fingerprint scans — no LLM, no re-extract. `never_run` (no snapshot) yields
    `computed_at:null, dirty:true` — absence is STATED, not omitted (a LIST that drops
    the field makes every consumer invent a default). 24's Hub consumes this route
    directly; 28's agent aggregates compose this same helper — one shape, no siblings."""
    from app.db.repositories.conformance_state import ConformanceStateRepo
    from app.db.repositories.structure import StructureRepo

    nodes = await StructureRepo(pool).list_tree(book_id)
    if arc_id is not None:
        nodes = [n for n in nodes if n.id == arc_id]
    snaps = {s.structure_node_id: s
             for s in await ConformanceStateRepo(pool).list_for_book(book_id)}

    # Gather member/binding rows for the SNAPSHOTTED arcs only (a never_run arc needs
    # no reads), and union their member chapters for ONE canon-markers batch.
    per_arc: dict[Any, tuple[list[Any], list[Any], list[Any]]] = {}
    all_chapter_ids: set[Any] = set()
    for n in nodes:
        if n.id in snaps:
            member_rows = await _member_chapter_rows(pool, book_id, n.id)
            binding_rows = await _binding_rows(pool, book_id, n.id)
            chapter_ids = list(dict.fromkeys(
                r["chapter_id"] for r in member_rows if r["chapter_id"] is not None))
            per_arc[n.id] = (member_rows, binding_rows, chapter_ids)
            all_chapter_ids.update(chapter_ids)

    markers: dict[str, Any] = {}
    if all_chapter_ids:
        markers = await book_client.canon_markers(book_id, list(all_chapter_ids))

    arcs: list[dict[str, Any]] = []
    global_stale: set[str] = set()
    for n in nodes:
        snap = snaps.get(n.id)
        if snap is None:
            arcs.append({
                "structure_node_id": str(n.id), "title": n.title, "kind": n.kind,
                "computed_at": None, "deep": False,
                "dirty": True, "dirty_reasons": ["never_run"],
                "stale_chapters": [], "summary": None,
            })
            continue
        member_rows, binding_rows, chapter_ids = per_arc[n.id]
        reasons, stale_chapters, index_stale = _dirty_reasons(
            snap=snap, arc=n, member_rows=member_rows, binding_rows=binding_rows,
            chapter_ids=chapter_ids, markers=markers)
        # The book-level rollup counts INDEX-stale chapters only (what the sweeper
        # heals); the per-arc chip surfaces prose-drift ∪ index-stale (COMP-STALE-1).
        global_stale.update(index_stale)
        arcs.append({
            "structure_node_id": str(n.id), "title": n.title, "kind": n.kind,
            "computed_at": snap.computed_at.isoformat() if snap.computed_at else None,
            "deep": bool(snap.deep),
            "dirty": bool(reasons), "dirty_reasons": reasons,
            "stale_chapters": stale_chapters,
            "summary": _summary_projection(snap.report or {}),
        })

    return {"book_id": str(book_id), "arcs": arcs,
            "index": {"stale_chapter_count": len(global_stale)}}
