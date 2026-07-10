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
generation_job per node (the same rule stitch/publish use).

`scope=arc` (BA4 retarget) is `diff(structure_node, prose)` — the durable SPEC arc
(`arc_id` = `structure_node.id`) vs the realized `motif_application` bindings keyed by
`structure_node_id`. `scope=arc_template_drift` is the split-out, optional comparison
against the `arc_template` the arc was authored from (via the node's provenance). Both
share the coarse builder + optional deep prose overlay (D-W10-ARC-CONFORMANCE).

TENANCY: access is decided BEFORE these reads, at the gate (E0 grant on the row's
book_id — 25 PM-8). The two reads filter project_id on BOTH the application/job AND
the joined node (defense-in-depth — the kinds-bug lesson). A node-id-only query
would be a cross-tenant read.

OWNERSHIP: W5 owns this file. The two reads here are W5-local (the
`motif_application` table is W2/F0-owned but W5 only READS it; the binder writes
`motif_id`/`beat_key`-in-annotations). If W1/W2 later add a `MotifApplicationRepo`,
these reads can move there — but W5 does not edit their files to add them.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.models import MotifApplication, OutlineNode
from app.db.pool import get_pool
from app.db.repositories.arc_template_repo import ArcTemplateRepo
from app.db.repositories.motif_repo import MotifRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.structure import StructureRepo
from app.db.repositories.works import WorksRepo
from app.clients.knowledge_client import KnowledgeClient
from app.deps import (get_arc_template_repo, get_grant_client_dep,
                      get_knowledge_client_dep, get_outline_repo, get_works_repo)
from app.engine.arc_conformance_orchestrate import compute_arc_report
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.middleware.jwt_auth import get_current_user
from app.packer.pack import OwnershipError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/composition")


async def _persist_conformance_best_effort(
    *, book_id: UUID, arc: Any, report: dict[str, Any], deep: bool,
) -> None:
    """IX-8 — snapshot the durable, input-pinned report after an arc-scope compute
    (the sync GET's twin of the Tier-W worker's persist). BEST-EFFORT: the report is
    the primary product, so a snapshot-write failure (book-service markers down, DB
    hiccup) is logged, never a 500 (OQ-1 philosophy — freshness of a derived artifact
    must not hold the read hostage). The book-markers read inside uses the INTERNAL
    token, safe because the E0 VIEW gate already authorized this book."""
    from app.clients.book_client import get_book_client
    from app.engine.arc_conformance_orchestrate import persist_conformance_state

    try:
        await persist_conformance_state(
            pool=get_pool(), book_client=get_book_client(),
            book_id=book_id, arc=arc, report=report, deep=deep)
    except Exception:  # noqa: BLE001 — best-effort snapshot (IX-8); logged, never fatal
        logger.warning(
            "arc_conformance_state persist failed for arc %s",
            getattr(arc, "id", "?"), exc_info=True)


class ConformanceTraceReader:
    """W5-owned read helper for the two trace joins (§4.2). Both queries are
    project scoped on BOTH the row AND the joined node (defense-in-depth)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def apps_by_nodes(
        self, project_id: UUID, node_ids: list[UUID],
    ) -> dict[UUID, MotifApplication]:
        """The bound motif_application per scene node (most-recent per node). READ-
        only; W2 is the sole writer. Returns a node_id → MotifApplication map."""
        if not node_ids:
            return {}
        # DISTINCT ON the node → the most-recent binding per node (a re-bind supersedes).
        rows = await self._pool.fetch(
            """
            SELECT DISTINCT ON (outline_node_id)
                   id, created_by, project_id, book_id, motif_id, motif_version,
                   outline_node_id, role_bindings, annotations, created_at
            FROM motif_application
            WHERE project_id = $1 AND outline_node_id = ANY($2)
            ORDER BY outline_node_id, created_at DESC
            """,
            project_id, node_ids,
        )
        out: dict[UUID, MotifApplication] = {}
        for r in rows:
            app = MotifApplication.model_validate(_jsonb_loads(dict(r)))
            if app.outline_node_id is not None:
                out[app.outline_node_id] = app
        return out

    async def arc_bindings(
        self, project_id: UUID, arc_template_id: UUID,
    ) -> list[dict[str, Any]]:
        """The realized bindings materialized from one arc (D-W10-ARC-CONFORMANCE) →
        rows ``{motif_id, motif_code, annotations, chapter_id, tension, story_order}``,
        ordered by story_order. JOINs ``motif_application`` (the materialize ledger, keyed
        by ``annotations->>'arc_template_id'``) → its scene ``outline_node`` (chapter +
        tension) → ``motif`` (the stable code). Project-scoped on BOTH the application AND
        the node (the kinds-bug rule). An archived/cleared binding (motif_id NULL) drops
        out via the INNER motif JOIN — it can't be conformance-checked."""
        rows = await self._pool.fetch(
            """
            SELECT a.motif_id, m.code AS motif_code, a.annotations,
                   o.chapter_id, o.tension, o.story_order
            FROM motif_application a
            JOIN outline_node o ON o.id = a.outline_node_id
            JOIN motif m ON m.id = a.motif_id
            WHERE a.project_id = $1
              AND o.project_id = $1
              AND a.annotations->>'arc_template_id' = $2
            ORDER BY o.story_order NULLS LAST, o.id
            """,
            project_id, str(arc_template_id),
        )
        import json
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            ann = d.get("annotations")
            d["annotations"] = json.loads(ann) if isinstance(ann, str) else (ann or {})
            out.append(d)
        return out

    async def arc_bindings_by_structure(
        self, project_id: UUID, structure_node_id: UUID,
    ) -> list[dict[str, Any]]:
        """BA4 — the realized bindings for a durable SPEC arc (``structure_node.id``), keyed on
        the ``motif_application.structure_node_id`` column Deploy 1 added (23 M1.3). This
        REPLACES the ``annotations->>'arc_template_id'`` provenance for the primary arc axis:
        the spec is what the prose is measured against ("did the prose realize *my plan*"), not
        the template it came from. Rows ``{motif_id, motif_code, annotations, chapter_id,
        tension, story_order}`` ordered by story_order — the SAME shape ``arc_bindings`` returns,
        so ``compute_arc_report`` is provenance-agnostic downstream. JOINs the scene
        ``outline_node`` (chapter + tension) → ``motif`` (the stable code). PM-11 double-filter:
        ``project_id`` on BOTH the application AND the joined node (the kinds-bug rule) — a
        node-id-only query would be a cross-tenant read. An archived/cleared binding (motif_id
        NULL) drops out via the INNER motif JOIN — it can't be conformance-checked."""
        rows = await self._pool.fetch(
            """
            SELECT a.motif_id, m.code AS motif_code, a.annotations,
                   o.chapter_id, o.tension, o.story_order
            FROM motif_application a
            JOIN outline_node o ON o.id = a.outline_node_id
            JOIN motif m ON m.id = a.motif_id
            WHERE a.project_id = $1
              AND o.project_id = $1
              AND a.structure_node_id = $2
            ORDER BY o.story_order NULLS LAST, o.id
            """,
            project_id, structure_node_id,
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
        self, project_id: UUID, node_ids: list[UUID],
    ) -> dict[UUID, dict[str, Any]]:
        """The latest COMPLETED generation_job per node → {job_id, critic, has_text}.
        The prose blob is NOT projected (the trace shows status; the editor shows
        prose). Mirrors chapter_scene_drafts' DISTINCT ON + created_at DESC rule.
        Isolation: project_id on BOTH the job AND the joined node."""
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
            WHERE j.project_id = $1
              AND o.project_id = $1
              AND j.outline_node_id = ANY($2)
              AND j.status = 'completed'
            ORDER BY j.outline_node_id, j.created_at DESC
            """,
            project_id, node_ids,
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


async def get_structure_repo() -> StructureRepo:
    """BA4 — the durable-spec repo (23 A3). Local dep (not app.deps) so the arc-scope
    conformance path resolves the ``structure_node`` (book gate + tracks) without
    coupling to the wider deps wiring; the route test overrides this."""
    return StructureRepo(get_pool())


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


async def _resolve_book_arc(
    structure_repo: StructureRepo, arc_id: UUID, book_id: UUID,
) -> Any:
    """Resolve a durable-spec arc (``structure_node``) INTO the gated book. Returns the
    node, or raises 422 (missing id) / 404 (foreign or absent — H13 uniform, no existence
    oracle for a node in another book). The E0 book gate already ran on ``book_id``; a
    ``structure_node`` is per-book so its own ``book_id`` MUST match (defense-in-depth)."""
    if arc_id is None:
        raise HTTPException(status_code=422, detail={"code": "ARC_ID_REQUIRED"})
    node = await structure_repo.get(arc_id)
    if node is None or node.book_id != book_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    return node


@router.get("/works/{project_id}/conformance")
async def read_conformance(
    project_id: UUID,
    scope: str = Query("chapter"),
    chapter_id: UUID | None = None,
    arc_id: UUID | None = None,            # BA4: structure_node.id (replaces arc_template_id)
    deep: bool = Query(False),
    model_ref: str | None = Query(None),
    model_source: str | None = Query(None),
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    reader: ConformanceTraceReader = Depends(get_conformance_trace_reader),
    arc_repo: ArcTemplateRepo = Depends(get_arc_template_repo),
    structure_repo: StructureRepo = Depends(get_structure_repo),
    knowledge: KnowledgeClient = Depends(get_knowledge_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """The motif-conformance trace (§4). `scope=chapter` (default) is the per-scene
    planned│realized│conformance trace.

    `scope=arc` (BA4 RETARGET) is `diff(structure_node, prose)` — the durable SPEC arc
    (`arc_id` = `structure_node.id`, NOT `arc_template_id`) vs the realized `motif_application`
    bindings keyed by `structure_node_id`: "did the prose realize *my plan*". `scope=arc_template_drift`
    is the split-out, optional question — the SAME coarse diff but against the `arc_template` the
    arc was authored from (resolved via the node's `arc_template_id` provenance). Both accept
    `deep` for the realized-from-PROSE overlay; `coarse=true`, `causal_verified=false` otherwise."""
    from app.config import settings

    work = await works.get(project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    # E0 book gate (25 PM-8): the trace is a READ of an advisory signal → VIEW.
    try:
        await authorize_book(grant, work.book_id, user_id, GrantLevel.VIEW)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="work not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")

    # Shared with the Tier-W run_conformance_run worker (D-W10-ARC-CONFORMANCE-DEEP-JOB): the
    # synchronous deep+model_ref tagging storm stays here for tests/small books; the FE uses the
    # job (composition_conformance_run) for real books — see the deep-job plan.
    if scope == "arc":
        # BA4 — the durable-spec arc, measured against the PROSE (via structure_node_id).
        node = await _resolve_book_arc(structure_repo, arc_id, work.book_id)
        report = await compute_arc_report(
            reader=reader, mrepo=MotifRepo(get_pool()), knowledge=knowledge,
            user_id=user_id, project_id=project_id, book_id=work.book_id, arc=node,
            by_structure=True, deep=deep, model_ref=model_ref, model_source=model_source)
        # IX-8 — durable, input-pinned snapshot (ONE persist seam shared with the
        # Tier-W worker; the template-drift scope below never persists — it is not a
        # structure_node arc).
        await _persist_conformance_best_effort(
            book_id=work.book_id, arc=node, report=report, deep=deep)
        return report
    if scope == "arc_template_drift":
        # BA4 — the SPLIT-OUT optional question: the spec vs the template it came from. Resolve
        # the node's arc_template_id provenance, then run the OLD comparison (annotation-keyed).
        node = await _resolve_book_arc(structure_repo, arc_id, work.book_id)
        if node.arc_template_id is None:
            # BA13 — an arc authored from conversation has no template to drift from.
            raise HTTPException(status_code=422, detail={"code": "NO_TEMPLATE_PROVENANCE"})
        arc = await arc_repo.get_visible(user_id, node.arc_template_id)
        if arc is None:
            # H13 uniform — no existence oracle for a foreign/missing/deleted template.
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
        return await compute_arc_report(
            reader=reader, mrepo=MotifRepo(get_pool()), knowledge=knowledge,
            user_id=user_id, project_id=project_id, book_id=work.book_id, arc=arc,
            by_structure=False, deep=deep, model_ref=model_ref, model_source=model_source)
    if scope != "chapter":
        raise HTTPException(status_code=422, detail={"code": "UNSUPPORTED_SCOPE", "scope": scope})
    if chapter_id is None:
        raise HTTPException(status_code=422, detail={"code": "CHAPTER_ID_REQUIRED"})

    scenes = await outline.scenes_for_chapter(project_id, chapter_id)
    node_ids = [s.id for s in scenes]
    apps_by_node = await reader.apps_by_nodes(project_id, node_ids)
    latest_by_node = await reader.latest_completed_by_nodes(project_id, node_ids)

    return _assemble_conformance(
        chapter_id=chapter_id,
        calibrated=settings.motif_conformance_calibrated,
        scenes=scenes,
        apps_by_node=apps_by_node,
        latest_by_node=latest_by_node,
    )


@router.get("/books/{book_id}/conformance/status")
async def read_conformance_status(
    book_id: UUID,
    arc_id: UUID | None = Query(None),
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """IX-14 — the conformance staleness read contract, defined ONCE here. VIEW-gated
    (E0 grant on `book_id`, BPS-8). Cheap: no LLM, no re-extract — `arc_conformance_
    state` + one canon-markers batch + in-DB fingerprint scans. Returns per-arc
    `{dirty, dirty_reasons, stale_chapters, summary, computed_at, deep}` + an
    `index.stale_chapter_count` rollup; pass `arc_id` to scope to one arc. 24's Plan
    Hub consumes this route directly (its read surface #7); 22's scene-inspector reads
    the same response (a scene's dirty chip = its arc's `dirty ∧ chapter ∈
    stale_chapters`). To RE-RUN conformance use the existing
    `composition_conformance_run` Tier-W flow — on completion the snapshot updates and
    the badge clears by predicate, no cache to invalidate."""
    from app.clients.book_client import get_book_client
    from app.engine.arc_conformance_orchestrate import compute_conformance_status

    # E0 book gate (BPS-8): the staleness read is a VIEW of an advisory signal. H13
    # uniform — a foreign/missing book is 404, a viewer without VIEW is 403.
    try:
        await authorize_book(grant, book_id, user_id, GrantLevel.VIEW)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="book not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")

    return await compute_conformance_status(
        pool=get_pool(), book_client=get_book_client(), book_id=book_id, arc_id=arc_id)
