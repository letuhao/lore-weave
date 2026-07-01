"""PlanForge HTTP service layer (M3).

Orchestrates ingest→propose→validate→compile against plan_run/plan_artifact
persistence and generation_job async worker ops.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID

from app.clients.llm_client import LLMClient
from app.config import settings
from app.db.models import CompositionWork, GenerationJob, PlanRun
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.db.repositories.plan_runs import PlanRunsRepo
from app.db.repositories.works import WorksRepo
from app.engine.plan_forge.compile import compile_artifacts, mock_pipeline_result
from app.engine.plan_forge.coverage import load_coverage_context
from app.engine.plan_forge.decompose import build_graph
from app.engine.plan_forge.elaborate import consistency_audit
from app.engine.plan_forge.eval_fidelity import evaluate_spec_fidelity, load_fidelity_config
from app.engine.plan_forge.ingest import ingest_markdown
from app.engine.plan_forge.interpret import interpret_feedback, interpret_rules
from app.engine.plan_forge.llm import ProviderPlanForgeLLM
from app.engine.plan_forge.propose import propose_spec
from app.engine.plan_forge.self_check import run_self_check
from app.engine.plan_forge.validate import _deep_merge, run_rules, validate_golden
from app.worker.events import enqueue_job
from app.worker.operations import run_plan_forge_propose, run_plan_forge_refine

_FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "plan-forge"
_GOLDEN = _FIXTURES / "story-plan-v1.expectations.yaml"
_FIDELITY = _FIXTURES / "story-plan-v1.fidelity.yaml"


def _spec_checksum(spec: dict[str, Any] | None) -> str:
    """Stable content hash of a spec — used to tell an actual edit from a no-op
    refine (D-PF-APPLY-HONESTY). Key-order-independent via sort_keys."""
    import json as _json

    return hashlib.sha256(
        _json.dumps(spec or {}, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


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

    async def sync_from_job(self, owner_user_id: UUID, book_id: UUID, run: PlanRun) -> PlanRun:
        """Lazy backstop: persist worker result when GET arrives before hook."""
        if run.active_job_id is None:
            return run
        job = await self._jobs.get(owner_user_id, run.active_job_id)
        if job is None:
            return run
        if job.status in ("pending", "running"):
            return run
        if job.status == "completed":
            await self.apply_job_outcome(owner_user_id, book_id, run.id, job, job.result or {})
        elif job.status == "failed":
            err = (job.result or {}).get("error", "job failed")
            await self._runs.update_run(
                owner_user_id, book_id, run.id,
                status="failed", error_detail=str(err), active_job_id=None,
            )
        return (await self._runs.get_for_owner(owner_user_id, book_id, run.id)) or run

    async def create_run(
        self,
        owner_user_id: UUID,
        book_id: UUID,
        *,
        source_markdown: str,
        mode: str,
        model_ref: UUID | None,
        force: bool = False,
    ) -> tuple[PlanRun, bool, UUID | None]:
        """Returns (run, is_async, job_id). is_async=True → caller returns 202."""
        text = source_markdown.strip()
        if not text:
            raise ValueError("source_markdown required")
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if not force:
            existing = await self._runs.find_by_checksum(owner_user_id, book_id, checksum)
            if existing is not None and existing.status != "failed":
                synced = await self.sync_from_job(owner_user_id, book_id, existing)
                return synced, False, synced.active_job_id

        if mode == "llm" and model_ref is None:
            raise ValueError("model_ref required when mode=llm")

        run = await self._runs.create(
            owner_user_id,
            book_id,
            mode=mode,  # type: ignore[arg-type]
            source_checksum=checksum,
            source_markdown=text,
            model_ref=model_ref,
            status="pending",
        )
        doc = ingest_markdown(text)
        await self._runs.save_artifact(owner_user_id, run.id, "document", doc)

        if mode == "rules":
            await self._finalize_rules_propose(owner_user_id, book_id, run.id, doc)
            updated = await self._runs.get_for_owner(owner_user_id, book_id, run.id)
            return updated or run, False, None

        job_id = await self._enqueue_propose(owner_user_id, book_id, run, text, model_ref)
        updated = await self._runs.get_for_owner(owner_user_id, book_id, run.id)
        return updated or run, True, job_id

    async def _finalize_rules_propose(
        self, owner_user_id: UUID, book_id: UUID, run_id: UUID, doc: dict[str, Any],
    ) -> None:
        spec = propose_spec(doc)
        graph = build_graph(spec)
        await self._runs.save_artifact(owner_user_id, run_id, "spec", spec)
        await self._runs.save_artifact(owner_user_id, run_id, "graph", graph)
        await self._runs.update_run(
            owner_user_id, book_id, run_id,
            status="proposed", clear_error=True, active_job_id=None,
        )

    async def _enqueue_propose(
        self,
        owner_user_id: UUID,
        book_id: UUID,
        run: PlanRun,
        source_markdown: str,
        model_ref: UUID | None,
    ) -> UUID:
        work = await self._ensure_work(owner_user_id, book_id)
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
                owner_user_id, project_id,
                operation="plan_forge_propose", mode="auto", status="pending",
                input=pipe_input,
            )
            await enqueue_job(
                settings.redis_url, job_id=str(job.id),
                user_id=str(owner_user_id), project_id=str(project_id),
            )
            await self._runs.update_run(
                owner_user_id, book_id, run.id, active_job_id=job.id,
            )
            return job.id
        if self._llm is None:
            raise RuntimeError("LLM client required when worker disabled")
        result = await run_plan_forge_propose(
            self._llm, user_id=str(owner_user_id), input=pipe_input,
        )
        job, _ = await self._jobs.create(
            owner_user_id, project_id,
            operation="plan_forge_propose", mode="auto", status="completed",
            input=pipe_input, result=result,
        )
        await self.apply_job_outcome(owner_user_id, book_id, run.id, job, result)
        return job.id

    async def apply_job_outcome(
        self,
        owner_user_id: UUID,
        book_id: UUID,
        run_id: UUID,
        job: GenerationJob,
        result: dict[str, Any],
    ) -> None:
        op = (job.input or {}).get("worker_op") or job.operation
        if job.status == "failed" or result.get("error"):
            await self._runs.update_run(
                owner_user_id, book_id, run_id,
                status="failed",
                error_detail=str(result.get("error", "job failed")),
                active_job_id=None,
            )
            return
        if op == "plan_forge_propose":
            spec = result.get("novel_system_spec")
            analyze = result.get("plan_analyze")
            if isinstance(spec, dict):
                await self._runs.save_artifact(owner_user_id, run_id, "spec", spec)
                await self._runs.save_artifact(owner_user_id, run_id, "graph", build_graph(spec))
            if isinstance(analyze, dict):
                await self._runs.save_artifact(owner_user_id, run_id, "analyze", analyze)
            llm_io = result.get("llm_io")
            if llm_io:
                await self._runs.save_artifact(
                    owner_user_id, run_id, "llm_io", {"steps": llm_io},
                )
            await self._runs.update_run(
                owner_user_id, book_id, run_id,
                status="proposed", clear_error=True, active_job_id=None,
            )
            return
        if op == "plan_forge_refine":
            llm_io = result.get("llm_io")
            if llm_io:
                await self._runs.save_artifact(
                    owner_user_id, run_id, "llm_io", {"steps": llm_io},
                )
            if result.get("accepted") and isinstance(result.get("spec"), dict):
                await self._runs.save_artifact(owner_user_id, run_id, "spec", result["spec"])
                await self._runs.save_artifact(
                    owner_user_id, run_id, "graph", build_graph(result["spec"]),
                )
                await self._runs.update_run(
                    owner_user_id, book_id, run_id,
                    status="checkpoint", clear_error=True, active_job_id=None,
                )
            else:
                await self._runs.update_run(
                    owner_user_id, book_id, run_id,
                    status="checkpoint",
                    error_detail=str(result.get("error") or result.get("reasons")),
                    active_job_id=None,
                )

    async def get_run_detail(
        self, owner_user_id: UUID, book_id: UUID, run_id: UUID,
    ) -> dict[str, Any] | None:
        run = await self._runs.get_for_owner(owner_user_id, book_id, run_id)
        if run is None:
            return None
        run = await self.sync_from_job(owner_user_id, book_id, run)
        return await self._serialize_run(owner_user_id, run)

    async def list_runs(
        self, owner_user_id: UUID, book_id: UUID, *, limit: int, cursor: str | None,
    ) -> dict[str, Any]:
        runs, next_cursor = await self._runs.list_for_owner(
            owner_user_id, book_id, limit=limit, cursor=cursor,
        )
        items = []
        for r in runs:
            synced = await self.sync_from_job(owner_user_id, book_id, r)
            items.append(await self._serialize_run(owner_user_id, synced))
        return {"items": items, "next_cursor": next_cursor}

    async def _serialize_run(self, owner_user_id: UUID, run: PlanRun) -> dict[str, Any]:
        job_status = None
        if run.active_job_id is not None:
            job = await self._jobs.get(owner_user_id, run.active_job_id)
            if job is not None:
                job_status = job.status
        artifacts = await self._runs.list_artifact_refs(owner_user_id, run.id)
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
            "artifacts": [
                {"kind": a["kind"], "artifact_id": str(a["artifact_id"])}
                for a in artifacts
            ],
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        }

    async def patch_spec(
        self, owner_user_id: UUID, book_id: UUID, run_id: UUID, patch: dict[str, Any],
    ) -> dict[str, Any] | None:
        run = await self._runs.get_for_owner(owner_user_id, book_id, run_id)
        if run is None:
            return None
        art = await self._runs.latest_artifact(owner_user_id, run_id, "spec")
        if art is None:
            raise ValueError("no spec artifact to patch")
        merged = _deep_merge(art.content, patch)
        await self._runs.save_artifact(owner_user_id, run_id, "spec", merged)
        await self._runs.save_artifact(owner_user_id, run_id, "graph", build_graph(merged))
        await self._runs.update_run(
            owner_user_id, book_id, run_id, status="checkpoint",
        )
        updated = await self._runs.get_for_owner(owner_user_id, book_id, run_id)
        return await self._serialize_run(owner_user_id, updated) if updated else None

    async def validate(
        self, owner_user_id: UUID, book_id: UUID, run_id: UUID,
    ) -> dict[str, Any] | None:
        run = await self._runs.get_for_owner(owner_user_id, book_id, run_id)
        if run is None:
            return None
        spec_art = await self._runs.latest_artifact(owner_user_id, run_id, "spec")
        if spec_art is None:
            raise ValueError("no spec to validate")
        spec = spec_art.content
        doc_art = await self._runs.latest_artifact(owner_user_id, run_id, "document")
        pkg_art = await self._runs.latest_artifact(owner_user_id, run_id, "package")
        package = pkg_art.content.get("planning_package") if pkg_art else None
        graph = build_graph(spec)
        rules_out = run_rules(spec, package)
        passed_rules = all(r["pass"] for r in rules_out)
        fidelity_score = None
        golden_rules: list[dict[str, Any]] = [
            {"id": r["rule"], "passed": r["pass"], "message": r.get("detail", "")}
            for r in rules_out
        ]
        all_pass = passed_rules
        if _FIDELITY.exists():
            try:
                fidelity_cfg = load_fidelity_config(_FIDELITY)
                fidelity = evaluate_spec_fidelity(spec, fidelity_cfg)
                fidelity_score = fidelity.get("score")
            except Exception:
                pass
        if _GOLDEN.exists() and doc_art is not None:
            try:
                golden = validate_golden(doc_art.content, spec, graph, _GOLDEN, package)
                for kid, ok in golden.get("criteria", {}).items():
                    golden_rules.append({"id": kid, "passed": ok, "message": ""})
                all_pass = golden.get("all_pass", False) and passed_rules
            except Exception:
                pass
        report = {
            "passed": all_pass,
            "rules": golden_rules,
            "fidelity_score": fidelity_score,
            "fidelity_report_id": None,
        }
        art = await self._runs.save_artifact(
            owner_user_id, run_id, "validation_report", report,
        )
        report["fidelity_report_id"] = str(art.id)
        if all_pass:
            await self._runs.update_run(owner_user_id, book_id, run_id, status="validated")
        return report

    async def refine(
        self,
        owner_user_id: UUID,
        book_id: UUID,
        run_id: UUID,
        *,
        model_ref: UUID,
        revision: dict[str, Any] | None,
        focus_paths: list[str] | None,
    ) -> tuple[str, dict[str, Any]]:
        """Returns (http_mode, body) where http_mode is 'sync' or 'async'."""
        run = await self._runs.get_for_owner(owner_user_id, book_id, run_id)
        if run is None:
            raise LookupError("run not found")
        spec_art = await self._runs.latest_artifact(owner_user_id, run_id, "spec")
        if spec_art is None:
            raise ValueError("no spec to refine")
        spec = spec_art.content
        rev = dict(revision or {})
        if focus_paths:
            rev["focus_paths"] = focus_paths
        analyze_art = await self._runs.latest_artifact(owner_user_id, run_id, "analyze")
        analyze = analyze_art.content if analyze_art else None
        pkg_art = await self._runs.latest_artifact(owner_user_id, run_id, "package")
        package = pkg_art.content.get("planning_package") if pkg_art else None

        if not rev:
            return "sync", {
                "status": "no_change",
                "spec_artifact_id": str(spec_art.id),
                "fidelity_delta": 0.0,
                "diagnosis": None,
            }

        work = await self._ensure_work(owner_user_id, book_id)
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
                owner_user_id, project_id,
                operation="plan_forge_refine", mode="auto", status="pending",
                input=pipe_input,
            )
            await enqueue_job(
                settings.redis_url, job_id=str(job.id),
                user_id=str(owner_user_id), project_id=str(project_id),
            )
            await self._runs.update_run(
                owner_user_id, book_id, run_id, active_job_id=job.id, status="checkpoint",
            )
            return "async", {"run_id": str(run_id), "job_id": str(job.id), "status": "pending"}

        if self._llm is None:
            raise RuntimeError("LLM client required when worker disabled")
        before_checksum = _spec_checksum(spec)
        result = await run_plan_forge_refine(
            self._llm, user_id=str(owner_user_id), input=pipe_input,
        )
        job, _ = await self._jobs.create(
            owner_user_id, project_id,
            operation="plan_forge_refine", mode="auto", status="completed",
            input=pipe_input, result=result,
        )
        await self.apply_job_outcome(owner_user_id, book_id, run_id, job, result)
        new_spec_art = await self._runs.latest_artifact(owner_user_id, run_id, "spec")
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
        self, owner_user_id: UUID, book_id: UUID, run_id: UUID, *, approved: bool,
    ) -> dict[str, Any] | None:
        """Advance/hold a checkpoint (M4 plan_review_checkpoint). approved=True →
        the current spec becomes `validated` intent; approved=False keeps it at
        `checkpoint` for further refinement. Idempotent, no LLM."""
        run = await self._runs.get_for_owner(owner_user_id, book_id, run_id)
        if run is None:
            return None
        spec_art = await self._runs.latest_artifact(owner_user_id, run_id, "spec")
        if spec_art is None:
            raise ValueError("no spec to review")
        await self._runs.update_run(
            owner_user_id, book_id, run_id,
            status="validated" if approved else "checkpoint",
        )
        updated = await self._runs.get_for_owner(owner_user_id, book_id, run_id)
        return await self._serialize_run(owner_user_id, updated) if updated else None

    async def handoff_autofix(
        self, owner_user_id: UUID, book_id: UUID, run_id: UUID,
        *, model_ref: UUID, max_rounds: int = 3,
    ) -> dict[str, Any] | None:
        """Batch-apply the top self-check gaps as a bounded refine loop (M4
        plan_handoff_autofix). Each round: self-check → take the ranked gaps →
        refine toward them; stop when no gaps remain or max_rounds is hit. Runs the
        refine synchronously (worker-off path); enqueues if the worker is on."""
        run = await self._runs.get_for_owner(owner_user_id, book_id, run_id)
        if run is None:
            return None
        rounds = max(1, min(int(max_rounds), 5))
        applied: list[dict[str, Any]] = []
        for i in range(rounds):
            check = await self.self_check(owner_user_id, book_id, run_id)
            gaps = (check or {}).get("gaps") or []
            top = [g for g in gaps if g.get("severity") in ("error", "warn")][:5]
            if not top:
                break
            revision = {"focus_paths": [g["path"] for g in top if g.get("path")]}
            mode, payload = await self.refine(
                owner_user_id, book_id, run_id,
                model_ref=model_ref, revision=revision, focus_paths=None,
            )
            applied.append({"round": i + 1, "targets": len(top), "result": payload.get("status")})
            if mode == "async" or payload.get("status") != "applied":
                # async enqueued (can't loop synchronously) or no progress → stop.
                break
        detail = await self.get_run_detail(owner_user_id, book_id, run_id)
        return {"rounds": applied, "run": detail}

    async def interpret(
        self,
        owner_user_id: UUID,
        book_id: UUID,
        run_id: UUID,
        *,
        user_message: str,
        model_ref: UUID,
        apply_mode_hint: str | None = None,
    ) -> dict[str, Any] | None:
        run = await self._runs.get_for_owner(owner_user_id, book_id, run_id)
        if run is None:
            return None
        spec_art = await self._runs.latest_artifact(owner_user_id, run_id, "spec")
        if spec_art is None:
            raise ValueError("no spec for interpret")
        spec = spec_art.content
        doc_art = await self._runs.latest_artifact(owner_user_id, run_id, "document")
        section_map: list[dict[str, Any]] = []
        self_check_report = None
        if _FIDELITY.exists() and doc_art is not None:
            try:
                section_map, fidelity_cfg = load_coverage_context(
                    _FIXTURES / "story-plan-v1.md", _FIDELITY,
                )
                self_check_report = run_self_check(
                    spec, _FIXTURES / "story-plan-v1.md", _FIDELITY,
                )
            except Exception:
                section_map, _ = load_coverage_context(
                    _FIXTURES / "story-plan-v1.md", _FIDELITY,
                ) if _FIDELITY.exists() else ([], {})

        if self._llm is not None:
            client = ProviderPlanForgeLLM(
                self._llm,
                user_id=str(owner_user_id),
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
        self, owner_user_id: UUID, book_id: UUID, run_id: UUID,
    ) -> dict[str, Any] | None:
        run = await self._runs.get_for_owner(owner_user_id, book_id, run_id)
        if run is None:
            return None
        spec_art = await self._runs.latest_artifact(owner_user_id, run_id, "spec")
        if spec_art is None:
            raise ValueError("no spec for self-check")
        spec = spec_art.content
        gaps: list[dict[str, Any]] = []
        fidelity_score = None
        if _FIDELITY.exists():
            try:
                report = run_self_check(spec, _FIXTURES / "story-plan-v1.md", _FIDELITY)
                fidelity_score = (report.get("fidelity") or {}).get("score")
                for g in report.get("ranked_gaps") or []:
                    gaps.append({
                        "path": g.get("id", ""),
                        "severity": g.get("severity", "warn"),
                        "message": g.get("detail", ""),
                    })
            except Exception:
                pass
        if not gaps:
            audit = consistency_audit(spec)
            for c in audit.get("critical") or []:
                gaps.append({"path": c.get("field", ""), "severity": "error", "message": c.get("issue", "")})
            for r in run_rules(spec):
                if not r["pass"]:
                    gaps.append({"path": r["rule"], "severity": "warn", "message": r.get("detail", "")})
        return {"gaps": gaps, "fidelity_score": fidelity_score}

    async def compile(
        self,
        owner_user_id: UUID,
        book_id: UUID,
        run_id: UUID,
        *,
        arc_id: str,
        run_pipeline: bool = False,
        model_ref: UUID | None = None,
    ) -> tuple[str, dict[str, Any]]:
        run = await self._runs.get_for_owner(owner_user_id, book_id, run_id)
        if run is None:
            raise LookupError("run not found")
        spec_art = await self._runs.latest_artifact(owner_user_id, run_id, "spec")
        if spec_art is None:
            raise ValueError("no spec to compile")
        spec = spec_art.content
        rules_out = run_rules(spec)
        if not all(r["pass"] for r in rules_out):
            raise ValueError("validation failed — compile blocked")

        compiled = compile_artifacts(spec, arc_id=arc_id)
        package = compiled["planning_package"]
        await self._runs.save_artifact(
            owner_user_id, run_id, "package",
            {"planning_package": package, **{k: v for k, v in compiled.items() if k != "planning_package"}},
        )
        work = await self._ensure_work(owner_user_id, book_id)
        await self._runs.update_run(
            owner_user_id, book_id, run_id,
            status="compiled", work_id=work.id,
        )
        body: dict[str, Any] = {
            "package": package,
            "pipeline_job_id": None,
            "work_id": str(work.id) if work.id else None,
        }
        if not run_pipeline:
            return "sync", body
        if model_ref is None:
            raise ValueError("model_ref required when run_pipeline=true")
        project_id = _work_project_id(work)
        pipe_input = {
            "worker_op": "plan_pipeline",
            "model_source": "user_model",
            "model_ref": str(model_ref),
            "premise": package.get("premise", ""),
            "beats": [],
            "chapters": package.get("chapters", []),
            "genre_tags": package.get("genre_tags", []),
            "book_id": str(book_id),
            "project_id": str(project_id),
            "plan_forge_package": package,
        }
        if settings.composition_worker_enabled:
            job, _ = await self._jobs.create(
                owner_user_id, project_id,
                operation="plan_pipeline", mode="auto", status="pending",
                input=pipe_input,
            )
            await enqueue_job(
                settings.redis_url, job_id=str(job.id),
                user_id=str(owner_user_id), project_id=str(project_id),
            )
            body["pipeline_job_id"] = str(job.id)
            return "async", body
        body["pipeline_preview"] = mock_pipeline_result(package)
        return "sync", body

    async def _ensure_work(self, owner_user_id: UUID, book_id: UUID) -> CompositionWork:
        import asyncpg

        marked = await self._works.resolve_by_book(owner_user_id, book_id)
        if len(marked) == 1:
            return marked[0]
        pending = await self._works.get_pending_for_book(owner_user_id, book_id)
        if pending is not None:
            return pending
        try:
            return await self._works.create_pending(owner_user_id, book_id)
        except asyncpg.UniqueViolationError:
            pending = await self._works.get_pending_for_book(owner_user_id, book_id)
            if pending is not None:
                return pending
            marked = await self._works.resolve_by_book(owner_user_id, book_id)
            if len(marked) == 1:
                return marked[0]
            raise
