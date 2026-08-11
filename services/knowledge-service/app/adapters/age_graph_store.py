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

    async def _run(self, cypher: str, *, columns: str = "v agtype") -> list:
        sql = f"SELECT * FROM cypher('{self._graph}', $CY${cypher}$CY$) as ({columns})"
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
        out = (
            f"MATCH (a:Entity {{id: {_lit(entity_id)}, user_id: {_lit(user_id)}}})"
            f"-[r:RELATES_TO]->(p:Entity) "
            f"WHERE p.user_id = {_lit(user_id)} AND {conf} AND {window} RETURN r"
        )
        inc = (
            f"MATCH (p:Entity)-[r:RELATES_TO]->"
            f"(a:Entity {{id: {_lit(entity_id)}, user_id: {_lit(user_id)}}}) "
            f"WHERE p.user_id = {_lit(user_id)} AND {conf} AND {window} RETURN r"
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
