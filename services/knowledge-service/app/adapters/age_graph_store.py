"""`GraphStore` on Apache AGE — the second adapter (plan T42, decision X1).

WHY A SECOND ADAPTER AT ALL
---------------------------
X1: build BOTH candidates and let T43's shadow comparison choose, rather than deciding the
engine by argument. AGE's case is **colocation** — graph, vectors (T3 → pgvector) and truth
in one Postgres, one backup, one ops surface. Its cost is a query-layer rewrite, and this
file is that cost, paid and measurable rather than estimated.

AGE IS NOT NEO4J WITH A DIFFERENT PORT NUMBER
---------------------------------------------
Four differences drive almost every line below. Each was measured against a running AGE
1.7.0, not read from documentation — the 2026-08-09 audit eliminated AGE from a doc check
that a container later refuted, so this file's claims are all reproducible.

**1 · No `ON CREATE SET` / `ON MATCH SET`.** They are syntax errors. The equivalent is
`SET x = coalesce(x, v)` for create-only fields and a plain `SET` for always-write fields.
Verified: run the same MERGE twice, the coalesced field keeps its first value while the
plain one advances.

**2 · Whether a MERGE created or matched is not observable inside Cypher.** Neo4j's
`ON CREATE SET e.__was_created = true` has no AGE equivalent. Where that matters, ask
`ag_graph`/the node BEFORE the merge, in the same transaction — never infer it from
`created_at == updated_at`, which the Neo4j adapter's own comment rejects as fragile.

**3 · `CALL { … }` is unsupported**, so composition moves to SQL: `cypher()` is a
table-valued function, and `UNION`/`LATERAL`/CTEs do what the subquery did. That is not a
workaround — for the correlated per-row case it is the better tool.

**4 · Parameters do not reach Cypher.** AGE takes a `$1`-style argument to `cypher()` only
as a whole agtype map, and referencing it inside the query is limited. Values are therefore
**interpolated**, which makes escaping a correctness AND a security concern rather than a
formatting detail — see `_lit`.

THE EVENT SURFACE — implemented 2026-08-12, and it used to raise
-----------------------------------------------------------------
`status_at_order` and `events_in_window` shipped as `NotImplementedError` on purpose
(`D-T42-AGE-EVENT-SURFACE`): T43 compares this adapter against Neo4j, and a method that
silently returned `[]` would have made a COVERAGE gap look like a DATA difference — and
would have satisfied the shadow coverage floor while proving nothing. **Raising was the
honest interim state; it was never the destination.** Both are now real, which takes the
comparison from 7 of 9 operations to all nine.

Two choices in them are worth reading before editing:

* **`status_at_order` falls back to `'active'`**, matching Neo4j's
  `coalesce(latest.status, 'active')`. The asymmetry matters: a wrongly-`gone` entity
  vanishes from a panel, while a wrongly-`active` one silently un-kills a character.
* **`events_in_window` sorts in PYTHON.** Neo4j sinks unplaced events with
  `coalesce(e.event_order, 9223372036854775807)`; AGE's ordering over a NULL property is
  exactly the engine-specific behaviour this migration keeps finding differs. Sorting here
  makes the two adapters agree by construction on the one thing a caller sees — the sequence.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from loreweave_extraction.canonical import canonicalize_entity_name

from app.db.neo4j_repos.entities import Entity, EntityDetail
from app.db.neo4j_repos.events import Event
from app.domain.graph_models import Fact
from app.db.neo4j_repos.relations import Relation
from app.ports.graph_store import EventAxis, RelationDirection

__all__ = ["AgeGraphStore"]


def _lit(value: Any) -> str:
    """Render a Python value as a Cypher literal for interpolation.

    AGE cannot take query parameters the way the Neo4j driver does (difference 4 above), so
    every value is interpolated — which makes this function the tenancy boundary, not a
    formatting helper. A `user_id` that escaped its quotes would not merely error; it would
    let one tenant's filter be rewritten by another tenant's data.

    Strings go through `json.dumps`, which escapes quotes, backslashes and control
    characters to JSON rules that Cypher string literals share. Numbers and booleans are
    emitted unquoted so they compare as numbers — quoting an ordinal would make
    `valid_from_ordinal <= 10` a STRING comparison, where '9' > '10'.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_lit(v) for v in value) + "]"
    if isinstance(value, datetime):
        return json.dumps(value.astimezone(timezone.utc).isoformat())
    return json.dumps(str(value))


def _props(row: Any) -> dict:
    """agtype → dict of node/edge properties.

    asyncpg hands back agtype as a string with a `::vertex` / `::edge` type suffix that is
    NOT valid JSON. Stripping it is the whole of the mapping layer, and it is isolated here
    so a future asyncpg agtype codec replaces one function.
    """
    if row is None:
        return {}
    if isinstance(row, dict):
        return row.get("properties", row)
    text = str(row)
    for suffix in ("::vertex", "::edge", "::path"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed.get("properties", parsed) if isinstance(parsed, dict) else {}


def _unwrap(cell: Any) -> Any:
    """A scalar agtype cell -> a Python value.

    agtype scalars arrive as JSON text (`"gone"`, `12`, `null`), so a bare `str()` would make
    the quotes part of the value and `'"gone"' != 'gone'` would read as an engine divergence.
    """
    if cell is None:
        return None
    try:
        return json.loads(str(cell))
    except (json.JSONDecodeError, TypeError):
        return str(cell)


def _to_event(props: dict) -> Event:
    return Event.model_validate(
        {
            "id": props.get("id", ""),
            "user_id": props.get("user_id", ""),
            "project_id": props.get("project_id"),
            "title": props.get("title", ""),
            "canonical_title": props.get("canonical_title", props.get("title", "")),
            "summary": props.get("summary"),
            "chapter_id": props.get("chapter_id"),
            "event_order": props.get("event_order"),
            "chronological_order": props.get("chronological_order"),
        }
    )


def _to_entity(props: dict) -> Entity:
    return Entity.model_validate(
        {
            "id": props.get("id", ""),
            "user_id": props.get("user_id", ""),
            "project_id": props.get("project_id"),
            "name": props.get("name", ""),
            "canonical_name": props.get("canonical_name", ""),
            "kind": props.get("kind", ""),
            "aliases": props.get("aliases") or [],
            "canonical_version": props.get("canonical_version", 1),
            "source_types": props.get("source_types") or [],
            "confidence": props.get("confidence", 0.0),
            "glossary_entity_id": props.get("glossary_entity_id"),
            "anchor_score": props.get("anchor_score", 0.0),
            "archived_at": props.get("archived_at"),
            "archive_reason": props.get("archive_reason"),
        }
    )


def _to_relation(props: dict) -> Relation:
    return Relation.model_validate(
        {
            "id": props.get("id", ""),
            "user_id": props.get("user_id", ""),
            "subject_id": props.get("subject_id", ""),
            "object_id": props.get("object_id", ""),
            "predicate": props.get("predicate", ""),
            "confidence": props.get("confidence", 0.0),
            "source_event_ids": props.get("source_event_ids") or [],
            "source_chapter": props.get("source_chapter"),
            "valid_from_ordinal": props.get("valid_from_ordinal"),
            "valid_to_ordinal": props.get("valid_to_ordinal"),
        }
    )


def _to_fact(props: dict) -> Fact:
    return Fact.model_validate(
        {
            "id": props.get("id", ""),
            "user_id": props.get("user_id", ""),
            "project_id": props.get("project_id"),
            "type": props.get("type", ""),
            "content": props.get("content", ""),
            "canonical_content": props.get("canonical_content", props.get("content", "")),
            "confidence": props.get("confidence", 0.0),
            "pending_validation": props.get("pending_validation", False),
            "source_types": props.get("source_types") or [],
            "source_chapter": props.get("source_chapter"),
            "from_order": props.get("from_order"),
            "valid_from_ordinal": props.get("valid_from_ordinal"),
            "valid_to_ordinal": props.get("valid_to_ordinal"),
            "event_date_iso": props.get("event_date_iso"),
            "predicate": props.get("predicate"),
            "object": props.get("object"),
        }
    )


#: How many events `events_page` will scan into Python before refusing. A browse that
#: silently truncated would report a `total` describing the cap, not the corpus.
_AGE_BROWSE_SCAN_CAP = 5_000

class AgeGraphStore:
    """`GraphStore` over Apache AGE. Construct with an asyncpg pool from `create_age_pool`.

    The graph name is derived per project (`age_bootstrap.graph_name_for`), so tenancy has
    two layers: the graph a query runs against, AND a `user_id` predicate inside it. Both,
    deliberately — the graph split is an optimisation and a blast-radius limit, while the
    predicate is the thing that must be correct even if two projects ever shared a graph.
    """

    def __init__(self, pool, graph_name: str) -> None:
        self._pool = pool
        self._graph = graph_name

    @staticmethod
    def _dollar_tag(body: str) -> str:
        """A dollar-quote tag that does not occur in `body`.

        🔴 **THIS IS AN INJECTION FIX, found by `/review-impl` attacking this adapter.**
        `_lit` escapes correctly for the CYPHER layer — quotes, backslashes and newlines all
        survive, verified — but `$` is not a JSON escape, so a value containing the delimiter
        terminated the SQL dollar-quote early:

            name = 'evil$CY$ ) as (v agtype); DROP TABLE IF EXISTS pwned; --'
            -> PostgresSyntaxError: syntax error at or near "canonical_name"

        It errored rather than executing, but that is luck rather than design: the payload
        reached the SQL parser as SQL. Two layers of quoting were in play and only one was
        being escaped.

        Widening the tag until it is absent makes the delimiter unforgeable by construction —
        a value cannot contain a tag that was chosen *because* the value does not contain it.
        Preferred over rejecting `$` in input: the graph stores prose, and a rule banning a
        common character from names would be worked around rather than obeyed.
        """
        tag = "CY"
        while f"${tag}$" in body:
            tag += "X"
        return tag

    async def _run(self, cypher: str, *, columns: str = "v agtype") -> list:
        tag = self._dollar_tag(cypher)
        sql = f"SELECT * FROM cypher('{self._graph}', ${tag}${cypher}${tag}$) as ({columns})"
        async with self._pool.acquire() as conn:
            return await conn.fetch(sql)

    # ── entities ─────────────────────────────────────────────────────

    async def resolve_or_merge_entity(
        self,
        *,
        user_id: str,
        project_id: str | None,
        name: str,
        kind: str,
        source_type: str,
        confidence: float = 0.0,
        auto_created: bool = False,
        provenance: str = "human_authored",
        job_id: str | None = None,
    ) -> Entity:
        """Idempotent upsert keyed on (user, project, canonical name, kind).

        `source_types` ACCUMULATE — the conformance suite asserts this, and it is what
        distinguishes a real upsert from an adapter that rebuilds an object at the same key.
        AGE has no list-append in `SET`, so the accumulation is expressed as a coalesce over
        a CASE: keep the list when the type is already present, append when it is not.
        """
        canonical = canonicalize_entity_name(name)
        # MERGE keys on the identity tuple, not on a derived id — the derived-id scheme is
        # what T35 is retiring, and repeating it here would build the second adapter on the
        # defect the first one is being cured of.
        cy = f"""
        MERGE (e:Entity {{user_id: {_lit(user_id)}, project_id: {_lit(project_id)},
                          canonical_name: {_lit(canonical)}, kind: {_lit(kind)}}})
        SET e.id            = coalesce(e.id, {_lit(str(uuid4()))}),
            e.name          = coalesce(e.name, {_lit(name)}),
            e.canonical_version = coalesce(e.canonical_version, 1),
            e.confidence    = coalesce(e.confidence, {_lit(confidence)}),
            e.anchor_score  = coalesce(e.anchor_score, 0.0),
            e.aliases       = coalesce(e.aliases, [{_lit(name)}]),
            e.source_types  = CASE
                WHEN e.source_types IS NULL THEN [{_lit(source_type)}]
                WHEN {_lit(source_type)} IN e.source_types THEN e.source_types
                ELSE e.source_types + [{_lit(source_type)}] END
        RETURN e
        """
        rows = await self._run(cy)
        return _to_entity(_props(rows[0]["v"]))

    async def find_entities_by_name(
        self,
        *,
        user_id: str,
        project_id: str | None,
        name: str,
        include_archived: bool = False,
        exclude_project_ids: list[str] | None = None,
    ) -> list[Entity]:
        """Canonical-name and display-name matches, archived excluded by default.

        The archived default is not cosmetic: a resolver that matched an archived entity
        would silently re-anchor extraction onto something the author deliberately removed.
        """
        canonical = canonicalize_entity_name(name)
        where = [
            f"e.user_id = {_lit(user_id)}",
            f"(e.canonical_name = {_lit(canonical)} OR e.name = {_lit(name)})",
        ]
        if project_id is not None:
            where.append(f"e.project_id = {_lit(project_id)}")
        if not include_archived:
            where.append("e.archived_at IS NULL")
        for pid in exclude_project_ids or []:
            where.append(f"(e.project_id IS NULL OR e.project_id <> {_lit(pid)})")
        cy = f"MATCH (e:Entity) WHERE {' AND '.join(where)} RETURN e"
        return [_to_entity(_props(r["v"])) for r in await self._run(cy)]

    async def archive_entity(
        self, *, user_id: str, canonical_id: str, reason: str,
    ) -> Entity | None:
        """Soft-delete. Returns None when the id is not this user's.

        ⚠️ The `user_id` predicate is inside the MATCH, not applied to the result. A version
        that filtered the RETURN would still have performed the write — the conformance
        suite's `archiving_another_users_entity_is_a_miss_not_a_write` exists for exactly
        that mistake, and it is the shape a "just filter the output" fix produces.
        """
        cy = f"""
        MATCH (e:Entity {{id: {_lit(canonical_id)}, user_id: {_lit(user_id)}}})
        SET e.archived_at = {_lit(datetime.now(timezone.utc))},
            e.archive_reason = {_lit(reason)}
        RETURN e
        """
        rows = await self._run(cy)
        return _to_entity(_props(rows[0]["v"])) if rows else None

    async def restore_entity(self, *, user_id: str, canonical_id: str) -> Entity | None:
        cy = f"""
        MATCH (e:Entity {{id: {_lit(canonical_id)}, user_id: {_lit(user_id)}}})
        SET e.archived_at = null, e.archive_reason = null
        RETURN e
        """
        rows = await self._run(cy)
        return _to_entity(_props(rows[0]["v"])) if rows else None

    async def neighborhood(
        self,
        *,
        user_id: str,
        glossary_entity_id: str,
        project_id: str | None = None,
        rel_cap: int = 50,
    ) -> EntityDetail | None:
        """One entity plus its capped one-hop neighbourhood.

        `rel_cap` is part of the contract rather than a tuning knob — this feeds a context
        block, and an uncapped neighbourhood on a hub entity is how a prompt budget vanishes.
        """
        where = [f"e.user_id = {_lit(user_id)}",
                 f"e.glossary_entity_id = {_lit(glossary_entity_id)}"]
        if project_id is not None:
            where.append(f"e.project_id = {_lit(project_id)}")
        rows = await self._run(
            f"MATCH (e:Entity) WHERE {' AND '.join(where)} RETURN e")
        if not rows:
            return None
        entity = _to_entity(_props(rows[0]["v"]))
        rels = await self.relations_for(
            user_id=user_id, entity_id=entity.id, project_id=project_id, limit=rel_cap)
        return EntityDetail.model_validate(
            {**entity.model_dump(), "relations": [r.model_dump() for r in rels]})

    # ── relations ────────────────────────────────────────────────────

    async def upsert_relation(
        self,
        *,
        user_id: str,
        subject_id: str,
        predicate: str,
        object_id: str,
        confidence: float = 0.0,
        source_event_id: str | None = None,
        valid_from_ordinal: int | None = None,
    ) -> Relation:
        """Create or update one edge.

        ⚠️ AGE cannot parameterise a relationship TYPE any more than Neo4j can, and here the
        predicate is domain data — so the edge carries a fixed `:RELATES_TO` type with the
        predicate as a PROPERTY, matching the Neo4j adapter. That agreement is what lets T43
        compare the two at all.

        `valid_from_ordinal` uses `coalesce(param, existing)` so re-asserting an edge without
        a position cannot STRIP one that is already there — the exact defect T36 fixed on the
        Neo4j authoring path, not repeated here.
        """
        cy = f"""
        MATCH (s:Entity {{id: {_lit(subject_id)}, user_id: {_lit(user_id)}}})
        MATCH (o:Entity {{id: {_lit(object_id)}, user_id: {_lit(user_id)}}})
        MERGE (s)-[r:RELATES_TO {{predicate: {_lit(predicate)}, user_id: {_lit(user_id)}}}]->(o)
        SET r.id         = coalesce(r.id, {_lit(str(uuid4()))}),
            r.subject_id = {_lit(subject_id)},
            r.object_id  = {_lit(object_id)},
            r.confidence = {_lit(confidence)},
            r.valid_from_ordinal = coalesce({_lit(valid_from_ordinal)}, r.valid_from_ordinal),
            r.source_event_ids = CASE
                WHEN {_lit(source_event_id)} IS NULL THEN coalesce(r.source_event_ids, [])
                WHEN r.source_event_ids IS NULL THEN [{_lit(source_event_id)}]
                WHEN {_lit(source_event_id)} IN r.source_event_ids THEN r.source_event_ids
                ELSE r.source_event_ids + [{_lit(source_event_id)}] END
        RETURN r
        """
        rows = await self._run(cy)
        return _to_relation(_props(rows[0]["v"]))

    async def get_relation(self, *, user_id: str, relation_id: str) -> Relation | None:
        cy = f"""
        MATCH ()-[r:RELATES_TO {{id: {_lit(relation_id)}, user_id: {_lit(user_id)}}}]->()
        RETURN r
        """
        rows = await self._run(cy)
        # A MISS for another user's relation — the `user_id` in the pattern makes it a
        # non-match rather than a filtered read, so there is no existence oracle.
        return _to_relation(_props(rows[0]["v"])) if rows else None

    async def invalidate_relation(
        self, *, user_id: str, relation_id: str, valid_until: datetime | None = None,
    ) -> Relation | None:
        # Idempotent by construction: SET overwrites whatever `valid_until` held, so
        # re-invalidating moves the instant instead of failing.
        stamp = (valid_until or datetime.now(timezone.utc)).isoformat()
        cy = f"""
        MATCH ()-[r:RELATES_TO {{id: {_lit(relation_id)}, user_id: {_lit(user_id)}}}]->()
        SET r.valid_until = {_lit(stamp)}
        RETURN r
        """
        rows = await self._run(cy)
        return _to_relation(_props(rows[0]["v"])) if rows else None

    async def recreate_relation(
        self,
        *,
        user_id: str,
        subject_id: str,
        predicate: str,
        object_id: str,
        source_chapter: str | None = None,
        valid_from_ordinal: int | None = None,
    ) -> Relation | None:
        """Author-asserted: confidence 1.0 and `valid_until` RESURRECTED to NULL.

        MERGE matches on (subject, predicate, object, user) WITHOUT `valid_until`, which is
        the whole point — matching on it would mint a second edge beside the invalidated one
        instead of reviving it, and the author's correction would silently not take.
        """
        cy = f"""
        MATCH (s:Entity {{id: {_lit(subject_id)}, user_id: {_lit(user_id)}}})
        MATCH (o:Entity {{id: {_lit(object_id)}, user_id: {_lit(user_id)}}})
        MERGE (s)-[r:RELATES_TO {{predicate: {_lit(predicate)}, user_id: {_lit(user_id)}}}]->(o)
        SET r.id         = coalesce(r.id, {_lit(str(uuid4()))}),
            r.subject_id = {_lit(subject_id)},
            r.object_id  = {_lit(object_id)},
            r.confidence = 1.0,
            r.valid_until = NULL,
            r.valid_from_ordinal = coalesce({_lit(valid_from_ordinal)}, r.valid_from_ordinal)
        RETURN r
        """
        rows = await self._run(cy)
        return _to_relation(_props(rows[0]["v"])) if rows else None

    async def relations_for(
        self,
        *,
        user_id: str,
        entity_id: str,
        project_id: str | None = None,
        direction: RelationDirection = "both",
        min_confidence: float = 0.8,
        as_of: int | None = None,
        limit: int = 100,
    ) -> list[Relation]:
        """This entity's edges. `as_of=None` reads the HEAD.

        With `as_of=N`, the half-open convention `valid_from_ordinal <= N < valid_to_ordinal`
        applies and a **positionless edge is EXCLUDED** — it cannot be placed on the axis, and
        including it would mix untimed legacy data into an answer whose entire value is that
        it is timed.

        `direction="both"` is two MATCHes UNIONed at the SQL level, because AGE has no
        `CALL { … }` — difference 3. The Neo4j adapter expresses the same thing as a Cypher
        subquery; the results must agree, which is what T43 checks.
        """
        conf = f"r.confidence >= {_lit(min_confidence)}"
        if as_of is None:
            window = "true"
        else:
            window = (
                f"r.valid_from_ordinal IS NOT NULL AND r.valid_from_ordinal <= {_lit(as_of)} "
                f"AND (r.valid_to_ordinal IS NULL OR {_lit(as_of)} < r.valid_to_ordinal)"
            )
        # ⚠️ AN ARCHIVED PEER'S EDGES ARE EXCLUDED, matching the Neo4j repo's
        # `include_archived_peer=False` default. This was MISSING here and the property-based
        # differential suite found it (seed=1): after an `archive()`, AGE returned an edge
        # Neo4j did not —
        #     primary  =[('parent_of','0.85','12')]
        #     secondary=[('ally_of','0.7','5'), ('parent_of','0.85','12')]
        # The scripted shadow pass never archived a peer and then read relations, so nine
        # green operations had said nothing about this. It is a real behaviour difference,
        # not a comparison artifact: a caller would have seen a relation to an entity the
        # author archived.
        peer_live = "p.archived_at IS NULL"
        # T17 A1 2026-08-13 — the SUPERSEDED filter, which was missing. Neo4j's
        # `find_relations_for_entity` has always required `r.valid_until IS NULL`; this
        # adapter did not, so every soft-invalidated edge stayed in ordinary reads. Nothing
        # saw it: T43's shadow reported 9 of 9 operations AGREEING because no test ever
        # invalidated an edge and then read it back, and two implementations agree happily
        # about a case neither one is asked. The conformance rule that found it is
        # `test_invalidate_hides_the_edge_from_ordinary_reads_and_is_idempotent`.
        live = "r.valid_until IS NULL"
        out = (
            f"MATCH (a:Entity {{id: {_lit(entity_id)}, user_id: {_lit(user_id)}}})"
            f"-[r:RELATES_TO]->(p:Entity) "
            f"WHERE p.user_id = {_lit(user_id)} AND {peer_live} AND {live} AND {conf} AND {window} "
            f"RETURN r"
        )
        inc = (
            f"MATCH (p:Entity)-[r:RELATES_TO]->"
            f"(a:Entity {{id: {_lit(entity_id)}, user_id: {_lit(user_id)}}}) "
            f"WHERE p.user_id = {_lit(user_id)} AND {peer_live} AND {live} AND {conf} AND {window} "
            f"RETURN r"
        )
        parts = {"outgoing": [out], "incoming": [inc], "both": [out, inc]}[direction]
        rels: list[Relation] = []
        seen: set[str] = set()
        for part in parts:
            for row in await self._run(part):
                rel = _to_relation(_props(row["v"]))
                # A self-edge appears in BOTH halves of the union. Neo4j's subquery form
                # dedupes it inside the query; here the dedupe is explicit, or "both" would
                # report one loop twice and disagree with the other adapter.
                if rel.id and rel.id in seen:
                    continue
                seen.add(rel.id)
                rels.append(rel)
        return rels[:limit]

    async def add_evidence(
        self,
        *,
        user_id: str,
        target_label: str,
        target_id: str,
        source_id: str,
        extraction_model: str,
        confidence: float,
        job_id: str,
        quote: str | None = None,
    ):
        """`EVIDENCED_BY` + an ATOMIC counter bump, in one statement.

        ⚠️ **One statement is the invariant, not a style choice.** The port's docstring says
        so: writing the edge and then read-modify-writing the counter would satisfy the
        signature while letting `evidence_count` drift under concurrency, and the K11.9
        reconciler is only the offline net that catches drift. Never producing it is cheaper.

        Validation mirrors the repo's exactly — a port whose two implementations disagree
        about what is a *caller* error is a port that leaks its engine.
        """
        if not all((target_id, source_id, extraction_model, job_id)):
            raise ValueError("target_id/source_id/extraction_model/job_id must be non-empty")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence must be in [0,1], got {confidence}")

        # ⚠️ THE INCREMENT MUST HAPPEN ONLY ON CREATE, and AGE has no `ON CREATE SET` — so
        # existence is checked and the counter bumped inside ONE TRANSACTION rather than in
        # one statement. The first cut did `t.evidence_count = coalesce(...) + 1` on every
        # call, which is the exact drift this operation's port docstring warns about: the
        # conformance rule caught it on `[age]` while `[fake]` and `[neo4j]` passed.
        #
        # A transaction, not a single statement, is what makes it atomic here. Doing the
        # check outside one would let two concurrent extractions both see "absent" and both
        # increment — the read-modify-write the docstring rules out.
        from app.db.neo4j_repos.provenance import EvidenceWriteResult

        tag_probe = f"""
        MATCH (t:{target_label} {{id: {_lit(target_id)}, user_id: {_lit(user_id)}}})
              -[r:EVIDENCED_BY {{job_id: {_lit(job_id)}}}]->
              (s:ExtractionSource {{id: {_lit(source_id)}, user_id: {_lit(user_id)}}})
        RETURN r
        """
        merge = f"""
        MATCH (t:{target_label} {{id: {_lit(target_id)}, user_id: {_lit(user_id)}}})
        MATCH (s:ExtractionSource {{id: {_lit(source_id)}, user_id: {_lit(user_id)}}})
        MERGE (t)-[r:EVIDENCED_BY {{job_id: {_lit(job_id)}}}]->(s)
        SET r.extraction_model = {_lit(extraction_model)},
            r.confidence       = {_lit(confidence)},
            r.quote            = coalesce({_lit(quote)}, r.quote)
        RETURN r
        """
        bump = f"""
        MATCH (t:{target_label} {{id: {_lit(target_id)}, user_id: {_lit(user_id)}}})
        SET t.evidence_count = coalesce(t.evidence_count, 0) + 1
        RETURN t.evidence_count
        """
        read = f"""
        MATCH (t:{target_label} {{id: {_lit(target_id)}, user_id: {_lit(user_id)}}})
        RETURN coalesce(t.evidence_count, 0), coalesce(t.mention_count, 0)
        """

        def _wrap(cy: str, cols: str) -> str:
            tag = self._dollar_tag(cy)
            return f"SELECT * FROM cypher('{self._graph}', ${tag}${cy}${tag}$) as ({cols})"

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                existed = await conn.fetch(_wrap(tag_probe, "r agtype"))
                merged = await conn.fetch(_wrap(merge, "r agtype"))
                if not merged:
                    # Target or source absent under this user: "no evidence to record", not
                    # an error — the repo returns None here and the two must agree.
                    return None
                if not existed:
                    await conn.fetch(_wrap(bump, "n agtype"))
                counts = await conn.fetch(_wrap(read, "ev agtype, mn agtype"))

        return EvidenceWriteResult(
            evidence_count=int(_unwrap(counts[0]["ev"]) or 0),
            mention_count=int(_unwrap(counts[0]["mn"]) or 0),
            created=not existed,
        )

    # ── the event surface — NOT implemented, and loudly ───────────────

    # ⚠️ These two signatures are copied from the port EXACTLY, including `min_evidence`,
    # `include_archived` and the defaults. The first cut of this file guessed them
    # (`entity_id` singular, no `include_archived`, `limit=100`) and
    # `isinstance(store, GraphStore)` still returned **True** — `runtime_checkable` checks
    # method NAMES only. That is why `test_implementations_match_the_port_signatures`
    # exists, and why a Protocol is not a contract on its own.

    async def status_at_order(
        self,
        *,
        user_id: str,
        project_id: str | None,
        entity_ids: list[str],
        at_order: int,
        min_evidence: int = 1,
    ) -> dict[str, str]:
        """`{entity_id: status}` at a story position — the LATEST transition at or before it.

        ⚠️ **Fail-OPEN is the danger here, and `'active'` is the fallback**: an entity with no
        qualifying transition is alive. That is the Neo4j behaviour
        (`coalesce(latest.status, 'active')`) and it must be matched exactly, because the
        author-facing consequence of getting it wrong is asymmetric — a wrongly-`gone` entity
        disappears from a panel, while a wrongly-`active` one silently un-kills a character.

        **One query per entity, not an `UNWIND` + aggregate.** Neo4j does this in a single
        pass with `head(collect(s))`; AGE's aggregate handling across `OPTIONAL MATCH` is the
        kind of construct this migration has repeatedly found differs, and a per-entity loop
        is boring, obviously correct, and the shadow comparison's job is to catch it if it is
        not. Entity counts here are a handful (a canon check's cast), not a page of results.
        """
        out: dict[str, str] = {}
        for eid in entity_ids:
            where = [
                f"s.user_id = {_lit(user_id)}",
                f"s.entity_id = {_lit(eid)}",
                f"s.from_order <= {_lit(at_order)}",
                f"s.evidence_count >= {_lit(min_evidence)}",
            ]
            if project_id is not None:
                where.append(f"s.project_id = {_lit(project_id)}")
            rows = await self._run(
                f"MATCH (s:EntityStatus) WHERE {' AND '.join(where)} "
                f"RETURN s.status, s.from_order",
                columns="status agtype, from_order agtype",
            )
            latest, best = None, None
            for r in rows:
                order = _unwrap(r["from_order"])
                if best is None or (order is not None and order > best):
                    best, latest = order, _unwrap(r["status"])
            out[eid] = str(latest) if latest is not None else "active"
        return out

    # ── event corrections (T17/A2) ───────────────────────────────────
    #
    # ⚠️ `merge_event` and `update_event_fields` are NOT implemented here and RAISE. AGE
    # has no `apoc`-free equivalent of the ON MATCH branch this merge needs (min-wins
    # `event_order`, union-merged participants, upgrade-not-overwrite summary), and
    # `update_event_fields` needs the same-statement `before` snapshot that the OCC
    # correction event is written from. Guessing either would produce an adapter that
    # ANSWERS WRONGLY, and the port's own rule is that an operation which answers wrongly
    # is worse than one that refuses — an empty return here would look like "no such
    # event" to every caller. Tracked as D-AGE-EVENT-WRITE-UNIMPLEMENTED.

    async def events_page(
        self,
        *,
        user_id: str,
        project_id: str | None = None,
        after: int | str | None = None,
        before: int | str | None = None,
        axis: EventAxis = "narrative",
        participants: list[str] | None = None,
        q: str | None = None,
        sort_dir: str = "asc",
        limit: int = 50,
        offset: int = 0,
        exclude_project_ids: list[str] | None = None,
    ) -> tuple[list[Event], int]:
        """A3 — the browse, built on this adapter's own window read.

        Paged in PYTHON, not in Cypher, and that is a deliberate v1 limit rather than an
        oversight: AGE has no `count(*)`-with-`SKIP`/`LIMIT` shape that returns the page and
        the unpaged total in one statement, so the honest choices were two round trips that
        can disagree under concurrent writes, or one read the caller pays for. The bound
        below is what makes it safe to say so — past it, `total` would be a LIE about how
        many matched, so it refuses instead.
        """
        rows = await self.events_in_window(
            user_id=user_id, project_id=project_id, after=after, before=before, axis=axis,
            limit=_AGE_BROWSE_SCAN_CAP,
        )
        if len(rows) >= _AGE_BROWSE_SCAN_CAP:
            raise NotImplementedError(
                f"AgeGraphStore.events_page — the filter matched at least "
                f"{_AGE_BROWSE_SCAN_CAP} events, the in-Python paging cap. Returning a page "
                "here would report a `total` that is an artifact of the cap rather than the "
                "count of what matched, and a wrong total is worse than a refusal. See "
                "D-AGE-BROWSE-PAGES-IN-PYTHON."
            )
        excluded = set(exclude_project_ids or ())
        wanted = set(participants or ())
        needle = (q or "").strip().lower()
        matched = [
            e for e in rows
            if e.project_id not in excluded
            and (not wanted or wanted.intersection(e.participants or ()))
            and (not needle or needle in (e.title or "").lower()
                 or needle in (e.summary or "").lower())
        ]
        if sort_dir == "desc":
            matched.reverse()
        return matched[offset:offset + limit], len(matched)

    async def merge_fact(
        self,
        *,
        user_id: str,
        project_id: str | None,
        type: str,
        content: str,
        confidence: float = 0.0,
        pending_validation: bool = False,
        source_type: str = "book_content",
        source_chapter: str | None = None,
        provenance: str = "human_authored",
        subject_id: str | None = None,
        from_order: int | None = None,
        valid_from_ordinal: int | None = None,
        event_date_iso: str | None = None,
        predicate: str | None = None,
        object: str | None = None,
        maintain_chain: bool = False,
    ) -> Fact:
        raise NotImplementedError(
            "AgeGraphStore.merge_fact — see D-AGE-FACT-WRITE-UNIMPLEMENTED. The plain upsert is "
            "expressible; `maintain_chain` is the problem: re-deriving the valid_to_ordinal "
            "chain for a (subject, type) family needs an ordered window over sibling facts in "
            "ONE statement, which AGE has no APOC-free shape for. Refusing rather than "
            "half-writing: an accepted flag that closed no interval leaves every fact open "
            "forever, and an as-of read then answers with the latest value at every position — "
            "a book with no history, reported as a working timeline."
        )

    async def facts_for(
        self,
        *,
        user_id: str,
        subject_id: str,
        type: str | None = None,
        as_of: int | None = None,
        limit: int = 100,
    ) -> list[Fact]:
        """Facts ABOUT one subject (SPEC §1.1).

        ⚠️ **THIS ONE IS IMPLEMENTED, AND `merge_fact` DIRECTLY ABOVE IS NOT.** That is not an
        inconsistency — it is what rule 9 actually says. An adapter raises when it CANNOT
        honour an operation; AGE cannot honour `merge_fact` because `maintain_chain` needs an
        ordered window over sibling facts in one statement. This is a plain `WHERE`, the same
        half-open shape `relations_for` already expresses here. Refusing a read AGE can answer
        would be a lie in the opposite direction, and it would strand any future AGE fact
        write behind a second refusal it never earned.

        The cost is stated rather than hidden: **no conformance rule can seed this adapter
        through the port**, because the only fact write refuses. So the fact rules in
        `test_graph_store_conformance.py` seed AGE with raw Cypher through `_run` and read
        back through here — the READ is what is under test, and seeding it any other way
        would leave this method as untested code shipped green.
        """
        if not subject_id:
            raise ValueError("subject_id must be a non-empty string")
        type_pred = "true" if type is None else f"f.type = {_lit(type)}"
        if as_of is None:
            window = "true"
        else:
            # Half-open, POSITIONLESS EXCLUDED — the same convention `relations_for` applies
            # above, spelled out rather than shared because AGE takes literals, not params.
            # The `IS NOT NULL` is legibility, not behaviour: biting it out stays green here
            # too, since AGE's NULL comparison already drops the row. Documented so nobody
            # deletes it believing they found dead weight, and nobody trusts it as a guard.
            window = (
                f"f.valid_from_ordinal IS NOT NULL AND f.valid_from_ordinal <= {_lit(as_of)} "
                f"AND (f.valid_to_ordinal IS NULL OR {_lit(as_of)} < f.valid_to_ordinal)"
            )
        cy = (
            f"MATCH (f:Fact)-[:ABOUT]->(e:Entity {{id: {_lit(subject_id)}, "
            f"user_id: {_lit(user_id)}}}) "
            f"WHERE f.user_id = {_lit(user_id)} AND f.valid_until IS NULL "
            f"AND {type_pred} AND {window} "
            f"RETURN f"
        )
        facts = [_to_fact(_props(row["v"])) for row in await self._run(cy)]
        # Ordered in Python, not in Cypher: AGE sorts NULLs first under ASC, which would put
        # positionless facts at the FRONT of a head read and misread as "earliest". Neo4j's
        # arm uses a null-sink in the ORDER BY for the same reason — two engines, one order,
        # which is the whole point of T43 being able to compare them.
        facts.sort(key=lambda f: (f.valid_from_ordinal is None, f.valid_from_ordinal or 0))
        return facts[:limit]


    async def get_event(self, *, user_id: str, event_id: str) -> Event | None:
        cy = f"""
        MATCH (e:Event {{id: {_lit(event_id)}, user_id: {_lit(user_id)}}})
        RETURN e
        """
        rows = await self._run(cy)
        return _to_event(_props(rows[0]["v"])) if rows else None

    async def archive_event(self, *, user_id: str, event_id: str) -> Event | None:
        # Idempotent: coalesce keeps the FIRST archive instant, so re-archiving succeeds
        # without rewriting when the event was archived.
        stamp = datetime.now(timezone.utc).isoformat()
        cy = f"""
        MATCH (e:Event {{id: {_lit(event_id)}, user_id: {_lit(user_id)}}})
        SET e.archived_at = coalesce(e.archived_at, {_lit(stamp)})
        RETURN e
        """
        rows = await self._run(cy)
        return _to_event(_props(rows[0]["v"])) if rows else None

    async def merge_event(
        self,
        *,
        user_id: str,
        project_id: str | None,
        title: str,
        summary: str | None = None,
        chapter_id: str | None = None,
        event_order: int | None = None,
        chronological_order: int | None = None,
        event_date_iso: str | None = None,
        time_cue: str | None = None,
        participants: list[str] | None = None,
        source_type: str = "book_content",
        confidence: float = 0.0,
    ) -> Event:
        raise NotImplementedError(
            "AgeGraphStore.merge_event — see D-AGE-EVENT-WRITE-UNIMPLEMENTED. The ON MATCH "
            "branch (min-wins event_order for CM4 spoiler-safety, union-merged participants, "
            "upgrade-not-overwrite summary) has no APOC-free AGE equivalent yet. Refusing "
            "rather than half-merging: a wrong event_order is silent in both directions."
        )

    async def update_event_fields(
        self,
        *,
        user_id: str,
        event_id: str,
        title: str | None,
        summary: str | None,
        time_cue: str | None,
        event_date_iso: str | None,
        expected_version: int,
    ) -> tuple[Event | None, dict | None]:
        raise NotImplementedError(
            "AgeGraphStore.update_event_fields — see D-AGE-EVENT-WRITE-UNIMPLEMENTED. Needs "
            "the same-statement pre-edit `before` snapshot the OCC correction event is "
            "written from; without it a caller would silently lose the audit half."
        )

    async def events_in_window(
        self,
        *,
        user_id: str,
        project_id: str | None = None,
        after: int | str | None = None,
        before: int | str | None = None,
        axis: EventAxis = "narrative",
        include_archived: bool = False,
        limit: int = 200,
    ) -> list[Event]:
        """Events between two bounds on ONE axis. Three axes, three different questions.

        `narrative` = authored `event_order` · `chronological` = in-story order, where undated
        events sink last · `date` = the parsed `event_date_iso` timeline. Collapsing them into
        one "time" parameter would make a caller unable to ask the one it means — the port's
        own docstring says so, and this adapter keeps them distinct rather than aliasing two
        of them to the cheap one.
        """
        field = {
            "narrative": "event_order",
            "chronological": "chronological_order",
            "date": "event_date_iso",
        }[axis]

        where = [f"e.user_id = {_lit(user_id)}"]
        if project_id is not None:
            where.append(f"e.project_id = {_lit(project_id)}")
        if after is not None:
            where.append(f"e.{field} > {_lit(after)}")
        if before is not None:
            where.append(f"e.{field} < {_lit(before)}")
        if not include_archived:
            where.append("e.archived_at IS NULL")

        rows = await self._run(
            f"MATCH (e:Event) WHERE {' AND '.join(where)} RETURN e")
        events = [_to_event(_props(r["v"])) for r in rows]

        # Sorted in PYTHON, deliberately. Neo4j orders with
        # `coalesce(e.event_order, 9223372036854775807)` so unplaced events sink last; AGE's
        # ordering over a NULL property is exactly the sort of engine-specific behaviour this
        # comparison exists to avoid depending on. Doing it here makes the two adapters agree
        # by construction on the one thing a caller can actually see — the sequence.
        sink = float("inf")
        events.sort(key=lambda e: (
            sink if getattr(e, field, None) is None else getattr(e, field),
            e.title or "",
        ))
        return events[:limit]
