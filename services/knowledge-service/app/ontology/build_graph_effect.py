"""Confirm-effect for the cost-gated `kg_build_graph` MCP tool (D-KG-LF-BUILDKG-MCP).

The MCP tool mints a `DESC_BUILD_GRAPH` token (resolves the project's embedding model
+ the caller-supplied extraction LLM); the human confirms via /v1/kg/actions/confirm.

  * ``preview_build_graph`` — re-renders the human-facing card from CURRENT state: the
    item counts + an estimated cost range (same math as the REST estimate endpoint), plus
    a warning when the embedding benchmark hasn't passed (so the human doesn't confirm a
    job the gate will reject).
  * ``apply_build_graph`` — delegates to the SAME ``_start_extraction_job_core`` the REST
    start endpoint uses (no logic fork), returning the job id. The K17.9 benchmark gate +
    active-job/scope guards live in that core and surface as HTTPExceptions.

The heavy deps (jobs/benchmark repos, book client, extraction wake) are injected by the
confirm/preview routes (FastAPI DI) — the MCP tool never touches them.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.pricing import cost_per_token
from app.routers.public.extraction import (
    _SECONDS_PER_ITEM,
    _TOKENS_PER_CHAPTER,
    _TOKENS_PER_CHAT_TURN,
    _TOKENS_PER_GLOSSARY_ENTITY,
    StartJobRequest,
    _start_extraction_job_core,
)

JobScopeLiteral = ("all", "chapters", "chat", "glossary_sync")


class BuildGraphParams(BaseModel):
    """The action-spec captured at mint. Re-validated at confirm against current state."""

    model_config = ConfigDict(extra="forbid")

    scope: str = "all"
    chapter_from: int | None = Field(default=None, ge=0)
    chapter_to: int | None = Field(default=None, ge=0)
    llm_model: str = Field(min_length=1, max_length=200)
    embedding_model: str = Field(min_length=1, max_length=200)
    # D-RE-OTHER-AGENTIC-EFFORT: the clamped reasoning effort captured at mint (re-clamped at
    # confirm). Default 'none' for back-compat with tokens minted before this field.
    reasoning_effort: str = "none"


def _scope_range(params: BuildGraphParams) -> dict | None:
    if params.chapter_from is not None and params.chapter_to is not None:
        return {"chapter_range": [params.chapter_from, params.chapter_to]}
    return None


async def apply_build_graph(
    *,
    project_id: str,
    owner: UUID,
    params: BuildGraphParams,
    projects_repo,
    jobs_repo,
    benchmark_repo,
    book_client,
    extraction_wake,
    mcp_key_id: str | None = None,
    spend_cap_usd: float | None = None,
) -> dict:
    """Start the extraction job via the shared core. Returns {job_id, status, scope}.
    HTTPExceptions from the core (benchmark gate 409, active-job 409, scope 422) propagate
    to the confirm route. The owner drives the graph partition (caller=None → owner-paid)."""
    body = StartJobRequest(
        scope=params.scope,
        scope_range=_scope_range(params),
        llm_model=params.llm_model,
        embedding_model=params.embedding_model,
        reasoning_effort=params.reasoning_effort,
    )
    job = await _start_extraction_job_core(
        UUID(project_id), body, owner, projects_repo, jobs_repo, benchmark_repo,
        caller=None, book_client=book_client, extraction_wake=extraction_wake,
        mcp_key_id=mcp_key_id, spend_cap_usd=spend_cap_usd,
    )
    return {
        "started": True,
        "job_id": str(job.job_id),
        "status": getattr(job, "status", "running"),
        "scope": params.scope,
    }


async def preview_build_graph(
    *,
    project,
    params: BuildGraphParams,
    book_client,
    benchmark_repo,
    owner: UUID,
) -> dict:
    """Re-render the card: chapter count + estimated cost range + a benchmark warning.

    The estimate covers the dominant cost driver (chapter extraction); when scope also
    includes chat / glossary_sync those tails add to the real cost at run time, noted on
    the card. Keeping the preview to the book-client call (no pending/glossary deps) bounds
    the surface added to the shared confirm/preview routes."""
    scope = params.scope
    chapters = 0
    if scope in ("chapters", "all") and project.book_id is not None:
        # WS-0.6: the preview must count what the JOB will extract. The job enumerates
        # kg-indexed chapters (worker-ai runner), so a preview keyed on publish would
        # quote "0 chapters" and then the job would extract 50 — preview and job MUST
        # agree, or the cost card is a lie.
        c = await book_client.count_chapters(
            project.book_id, from_sort=params.chapter_from, to_sort=params.chapter_to,
            kg_indexed=True,
        )
        chapters = c or 0

    est_tokens = chapters * _TOKENS_PER_CHAPTER
    base = Decimal(est_tokens) * cost_per_token(params.llm_model)
    low = (base * Decimal("0.7")).quantize(Decimal("0.01"))
    high = (base * Decimal("1.3")).quantize(Decimal("0.01"))

    # Benchmark warning (the gate runs at confirm; surface it pre-confirm so the human
    # doesn't burn the token on a job the core will 409).
    benchmark_ok = True
    if project.embedding_model:
        latest = await benchmark_repo.get_latest(owner, project.project_id, project.embedding_model)
        benchmark_ok = latest is not None and latest.passed

    chapters_note = "chapter extraction"
    if scope in ("chat", "glossary_sync", "all"):
        chapters_note += " (+ chat/glossary tails added at run)"
    rows = [
        {"label": "scope", "value": scope},
        {"label": "chapters", "value": str(chapters)},
        {"label": "extraction (PAID)", "value": f"${low}–${high}",
         "note": f"estimated LLM cost — {chapters_note} (caller-paid)"},
    ]
    if not benchmark_ok:
        rows.append({
            "label": "⚠ benchmark", "value": "not passing",
            "note": "run the embedding benchmark in extraction setup first — confirm will be rejected otherwise",
        })
    return {
        "descriptor": "kg_build_graph",
        "destructive": False,
        "title": f"Build the knowledge graph ({scope})",
        "preview_rows": rows,
        "estimated_duration_seconds": chapters * _SECONDS_PER_ITEM,
        "benchmark_ok": benchmark_ok,
    }
