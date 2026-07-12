"""PlanForge HTTP service layer (M3).

Orchestrates ingest→propose→validate→compile against plan_run/plan_artifact
persistence and generation_job async worker ops.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID

from app.clients.llm_client import LLMClient
from app.config import settings
from app.db.pool import get_pool
from app.services.plan_link_service import LinkError, PlanLinkService
from app.services.plan_pass_service import derive_view
from app.db.models import CompositionWork, GenerationJob, PlanRun
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.db.repositories.plan_runs import PlanRunsRepo
from app.db.repositories.works import WorksRepo
from app.engine.plan_forge.compile import compile_artifacts, mock_pipeline_result
from app.engine.plan_forge.coverage import build_section_map_from_text, load_coverage_context
from app.engine.plan_forge.decompose import build_graph
from app.engine.plan_forge.elaborate import consistency_audit
from app.engine.plan_forge.eval_fidelity import evaluate_spec_fidelity, load_fidelity_config
from app.engine.plan_forge.ingest import ingest_markdown
from app.engine.plan_forge.interpret import interpret_feedback, interpret_rules
from app.engine.plan_forge.llm import ProviderPlanForgeLLM
from app.engine.plan_forge.propose import propose_spec
from app.engine.plan_forge.self_check import run_self_check, run_self_check_on_document
from app.engine.plan_forge.validate import _deep_merge, run_rules
from app.worker.events import enqueue_job
from app.worker.operations import run_plan_forge_propose, run_plan_forge_refine

logger = logging.getLogger(__name__)

# 27 PF-19 — the POC fixture is REGRESSION-HARNESS-ONLY from here on (09 §8b). No production path
# in this service may read `story-plan-v1.md` / `.fidelity.yaml`: coverage, gaps and fidelity are
# computed against the RUN'S OWN document + rubric, or not at all. A constant pointing at the
# fixture is how the last three call sites found it, so it is gone rather than merely unused.


def _spec_checksum(spec: dict[str, Any] | None) -> str:
    """Stable content hash of a spec — used to tell an actual edit from a no-op
    refine (D-PF-APPLY-HONESTY). Key-order-independent via sort_keys."""
    import json as _json

    return hashlib.sha256(
        _json.dumps(spec or {}, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _hard_rules_pass(rules_out: list[dict[str, Any]]) -> bool:
    """Advisory-tier rules (e.g. Story Grid's sg_value_shift_per_scene, see
    docs/eval/plan-forge-story-grid-poc-2026-07-06.md) are reported but must
    NEVER block validate()/compile() -- only hard tier (the default) gates.
    """
    return all(r["pass"] for r in rules_out if r.get("tier", "hard") == "hard")


def _work_project_id(work: CompositionWork) -> UUID:
    """generation_job.project_id is NOT NULL — knowledge project or surrogate work.id."""
    if work.project_id is not None:
        return work.project_id
    if work.id is None:
        raise ValueError("work.id required for pending work")
    return work.id


class PlanForgeService:
    def __init__(
        self,
        plan_runs: PlanRunsRepo,
        jobs: GenerationJobsRepo,
        works: WorksRepo,
        llm: LLMClient | None = None,
    ) -> None:
        self._runs = plan_runs
        self._jobs = jobs
        self._works = works
        self._llm = llm
        self._proposals_repo: Any = None

    @property
    def _proposals(self):
        """Lazy — PF-7's gate is the only reader, and building it eagerly would have meant threading
        a new argument through every construction site (routers, deps, the worker's finalize hook)
        for a dependency most calls never touch."""
        if self._proposals_repo is None:
            from app.db.repositories.plan_bootstrap_proposals import PlanBootstrapProposalsRepo

            self._proposals_repo = PlanBootstrapProposalsRepo(self._runs._pool)
        return self._proposals_repo

    async def sync_from_job(self, created_by: UUID, book_id: UUID, run: PlanRun) -> PlanRun:
        """Lazy backstop: persist worker result when GET arrives before hook."""
        if run.active_job_id is None:
            return run
        # jobs.get is a BARE-ID read (no scope filter, spec 25 §Repo/service layer) —
        # assert the loaded job lives in THIS run's book partition before adopting it,
        # mirroring the MCP server's `job.project_id != pid` IDOR guard
        # (worker-loaded-id-needs-parent-scoping). A wrong/foreign active_job_id → not-found.
        job = await self._jobs.get(run.active_job_id)
        if job is None or job.book_id != book_id:
            return run
        if job.status in ("pending", "running"):
            return run
        if job.status == "completed":
            await self.apply_job_outcome(created_by, book_id, run.id, job, job.result or {})
        elif job.status == "failed":
            err = (job.result or {}).get("error", "job failed")
            await self._runs.update_run(
                book_id, run.id,
                status="failed", error_detail=str(err), active_job_id=None,
            )
        return (await self._runs.get_for_book(book_id, run.id)) or run

    async def _resolve_model_ref(self, created_by: UUID, model_ref: UUID | None) -> UUID:
        """D-PLANFORGE-DEFAULT-MODEL — shared fallback for every PlanForge LLM step:
        an explicit ref always wins; otherwise resolve the author's default planner
        model (mirrors glossary_plan's own GET /internal/planner-model fallback —
        their pinned 'planner' default, else their best active chat model) instead
        of hard-requiring the caller to name one. The agent is never authoritative
        for this pick (chat-service already strips any agent-guessed model_ref for
        these tools when no session pin is set)."""
        if model_ref is not None:
            return model_ref
        resolved = self._llm and await self._llm.resolve_planner_model(str(created_by))
        if resolved is None:
            raise ValueError(
                "model_ref required — no default chat model is set; "
                "pick one, or add a chat model in Settings"
            )
        return UUID(resolved)

    async def create_run(
        self,
        created_by: UUID,
        book_id: UUID,
        *,
        source_markdown: str,
        mode: str,
        model_ref: UUID | None,
        force: bool = False,
        # 27 PF-15 — the genre this plan is written FOR. It reaches the cast/world/motif prompts
        # (they are already genre-aware) and rides the RUN, because it is a per-run authorial
        # choice, not platform config.
        genre_tags: list[str] | None = None,
    ) -> tuple[PlanRun, bool, UUID | None]:
        """Returns (run, is_async, job_id). is_async=True → caller returns 202."""
        text = source_markdown.strip()
        if not text:
            raise ValueError("source_markdown required")
        # Resolved BEFORE the dedupe check below (not after) -- two omitted-model_ref
        # LLM proposes for the SAME text must both resolve to the caller's current
        # default and therefore dedupe against each other. Resolving after the check
        # would compare against the still-None sentinel, never match a prior run's
        # already-resolved model_ref, and silently re-run the (billed) LLM propose
        # on every retry.
        if mode == "llm":
            model_ref = await self._resolve_model_ref(created_by, model_ref)
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if not force:
            # D-PLANFORGE-MODE-DEDUPE: identical text but a different mode/model is a
            # DIFFERENT request, not a duplicate -- reusing the prior run here silently
            # ignored the user's newly-picked mode/model (e.g. Rules -> LLM retry on
            # unchanged text kept returning the stale Rules-mode result with no error).
            existing = await self._runs.find_by_checksum(book_id, checksum, mode)
            if existing is not None and existing.status != "failed" and existing.model_ref == model_ref:
                synced = await self.sync_from_job(created_by, book_id, existing)
                return synced, False, synced.active_job_id

        run = await self._runs.create(
            created_by,
            book_id,
            mode=mode,  # type: ignore[arg-type]
            source_checksum=checksum,
            source_markdown=text,
            model_ref=model_ref,
            status="pending",
            genre_tags=genre_tags,
        )
        doc = ingest_markdown(text)
        await self._runs.save_artifact(created_by, run.id, "document", doc)

        if mode == "rules":
            await self._finalize_rules_propose(created_by, book_id, run.id, doc)
            updated = await self._runs.get_for_book(book_id, run.id)
            return updated or run, False, None

        job_id = await self._enqueue_propose(created_by, book_id, run, text, model_ref)
        updated = await self._runs.get_for_book(book_id, run.id)
        return updated or run, True, job_id

    async def _finalize_rules_propose(
        self, created_by: UUID, book_id: UUID, run_id: UUID, doc: dict[str, Any],
    ) -> None:
        spec = propose_spec(doc)
        graph = build_graph(spec)
        await self._runs.save_artifact(created_by, run_id, "spec", spec)
        await self._runs.save_artifact(created_by, run_id, "graph", graph)
        await self._runs.update_run(
            book_id, run_id,
            status="proposed", clear_error=True, active_job_id=None,
        )

    async def _enqueue_propose(
        self,
        created_by: UUID,
        book_id: UUID,
        run: PlanRun,
        source_markdown: str,
        model_ref: UUID | None,
    ) -> UUID:
        # PM-9: the Work resolves per-BOOK; the caller flows only as the actor
        # stamp on a pending create (and as spend attribution below).
        work = await self._ensure_work(book_id, created_by=created_by)
        project_id = _work_project_id(work)
        pipe_input: dict[str, Any] = {
            "worker_op": "plan_forge_propose",
            "run_id": str(run.id),
            "book_id": str(book_id),
            "source_markdown": source_markdown,
            "model_ref": str(model_ref),
            "model_source": "user_model",
        }
        if settings.composition_worker_enabled:
            job, _ = await self._jobs.create(
                project_id,
                created_by=created_by,
                operation="plan_forge_propose", mode="auto", status="pending",
                input=pipe_input,
            )
            await enqueue_job(
                settings.redis_url, job_id=str(job.id),
                user_id=str(created_by), project_id=str(project_id),
            )
            await self._runs.update_run(
                book_id, run.id, active_job_id=job.id,
            )
            return job.id
        if self._llm is None:
            raise RuntimeError("LLM client required when worker disabled")
        result = await run_plan_forge_propose(
            self._llm, user_id=str(created_by), input=pipe_input,
        )
        job, _ = await self._jobs.create(
            project_id,
            created_by=created_by,
            operation="plan_forge_propose", mode="auto", status="completed",
            input=pipe_input, result=result,
        )
        await self.apply_job_outcome(created_by, book_id, run.id, job, result)
        return job.id

    async def apply_job_outcome(
        self,
        created_by: UUID,
        book_id: UUID,
        run_id: UUID,
        job: GenerationJob,
        result: dict[str, Any],
    ) -> None:
        op = (job.input or {}).get("worker_op") or job.operation
        if job.status == "failed" or result.get("error"):
            await self._runs.update_run(
                book_id, run_id,
                status="failed",
                error_detail=str(result.get("error", "job failed")),
                active_job_id=None,
            )
            return
        if op == "plan_forge_propose":
            spec = result.get("novel_system_spec")
            analyze = result.get("plan_analyze")
            if isinstance(spec, dict):
                await self._runs.save_artifact(created_by, run_id, "spec", spec)
                await self._runs.save_artifact(created_by, run_id, "graph", build_graph(spec))
            if isinstance(analyze, dict):
                await self._runs.save_artifact(created_by, run_id, "analyze", analyze)
            llm_io = result.get("llm_io")
            if llm_io:
                await self._runs.save_artifact(
                    created_by, run_id, "llm_io", {"steps": llm_io},
                )
            await self._runs.update_run(
                book_id, run_id,
                status="proposed", clear_error=True, active_job_id=None,
            )
            return
        if op == "plan_forge_refine":
            llm_io = result.get("llm_io")
            if llm_io:
                await self._runs.save_artifact(
                    created_by, run_id, "llm_io", {"steps": llm_io},
                )
            if result.get("accepted") and isinstance(result.get("spec"), dict):
                await self._runs.save_artifact(created_by, run_id, "spec", result["spec"])
                await self._runs.save_artifact(
                    created_by, run_id, "graph", build_graph(result["spec"]),
                )
                await self._runs.update_run(
                    book_id, run_id,
                    status="checkpoint", clear_error=True, active_job_id=None,
                )
            else:
                await self._runs.update_run(
                    book_id, run_id,
                    status="checkpoint",
                    error_detail=str(result.get("error") or result.get("reasons")),
                    active_job_id=None,
                )

    async def get_run_detail(
        self, created_by: UUID, book_id: UUID, run_id: UUID,
    ) -> dict[str, Any] | None:
        run = await self._runs.get_for_book(book_id, run_id)
        if run is None:
            return None
        run = await self.sync_from_job(created_by, book_id, run)
        return await self._serialize_run(created_by, run)

    async def list_runs(
        self, created_by: UUID, book_id: UUID, *, limit: int, cursor: str | None,
    ) -> dict[str, Any]:
        runs, next_cursor = await self._runs.list_for_book(
            book_id, limit=limit, cursor=cursor,
        )
        items = []
        for r in runs:
            synced = await self.sync_from_job(created_by, book_id, r)
            items.append(await self._serialize_run(created_by, synced))
        return {"items": items, "next_cursor": next_cursor}

    async def _serialize_run(self, created_by: UUID, run: PlanRun) -> dict[str, Any]:
        job_status = None
        if run.active_job_id is not None:
            # Bare-id job read (spec 25) — confirm it belongs to this run's book
            # partition before surfacing its status (same IDOR guard as sync_from_job).
            job = await self._jobs.get(run.active_job_id)
            if job is not None and job.book_id == run.book_id:
                job_status = job.status
        artifacts = await self._runs.list_artifact_refs(run.book_id, run.id)
        # D-PLANFORGE-ARC-PICKER: the Compile step's `arc_id` was a bare text input —
        # a writer has no reason to know a spec's internal arc ids ("arc_2"). The spec
        # itself already HAS the picker data (id + a human title); it was just never
        # surfaced to the FE (only artifact REFS — kind + id, no content — were ever
        # returned). Cheap to add: read the already-fetched-elsewhere latest spec
        # artifact once here. Empty list (not an error) when no spec exists yet.
        arcs: list[dict[str, Any]] = []
        spec_art = await self._runs.latest_artifact(run.book_id, run.id, "spec")
        if spec_art is not None:
            arcs = [
                {"id": a.get("id"), "title": a.get("title") or a.get("id")}
                for a in spec_art.content.get("arcs", [])
                if a.get("id")
            ]
        return {
            "id": str(run.id),
            "book_id": str(run.book_id),
            "status": run.status,
            "mode": run.mode,
            "model_ref": str(run.model_ref) if run.model_ref else None,
            "source_checksum": run.source_checksum,
            "active_job_id": str(run.active_job_id) if run.active_job_id else None,
            "job_status": job_status,
            "error_detail": run.error_detail,
            "checkpoint_state": run.checkpoint_state,
            # 27 PF-15 — the genre this plan was written for. Round-tripped so a client can SEE
            # what it asked for; a stored-but-never-returned field is indistinguishable from a
            # dropped one.
            "genre_tags": run.genre_tags,
            # 27 PF-3 — the pass ledger, WITH its derived fields (per-pass fresh|stale, the
            # contiguous pass_cursor, and blocked_at). Derived HERE, at serialization, and never
            # stored: a persisted freshness flag is a second source of truth that goes stale the
            # moment anything writes around it, which is the entire reason PF-3 fingerprints
            # inputs instead of setting dirty bits.
            **derive_view(run),
            "arcs": arcs,
            "artifacts": [
                {"kind": a["kind"], "artifact_id": str(a["artifact_id"])}
                for a in artifacts
            ],
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        }

    async def patch_spec(
        self, created_by: UUID, book_id: UUID, run_id: UUID, patch: dict[str, Any],
    ) -> dict[str, Any] | None:
        run = await self._runs.get_for_book(book_id, run_id)
        if run is None:
            return None
        art = await self._runs.latest_artifact(book_id, run_id, "spec")
        if art is None:
            raise ValueError("no spec artifact to patch")
        merged = _deep_merge(art.content, patch)
        await self._runs.save_artifact(created_by, run_id, "spec", merged)
        await self._runs.save_artifact(created_by, run_id, "graph", build_graph(merged))
        await self._runs.update_run(
            book_id, run_id, status="checkpoint",
        )
        updated = await self._runs.get_for_book(book_id, run_id)
        return await self._serialize_run(created_by, updated) if updated else None

    async def validate(
        self, created_by: UUID, book_id: UUID, run_id: UUID,
    ) -> dict[str, Any] | None:
        run = await self._runs.get_for_book(book_id, run_id)
        if run is None:
            return None
        spec_art = await self._runs.latest_artifact(book_id, run_id, "spec")
        if spec_art is None:
            raise ValueError("no spec to validate")
        spec = spec_art.content
        pkg_art = await self._runs.latest_artifact(book_id, run_id, "package")
        package = pkg_art.content.get("planning_package") if pkg_art else None
        rules_out = run_rules(spec, package)
        passed_rules = _hard_rules_pass(rules_out)
        fidelity_score = None
        golden_rules: list[dict[str, Any]] = [
            {"id": r["rule"], "passed": r["pass"], "message": r.get("detail", "")}
            for r in rules_out
        ]
        all_pass = passed_rules
        # 27 PF-19 — `fidelity_score` stays None unless a PER-RUN rubric exists.
        #
        # It used to be scored against `story-plan-v1.fidelity.yaml`: every user's plan was graded
        # on how closely it resembled the POC's novel, and the number looked like a real quality
        # score. A meaningless number is worse than no number — you can act on `None`.
        fidelity_cfg = await self._run_fidelity_config(book_id, run_id)
        if fidelity_cfg:
            try:
                fidelity = evaluate_spec_fidelity(spec, fidelity_cfg)
                fidelity_score = fidelity.get("score")
            except Exception:
                logger.warning("validate: per-run fidelity scoring failed", exc_info=True)
        # D-PLANFORGE-GENERAL-VALIDATE: a `validate_golden(...)` call used to sit
        # here, but its args were passed in the wrong order for this function's
        # real signature (spec, package, graph, doc, golden_path) -- it threw on
        # every single call and was silently swallowed by the bare `except`, so
        # it NEVER actually contributed to a real user's validate() response.
        # validate_golden is the POC's own self-test harness (see
        # tests/unit/test_plan_forge.py + scripts/live_validate_planforge_llm.py)
        # gating a live user's plan on the ORIGINAL fixture's golden expectations
        # (required section kinds, arc_2 min_events, etc.) was never correct
        # anyway -- removed rather than "fixed", since fixing the call would
        # have re-introduced that gate for real, differently-structured stories.
        report = {
            "passed": all_pass,
            "rules": golden_rules,
            "fidelity_score": fidelity_score,
            "fidelity_report_id": None,
        }
        art = await self._runs.save_artifact(
            created_by, run_id, "validation_report", report,
        )
        report["fidelity_report_id"] = str(art.id)
        if all_pass:
            await self._runs.update_run(book_id, run_id, status="validated")
        return report

    async def refine(
        self,
        created_by: UUID,
        book_id: UUID,
        run_id: UUID,
        *,
        model_ref: UUID | None,
        revision: dict[str, Any] | None,
        focus_paths: list[str] | None,
    ) -> tuple[str, dict[str, Any]]:
        """Returns (http_mode, body) where http_mode is 'sync' or 'async'."""
        run = await self._runs.get_for_book(book_id, run_id)
        if run is None:
            raise LookupError("run not found")
        spec_art = await self._runs.latest_artifact(book_id, run_id, "spec")
        if spec_art is None:
            raise ValueError("no spec to refine")
        spec = spec_art.content
        rev = dict(revision or {})
        if focus_paths:
            rev["focus_paths"] = focus_paths
        analyze_art = await self._runs.latest_artifact(book_id, run_id, "analyze")
        analyze = analyze_art.content if analyze_art else None
        pkg_art = await self._runs.latest_artifact(book_id, run_id, "package")
        package = pkg_art.content.get("planning_package") if pkg_art else None

        if not rev:
            return "sync", {
                "status": "no_change",
                "spec_artifact_id": str(spec_art.id),
                "fidelity_delta": 0.0,
                "diagnosis": None,
            }

        # Resolved AFTER the no-op early-return above — a no_change refine never
        # needs a model at all, so it must not force a resolve (or a required-model
        # error) on a call that's about to do nothing anyway.
        model_ref = await self._resolve_model_ref(created_by, model_ref)
        work = await self._ensure_work(book_id, created_by=created_by)
        project_id = _work_project_id(work)
        pipe_input: dict[str, Any] = {
            "worker_op": "plan_forge_refine",
            "run_id": str(run_id),
            "book_id": str(book_id),
            "spec": spec,
            "revision": rev,
            "model_ref": str(model_ref),
            "model_source": "user_model",
            "source_checksum": run.source_checksum,
            "analyze": analyze,
            "package": package,
        }

        if settings.composition_worker_enabled:
            job, _ = await self._jobs.create(
                project_id,
                created_by=created_by,
                operation="plan_forge_refine", mode="auto", status="pending",
                input=pipe_input,
            )
            await enqueue_job(
                settings.redis_url, job_id=str(job.id),
                user_id=str(created_by), project_id=str(project_id),
            )
            await self._runs.update_run(
                book_id, run_id, active_job_id=job.id, status="checkpoint",
            )
            return "async", {"run_id": str(run_id), "job_id": str(job.id), "status": "pending"}

        if self._llm is None:
            raise RuntimeError("LLM client required when worker disabled")
        before_checksum = _spec_checksum(spec)
        result = await run_plan_forge_refine(
            self._llm, user_id=str(created_by), input=pipe_input,
        )
        job, _ = await self._jobs.create(
            project_id,
            created_by=created_by,
            operation="plan_forge_refine", mode="auto", status="completed",
            input=pipe_input, result=result,
        )
        await self.apply_job_outcome(created_by, book_id, run_id, job, result)
        new_spec_art = await self._runs.latest_artifact(book_id, run_id, "spec")
        # D-PF-APPLY-HONESTY: a refine the model "accepted" but that did NOT change
        # the spec is a `no_change`, never `applied` — don't claim an edit that didn't
        # land. Compare the actual spec content, not the model's self-report.
        changed = (
            result.get("accepted")
            and new_spec_art is not None
            and _spec_checksum(new_spec_art.content) != before_checksum
        )
        if changed:
            status = "applied"
        elif result.get("accepted"):
            status = "no_change"
        else:
            status = "rejected"
        return "sync", {
            "status": status,
            "spec_artifact_id": str(new_spec_art.id) if new_spec_art else str(spec_art.id),
            "fidelity_delta": 0.0,
            "diagnosis": str(result.get("reasons")) if not result.get("accepted") else None,
        }

    async def review_checkpoint(
        self, created_by: UUID, book_id: UUID, run_id: UUID, *, approved: bool,
        pass_id: str | None = None,
        edits: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Advance/hold a checkpoint.

        Two checkpoints share this door, and `pass_id` picks which:

        * **`pass_id=None` — the SPEC checkpoint** (the v1 M4 behaviour, unchanged). approved=True →
          the current spec becomes `validated`; approved=False holds it at `checkpoint`.
        * **`pass_id=<a pass>` — a PASS checkpoint** (27 V2-D2/PF-6). This is the only way a
          BLOCKING pass (`cast`, `beats`) is ever accepted, and therefore the only way the compiler
          proceeds past the two questions the author alone can answer.

        `edits` deep-merges into the pass's artifact and saves a **NEW** artifact, which the pass
        then points at. That new id changes every downstream fingerprint, so everything below goes
        STALE by derivation — with zero invalidation writes. That is not a side effect; it is the
        point (PF-3). A human editing the cast SHOULD invalidate the scenes planned against the old
        one, and the alternative — mutating the artifact in place — would leave the downstream
        passes fresh against a plan that no longer exists.

        Idempotent, no LLM.
        """
        run = await self._runs.get_for_book(book_id, run_id)
        if run is None:
            return None
        if pass_id is not None:
            return await self._review_pass(
                created_by, book_id, run, pass_id, approved=approved, edits=edits,
            )
        spec_art = await self._runs.latest_artifact(book_id, run_id, "spec")
        if spec_art is None:
            raise ValueError("no spec to review")
        await self._runs.update_run(
            book_id, run_id,
            status="validated" if approved else "checkpoint",
        )
        updated = await self._runs.get_for_book(book_id, run_id)
        return await self._serialize_run(created_by, updated) if updated else None

    async def _review_pass(
        self, created_by: UUID, book_id: UUID, run: PlanRun, pass_id: str, *,
        approved: bool, edits: dict[str, Any] | None,
    ) -> dict[str, Any]:
        from app.services.plan_pass_service import (
            PACKAGE_KIND, PASS_REGISTRY, record_pass,
        )

        if pass_id not in PASS_REGISTRY:
            raise ValueError(f"unknown pass_id: {pass_id}")
        entry = dict(run.pass_state.get(pass_id) or {})
        if entry.get("status") != "completed":
            # You cannot accept a pass that never produced anything. Allowing it would let the
            # compiler proceed past a blocking checkpoint on an artifact that does not exist —
            # every downstream pass would then resolve its input to nothing and plan on air.
            raise ValueError(
                f"pass '{pass_id}' has not completed (status: {entry.get('status') or 'never run'})",
            )
        run_id = run.id
        spec = PASS_REGISTRY[pass_id]

        # THE GATE RUNS BEFORE ANY WRITE — so a refused checkpoint changed NOTHING.
        #
        # The live smoke caught the other order: with `approved=true` AND `edits`, the edit was
        # saved and *then* the seed gate refused, so the caller got a 409 for a call that had
        # already mutated their plan. A partial success reported as a failure is the worst of both —
        # the user retries, and the retry re-applies the edit on top of itself.
        #
        # Only the approve path is gated: `approved=false` + `edits` is "hold this, but keep my
        # revisions", which must still work while the seed sits unapplied.
        if approved:
            await self._assert_seed_applied(book_id, run, pass_id)

        artifact_id = entry.get("artifact_id")
        if edits:
            if not artifact_id:
                raise ValueError(f"pass '{pass_id}' has no artifact to edit")
            loaded = await self._runs.artifacts_by_ids(book_id, run_id, [artifact_id])
            art = loaded.get(str(artifact_id))
            if art is None:
                raise ValueError(
                    f"pass '{pass_id}' points at artifact {artifact_id}, which does not exist",
                )
            merged = _deep_merge(art.content, edits)
            new_art = await self._runs.save_artifact(
                created_by, run_id, spec.output_kind, merged,
            )
            artifact_id = new_art.id
            # Re-fingerprint against the SAME inputs: the human changed the OUTPUT, not the inputs,
            # so this pass stays FRESH (it is exactly the plan the author now wants). What goes
            # stale is everything DOWNSTREAM, because their input pointer — this artifact's id —
            # just changed. Derived, not written.
            state = record_pass(
                run, pass_id, status="completed", artifact_id=artifact_id,
                input_fingerprint=entry.get("input_fingerprint"),
                params=entry.get("params") or {},
            )
            await self._runs.update_run(book_id, run_id, pass_state=state)
            run = await self._runs.get_for_book(book_id, run_id) or run

        decision = "accepted" if approved else "rejected"
        state = record_pass(
            run, pass_id, decision=decision, decided_by="user",
            decided_at=datetime.now(UTC).isoformat(),
        )
        await self._runs.update_run(book_id, run_id, pass_state=state)
        run = await self._runs.get_for_book(book_id, run_id) or run

        if approved and pass_id == "cast":
            await self._bind_roster(created_by, book_id, run)

        return await self._serialize_run(created_by, run)

    async def _assert_seed_applied(self, book_id: UUID, run: PlanRun, pass_id: str) -> None:
        """PF-7: pass 2 cannot be ACCEPTED until its glossary seed proposal has been APPLIED.

        The blocking gate and the mutation gate are the same gate, so they cannot disagree. Without
        this, a user could accept the cast, let passes 3-7 plan an entire book around characters that
        exist only inside a run artifact, and only discover at bootstrap that none of them were ever
        in the glossary — with the scenes already referencing entity ids that resolve to nothing.

        Pass 3 (`world`) is ADVISORY and may lag: an unapplied world seed degrades grounding, it does
        not corrupt the plan. So only the blocking pass is gated.
        """
        if pass_id != "cast":
            return
        entry = dict(run.pass_state.get(pass_id) or {})
        proposal_id = entry.get("bootstrap_proposal_id")
        if not proposal_id:
            raise ValueError(
                "cast cannot be accepted before its glossary seed proposal exists "
                "(call plan_bootstrap_seed for this pass first)",
            )
        proposal = await self._proposals.get_for_book(book_id, UUID(str(proposal_id)))
        if proposal is None:
            raise ValueError(f"cast's seed proposal {proposal_id} no longer exists")
        if proposal.status != "applied":
            raise ValueError(
                f"cast cannot be accepted while its glossary seed proposal is "
                f"'{proposal.status}' — apply it first (PF-7)",
            )

    async def _bind_roster(self, created_by: UUID, book_id: UUID, run: PlanRun) -> None:
        """PF-13 — the symbol table lands in the SPEC, not only in the run.

        After the cast is accepted (and therefore seeded), write `{role_key: glossary_entity_id}`
        onto the linked arc's `structure_node.roster_bindings`. Without this, `cast_plan` is a
        stored-but-unread blob on the spec side — the write-only-behaviour bug `structure_node`
        exists to kill: the packer would keep prompting with names it re-resolves every time instead
        of the ids the author actually approved.

        Degrade-safe: an unlinked arc (no skeleton) or an unresolvable name leaves the binding out
        rather than failing the acceptance. The names that could NOT be bound are logged — an
        absent binding must be visible, not silently equivalent to "this role has no character".
        """
        from app.db.repositories.structure import StructureRepo

        entry = dict(run.pass_state.get("cast") or {})
        artifact_id = entry.get("artifact_id")
        if not artifact_id:
            return
        loaded = await self._runs.artifacts_by_ids(book_id, run.id, [artifact_id])
        art = loaded.get(str(artifact_id))
        if art is None:
            return
        cast = art.content.get("cast") or []
        if not cast:
            return

        roster = await self._roster_ids_by_name(book_id, run)
        bindings: dict[str, str] = {}
        unbound: list[str] = []
        for member in cast:
            role = (member.get("role") or "").strip().lower().replace(" ", "_")
            name = (member.get("name") or "").strip()
            if not role or not name:
                continue
            entity_id = roster.get(name.casefold())
            if not entity_id:
                unbound.append(name)
                continue
            # First writer wins per role: two "protagonist"s is the plan's problem to surface, not
            # something to silently resolve by overwriting.
            bindings.setdefault(role, str(entity_id))

        if unbound:
            logger.info(
                "roster bind: book=%s run=%s could not resolve %d cast name(s) to a glossary "
                "entity: %s — those roles stay UNBOUND (absent, not empty)",
                book_id, run.id, len(unbound), ", ".join(sorted(unbound)),
            )
        if not bindings:
            return

        repo = StructureRepo(self._runs._pool)
        arc = await repo.find_by_plan_run(book_id, run.id)
        if arc is None:
            logger.info(
                "roster bind: book=%s run=%s has no linked arc yet — skipping (the skeleton link "
                "runs at compile; a run that never compiled has nothing to bind onto)",
                book_id, run.id,
            )
            return
        await repo.update(
            arc.id,
            {"roster_bindings": {**(arc.roster_bindings or {}), **bindings}},
            expected_version=None,
        )
        logger.info(
            "roster bind: book=%s run=%s arc=%s bound %d role(s): %s",
            book_id, run.id, arc.id, len(bindings), sorted(bindings),
        )

    async def _roster_ids_by_name(self, book_id: UUID, run: PlanRun) -> dict[str, UUID]:
        """name.casefold() → glossary_entity_id, from the applied seed proposal.

        Read from the proposal's APPLY result, not from glossary directly: composition reads cast
        through the knowledge-gateway roster, never glossary (INV-KAL). The apply step is what
        minted the ids, and it recorded them.
        """
        # EVERY applied proposal for this book, not just the one `cast` points at — an id is a fact
        # about the BOOK, not about the proposal that minted it. A re-run of `cast` that adds one
        # character produces a proposal containing only that character; reading it alone would leave
        # every previously-seeded role UNBOUND, and the roster would shrink on a re-run.
        out: dict[str, UUID] = {}
        for proposal in await self._proposals.list_active_for_book(book_id):
            if proposal.status != "applied":
                continue
            # `applied_results` is keyed by the proposal's item key; each value is the row apply()
            # recorded from glossary-service — {entity_id, kind_code, name, status}. That row is
            # where the id was MINTED, which is why we read it here rather than asking glossary
            # (INV-KAL: composition reads cast through the roster, never glossary directly).
            for row in (proposal.applied_results or {}).values():
                if not isinstance(row, dict):
                    continue
                name = (row.get("name") or "").strip()
                eid = row.get("entity_id")
                if name and eid:
                    try:
                        out[name.casefold()] = UUID(str(eid))
                    except (ValueError, TypeError):
                        continue
        return out

    async def handoff_autofix(
        self, created_by: UUID, book_id: UUID, run_id: UUID,
        *, model_ref: UUID | None, max_rounds: int = 3,
    ) -> dict[str, Any] | None:
        """Batch-apply the top self-check gaps as a bounded refine loop (M4
        plan_handoff_autofix). Each round: self-check → take the ranked gaps →
        refine toward them; stop when no gaps remain or max_rounds is hit. Runs the
        refine synchronously (worker-off path); enqueues if the worker is on."""
        run = await self._runs.get_for_book(book_id, run_id)
        if run is None:
            return None
        # Resolved ONCE up front (not per-round) — every round in this loop must use
        # the SAME model, and resolving here also means a gap-free run (0 rounds)
        # never pays for a resolve it doesn't need.
        model_ref = await self._resolve_model_ref(created_by, model_ref)
        rounds = max(1, min(int(max_rounds), 5))
        applied: list[dict[str, Any]] = []
        for i in range(rounds):
            check = await self.self_check(created_by, book_id, run_id)
            gaps = (check or {}).get("gaps") or []
            top = [g for g in gaps if g.get("severity") in ("error", "warn")][:5]
            if not top:
                break
            revision = {"focus_paths": [g["path"] for g in top if g.get("path")]}
            mode, payload = await self.refine(
                created_by, book_id, run_id,
                model_ref=model_ref, revision=revision, focus_paths=None,
            )
            applied.append({"round": i + 1, "targets": len(top), "result": payload.get("status")})
            if mode == "async" or payload.get("status") != "applied":
                # async enqueued (can't loop synchronously) or no progress → stop.
                break
        detail = await self.get_run_detail(created_by, book_id, run_id)
        return {"rounds": applied, "run": detail}

    async def interpret(
        self,
        created_by: UUID,
        book_id: UUID,
        run_id: UUID,
        *,
        user_message: str,
        model_ref: UUID | None,
        apply_mode_hint: str | None = None,
    ) -> dict[str, Any] | None:
        run = await self._runs.get_for_book(book_id, run_id)
        if run is None:
            return None
        spec_art = await self._runs.latest_artifact(book_id, run_id, "spec")
        if spec_art is None:
            raise ValueError("no spec for interpret")
        model_ref = await self._resolve_model_ref(created_by, model_ref)
        spec = spec_art.content
        doc_art = await self._runs.latest_artifact(book_id, run_id, "document")
        section_map: list[dict[str, Any]] = []
        self_check_report = None
        # 27 PF-19 — the section map comes from THIS RUN'S document, not the POC's. Feeding the
        # interpreter another book's section headings gave it a map of a story the user never wrote.
        doc_md = await self._document_markdown(book_id, run_id)
        if doc_md:
            try:
                section_map = build_section_map_from_text(doc_md)
                self_check_report = run_self_check_on_document(
                    spec, doc_md, await self._run_fidelity_config(book_id, run_id),
                )
            except Exception:
                logger.warning("interpret: own-document coverage failed", exc_info=True)
                section_map = []

        if self._llm is not None:
            client = ProviderPlanForgeLLM(
                self._llm,
                user_id=str(created_by),
                model_source="user_model",
                model_ref=str(model_ref),
            )
            # Adapter: interpret_feedback expects LMStudioClient.sync chat — use rules + LLM steps
            rules_result = interpret_rules(
                user_message, spec, section_map, self_check_report=self_check_report,
            )
            if rules_result.get("intent") in ("handoff", "recheck", "complaint"):
                out = rules_result
            else:
                from app.engine.plan_forge.interpret import interpret_user_prompt, INTERPRET_SYSTEM
                from app.engine.plan_forge.json_extract import extract_json_object
                from app.engine.plan_forge.spec_index import build_spec_index, search_index, spec_slice_for_paths

                index = build_spec_index(spec, section_map)
                hits = search_index(user_message, index, top_k=5)
                paths = rules_result.get("focus_paths") or [h["path"] for h in hits[:2]]
                spec_slice = spec_slice_for_paths(spec, paths)
                gaps = (self_check_report or {}).get("gaps") or []
                user_prompt = interpret_user_prompt(user_message, spec_slice, hits, gaps)
                content = await client.chat(
                    step="interpret", system=INTERPRET_SYSTEM, user=user_prompt, temperature=0.1,
                )
                try:
                    out = extract_json_object(content)
                    out.setdefault("version", 1)
                except Exception:
                    out = rules_result
        else:
            out = interpret_feedback(
                user_message, spec, section_map, self_check_report=self_check_report,
            )
        if apply_mode_hint and apply_mode_hint != "auto":
            out["apply_mode"] = apply_mode_hint
        return out

    async def self_check(
        self, created_by: UUID, book_id: UUID, run_id: UUID,
    ) -> dict[str, Any] | None:
        run = await self._runs.get_for_book(book_id, run_id)
        if run is None:
            return None
        spec_art = await self._runs.latest_artifact(book_id, run_id, "spec")
        if spec_art is None:
            raise ValueError("no spec for self-check")
        spec = spec_art.content
        gaps: list[dict[str, Any]] = []
        fidelity_score = None
        # 27 PF-19 — the gaps are against THIS RUN'S OWN document. Before this, "what is missing from
        # your plan" answered "what does your plan not have that the POC's novel does" — a fixture
        # constant with extra steps (DA-14), delivered to the user as advice.
        doc_md = await self._document_markdown(book_id, run_id)
        if doc_md:
            try:
                report = run_self_check_on_document(
                    spec, doc_md, await self._run_fidelity_config(book_id, run_id),
                )
                fidelity_score = (report.get("fidelity") or {}).get("score")
                for g in report.get("ranked_gaps") or []:
                    gaps.append({
                        "path": g.get("id", ""),
                        "severity": g.get("severity", "warn"),
                        "message": g.get("detail", ""),
                    })
            except Exception:
                logger.warning("self_check: own-document coverage failed", exc_info=True)
        if not gaps:
            audit = consistency_audit(spec)
            for c in audit.get("critical") or []:
                gaps.append({"path": c.get("field", ""), "severity": "error", "message": c.get("issue", "")})
            for r in run_rules(spec):
                if not r["pass"]:
                    gaps.append({"path": r["rule"], "severity": "warn", "message": r.get("detail", "")})
        return {"gaps": gaps, "fidelity_score": fidelity_score}

    # ── 27 PF-19 — fixture severing ─────────────────────────────────────────────────────────
    async def _document_markdown(self, book_id: UUID, run_id: UUID) -> str:
        """The run's OWN source markdown.

        It lives on `plan_run.source_markdown` — every run persists it. (NOT on the `document`
        artifact: `ingest_markdown` stores only the PARSED sections plus a checksum, so the raw text
        is not there. I reached for the artifact first and it silently returned "" — which would
        have quietly disabled coverage for every run rather than pointing it at the right source.)

        Returns "" when a run has no source. The callers then compute NOTHING — they do not fall
        back to the fixture, because a coverage report against someone else's novel is not a
        degraded answer, it is a wrong one.
        """
        run = await self._runs.get_for_book(book_id, run_id)
        return (run.source_markdown or "") if run else ""

    async def _run_fidelity_config(self, book_id: UUID, run_id: UUID) -> dict[str, Any]:
        """This run's OWN fidelity rubric, or {} — never the POC's.

        A fidelity score is a grade against a rubric. With no per-run rubric there is no honest
        grade, so callers report `None` (absent), never a number derived from another book's rubric.
        The fixture YAML is regression-harness-only from here on (09 §8b).
        """
        art = await self._runs.latest_artifact(book_id, run_id, "validation_report")
        cfg = (art.content or {}).get("fidelity_config") if art else None
        return cfg if isinstance(cfg, dict) else {}

    # ── 27 V2-F1 — the pass ledger (read) ───────────────────────────────────────────────────
    async def pass_status(
        self, created_by: UUID, book_id: UUID, run_id: UUID,
    ) -> dict[str, Any] | None:
        """The run's DERIVED pass view: per-pass freshness, the cursor, and what is blocking.

        Nothing here is stored. `fresh`, `pass_cursor` and `blocked_at` are all recomputed from the
        recorded fingerprints against the CURRENT input pointers, every read — which is the only way
        a staleness report cannot itself be stale (PF-3/DA-7).
        """
        from app.services.plan_pass_service import PACKAGE_KIND, derive_view

        run = await self._runs.get_for_book(book_id, run_id)
        if run is None:
            return None
        package = await self._runs.latest_artifact(book_id, run_id, PACKAGE_KIND)
        return {
            "run_id": str(run_id),
            "book_id": str(book_id),
            "genre_tags": list(run.genre_tags or []),
            # Absent ≠ zero: a run that has never compiled has NO package, and every
            # package-reading pass is therefore un-runnable. Say so, rather than reporting seven
            # tidy "pending" rows that imply the compiler is merely waiting to be told to go.
            "compiled": package is not None,
            **derive_view(run, package_artifact_id=package.id if package else None),
        }

    # ── 27 V2-F1 — re-link ──────────────────────────────────────────────────────────────────
    async def relink(
        self, created_by: UUID, book_id: UUID, run_id: UUID, *, target: str = "skeleton",
    ) -> dict[str, Any]:
        """Re-run a linker over an existing run (27 PF-8, both halves).

        The skeleton link already runs inline at `compile()`; this is the door for re-linking after
        an edit, and the ONLY door for the scene link (which has no natural compile-time moment —
        the scenes do not exist until pass 6 has run and pass 7 has healed them).

        Idempotent by construction: the upserts arbitrate on the run-scoped partial unique index, so
        a re-link updates the nodes THIS RUN minted and never duplicates them. And it never reclaims
        a node a human has edited since — those come back as `preserved_user_edit` (PF-11).
        """
        from app.services.plan_pass_service import PACKAGE_KIND

        run = await self._runs.get_for_book(book_id, run_id)
        if run is None:
            raise LookupError("run not found")
        work = await self._ensure_work(book_id, created_by=created_by)
        linker = PlanLinkService(get_pool())
        prior = await self._runs.latest_link_report(book_id, run_id, target)
        prior_versions = (prior.content or {}).get("linked_versions") if prior else None

        if target == "skeleton":
            pkg_art = await self._runs.latest_artifact(book_id, run_id, PACKAGE_KIND)
            package = (pkg_art.content or {}).get("planning_package") if pkg_art else None
            if not package:
                raise ValueError("this run has no compiled package to link — compile it first")
            coro = linker.link_outline_skeleton(
                created_by=created_by, book_id=book_id,
                project_id=_work_project_id(work), run_id=run_id,
                package=package, prior_versions=prior_versions,
            )
        elif target == "scene_plan":
            scenes_by_event = await self._scenes_by_event(book_id, run)
            if not scenes_by_event:
                # E4's law, applied to the scene half: zero nodes linked is an ERROR, never a silent
                # 200. "The scenes pass has not produced anything yet" and "your book has no scenes"
                # must not look the same to a caller.
                raise ValueError(
                    "this run has no scene plan to link — run the `scenes` pass first "
                    "(and `self_heal` if you want the healed version)",
                )
            coro = linker.link_scene_plan(
                created_by=created_by, book_id=book_id,
                project_id=_work_project_id(work), run_id=run_id,
                scenes_by_event=scenes_by_event, prior_versions=prior_versions,
            )
        else:
            raise ValueError(f"unknown link target: {target}")

        try:
            report = await coro
        except LinkError as exc:
            await self._runs.save_artifact(
                created_by, run_id, "link_report", exc.report.to_dict(),
            )
            raise ValueError(exc.report.detail or "link failed") from exc
        await self._runs.save_artifact(created_by, run_id, "link_report", report.to_dict())
        return report.to_dict()

    async def _scenes_by_event(
        self, book_id: UUID, run: PlanRun,
    ) -> dict[str, list[dict[str, Any]]]:
        """The scenes to link, `event_id` → ordered scenes.

        Read through the PASS POINTER, not by latest-kind: passes 6 and 7 BOTH emit `scene_plan`,
        so "the newest scene_plan artifact" is ambiguous by construction. We take pass 7's if it has
        run (the healed plan is the one the author reviewed), else pass 6's.
        """
        for pass_id in ("self_heal", "scenes"):
            entry = dict(run.pass_state.get(pass_id) or {})
            if entry.get("status") != "completed" or not entry.get("artifact_id"):
                continue
            loaded = await self._runs.artifacts_by_ids(
                book_id, run.id, [entry["artifact_id"]],
            )
            art = loaded.get(str(entry["artifact_id"]))
            if art is None:
                continue
            out: dict[str, list[dict[str, Any]]] = {}
            for ch in (art.content or {}).get("chapters", []) or []:
                event_id = ((ch.get("chapter") or {}).get("chapter_id") or "").strip()
                if not event_id:
                    continue
                out[event_id] = list(ch.get("scenes") or [])
            if out:
                return out
        return {}

    # ── 27 V2-C2 — run ONE compiler pass ────────────────────────────────────────────────────
    async def run_pass(
        self,
        created_by: UUID,
        book_id: UUID,
        run_id: UUID,
        pass_id: str,
        *,
        model_ref: UUID | None,
        params: dict[str, Any] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Enqueue `pass_id` for this run. Returns the job envelope; the artifact and the
        `pass_state` entry land via the worker's finalize hook (27 V2-C2).

        The PF-5 gate is checked HERE as well as in the worker — not belt-and-braces, but two
        different jobs. Here it gives the caller a synchronous 409 with the actual blockers, so a
        user (or an agent) learns *why* immediately instead of polling a job that was always going
        to fail. In the worker it is the real gate: by the time the job runs, the state it was
        enqueued against may have changed underneath it.
        """
        from app.services.plan_pass_service import (
            PACKAGE_KIND, PASS_REGISTRY, UpstreamStale, blockers_for, derive_view, record_pass,
        )

        if pass_id not in PASS_REGISTRY:
            raise ValueError(f"unknown pass_id: {pass_id}")
        run = await self._runs.get_for_book(book_id, run_id)
        if run is None:
            raise ValueError("run not found")

        package = await self._runs.latest_artifact(book_id, run_id, PACKAGE_KIND)
        if PASS_REGISTRY[pass_id].reads_package and package is None:
            raise ValueError(
                f"pass '{pass_id}' reads the planning package, but this run has none — compile first",
            )
        package_id = package.id if package else None

        if not force:
            blockers = blockers_for(run, pass_id, package_artifact_id=package_id)
            if blockers:
                # ONE name for one concept — the worker raises this same type.
                raise UpstreamStale(pass_id, blockers)

        work = await self._ensure_work(book_id, created_by=created_by)
        project_id = _work_project_id(work)
        pass_input: dict[str, Any] = {
            "worker_op": "plan_pass",
            "run_id": str(run_id),
            "book_id": str(book_id),
            "project_id": str(project_id),
            "pass_id": pass_id,
            "model_ref": str(model_ref),
            "model_source": "user_model",
            "params": dict(params or {}),
            "force": force,
        }
        job, _ = await self._jobs.create(
            project_id,
            created_by=created_by,
            operation="plan_pass", mode="auto", status="pending",
            input=pass_input,
        )

        # MARK THE PASS `running` THE MOMENT IT IS ENQUEUED — the ledger must describe the PRESENT.
        #
        # Without this, a RE-RUN is invisible: the entry still carries the PREVIOUS run's
        # `completed` + `accepted`, because nothing writes to it again until the finalize hook lands
        # 30 seconds later. So for the whole duration of a re-run the ledger reports a pass that is
        # done and approved, while the artifact it names is being replaced.
        #
        # The live smoke showed what that costs. A caller polls `status`, sees `completed`
        # instantly (it never changed), and accepts — and then the re-run's finalize hook writes
        # `decision: pending` on top, because a NEW cast has not been reviewed by anyone. Their
        # acceptance is silently discarded, `world` refuses with `blockers: ['cast']`, and the ledger
        # says cast is `completed` and `pending` with no explanation of how it got there.
        #
        # `running` also makes the freshness derivation honest: `is_fresh` requires `completed`, so
        # nothing downstream can run against a pass that is mid-flight, and `_review_pass` refuses to
        # accept it ("has not completed"). One field, and all three lies stop.
        state = record_pass(run, pass_id, status="running", job_id=job.id)
        await self._runs.update_run(book_id, run_id, pass_state=state)

        if settings.composition_worker_enabled:
            await enqueue_job(
                settings.redis_url, job_id=str(job.id),
                user_id=str(created_by), project_id=str(project_id),
            )
        else:
            # Worker off (dev): run it inline so the pass is not silently a no-op. A job row that
            # sits `pending` forever with nobody to run it IS the silent-success bug — the API
            # said 202 and nothing ever happened.
            from app.worker.job_consumer import run_job

            if self._llm is None:
                raise RuntimeError("LLM client required when worker disabled")
            await run_job(
                self._runs._pool, self._llm, job_id=str(job.id), user_id=str(created_by),
            )
            job = await self._jobs.get(job.id) or job

        run_after = await self._runs.get_for_book(book_id, run_id) or run
        return {
            "job_id": str(job.id),
            "status": job.status,
            "pass_id": pass_id,
            **derive_view(run_after, package_artifact_id=package_id),
        }

    async def compile(
        self,
        created_by: UUID,
        book_id: UUID,
        run_id: UUID,
        *,
        arc_id: str,
        run_pipeline: bool = False,
        model_ref: UUID | None = None,
    ) -> tuple[str, dict[str, Any]]:
        run = await self._runs.get_for_book(book_id, run_id)
        if run is None:
            raise LookupError("run not found")
        spec_art = await self._runs.latest_artifact(book_id, run_id, "spec")
        if spec_art is None:
            raise ValueError("no spec to compile")
        spec = spec_art.content
        rules_out = run_rules(spec)
        if not _hard_rules_pass(rules_out):
            raise ValueError("validation failed — compile blocked")

        # GENRE (PF-15) — the open sub-question this comment used to name is now ANSWERED.
        #
        # It read: "`NovelSystemSpec` has nowhere to declare a genre, and compile.py used to
        # fabricate the POC fixture's ["xianxia","cultivation","psychological"] for EVERY book —
        # which reached `propose_cast`. An empty list is honest; a wrong genre is not. Sourcing it
        # (spec.meta, a per-book setting, or an explicit field) is BPS-20's open sub-question."
        #
        # `plan_run.genre_tags` IS the explicit field (27 PF-15): the caller declares the genre when
        # they create the RUN, it rides the row, and it lands here. Still no fabricated default —
        # an unset genre stays `[]`, which is the honest value the old comment insisted on.
        compiled = compile_artifacts(spec, arc_id=arc_id)
        package = compiled["planning_package"]
        if run.genre_tags:
            package["genre_tags"] = list(run.genre_tags)
        await self._runs.save_artifact(
            created_by, run_id, "package",
            {"planning_package": package, **{k: v for k, v in compiled.items() if k != "planning_package"}},
        )
        work = await self._ensure_work(book_id, created_by=created_by)

        # 27 PF-8(a) — THE SKELETON LINK, inline. This is the step that makes the compiler actually
        # produce something: arc → structure_node, chapters → outline_node. It runs HERE, not behind
        # a separate call, because a compile that materialises nothing IS the silent-success bug at
        # compile scale (BPS-18/DA-13: "an emitted artifact with no linker is a bug"). It is
        # deterministic and composition-local — no LLM, no human gate; the spec layer is the agent's
        # normal CRUD surface, and the heavy gates guard the manuscript and the glossary, not this.
        #
        # A prior link_report supplies the versions we last wrote, so PF-11's preservation can tell
        # "we wrote this" from "a human has edited it since".
        # BY TARGET, not "latest link_report". Both linkers emit kind `link_report`, so a bare
        # latest-by-kind read would hand the SKELETON link the SCENE link's report — whose ledger
        # holds only `scene:*` keys. The skeleton would then see no prior `arc:*`/`chapter:*`
        # version, fall back to the no-prior sentinel, and overwrite every human edit on the next
        # compile. Same root cause as the preserved-path bug: "missing bookkeeping ⇒ overwrite" is
        # only safe if the bookkeeping cannot go missing during normal operation. It can.
        prior_report = await self._runs.latest_link_report(book_id, run_id, "skeleton")
        prior_versions = (
            (prior_report.content or {}).get("linked_versions") or {} if prior_report else {}
        )
        linker = PlanLinkService(get_pool())
        try:
            link_report = await linker.link_outline_skeleton(
                created_by=created_by,
                book_id=book_id,
                project_id=_work_project_id(work),
                run_id=run_id,
                package=package,
                prior_versions=prior_versions,
            )
        except LinkError as exc:
            # Persist the FAILED report before raising. A failure the user cannot inspect is barely
            # better than a silent success — they need to see that zero nodes were written and why.
            await self._runs.save_artifact(
                created_by, run_id, "link_report", exc.report.to_dict(),
            )
            raise ValueError(exc.report.detail or "link failed") from exc
        await self._runs.save_artifact(created_by, run_id, "link_report", link_report.to_dict())

        await self._runs.update_run(
            book_id, run_id,
            status="compiled", work_id=work.id,
        )
        body: dict[str, Any] = {
            "package": package,
            "pipeline_job_id": None,
            "work_id": str(work.id) if work.id else None,
            # E4 — per-target counts, ALWAYS returned. A caller that only gets "ok" cannot tell that
            # the compiler wrote nothing.
            "link": link_report.to_dict(),
        }
        if not run_pipeline:
            return "sync", body
        model_ref = await self._resolve_model_ref(created_by, model_ref)
        project_id = _work_project_id(work)
        # D-PLANFORGE-PIPELINE-CHAPTERPLAN-FIX: package.chapters[] is
        # {title, ordinal, event_id} (compile.py) — the worker's
        # `run_plan_pipeline` needs `ChapterPlan`-shaped dicts
        # {chapter_id, title, sort_order, beat_role, intent}. This mapping
        # was previously ABSENT (raw package.chapters[] passed straight
        # through), so `ChapterPlan(**c)` raised a TypeError on every real
        # invocation — confirmed via a code audit 2026-07-06, never
        # exercised successfully in production. `chapter_id=event_id` is
        # the correlation key the auto-bootstrap gate (§6 M3) uses to
        # attach each event's resulting scene/beat plan back to the real
        # chapter it creates. `beats: []` degrades the pipeline's L1
        # beat-map stage to a no-op (beat_role stays None) — PlanForge's
        # `arc_kind` (e.g. "discovery"/"power") is a THEME tag, not a
        # `structure_template.kind`, so there is no beats list to source
        # here without inventing a new mapping; the pipeline's own
        # degrade-safe design (planning_pipeline.py) tolerates this.
        pipe_input = {
            "worker_op": "plan_pipeline",
            "model_source": "user_model",
            "model_ref": str(model_ref),
            "premise": package.get("premise", ""),
            "beats": [],
            "chapters": [
                {
                    "chapter_id": ch["event_id"], "title": ch["title"],
                    "sort_order": ch.get("ordinal", i),
                    "beat_role": None, "intent": "",
                }
                for i, ch in enumerate(package.get("chapters", []), start=1)
            ],
            "genre_tags": package.get("genre_tags", []),
            "book_id": str(book_id),
            "project_id": str(project_id),
            "k_ceiling": settings.compose_diverge_k,
            "high_threshold": settings.plan_high_tension_threshold,
            "min_scenes": settings.plan_min_scenes_per_chapter,
            "max_scenes": settings.plan_max_scenes_per_chapter,
            "source_language": "auto",
            "self_heal": True,
            "plan_forge_package": package,
        }
        if settings.composition_worker_enabled:
            job, _ = await self._jobs.create(
                project_id,
                created_by=created_by,
                operation="plan_pipeline", mode="auto", status="pending",
                input=pipe_input,
            )
            await enqueue_job(
                settings.redis_url, job_id=str(job.id),
                user_id=str(created_by), project_id=str(project_id),
            )
            body["pipeline_job_id"] = str(job.id)
            # §6 M3: persist the job id onto the run (checkpoint_state — a
            # scratch JSONB field already used for exactly this kind of
            # cross-call bookkeeping) so the auto-bootstrap gate's propose()
            # can find + consume this job's result later. Previously this
            # id was returned in the response body ONCE and never
            # persisted anywhere queryable — a caller that didn't capture
            # the response had no way to find it again.
            await self._runs.update_run(
                book_id, run_id,
                checkpoint_state={**run.checkpoint_state, "pipeline_job_id": str(job.id)},
            )
            return "async", body
        body["pipeline_preview"] = mock_pipeline_result(package)
        return "sync", body

    async def _ensure_work(self, book_id: UUID, *, created_by: UUID) -> CompositionWork:
        """Resolve THE Work for the book — caller-INDEPENDENT (PM-9, spec 25).

        Previously keyed by the acting caller, so an EDIT-grantee running
        PlanForge silently forked their own pending Work that could never be
        backfilled (knowledge create is owner-only) — the F5 fork bug. Now:
        the book's CANONICAL marked Work (`source_work_id IS NULL`, active —
        at most one via the partial `uq_composition_work_book`), else the
        book's single pending Work (`(book_id) WHERE pending` partial unique,
        PM-4), else create a pending Work stamped `created_by` = the acting
        caller (plain actor stamp for attribution — never scope). Whichever
        later owner-path creates the knowledge project backfills that row.
        The UniqueViolation catch re-gets by the SAME book-keyed predicates
        the partial indexes enforce."""
        import asyncpg

        def _canonical(works: list[CompositionWork]) -> CompositionWork | None:
            for w in works:
                if w.source_work_id is None:
                    return w  # earliest-created first (repo ORDER BY); ≤1 post-M3
            return None

        work = _canonical(await self._works.resolve_by_book(book_id))
        if work is not None:
            return work
        pending = await self._works.get_pending_for_book(book_id)
        if pending is not None:
            return pending
        try:
            return await self._works.create_pending(created_by, book_id)
        except asyncpg.UniqueViolationError:
            pending = await self._works.get_pending_for_book(book_id)
            if pending is not None:
                return pending
            work = _canonical(await self._works.resolve_by_book(book_id))
            if work is not None:
                return work
            raise
