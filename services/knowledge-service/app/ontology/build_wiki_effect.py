"""Confirm-effect for the cost-gated `kg_build_wiki` MCP tool (D-KG-LF-WIKI-MCP).

The MCP tool mints a `DESC_BUILD_WIKI` token (the LLM model + an optional explicit entity
subset); the human confirms via /v1/kg/actions/confirm.

  * ``preview_build_wiki`` — entity count + an estimated cost range.
  * ``apply_build_wiki`` — resolves the entity set (explicit subset, else ALL of the book's
    active glossary entities — the backend's generate path requires explicit ids), creates
    a wiki-gen job, and enqueues it. Returns the job id.

Entity resolution happens at CONFIRM (not mint) for the "all" case so the token stays small
and reflects current state. Deps (glossary client, jobs repo, redis) are built by the
confirm/preview branches, never injected into the shared route signature.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.repositories.wiki_gen_jobs import ActiveJobExists, WikiGenJobsRepo
from app.jobs.wiki_gen_enqueue import enqueue_wiki_gen
from app.pricing import cost_per_token

# A wiki article = draft generation + a corrective revise pass; ~3k tokens/entity is a
# coarse estimate for the cost CARD (shown as a ±30% range), not a billing figure.
_TOKENS_PER_WIKI_ENTITY = 3000


class BuildWikiNoEntities(Exception):
    """The book has no entities to generate wiki articles for (extract glossary first)."""


class BuildWikiActiveJob(Exception):
    """A wiki-gen job is already running for this book."""

    def __init__(self, existing_job_id: str | None):
        self.existing_job_id = existing_job_id


class BuildWikiParams(BaseModel):
    """Action-spec captured at mint. `entity_ids` empty ⇒ generate for ALL book entities
    (resolved at confirm)."""

    model_config = ConfigDict(extra="forbid")

    model_source: str = Field(default="user_model", min_length=1, max_length=40)
    model_ref: str = Field(min_length=1, max_length=200)
    entity_ids: list[str] = Field(default_factory=list)
    # D-RE-OTHER-AGENTIC-EFFORT: clamped reasoning effort (mint + confirm). Default 'none'.
    reasoning_effort: str = "none"


async def _resolve_entity_ids(params: BuildWikiParams, book_id: UUID, glossary_client) -> list[str]:
    if params.entity_ids:
        return params.entity_ids
    # Wiki wants EVERY entity of the book, not just multi-chapter ones — each
    # extracted entity has ≥1 chapter link, so min_frequency=1 includes them all
    # (the default 2 is the extraction-ANCHOR semantics and silently drops every
    # entity on a single-chapter book → spurious "no entities" → 422).
    #
    # `status_filter` is deliberately NOT "active" (it used to say so, but the
    # handler ignored the param entirely — D-GLOSSARY-KNOWN-ENTITIES-STATUS-PARAM).
    # Now that it is honored, passing "active" would empty the wiki: BOTH entity
    # creation paths insert `status='draft'`, so entities stay draft until triaged.
    # None = no status filter = the behavior this call has always actually had.
    #
    # Paged (D-ANCHOR-PRELOAD-50-CAP): the un-limited call inherited the handler's
    # silent default of 50, so a book with more entities only ever got 50 wiki stubs.
    page = await glossary_client.list_all_entities(
        book_id, status_filter=None, min_frequency=1,
    )
    if not page:
        return []
    rows, _truncated = page
    return [r["entity_id"] for r in rows if r.get("entity_id")]


async def apply_build_wiki(
    *,
    project,
    owner: UUID,
    params: BuildWikiParams,
    glossary_client,
    redis,
) -> dict:
    """Create + enqueue a wiki-gen job over the resolved entity set. Returns
    {job_id, status, entity_count}."""
    if project.book_id is None:
        raise BuildWikiNoEntities()
    entity_ids = await _resolve_entity_ids(params, project.book_id, glossary_client)
    if not entity_ids:
        raise BuildWikiNoEntities()

    from app.db.pool import get_knowledge_pool

    repo = WikiGenJobsRepo(get_knowledge_pool())
    try:
        job = await repo.create(
            user_id=owner, project_id=project.project_id, book_id=project.book_id,
            model_source=params.model_source, model_ref=params.model_ref,
            entity_ids=entity_ids, max_spend_usd=None, items_total=len(entity_ids),
            revise_model_ref=None, revise_model_source=None,
            reasoning_effort=params.reasoning_effort,
        )
    except ActiveJobExists as exc:
        raise BuildWikiActiveJob(
            str(exc.existing_job_id) if exc.existing_job_id else None
        )
    await enqueue_wiki_gen(redis, str(job.job_id))
    return {
        "started": True,
        "job_id": str(job.job_id),
        "status": "pending",
        "entity_count": len(entity_ids),
    }


async def preview_build_wiki(
    *, project, params: BuildWikiParams, glossary_client,
) -> dict:
    """Entity count + estimated cost range for the review card."""
    count = 0
    if params.entity_ids:
        count = len(params.entity_ids)
    elif project.book_id is not None:
        c = await glossary_client.count_entities(project.book_id)
        count = c or 0

    est_tokens = count * _TOKENS_PER_WIKI_ENTITY
    base = Decimal(est_tokens) * cost_per_token(params.model_ref)
    low = (base * Decimal("0.7")).quantize(Decimal("0.01"))
    high = (base * Decimal("1.3")).quantize(Decimal("0.01"))
    return {
        "descriptor": "kg_build_wiki",
        "destructive": False,
        "title": "Generate wiki articles",
        "preview_rows": [
            {"label": "entities", "value": str(count),
             "note": "all active glossary entities" if not params.entity_ids else "selected"},
            {"label": "wiki generation (PAID)", "value": f"${low}–${high}",
             "note": "estimated LLM cost (draft + revise per entity, caller-paid)"},
        ],
    }
