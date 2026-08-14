"""`GraphStore` on Kuzu — the second X1 candidate (plan T42).

The entity surface is implemented; every other operation RAISES naming its section, which is
this repo's convention for an adapter that cannot honour something (`AgeGraphStore` refuses the
two event writes the same way). Refusing is not a gap to be embarrassed about: a half-written
operation that accepts a flag it does not honour is how a book ends up with no history and a
timeline that reports as working.

THREE THINGS THIS ADAPTER DOES THAT NEITHER OTHER ONE DOES, each measured before it was written
------------------------------------------------------------------------------------------
**1 · Identity is MATCH-then-CREATE, not MERGE.** Kuzu demands the primary key in every MERGE:

    MERGE (n:Entity {user_id:…, canonical_name:…, kind:…}) ON CREATE SET n.id = <uuid>
      -> Binder exception: Create node n expects primary key id as input.

and it offers no uniqueness constraint on a non-PK column (`UNIQUE(a)` is a parser error). The
port MERGEs on the IDENTITY TUPLE on purpose — `age_graph_store` records why: *"the derived-id
scheme is what T35 is retiring, and repeating it here would build the second adapter on the
defect the first one is being cured of."* Making the PK `hash(user, project, canonical_name,
kind)` is therefore the one escape that must not be taken. So: look up by the tuple, create with
a fresh UUID when absent, and MERGE by the now-known PK to update.

**2 · That read-then-write is serialised, and Kuzu's own limitation is what makes it sound.**
With no unique index to lean on, the sequence is only safe if writers cannot interleave. Kuzu
guarantees exactly that ACROSS processes — one `Database` handle per path, enforced by a file
lock. WITHIN the process it guarantees nothing about two async tasks, so `_identity_lock` closes
that half. The limitation and the workaround are the same fact, and the lock is a cost the other
two adapters do not pay: a T43 input, not an implementation detail.

**3 · Every call runs in a thread.** `kuzu.Connection.execute` is SYNCHRONOUS (verified:
`inspect.iscoroutinefunction` is False). Awaiting it directly would block the event loop for the
duration of every graph query — the whole service, not just this call. `asyncio.to_thread` is
the boundary.

⚠️ QUERIES ARE PARAMETERISED, WITHOUT EXCEPTION. This repo has already shipped a SQL injection
in `age_graph_store` and had to fix it; that adapter interpolates through a `_lit()` helper
because AGE's cypher() takes a string literal, which is the shape that went wrong. Kuzu takes
real parameters, so there is no reason to build strings — verified with a name containing
`'; DROP TABLE Entity; --`, which round-trips as data.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from loreweave_extraction.canonical import canonicalize_entity_name

from app.domain.graph_models import Entity, EntityDetail, Relation

__all__ = ["KuzuGraphStore"]

#: ⚠️ Kuzu binds parameters STRICTLY: a key present in the dict but absent from the query is
#: `RuntimeError: Parameter <name> not found`, not a harmless extra. So a read-back cannot
#: reuse the write's parameter dict, and each statement is given exactly the keys it names.
_REL_BY_TUPLE = (
    "MATCH (s:Entity)-[r:RELATES_TO]->(o:Entity) WHERE s.id = $s AND o.id = $o "
    "AND r.predicate = $p AND r.user_id = $u RETURN r, s.id AS sid, o.id AS oid"
)

#: Named once so a refusal cannot drift from the section that explains it.
_UNIMPLEMENTED = (
    "see T42 · 'Kuzu's PRIMARY KEY collides with the port's identity model' and the slice that "
    "follows it. The entity surface is implemented; this operation is not yet written. Refusing "
    "rather than half-writing, exactly as AgeGraphStore refuses the event writes."
)


def _to_entity(row: dict) -> Entity:
    """One node's properties → the domain model. Mirrors `age_graph_store._to_entity` field for
    field: two adapters that disagree about defaults would pass the conformance suite
    separately and diverge in production."""
    return Entity.model_validate({
        "id": row.get("id") or "",
        "user_id": row.get("user_id") or "",
        "project_id": row.get("project_id"),
        "name": row.get("name") or "",
        "canonical_name": row.get("canonical_name") or "",
        "kind": row.get("kind") or "",
        "aliases": list(row.get("aliases") or []),
        "canonical_version": row.get("canonical_version") or 1,
        "source_types": list(row.get("source_types") or []),
        "confidence": row.get("confidence") or 0.0,
        "glossary_entity_id": row.get("glossary_entity_id"),
        "anchor_score": row.get("anchor_score") or 0.0,
        "archived_at": row.get("archived_at"),
        "archive_reason": row.get("archive_reason"),
    })


class KuzuGraphStore:
    """`GraphStore` over an embedded Kuzu database.

    Takes an open connection rather than a path: the file lock means the process may hold
    exactly one, so ownership belongs to whoever opened it (`kuzu_bootstrap.open_kuzu`). An
    adapter that opened its own would make a second instance impossible to construct, and the
    error would read like corruption.
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn
        #: Guards MATCH-then-CREATE. See point 2 in the module docstring — without it, two
        #: async tasks resolving the same name both miss the lookup and both create, and the
        #: identity tuple has no unique index to catch the duplicate.
        self._identity_lock = asyncio.Lock()

    # ── plumbing ──────────────────────────────────────────────────────────────────────────
    async def _run(self, query: str, params: dict | None = None) -> list[dict]:
        """Execute off the event loop and return rows as dicts."""
        def _sync() -> list[dict]:
            res = self._conn.execute(query, parameters=params or {})
            cols = res.get_column_names()
            out = []
            while res.has_next():
                out.append(dict(zip(cols, res.get_next())))
            return out

        return await asyncio.to_thread(_sync)

    @staticmethod
    def _props(row: dict, alias: str = "n") -> dict:
        """`RETURN n` yields one column holding the node; unwrap it to a flat dict."""
        node = row.get(alias)
        return dict(node) if isinstance(node, dict) else row

    # ── entities ──────────────────────────────────────────────────────────────────────────
    async def resolve_or_merge_entity(
        self, *, user_id: str, project_id: str | None, name: str, kind: str,
        source_type: str, confidence: float = 0.0, auto_created: bool = False,
        provenance: str = "human_authored", job_id: str | None = None,
    ) -> Entity:
        """Idempotent upsert keyed on (user, project, canonical name, kind).

        `source_types` ACCUMULATE and `confidence` is a MAX — the conformance suite asserts
        both, and they are what distinguish an upsert from an adapter that rebuilds the object
        at the same key. Kuzu expresses the accumulation directly, which AGE could not:
        `list_distinct(list_concat(...))`.
        """
        canonical = canonicalize_entity_name(name)
        key = {"u": user_id, "p": project_id, "c": canonical, "k": kind}
        async with self._identity_lock:
            found = await self._run(
                "MATCH (n:Entity) WHERE n.user_id = $u AND n.canonical_name = $c "
                "AND n.kind = $k AND ((n.project_id IS NULL AND $p IS NULL) "
                "OR n.project_id = $p) RETURN n", key)
            if not found:
                await self._run(
                    "CREATE (n:Entity {id: $id, user_id: $u, project_id: $p, name: $name, "
                    "canonical_name: $c, kind: $k, source_types: $st, confidence: $conf, "
                    "auto_created: $auto, provenance: $prov, job_id: $job, "
                    "canonical_version: 1, aliases: [], anchor_score: 0.0, "
                    "evidence_count: 0, mention_count: 0, version: 1, user_edited: false})",
                    {**key, "id": str(uuid.uuid4()), "name": name, "st": [source_type],
                     "conf": float(confidence), "auto": bool(auto_created),
                     "prov": provenance, "job": job_id})
            else:
                # By the PRIMARY KEY now that it is known — the shape Kuzu accepts.
                await self._run(
                    "MATCH (n:Entity) WHERE n.id = $id SET "
                    "n.source_types = list_distinct(list_concat(n.source_types, $st)), "
                    "n.confidence = CASE WHEN n.confidence >= $conf THEN n.confidence "
                    "ELSE $conf END",
                    {"id": self._props(found[0])["id"], "st": [source_type],
                     "conf": float(confidence)})
            rows = await self._run(
                "MATCH (n:Entity) WHERE n.user_id = $u AND n.canonical_name = $c "
                "AND n.kind = $k AND ((n.project_id IS NULL AND $p IS NULL) "
                "OR n.project_id = $p) RETURN n", key)
        return _to_entity(self._props(rows[0]))

    async def find_entities_by_name(
        self, *, user_id: str, project_id: str | None, name: str,
        include_archived: bool = False, exclude_project_ids: list[str] | None = None,
    ) -> list[Entity]:
        """Canonical-name and display-name matches, archived excluded by default.

        `exclude_project_ids` is why this adapter scopes projects with a COLUMN rather than a
        database per project (see `kuzu_bootstrap`): the operation asks one question of several
        projects at once, which per-project databases make unimplementable.
        """
        q = ["MATCH (n:Entity) WHERE n.user_id = $u AND (n.canonical_name = $c OR n.name = $n)"]
        params: dict[str, Any] = {"u": user_id, "c": canonicalize_entity_name(name), "n": name}
        if project_id is not None:
            q.append("AND n.project_id = $p")
            params["p"] = project_id
        if not include_archived:
            q.append("AND n.archived_at IS NULL")
        if exclude_project_ids:
            q.append("AND (n.project_id IS NULL OR NOT list_contains($ex, n.project_id))")
            params["ex"] = list(exclude_project_ids)
        rows = await self._run(" ".join(q) + " RETURN n", params)
        return [_to_entity(self._props(r)) for r in rows]

    async def neighborhood(
        self, *, user_id: str, glossary_entity_id: str, project_id: str | None = None,
        rel_cap: int = 50,
    ) -> EntityDetail | None:
        """One entity plus its capped one-hop neighbourhood.

        `rel_cap` is contract, not tuning: this feeds a context block, and an uncapped
        neighbourhood on a hub entity is how a prompt budget disappears. The TOTAL is counted
        separately from the capped page, so `relations_truncated` is a fact rather than
        `len(page) == cap` — which is wrong exactly when the count equals the cap.
        """
        params: dict[str, Any] = {"u": user_id, "g": glossary_entity_id}
        scope = ""
        if project_id is not None:
            scope, params["p"] = " AND n.project_id = $p", project_id
        rows = await self._run(
            f"MATCH (n:Entity) WHERE n.user_id = $u AND n.glossary_entity_id = $g{scope} "
            "RETURN n", params)
        if not rows:
            return None
        ent = _to_entity(self._props(rows[0]))
        total = (await self._run(
            "MATCH (s:Entity)-[r:RELATES_TO]->(o:Entity) WHERE s.id = $id AND r.user_id = $u "
            "RETURN count(r) AS c", {"id": ent.id, "u": user_id}))[0]["c"]
        edges = await self._run(
            "MATCH (s:Entity)-[r:RELATES_TO]->(o:Entity) WHERE s.id = $id AND r.user_id = $u "
            "RETURN r, o.id AS oid LIMIT $cap",
            {"id": ent.id, "u": user_id, "cap": int(rel_cap)})
        rels = [
            Relation.model_validate({
                "id": dict(e["r"]).get("id") or "", "user_id": user_id,
                "subject_id": ent.id, "object_id": e["oid"],
                "predicate": dict(e["r"]).get("predicate") or "",
                "confidence": dict(e["r"]).get("confidence") or 0.0,
            })
            for e in edges
        ]
        return EntityDetail(entity=ent, relations=rels,
                            relations_truncated=total > len(rels), total_relations=total)

    async def archive_entity(
        self, *, user_id: str, canonical_id: str, reason: str,
    ) -> Entity | None:
        """Soft-delete. `reason` is required because the archive is auditable — an entity that
        vanished with no reason cannot be told from one lost to a bug."""
        rows = await self._run(
            "MATCH (n:Entity) WHERE n.id = $id AND n.user_id = $u "
            "SET n.archived_at = current_timestamp(), n.archive_reason = $r RETURN n",
            {"id": canonical_id, "u": user_id, "r": reason})
        return _to_entity(self._props(rows[0])) if rows else None

    async def restore_entity(self, *, user_id: str, canonical_id: str) -> Entity | None:
        """Undo an archive. `None` when the id does not exist or is not this user's."""
        rows = await self._run(
            "MATCH (n:Entity) WHERE n.id = $id AND n.user_id = $u "
            "SET n.archived_at = NULL, n.archive_reason = NULL RETURN n",
            {"id": canonical_id, "u": user_id})
        return _to_entity(self._props(rows[0])) if rows else None

    # ── relations ─────────────────────────────────────────────────────────────────────────
    async def upsert_relation(
        self, *, user_id: str, subject_id: str, predicate: str, object_id: str,
        confidence: float = 0.0, source_event_id: str | None = None,
        valid_from_ordinal: int | None = None,
    ) -> Relation:
        """Create or update one edge.

        The predicate is a PROPERTY on a fixed `:RELATES_TO` type, not the edge type — the
        same choice both other adapters make, and the agreement is what lets T43 compare them
        at all. Kuzu could not do otherwise anyway: rel tables are declared up front, so a
        type per predicate would mean DDL per domain verb.

        ⚠️ `valid_from_ordinal` is written only when supplied. Re-asserting an edge WITHOUT a
        position must never STRIP one already there — that is the exact defect T36 fixed on
        the Neo4j authoring path, and it is expressed here as an explicit `ON MATCH` CASE
        rather than a `coalesce`, so the intent survives a reader.
        """
        params = {
            "u": user_id, "s": subject_id, "o": object_id, "p": predicate,
            "conf": float(confidence), "vfo": valid_from_ordinal,
            "ev": source_event_id, "nid": str(uuid.uuid4()),
        }
        # ⚠️ The NULL branches are chosen in PYTHON, not in a Cypher CASE. Kuzu type-checks
        # BOTH arms of a CASE regardless of which one runs, and `[$ev]` with `$ev` bound to
        # NULL infers `INT64[]`, so the whole statement fails to bind:
        #     Binder exception: Cannot bind LIST_CONCAT with parameter type STRING[] and INT64[]
        # Building the two shapes here keeps every parameter concretely typed.
        ev_create = "[$ev]" if source_event_id is not None else "CAST([] AS STRING[])"
        ev_match = ("list_distinct(list_concat(r.source_event_ids, [$ev]))"
                    if source_event_id is not None else "r.source_event_ids")
        vfo_match = "$vfo" if valid_from_ordinal is not None else "r.valid_from_ordinal"
        keys = ["u", "s", "o", "p", "conf", "nid"]
        if source_event_id is not None:
            keys.append("ev")
        if valid_from_ordinal is not None:
            keys.append("vfo")
        await self._run(
            "MATCH (s:Entity), (o:Entity) WHERE s.id = $s AND s.user_id = $u "
            "AND o.id = $o AND o.user_id = $u "
            "MERGE (s)-[r:RELATES_TO {predicate: $p, user_id: $u}]->(o) "
            f"ON CREATE SET r.id = $nid, r.confidence = $conf, r.source_event_ids = {ev_create}"
            + (", r.valid_from_ordinal = $vfo " if valid_from_ordinal is not None else " ")
            + f"ON MATCH SET r.confidence = $conf, r.valid_from_ordinal = {vfo_match}, "
            f"  r.source_event_ids = {ev_match}",
            {k: params[k] for k in keys})
        rows = await self._run(_REL_BY_TUPLE, {k: params[k] for k in ("s", "o", "p", "u")})
        return self._to_relation(rows[0])

    async def relations_for(
        self, *, user_id: str, entity_id: str, project_id: str | None = None,
        direction: str = "both", min_confidence: float = 0.8,
        as_of: int | None = None, limit: int = 100,
    ) -> list[Relation]:
        """This entity's edges. `as_of=None` reads the HEAD.

        With `as_of=N` the window is HALF-OPEN — `valid_from_ordinal <= N < valid_to_ordinal`
        — and a POSITIONLESS edge is EXCLUDED. That exclusion is the point rather than an
        omission: an edge with no position cannot be placed on the axis, and returning it
        would mix untimed legacy data into an answer whose whole value is that it is timed.
        """
        out: list[Relation] = []
        arms = (("out", "(e)-[r:RELATES_TO]->(peer)"), ("in", "(peer)-[r:RELATES_TO]->(e)"))
        for arm, pattern in arms:
            if direction not in ("both", arm):
                continue
            where = ["e.id = $id", "e.user_id = $u", "r.user_id = $u",
                     "r.confidence >= $mc", "r.valid_until IS NULL",
                     # An edge to an entity the author archived must not surface: the peer is
                     # gone from every other read, and a canon check handed it would enforce
                     # a tie the book retired.
                     "peer.archived_at IS NULL"]
            params: dict[str, Any] = {"id": entity_id, "u": user_id,
                                      "mc": float(min_confidence), "lim": int(limit)}
            if as_of is not None:
                where += ["r.valid_from_ordinal IS NOT NULL", "r.valid_from_ordinal <= $ao",
                          "(r.valid_to_ordinal IS NULL OR $ao < r.valid_to_ordinal)"]
                params["ao"] = int(as_of)
            if project_id is not None:
                where.append("e.project_id = $p")
                params["p"] = project_id
            rows = await self._run(
                f"MATCH (e:Entity), {pattern} WHERE {' AND '.join(where)} "
                "RETURN r, e.id AS eid, peer.id AS pid LIMIT $lim", params)
            for row in rows:
                sid = row["eid"] if arm == "out" else row["pid"]
                oid = row["pid"] if arm == "out" else row["eid"]
                out.append(self._to_relation({**row, "sid": sid, "oid": oid}))
        return out[:limit]

    async def get_relation(self, *, user_id: str, relation_id: str) -> Relation | None:
        """`None` is a MISS, never a permission error — a caller must not be able to learn
        that someone else's relation exists."""
        rows = await self._run(
            "MATCH (s:Entity)-[r:RELATES_TO]->(o:Entity) WHERE r.id = $r AND r.user_id = $u "
            "RETURN r, s.id AS sid, o.id AS oid", {"r": relation_id, "u": user_id})
        return self._to_relation(rows[0]) if rows else None

    async def invalidate_relation(
        self, *, user_id: str, relation_id: str, valid_until: Any = None,
    ) -> Relation | None:
        """Soft-invalidate by stamping `valid_until`. IDEMPOTENT — re-invalidating moves the
        instant rather than failing, because a correction that errors on a repeat is one that
        cannot be retried after a timeout.

        ⚠️ This closes the WALL-CLOCK interval, not the STORY interval (`valid_to_ordinal`).
        Two axes, two closes; conflating them is what T45 exists to prevent.
        """
        rows = await self._run(
            "MATCH (s:Entity)-[r:RELATES_TO]->(o:Entity) WHERE r.id = $r AND r.user_id = $u "
            "SET r.valid_until = CASE WHEN $vu IS NULL THEN current_timestamp() ELSE $vu END "
            "RETURN r, s.id AS sid, o.id AS oid",
            {"r": relation_id, "u": user_id, "vu": valid_until})
        return self._to_relation(rows[0]) if rows else None

    async def recreate_relation(
        self, *, user_id: str, subject_id: str, predicate: str, object_id: str,
        source_chapter: str | None = None, valid_from_ordinal: int | None = None,
    ) -> Relation | None:
        """The AUTHOR-asserted edge: confidence 1.0, and it RESURRECTS `valid_until` to NULL.

        Separate from `upsert_relation` on purpose. An extraction writer re-mentioning a pair
        must never revive an edge a human removed, and a shared entry point with a boolean
        would make that one wrong argument away.
        """
        params = {"u": user_id, "s": subject_id, "o": object_id, "p": predicate,
                  "vfo": valid_from_ordinal, "sc": source_chapter, "nid": str(uuid.uuid4())}
        exists = await self._run(
            "MATCH (s:Entity), (o:Entity) WHERE s.id = $s AND s.user_id = $u "
            "AND o.id = $o AND o.user_id = $u RETURN s.id",
            {k: params[k] for k in ("s", "o", "u")})
        if not exists:
            return None
        vfo_set = "$vfo" if valid_from_ordinal is not None else "r.valid_from_ordinal"
        keys2 = ["u", "s", "o", "p", "sc", "nid"] + (
            ["vfo"] if valid_from_ordinal is not None else [])
        await self._run(
            "MATCH (s:Entity), (o:Entity) WHERE s.id = $s AND s.user_id = $u "
            "AND o.id = $o AND o.user_id = $u "
            "MERGE (s)-[r:RELATES_TO {predicate: $p, user_id: $u}]->(o) "
            "ON CREATE SET r.id = $nid, r.source_event_ids = CAST([] AS STRING[]) "
            "SET r.confidence = 1.0, r.valid_until = NULL, r.source_chapter = $sc, "
            f"  r.valid_from_ordinal = {vfo_set}",
            {k: params[k] for k in keys2})
        rows = await self._run(_REL_BY_TUPLE, {k: params[k] for k in ("s", "o", "p", "u")})
        return self._to_relation(rows[0]) if rows else None

    @staticmethod
    def _to_relation(row: dict) -> Relation:
        r = dict(row.get("r") or {})
        return Relation.model_validate({
            "id": r.get("id") or "",
            "user_id": r.get("user_id") or "",
            "subject_id": row.get("sid") or "",
            "object_id": row.get("oid") or "",
            "predicate": r.get("predicate") or "",
            "confidence": r.get("confidence") or 0.0,
            "source_event_ids": list(r.get("source_event_ids") or []),
            "source_chapter": r.get("source_chapter"),
            "valid_until": r.get("valid_until"),
            "valid_from_ordinal": r.get("valid_from_ordinal"),
            "valid_to_ordinal": r.get("valid_to_ordinal"),
        })

    # ── events ────────────────────────────────────────────────────────────────────────────
    async def merge_event(
        self, *, user_id: str, project_id: str | None, title: str,
        summary: str | None = None, chapter_id: str | None = None,
        event_order: int | None = None, chronological_order: int | None = None,
        event_date_iso: str | None = None, time_cue: str | None = None,
        participants: list[str] | None = None, source_type: str = "book_content",
        confidence: float = 0.0,
    ) -> Any:
        """Idempotent upsert keyed on (user, project, chapter, title).

        FOUR merge semantics, every one of them silent when wrong:
          * `source_types` accumulate, `confidence` is a MAX, `participants` union-merge —
            a re-mention must never NARROW what is already known.
          * `summary` upgrades from NULL and **never overwrites** — a later, thinner mention
            must not erase a richer one.
          * `event_order` keeps the **MINIMUM** (CM4 spoiler-safety). The earliest reading
            position at which the event is known wins, so an event re-mentioned in chapter 40
            does not migrate forward and become invisible to a reader at chapter 12. An
            adapter taking the latest leaks nothing and hides everything.

        Same MATCH-then-CREATE-under-the-lock shape as `resolve_or_merge_entity`, for the same
        reason: Kuzu wants the primary key in every MERGE and the identity here is a tuple.
        """
        from app.domain.graph_models import Event

        canonical = canonicalize_entity_name(title)
        key = {"u": user_id, "p": project_id, "c": canonical, "ch": chapter_id}
        where = ("n.user_id = $u AND n.canonical_title = $c "
                 "AND ((n.project_id IS NULL AND $p IS NULL) OR n.project_id = $p) "
                 "AND ((n.chapter_id IS NULL AND $ch IS NULL) OR n.chapter_id = $ch)")
        async with self._identity_lock:
            found = await self._run(f"MATCH (n:Event) WHERE {where} RETURN n", key)
            if not found:
                await self._run(
                    "CREATE (n:Event {id: $id, user_id: $u, project_id: $p, title: $t, "
                    "canonical_title: $c, summary: $sum, chapter_id: $ch, "
                    "event_order: $eo, chronological_order: $co, event_date_iso: $edi, "
                    "time_cue: $tc, participants: $parts, source_types: $st, "
                    "confidence: $conf, evidence_count: 0, mention_count: 1})",
                    {**key, "id": str(uuid.uuid4()), "t": title, "sum": summary,
                     "eo": event_order, "co": chronological_order, "edi": event_date_iso,
                     "tc": time_cue, "parts": list(participants or []),
                     "st": [source_type], "conf": float(confidence)})
            else:
                # Each clause is chosen in PYTHON where a NULL is involved — see the note on
                # `upsert_relation`: Kuzu type-checks both arms of a CASE, so a NULL parameter
                # inside one poisons the bind even when that arm never runs.
                eid = self._props(found[0])["id"]
                sets = ["n.source_types = list_distinct(list_concat(n.source_types, $st))",
                        "n.confidence = CASE WHEN n.confidence >= $conf THEN n.confidence "
                        "ELSE $conf END",
                        "n.participants = list_distinct(list_concat(n.participants, $parts))",
                        "n.mention_count = n.mention_count + 1"]
                p2: dict[str, Any] = {"id": eid, "st": [source_type],
                                      "conf": float(confidence),
                                      "parts": list(participants or [])}
                if summary is not None:
                    # Upgrades from NULL, never overwrites.
                    sets.append("n.summary = CASE WHEN n.summary IS NULL THEN $sum "
                                "ELSE n.summary END")
                    p2["sum"] = summary
                if event_order is not None:
                    # MINIMUM wins. Not `least(...)`: the existing value may be NULL, and the
                    # first stamped position must then take.
                    sets.append("n.event_order = CASE WHEN n.event_order IS NULL "
                                "OR $eo < n.event_order THEN $eo ELSE n.event_order END")
                    p2["eo"] = event_order
                await self._run(
                    f"MATCH (n:Event) WHERE n.id = $id SET {', '.join(sets)}", p2)
            rows = await self._run(f"MATCH (n:Event) WHERE {where} RETURN n", key)
        return Event.model_validate(self._event_props(self._props(rows[0])))

    async def get_event(self, *, user_id: str, event_id: str) -> Any:
        """`None` for a miss — another user's event is ABSENT, not forbidden."""
        from app.domain.graph_models import Event

        rows = await self._run(
            "MATCH (n:Event) WHERE n.id = $id AND n.user_id = $u RETURN n",
            {"id": event_id, "u": user_id})
        return Event.model_validate(self._event_props(self._props(rows[0]))) if rows else None

    async def archive_event(self, *, user_id: str, event_id: str, reason: str = "") -> Any:
        """Soft-delete, IDEMPOTENT — re-archiving restamps rather than failing, for the same
        reason `invalidate_relation` does: a correction that errors on a repeat cannot be
        retried after a timeout."""
        from app.domain.graph_models import Event

        rows = await self._run(
            "MATCH (n:Event) WHERE n.id = $id AND n.user_id = $u "
            "SET n.archived_at = current_timestamp() RETURN n",
            {"id": event_id, "u": user_id})
        return Event.model_validate(self._event_props(self._props(rows[0]))) if rows else None

    @staticmethod
    def _event_props(row: dict) -> dict:
        return {
            "id": row.get("id") or "", "user_id": row.get("user_id") or "",
            "project_id": row.get("project_id"), "title": row.get("title") or "",
            "canonical_title": row.get("canonical_title") or "",
            "summary": row.get("summary"), "chapter_id": row.get("chapter_id"),
            "event_order": row.get("event_order"),
            "chronological_order": row.get("chronological_order"),
            "event_date_iso": row.get("event_date_iso"), "time_cue": row.get("time_cue"),
            "participants": list(row.get("participants") or []),
            "source_types": list(row.get("source_types") or []),
            "confidence": row.get("confidence") or 0.0,
            "evidence_count": row.get("evidence_count") or 0,
            "mention_count": row.get("mention_count") or 0,
            "archived_at": row.get("archived_at"),
        }

    # ── not yet written — each RAISES rather than half-honouring (rule 9) ──────────────────
    def _refuse(self, op: str) -> Any:
        raise NotImplementedError(f"KuzuGraphStore.{op} — {_UNIMPLEMENTED}")

    async def events_page(self, **kw: Any) -> Any: self._refuse("events_page")
    async def update_event_fields(self, **kw: Any) -> Any: self._refuse("update_event_fields")
    async def merge_fact(self, **kw: Any) -> Any: self._refuse("merge_fact")
    async def facts_for(self, **kw: Any) -> Any: self._refuse("facts_for")
    async def add_evidence(self, **kw: Any) -> Any: self._refuse("add_evidence")
    async def status_at_order(self, **kw: Any) -> Any: self._refuse("status_at_order")
    async def events_in_window(self, **kw: Any) -> Any: self._refuse("events_in_window")
