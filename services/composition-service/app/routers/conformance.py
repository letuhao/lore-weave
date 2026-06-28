"""Motif-conformance trace read (W5, §4) — "why this scene": planned│realized│
conformance per scene in a chapter.

`GET /v1/composition/works/{project_id}/conformance?scope=chapter&chapter_id=…`
joins, per scene node:
  outline_node (PLANNED: beat_role, tension)
    ⋈ motif_application  (the bound motif_id + beat_key + role_bindings — W2-written)
    ⋈ generation_job     (the latest completed job + its critic.motif_conformance)

ADVISORY (§14.6): this is a READ of an advisory signal — it informs the author's
work/trace view (mockup 07-A) and feeds the existing "regenerate to beat" one-click
(it returns the outline_node_id + motif_id + beat_key that the existing scene-
regenerate needs as inputs). It never gates anything.

COARSE only (§14.2 / §R1.5): the join keys on the shared chapter_id; there is NO
fine offset-span attribution. The realized side is the LATEST completed
generation_job per node (the same rule stitch/publish use). `scope=arc` is accepted
in the contract (so the FE shape is stable) but returns a clear "not available
yet — P4" body (the §14.4 extract-diff is out of P1).

TENANCY: the two reads filter user_id + project_id on BOTH the application/job AND
the joined node (defense-in-depth — the kinds-bug lesson). A node-id-only query
would be a cross-tenant read.

OWNERSHIP: W5 owns this file. The two reads here are W5-local (the
`motif_application` table is W2/F0-owned but W5 only READS it; the binder writes
`motif_id`/`beat_key`-in-annotations). If W1/W2 later add a `MotifApplicationRepo`,
these reads can move there — but W5 does not edit their files to add them.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.models import MotifApplication, OutlineNode
from app.db.pool import get_pool
from app.db.repositories.arc_template_repo import ArcTemplateRepo
from app.db.repositories.motif_repo import MotifRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.works import WorksRepo
from app.clients.knowledge_client import KnowledgeClient
from app.deps import (get_arc_template_repo, get_knowledge_client_dep,
                      get_outline_repo, get_works_repo)
from app.engine.arc_conformance import build_arc_conformance, build_deep_report
from app.middleware.jwt_auth import get_current_user

router = APIRouter(prefix="/v1/composition")


class ConformanceTraceReader:
    """W5-owned read helper for the two trace joins (§4.2). Both queries are
    user+project scoped on BOTH the row AND the joined node (defense-in-depth)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def apps_by_nodes(
        self, user_id: UUID, project_id: UUID, node_ids: list[UUID],
    ) -> dict[UUID, MotifApplication]:
        """The bound motif_application per scene node (most-recent per node). READ-
        only; W2 is the sole writer. Returns a node_id → MotifApplication map."""
        if not node_ids:
            return {}
        # DISTINCT ON the node → the most-recent binding per node (a re-bind supersedes).
        rows = await self._pool.fetch(
            """
            SELECT DISTINCT ON (outline_node_id)
                   id, user_id, project_id, book_id, motif_id, motif_version,
                   outline_node_id, role_bindings, annotations, created_at
            FROM motif_application
            WHERE user_id = $1 AND project_id = $2 AND outline_node_id = ANY($3)
            ORDER BY outline_node_id, created_at DESC
            """,
            user_id, project_id, node_ids,
        )
        out: dict[UUID, MotifApplication] = {}
        for r in rows:
            app = MotifApplication.model_validate(_jsonb_loads(dict(r)))
            if app.outline_node_id is not None:
                out[app.outline_node_id] = app
        return out

    async def arc_bindings(
        self, user_id: UUID, project_id: UUID, arc_template_id: UUID,
    ) -> list[dict[str, Any]]:
        """The realized bindings materialized from one arc (D-W10-ARC-CONFORMANCE) →
        rows ``{motif_id, motif_code, annotations, chapter_id, tension, story_order}``,
        ordered by story_order. JOINs ``motif_application`` (the materialize ledger, keyed
        by ``annotations->>'arc_template_id'``) → its scene ``outline_node`` (chapter +
        tension) → ``motif`` (the stable code). Tenant-scoped on BOTH the application AND
        the node (the kinds-bug rule). An archived/cleared binding (motif_id NULL) drops
        out via the INNER motif JOIN — it can't be conformance-checked."""
        rows = await self._pool.fetch(
            """
            SELECT a.motif_id, m.code AS motif_code, a.annotations,
                   o.chapter_id, o.tension, o.story_order
            FROM motif_application a
            JOIN outline_node o ON o.id = a.outline_node_id
            JOIN motif m ON m.id = a.motif_id
            WHERE a.user_id = $1 AND a.project_id = $2
              AND o.user_id = $1 AND o.project_id = $2
              AND a.annotations->>'arc_template_id' = $3
            ORDER BY o.story_order NULLS LAST, o.id
            """,
            user_id, project_id, str(arc_template_id),
        )
        import json
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            ann = d.get("annotations")
            d["annotations"] = json.loads(ann) if isinstance(ann, str) else (ann or {})
            out.append(d)
        return out

    async def latest_completed_by_nodes(
        self, user_id: UUID, project_id: UUID, node_ids: list[UUID],
    ) -> dict[UUID, dict[str, Any]]:
        """The latest COMPLETED generation_job per node → {job_id, critic, has_text}.
        The prose blob is NOT projected (the trace shows status; the editor shows
        prose). Mirrors chapter_scene_drafts' DISTINCT ON + created_at DESC rule.
        M5 isolation: user_id/project_id on BOTH the job AND the joined node."""
        if not node_ids:
            return {}
        rows = await self._pool.fetch(
            """
            SELECT DISTINCT ON (j.outline_node_id)
                   j.outline_node_id AS node_id,
                   j.id              AS job_id,
                   j.critic          AS critic,
                   (j.result->>'text' IS NOT NULL AND j.result->>'text' <> '') AS has_text
            FROM generation_job j
            JOIN outline_node o ON o.id = j.outline_node_id
            WHERE j.user_id = $1 AND j.project_id = $2
              AND o.user_id = $1 AND o.project_id = $2
              AND j.outline_node_id = ANY($3)
              AND j.status = 'completed'
            ORDER BY j.outline_node_id, j.created_at DESC
            """,
            user_id, project_id, node_ids,
        )
        out: dict[UUID, dict[str, Any]] = {}
        for r in rows:
            node_id = r["node_id"]
            critic = r["critic"]
            if isinstance(critic, str):
                import json
                critic = json.loads(critic)
            out[node_id] = {
                "job_id": str(r["job_id"]),
                "critic": critic or {},
                "has_text": bool(r["has_text"]),
            }
        return out


def _jsonb_loads(data: dict[str, Any]) -> dict[str, Any]:
    """asyncpg returns JSONB as str unless a codec is registered — decode the two
    JSONB fields the MotifApplication model reads so model_validate gets dicts."""
    import json
    for f in ("role_bindings", "annotations"):
        v = data.get(f)
        if isinstance(v, str):
            data[f] = json.loads(v)
    return data


async def get_conformance_trace_reader() -> ConformanceTraceReader:
    """W5 — the trace-read helper (the two §4.2 joins). Read-only over W2's
    motif_application + the existing generation_job."""
    return ConformanceTraceReader(get_pool())


def _assemble_conformance(
    *,
    chapter_id: UUID,
    calibrated: bool,
    scenes: list[OutlineNode],
    apps_by_node: dict[UUID, MotifApplication],
    latest_by_node: dict[UUID, dict[str, Any]],
) -> dict[str, Any]:
    """PURE in-memory join → the §4.1 trace shape. No DB. This is the join-
    correctness surface (audit gap4 / F-3 test target).

    Per scene: planned (bound motif/beat/tension/roles), realized (job presence
    only), conformance (the critic.motif_conformance dim, or null when no completed
    job / no dim yet / no bound motif). The dim is echoed verbatim — W5 never
    fabricates a verdict."""
    scene_rows: list[dict[str, Any]] = []
    for s in scenes:
        app = apps_by_node.get(s.id)
        latest = latest_by_node.get(s.id)

        # PLANNED — the bound motif + the specific beat (from annotations, §8 MD-3:
        # the binder writes beat_key into motif_application.annotations; absent →
        # null = motif-level conformance, still useful).
        planned: dict[str, Any] = {
            "motif_id": str(app.motif_id) if (app and app.motif_id) else None,
            "motif_version": app.motif_version if app else None,
            "beat_key": (app.annotations.get("beat_key") if app else None) or None,
            "tension": s.tension,
            "role_bindings": app.role_bindings if app else {},
        }

        # REALIZED — text presence only (never the prose blob in the trace).
        realized: dict[str, Any] = {
            "job_id": latest["job_id"] if latest else None,
            "has_prose": bool(latest["has_text"]) if latest else False,
        }

        # CONFORMANCE — the dim from the latest job's critic, or null. Null when:
        # no completed job, OR the job has no motif_conformance dim yet, OR the
        # scene has no bound motif (nothing planned to conform to).
        conformance: dict[str, Any] | None = None
        if app and app.motif_id and latest:
            dim = (latest.get("critic") or {}).get("motif_conformance")
            if isinstance(dim, dict):
                conformance = dim

        scene_rows.append({
            "outline_node_id": str(s.id),
            "title": s.title,
            "beat_role": s.beat_role,
            "planned": planned,
            "realized": realized,
            "conformance": conformance,
        })

    return {
        "scope": "chapter",
        "chapter_id": str(chapter_id),
        "calibrated": bool(calibrated),
        "scenes": scene_rows,
    }


@router.get("/works/{project_id}/conformance")
async def read_conformance(
    project_id: UUID,
    scope: str = Query("chapter"),
    chapter_id: UUID | None = None,
    arc_template_id: UUID | None = None,
    deep: bool = Query(False),
    model_ref: str | None = Query(None),
    model_source: str | None = Query(None),
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    reader: ConformanceTraceReader = Depends(get_conformance_trace_reader),
    arc_repo: ArcTemplateRepo = Depends(get_arc_template_repo),
    knowledge: KnowledgeClient = Depends(get_knowledge_client_dep),
) -> dict[str, Any]:
    """The motif-conformance trace (§4). `scope=chapter` (default) is the per-scene
    planned│realized│conformance trace. `scope=arc` is the COARSE arc-conformance diff
    (D-W10-ARC-CONFORMANCE, §14.4 altitude 3): the materialized bindings vs the arc
    template across thread-progress / pacing / structural succession. The DEEP
    prose-extract diff (effects→preconditions over written text) stays P4+ —
    `coarse=true`, `causal_verified=false`."""
    from app.config import settings

    work = await works.get(user_id, project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")

    if scope == "arc":
        if arc_template_id is None:
            raise HTTPException(status_code=422, detail={"code": "ARC_TEMPLATE_ID_REQUIRED"})
        arc = await arc_repo.get_visible(user_id, arc_template_id)
        if arc is None:
            # H13 uniform — no existence oracle for a foreign/missing arc.
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
        rows = await reader.arc_bindings(user_id, project_id, arc_template_id)
        # assign a 1-based realized-chapter index: chapters in story_order of first sight.
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
        succ_map = await MotifRepo(get_pool()).successors_by_ids(realized_ids)
        precedes_pairs = {(frm, s["id"]) for frm, lst in succ_map.items() for s in lst}
        report = build_arc_conformance(arc=arc, realized=realized, precedes_pairs=precedes_pairs)
        if deep:
            # DEEP overlay — the realized-from-PROSE diff (motif_beat extractor, cross-service).
            # Only on opt-in (deep=true). When a classify model is supplied, tag the book's
            # events into the arc's thread vocabulary FIRST (D-W10-…-THREAD-TAG) so the beats
            # carry real narrative_thread → thread-progression; without it, pacing-only (plus
            # any pre-existing tags). Degrades to available:false on an outage / empty corpus.
            if model_ref:
                await knowledge.tag_threads(
                    user_id, book_id=work.book_id, threads=(arc.threads or []),
                    model_source=model_source or "user_model", model_ref=model_ref)
            seqs = await knowledge.get_motif_beat_sequences(user_id, book_id=work.book_id)
            report["deep"] = build_deep_report(
                sequences=seqs or [],
                chapter_index_by_id={str(ch): idx for ch, idx in order.items()},
                planned_by_index={pt["chapter_index"]: pt["avg_tension"]
                                  for pt in report["pacing"]["realized"]},
                arc_threads=arc.threads or [],
            )
        return report
    if scope != "chapter":
        raise HTTPException(status_code=422, detail={"code": "UNSUPPORTED_SCOPE", "scope": scope})
    if chapter_id is None:
        raise HTTPException(status_code=422, detail={"code": "CHAPTER_ID_REQUIRED"})

    scenes = await outline.scenes_for_chapter(user_id, project_id, chapter_id)
    node_ids = [s.id for s in scenes]
    apps_by_node = await reader.apps_by_nodes(user_id, project_id, node_ids)
    latest_by_node = await reader.latest_completed_by_nodes(user_id, project_id, node_ids)

    return _assemble_conformance(
        chapter_id=chapter_id,
        calibrated=settings.motif_conformance_calibrated,
        scenes=scenes,
        apps_by_node=apps_by_node,
        latest_by_node=latest_by_node,
    )
