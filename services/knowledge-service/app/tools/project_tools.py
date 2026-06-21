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


PROJECT_TOOL_ARG_MODELS: dict[str, type[BaseModel]] = {
    "kg_project_create": KgProjectCreateArgs,
}

PROJECT_TOOL_HANDLERS = {
    "kg_project_create": _handle_kg_project_create,
}
