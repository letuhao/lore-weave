"""Cost-gated job-trigger MCP tools (D-KG-LF-BUILDKG-MCP / D-KG-LF-WIKI-MCP).

`kg_build_graph` lets an agent start an extraction job ("build the knowledge graph")
over a book's chapters. It is EXPENSIVE + irreversible spend, so it follows the KM6
propose→confirm spine: this handler MINTS a `DESC_BUILD_GRAPH` confirm-token (resolving
the project's stored embedding model + the caller-supplied extraction LLM) — it starts
NOTHING. The human redeems the token via POST /v1/kg/actions/confirm (browser-JWT), where
the confirm route's effect runs the real job; the review card shows the cost estimate.

Model resolution (the reason this isn't a blind direct trigger): the embedding model comes
from the project (`project.embedding_model`, the canonical stored column — same source the
campaign/internal-dispatch path uses); the extraction LLM is a required arg the agent picks
via settings_list_models (there is no reliable project-stored LLM default). The K17.9
benchmark gate is enforced at confirm (and warned in the preview card).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import ConfigDict, Field

from app.config import settings
from app.ontology.confirm import (
    ACTION_TOKEN_TTL_S,
    AUTH_GRANT,
    DESC_BUILD_GRAPH,
    DESC_BUILD_WIKI,
    ActionClaims,
    mint_action_token,
)
from app.effort import clamp_effort_to_grant
from app.tools.argbase import ProjectScopedArgs
from app.tools.graph_schema_tools import (
    GrantLevel,
    _resolve_project_owner,
    _resolve_project_owner_and_level,
)

_EFFORT_DESC = ("Reasoning effort for the build LLM: none|low|medium|high (paid compute; "
                "clamped to your grant — Edit caps at medium, Manage/owner at high).")

if TYPE_CHECKING:
    from app.tools.executor import ToolContext


class KgBuildGraphArgs(ProjectScopedArgs):
    """`kg_build_graph` — class-C cost gate. Start an extraction job over the project's
    book. Mints a confirm-token (no spend until a human confirms)."""

    model_config = ConfigDict(extra="forbid")

    llm_model: str = Field(
        min_length=1,
        max_length=200,
        description="The extraction LLM model ref (from settings_list_models).",
    )
    scope: Literal["all", "chapters", "chat", "glossary_sync"] = "all"
    chapter_from: int | None = Field(default=None, ge=0)
    chapter_to: int | None = Field(default=None, ge=0)
    reasoning_effort: Literal["none", "low", "medium", "high"] = Field(
        default="none", description=_EFFORT_DESC)


async def _handle_kg_build_graph(ctx: "ToolContext", args: KgBuildGraphArgs) -> dict:
    """C (confirm-token). Resolve owner (EDIT) + the project's embedding model, then mint
    a DESC_BUILD_GRAPH token. NO job starts here — the human confirms via the review
    surface, where the cost estimate is shown and the job is started."""
    from app.tools.executor import ToolExecutionError

    # EDIT to start extraction (mirrors the REST start route). Resolve owner + the caller's
    # grant LEVEL so the paid reasoning effort can be clamped to their ceiling (INV-T11).
    owner, level = await _resolve_project_owner_and_level(ctx, GrantLevel.EDIT)
    project = await ctx.projects_repo.get(owner, ctx.project_id)
    if project is None:
        raise ToolExecutionError("project not found")
    if not project.embedding_model:
        # An agent cannot open a dialog. This error string is the ONLY instruction a
        # tool-calling model gets here, so it must name the tools that unblock it, in
        # order (F6 — Track D liveness eval; same discipline as kg_run_benchmark's
        # "call this ... instead of sending the user to the UI").
        raise ToolExecutionError(
            "this project has no embedding model configured — call "
            "kg_project_set_embedding_model first (pick one of your embedding models "
            "with settings_list_models), then kg_run_benchmark, then retry this build"
        )

    # D-RE-OTHER-AGENTIC-EFFORT: clamp the requested effort to the caller's grant at MINT
    # (re-clamped again at confirm against a fresh grant). Store the clamped value in the token.
    effort, _capped = clamp_effort_to_grant(args.reasoning_effort, level)
    params = {
        "scope": args.scope,
        "chapter_from": args.chapter_from,
        "chapter_to": args.chapter_to,
        "llm_model": args.llm_model,
        "embedding_model": project.embedding_model,
        "reasoning_effort": effort,
    }
    token = mint_action_token(
        settings.jwt_secret,
        ActionClaims(
            jti=str(uuid4()),
            authority=AUTH_GRANT,
            user_id=str(ctx.user_id),
            descriptor=DESC_BUILD_GRAPH,
            project_id=str(ctx.project_id),
            params=params,
        ),
        time.time(),
    )
    if not token:
        raise ToolExecutionError("could not mint a confirmation token")

    return {
        "proposed": True,
        "confirm_token": token,
        "expires_in_s": ACTION_TOKEN_TTL_S,
        "descriptor": DESC_BUILD_GRAPH,
        "summary": f"build the knowledge graph (scope={args.scope})",
        "requires": "human confirmation via the review surface — the card shows the cost "
                    "estimate; nothing is spent until confirmed",
    }


class KgBuildWikiArgs(ProjectScopedArgs):
    """`kg_build_wiki` — class-C cost gate. Generate wiki articles for the project's book
    entities. Mints a confirm-token (no spend until a human confirms)."""

    model_config = ConfigDict(extra="forbid")

    model_ref: str = Field(
        min_length=1,
        max_length=200,
        description="The wiki-generation LLM model ref (from settings_list_models).",
    )
    model_source: str = Field(default="user_model", max_length=40)
    entity_ids: list[str] | None = Field(
        default=None,
        max_length=2000,
        description="Optional explicit entity ids; omit to generate for ALL book entities.",
    )
    reasoning_effort: Literal["none", "low", "medium", "high"] = Field(
        default="none", description=_EFFORT_DESC)


async def _handle_kg_build_wiki(ctx: "ToolContext", args: KgBuildWikiArgs) -> dict:
    """C (confirm-token). Resolve owner (EDIT) + the project's book, then mint a
    DESC_BUILD_WIKI token. NO job starts here — the human confirms via the review surface
    (which shows the entity count + cost), where the entity set is resolved + the job runs."""
    from app.tools.executor import ToolExecutionError

    owner, level = await _resolve_project_owner_and_level(ctx, GrantLevel.EDIT)
    project = await ctx.projects_repo.get(owner, ctx.project_id)
    if project is None:
        raise ToolExecutionError("project not found")
    if project.book_id is None:
        raise ToolExecutionError(
            "this project has no linked book — wiki articles are generated for a book's entities"
        )

    # D-RE-OTHER-AGENTIC-EFFORT: clamp the paid reasoning effort to the caller's grant at mint.
    effort, _capped = clamp_effort_to_grant(args.reasoning_effort, level)
    params = {
        "model_source": args.model_source,
        "model_ref": args.model_ref,
        "entity_ids": args.entity_ids or [],
        "reasoning_effort": effort,
    }
    token = mint_action_token(
        settings.jwt_secret,
        ActionClaims(
            jti=str(uuid4()),
            authority=AUTH_GRANT,
            user_id=str(ctx.user_id),
            descriptor=DESC_BUILD_WIKI,
            project_id=str(ctx.project_id),
            params=params,
        ),
        time.time(),
    )
    if not token:
        raise ToolExecutionError("could not mint a confirmation token")

    scope_note = "selected entities" if args.entity_ids else "all book entities"
    return {
        "proposed": True,
        "confirm_token": token,
        "expires_in_s": ACTION_TOKEN_TTL_S,
        "descriptor": DESC_BUILD_WIKI,
        "summary": f"generate wiki articles ({scope_note})",
        "requires": "human confirmation via the review surface — the card shows the entity "
                    "count + cost estimate; nothing is spent until confirmed",
    }


class KgRunBenchmarkArgs(ProjectScopedArgs):
    """`kg_run_benchmark` — R4 (D-JOURNEY-KG-BENCHMARK-UX). Run the K17.9 golden-set
    embedding benchmark for the project's configured embedding model. No args — the
    model is read from the project; the run executes on a hidden sandbox (so it never
    touches the real graph), and a pass enables Build-KG for that model."""

    model_config = ConfigDict(extra="forbid")


async def _handle_kg_run_benchmark(ctx: "ToolContext", args: KgRunBenchmarkArgs) -> dict:
    """Direct action (NOT cost-gated — embeddings-only, ~$0). The agent calls this when
    `kg_build_graph`'s preview shows '⚠ benchmark not passing', instead of dead-ending
    into the FE. Owner-only (mirrors the REST benchmark-run route). Runs on the hidden
    per-(user, model) sandbox via the same orchestration the REST endpoint uses, so it
    can't trip not_benchmark_project and never pollutes the real graph (R1)."""
    from app.benchmark.runner import (
        BenchmarkAlreadyRunningError,
        FixtureLoadIncompleteError,
        NotBenchmarkProjectError,
        UnknownEmbeddingModelError,
        run_project_benchmark,
    )
    from app.db.pool import get_knowledge_pool
    from app.tools.executor import ToolExecutionError

    owner = await _resolve_project_owner(ctx, GrantLevel.OWNER)
    project = await ctx.projects_repo.get(owner, ctx.project_id)
    if project is None:
        raise ToolExecutionError("project not found")
    if not project.embedding_model or not project.embedding_dimension:
        raise ToolExecutionError(
            "this project has no embedding model configured — set one first"
        )
    sandbox = await ctx.projects_repo.get_or_create_benchmark_sandbox(
        owner, project.embedding_model, project.embedding_dimension,
    )
    try:
        result = await run_project_benchmark(
            user_id=owner,
            project_id=sandbox.project_id,
            runs=3,  # the runner clamps up to min_runs anyway (R3)
            pool=get_knowledge_pool(),
            projects_repo=ctx.projects_repo,
            embedding_client=ctx.embedding_client,
        )
    except (UnknownEmbeddingModelError, NotBenchmarkProjectError) as e:
        raise ToolExecutionError(str(e))
    except BenchmarkAlreadyRunningError:
        raise ToolExecutionError("a benchmark is already running for this model — retry shortly")
    except FixtureLoadIncompleteError:
        raise ToolExecutionError(
            "the embedding provider returned an incomplete fixture (provider flake) — retry"
        )

    return {
        "passed": result.passed,
        "embedding_model": result.embedding_model,
        "recall_at_3": result.recall_at_3,
        "mrr": result.mrr,
        "runs": result.runs,
        "gate_failures": list(result.gate_failures),
        "summary": (
            "benchmark PASSED — Build Knowledge Graph is now enabled for this embedding model"
            if result.passed
            else f"benchmark did NOT pass (gate_failures={list(result.gate_failures)})"
        ),
    }


BUILD_TOOL_ARG_MODELS: dict[str, type[BaseModel]] = {
    "kg_build_graph": KgBuildGraphArgs,
    "kg_build_wiki": KgBuildWikiArgs,
    "kg_run_benchmark": KgRunBenchmarkArgs,
}

BUILD_TOOL_HANDLERS = {
    "kg_build_graph": _handle_kg_build_graph,
    "kg_build_wiki": _handle_kg_build_wiki,
    "kg_run_benchmark": _handle_kg_run_benchmark,
}
