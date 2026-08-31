"""Glossary-build FSM service — the deterministic driver around the engine.

State machine (spec 2026-07-27): draft → planning → plan_ready → [human approves]
→ building → proposing → proposed → (M3: kg_projecting → edges_ready → done).
The LLM never chooses a tool: the driver calls engine steps in order, the
platform makes every write. Items are resumable rows; a failed item SKIPS with
a recorded reason and the run continues (no item can wedge the run).

Durability note (registered debt in the plan): the v1 driver is an in-process
asyncio task — a service restart mid-build leaves the run in `building`; the
authoring-run heartbeat/sweep pattern is the planned follow-up.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID

import asyncpg
from loreweave_llm import no_thinking_fields
from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient
# The QAT thinking-model suppressor — same fields compress/draft use. Private by
# convention but one source of truth beats a drifting copy.
from app.services.glossary_build import engine
from app.services.glossary_build.prompts import BATCH_MAX, NARROW_THRESHOLD, select_fields
from app.llm_budget import max_tokens_for

logger = logging.getLogger("app.services.glossary_build")

DEFAULT_KINDS = ["character", "organization", "event", "terminology",
                 "power_system", "relationship", "location", "item"]

# MODULE-level driver registry — NOT per-instance. `get_glossary_build_service()` is a
# FastAPI dependency, so every request builds a FRESH service: a `self._tasks` dict could
# never be seen by the later /cancel request, and cancel() would flip the row to
# 'cancelled' while the driver kept calling the LLM (spending real money) to the end of
# the worklist. Same reason authoring-runs keeps its registry module-level.
_DRIVER_TASKS: dict[str, asyncio.Task] = {}


class GlossaryBuildError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


# jsonb columns asyncpg hands back as TEXT (no codec registered on this pool) —
# decoded ONCE at the repo boundary so nothing downstream has to guess whether a
# field is a str or a dict. Live-caught by the M4 maiden run: the fake repo in the
# unit tests stored real dicts, so `params.items()` blew up only against Postgres
# (the mock-only-coverage lesson, again).
_JSONB_FIELDS = ("params", "worklist", "edges", "built", "sections", "relations")


def _row(record) -> dict:
    out = dict(record)
    for k in _JSONB_FIELDS:
        v = out.get(k)
        if isinstance(v, str):
            try:
                out[k] = json.loads(v)
            except ValueError:
                pass
    return out


# The statuses `uq_glossary_build_active_book` holds -- one in-flight run per book. `draft`
# is deliberately outside the index (creating a draft is free), so a collision lands on the
# first real transition instead.
_ACTIVE_STATUSES = ("planning", "plan_ready", "building", "proposing",
                    "kg_projecting", "edges_ready")

# What a caller should do NEXT with a run in each of those states. An ACTIVE_RUN refusal that
# names none of these is a dead end, and it was measured as one.
_NEXT_OP_FOR_STATUS = {
    "plan_ready": "approve_plan",
    "edges_ready": "approve_edges",
    "planning": "status",
    "building": "status",
    "proposing": "status",
    "kg_projecting": "status",
}


class Repo:
    """Thin asyncpg repo — every query filters by owner_user_id (+ book scope).

    Returns plain dicts with the jsonb columns already decoded (see `_row`)."""

    def __init__(self, pool) -> None:
        self._pool = pool

    async def create_run(self, *, owner: UUID, book_id: UUID, params: dict) -> dict:
        row = await self._pool.fetchrow(
            """INSERT INTO glossary_build_runs (owner_user_id, book_id, params)
               VALUES ($1, $2, $3::jsonb) RETURNING *""",
            owner, book_id, json.dumps(params),
        )
        return _row(row)

    async def get_run(self, run_id: UUID, owner: UUID) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM glossary_build_runs WHERE run_id=$1 AND owner_user_id=$2",
            run_id, owner,
        )
        return _row(row) if row else None

    async def active_run_for_book(self, book_id: UUID, owner: UUID) -> dict | None:
        """The run holding `uq_glossary_build_active_book`, or None.

        Exists so an ACTIVE_RUN refusal can NAME the run it is refusing for. The statuses
        are the index's own, kept in `_ACTIVE_STATUSES` so this and the refusal cannot
        drift from each other -- a five-of-six mismatch is exactly how a book was stranded
        for two weeks (see the cancel() note below).
        """
        row = await self._pool.fetchrow(
            """SELECT * FROM glossary_build_runs
               WHERE book_id=$1 AND owner_user_id=$2 AND status = ANY($3::text[])
               ORDER BY updated_at DESC LIMIT 1""",
            book_id, owner, list(_ACTIVE_STATUSES),
        )
        return _row(row) if row else None

    async def transition(self, run_id: UUID, owner: UUID, from_status: list[str],
                         to_status: str, **fields: Any) -> dict | None:
        """Optimistic transition — None when the run is not in from_status (409)."""
        sets, args = ["status=$3", "updated_at=now()"], [run_id, owner, to_status]
        for k, v in fields.items():
            args.append(json.dumps(v) if isinstance(v, (dict, list)) else v)
            cast = "::jsonb" if isinstance(v, (dict, list)) else ""
            sets.append(f"{k}=${len(args)}{cast}")
        row = await self._pool.fetchrow(
            f"""UPDATE glossary_build_runs SET {', '.join(sets)}
                WHERE run_id=$1 AND owner_user_id=$2 AND status = ANY(${len(args) + 1}::text[])
                RETURNING *""",
            *args, from_status,
        )
        return _row(row) if row else None

    async def insert_items(self, run: dict, worklist: list[dict]) -> None:
        await self._pool.executemany(
            """INSERT INTO glossary_build_items
               (run_id, owner_user_id, book_id, ordinal, name, kind, depth)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            [(run["run_id"], run["owner_user_id"], run["book_id"], i,
              w["name"], w["kind"], w.get("depth", "standard"))
             for i, w in enumerate(worklist)],
        )

    async def list_runs(self, *, owner: UUID, book_id: UUID, limit: int = 20) -> list[dict]:
        rows = await self._pool.fetch(
            """SELECT * FROM glossary_build_runs
               WHERE owner_user_id=$1 AND book_id=$2
               ORDER BY created_at DESC LIMIT $3""",
            owner, book_id, limit,
        )
        return [_row(r) for r in rows]

    async def list_items(self, run_id: UUID, owner: UUID) -> list[dict]:
        rows = await self._pool.fetch(
            """SELECT * FROM glossary_build_items
               WHERE run_id=$1 AND owner_user_id=$2 ORDER BY ordinal""",
            run_id, owner,
        )
        return [_row(r) for r in rows]

    async def update_item(self, item_id: UUID, owner: UUID, **fields: Any) -> None:
        sets, args = ["updated_at=now()"], [item_id, owner]
        for k, v in fields.items():
            args.append(json.dumps(v) if isinstance(v, (dict, list)) else v)
            cast = "::jsonb" if isinstance(v, (dict, list)) else ""
            sets.append(f"{k}=${len(args)}{cast}")
        await self._pool.execute(
            f"UPDATE glossary_build_items SET {', '.join(sets)} "
            f"WHERE item_id=$1 AND owner_user_id=$2",
            *args,
        )


class GlossaryBuildService:
    def __init__(self, repo: Repo, llm: LLMClient, glossary, knowledge=None) -> None:
        self._repo = repo
        self._llm = llm
        self._glossary = glossary
        self._knowledge = knowledge          # M3 KG phase (None ⇒ KG phase unavailable)

    # ── LLM binding: engine's injected callable → the platform job seam ──────
    def _llm_fn(self, *, user_id: str, model_source: str, model_ref: str):
        async def call(messages: list[dict], *, budget: str,
                       target: int | None = None, language: str | None = None) -> str:
            job = await self._llm.submit_and_wait(
                user_id=user_id, operation="chat",
                model_source=model_source, model_ref=model_ref,
                input={"messages": messages, "response_format": {"type": "text"},
                       "temperature": 0.4,
                       "max_tokens": max_tokens_for(budget, target=target, language=language),
                       **no_thinking_fields()},
                job_meta={"usage_purpose": "glossary_build"},
            )
            if getattr(job, "status", None) != "completed":
                raise LLMError(f"glossary_build LLM job status={getattr(job, 'status', None)}")
            return extract_judge_content(job.result)
        return call

    async def _ontology(self, run: dict) -> dict[str, list[dict]]:
        """The book's REAL per-kind attribute schema, read ONCE per run.

        The background driver holds no user bearer, so mint the short-lived service
        bearer for the run's owner — the same pattern the MCP path uses for
        book-service draft routes. {} on failure: the caller must then SKIP every
        item, never fall back to a guessed schema (that fallback is what produced
        the empty shells)."""
        from app.config import settings
        from app.mcp.service_bearer import mint_service_bearer
        try:
            bearer = mint_service_bearer(UUID(str(run["owner_user_id"])), settings.jwt_secret)
            return await self._glossary.read_book_ontology(bearer, run["book_id"])
        except Exception:  # noqa: BLE001 — schema read is never allowed to crash the run
            logger.warning("glossary_build: ontology read failed for run=%s", run["run_id"],
                           exc_info=True)
            return {}

    def _params(self, run: dict) -> dict:
        p = run.get("params") or {}
        return json.loads(p) if isinstance(p, str) else p

    # ── FSM entry points ─────────────────────────────────────────────────────
    async def create_run(self, *, owner: UUID, book_id: UUID, params: dict) -> dict:
        required = ("model_source", "model_ref", "source_text")
        missing = [k for k in required if not params.get(k)]
        if missing:
            raise GlossaryBuildError(422, "MISSING_PARAMS", f"params missing: {missing}")
        return await self._repo.create_run(owner=owner, book_id=book_id, params=params)

    async def _active_run_refusal(self, *, run_id: UUID, owner: UUID) -> str:
        """Name the run that is blocking, and the op that CONTINUES it.

        \U0001f534 THE DEAD END THIS REPLACES, MEASURED LIVE 2026-08-31 (K=5, batch
        t64-protocol2). On the turn where the author approves the worklist, the model called
        `op=start` again in 5 of 5 runs and got back only

            ACTIVE_RUN: this book already has a build run in progress

        -- true, and no way forward. `op=approve_plan` has been called ZERO times across 89
        recorded sessions and 95 calls, every one of them `start`. This file already knew the
        shape: see cancel()'s note, where the same refusal stranded a book for two weeks.

        THE PLATFORM'S OWN IDIOM, applied here: a refusal that names the id and the exact
        next call, the way the missing-argument repair says \"YOU ALREADY HAVE IT\".

        Degrade-safe: if the blocking run cannot be read the original sentence is returned
        unchanged, because a refusal that fails to build is still a refusal that must be sent.
        """
        base = "this book already has a build run in progress"
        try:
            # The run being REFUSED is a fresh draft; its book is what the index collided on.
            refused = await self._repo.get_run(run_id, owner)
            if not refused or not refused.get("book_id"):
                return base
            active = await self._repo.active_run_for_book(refused["book_id"], owner)
        except Exception:  # noqa: BLE001 -- never let the hint break the refusal
            logger.debug("ACTIVE_RUN hint unavailable", exc_info=True)
            return base
        if not active:
            return base
        status = str(active.get("status") or "")
        nxt = _NEXT_OP_FOR_STATUS.get(status)
        if not nxt:
            return base
        return (
            f"{base}: run_id={active['run_id']} is at status '{status}'. "
            f"Do NOT call op='start' again -- continue that run with "
            f"op='{nxt}' (pass run_id={active['run_id']}), or abandon it with op='cancel'."
        )

    async def plan(self, run_id: UUID, owner: UUID) -> dict:
        """draft → planning → plan_ready. Synchronous (the planner is 1-2 calls)."""
        try:
            run = await self._repo.transition(run_id, owner, ["draft"], "planning")
        except asyncpg.UniqueViolationError as exc:
            # uq_glossary_build_active_book — one in-flight run per book. `draft` is
            # deliberately outside that index (creating a draft is free), so the
            # collision lands HERE, on the first real transition. Map it to a clean
            # 409 instead of letting the raw constraint 500.
            raise GlossaryBuildError(
                409, "ACTIVE_RUN",
                await self._active_run_refusal(run_id=run_id, owner=owner),
            ) from exc
        if run is None:
            raise GlossaryBuildError(409, "BAD_STATE", "run is not in draft")
        p = self._params(run)
        kinds = p.get("kinds") or DEFAULT_KINDS
        existing = await self._existing_names(run, p)
        try:
            worklist = await engine.run_planner(
                self._llm_fn(user_id=str(run["owner_user_id"]),
                             model_source=p["model_source"], model_ref=p["model_ref"]),
                source_text=p["source_text"], kinds=kinds, existing_names=existing,
                lang=p.get("lang", "vi"), max_items=int(p.get("max_items", 30)),
            )
        except LLMError as exc:
            await self._repo.transition(run_id, owner, ["planning"], "failed",
                                        error_message=str(exc))
            raise GlossaryBuildError(502, "PLANNER_FAILED", str(exc)) from exc
        if not worklist:
            run = await self._repo.transition(run_id, owner, ["planning"], "failed",
                                              error_message="planner produced no items")
            raise GlossaryBuildError(422, "EMPTY_PLAN", "planner produced no items")
        await self._repo.transition(run_id, owner, ["planning"], "plan_ready",
                                    worklist=worklist)
        return await self.get(run_id, owner)

    async def approve_plan(self, run_id: UUID, owner: UUID,
                           worklist: list[dict] | None = None) -> dict:
        """[human checkpoint #1] plan_ready → building; spawns the driver."""
        run = await self._repo.get_run(run_id, owner)
        if run is None:
            raise GlossaryBuildError(404, "NOT_FOUND", "run not found")
        wl = worklist if worklist is not None else (
            json.loads(run["worklist"]) if isinstance(run["worklist"], str)
            else run["worklist"])
        wl = [w for w in wl if isinstance(w, dict) and w.get("name") and w.get("kind")]
        if not wl:
            raise GlossaryBuildError(422, "EMPTY_WORKLIST", "nothing approved to build")
        run = await self._repo.transition(run_id, owner, ["plan_ready"], "building",
                                          worklist=wl)
        if run is None:
            raise GlossaryBuildError(409, "BAD_STATE", "run is not in plan_ready")
        await self._repo.insert_items(run, wl)
        _DRIVER_TASKS[str(run_id)] = asyncio.create_task(self._drive(run_id, owner))
        return await self.get(run_id, owner)

    async def get(self, run_id: UUID, owner: UUID) -> dict:
        run = await self._repo.get_run(run_id, owner)
        if run is None:
            raise GlossaryBuildError(404, "NOT_FOUND", "run not found")
        run["items"] = await self._repo.list_items(run_id, owner)
        return run

    async def list_runs(self, *, owner: UUID, book_id: UUID, limit: int = 20) -> list[dict]:
        return await self._repo.list_runs(owner=owner, book_id=book_id, limit=limit)

    # ── KG phase (M3) ────────────────────────────────────────────────────────
    async def project_kg(self, run_id: UUID, owner: UUID, bearer: str = "") -> dict:
        """proposed → kg_projecting → edges_ready.

        Deterministic, no LLM: ensure the book's knowledge project, project the
        proposed entities into the graph as nodes, then resolve every NAME-based
        relation the executor produced into a concrete {source_id, target_id}
        edge proposal. Unresolvable names are KEPT with `unresolved: true` so the
        human sees what was dropped rather than silently losing it."""
        if self._knowledge is None:
            raise GlossaryBuildError(503, "KG_UNAVAILABLE", "knowledge client not configured")
        run = await self._repo.transition(run_id, owner, ["proposed"], "kg_projecting")
        if run is None:
            raise GlossaryBuildError(409, "BAD_STATE", "run is not in proposed")
        try:
            items = await self._repo.list_items(run_id, owner)
            proposed = [i for i in items if i["status"] == "proposed" and i.get("proposed_entity_id")]
            project = await self._knowledge.create_project(
                run["book_id"], f"{run['book_id']} — glossary build", bearer)
            project_id = (project or {}).get("project_id")
            if not project_id:
                raise GlossaryBuildError(502, "PROJECT_FAILED", "could not resolve a knowledge project")
            projection = await self._knowledge.project_entities_from_glossary(
                bearer, project_id=UUID(str(project_id)),
                entity_ids=[str(i["proposed_entity_id"]) for i in proposed],
            )
            # No-silent-seam: if we had entities to project and the graph took
            # NONE of them, say so with the counts rather than producing edges
            # that would each fail at write time.
            if proposed and projection is not None and not (
                projection.get("created", 0) or projection.get("existing", 0)
            ):
                raise GlossaryBuildError(
                    502, "NOTHING_PROJECTED",
                    f"the graph accepted none of the {len(proposed)} proposed entities "
                    f"({projection}) — approve them in the review inbox first",
                )
            # NAME → GRAPH NODE ID. The one resolution point (the executor only
            # ever emitted names, so the model never touches an id).
            #
            # Two things live-caught in the M4 maiden run:
            #  1. a relation must carry the KG node id (a content hash), NOT the
            #     glossary entity_id — the glossary id 409s "entity not found";
            #  2. the index must cover the WHOLE project graph, not just this
            #     run's items, or every relation pointing at previously-built
            #     lore (Lâm Uyên, Lâm gia…) reads as unresolved. That is the
            #     normal incremental case, not the exception.
            graph = await self._knowledge.list_project_entities(
                bearer, project_id=UUID(str(project_id)))
            by_name = {
                str(g.get("name") or "").casefold(): g.get("id")
                for g in graph if g.get("name") and g.get("id")
            }
            # A just-projected entity may lag the list read; fall back to its
            # glossary anchor so this run's own items always resolve.
            by_gid = {
                str(g.get("glossary_entity_id")): g.get("id")
                for g in graph if g.get("glossary_entity_id") and g.get("id")
            }
            edges: list[dict] = []
            for i in proposed:
                src = by_name.get(i["name"].casefold()) or by_gid.get(str(i["proposed_entity_id"]))
                for r in (i.get("relations") or []):
                    target = str(r.get("target_name") or "").strip()
                    tid = by_name.get(target.casefold())
                    edges.append({
                        "source_name": i["name"], "source_id": src,
                        "target_name": target, "target_id": tid,
                        "type": r.get("type"), "note": r.get("note") or "",
                        "unresolved": tid is None or src is None,
                    })
            # Make the built lore RETRIEVABLE, not just present. Projecting entities
            # above puts them in the graph; the packer's lore lens searches PASSAGES,
            # and `source_type='glossary'` had no producer — so a glossary built before
            # chapter 1 could never be retrieved from its own canon. Best-effort, and
            # the outcome tally rides on the run: a project with no embedding model
            # gets `{"no_embedding_model": N}` and the wizard TELLS the author, instead
            # of a build that silently indexed nothing.
            lore_index = await self._knowledge.index_glossary_passages(
                project_id=UUID(str(project_id)))
            await self._repo.transition(
                run_id, owner, ["kg_projecting"], "edges_ready",
                edges=edges,
                params={**self._params(run), "project_id": str(project_id),
                        "kg_projection": projection or {},
                        "lore_index": lore_index or {"error": "unavailable"}},
            )
            # Return the FULL run (with items): project_kg used to answer the bare
            # transition row, so the wizard's "N entries filed" counter read 0 after
            # this step — a real regression caught by driving the panel as an author.
            return await self.get(run_id, owner)
        except GlossaryBuildError:
            await self._repo.transition(run_id, owner, ["kg_projecting"], "failed",
                                        error_message="kg projection failed")
            raise
        except Exception as exc:  # noqa: BLE001 — fail LOUD on the row
            await self._repo.transition(run_id, owner, ["kg_projecting"], "failed",
                                        error_message=str(exc))
            raise GlossaryBuildError(502, "KG_FAILED", str(exc)) from exc

    async def approve_edges(self, run_id: UUID, owner: UUID, bearer: str = "",
                            edges: list[dict] | None = None) -> dict:
        """[human checkpoint #3] edges_ready → done. Writes the approved,
        RESOLVED edges as user-authored relations. A partial apply is REPORTED
        (applied/failed counts on the run) — never rounded up to success."""
        if self._knowledge is None:
            raise GlossaryBuildError(503, "KG_UNAVAILABLE", "knowledge client not configured")
        run = await self._repo.get_run(run_id, owner)
        if run is None:
            raise GlossaryBuildError(404, "NOT_FOUND", "run not found")
        stored = run.get("edges") or []
        stored = json.loads(stored) if isinstance(stored, str) else stored
        approved = edges if edges is not None else stored
        applied, failed = 0, 0
        for e in approved:
            if e.get("unresolved") or not e.get("source_id") or not e.get("target_id"):
                failed += 1
                continue
            rel = await self._knowledge.create_relation(
                bearer, subject_id=e["source_id"], predicate=str(e.get("type") or "related_to"),
                object_id=e["target_id"])
            if rel is None:
                failed += 1
            else:
                applied += 1
        out = await self._repo.transition(
            run_id, owner, ["edges_ready"], "done",
            params={**self._params(run), "edges_applied": applied, "edges_failed": failed})
        if out is None:
            raise GlossaryBuildError(409, "BAD_STATE", "run is not in edges_ready")
        return await self.get(run_id, owner)

    async def cancel(self, run_id: UUID, owner: UUID) -> dict:
        task = _DRIVER_TASKS.pop(str(run_id), None)
        if task is not None:
            task.cancel()
        # Every state the active-run index HOLDS must be cancellable, or a book can be
        # stranded. Measured 2026-08-03 on the Mị Đế book: a run sat at `edges_ready` since
        # 27 July — `uq_glossary_build_active_book` covers
        # (planning, plan_ready, building, proposing, kg_projecting, edges_ready) while this
        # list covered five of the six, so the wizard refused to start a new run with
        # ACTIVE_RUN and cancel refused with BAD_STATE. No way forward and no way out, from
        # the UI or the API.
        #
        # `edges_ready` is a HUMAN checkpoint (CP3 — approve relationships). Abandoning a
        # review is an ordinary thing to do, and a checkpoint that cannot be abandoned is a
        # trap rather than a gate. `kg_projecting` is in-flight work the driver owns, and the
        # driver task is cancelled two lines above — the same treatment `building` and
        # `proposing` already get.
        run = await self._repo.transition(
            run_id, owner,
            ["draft", "planning", "plan_ready", "building", "proposing",
             "kg_projecting", "edges_ready"], "cancelled")
        if run is None:
            raise GlossaryBuildError(409, "BAD_STATE", "run is not cancellable")
        return await self.get(run_id, owner)

    # ── the driver ───────────────────────────────────────────────────────────
    async def _drive(self, run_id: UUID, owner: UUID) -> None:
        """building → (each item built|skipped) → proposing → proposed.
        Any unexpected error fails the RUN loudly — never a silent stall."""
        try:
            run = await self._repo.get_run(run_id, owner)
            if run is None or run["status"] != "building":
                return
            p = self._params(run)
            kinds = p.get("kinds") or DEFAULT_KINDS
            llm = self._llm_fn(user_id=str(run["owner_user_id"]),
                               model_source=p["model_source"], model_ref=p["model_ref"])
            ontology = await self._ontology(run)
            pending = [i for i in await self._repo.list_items(run_id, owner)
                       if i["status"] == "pending"]
            # BATCH pass (measured 3x cheaper): only `standard` items, grouped by
            # kind, only for kinds whose schema is already narrow — and NEVER mixing
            # kinds in a call (that is the E2 collapse). Anything the batch does not
            # return simply falls through to the per-item loop below.
            batched: dict[str, dict] = {}
            by_kind: dict[str, list[dict]] = {}
            for i in pending:
                if i["depth"] == "standard" and ontology.get(i["kind"]):
                    by_kind.setdefault(i["kind"], []).append(i)
            for kind, group in by_kind.items():
                # Batch eligibility is decided on the kind's FULL schema width, never
                # on the post-slice width: a wide kind narrowed to 4 core fields is
                # still a wide kind, and the POC only validated batching for schemas
                # that are genuinely small (terminology-shaped).
                if len(ontology[kind]) > NARROW_THRESHOLD or len(group) < 2:
                    continue
                fields = select_fields(ontology[kind], deep=False)
                types = {str(d.get("code")): str(d.get("field_type") or "text")
                         for d in ontology[kind]}
                for start in range(0, len(group), BATCH_MAX):
                    chunk = group[start:start + BATCH_MAX]
                    try:
                        got = await engine.build_batch(
                            llm, source_text=p["source_text"],
                            names=[c["name"] for c in chunk], kind=kind,
                            fields=fields, lang=p.get("lang", "vi"), types=types)
                    except LLMError:
                        got = {}          # per-item loop retries these individually
                    batched.update(got)

            for item in pending:
                if item["status"] != "pending":
                    continue  # resume-safe: already handled
                # Re-read the RUN before each item: a /cancel from another request
                # (a DIFFERENT service instance) can only signal us through the row.
                # Without this the driver kept building — and paying — after cancel.
                live = await self._repo.get_run(run_id, owner)
                if live is None or live["status"] != "building":
                    logger.info("glossary_build driver: run=%s left 'building' (%s) — stopping",
                                run_id, (live or {}).get("status"))
                    return
                await self._repo.update_item(item["item_id"], owner, status="building")
                defs = ontology.get(item["kind"]) or []
                if not defs:
                    # No schema ⇒ SKIP. Guessing the fields is what wrote rows with
                    # no name and no attributes on the first live run.
                    await self._repo.update_item(
                        item["item_id"], owner, status="skipped",
                        skip_reason=f"no attribute schema for kind '{item['kind']}'")
                    continue
                fields = select_fields(defs, deep=item["depth"] == "deep")
                types = {str(d.get("code")): str(d.get("field_type") or "text") for d in defs}
                sections: list[dict] = []
                entity = batched.get(item["name"])
                try:
                    if entity is not None:
                        pass                      # already built in the batch pass
                    elif item["depth"] == "deep":
                        entity, sections = await engine.build_deep(
                            llm, source_text=p["source_text"], name=item["name"],
                            kind=item["kind"], fields=fields, lang=p.get("lang", "vi"),
                            types=types)
                    else:
                        entity = await engine.build_standard(
                            llm, source_text=p["source_text"], name=item["name"],
                            kind=item["kind"], fields=fields, lang=p.get("lang", "vi"),
                            types=types)
                except LLMError as exc:
                    await self._repo.update_item(item["item_id"], owner, status="skipped",
                                                 skip_reason=f"llm: {exc}")
                    continue
                if entity is None:
                    await self._repo.update_item(
                        item["item_id"], owner, status="skipped",
                        skip_reason="the model returned nothing that fits this kind's schema")
                    continue
                await self._repo.update_item(
                    item["item_id"], owner, status="built", built=entity,
                    sections=sections, relations=entity.get("relations") or [])

            await self._propose(run_id, owner)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — fail LOUD on the row, never stall
            logger.exception("glossary_build driver failed run=%s", run_id)
            await self._repo.transition(
                run_id, owner, ["building", "proposing"], "failed", error_message=str(exc))
        finally:
            _DRIVER_TASKS.pop(str(run_id), None)

    async def _propose(self, run_id: UUID, owner: UUID) -> None:
        """built items → glossary drafts (bulk, ONE platform call), then proposed."""
        run = await self._repo.transition(run_id, owner, ["building"], "proposing")
        if run is None:
            return
        p = self._params(run)
        items = [i for i in await self._repo.list_items(run_id, owner)
                 if i["status"] == "built"]
        if not items:
            await self._repo.transition(run_id, owner, ["proposing"], "failed",
                                        error_message="no items built")
            return
        payload = []
        for i in items:
            built = json.loads(i["built"]) if isinstance(i["built"], str) else i["built"]
            payload.append({"kind_code": i["kind"], "name": i["name"],
                            "attributes": built.get("attributes") or {}})
        created = await self._glossary.seed_entities_or_raise(
            run["book_id"], source_language=p.get("lang", "vi"), entities=payload)
        by_name = {str(c.get("name", "")).casefold(): c.get("entity_id") for c in created}
        for i in items:
            eid = by_name.get(i["name"].casefold())
            if eid:
                await self._repo.update_item(
                    i["item_id"], owner, status="proposed", proposed_entity_id=UUID(eid))
            else:
                # The glossary SKIPS a name that already exists (or was rejected before).
                # Reporting that as `proposed` was a FALSE SUCCESS: the wizard counted it
                # as filed and the KG phase silently dropped it (no entity id to project).
                await self._repo.update_item(
                    i["item_id"], owner, status="skipped",
                    skip_reason="the glossary already has an entry with this name")
        await self._repo.transition(run_id, owner, ["proposing"], "proposed")

    async def _existing_names(self, run: dict, p: dict) -> list[str]:
        """Names already in the glossary, for planner dedup — best-effort
        (semantic select over the source text; a full-list route is registered debt)."""
        try:
            ents = await self._glossary.select_for_context(
                run["book_id"], run["owner_user_id"],
                p["source_text"][:1000], max_entities=50)
            return [e.get("cached_name") or e.get("name") or "" for e in ents]
        except Exception:  # noqa: BLE001 — dedup is best-effort, never blocks planning
            return []
