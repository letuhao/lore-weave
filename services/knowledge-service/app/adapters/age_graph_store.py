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

**4 · Parameters DO reach Cypher — this entry used to say the opposite and was wrong.**
It read: *"AGE takes a `$1`-style argument to `cypher()` only as a whole agtype map, and
referencing it inside the query is limited. Values are therefore interpolated."* Measured
2026-08-22 (T83) against the AGE this project runs — **1.7.0 on PostgreSQL 18.4** — a named
`$user_id` resolves from that map, and so do several parameters at once, a NULL in an optional
filter, a list, a parameter inside `MERGE`/`SET`, and a hostile string, which comes back
treated as DATA rather than as Cypher.

So `_lit` and its interpolation are a **choice this adapter is still making, not a constraint
the engine imposes** — and the choice costs something specific: `_lit`'s own docstring calls
itself "the tenancy boundary", which means a hand-rolled escaper stands where a bound parameter
would make the property structural. `app/db/age_session.py` binds instead, and 12 repo
functions run through it against a live AGE graph. Migrating this adapter onto bound parameters
is a separate unit; the claim is corrected here so nobody inherits it as a fact.

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
from app.db.neo4j_repos.canonical import canonicalize_text as _canonicalize_text
# `event_id` is aliased because `update_event_fields` takes a PARAMETER of that name;
# an unaliased import would be shadowed inside the method that needs it most.
from app.db.neo4j_repos.events import Event, event_id as _event_id
from app.db.neo4j_repos.facts import fact_id as _fact_id
from app.db.neo4j_repos.temporal import ORDINAL_OPEN_CEILING as _ORDINAL_OPEN_CEILING
from app.domain.graph_labels import COUNTABLE_LABELS
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
            # ⚠️ These seven were MISSING, and the event-write skips hid it. `version` and
            # `archived_at` are asserted by conformance rules that skipped for `age` because
            # they need `merge_event` to create the row -- so un-skipping the writes is what
            # surfaced them. A skip does not only hide the operation it names; it hides every
            # assertion downstream of it.
            "event_date_iso": props.get("event_date_iso"),
            "time_cue": props.get("time_cue"),
            "participants": props.get("participants") or [],
            "source_types": props.get("source_types") or [],
            "confidence": props.get("confidence") or 0.0,
            "archived_at": props.get("archived_at"),
            "version": props.get("version") or 1,
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
            f"MATCH (e:Entity) WHERE {' AND '.join(where)} "
            f"RETURN e ORDER BY e.project_id ASC")
        if not rows:
            return None
        # Neo4j's `ORDER BY e.project_id ASC` + take-the-first: without a project scope the
        # glossary FK can legitimately match one node per project, and both adapters must
        # pick the SAME one or an unscoped read silently depends on the engine.
        entity = _to_entity(_props(rows[0]["v"]))

        # ⚠️ NOT `self.relations_for(...)`, which was the original delegate and is a
        # DIFFERENT query. Its defaults apply `confidence >= 0.8` and exclude edges to an
        # archived peer; `_GET_NEIGHBORHOOD_BY_GLOSSARY_ID_CYPHER` filters on
        # `r.valid_until IS NULL` alone. Delegating dropped every low-confidence edge and
        # every edge to an archived peer from this adapter's answer only — a silent
        # under-report, not an error, and invisible to a suite that never called it.
        erows = await self._run(
            f"MATCH (subj:Entity)-[r:RELATES_TO]->(obj:Entity) "
            f"WHERE (subj.id = {_lit(entity.id)} OR obj.id = {_lit(entity.id)}) "
            f"AND r.user_id = {_lit(user_id)} AND r.valid_until IS NULL "
            f"RETURN r, subj, obj ORDER BY r.confidence DESC, r.created_at DESC",
            columns="r agtype, subj agtype, obj agtype",
        )
        relations: list[Relation] = []
        for row in erows:
            rel = _to_relation(_props(row["r"]))
            sp, op_ = _props(row["subj"]), _props(row["obj"])
            rel.subject_name, rel.subject_kind = sp.get("name"), sp.get("kind")
            rel.object_name, rel.object_kind = op_.get("name"), op_.get("kind")
            relations.append(rel)

        # `total` is the UNCAPPED count and the cap is applied after it — the pair is what
        # tells a caller its neighbourhood was cut. Computing the cap without the total
        # (the original shape) reports `relations_truncated=False` on every hub entity.
        total = len(relations)
        capped = relations[:rel_cap]
        return EntityDetail(
            entity=entity,
            relations=capped,
            relations_truncated=total > len(capped),
            total_relations=total,
        )

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
        """Content-keyed upsert, plus the F3 story-time interval chain.

        🔴 `D-AGE-FACT-WRITE-UNIMPLEMENTED` said `maintain_chain` *"needs an ordered window
        over sibling facts in ONE statement, which AGE has no APOC-free shape for"*. **One
        statement was never the requirement — one TRANSACTION was**, which is the same
        conflation T58 corrected for `update_event_fields` and which the 2026-08-11 construct
        probe had already settled: on AGE the single-statement form is the WRONG one, because
        Postgres does not guarantee evaluation order inside a CTE.

        So the chain is re-derived from the family read in the SAME transaction as the merge.
        A concurrent writer cannot interleave: it would have to read the family too, and the
        `MERGE` above has already taken the row locks its own write needs.
        """
        if not content:
            raise ValueError("content must be a non-empty string")
        if not source_type:
            raise ValueError("source_type must be a non-empty string")
        fid = _fact_id(user_id=user_id, project_id=project_id, type=type, content=content)
        canonical_content = _canonicalize_text(content)
        norm_chapter = source_chapter or None
        norm_date = event_date_iso or None
        # F3 — an explicit valid_from_ordinal wins, else the reading-axis `from_order`. They
        # are the same ordinal; the two names exist because one is authored and one derived.
        eff_from = valid_from_ordinal if valid_from_ordinal is not None else from_order
        stamp = datetime.now(timezone.utc).isoformat()
        ceil_ = _ORDINAL_OPEN_CEILING

        # Tenancy in the MERGE KEY, not a trailing `WITH … WHERE` — on AGE 1.7.0 a `WITH`
        # after `SET` SILENTLY DISCARDS THE WRITE (measured, T58). `fact_id` hashes user_id,
        # so the pair cannot disagree.
        merge = f"""
        MERGE (f:Fact {{id: {_lit(fid)}, user_id: {_lit(user_id)}}})
        SET f.project_id        = coalesce(f.project_id, {_lit(project_id)}),
            f.type              = coalesce(f.type, {_lit(type)}),
            f.content           = coalesce(f.content, {_lit(content)}),
            f.canonical_content = coalesce(f.canonical_content, {_lit(canonical_content)}),
            f.source_chapter    = coalesce(f.source_chapter, {_lit(norm_chapter)}),
            f.evidence_count    = coalesce(f.evidence_count, 0),
            f.created_at        = coalesce(f.created_at, {_lit(stamp)}),
            f.valid_from        = coalesce(f.valid_from, {_lit(stamp)}),
            f.from_order        = coalesce(f.from_order, {_lit(from_order)}),
            f.valid_from_ordinal = coalesce(f.valid_from_ordinal, {_lit(eff_from)}),
            f.valid_to_ordinal_eff = coalesce(f.valid_to_ordinal_eff, {_lit(ceil_)}),
            f.predicate         = coalesce(f.predicate, {_lit(predicate)}),
            f.object            = coalesce(f.object, {_lit(object)}),
            f.event_date_iso = CASE
                WHEN {_lit(norm_date)} IS NULL THEN f.event_date_iso
                WHEN f.event_date_iso IS NULL THEN {_lit(norm_date)}
                WHEN size({_lit(norm_date)}) > size(f.event_date_iso) THEN {_lit(norm_date)}
                ELSE f.event_date_iso END,
            f.source_types = CASE
                WHEN f.source_types IS NULL THEN [{_lit(source_type)}]
                WHEN {_lit(source_type)} IN f.source_types THEN f.source_types
                ELSE f.source_types + [{_lit(source_type)}] END,
            f.provenances = CASE
                WHEN f.provenances IS NULL THEN [{_lit(provenance)}]
                WHEN {_lit(provenance)} IN f.provenances THEN f.provenances
                ELSE f.provenances + [{_lit(provenance)}] END,
            f.confidence = CASE
                WHEN f.confidence IS NULL THEN {_lit(confidence)}
                WHEN {_lit(confidence)} > f.confidence THEN {_lit(confidence)}
                ELSE f.confidence END,
            f.pending_validation = CASE
                WHEN f.confidence IS NULL THEN {_lit(pending_validation)}
                WHEN {_lit(confidence)} > f.confidence THEN {_lit(pending_validation)}
                ELSE f.pending_validation END,
            f.updated_at = {_lit(stamp)}
        RETURN f
        """
        link = f"""
        MATCH (f:Fact {{id: {_lit(fid)}, user_id: {_lit(user_id)}}}),
              (e:Entity {{id: {_lit(subject_id)}, user_id: {_lit(user_id)}}})
        MERGE (f)-[:ABOUT]->(e)
        RETURN f
        """
        # The chain family: every OPEN, POSITIONED fact of this (subject, type). Read
        # ordered so the derivation below is a plain scan rather than a sort of its own.
        family = f"""
        MATCH (f:Fact)-[:ABOUT]->(e:Entity {{id: {_lit(subject_id)},
                                            user_id: {_lit(user_id)}}})
        WHERE f.user_id = {_lit(user_id)} AND f.type = {_lit(type)}
              AND f.valid_from_ordinal IS NOT NULL
        RETURN f
        """

        def _wrap(cy: str, cols: str = "v agtype") -> str:
            tag = self._dollar_tag(cy)
            return f"SELECT * FROM cypher('{self._graph}', ${tag}${cy}${tag}$) as ({cols})"

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(_wrap(merge))
                if not rows:
                    raise RuntimeError(
                        f"merge_fact: AGE returned no row for fact {fid} — the write did "
                        f"not land"
                    )
                out = _props(rows[0]["v"])
                if subject_id:
                    await conn.fetch(_wrap(link))
                    if maintain_chain and eff_from is not None:
                        sibs = [_props(r["v"]) for r in await conn.fetch(_wrap(family))]
                        for cy in self._chain_writes(sibs, user_id, stamp):
                            await conn.fetch(_wrap(cy))
                        # Re-read: the chain may have closed THIS fact's own interval, and
                        # returning the pre-chain projection would hand the caller a fact
                        # whose valid_to_ordinal is null when the store says otherwise.
                        again = await conn.fetch(_wrap(f"""
                        MATCH (f:Fact {{id: {_lit(fid)}, user_id: {_lit(user_id)}}})
                        RETURN f
                        """))
                        if again:
                            out = _props(again[0]["v"])
        return _to_fact(out)

    def _chain_writes(
        self, sibs: list[dict], user_id: str, stamp: str
    ) -> list[str]:
        """F3 chain re-derivation — the Cypher writes, derived in Python from one read.

        Mirrors `temporal.MAINTAIN_FACT_CHAIN_CYPHER` clause for clause:

        * only OPEN instances participate (`valid_until IS NULL`);
        * the next bound is the next **STRICTLY-GREATER** `valid_from_ordinal`, never an
          equal one — two facts sharing an ordinal (same-chapter ties, which carry no
          per-item offset) must not close each other into a zero-width `[base, base)`
          interval that is invisible at every as-of read. That was the A2 bug, and it is
          the reason this is not simply "close each fact at the next one's start";
        * a `valid_to_pinned` instance is an AUTHORED input, not a derivation — skipped
          entirely, timestamp included, so an operator reading `updated_at` is not told the
          chain rewrote something it did not.
        """
        openish = [
            s for s in sibs
            if s.get("valid_until") in (None, "")
            and s.get("valid_from_ordinal") is not None
        ]
        openish.sort(key=lambda s: (s["valid_from_ordinal"], s.get("created_at") or ""))
        ordinals = sorted({s["valid_from_ordinal"] for s in openish})
        writes: list[str] = []
        for s in openish:
            if s.get("valid_to_pinned"):
                continue
            cur = s["valid_from_ordinal"]
            greaters = [o for o in ordinals if o > cur]
            to_ord = greaters[0] if greaters else None
            eff = greaters[0] if greaters else _ORDINAL_OPEN_CEILING
            writes.append(f"""
            MATCH (f:Fact {{id: {_lit(s.get("id"))}, user_id: {_lit(user_id)}}})
            SET f.valid_to_ordinal = {_lit(to_ord)},
                f.valid_to_ordinal_eff = {_lit(eff)},
                f.updated_at = {_lit(stamp)}
            RETURN f
            """)
        return writes

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
        """Idempotent upsert, keyed exactly as the Neo4j arm keys it.

        AGE has no `ON CREATE` / `ON MATCH`, so every assignment below is written as ONE
        expression that degenerates correctly on create — `coalesce(e.x, …)` for create-only
        fields, and for the accumulating ones the same expression that merges also produces
        the initial value when the property is absent. That is not a trick: min-wins against
        a null order IS the incoming order, and a union against an absent list IS the
        incoming list. Proven both ways on AGE 1.7.0 in T58, including the re-run.

        🔴 `D-AGE-EVENT-WRITE-UNIMPLEMENTED` said this had "no APOC-free AGE equivalent".
        Refuted by T57/T58: the list union is a plain Cypher list comprehension AGE accepts,
        so it needs neither APOC, nor the SQL host, nor a read-modify-write — and therefore
        no lock. The measurement is `docs/measurements/2026-08-22-age-event-write-probe.md`.

        ⚠️ **Tenancy is in the MERGE KEY, not in a trailing filter, and that is not a style
        choice.** The first cut wrote `… SET … WITH e WHERE e.user_id = $u RETURN e`, mirroring
        the Neo4j arm. On AGE 1.7.0 a `WITH` clause after `SET` **silently discards the SET** —
        measured: the node was created and every assigned property came back empty, with no
        error. Keying the MERGE on `(id, user_id)` is safe because `event_id()` already hashes
        `user_id` into the id, so the pair cannot disagree.
        """
        if not title:
            raise ValueError("title must be a non-empty string")
        if not source_type:
            raise ValueError("source_type must be a non-empty string")
        eid = _event_id(
            user_id=user_id, project_id=project_id, chapter_id=chapter_id, title=title)
        canonical_title = _canonicalize_text(title)
        # R1, mirroring the repo: order-preserving dedup BEFORE the write, so a sloppy
        # extractor passing ["a","a","b"] cannot land a duplicate on the create path. The
        # union below only dedups against what is already stored.
        deduped = list(dict.fromkeys(participants or []))
        # R4: "" → null so the coalesce reads it as "no new value" rather than as a
        # deliberate clear. Same for time_cue.
        norm_summary = summary or None
        norm_time_cue = time_cue or None
        stamp = datetime.now(timezone.utc).isoformat()
        inc = _lit(deduped)
        cy = f"""
        MERGE (e:Event {{id: {_lit(eid)}, user_id: {_lit(user_id)}}})
        SET e.project_id         = coalesce(e.project_id, {_lit(project_id)}),
            e.title              = coalesce(e.title, {_lit(title)}),
            e.canonical_title    = coalesce(e.canonical_title, {_lit(canonical_title)}),
            e.chapter_id         = coalesce(e.chapter_id, {_lit(chapter_id)}),
            e.evidence_count     = coalesce(e.evidence_count, 0),
            e.mention_count      = coalesce(e.mention_count, 0),
            e.version            = coalesce(e.version, 1),
            e.created_at         = coalesce(e.created_at, {_lit(stamp)}),
            e.summary            = coalesce(e.summary, {_lit(norm_summary)}),
            e.time_cue           = coalesce(e.time_cue, {_lit(norm_time_cue)}),
            e.chronological_order = coalesce(e.chronological_order,
                                             {_lit(chronological_order)}),
            e.event_order = CASE
                WHEN {_lit(event_order)} IS NULL THEN e.event_order
                WHEN e.event_order IS NULL THEN {_lit(event_order)}
                WHEN {_lit(event_order)} < e.event_order THEN {_lit(event_order)}
                ELSE e.event_order END,
            e.event_date_iso = CASE
                WHEN {_lit(event_date_iso)} IS NULL THEN e.event_date_iso
                WHEN e.event_date_iso IS NULL THEN {_lit(event_date_iso)}
                WHEN size({_lit(event_date_iso)}) > size(e.event_date_iso)
                    THEN {_lit(event_date_iso)}
                ELSE e.event_date_iso END,
            e.participants = CASE
                WHEN size({inc}) = 0 THEN coalesce(e.participants, [])
                ELSE coalesce(e.participants, [])
                     + [p IN {inc} WHERE NOT p IN coalesce(e.participants, [])] END,
            e.source_types = CASE
                WHEN e.source_types IS NULL THEN [{_lit(source_type)}]
                WHEN {_lit(source_type)} IN e.source_types THEN e.source_types
                ELSE e.source_types + [{_lit(source_type)}] END,
            e.confidence = CASE
                WHEN e.confidence IS NULL THEN {_lit(confidence)}
                WHEN {_lit(confidence)} > e.confidence THEN {_lit(confidence)}
                ELSE e.confidence END,
            e.updated_at = {_lit(stamp)}
        RETURN e
        """
        rows = await self._run(cy)
        if not rows:
            # MERGE always returns its node, so an empty result means the write did not
            # happen. Raising beats returning a fabricated Event: the caller would persist
            # it as if the merge had landed.
            raise RuntimeError(
                f"merge_event: AGE returned no row for event {eid} — the write did not land"
            )
        return _to_event(_props(rows[0]["v"]))

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
        """User-edit with optimistic concurrency; returns `(event, before)`.

        The Neo4j arm does this in one statement with `FOREACH (_ IN CASE … | SET …)`, a
        conditional-write idiom AGE does not have. Two statements in ONE TRANSACTION instead,
        which is what `D-AGE-EVENT-WRITE-UNIMPLEMENTED` actually needed — it says
        "same-statement", and the 2026-08-11 construct probe had already established that the
        single-statement form is the WRONG one on AGE: Postgres does not guarantee evaluation
        order inside a CTE, and it returned `was_created=false` for a node that did not exist.
        Same transaction is the requirement; same statement was never it.

        The version check is a compare-and-swap, not a lock: the UPDATE carries
        `WHERE coalesce(e.version, 1) = <observed>`, so a writer that lost a race updates
        nothing and gets `VersionMismatchError` rather than silently overwriting the winner.
        """
        from app.db.repositories import VersionMismatchError

        canonical_title = _canonicalize_text(title) if title is not None else None
        stamp = datetime.now(timezone.utc).isoformat()
        read = f"""
        MATCH (e:Event {{id: {_lit(event_id)}}})
        WHERE e.user_id = {_lit(user_id)}
        RETURN e
        """

        def _wrap(cy: str, cols: str) -> str:
            tag = self._dollar_tag(cy)
            return f"SELECT * FROM cypher('{self._graph}', ${tag}${cy}${tag}$) as ({cols})"

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(_wrap(read, "v agtype"))
                if not rows:
                    return None, None
                props = _props(rows[0]["v"])
                current = props.get("version") or 1
                # §6.3 — the pre-edit snapshot the correction event is written from. Taken
                # from the SAME transaction as the write, so it cannot record a state the
                # edit did not start from.
                before = {
                    "title": props.get("title"),
                    "summary": props.get("summary"),
                    "time_cue": props.get("time_cue"),
                    "event_date_iso": props.get("event_date_iso"),
                    "participants": props.get("participants") or [],
                }
                if current != expected_version:
                    raise VersionMismatchError(_to_event(props))
                write = f"""
                MATCH (e:Event {{id: {_lit(event_id)}}})
                WHERE e.user_id = {_lit(user_id)}
                  AND coalesce(e.version, 1) = {_lit(current)}
                SET e.title = CASE WHEN {_lit(title)} IS NULL
                                   THEN e.title ELSE {_lit(title)} END,
                    e.canonical_title = CASE WHEN {_lit(canonical_title)} IS NULL
                                   THEN e.canonical_title ELSE {_lit(canonical_title)} END,
                    e.summary = CASE WHEN {_lit(summary)} IS NULL
                                   THEN e.summary ELSE {_lit(summary)} END,
                    e.time_cue = CASE WHEN {_lit(time_cue)} IS NULL
                                   THEN e.time_cue ELSE {_lit(time_cue)} END,
                    e.event_date_iso = CASE WHEN {_lit(event_date_iso)} IS NULL
                                   THEN e.event_date_iso ELSE {_lit(event_date_iso)} END,
                    e.version = {_lit(current + 1)},
                    e.updated_at = {_lit(stamp)}
                RETURN e
                """
                written = await conn.fetch(_wrap(write, "v agtype"))
                if not written:
                    # Someone else bumped the version between the read and the write. The
                    # CAS refused, which is the whole point — report the clash rather than
                    # returning the row we failed to change.
                    raise VersionMismatchError(_to_event(props))
                return _to_event(_props(written[0]["v"])), before

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

    # ── the project as a whole ───────────────────────────────────────

    async def project_graph_stats(
        self, *, user_id: str, project_id: str,
    ) -> dict[str, int]:
        """One count per label in `COUNTABLE_LABELS`.

        **Three round trips, not one `UNION ALL`.** Neo4j runs this as a single call-subquery
        so a stats card is one hop; AGE's `UNION ALL` inside `cypher()` has to agree with the
        column list declared in the SQL wrapper, and a four-arm union of differently-shaped
        rows is exactly the construct this migration keeps finding a difference in. Three
        boring counts cannot be wrong in a way the shadow would have to catch. A stats card
        is not on a hot path.

        The label is INTERPOLATED because Cypher cannot parameterise one — `COUNTABLE_LABELS`
        is the injection barrier and it is iterated, never taken from a caller.
        """
        out: dict[str, int] = {}
        for label in COUNTABLE_LABELS:
            rows = await self._run(
                f"MATCH (n:{label}) WHERE n.user_id = {_lit(user_id)} "
                f"AND n.project_id = {_lit(project_id)} RETURN count(n)",
                columns="c agtype",
            )
            out[f"{label.lower()}_count"] = int(rows[0]["c"]) if rows else 0
        return out
