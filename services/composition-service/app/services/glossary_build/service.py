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

from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient
# The QAT thinking-model suppressor — same fields compress/draft use. Private by
# convention but one source of truth beats a drifting copy.
from app.engine.compress import _NO_THINK
from app.services.glossary_build import engine

logger = logging.getLogger("app.services.glossary_build")

DEFAULT_KINDS = ["character", "organization", "event", "terminology",
                 "power_system", "relationship", "location", "item"]


class GlossaryBuildError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class Repo:
    """Thin asyncpg repo — every query filters by owner_user_id (+ book scope)."""

    def __init__(self, pool) -> None:
        self._pool = pool

    async def create_run(self, *, owner: UUID, book_id: UUID, params: dict) -> dict:
        row = await self._pool.fetchrow(
            """INSERT INTO glossary_build_runs (owner_user_id, book_id, params)
               VALUES ($1, $2, $3::jsonb) RETURNING *""",
            owner, book_id, json.dumps(params),
        )
        return dict(row)

    async def get_run(self, run_id: UUID, owner: UUID) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM glossary_build_runs WHERE run_id=$1 AND owner_user_id=$2",
            run_id, owner,
        )
        return dict(row) if row else None

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
        return dict(row) if row else None

    async def insert_items(self, run: dict, worklist: list[dict]) -> None:
        await self._pool.executemany(
            """INSERT INTO glossary_build_items
               (run_id, owner_user_id, book_id, ordinal, name, kind, depth)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            [(run["run_id"], run["owner_user_id"], run["book_id"], i,
              w["name"], w["kind"], w.get("depth", "standard"))
             for i, w in enumerate(worklist)],
        )

    async def list_items(self, run_id: UUID, owner: UUID) -> list[dict]:
        rows = await self._pool.fetch(
            """SELECT * FROM glossary_build_items
               WHERE run_id=$1 AND owner_user_id=$2 ORDER BY ordinal""",
            run_id, owner,
        )
        return [dict(r) for r in rows]

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
    def __init__(self, repo: Repo, llm: LLMClient, glossary) -> None:
        self._repo = repo
        self._llm = llm
        self._glossary = glossary
        self._tasks: dict[str, asyncio.Task] = {}

    # ── LLM binding: engine's injected callable → the platform job seam ──────
    def _llm_fn(self, *, user_id: str, model_source: str, model_ref: str):
        async def call(messages: list[dict], max_tokens: int) -> str:
            job = await self._llm.submit_and_wait(
                user_id=user_id, operation="chat",
                model_source=model_source, model_ref=model_ref,
                input={"messages": messages, "response_format": {"type": "text"},
                       "temperature": 0.4, "max_tokens": max_tokens, **_NO_THINK},
                job_meta={"usage_purpose": "glossary_build"},
            )
            if getattr(job, "status", None) != "completed":
                raise LLMError(f"glossary_build LLM job status={getattr(job, 'status', None)}")
            return extract_judge_content(job.result)
        return call

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

    async def plan(self, run_id: UUID, owner: UUID) -> dict:
        """draft → planning → plan_ready. Synchronous (the planner is 1-2 calls)."""
        run = await self._repo.transition(run_id, owner, ["draft"], "planning")
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
        out = await self._repo.transition(run_id, owner, ["planning"], "plan_ready",
                                          worklist=worklist)
        return out or run

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
        task = asyncio.create_task(self._drive(run_id, owner))
        self._tasks[str(run_id)] = task
        return run

    async def get(self, run_id: UUID, owner: UUID) -> dict:
        run = await self._repo.get_run(run_id, owner)
        if run is None:
            raise GlossaryBuildError(404, "NOT_FOUND", "run not found")
        run["items"] = await self._repo.list_items(run_id, owner)
        return run

    async def cancel(self, run_id: UUID, owner: UUID) -> dict:
        task = self._tasks.pop(str(run_id), None)
        if task is not None:
            task.cancel()
        run = await self._repo.transition(
            run_id, owner,
            ["draft", "planning", "plan_ready", "building", "proposing"], "cancelled")
        if run is None:
            raise GlossaryBuildError(409, "BAD_STATE", "run is not cancellable")
        return run

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
            for item in await self._repo.list_items(run_id, owner):
                if item["status"] != "pending":
                    continue  # resume-safe: already handled
                await self._repo.update_item(item["item_id"], owner, status="building")
                try:
                    if item["depth"] == "deep":
                        entity, sections = await engine.build_deep(
                            llm, source_text=p["source_text"], name=item["name"],
                            kind=item["kind"], kinds=kinds, lang=p.get("lang", "vi"))
                    else:
                        entity = await engine.build_standard(
                            llm, source_text=p["source_text"], name=item["name"],
                            kind=item["kind"], kinds=kinds, lang=p.get("lang", "vi"))
                        sections = []
                except LLMError as exc:
                    await self._repo.update_item(item["item_id"], owner, status="skipped",
                                                 skip_reason=f"llm: {exc}")
                    continue
                if entity is None:
                    await self._repo.update_item(item["item_id"], owner, status="skipped",
                                                 skip_reason="invalid model output after retry")
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
            self._tasks.pop(str(run_id), None)

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
            await self._repo.update_item(
                i["item_id"], owner, status="proposed",
                **({"proposed_entity_id": UUID(eid)} if eid else {}))
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
