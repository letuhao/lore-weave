"""P3 D-P3-INDEX-PRUNE-ENDPOINT — admin maintenance endpoints.

Hosts cross-service admin/janitor ops that don't fit any single
extraction-domain router. Today: prune orphaned summary vector indexes
from Neo4j (created lazily by `ensure_summary_indexes` per
(project, embedding_model) pair; orphaned when the project's selection
changes OR the project is deleted).

Authentication: X-Internal-Token (service-to-service).
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Literal

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from uuid import UUID

from app.config import settings
from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.passages import delete_all_passages_for_project
from app.db.repositories.projects import ProjectsRepo
from app.db.neo4j_helpers import (
    drop_summary_index,
    list_summary_vector_indexes,
)
from app.db.pool import get_knowledge_pool
from app.metrics import knowledge_extraction_filter_reload_total
from app.middleware.internal_auth import require_internal_token

from loreweave_extraction import (
    FILTER_CONFIG_REDIS_KEY,
    PrecisionFilterConfig,
    delete_filter_config,
    set_filter_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal/admin",
    tags=["Internal", "Admin"],
    dependencies=[Depends(require_internal_token)],
)


@router.delete("/assistant/erase")
async def erase_assistant_knowledge(
    user_id: UUID = Query(...),
    project_id: UUID = Query(...),
) -> dict:
    """D-R27 (human-authorized erasure) — delete a user's ASSISTANT knowledge project + its ENTIRE
    semantic index. Removes every `:Passage` node for (user, project) in Neo4j AND the
    `knowledge_projects` row (Postgres, owner-scoped + summary cascade in one tx). Both stores are
    tenant-scoped on (user_id, project_id), so this can only reach the caller's own project.

    ORDER (erase review MED-3): the Neo4j passages are deleted FIRST, the PG project row LAST. The
    project_id is what identifies the passages, so if we deleted the PG row first and the Neo4j delete
    then failed, a re-erase would get-or-create a DIFFERENT project_id and the orphaned passages (raw
    diary text) would never be reclaimed. Deleting Neo4j first means a failure leaves the PG project
    intact → a re-erase re-resolves the SAME project_id → retries the passage delete. Internal-token."""
    pool = get_knowledge_pool()
    async with neo4j_session() as session:
        passages_deleted = await delete_all_passages_for_project(
            session, user_id=str(user_id), project_id=str(project_id),
        )
    project_deleted = await ProjectsRepo(pool).delete(user_id, project_id)
    return {"project_deleted": bool(project_deleted), "passages_deleted": passages_deleted}


class _DiaryFactIn(BaseModel):
    kind: str
    text: str


class _QueueDiaryFactsIn(BaseModel):
    user_id: UUID
    book_id: UUID
    entry_date: str | None = None
    facts: list[_DiaryFactIn]


@router.post("/assistant/queue-facts")
async def queue_diary_facts(body: _QueueDiaryFactsIn) -> dict:
    """WS-2.1/2.3 — the assistant's DIVERT-TO-INBOX fact write. A distilled day's facts are queued into
    the pending-facts INBOX (never `pending_validation=False`; the diary's facts are human-gated, D4),
    resolving the user's assistant project by (user, book). Each fact lands as `fact_type='statement'`
    with the kind + entry_date encoded in `fact_text`; `session_id` is None (a diary fact has no chat
    session — WS-2.1 made the column nullable). Internal-token. The structured s/p/o + dedup key are
    WS-2.2; a re-distill of the same day re-queues (dedup lands with WS-2.2)."""
    pool = get_knowledge_pool()
    project, _ = await ProjectsRepo(pool).get_or_create_assistant_project(body.user_id, body.book_id)
    queued = 0
    async with pool.acquire() as conn:
        for f in body.facts:
            text = (f.text or "").strip()
            if not text:
                continue
            date_sfx = f" ({body.entry_date})" if body.entry_date else ""
            fact_text = f"[{(f.kind or 'event').strip()}] {text}{date_sfx}"
            # WS-2.2 dedup — a stable key over (project, fact_text) so a re-distill of the SAME day
            # doesn't duplicate the fact in the inbox. ON CONFLICT DO NOTHING repeats the partial
            # index's predicate (memory: an ON CONFLICT must match the partial-unique's WHERE).
            dedup_key = hashlib.sha256(f"{project.project_id}:{fact_text}".encode("utf-8")).hexdigest()
            row = await conn.fetchrow(
                """
                INSERT INTO knowledge_pending_facts
                  (user_id, project_id, session_id, fact_type, fact_text, dedup_key)
                VALUES ($1, $2, NULL, 'statement', $3, $4)
                ON CONFLICT (user_id, project_id, dedup_key) WHERE dedup_key IS NOT NULL
                DO NOTHING
                RETURNING pending_fact_id
                """,
                body.user_id, project.project_id, fact_text, dedup_key,
            )
            if row is not None:  # None ⇒ a duplicate was skipped
                queued += 1
    return {"queued": queued, "project_id": str(project.project_id)}


class OrphanIndex(BaseModel):
    """One orphaned summary vector index. `reason` distinguishes the two
    classes (project_deleted vs embedding_model_changed) so an operator
    can audit before approving a non-dry-run prune."""
    index_name: str
    level: Literal["chapter", "part", "book"]
    project_id: str            # 32-hex (no dashes — as stored in the index name)
    embedding_model_uuid: str  # 32-hex
    reason: Literal["project_deleted", "embedding_model_changed", "project_model_unset"]


class PruneSummaryIndexesResponse(BaseModel):
    """Result envelope.

    `dry_run=True` → orphans listed, no DROP fired. `dry_run=False` →
    orphans dropped (idempotent; tolerates concurrent drops).
    """
    dry_run: bool
    total_summary_indexes: int
    orphan_indexes: list[OrphanIndex]
    dropped_count: int  # always 0 when dry_run=True


@router.post(
    "/summary-indexes/prune",
    response_model=PruneSummaryIndexesResponse,
    summary="P3 — prune orphaned per-(project, embedding_model) summary vector indexes",
    description=(
        "Enumerates Neo4j summary vector indexes (created lazily by "
        "`ensure_summary_indexes` on first summary write for a project + "
        "embedding_model pair); flags any whose namespace no longer matches "
        "an active project selection. Default `dry_run=true` returns the "
        "orphan list without dropping. Set `dry_run=false` to actually DROP. "
        "Orphan reasons: `project_deleted` (no row in knowledge_projects), "
        "`embedding_model_changed` (project's current embedding_model differs "
        "from the index's), `project_model_unset` (project exists but "
        "embedding_model column is NULL — indexes unusable for Mode-3 query)."
    ),
)
async def prune_summary_indexes(
    dry_run: bool = Query(
        default=True,
        description="When true (default), only enumerate orphans. When false, DROP them.",
    ),
) -> PruneSummaryIndexesResponse:
    # 1. Enumerate all summary vector indexes from Neo4j.
    async with neo4j_session() as session:
        indexes = await list_summary_vector_indexes(session)

        if not indexes:
            return PruneSummaryIndexesResponse(
                dry_run=dry_run,
                total_summary_indexes=0,
                orphan_indexes=[],
                dropped_count=0,
            )

        # 2. Resolve current embedding_model per project (hex without dashes).
        #    Single batched query keyed on the hex form so the index parser
        #    output joins directly.
        unique_proj_hex = {idx["project_id"] for idx in indexes}
        current_models = await _current_embedding_models(unique_proj_hex)

        # 3. Classify each index.
        orphans: list[OrphanIndex] = []
        for idx in indexes:
            proj_hex = idx["project_id"]
            emb_hex = idx["embedding_model_uuid"]
            current = current_models.get(proj_hex, _SENTINEL_MISSING)
            if current is _SENTINEL_MISSING:
                reason = "project_deleted"
            elif current is None:
                reason = "project_model_unset"
            elif current != emb_hex:
                reason = "embedding_model_changed"
            else:
                continue  # active — keep
            orphans.append(OrphanIndex(
                index_name=idx["name"],
                level=idx["level"],  # type: ignore[arg-type]
                project_id=proj_hex,
                embedding_model_uuid=emb_hex,
                reason=reason,  # type: ignore[arg-type]
            ))

        # 4. Drop if requested. Idempotent — `DROP INDEX … IF EXISTS`.
        dropped = 0
        if not dry_run:
            for orphan in orphans:
                await drop_summary_index(session, orphan.index_name)
                dropped += 1

    logger.info(
        "p3 admin prune-summary-indexes dry_run=%s total=%d orphans=%d dropped=%d",
        dry_run, len(indexes), len(orphans), dropped,
    )
    return PruneSummaryIndexesResponse(
        dry_run=dry_run,
        total_summary_indexes=len(indexes),
        orphan_indexes=orphans,
        dropped_count=dropped,
    )


# Sentinel distinguishing "project row missing" from "project row exists
# but embedding_model column is NULL" — both are orphans but the operator
# audit needs different reasons.
_SENTINEL_MISSING: object = object()


async def _current_embedding_models(
    proj_hex_set: set[str],
) -> dict[str, str | None]:
    """Return {project_id_hex: embedding_model_hex_or_None} for every
    proj_hex in `proj_hex_set` that exists in knowledge_projects.

    Missing projects are absent from the dict (caller distinguishes via
    `_SENTINEL_MISSING`). knowledge_projects.embedding_model is the
    provider-registry user_model UUID with hyphens; we strip them so the
    output matches the index name's `e<32hex>` segment.
    """
    pool = get_knowledge_pool()
    rows = await pool.fetch(
        """
        SELECT
            REPLACE(LOWER(project_id::text), '-', '') AS proj_hex,
            REPLACE(LOWER(embedding_model::text), '-', '') AS emb_hex
        FROM knowledge_projects
        WHERE REPLACE(LOWER(project_id::text), '-', '') = ANY($1::text[])
        """,
        list(proj_hex_set),
    )
    result: dict[str, str | None] = {}
    for row in rows:
        emb = row["emb_hex"]
        # embedding_model is nullable; REPLACE(NULL, ...) = NULL → preserve.
        result[row["proj_hex"]] = emb if emb else None
    return result


# ─────────────────────────────────────────────────────────────────────
# Cycle 73f — runtime precision-filter reload
# ─────────────────────────────────────────────────────────────────────


class FilterReloadRequest(BaseModel):
    """Cycle 73f request body for /internal/admin/precision-filter/reload.

    Either ``disable=true`` OR ``model_ref`` is required. Both being set
    is a 422 (silent precedence is a footgun). All other fields optional;
    omitted = PrecisionFilterConfig dataclass defaults.

    `categories` excludes "fact" — facts intentionally not in cycle 73f
    scope (see cycle 72 spec D2 + pass2_filter.Category Literal).
    """
    model_ref: str | None = Field(default=None, min_length=1, max_length=200)
    model_source: Literal["user_model", "platform_model"] | None = None
    partial_policy: Literal["keep", "drop"] | None = None
    categories: list[Literal["entity", "relation", "event"]] | None = Field(
        default=None, min_length=1,
    )
    max_items_per_batch: int | None = Field(default=None, ge=1, le=50)
    transient_retry_budget: int | None = Field(default=None, ge=0, le=10)
    disable: bool = Field(
        default=False,
        description=(
            "Clear the runtime override: DELETE the Redis key and revert "
            "to env-config (cycle 74b — NOT a force-off; if filter env is "
            "set, reverts to that). Mutually exclusive with model_ref."
        ),
    )

    @model_validator(mode="after")
    def _check_disable_xor_model_ref(self) -> "FilterReloadRequest":
        # /review-impl r1 H2 fold: disable+model_ref both set = ambiguous, reject.
        if self.disable and self.model_ref is not None:
            raise ValueError(
                "disable=true is mutually exclusive with model_ref; "
                "pick one"
            )
        # /review-impl r1 H5 fold: empty body without disable=true is also
        # rejected (no implicit fall-through).
        if not self.disable and self.model_ref is None:
            raise ValueError(
                "either disable=true OR model_ref must be provided"
            )
        return self


class FilterReloadResponse(BaseModel):
    """Cycle 73f response body — server-generated timestamp + echoed config."""
    reloaded_at: str  # ISO8601 server-generated (r1 M1 fold)
    knowledge_service_config: dict[str, Any] | None
    redis_publish_status: Literal["published", "failed"]


def _build_filter_config_from_request(
    body: FilterReloadRequest,
) -> PrecisionFilterConfig | None:
    """r1 H3 fold: rebuild-from-scratch (NOT merge with current). Returns
    None when disable=true; PrecisionFilterConfig from body fields otherwise.
    PrecisionFilterConfig.__post_init__ validates remaining invariants
    (raises ValueError → 422 propagated by FastAPI)."""
    if body.disable:
        return None
    # model_ref is required (validated by model_validator above)
    assert body.model_ref is not None
    kwargs: dict[str, Any] = {"model_ref": body.model_ref}
    if body.model_source is not None:
        kwargs["model_source"] = body.model_source
    if body.partial_policy is not None:
        kwargs["partial_policy"] = body.partial_policy
    if body.categories is not None:
        kwargs["categories"] = tuple(body.categories)  # r1 M3: list → tuple
    if body.max_items_per_batch is not None:
        kwargs["max_items_per_batch"] = body.max_items_per_batch
    if body.transient_retry_budget is not None:
        kwargs["transient_retry_budget"] = body.transient_retry_budget
    return PrecisionFilterConfig(**kwargs)


@router.post(
    "/precision-filter/reload",
    response_model=FilterReloadResponse,
    summary="Cycle 73f — runtime reload Pass2 precision filter config",
    description=(
        "Ops endpoint to change filter config WITHOUT compose restart. "
        "Writes the new config to Redis key `loreweave:precision-filter-config` "
        "(source of truth across services) + publishes a reload signal on "
        "`loreweave:precision-filter-reload` pubsub channel. Subscribers "
        "(KS orchestrator + worker-ai) re-read the key and atomically swap "
        "their module-level cache.\n\n"
        "**Persistence:** the Redis key persists across container restart. "
        "Send `{disable: true}` to DELETE the key and revert to env-config. "
        "Cycle 74b: `disable` is a *clear-the-override* op, NOT a force-off — "
        "subscribers (and this endpoint's local apply) re-read the absent key "
        "and reload env config at runtime, identical to startup hydrate. If "
        "the deployment sets no filter env, that env config is itself None "
        "(filter off); if it sets one (the compose default is `relation`/"
        "`drop`), disable reverts to THAT, not to off. This closed the "
        "cycle-73f live-smoke finding where the runtime path set None while "
        "a restart reloaded env config — a silent cross-path divergence.\n\n"
        "**Failure modes:** if Redis SET succeeds but PUBLISH fails, the "
        "response returns `redis_publish_status='failed'` (200, not 502, "
        "since KS-side cache is still updated). Ops MUST check the status "
        "field. Counter `knowledge_extraction_filter_reload_total{source=api}` "
        "tracks outcomes — `applied` and `failed` are ADDITIVE per r3 M1 "
        "fold (both bump when local-applied + redis-failed).\n\n"
        "**Known limitations (r3 L3+L4 docs):**\n"
        "- **Pubsub message-loss:** Redis pub/sub is fire-and-forget; if a "
        "subscriber's TCP buffer is full or connection blips, the reload "
        "signal is silently dropped. The affected replica/worker stays on "
        "old cache until next reload POST. Workaround: re-POST to converge.\n"
        "- **Redis restart:** if Redis itself restarts (not the service), the "
        "config key is lost. Next KS startup hydrate finds no key and falls "
        "back to env defaults silently. Ops should re-POST after Redis "
        "incidents. (Future: persistent Redis storage class OR config-store "
        "in Postgres for cross-Redis-restart durability.)"
    ),
)
async def reload_precision_filter(
    body: FilterReloadRequest,
) -> FilterReloadResponse:
    from app.extraction.pass2_orchestrator import (
        _load_precision_filter_config,
        set_precision_filter_config,
    )

    # 1. Build new config from request body (None if disable=true).
    try:
        new_config = _build_filter_config_from_request(body)
    except (ValueError, NotImplementedError) as exc:
        knowledge_extraction_filter_reload_total.labels(
            source="api", outcome="rejected",
        ).inc()
        raise HTTPException(status_code=422, detail=str(exc))

    # 2. Connect to Redis. Per-request client; closed in finally.
    redis_client: aioredis.Redis | None = None
    publish_status: Literal["published", "failed"] = "failed"
    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=False)
        # 3. SET or DELETE the key + PUBLISH the reload signal.
        if new_config is None:
            await delete_filter_config(redis_client)
        else:
            await set_filter_config(redis_client, new_config)
        publish_status = "published"
    except Exception:
        # /review-impl r1 H4 fold: Redis SET/PUBLISH failure leaves the
        # local cache untouched and surfaces in the response. Ops should
        # check `redis_publish_status` and either retry or escalate.
        logger.exception("filter-reload: Redis SET/PUBLISH failed")
        knowledge_extraction_filter_reload_total.labels(
            source="api", outcome="failed",
        ).inc()
        publish_status = "failed"
    finally:
        if redis_client is not None:
            try:
                await redis_client.aclose()
            except Exception:
                pass  # best-effort cleanup

    # 4. Apply locally even if Redis publish failed — KS still gets the
    #    new config; worker-ai may drift until next manual reload.
    #    Cycle 74b — on disable (new_config is None), revert to env config
    #    instead of None so the runtime cache matches startup-hydrate +
    #    pubsub re-read semantics: `disable=true` clears the override and
    #    reverts to env-config (NOT "force-off until restart"). `_load`
    #    returns None when no filter env is set, so a no-filter deployment
    #    still lands at None.
    if new_config is None:
        new_config = _load_precision_filter_config()
    effective = set_precision_filter_config(new_config)

    # 5. Bookkeeping per /review-impl r3 M1 fold: counter outcomes are
    #    ADDITIVE so dashboards can compute "total reload attempts" =
    #    sum of all outcomes. Always bump `applied` on successful
    #    local-apply (the KS-side cache is now correct regardless of
    #    Redis state). The publish-failure path bumped `failed` above.
    #    Total per-reload: 1 bump if redis OK; 2 bumps if redis failed.
    knowledge_extraction_filter_reload_total.labels(
        source="api", outcome="applied",
    ).inc()

    # 6. Build response.
    config_dict = dataclasses.asdict(effective) if effective is not None else None
    if config_dict is not None and "categories" in config_dict:
        config_dict["categories"] = list(config_dict["categories"])
    logger.info(
        "filter-reload: source=api effective=%s publish=%s",
        "active" if effective else "disabled", publish_status,
    )
    return FilterReloadResponse(
        reloaded_at=datetime.now(timezone.utc).isoformat(),
        knowledge_service_config=config_dict,
        redis_publish_status=publish_status,
    )
