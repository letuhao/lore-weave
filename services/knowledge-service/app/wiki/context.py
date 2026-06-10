"""Wiki generation — per-entity context gathering (wiki-llm M2 / §C4).

For ONE entity, assemble the grounding the LLM writes from: the glossary entity
brief (name/kind/aliases/short-description), its 1-hop KG neighbours, and the
top retrieved chapter passages (via the in-process hybrid retriever). ALL
untrusted text is injection-sanitized on the way in (`neutralize_injection`, the
shared SDK shim), and every citable item is assigned a stable **cite-label** —
``G1..`` glossary · ``K1..`` KG · ``P1..`` passages — producing the M0 IR
:class:`Source` table the prompt (M3) hands the LLM and echoes back as citations.

The cite labels are OURS: a label the LLM emits that is NOT in ``sources`` is a
hallucinated reference (dropped at parse, M3). Degrades gracefully — a book with
no semantic index (risk #9) yields no passages but the brief + KG still ground
the article; a down graph drops the KG facts; nothing raises. An entity that
can't be read (or has no name) returns ``None`` → the orchestrator skips it.
"""

from __future__ import annotations

import logging
from uuid import UUID

from pydantic import BaseModel, Field

from app.clients.book_client import BookClient
from app.clients.embedding_client import EmbeddingClient
from app.clients.glossary_client import GlossaryClient
from app.clients.reranker_client import RerankerClient
from app.db.models import Project
from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.relations import find_relations_for_entity
from app.extraction.injection_defense import neutralize_injection
from app.search.retriever import Granularity, SearchMode, run_hybrid_search
from app.wiki.ir import Source

logger = logging.getLogger(__name__)

#: Stored snippet length (~the citation hover-preview budget, IR §C1/C3). The
#: FULL text still goes to the LLM via :attr:`ContextSource.text`.
SNIPPET_CHARS = 160
#: Default fan-out — small on purpose: a focused article cites a handful of
#: passages, and a wider net dilutes grounding + costs tokens.
DEFAULT_PASSAGE_LIMIT = 8
DEFAULT_KG_LIMIT = 20


def _sanitize(text: str | None) -> str:
    """Injection-neutralize untrusted entity/KG/passage text → safe string."""
    return neutralize_injection(text or "")[0]


def _snippet(text: str, n: int = SNIPPET_CHARS) -> str:
    """Truncate to the stored-snippet budget (rune-safe; '…' on overflow)."""
    text = text.strip()
    return text if len(text) <= n else text[:n].rstrip() + "…"


class EntityBrief(BaseModel):
    """The entity identity (NOT a citable claim — the article's subject header).
    All fields are sanitized; ``name`` is the article title source."""

    entity_id: str
    name: str
    kind: str = ""
    aliases: list[str] = Field(default_factory=list)
    short_description: str = ""


class ContextSource(BaseModel):
    """One citable item: the IR :class:`Source` (cite-label + anchor + stored
    snippet) PLUS the FULL ``text`` fed to the LLM under that label. The prompt
    (M3) formats ``[cite_id] text``; the writeback stores ``source`` verbatim."""

    source: Source
    text: str


class GenerationContext(BaseModel):
    """Everything the prompt (M3) needs for one entity. ``items`` is the ordered
    cite table (glossary → KG → passages); ``degraded`` records any leg that fell
    back (e.g. ``{"semantic": "not_indexed"}``)."""

    brief: EntityBrief
    items: list[ContextSource] = Field(default_factory=list)
    degraded: dict[str, str] = Field(default_factory=dict)

    @property
    def sources(self) -> list[Source]:
        """The IR cite-label table (what the writeback + parser validate against)."""
        return [it.source for it in self.items]

    @property
    def passage_count(self) -> int:
        return sum(1 for it in self.items if it.source.kind == "passage")


def _kg_fact_text(rel) -> str:
    """Render a 1-hop relation as a directed fact line ``subject — predicate →
    object`` (names sanitized; the predicate is a KG slug we control). Falls back
    to ids when an endpoint name is missing."""
    subj = _sanitize(rel.subject_name) or rel.subject_id
    obj = _sanitize(rel.object_name) or rel.object_id
    pred = _sanitize(rel.predicate) or "related to"
    return f"{subj} — {pred} → {obj}"


async def _gather_kg(
    *, entity_id: str, user_id: UUID, project: Project, kg_limit: int,
    degraded: dict[str, str],
) -> list[str]:
    """1-hop KG neighbour facts (best-effort). A down/empty graph → [] +
    a degraded marker; never raises into generation."""
    try:
        async with neo4j_session() as session:
            rels = await find_relations_for_entity(
                session,
                user_id=str(user_id),
                entity_id=entity_id,
                project_id=str(project.project_id),
                limit=kg_limit,
            )
    except Exception as exc:  # noqa: BLE001 — KG is optional grounding
        logger.warning("wiki context: KG read failed for %s: %s", entity_id, exc)
        degraded["kg"] = "unavailable"
        return []
    facts: list[str] = []
    for rel in rels:
        text = _kg_fact_text(rel)
        if text.strip():
            facts.append(text)
    return facts


async def gather_entity_context(
    *,
    entity_id: str,
    book_id: UUID,
    user_id: UUID,
    project: Project,
    glossary_client: GlossaryClient,
    book_client: BookClient,
    embedding_client: EmbeddingClient,
    reranker_client: RerankerClient,
    passage_limit: int = DEFAULT_PASSAGE_LIMIT,
    kg_limit: int = DEFAULT_KG_LIMIT,
    mode: SearchMode = "hybrid",
    granularity: Granularity = "chapter",
) -> GenerationContext | None:
    """Assemble the grounded, sanitized, cite-labelled context for one entity.

    Returns ``None`` when the entity can't be read or has no name (the
    orchestrator skips it). Otherwise builds the cite table G1.. (glossary) →
    K1.. (KG) → P1.. (passages); a missing leg degrades (marker) rather than
    failing. The passage query is the entity name + aliases."""
    degraded: dict[str, str] = {}

    # 1. Entity brief (glossary). No entity / no name ⇒ skip (can't title it).
    entities = await glossary_client.fetch_entities_by_ids(
        book_id=book_id, entity_ids=[entity_id],
    )
    if not entities:
        return None
    ent = entities[0]
    name = _sanitize(ent.cached_name)
    if not name:
        return None
    aliases = [a for a in (_sanitize(x) for x in ent.cached_aliases) if a]
    short_description = _sanitize(ent.short_description)
    brief = EntityBrief(
        entity_id=entity_id, name=name, kind=_sanitize(ent.kind_code),
        aliases=aliases, short_description=short_description,
    )

    items: list[ContextSource] = []

    # G1 — the glossary short-description as the one authored-canon glossary fact.
    if short_description:
        items.append(ContextSource(
            source=Source(cite_id="G1", kind="glossary", snippet=_snippet(short_description)),
            text=short_description,
        ))

    # K1.. — 1-hop KG neighbour facts.
    kg_facts = await _gather_kg(
        entity_id=entity_id, user_id=user_id, project=project,
        kg_limit=kg_limit, degraded=degraded,
    )
    for i, fact in enumerate(kg_facts, start=1):
        items.append(ContextSource(
            source=Source(cite_id=f"K{i}", kind="kg", snippet=_snippet(fact)),
            text=fact,
        ))

    # P1.. — retrieved chapter passages (hybrid, in-process). not_indexed/down ⇒
    # empty + a degraded marker; the brief + KG still ground the article (risk #9).
    pquery = " ".join([name, *aliases]).strip()
    retrieval = await run_hybrid_search(
        user_id=user_id, book_id=book_id, query=pquery, project=project,
        book_client=book_client, embedding_client=embedding_client,
        reranker_client=reranker_client, mode=mode, granularity=granularity,
        limit=passage_limit,
    )
    degraded.update(retrieval.degraded)
    # Running counter (NOT the enumerate index) so a skipped (empty-snippet) hit
    # doesn't leave a gap in the P-labels — the labels must be P1..Pk contiguous.
    p_label = 0
    for hit in retrieval.hits:
        passage_text = _sanitize(hit.get("snippet")).strip()
        if not passage_text:
            continue
        loc = hit.get("location") or {}
        p_label += 1
        items.append(ContextSource(
            source=Source(
                cite_id=f"P{p_label}",
                kind="passage",
                chapter_id=str(hit["chapterId"]) if hit.get("chapterId") else None,
                block_index=loc.get("blockIndex"),
                chapter_sort_order=hit.get("sortOrder"),
                score=hit.get("score"),
                snippet=_snippet(passage_text),
            ),
            text=passage_text,
        ))

    return GenerationContext(brief=brief, items=items, degraded=degraded)
