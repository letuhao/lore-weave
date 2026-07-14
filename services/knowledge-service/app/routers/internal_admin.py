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
from datetime import date, datetime, timezone
from typing import Any, Literal

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from uuid import UUID

from app.config import settings
from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.passages import (
    delete_all_kg_nodes_for_project,
    delete_all_passages_for_project,
)
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


async def _erase_one_assistant_project(pool, user_id: UUID, project_id: UUID) -> dict:
    """Erase ONE assistant project + its entire semantic index. Neo4j passages FIRST, PG rows LAST (erase
    review MED-3): the project_id identifies the passages, so a PG-first delete that then failed on Neo4j
    would strand the raw diary passages under a project_id nothing can re-resolve. Also clears the
    pending-facts inbox + rejection tombstones (they hold decryptable diary fact text, no FK cascade)."""
    async with neo4j_session() as session:
        passages_deleted = await delete_all_passages_for_project(
            session, user_id=str(user_id), project_id=str(project_id),
        )
        # D-R27 — also delete the CONFIRMED-fact graph (WS-2.4 promote → :Fact/:Entity/:ABOUT), else a
        # confirmed diary fact + the colleague it names survives erasure (caught by the E2E erase smoke).
        kg_nodes_deleted = await delete_all_kg_nodes_for_project(
            session, user_id=str(user_id), project_id=str(project_id),
        )
    async with pool.acquire() as conn:
        pf = await conn.execute(
            "DELETE FROM knowledge_pending_facts WHERE user_id=$1 AND project_id=$2", user_id, project_id,
        )
        await conn.execute(
            "DELETE FROM knowledge_rejected_facts WHERE user_id=$1 AND project_id=$2", user_id, project_id,
        )
    pending_facts_deleted = int(pf.split()[-1]) if pf else 0
    project_deleted = await ProjectsRepo(pool).delete(user_id, project_id)
    return {
        "project_deleted": bool(project_deleted),
        "passages_deleted": passages_deleted,
        "kg_nodes_deleted": kg_nodes_deleted,
        "pending_facts_deleted": pending_facts_deleted,
    }


@router.delete("/assistant/erase")
async def erase_assistant_knowledge(
    user_id: UUID = Query(...),
    project_id: UUID | None = Query(None),
) -> dict:
    """D-R27 (human-authorized erasure) — delete a user's ASSISTANT knowledge + its ENTIRE semantic index
    (Neo4j `:Passage` nodes + the `knowledge_projects` row + the pending/rejected fact inboxes). Every
    store is tenant-scoped on (user_id, project_id), so this only reaches the caller's own data.

    project_id is OPTIONAL (audit HIGH-2): when omitted, ALL of the user's assistant projects are resolved
    by the `is_assistant` flag (via `list_assistant_project_ids`) and each is erased. The gateway erase
    calls it WITHOUT a project_id — so the KG erase runs by user_id alone, independent of whether the diary
    BOOK still exists. A book-keyed project resolution that fails after the book is deleted used to skip
    this leg while still reporting `erased:true`, leaving decryptable diary passages + fact text behind."""
    pool = get_knowledge_pool()
    if project_id is not None:
        targets = [project_id]
    else:
        targets = [UUID(p) for p in await ProjectsRepo(pool).list_assistant_project_ids(user_id)]
    results = [await _erase_one_assistant_project(pool, user_id, pid) for pid in targets]
    return {
        "projects_erased": len(results),
        "project_deleted": any(r["project_deleted"] for r in results),
        "passages_deleted": sum(r["passages_deleted"] for r in results),
        "kg_nodes_deleted": sum(r["kg_nodes_deleted"] for r in results),
        "pending_facts_deleted": sum(r["pending_facts_deleted"] for r in results),
    }


class _DiaryFactIn(BaseModel):
    kind: str
    text: str
    # WS-2.2 (structured s/p/o) — optional; a coarse fact carries only text, a structured one the trio.
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    event_date: str | None = None  # ISO 'YYYY-MM-DD'; the day the fact is true of
    provenance: str | None = None  # 'user' | 'quoted_third_party'


class _QueueDiaryFactsIn(BaseModel):
    user_id: UUID
    book_id: UUID
    entry_date: str | None = None
    facts: list[_DiaryFactIn]


def _parse_iso_date(value: str | None) -> date | None:
    """Parse an ISO 'YYYY-MM-DD' into a date for an asyncpg ::date bind, tolerating None/garbage (→ None
    rather than a 500). A trailing time component (an ISO datetime) is accepted by taking the date part."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _diary_fact_dedup_key(project_id: object, kind: str, text: str, fact: _DiaryFactIn, day: str) -> str:
    """A STABLE, PER-DAY dedup identity for a distilled fact. When the structured trio is present, key on
    the normalized (subject, predicate, object) so an LLM re-phrasing of the SAME fact across re-distills
    collides (the semantic-dedup fix — fact_text alone drifts with wording). Else fall back to the coarse
    fact_text. Normalization: casefold + collapse whitespace, so "The Q3 Budget" == "q3 budget".

    `day` (the fact's effective ISO date) is part of the key so dedup + the rejection tombstone are
    per-DAY (audit MED-2): the same (Alice, said, budget) on Mon and Fri are DISTINCT facts — a Friday
    re-affirmation isn't silently dropped, and rejecting Monday's doesn't tombstone Friday's forever."""
    def _norm(s: str | None) -> str:
        return " ".join((s or "").split()).casefold()

    if fact.subject and fact.object:
        basis = f"spo:{_norm(fact.subject)}|{_norm(fact.predicate)}|{_norm(fact.object)}"
    else:
        basis = f"text:{_norm(kind)}|{_norm(text)}"
    return hashlib.sha256(f"{project_id}:{day}:{basis}".encode("utf-8")).hexdigest()


@router.post("/assistant/queue-facts")
async def queue_diary_facts(body: _QueueDiaryFactsIn) -> dict:
    """WS-2.1/2.3/2.2 — the assistant's DIVERT-TO-INBOX fact write. A distilled day's facts are queued
    into the pending-facts INBOX (never `pending_validation=False`; the diary's facts are human-gated,
    D4), resolving the user's assistant project by (user, book). Each fact lands as `fact_type='statement'`
    with the kind + entry_date encoded in `fact_text`, PLUS the WS-2.2 structured s/p/o + event_date +
    provenance columns when the distiller extracted them. `session_id` is None (a diary fact has no chat
    session). Internal-token.

    Two idempotency guards (WS-2.2): the `dedup_key` (semantic when the trio is present, else text-based)
    makes a re-distill of the SAME day a no-op via ON CONFLICT DO NOTHING; a `knowledge_rejected_facts`
    tombstone on the same key makes a fact the user already DISMISSED stay dismissed (no re-nag loop)."""
    pool = get_knowledge_pool()
    project, _ = await ProjectsRepo(pool).get_or_create_assistant_project(body.user_id, body.book_id)
    queued = 0
    skipped_tombstoned = 0
    async with pool.acquire() as conn:
        for f in body.facts:
            text = (f.text or "").strip()
            if not text:
                continue
            date_sfx = f" ({body.entry_date})" if body.entry_date else ""
            fact_text = f"[{(f.kind or 'event').strip()}] {text}{date_sfx}"
            # asyncpg encodes a ::date param as a Python date (not a str) BEFORE the cast, so parse the ISO
            # string here. Parse EACH candidate independently (audit MED-3): `_parse_iso_date(f.event_date)
            # or _parse_iso_date(body.entry_date)` — a non-ISO f.event_date ("yesterday") must NOT swallow
            # the valid entry_date fallback (memory: asyncpg-timestamptz-param-needs-datetime).
            event_date = _parse_iso_date(f.event_date) or _parse_iso_date(body.entry_date)
            # The dedup/tombstone identity is PER-DAY (audit MED-2): include the effective date so the same
            # s/p/o on two different days are distinct facts (a re-affirmation isn't dropped; a Monday
            # reject doesn't tombstone Friday's). '' when no date at all → collapses to a single bucket.
            day_key = event_date.isoformat() if event_date is not None else ""
            dedup_key = _diary_fact_dedup_key(project.project_id, f.kind, text, f, day_key)
            # Tombstone gate: a fact the user rejected must not re-appear on the next distill. Skip BEFORE
            # the insert so a re-nag never even touches the inbox. (Keyed identically to the dedup so a
            # reject and a re-queue can never disagree on identity.)
            tomb = await conn.fetchval(
                "SELECT 1 FROM knowledge_rejected_facts "
                "WHERE user_id=$1 AND project_id=$2 AND dedup_key=$3",
                body.user_id, project.project_id, dedup_key,
            )
            if tomb is not None:
                skipped_tombstoned += 1
                continue
            row = await conn.fetchrow(
                """
                INSERT INTO knowledge_pending_facts
                  (user_id, project_id, session_id, fact_type, fact_text, dedup_key,
                   subject, predicate, object, event_date, provenance)
                VALUES ($1, $2, NULL, 'statement', $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (user_id, project_id, dedup_key) WHERE dedup_key IS NOT NULL
                DO NOTHING
                RETURNING pending_fact_id
                """,
                body.user_id, project.project_id, fact_text, dedup_key,
                f.subject, f.predicate, f.object, event_date, (f.provenance or "user"),
            )
            if row is not None:  # None ⇒ a duplicate was skipped
                queued += 1
    return {
        "queued": queued,
        "skipped_tombstoned": skipped_tombstoned,
        "project_id": str(project.project_id),
    }


class _RecallFactsIn(BaseModel):
    user_id: UUID
    book_id: UUID
    event_date_from: str | None = None   # ISO 'YYYY-MM-DD' inclusive lower bound
    event_date_to: str | None = None     # ISO 'YYYY-MM-DD' inclusive upper bound
    subject_name: str | None = None      # narrow to facts ABOUT this person/thing
    limit: int = 50


@router.post("/assistant/recall-facts")
async def recall_assistant_facts(body: _RecallFactsIn) -> dict:
    """WS-2.4 — the diary's date-filtered KG recall. Resolves the user's assistant project by (user,
    book), then returns confirmed :Fact nodes in the event_date range (optionally ABOUT a subject),
    newest-first. This is the read that answers "what did <subject> say about <topic> last month" — it
    is project-scoped (never all-projects), so it cannot surface another project's facts (D16)."""
    from app.db.neo4j import neo4j_session
    from app.db.neo4j_repos.facts import group_supersessions, recall_facts

    pool = get_knowledge_pool()
    project, _ = await ProjectsRepo(pool).get_or_create_assistant_project(body.user_id, body.book_id)
    async with neo4j_session() as session:
        facts = await recall_facts(
            session,
            user_id=str(body.user_id),
            project_id=str(project.project_id),
            event_date_from=body.event_date_from,
            event_date_to=body.event_date_to,
            subject_name=body.subject_name,
            limit=body.limit,
        )
    # WS-2.6b (spec 07 §Q5) — surface a SUPERSESSION ("it changed") rather than two independent truths
    # when a claim's object changed over time (same subject+predicate, different object across dates).
    supersessions = group_supersessions(facts)
    return {
        "project_id": str(project.project_id),
        "count": len(facts),
        "facts": [
            {
                "type": f.type, "content": f.content,
                "event_date_iso": f.event_date_iso,
                "valid_from_ordinal": f.valid_from_ordinal,
                "subject": f.subject_canonical, "predicate": f.predicate, "object": f.object,
            }
            for f in facts
        ],
        "supersessions": supersessions,
    }


class _RejectDiaryFactIn(BaseModel):
    user_id: UUID
    pending_fact_id: UUID


@router.post("/assistant/reject-fact")
async def reject_diary_fact(body: _RejectDiaryFactIn) -> dict:
    """WS-2.2 (rejection tombstone) — the user dismisses a proposed diary fact. Delegates to the SINGLE
    reject-with-tombstone repo path (shared with the public FE reject route, so the two can never drift):
    it deletes the pending row and writes a `knowledge_rejected_facts` tombstone on its dedup_key so the
    next "End my day" does NOT re-propose the dismissed fact. Owner-scoped + idempotent."""
    from app.db.repositories.pending_facts import PendingFactsRepo
    rejected = await PendingFactsRepo(get_knowledge_pool()).reject(body.user_id, body.pending_fact_id)
    return {"rejected": 1 if rejected else 0, "tombstoned": rejected}


class _MergeEntitiesIn(BaseModel):
    user_id: UUID
    book_id: UUID
    from_name: str   # the DUPLICATE/old spelling to fold away (e.g. "Minh")
    into_name: str   # the entity to keep (e.g. "Minh Nguyen")


@router.post("/assistant/merge-entities")
async def merge_assistant_entities(body: _MergeEntitiesIn) -> dict:
    """WS-2.6d (D17 merge-a-renamed-entity) — fold one diary person/thing into another BY NAME within the
    user's assistant project. The diary agent knows colleague NAMES, not KG ids, so this resolves both
    names → the best-matching :Entity in the assistant project (never all-projects — D16) and runs the
    proven `merge_entities` surgery: re-point the loser's `(:Fact)-[:ABOUT]->` edges onto the winner (so
    recall attributes BOTH names' facts to one person), move aliases, then DETACH DELETE the loser.

    Idempotent-ish: a `from_name` that no longer resolves (already merged) → 404 `from_not_found`. Same
    entity both sides → 400 `same_entity`. Internal-token; the diary subjects are KG-only auto-created
    entities (no glossary anchor), so this never touches an authored glossary row."""
    from app.db.neo4j import neo4j_session
    from app.db.neo4j_repos.entities import (
        MergeEntitiesError,
        find_entities_by_name,
        merge_entities,
    )

    from_name = (body.from_name or "").strip()
    into_name = (body.into_name or "").strip()
    if not from_name or not into_name:
        raise HTTPException(status_code=422, detail="from_name and into_name are required")

    pool = get_knowledge_pool()
    project, _ = await ProjectsRepo(pool).get_or_create_assistant_project(body.user_id, body.book_id)
    pid = str(project.project_id)
    async with neo4j_session() as session:
        # Resolve within the assistant project only (D16 — never fold a novel entity into a diary one).
        src = await find_entities_by_name(session, user_id=str(body.user_id), project_id=pid, name=from_name)
        dst = await find_entities_by_name(session, user_id=str(body.user_id), project_id=pid, name=into_name)
        if not src:
            raise HTTPException(status_code=404, detail={"error_code": "from_not_found",
                                "message": f"no assistant entity named {from_name!r}"})
        if not dst:
            raise HTTPException(status_code=404, detail={"error_code": "into_not_found",
                                "message": f"no assistant entity named {into_name!r}"})
        source_id, target_id = src[0].id, dst[0].id
        if source_id == target_id:
            raise HTTPException(status_code=400, detail={"error_code": "same_entity",
                                "message": "from_name and into_name resolve to the same entity"})
        try:
            target = await merge_entities(
                session, user_id=str(body.user_id), source_id=source_id, target_id=target_id,
            )
        except MergeEntitiesError as exc:
            code = exc.error_code
            http = 409 if code in ("glossary_conflict",) else 400
            raise HTTPException(status_code=http, detail={"error_code": code, "message": str(exc)})
    return {
        "merged": True, "project_id": pid,
        "target_id": target.id, "target_name": target.name,
        "merged_from_id": source_id, "aliases": list(target.aliases or []),
    }


class _ForgetEntityIn(BaseModel):
    user_id: UUID
    book_id: UUID
    name: str  # the person/thing to forget (e.g. "Minh")


@router.post("/assistant/forget-entity")
async def forget_assistant_entity(body: _ForgetEntityIn) -> dict:
    """WS-2.6c (D17 forget-a-person) — the KNOWLEDGE leg of the SCOPED-ERASURE PRIMITIVE at scope=entity.
    Resolve the person BY NAME within the user's assistant project (never all-projects — D16), then:
      1. KG cascade — DETACH DELETE the :Entity + every :Fact ABOUT it (`erase_entity_subgraph`).
      2. inbox tombstone — delete pending facts ABOUT them + tombstone each dedup_key, so a later
         re-distill of a day that still mentions them can NEVER re-propose the fact (no resurrection).
      3. emit `knowledge.entity_forgotten` (best-effort outbox) so every derived consumer reconciles.

    This is the STRUCTURED-memory half of forget. The SOURCE-text half — redacting the name from the
    diary entry bodies (book-service) so a re-index can't resurface it — is the diary-span REDACTION leg,
    driven by the gateway `/v1/assistant/forget` orchestration (book-service owns the entry text). Both
    are needed for a complete forget; this endpoint returns the resolved name so the caller can redact.

    Idempotent: a name that no longer resolves → `forgotten:false` (already gone). Internal-token."""
    from app.db.neo4j import neo4j_session
    from app.db.neo4j_repos.entities import erase_entity_subgraph, find_entities_by_name
    from app.db.repositories.pending_facts import PendingFactsRepo
    from app.events.outbox_emit import ENTITY_FORGOTTEN, emit_correction

    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")

    pool = get_knowledge_pool()
    project, _ = await ProjectsRepo(pool).get_or_create_assistant_project(body.user_id, body.book_id)
    pid = str(project.project_id)
    async with neo4j_session() as session:
        matches = await find_entities_by_name(session, user_id=str(body.user_id), project_id=pid, name=name)
        if not matches:
            # Nothing in the KG under that name; still tombstone any pending proposals so a forget of a
            # not-yet-confirmed person also can't resurrect.
            tombstoned = await PendingFactsRepo(pool).tombstone_by_subject(body.user_id, project.project_id, name)
            return {"forgotten": tombstoned > 0, "entities_deleted": 0, "facts_deleted": 0,
                    "pending_tombstoned": tombstoned, "project_id": pid, "name": name}
        entity = matches[0]
        cascade = await erase_entity_subgraph(
            session, user_id=str(body.user_id), entity_id=entity.id, project_id=pid,
        )
    tombstoned = await PendingFactsRepo(pool).tombstone_by_subject(body.user_id, project.project_id, name)
    # Best-effort event so downstream consumers (search caches, etc.) reconcile; the cascade already did
    # the destructive work, so a lost event under-notifies but never leaves the graph half-erased.
    await emit_correction(
        event_type=ENTITY_FORGOTTEN,
        aggregate_id=entity.id,
        payload={"user_id": str(body.user_id), "project_id": pid, "entity_id": entity.id,
                 "name": entity.name, "scope": "entity",
                 "facts_deleted": cascade["facts_deleted"], "pending_tombstoned": tombstoned},
    )
    return {
        "forgotten": True, "project_id": pid, "name": entity.name, "entity_id": entity.id,
        "entities_deleted": cascade["entities_deleted"], "facts_deleted": cascade["facts_deleted"],
        "pending_tombstoned": tombstoned,
    }


class _InvalidateDayIn(BaseModel):
    user_id: UUID
    book_id: UUID
    entry_date: str  # ISO 'YYYY-MM-DD' — the corrected diary day whose facts are superseded


@router.post("/assistant/invalidate-day")
async def invalidate_diary_day(body: _InvalidateDayIn) -> dict:
    """WS-2.6a leg 3 (D17 amendment reconcile) — soft-invalidate a corrected diary day's CONFIRMED facts.

    Called by worker-ai's re-extract path AFTER the user amends a day's entry (book-service leg 1) and
    the corrected facts are re-queued to the inbox (leg 2). Resolves the user's assistant project by
    (user, book) — never all-projects (D16) — then sets `valid_until` on every active confirmed :Fact
    whose `event_date_iso` equals the corrected day. This is the leg that makes the OLD fact stop
    resurrecting: without it a KG rebuild re-derives the superseded fact and recall shows both the wrong
    and the corrected value (the `memory_forget`-stops-at-leg-3 lie D17 exists to kill). Internal-token;
    idempotent (only active facts are touched)."""
    day = _parse_iso_date(body.entry_date)
    if day is None:
        raise HTTPException(status_code=422, detail="entry_date must be ISO 'YYYY-MM-DD'")
    from app.db.neo4j_repos.facts import invalidate_facts_for_day

    pool = get_knowledge_pool()
    project, _ = await ProjectsRepo(pool).get_or_create_assistant_project(body.user_id, body.book_id)
    async with neo4j_session() as session:
        invalidated = await invalidate_facts_for_day(
            session,
            user_id=str(body.user_id),
            project_id=str(project.project_id),
            event_date=day.isoformat(),
        )
    return {"invalidated": invalidated, "project_id": str(project.project_id),
            "entry_date": day.isoformat()}


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
