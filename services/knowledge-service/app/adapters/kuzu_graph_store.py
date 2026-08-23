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

from app.domain.graph_labels import COUNTABLE_LABELS
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
    """One node's properties -> the domain model, PASSING THROUGH what the row holds.

    Its docstring used to say it "mirrors `age_graph_store._to_entity` field for field: two
    adapters that disagree about defaults would pass the conformance suite separately and
    diverge in production." It mirrored it exactly — including the DEFECT. Both named 14 keys
    against a 21-field model and dropped the same seven (`version`, `user_edited`,
    `auto_created`, `mention_count`, `evidence_count`, `created_at`, `updated_at`), and the
    suite passed both because no rule looked at any of them.

    A21 fixed the AGE side; the two new conformance rules found this one. That is the mirror
    working as intended for the first time — the sentence above was true and useless while
    nothing conformed the fields it was talking about.
    """
    data = dict(row)
    if data.get("version") is None:
        data["version"] = 1
    if data.get("auto_created") is None:
        data["auto_created"] = False
    return Entity.model_validate(data)


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
                    "ELSE $conf END, "
                    # A24 — the ON MATCH arms this adapter was missing. `version` is the OCC
                    # token and must advance on every merge; `auto_created` FALLS to false
                    # when a real extraction claims a node an auto-creation minted. Both are
                    # copied from the Neo4j writer rather than guessed, and neither was
                    # conformed against ANY adapter until now.
                    "n.version = coalesce(n.version, 0) + 1, "
                    "n.auto_created = CASE WHEN $auto THEN n.auto_created ELSE false END",
                    {"id": self._props(found[0])["id"], "st": [source_type],
                     "conf": float(confidence), "auto": bool(auto_created)})
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
        # ⚠️ The arm labels ARE the port's `RelationDirection` values —
        # `Literal["outgoing", "incoming", "both"]` — not abbreviations of them. They were
        # "out"/"in" until 2026-08-14, so `direction="outgoing"` matched neither "both" nor
        # "out", BOTH arms were skipped, and the result was ALWAYS EMPTY. Every conformance
        # rule passed because they all use `direction="both"` — the one value that happened to
        # work. Only the shadow comparison caught it, and only because its random sequence
        # picks "outgoing" and "incoming" too.
        arms = (("outgoing", "(e)-[r:RELATES_TO]->(peer)"),
                ("incoming", "(peer)-[r:RELATES_TO]->(e)"))
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
                # ⚠️ `arm == "outgoing"`, not `"out"`. The comment above records that these values
                # were "out"/"in" until 2026-08-14; the rename reached the `arms` tuple and the
                # filter and MISSED these two lines, so `arm == "out"` was always False and EVERY
                # relation came back with its subject and object SWAPPED — on both arms. The
                # direction filter was right the whole time, which is why counting rows could
                # never find it; only comparing the ENDPOINTS does.
                sid = row["eid"] if arm == "outgoing" else row["pid"]
                oid = row["pid"] if arm == "outgoing" else row["eid"]
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
        # 🔴 `origin_title`, NOT `canonical_title` (T35d). The first cut matched the mutable
        # one and forked the event on every re-extraction that followed an author rename:
        # a title comes out of the PROSE, so a later pass still arrives with the ORIGINAL.
        # Found by the shadow differential, not by conformance — which had no rule for it.
        where = ("n.user_id = $u AND n.origin_title = $c "
                 "AND ((n.project_id IS NULL AND $p IS NULL) OR n.project_id = $p) "
                 "AND ((n.chapter_id IS NULL AND $ch IS NULL) OR n.chapter_id = $ch)")
        async with self._identity_lock:
            found = await self._run(f"MATCH (n:Event) WHERE {where} RETURN n", key)
            if not found:
                await self._run(
                    "CREATE (n:Event {id: $id, user_id: $u, project_id: $p, title: $t, "
                    "canonical_title: $c, origin_title: $c, summary: $sum, chapter_id: $ch, "
                    "event_order: $eo, chronological_order: $co, event_date_iso: $edi, "
                    "time_cue: $tc, participants: $parts, source_types: $st, "
                    "confidence: $conf, evidence_count: 0, mention_count: 0, version: 1, "
                    "created_at: current_timestamp(), updated_at: current_timestamp()})",
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

    #: Which column each axis reads. A dict rather than an `if` chain so the browse and the
    #: window cannot drift into two definitions of "narrative" — one conformance rule exists
    #: precisely because a second definition of "matching" is what goes wrong here.
    _AXIS_COL = {"narrative": "event_order", "chronological": "chronological_order",
                 "date": "event_date_iso"}

    def _window_where(self, axis: str, after: Any, before: Any) -> tuple[list[str], dict]:
        """The range predicate, shared by `events_page` and `events_in_window`.

        ⚠️ BOTH BOUNDS ARE INCLUSIVE, matching `FakeGraphStore` (`value < after` and
        `value > before` are its skips). Not a free choice: T43 diffs adapters against each
        other, and two stores that disagree about a boundary would report as a correctness
        difference on every windowed read.

        Shared rather than duplicated because the ONE rule that spans both operations asserts
        they agree — and two copies of a predicate are how they stop agreeing.
        """
        col = self._AXIS_COL.get(axis, "event_order")
        where, params = [], {}
        if after is not None:
            where.append(f"n.{col} IS NOT NULL AND n.{col} >= $after")
            params["after"] = after
        if before is not None:
            where.append(f"n.{col} IS NOT NULL AND n.{col} <= $before")
            params["before"] = before
        return where, params

    async def events_in_window(
        self, *, user_id: str, project_id: str | None = None, after: Any = None,
        before: Any = None, axis: str = "narrative", include_archived: bool = False,
        limit: int = 200,
    ) -> list[Any]:
        """Events between two bounds on one axis. NO total — a windowed read answers "what
        happened between here and there", and a count would be an unrelated second question
        riding along. The port says so explicitly and `events_page` is where the count lives.
        """
        from app.domain.graph_models import Event

        where = ["n.user_id = $u"]
        params: dict[str, Any] = {"u": user_id, "lim": int(limit)}
        if project_id is not None:
            where.append("n.project_id = $p")
            params["p"] = project_id
        if not include_archived:
            where.append("n.archived_at IS NULL")
        w, wp = self._window_where(axis, after, before)
        where += w
        params.update(wp)
        col = self._AXIS_COL.get(axis, "event_order")
        rows = await self._run(
            f"MATCH (n:Event) WHERE {' AND '.join(where)} RETURN n "
            f"ORDER BY n.{col} LIMIT $lim", params)
        return [Event.model_validate(self._event_props(self._props(r))) for r in rows]

    async def events_page(
        self, *, user_id: str, project_id: str | None = None, after: Any = None,
        before: Any = None, axis: str = "narrative", participants: list[str] | None = None,
        q: str | None = None, sort_dir: str = "asc", limit: int = 50, offset: int = 0,
        exclude_project_ids: list[str] | None = None,
    ) -> tuple[list[Any], int]:
        """One PAGE plus the TOTAL that matched — the browse.

        `total` counts everything matching the FILTERS, ignoring `limit`/`offset`. A total that
        shrank with the page would make "showing 1–50 of 50" true on every page of a thousand,
        which is an off-by-a-page bug nobody sees.
        """
        from app.domain.graph_models import Event

        where = ["n.user_id = $u"]
        params: dict[str, Any] = {"u": user_id}
        if project_id is not None:
            where.append("n.project_id = $p")
            params["p"] = project_id
        if exclude_project_ids:
            where.append("(n.project_id IS NULL OR NOT list_contains($ex, n.project_id))")
            params["ex"] = list(exclude_project_ids)
        if participants:
            # ANY overlap, not containment: an event matches if it involves any of them.
            where.append("size(list_intersect(n.participants, $parts)) > 0")
            params["parts"] = list(participants)
        if q:
            where.append("(contains(lower(n.title), lower($q)) "
                         "OR contains(lower(n.summary), lower($q)))")
            params["q"] = q
        where.append("n.archived_at IS NULL")
        w, wp = self._window_where(axis, after, before)
        where += w
        params.update(wp)
        clause = " AND ".join(where)
        total = (await self._run(
            f"MATCH (n:Event) WHERE {clause} RETURN count(n) AS c", params))[0]["c"]
        col = self._AXIS_COL.get(axis, "event_order")
        direction = "DESC" if str(sort_dir).lower() == "desc" else "ASC"
        rows = await self._run(
            f"MATCH (n:Event) WHERE {clause} RETURN n ORDER BY n.{col} {direction} "
            "SKIP $off LIMIT $lim",
            {**params, "off": int(offset), "lim": int(limit)})
        return [Event.model_validate(self._event_props(self._props(r))) for r in rows], total

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
            # [] not None: Neo4j returns an empty list and a shadow comparison would
            # score the difference as a divergence between engines rather than a
            # default chosen here.
            "participant_entity_ids": list(row.get("participant_entity_ids") or []),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "source_types": list(row.get("source_types") or []),
            "confidence": row.get("confidence") or 0.0,
            "evidence_count": row.get("evidence_count") or 0,
            "mention_count": row.get("mention_count") or 0,
            "archived_at": row.get("archived_at"),
        }

    # ── facts, and the ordinal chain ──────────────────────────────────────────────────────
    async def merge_fact(
        self, *, user_id: str, project_id: str | None, type: str, content: str,
        confidence: float = 0.0, pending_validation: bool = False,
        source_type: str = "book_content", source_chapter: str | None = None,
        provenance: str = "human_authored", subject_id: str | None = None,
        from_order: int | None = None, valid_from_ordinal: int | None = None,
        event_date_iso: str | None = None, predicate: str | None = None,
        object: str | None = None, maintain_chain: bool = False,
    ) -> Any:
        """Idempotent, CONTENT-KEYED fact upsert, with the ordinal chain.

        🔻 **KUZU CAN HONOUR `maintain_chain`, WHICH AGE REFUSED — and the reason is the same
        structural fact that forced this adapter's identity workaround.** AGE's refusal
        (`D-AGE-FACT-WRITE-UNIMPLEMENTED`) is that re-deriving the chain needs *"an ordered
        window over sibling facts in ONE statement, which AGE has no APOC-free shape for."*
        Kuzu does not need one statement: it is embedded and **single-writer**, so reading the
        `(subject, type)` family, computing the chain in Python and writing it back cannot
        interleave with another writer. The file lock that makes this adapter unable to scale
        out is the same property that makes a read-compute-write chain sound.

        The chain: each fact closes at the NEXT strictly-greater `valid_from_ordinal` among its
        siblings, and the last stays open. Derived by sorting the whole family every time
        rather than by patching neighbours, so out-of-order and backfill arrival — the whole
        difficulty the port names — are handled by construction.

        An adapter that ACCEPTED the flag and did nothing would leave every fact open forever,
        and every as-of read would answer with the latest value at every position: a book with
        no history, reported as a working timeline.
        """
        from app.domain.graph_models import Fact

        vfo = valid_from_ordinal if valid_from_ordinal is not None else from_order
        canonical = canonicalize_entity_name(content)
        key = {"u": user_id, "c": canonical, "t": type}
        # ⚠️ The subject is the `(Fact)-[:ABOUT]->(Entity)` EDGE, not a column — the shape
        # both other adapters use. Adding a `subject_id` property instead would give the same
        # fact two homes and make T43's cross-adapter diff report a difference that is really a
        # schema choice. Kuzu said so first: `Cannot find property subject_id for n`.
        where = "n.user_id = $u AND n.canonical_content = $c AND n.type = $t"
        async with self._identity_lock:
            found = await self._run(f"MATCH (n:Fact) WHERE {where} RETURN n", key)
            if not found:
                await self._run(
                    "CREATE (n:Fact {id: $id, user_id: $u, project_id: $p, type: $t, "
                    "content: $ct, canonical_content: $c, confidence: $conf, "
                    "pending_validation: $pv, source_types: $st, source_chapter: $sc, "
                    "provenance: $prov, from_order: $fo, "
                    "valid_from_ordinal: $vfo, event_date_iso: $edi, predicate: $pred, "
                    "object: $obj, evidence_count: 0})",
                    {**key, "id": str(uuid.uuid4()), "p": project_id, "ct": content,
                     "conf": float(confidence), "pv": bool(pending_validation),
                     "st": [source_type], "sc": source_chapter, "prov": provenance,
                     "fo": from_order, "vfo": vfo, "edi": event_date_iso,
                     "pred": predicate, "obj": object})
                if subject_id:
                    await self._run(
                        "MATCH (f:Fact), (e:Entity) WHERE f.canonical_content = $c "
                        "AND f.type = $t AND f.user_id = $u AND e.id = $s AND e.user_id = $u "
                        "MERGE (f)-[:ABOUT {user_id: $u}]->(e)",
                        {"c": canonical, "t": type, "u": user_id, "s": subject_id})
            else:
                fid = self._props(found[0])["id"]
                sets = ["n.source_types = list_distinct(list_concat(n.source_types, $st))",
                        "n.confidence = CASE WHEN n.confidence >= $conf THEN n.confidence "
                        "ELSE $conf END"]
                p2: dict[str, Any] = {"id": fid, "st": [source_type], "conf": float(confidence)}
                if vfo is not None:
                    # 🔴 BACKFILL, NEVER OVERWRITE — and this line was the seventh real
                    # Kuzu bug, found by T43's differential rather than by conformance.
                    # It read `n.valid_from_ordinal = $vfo`, so a re-mention of the same
                    # content in a LATER chapter moved the fact's birth forward. Neo4j
                    # coalesces (`facts.py`: *"never overwrite an existing one"*), and the
                    # difference is silent and directional: an as-of read at the ORIGINAL
                    # chapter stops returning a fact that was already established there —
                    # established canon vanishing from a reader's past, which is the same
                    # failure `merge_event` keeping the EARLIEST reading position exists
                    # to prevent, on the other node type.
                    sets.append(
                        "n.valid_from_ordinal = coalesce(n.valid_from_ordinal, $vfo)")
                    p2["vfo"] = vfo
                await self._run(f"MATCH (n:Fact) WHERE n.id = $id SET {', '.join(sets)}", p2)
            if maintain_chain and subject_id:
                await self._rederive_chain(user_id, subject_id, type)
            rows = await self._run(f"MATCH (n:Fact) WHERE {where} RETURN n", key)
        return Fact.model_validate(self._fact_props(self._props(rows[0])))

    async def _rederive_chain(self, user_id: str, subject_id: str, type_: str) -> None:
        """Close each positioned sibling at the NEXT strictly-greater ordinal; the last stays
        open. Recomputed over the WHOLE family rather than patched at the insertion point —
        patching is what gets out-of-order and backfill arrival wrong, and both are normal
        here."""
        fam = await self._run(
            "MATCH (n:Fact)-[:ABOUT]->(e:Entity) WHERE n.user_id = $u AND e.id = $s "
            "AND n.type = $t AND n.valid_from_ordinal IS NOT NULL "
            "RETURN n ORDER BY n.valid_from_ordinal",
            {"u": user_id, "s": subject_id, "t": type_})
        rows = [self._props(r) for r in fam]
        for i, row in enumerate(rows):
            nxt = next((r["valid_from_ordinal"] for r in rows[i + 1:]
                        if r["valid_from_ordinal"] > row["valid_from_ordinal"]), None)
            if nxt is None:
                await self._run("MATCH (n:Fact) WHERE n.id = $id "
                                "SET n.valid_to_ordinal = NULL", {"id": row["id"]})
            else:
                await self._run("MATCH (n:Fact) WHERE n.id = $id "
                                "SET n.valid_to_ordinal = $vt",
                                {"id": row["id"], "vt": nxt})

    async def facts_for(
        self, *, user_id: str, subject_id: str, type: str | None = None,
        as_of: int | None = None, limit: int = 100,
    ) -> list[Any]:
        """Facts ABOUT one subject. `as_of` is HALF-OPEN — `valid_from <= N < valid_to` — and a
        POSITIONLESS fact is EXCLUDED from a timed read, for the same reason as relations: it
        cannot be placed on the axis."""
        from app.domain.graph_models import Fact

        where = ["n.user_id = $u", "e.id = $s"]
        params: dict[str, Any] = {"u": user_id, "s": subject_id, "lim": int(limit)}
        if type is not None:
            where.append("n.type = $t")
            params["t"] = type
        if as_of is not None:
            where += ["n.valid_from_ordinal IS NOT NULL", "n.valid_from_ordinal <= $ao",
                      "(n.valid_to_ordinal IS NULL OR $ao < n.valid_to_ordinal)"]
            params["ao"] = int(as_of)
        rows = await self._run(
            f"MATCH (n:Fact)-[:ABOUT]->(e:Entity) WHERE {' AND '.join(where)} RETURN n "
            "ORDER BY n.valid_from_ordinal LIMIT $lim", params)
        return [Fact.model_validate(self._fact_props(self._props(r))) for r in rows]

    @staticmethod
    def _fact_props(row: dict) -> dict:
        return {
            "id": row.get("id") or "", "user_id": row.get("user_id") or "",
            "project_id": row.get("project_id"), "type": row.get("type") or "",
            "content": row.get("content") or "",
            "canonical_content": row.get("canonical_content") or "",
            "confidence": row.get("confidence") or 0.0,
            "pending_validation": bool(row.get("pending_validation")),
            "source_types": list(row.get("source_types") or []),
            "source_chapter": row.get("source_chapter"),
            "from_order": row.get("from_order"),
            "valid_from_ordinal": row.get("valid_from_ordinal"),
            "valid_to_ordinal": row.get("valid_to_ordinal"),
            "event_date_iso": row.get("event_date_iso"),
            "predicate": row.get("predicate"), "object": row.get("object"),
            "evidence_count": row.get("evidence_count") or 0,
        }

    # ── evidence, OCC, and status ─────────────────────────────────────────────────────────
    async def add_evidence(
        self, *, user_id: str, target_label: str, target_id: str, source_id: str,
        extraction_model: str, confidence: float, job_id: str, quote: str | None = None,
    ) -> Any:
        """Attach one extraction's evidence. IDEMPOTENT on `job_id`, and the counter bumps
        **only on create**.

        Validation mirrors the other adapters exactly — *a port whose two implementations
        disagree about what is a CALLER error is a port that leaks its engine.*

        ⚠️ The AGE adapter's first cut incremented on every call and the conformance rule caught
        it on `[age]` while `[fake]` and `[neo4j]` passed. Same hazard here, so existence is
        checked and the counter bumped under the SAME lock the identity path uses: Kuzu's
        `MERGE` on a relationship has no `ON CREATE`-only counter increment, and two concurrent
        extractions both seeing "absent" would both bump.
        """
        from app.domain.graph_models import EvidenceWriteResult

        if not all((target_id, source_id, extraction_model, job_id)):
            raise ValueError("target_id/source_id/extraction_model/job_id must be non-empty")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence must be in [0,1], got {confidence}")
        label = target_label if target_label in ("Entity", "Event", "Fact") else "Entity"
        p = {"u": user_id, "t": target_id, "s": source_id, "j": job_id,
             "m": extraction_model, "c": float(confidence), "q": quote}
        async with self._identity_lock:
            tgt = await self._run(
                f"MATCH (n:{label}) WHERE n.id = $t AND n.user_id = $u RETURN n",
                {"t": target_id, "u": user_id})
            if not tgt:
                return None
            # ⚠️ The source must ALREADY EXIST. Creating it here is what diverged from Neo4j,
            # which treats an absent `ExtractionSource` as a MISS and returns None:
            #     neo4j: [None, None]        kuzu: [(1, 0, True), (1, 0, False)]
            # An adapter that mints the node it was asked to attach to turns a caller's mistake
            # — evidence citing a source that was never recorded — into a silent success, and
            # the provenance chain then points at a node nothing else knows about.
            src = await self._run(
                "MATCH (s:ExtractionSource) WHERE s.id = $s AND s.user_id = $u RETURN s.id",
                {"s": source_id, "u": user_id})
            if not src:
                return None
            created = False
            seen = await self._run(
                f"MATCH (n:{label})-[r:EVIDENCED_BY]->(s:ExtractionSource) "
                "WHERE n.id = $t AND n.user_id = $u AND s.id = $s AND r.job_id = $j "
                "RETURN r", {"t": target_id, "u": user_id, "s": source_id, "j": job_id})
            if not seen:
                created = True
                await self._run(
                    f"MATCH (n:{label}), (s:ExtractionSource) "
                    "WHERE n.id = $t AND n.user_id = $u AND s.id = $s "
                    "CREATE (n)-[:EVIDENCED_BY {job_id: $j, extraction_model: $m, "
                    "confidence: $c, quote: $q}]->(s)", p)
                await self._run(
                    f"MATCH (n:{label}) WHERE n.id = $t AND n.user_id = $u "
                    "SET n.evidence_count = n.evidence_count + 1",
                    {"t": target_id, "u": user_id})
            row = self._props((await self._run(
                f"MATCH (n:{label}) WHERE n.id = $t AND n.user_id = $u RETURN n",
                {"t": target_id, "u": user_id}))[0])
        return EvidenceWriteResult(evidence_count=row.get("evidence_count") or 0,
                                   mention_count=row.get("mention_count") or 0,
                                   created=created)

    async def update_event_fields(
        self, *, user_id: str, event_id: str, title: str | None, summary: str | None,
        time_cue: str | None, event_date_iso: str | None, expected_version: int,
    ) -> tuple[Any, dict | None]:
        """Optimistic-concurrency edit, returning `(updated, pre_edit_snapshot)`.

        The second element is the state BEFORE the edit — a correction event has nothing to
        record without it, which is why it is part of the contract rather than a courtesy.
        A STALE `expected_version` **RAISES** rather than silently no-opping: a lost update
        that reports success is the failure this guard exists for."""
        from app.db.repositories import VersionMismatchError
        from app.domain.graph_models import Event

        rows = await self._run(
            "MATCH (n:Event) WHERE n.id = $id AND n.user_id = $u RETURN n",
            {"id": event_id, "u": user_id})
        if not rows:
            return None, None
        cur = self._props(rows[0])
        have = cur.get("version") or 1
        if have != expected_version:
            raise VersionMismatchError(
                f"event {event_id} is at version {have}, caller expected {expected_version}")
        sets, p = ["n.version = n.version + 1"], {"id": event_id}
        for col, val in (("title", title), ("summary", summary),
                         ("time_cue", time_cue), ("event_date_iso", event_date_iso)):
            if val is not None:
                sets.append(f"n.{col} = ${col}")
                p[col] = val
        if title is not None:
            # The canonical form is DERIVED from the title, so an edit that moves one and not
            # the other leaves the row self-inconsistent — and `canonical_title` is the
            # identity key `merge_event` upserts on, so a stale one silently splits the event
            # into two on its next mention. The concrete repo recomputes it here; this is that,
            # not an embellishment.
            sets.append("n.canonical_title = $ct")
            p["ct"] = canonicalize_entity_name(title)
        # EXACTLY the five keys the concrete repo returns —
        # `{title, summary, time_cue, event_date_iso, participants}`. Returning the whole
        # event read fine and diverged on every seed: the snapshot is a CONTRACT (it is what a
        # correction event records), not a convenience dump, and a richer one is still a
        # different one.
        snapshot = {
            "title": cur.get("title"), "summary": cur.get("summary"),
            "time_cue": cur.get("time_cue"), "event_date_iso": cur.get("event_date_iso"),
            "participants": list(cur.get("participants") or []),
        }
        out = await self._run(
            f"MATCH (n:Event) WHERE n.id = $id SET {', '.join(sets)} RETURN n", p)
        return Event.model_validate(self._event_props(self._props(out[0]))), snapshot

    async def status_at_order(
        self, *, user_id: str, project_id: str | None, entity_ids: list[str],
        at_order: int, min_evidence: int = 1,
    ) -> dict[str, str]:
        """`{entity_id: status}` at a story position.

        🔴 **The first cut ANSWERED, and answered wrongly** — it read `Fact` nodes with a
        hardcoded type and returned `{}`, which the differential caught against Neo4j
        (`primary={'…': 'active'} secondary={}`) and the conformance suite could not, because no
        rule covers this operation. Two contract violations at once: the wrong source, and a
        silent drop where **every requested id must appear**.

        The contract, mirrored from the concrete repo: the latest transition with
        `from_order <= at_order` and `evidence_count >= min_evidence` wins, and an entity with
        no qualifying transition **defaults to `'active'`**. A caller must never have to tell
        "no transition recorded" from "absent" — a canon guard reading a gap as *gone* would
        drop a living character out of the story.

        `min_evidence` is the bar, not a knob: a status derived from a single mention is a
        guess, and the guard raises the bar rather than acting on one.
        """
        if not entity_ids:
            return {}
        rows = await self._run(
            "MATCH (s:EntityStatus) WHERE s.user_id = $u AND list_contains($ids, s.entity_id) "
            "AND s.from_order <= $ao AND s.evidence_count >= $me "
            + ("AND s.project_id = $p " if project_id is not None else "")
            + "RETURN s.entity_id AS eid, s.status AS status, s.from_order AS fo "
            "ORDER BY s.from_order",
            {"u": user_id, "ids": list(entity_ids), "ao": int(at_order),
             "me": int(min_evidence), **({"p": project_id} if project_id is not None else {})})
        # Ascending order means the LAST write per entity is the latest qualifying transition.
        latest = {r["eid"]: r["status"] for r in rows}
        # Every requested id appears; the default is 'active'. This line is the contract.
        return {eid: latest.get(eid, "active") for eid in entity_ids}

    # ── the project as a whole ────────────────────────────────────────────────────────────

    async def project_graph_stats(
        self, *, user_id: str, project_id: str,
    ) -> dict[str, int]:
        """One count per label in `COUNTABLE_LABELS`.

        Kuzu is schema-full, so the label is a TABLE name and cannot be parameterised any
        more than a Cypher label can — `COUNTABLE_LABELS` is the injection barrier here for
        the same reason it is in the other two adapters, and it is iterated rather than
        accepted from a caller.

        ⚠️ **The graph has no `Passage` table at all**, which is why the port's shape omits
        `passage_count` rather than making this adapter answer `0` for a store it does not
        hold. See the port docstring.
        """
        out: dict[str, int] = {}
        for label in COUNTABLE_LABELS:
            rows = await self._run(
                f"MATCH (n:{label}) WHERE n.user_id = $u AND n.project_id = $p "
                "RETURN count(n) AS c",
                {"u": user_id, "p": project_id},
            )
            out[f"{label.lower()}_count"] = int(rows[0]["c"]) if rows else 0
        return out
