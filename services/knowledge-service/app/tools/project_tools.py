"""Knowledge-project lifecycle MCP tool (D-KG-LF-PROJECT-CREATE-MCP).

`kg_project_create` lets an agent stand up the knowledge project that anchors a
book's KG + memory — the prerequisite the KG schema / extraction / wiki tools all
need ("the current project"). Mirrors ``POST /v1/knowledge/projects`` exactly:

  * a book-bound project (book_id set) is **book-OWNER-only** — grant-gated with
    no existence oracle (a non-owner gets the same generic refusal as a missing
    book), matching `create_project`'s `resolve_grant(book_id) != OWNER → 404`;
  * a book-less project is a personal project the caller owns;
  * idempotent on the book-binding path (`create_or_get`) — a repeat call returns
    the existing project (created=False) instead of a duplicate.

Class-W: additive and reversible (delete the project), low-impact, no LLM cost —
so it writes directly and returns the new project_id, with no confirm-token. The
agent then uses that project_id (via the X-Project-Id envelope) for the class-C
schema-authoring tools, extraction, and wiki generation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from loreweave_grants import GrantLevel
from pydantic import BaseModel, ConfigDict, Field

from app.db.models import ProjectCreate, ProjectType
from app.tools.argbase import ProjectScopedArgs

if TYPE_CHECKING:
    from app.tools.executor import ToolContext


class KgProjectCreateArgs(BaseModel):
    """`kg_project_create` — class-W. Create (or get) the knowledge project that
    anchors a book's KG/memory. Book-bound create is book-owner-only; book-less is
    a personal project. Idempotent per (user, book)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    project_type: ProjectType = "book"
    book_id: str | None = Field(
        default=None,
        description="Link the project to this book (book-owner only). Omit for a personal project.",
    )
    description: str = Field(default="", max_length=2000)
    genre: str | None = Field(default=None, max_length=100)


async def _handle_kg_project_create(ctx: "ToolContext", args: KgProjectCreateArgs) -> dict:
    """W (direct, reversible). Replicates ``create_project``: book-owner gate for a
    book-bound project (no oracle), then ``create_or_get`` (idempotent per
    (user, book)). Returns the project_id the caller then puts in X-Project-Id."""
    from app.tools.executor import ToolExecutionError

    book_uuid: UUID | None = None
    if args.book_id:
        try:
            book_uuid = UUID(args.book_id)
        except (ValueError, TypeError):
            raise ToolExecutionError("book_id must be a valid id")
        # Book-bound create is book-OWNER-only — same generic refusal as a missing
        # book (no existence oracle), mirroring the REST create_project gate.
        lvl = await ctx.grant_client.resolve_grant(book_uuid, ctx.user_id)
        if lvl != GrantLevel.OWNER:
            raise ToolExecutionError(
                "only the book's owner can create a knowledge project for it"
            )

    body = ProjectCreate(
        name=args.name,
        project_type=args.project_type,
        book_id=book_uuid,
        description=args.description,
        genre=args.genre,
    )
    project, created = await ctx.projects_repo.create_or_get(ctx.user_id, body)
    return {
        "project_id": str(project.project_id),
        "name": project.name,
        "project_type": project.project_type,
        "book_id": str(project.book_id) if project.book_id else None,
        "created": created,
        "note": (
            "set this project_id as the active project (X-Project-Id) for the KG "
            "schema, extraction, and wiki tools"
        ),
    }


class KgProjectListArgs(BaseModel):
    """`kg_project_list` — Tier R. List the caller's OWN knowledge projects, so an
    agent can discover a `project_id` when no project is in scope (W0 #4a: the
    "no project in scope" error directs the model here)."""

    model_config = ConfigDict(extra="forbid")

    include_archived: bool = False
    limit: int = Field(default=20, ge=1, le=50)


async def _handle_kg_project_list(ctx: "ToolContext", args: KgProjectListArgs) -> dict:
    # @small_return: each project is a compact metadata ref (id/name/type/book/
    # archived) — no heavy body — and the set is owner-scoped + hard-capped by
    # `limit` (≤50) with a `more` flag, so it is not SET-bloat (spec §6b exemption).
    """R (read). Owner-scoped by the envelope identity — the repo filters
    `user_id = ctx.user_id`, so the caller only ever sees their own projects
    (public MCP keys included: owned-only, no grant traversal)."""
    projects = await ctx.projects_repo.list(
        ctx.user_id, include_archived=args.include_archived, limit=args.limit
    )
    more = len(projects) > args.limit  # the repo fetches limit+1 to signal more
    return {
        "projects": [
            {
                "project_id": str(p.project_id),
                "name": p.name,
                "project_type": p.project_type,
                "book_id": str(p.book_id) if p.book_id else None,
                "is_archived": p.is_archived,
            }
            for p in projects[: args.limit]
        ],
        "more": more,
        "note": "pass a project_id to a project-scoped kg_* tool to act on that project",
    }


class KgProjectSetEmbeddingModelArgs(ProjectScopedArgs):
    """`kg_project_set_embedding_model` — Tier A. Configure the project's embedding
    model, the precondition `kg_run_benchmark` and `kg_build_graph` both require."""

    embedding_model: str = Field(
        min_length=1,
        description=(
            "The provider-registry user_model UUID of an EMBEDDING model you own. "
            "List your models with settings_list_models and pick one whose "
            "capability_flags include embedding."
        ),
    )


async def _handle_kg_project_set_embedding_model(
    ctx: "ToolContext", args: KgProjectSetEmbeddingModelArgs
) -> dict:
    """A (direct, reversible). Mirrors ``PATCH /v1/knowledge/projects/{id}``'s
    embedding_model branch, minus the destructive re-embed path.

    This closes the agent-native gap that made `kg_build_graph` unreachable: an agent
    could create a project (kg_project_create), benchmark it (kg_run_benchmark), and
    build its graph (kg_build_graph) — but the ONE step between create and benchmark,
    setting the embedding model, existed only as a REST route behind a GUI dialog. So
    every agent-created project dead-ended at "run extraction setup once in the Build
    Knowledge Graph dialog", an instruction a tool-calling model cannot act on.

    Deliberately SET-ON-UNSET (plus same-value no-op). CHANGING the model on a project
    that already has a graph would orphan its passages — they stay in Neo4j tagged with
    the old model UUID while Mode-3 retrieval queries the new vector space: silent
    zero-recall (D-EMB-MODEL-REF-04). That path deletes vectors, so it stays a
    confirm-gated REST operation and this Tier-A tool refuses it by name.
    """
    from app.db.models import ProjectUpdate
    from app.db.neo4j_repos.passages import SUPPORTED_PASSAGE_DIMS
    from app.tools.executor import ToolExecutionError
    from app.tools.graph_schema_tools import _resolve_project_owner_and_level

    from app.clients.embedding_client import EmbeddingError, probe_embedding_dimension

    # EDIT mirrors kg_build_graph's gate; the repo update is owner-scoped, so a
    # collaborator resolves the grant but still cannot write the row (no oracle).
    owner, _level = await _resolve_project_owner_and_level(ctx, GrantLevel.EDIT)
    if ctx.user_id != owner:
        raise ToolExecutionError(
            "only the project's owner can set its embedding model"
        )
    assert ctx.project_id is not None  # _resolve_* raises when it is None

    current = await ctx.projects_repo.get(owner, ctx.project_id)
    if current is None:
        raise ToolExecutionError("project not found")

    if current.embedding_model == args.embedding_model:
        return {
            "project_id": str(ctx.project_id),
            "embedding_model": current.embedding_model,
            "embedding_dimension": current.embedding_dimension,
            "changed": False,
            "note": "already configured — next call kg_run_benchmark, then kg_build_graph",
        }

    if current.embedding_model and current.extraction_status != "disabled":
        raise ToolExecutionError(
            "this project already has a graph built with a different embedding model; "
            "changing it would orphan the existing passages (silent zero-recall). That "
            "requires deleting the stale vectors first, which is a confirm-gated "
            "operation: PUT /v1/knowledge/projects/{project_id}/embedding-model?confirm=true"
        )

    # The caller never knows the vector dimension — probe the model for it (the REST
    # route does the same). A probe failure means the ref is unreachable or is not an
    # embedding model at all.
    try:
        dim = await probe_embedding_dimension(owner, args.embedding_model)
    except EmbeddingError as exc:
        raise ToolExecutionError(
            f"embedding model probe failed: {exc} — check the model_ref is one of your "
            "own embedding models (settings_list_models)"
        )
    if dim not in SUPPORTED_PASSAGE_DIMS:
        raise ToolExecutionError(
            f"embedding model has dimension {dim}, which has no :Passage vector index "
            f"(supported: {sorted(SUPPORTED_PASSAGE_DIMS)})"
        )

    updated = await ctx.projects_repo.update(
        owner,
        ctx.project_id,
        ProjectUpdate(embedding_model=args.embedding_model, embedding_dimension=dim),
    )
    if updated is None:
        raise ToolExecutionError("project not found")
    return {
        "project_id": str(ctx.project_id),
        "embedding_model": updated.embedding_model,
        "embedding_dimension": updated.embedding_dimension,
        "changed": True,
        "note": "next call kg_run_benchmark (required, cheap), then kg_build_graph",
    }


PROJECT_TOOL_ARG_MODELS: dict[str, type[BaseModel]] = {
    "kg_project_create": KgProjectCreateArgs,
    "kg_project_list": KgProjectListArgs,
    "kg_project_set_embedding_model": KgProjectSetEmbeddingModelArgs,
}

PROJECT_TOOL_HANDLERS = {
    "kg_project_create": _handle_kg_project_create,
    "kg_project_list": _handle_kg_project_list,
    "kg_project_set_embedding_model": _handle_kg_project_set_embedding_model,
}
