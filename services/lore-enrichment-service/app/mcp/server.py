"""MCP facade for lore-enrichment-service (agent-driven enrichment).

Stands up an internal ``/mcp`` server (mounted in ``app/main.py``) exposing the
auto-enrich capability as an MCP tool, so the chat agent can drive Dracula-journey
step 10 ("enrich the lore") through the assistant instead of a bespoke REST call —
the MCP-first invariant (any agentic capability is an MCP tool-call through the
gateway, never a raw-prompt HTTP endpoint).

DESIGN (mirrors the proven jobs/composition `loreweave_mcp` facades):

- **Identity from the envelope ONLY** (`build_tool_context`: X-Internal-Token
  constant-time check, then X-User-Id). This is STRICTER than the bespoke REST
  route, whose `require_principal` decodes an UNVERIFIED JWT `sub` (contract-freeze
  posture). The MCP path requires the trusted internal token before lifting the
  user, so a tool call cannot smuggle an identity past the envelope.
- **Scope = book**; the arg model is `ForbidExtra` so the LLM cannot add fields.
- **Tier A** (auto-write): auto-enrich ENQUEUES an async job that only ever
  produces QUARANTINED proposals (H0 — nothing lands in canon without human
  promotion) and is cost-bounded (`max_spend_tokens` + the per-job cap). It is NOT a
  destructive/canon write, so it does not need the confirm-token (Tier-W) gate.

The tool delegates to the EXISTING REST handler (`app.api.gaps.auto_enrich`) with a
synthetic `Principal` built from the envelope identity — zero logic duplication; the
detect→top-N→create-job→enqueue path is reused verbatim.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import HTTPException
from mcp.server.fastmcp import Context as MCPContext

from loreweave_mcp import (
    ForbidExtra,
    ToolContext,
    build_tool_context,
    make_stateless_fastmcp,
    require_meta,
)

from app.api.gaps import AutoEnrichBody, AutoEnrichTarget, auto_enrich
from app.api.principal import Principal
from app.clients.grant_client import get_grant_client
from app.config import settings
from app.db.pool import get_pool

logger = logging.getLogger(__name__)

__all__ = ["mcp_server", "build_mcp_app"]

mcp_server = make_stateless_fastmcp("lore-enrichment")


def _ctx(ctx: MCPContext) -> ToolContext:
    """Validate the internal token + lift the envelope identity. A bad token /
    missing header surfaces as a tool error (success=False), not a 5xx."""
    return build_tool_context(ctx, settings.internal_service_token)


class _AutoEnrichArgs(ForbidExtra):
    book_id: str
    embedding_model_ref: str
    generation_model_ref: str
    technique: str = "retrieval"
    max_gaps: int = 10
    coverage_limit: int = 200
    max_spend_tokens: float | None = None
    eval_reserve_fraction: float = 0.15
    top_k: int = 5
    # Optional explicit gaps to enrich (the per-row "enrich →"); omit to auto-detect
    # the top-N under-described entities. Each item: {canonical_name, target_ref?,
    # entity_kind?, mention_count?, present_dimensions?}.
    targets: list[dict[str, Any]] | None = None


@mcp_server.tool(
    name="lore_enrichment_auto_enrich",
    description=(
        "Auto-enrich a book's lore: detect under-described glossary entities (gaps) "
        "and enqueue a background job that drafts enrichment for the top-N — grounded "
        "in the book's own text. Returns the job id immediately (async). Every "
        "generated proposal is QUARANTINED for human review (nothing lands in canon "
        "automatically); spend is bounded by max_spend_tokens. Requires the book to have "
        "been extracted first (it enriches existing entities). Pass `targets` to "
        "enrich specific entities instead of the auto-detected top-N."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["auto enrich", "enrich lore", "fill gaps", "enrich entities",
                  "lore enrichment", "deepen lore", "flesh out entities", "enrich"],
        async_job=True,
        tool_name="lore_enrichment_auto_enrich",
    ),
)
async def lore_enrichment_auto_enrich(
    ctx: MCPContext,
    project_id: Annotated[str, "The enrichment project id (= the knowledge project id)."],
    args: _AutoEnrichArgs,
) -> dict:
    tc = _ctx(ctx)
    try:
        targets = (
            [AutoEnrichTarget(**t) for t in args.targets] if args.targets else None
        )
        body = AutoEnrichBody(
            book_id=UUID(args.book_id),
            embedding_model_ref=UUID(args.embedding_model_ref),
            generation_model_ref=UUID(args.generation_model_ref),
            technique=args.technique,
            max_gaps=args.max_gaps,
            coverage_limit=args.coverage_limit,
            max_spend_tokens=args.max_spend_tokens,
            eval_reserve_fraction=args.eval_reserve_fraction,
            top_k=args.top_k,
            targets=targets,
        )
    except (ValueError, TypeError) as exc:
        return {"success": False, "error": f"invalid argument: {exc}"}

    # Reuse the REST handler verbatim with the envelope identity. It raises
    # HTTPException on a bad technique (400) or an upstream glossary error (502/503);
    # surface those as a structured tool refusal (not a raised 5xx).
    # NOTE: `auto_enrich` is called as a plain function here (not via FastAPI DI), so
    # its `Depends(...)` defaults are NOT resolved — every dependency it needs MUST be
    # passed explicitly. The grant gate (D-ENRICH-MCP-OWNER-GATE) therefore requires
    # `grants=get_grant_client()`; omitting it would pass a `Depends` sentinel and the
    # gate would AttributeError. The MCP envelope identity (tc.user_id, trusted via the
    # internal token) is the subject the grant is resolved for.
    try:
        result = await auto_enrich(
            UUID(project_id), body,
            principal=Principal(user_id=tc.user_id),
            pool=get_pool(),
            grants=get_grant_client(),
        )
    except HTTPException as exc:
        return {"success": False, "error": str(exc.detail), "status": exc.status_code}
    return result


def build_mcp_app():
    """Return the ASGI app to mount at ``/mcp`` in ``main.py``. The session manager
    is run in main.py's lifespan (a mounted sub-app's lifespan is not auto-run)."""
    return mcp_server.streamable_http_app()
