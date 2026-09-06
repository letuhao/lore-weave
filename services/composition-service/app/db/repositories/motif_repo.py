"""motif repository — the library unit CRUD + the ONE clone primitive (=adopt).

TENANCY (the kinds-bug fix + R1.1): a motif is system (owner_user_id NULL,
seed/migrate-only) or user-owned (owner set). The read predicate (R1.1) lives in
get_visible/list_for_caller SELECTs — a motif is visible IFF
  owner_user_id IS NULL (system) OR visibility = 'public' OR owner_user_id = caller.
The user-write path (create) SERVER-STAMPS owner_user_id = caller and can never
write a both-NULL (system) row (the DB motif_user_owned CHECK is the backstop).

EMBEDDING: ONE platform model for ALL motif vectors (R1.1.2/B-1). create() inserts
a NULL embedding (W3's embed pipeline fills it transactionally on the summary, and
seeds also start NULL — RECONCILE D4); clone() COPIES the source vector (same space
→ cross-tier cosine stays correct). The `embedding` column is NEVER projected into
a returned Motif (stays server-side, reference_source precedent).

This file is F0-frozen; after the foundation merges, master-plan §3 hands ownership
to W1, which EXTENDS it with adopt/publish/catalog (it does not re-key the CRUD).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID

import asyncpg

from loreweave_vecmath import cosine_similarity as _cosine

from app.clients.embedding_client import EmbeddingError
from app.config import settings
from app.db.models import Motif, MotifCreateArgs, MotifPatchArgs
from app.db.repositories import VersionMismatchError
from app.motif_i18n import resolve_text, source_hash
from app.engine.motif_embed import (
    EmbedConfigError, _platform_embed_model, embed_motif_summary, embed_query,
    motif_summary_text, summary_hash,
)

logger = logging.getLogger(__name__)

# How many rows a text query may pull into Python to cosine against. Same bound the planner's
# retrieve uses — one ceiling for "how much of the library do we brute-force at once".
_SEARCH_CEILING = 500

# vector + hash deliberately excluded — projection is the model shape only.
_SELECT_COLS = """
  id, owner_user_id, book_id, book_shared, code, original_language, visibility, kind, category, name, summary,
  genre_tags, roles, beats, preconditions, effects, info_asymmetry, annotations,
  tension_target, emotion_target, examples, abstraction_confidence, source,
  imported_derived, source_ref, source_version, embedding_model, embedding_dim,
  judge_score, mining_support, status, version, created_at, updated_at
"""

# The SEARCH projection — `_SELECT_COLS` plus the vector, loaded ONLY for the bounded
# candidate set of a text query. The vector never leaves this module (`_row_to_motif` drops it).
_SEARCH_COLS = _SELECT_COLS.rstrip() + ",\n  embedding, embedded_summary_hash\n"
# JSONB columns json.loads'd on read (asyncpg returns them as str).
_JSONB_FIELDS = (
    "roles", "beats", "preconditions", "effects", "info_asymmetry",
    "annotations", "examples",
)
# The read predicate (R1.1) — system | public | owned-by-caller. $1 = caller_id.
_VISIBLE_PREDICATE = "(owner_user_id IS NULL OR visibility = 'public' OR owner_user_id = $1)"


def _row_to_motif(row: asyncpg.Record) -> Motif:
    data = dict(row)
    data.pop("embedding", None)              # server-side only; never leaves the repo
    data.pop("embedded_summary_hash", None)
    for f in _JSONB_FIELDS:
        v = data.get(f)
        if isinstance(v, str):
            data[f] = json.loads(v)
    return Motif.model_validate(data)


def _jsonb(value: Any) -> str:
    """Dump a JSONB write value (list/dict/pydantic) to a json string for ::jsonb."""
    return json.dumps(value)


# ── display-language resolution ────────────────────────────────────────────
# `language` used to mean two different things at once — the language a row was
# STORED in (a filter) and the language a caller wanted to READ (a preference) — and
# the conflation is what let an English book's plan pass be briefed in Vietnamese.
# They are now two names: `original_language` on the row, `display_language` on reads.
_TR_COLS = (
    "motif_id, language_code, name, summary, emotion_target, "
    "roles, beats, preconditions, effects, examples, source_content_hash"
)
_TR_JSONB = ("roles", "beats", "preconditions", "effects", "examples")

# Values callers send that mean "unspecified" rather than a real language. Same list
# the retrieval path uses — `language='auto'` once matched zero rows and zeroed the
# whole library (D-MOTIF-AUTO-LANGUAGE-ZEROES-RETRIEVAL).
_UNSPECIFIED_LANGS = frozenset({"", "auto", "unknown", "und"})


def normalize_display_language(value: str | None) -> str | None:
    """A real language code, or None when the caller expressed no preference."""
    want = (value or "").strip().lower()
    return None if want in _UNSPECIFIED_LANGS else want


async def apply_display_language(
    conn: asyncpg.Connection, motifs: list[Motif], display_language: str | None
) -> list[Motif]:
    """Re-word a batch of motifs into `display_language`, falling back per leaf.

    ONE query for the whole batch (never per-motif — a 15-motif plan brief would
    otherwise cost 15 round-trips). Motifs already in the wanted language are skipped
    entirely. Every returned motif carries `text_language`/`text_fallback`/`text_stale`
    so no consumer can be handed text without knowing what language it is in.
    """
    want = normalize_display_language(display_language)
    if not want or not motifs:
        return motifs

    need = [m.id for m in motifs if m.original_language != want]
    by_id: dict[Any, dict[str, Any]] = {}
    if need:
        rows = await conn.fetch(
            f"SELECT {_TR_COLS} FROM motif_translation "
            f"WHERE language_code = $1 AND motif_id = ANY($2::uuid[])",
            want, need,
        )
        for r in rows:
            tr = dict(r)
            for f in _TR_JSONB:
                if isinstance(tr.get(f), str):
                    tr[f] = json.loads(tr[f])
            by_id[tr["motif_id"]] = tr

    out: list[Motif] = []
    for m in motifs:
        if m.original_language == want:
            out.append(m.model_copy(update={"text_language": want}))
            continue
        resolved = resolve_text(m, by_id.get(m.id), want)
        # `extract_translatable` normalizes a NULL scalar to "" so the hash is stable;
        # the column is nullable, so put the NULL back rather than storing an empty string.
        if not resolved.get("emotion_target"):
            resolved["emotion_target"] = None
        out.append(m.model_copy(update=resolved))
    return out


def _coerce_jsonb_value(value: Any) -> Any:
    """A JSONB column read from asyncpg is a json STRING (or already parsed) — return the
    PARSED value (list/dict) for embedding into a nested structure (the adopted_base snapshot)."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value


def _dump_models(items: list[Any]) -> list[dict[str, Any]]:
    """[MotifRole|MotifBeat|dict] → [dict] for JSONB serialization."""
    out: list[dict[str, Any]] = []
    for it in items:
        out.append(it.model_dump(mode="json") if hasattr(it, "model_dump") else it)
    return out


# A search box is INTERACTIVE — it runs per debounced keystroke, and a user waiting on a
# provider is a worse outcome than a slightly worse ranking. So the embed gets a hard wall-clock
# budget and degrades to the literal filter past it. This is deliberately unlike the planning
# pipelines, which must NOT be timeout-bounded (a long generate is legitimate); the difference is
# that nobody is watching a plan run, and someone is always watching a search field.
_SEARCH_EMBED_BUDGET_S = 2.0

# How many unjudgeable rows one search may re-embed, and the wall-clock it may spend doing it.
# Gathered concurrently, so the budget is roughly one round-trip regardless of the cap.
_WARM_CAP = 12
_WARM_BUDGET_S = 4.0


async def _query_vector(q: str) -> list[float] | None:
    """Embed the user's search text in the PLATFORM space, or None when that is impossible.

    None is the honest "we cannot rank semantically" signal — the caller then falls back to the
    literal ILIKE filter, i.e. exactly the behaviour that shipped before. A browse must never
    fail, and must never HANG, because of the embed provider."""
    if not q or not q.strip():
        return None
    try:
        return await asyncio.wait_for(embed_query(q.strip()), timeout=_SEARCH_EMBED_BUDGET_S)
    except (EmbeddingError, EmbedConfigError) as exc:
        logger.info("motif search: no query vector (%r) → literal filter", exc)
        return None
    except TimeoutError:
        logger.info("motif search: embed exceeded %.1fs → literal filter", _SEARCH_EMBED_BUDGET_S)
        return None


async def owns_motif(pool, caller_id, motif_id) -> bool:
    """Does `caller_id` own this motif? Used ONLY to turn an opaque refusal into an actionable
    one, never to decide access.

    🔴 WHY THIS DOES NOT WEAKEN H13, which is the same argument
    `EndpointsOwnedNotShared` already makes for create_link: the uniform refusal exists so a
    message is not an existence oracle for objects the caller does not own. This is consulted only
    AFTER a book-scoped lookup has failed, and it can only ever say "yes" about a row the caller
    OWNS and whose id it already holds. A "no" changes nothing — the uniform refusal still stands.
    """
    async with pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT 1 FROM motif WHERE id = $1 AND owner_user_id = $2", motif_id, caller_id,
        )
    return row is not None


class EndpointsOwnedNotShared(LookupError):
    """`create_link` was called WITH `book_id` over two motifs the caller owns.

    A LookupError subclass on purpose: every existing `except LookupError` keeps catching
    it unchanged, and a caller that wants to say something more useful can catch this
    first. See D-AN-OPTIONAL-ARG-SWITCHES-THE-MODE-AND-THE-REFUSAL-HIDES-IT — this is the
    one miss with an obvious remedy (drop `book_id`), and naming it leaks nothing, because
    the caller owns both endpoints and already holds their ids.
    """


class MotifRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self, user_id: UUID, args: MotifCreateArgs,
        *, source: str = "authored", imported_derived: bool = False,
        status: str = "active", judge_score: Any = None,
        mining_support: int | None = None,
        book_id: UUID | None = None, book_shared: bool = False,
    ) -> Motif:
        """Create a USER-tier motif. owner_user_id is STAMPED = user_id (never an
        arg → a both-NULL/system row is impossible from this path; the DB CHECK is
        the backstop). embedding starts NULL (W3 fills it). UNIQUE(owner,code,lang)
        violation → asyncpg.UniqueViolationError (router maps to 409).

        `source`/`imported_derived`/`status` default to the authored-active path
        (every existing caller is unchanged). W9's deconstruct passes
        source='imported', imported_derived=True so the B-3 lineage taint is set at
        birth (the publish-strip trigger reads it); a draft import passes
        status='draft'.

        `judge_score`/`mining_support` default NULL (the authored/imported paths
        leave them unset — those columns are F0-frozen, §2). W8's mining passes
        source='mined', status='draft' + the binary judge_score (0..1) + the
        PrefixSpan mining_support count so a mined draft carries its provenance for
        the review/promote UI. Added ADDITIVELY (every existing caller unchanged),
        the same way source/status were added for W9."""
        info = args.info_asymmetry.model_dump(mode="json") if args.info_asymmetry else None
        # book_shared (model B) targets the SHARED tier; the row stays private (the CHECK
        # motif_book_shared_shape backstops a shared row to visibility='private' + a book + owner).
        # The owner is STILL server-stamped = user_id (no owner arg → no cross-tenant injection).
        query = f"""
        INSERT INTO motif
          (owner_user_id, code, original_language, visibility, kind, category, name, summary,
           genre_tags, roles, beats, preconditions, effects, info_asymmetry,
           annotations, tension_target, emotion_target, examples, source,
           imported_derived, status, judge_score, mining_support, book_id, book_shared)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,
                $10::jsonb,$11::jsonb,$12::jsonb,$13::jsonb,$14::jsonb,$15::jsonb,
                $16,$17,$18::jsonb,$19,$20,$21,$22,$23,$24,$25)
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query,
                user_id, args.code, args.original_language, args.visibility, args.kind,
                args.category, args.name, args.summary, args.genre_tags,
                _jsonb(_dump_models(args.roles)), _jsonb(_dump_models(args.beats)),
                _jsonb(args.preconditions), _jsonb(args.effects),
                _jsonb(info) if info is not None else None,
                _jsonb(args.annotations), args.tension_target, args.emotion_target,
                _jsonb(args.examples), source, imported_derived, status,
                judge_score, mining_support, book_id, book_shared,
            )
        return _row_to_motif(row)

    async def get_visible(self, caller_id: UUID, motif_id: UUID) -> Motif | None:
        """THE read predicate (R1.1): returns the motif IFF system | public | owned
        by caller. A foreign PRIVATE motif returns None (IDOR-safe — the router maps
        None → the H13 uniform 'not found or not accessible', no existence oracle)."""
        query = f"""
        SELECT {_SELECT_COLS} FROM motif
        WHERE id = $2 AND {_VISIBLE_PREDICATE}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, caller_id, motif_id)
        return _row_to_motif(row) if row is not None else None

    async def get_by_codes(self, caller_id: UUID, codes: list[str]) -> dict[str, Motif]:
        """Resolve VISIBLE active motifs by exact code → {code: Motif} (W10 arc
        materialize). Tier-merged under the same R1.1 read predicate as get_visible;
        when a code exists in more than one visible tier, the CALLER'S OWN row shadows
        system/public (the resolution-merge order System→User). Codes with no visible
        match are simply absent from the map (the caller surfaces them as unresolved —
        no silent invention). Distinct caller-owned codes are unique, so the first row
        per code under the ordering is the correct winner."""
        uniq = sorted({c for c in codes if c})
        if not uniq:
            return {}
        query = f"""
        SELECT {_SELECT_COLS} FROM motif
        WHERE code = ANY($2) AND status = 'active' AND {_VISIBLE_PREDICATE}
        ORDER BY (owner_user_id = $1) DESC NULLS LAST, owner_user_id NULLS FIRST, version DESC
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, caller_id, uniq)
        out: dict[str, Motif] = {}
        for r in rows:
            m = _row_to_motif(r)
            out.setdefault(m.code, m)   # first per code wins (caller-owned ordered first)
        return out

    async def successors_by_ids(self, motif_ids: list[UUID]) -> dict[str, list[dict[str, Any]]]:
        """`precedes` legal-succession successors per motif (D-MOTIF-CHAIN-SUCCESSION-HINT)
        → ``{from_motif_id(str): [{code, name, ord}]}``, ordered by ``ord``. JOINs
        ``motif_link`` (kind='precedes') → the TARGET motif for its code+name.

        No extra visibility filter is needed: the F0 same-tier link guard
        (``motif_link_guard``) forbids a `precedes`/`composed_of` edge from crossing tiers,
        so a successor of a motif the caller can already see is itself in the caller's
        visible tier — no cross-tenant leak. Inactive (archived) targets are excluded."""
        uniq = list({m for m in motif_ids if m is not None})
        if not uniq:
            return {}
        query = """
        SELECT l.from_motif_id, m.id AS to_id, m.code, m.name, l.ord
        FROM motif_link l
        JOIN motif m ON m.id = l.to_motif_id
        WHERE l.kind = 'precedes' AND l.from_motif_id = ANY($1) AND m.status = 'active'
        ORDER BY l.from_motif_id, l.ord
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, uniq)
        out: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            out.setdefault(str(r["from_motif_id"]), []).append(
                {"id": str(r["to_id"]), "code": r["code"], "name": r["name"], "ord": r["ord"]})
        return out

    # ────────────────────────────────────────────────────────────────────────
    # motif_link edge-walk (D-MOTIF-LINK-EDGEWALK + D-MOTIF-LINK-SHARED-TIER) — traverse +
    # edit the relationship graph (composed_of / precedes / variant_of). The motif_link_guard
    # trigger enforces same-tier (both system | same-user-private | same-book-shared) + acyclicity
    # at the DB, but the system↔system hole (both owner NULL → "not distinct") slips the OLD owner
    # check — so the WRITE methods gate in the app too:
    #   • default (user tier): BOTH endpoints owned by the caller (a user may never reshape the
    #     system/foreign graph; the kinds-bug class).
    #   • book_id given (shared tier): BOTH endpoints `book_shared AND book_id=$book`, the caller
    #     EDIT-gated on the book at the tool (collaborators co-edit the book's shared graph).
    # READ is allowed for any VISIBLE anchor (own/system/public; + this book's shared tier when a
    # VIEW-gated book_id is passed), read-only.
    # ────────────────────────────────────────────────────────────────────────

    async def list_links(
        self, caller_id: UUID, motif_id: UUID, *,
        direction: str = "both", kinds: list[str] | None = None, limit: int = 200,
        book_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Edges touching a VISIBLE motif, each joined to its NEIGHBOR (id/code/name).
        `direction`: 'out' (motif→neighbor), 'in' (neighbor→motif), 'both'. Returns []
        if the anchor isn't visible to the caller (router maps the empty/None to H13 at
        the tool). Neighbors are re-filtered by the read predicate (defense-in-depth —
        the same-tier guard already keeps them in the caller's visible tier).

        With `book_id` (D-MOTIF-LINK-SHARED-TIER): the anchor is read in the (VIEW-gated) book
        context (own | system | this book's shared tier) and the neighbor filter ALSO admits the
        book's shared rows — so a grantee sees the shared graph. A foreign shared row stays hidden
        in the non-book path (get_visible)."""
        if book_id is not None:
            anchor = await self.get_in_book(caller_id, motif_id, book_id)
        else:
            anchor = await self.get_visible(caller_id, motif_id)
        if anchor is None:
            return []
        params: list[Any] = [caller_id, motif_id]
        neighbor_pred = _VISIBLE_PREDICATE
        if book_id is not None:
            params.append(book_id)
            neighbor_pred = f"({_VISIBLE_PREDICATE} OR (book_shared AND book_id = ${len(params)}))"
        kind_clause = ""
        if kinds:
            params.append(list(kinds))
            kind_clause = f" AND l.kind = ANY(${len(params)})"
        params.append(max(0, limit))
        limit_pos = len(params)
        arms: list[str] = []
        if direction in ("out", "both"):
            arms.append(f"""
            SELECT l.id, l.kind, l.ord, 'out' AS direction,
                   m.id AS neighbor_id, m.code AS neighbor_code, m.name AS neighbor_name
            FROM motif_link l JOIN motif m ON m.id = l.to_motif_id
            WHERE l.from_motif_id = $2 AND {neighbor_pred}{kind_clause}""")
        if direction in ("in", "both"):
            arms.append(f"""
            SELECT l.id, l.kind, l.ord, 'in' AS direction,
                   m.id AS neighbor_id, m.code AS neighbor_code, m.name AS neighbor_name
            FROM motif_link l JOIN motif m ON m.id = l.from_motif_id
            WHERE l.to_motif_id = $2 AND {neighbor_pred}{kind_clause}""")
        if not arms:
            return []
        query = f"{' UNION ALL '.join(arms)} ORDER BY kind, ord NULLS LAST LIMIT ${limit_pos}"
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, *params)
        return [
            {
                "id": str(r["id"]), "kind": r["kind"], "ord": r["ord"],
                "direction": r["direction"],
                "neighbor": {"id": str(r["neighbor_id"]), "code": r["neighbor_code"],
                             "name": r["neighbor_name"]},
            }
            for r in rows
        ]

    async def create_link(
        self, caller_id: UUID, from_motif_id: UUID, to_motif_id: UUID, kind: str,
        *, ord: int | None = None, book_id: UUID | None = None,
    ) -> "MotifLink":
        """Create one edge. Default (no book_id): between TWO motifs the caller OWNS (the
        both-owned app gate — a user may not touch the system/foreign graph; the DB same-tier
        guard misses system↔system). With `book_id` (D-MOTIF-LINK-SHARED-TIER): between two SHARED
        motifs of THAT book — the caller must hold EDIT on the book (gated at the tool) and BOTH
        endpoints must be `book_shared AND book_id=$book` (a different book's shared row, a private,
        or a system row is rejected; the DB guard backstops same-book-shared). Raises LookupError if
        an endpoint isn't in the required scope; UniqueViolationError on a duplicate edge;
        CheckViolationError on a self-link/cycle/cross-tier the DB trigger rejects."""
        from app.db.models import MotifLink
        async with self._pool.acquire() as c:
            if book_id is not None:
                rows = await c.fetch(
                    "SELECT id, book_shared, book_id FROM motif WHERE id = ANY($1)",
                    [from_motif_id, to_motif_id],
                )
                shared = {r["id"]: (r["book_shared"], r["book_id"]) for r in rows}

                def _in_book(mid: UUID) -> bool:
                    s = shared.get(mid)
                    return s is not None and s[0] and s[1] == book_id

                if not _in_book(from_motif_id) or not _in_book(to_motif_id):
                    # D-AN-OPTIONAL-ARG-SWITCHES-THE-MODE-AND-THE-REFUSAL-HIDES-IT — separate the
                    # RECOVERABLE miss from the rest. `book_id` silently selects between two
                    # endpoint rules, and a caller who passed it over TWO MOTIFS IT OWNS has made
                    # the one mistake that has an obvious remedy: drop book_id. Measured
                    # 2026-08-24 (batch c-motiflink5): the model resolved both real ids, passed the
                    # ambient book_id, and was told "not found or not accessible" about motifs it
                    # had just listed — with no path back to the working call.
                    #
                    # This does NOT weaken H13. The uniform message exists so a refusal is not an
                    # existence oracle for objects the caller does not own; here it owns both and
                    # already holds their ids, so naming the remedy discloses nothing new. Every
                    # other miss still raises the plain LookupError the tool maps to H13.
                    owners = await c.fetch(
                        "SELECT id, owner_user_id FROM motif WHERE id = ANY($1)",
                        [from_motif_id, to_motif_id],
                    )
                    owned = {r["id"]: r["owner_user_id"] for r in owners}
                    if (owned.get(from_motif_id) == caller_id
                            and owned.get(to_motif_id) == caller_id):
                        raise EndpointsOwnedNotShared(
                            "both endpoints are motifs you own and are not shared into this book"
                        )
                    raise LookupError("both endpoints must be shared motifs in this book")
            else:
                owners = await c.fetch(
                    "SELECT id, owner_user_id FROM motif WHERE id = ANY($1)",
                    [from_motif_id, to_motif_id],
                )
                owned = {r["id"]: r["owner_user_id"] for r in owners}
                if owned.get(from_motif_id) != caller_id or owned.get(to_motif_id) != caller_id:
                    raise LookupError("both endpoints must be motifs you own")
            row = await c.fetchrow(
                """
                INSERT INTO motif_link (from_motif_id, to_motif_id, kind, ord)
                VALUES ($1, $2, $3, $4)
                RETURNING id, from_motif_id, to_motif_id, kind, ord, created_at
                """,
                from_motif_id, to_motif_id, kind, ord,
            )
        return MotifLink.model_validate(dict(row))

    async def delete_link(
        self, caller_id: UUID, link_id: UUID, *, book_id: UUID | None = None,
    ) -> bool:
        """Delete one edge. Default (no book_id): an edge the caller OWNS (its from_motif is the
        caller's — and by the same-tier guard the to_motif is too). With `book_id`
        (D-MOTIF-LINK-SHARED-TIER): an edge in THAT book's SHARED graph (its from_motif is
        `book_shared AND book_id=$book`; the caller is EDIT-gated on the book at the tool). A
        foreign/system/missing/wrong-book edge is a no-op the router maps to H13. Returns True iff
        a row was removed."""
        async with self._pool.acquire() as c:
            if book_id is not None:
                tag = await c.execute(
                    """
                    DELETE FROM motif_link l USING motif m
                    WHERE l.id = $2 AND m.id = l.from_motif_id
                      AND m.book_shared AND m.book_id = $1
                    """,
                    book_id, link_id,
                )
                return tag.rsplit(" ", 1)[-1] != "0"
            tag = await c.execute(
                """
                DELETE FROM motif_link l USING motif m
                WHERE l.id = $2 AND m.id = l.from_motif_id AND m.owner_user_id = $1
                """,
                caller_id, link_id,
            )
        return tag.rsplit(" ", 1)[-1] != "0"

    async def patch(
        self, caller_id: UUID, motif_id: UUID, args: MotifPatchArgs, *, expected_version: int,
        repin_source_version: int | None = None, repin_adopted_base: str | None = None,
    ) -> Motif | None:
        """Optimistic-lock edit, OWNER-only (WHERE owner_user_id = caller_id — a
        system or foreign motif is never patchable here). Bumps version, sets
        updated_at. On a summary change, embedded_summary_hash is cleared so W3's
        re-embed fires. Returns None if the row isn't the caller's (router → H13);
        raises VersionMismatchError(current) on a stale expected_version.

        ``repin_source_version`` (W11 sync, D-MOTIF-SYNC-REPIN-ATOMICITY): when set, the
        upstream-lineage pin is updated IN THE SAME UPDATE as the content merge — so an
        accept-upstream + re-pin is ONE atomic statement (no crash window leaving a bumped
        version with a stale source_version). Default None = unchanged for every other caller.

        (Return is Motif|None to match the canon_rules/works house convention; the
        frozen CONTRACT is the parameter names + the version-mismatch raise.)"""
        # OWNER scope: only the caller's own row. Shared-tier edits go through patch_shared.
        return await self._patch(
            "owner_user_id = $1", caller_id, motif_id, args,
            expected_version=expected_version,
            repin_source_version=repin_source_version,
            repin_adopted_base=repin_adopted_base,
        )

    async def patch_shared(
        self, caller_id: UUID, motif_id: UUID, book_id: UUID, args: MotifPatchArgs,
        *, expected_version: int,
    ) -> Motif | None:
        """EDIT-grantee write to a SHARED book-tier row (D-MOTIF-ADOPT-BOOK-COLLAB-TIER). The
        caller MUST already hold EDIT on `book_id` (gated at the router/tool — access is the book
        grant, NOT ownership). Keys on `book_shared AND book_id` instead of owner, so ANY grantee
        may edit; the optimistic-lock `version` still blocks a blind clobber between collaborators.
        Returns None if no shared row in that book matches (router → H13); raises VersionMismatch
        on a stale expected_version. `caller_id` is unused in the predicate (the grant is the gate);
        it stays in the signature for call-site symmetry + future audit logging."""
        return await self._patch(
            "book_shared AND book_id = $1", book_id, motif_id, args,
            expected_version=expected_version,
        )

    async def _patch(
        self, scope_clause: str, scope_param: Any, motif_id: UUID, args: MotifPatchArgs,
        *, expected_version: int,
        repin_source_version: int | None = None, repin_adopted_base: str | None = None,
    ) -> Motif | None:
        """Shared body for patch (owner scope) + patch_shared (book-shared scope). `scope_clause`
        is the ownership/tenancy WHERE arm referencing $1 (bound to `scope_param`); $2 = motif_id;
        the version param is appended last."""
        sets: list[str] = []
        params: list[Any] = [scope_param, motif_id]
        data = args.model_dump(exclude_unset=True)
        for field, value in data.items():
            if field in ("roles", "beats"):
                value = _dump_models(getattr(args, field) or [])
            if field == "info_asymmetry":
                value = args.info_asymmetry.model_dump(mode="json") if args.info_asymmetry else None
            if field in _JSONB_FIELDS:
                params.append(_jsonb(value) if value is not None else None)
                sets.append(f"{field} = ${len(params)}::jsonb")
            else:
                params.append(value)
                sets.append(f"{field} = ${len(params)}")
        if "summary" in data:
            sets.append("embedded_summary_hash = NULL")  # W3 re-embeds on next retrieve
        if repin_source_version is not None:
            params.append(repin_source_version)
            sets.append(f"source_version = ${len(params)}")
        if repin_adopted_base is not None:
            params.append(repin_adopted_base)
            sets.append(f"adopted_base = ${len(params)}::jsonb")
        sets.append("version = version + 1")
        sets.append("updated_at = now()")
        params.append(expected_version)
        query = f"""
        UPDATE motif SET {", ".join(sets)}
        WHERE {scope_clause} AND id = $2 AND version = ${len(params)}
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, *params)
            if row is not None:
                return _row_to_motif(row)
            # distinguish not-in-scope/not-found (→ None) from a stale version (→ raise).
            current = await c.fetchrow(
                f"SELECT {_SELECT_COLS} FROM motif WHERE {scope_clause} AND id = $2",
                scope_param, motif_id,
            )
        if current is None:
            return None
        raise VersionMismatchError(_row_to_motif(current))

    async def archive(self, caller_id: UUID, motif_id: UUID) -> None:
        """Soft-archive (status='archived'), OWNER-only. Idempotent. A foreign/
        missing id is a no-op the router maps to H13 (no oracle). NOT a hard delete
        — motif_application FK is SET NULL, so history survives (data-R3)."""
        async with self._pool.acquire() as c:
            await c.execute(
                "UPDATE motif SET status = 'archived', updated_at = now() "
                "WHERE owner_user_id = $1 AND id = $2 AND status <> 'archived'",
                caller_id, motif_id,
            )

    async def archive_shared(self, caller_id: UUID, motif_id: UUID, book_id: UUID) -> None:
        """Archive a SHARED book-tier row (D-MOTIF-ADOPT-BOOK-COLLAB-TIER) — any EDIT-grantee may
        (the caller is EDIT-gated on `book_id` at the router/tool). Keys on book_shared AND book_id,
        not owner. Idempotent; a foreign/other-book id is a no-op (router → H13)."""
        async with self._pool.acquire() as c:
            await c.execute(
                "UPDATE motif SET status = 'archived', updated_at = now() "
                "WHERE book_shared AND book_id = $2 AND id = $1 AND status <> 'archived'",
                motif_id, book_id,
            )

    async def restore(self, caller_id: UUID, motif_id: UUID) -> Motif | None:
        """S-08 — archive()'s exact inverse (the reverse verb the archive tool's undo points at).
        OWNER-only. A status-only flip archived→active that RETURNS the row (so the FE refreshes);
        None if the row is missing / not-owned / NOT archived (router → 404). Mirrors
        canon_rules.restore: it must NOT bump version or touch any other field, and takes no OCC —
        an archived row has no concurrent editor."""
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                f"UPDATE motif SET status = 'active', updated_at = now() "
                f"WHERE owner_user_id = $1 AND id = $2 AND status = 'archived' "
                f"RETURNING {_SELECT_COLS}",
                caller_id, motif_id,
            )
        return _row_to_motif(row) if row is not None else None

    async def restore_shared(self, caller_id: UUID, motif_id: UUID, book_id: UUID) -> Motif | None:
        """Restore a SHARED book-tier row — the inverse of archive_shared, any EDIT-grantee (the caller
        is EDIT-gated on `book_id` at the router/tool). Keys on book_shared AND book_id, not owner.
        Returns the row; None if no ARCHIVED shared row in that book matches (router → 404)."""
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                f"UPDATE motif SET status = 'active', updated_at = now() "
                f"WHERE book_shared AND book_id = $2 AND id = $1 AND status = 'archived' "
                f"RETURNING {_SELECT_COLS}",
                motif_id, book_id,
            )
        return _row_to_motif(row) if row is not None else None

    async def _localize(
        self, motifs: list[Motif], display_language: str | None
    ) -> list[Motif]:
        """`apply_display_language` for a caller that has already released its connection."""
        if not motifs or not normalize_display_language(display_language):
            return motifs
        async with self._pool.acquire() as c:
            return await apply_display_language(c, motifs, display_language)

    # ── the user-paid translate path (docs/plans/2026-07-29-motif-translate-runtime.md)
    async def list_translatable(
        self, caller_id: UUID, motif_ids: list[UUID], *, book_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """The subset of `motif_ids` this caller is ALLOWED to buy a translation for.

        TENANCY — this is the gate, and it is deliberately narrower than the read
        predicate. A `motif_translation` row on a SYSTEM motif is System tier: seeded,
        admin-managed, shared by every user. Letting a regular user write one is the
        kinds bug exactly (`owner_user_id IS NULL` is therefore excluded here even
        though every read path shows system rows). A PUBLIC motif someone else owns is
        likewise refused — the spec's answer is that you adopt it first, which clones
        it into your tier, and then it is yours to translate.

        So: your own rows, or this book's SHARED tier when you hold EDIT on the book
        (gated at the router/tool, as everywhere else — never here).
        """
        if not motif_ids:
            return []
        params: list[Any] = [caller_id, motif_ids]
        scope = "owner_user_id = $1"
        if book_id is not None:
            params.append(book_id)
            scope = f"(owner_user_id = $1 OR (book_shared AND book_id = ${len(params)}))"
        query = f"""
        SELECT {_SELECT_COLS} FROM motif
        WHERE id = ANY($2::uuid[]) AND status <> 'archived' AND {scope}
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, *params)
        out: list[dict[str, Any]] = []
        for r in rows:
            data = dict(r)
            for f in _JSONB_FIELDS:
                if isinstance(data.get(f), str):
                    data[f] = json.loads(data[f])
            out.append(data)
        return out

    async def list_translations(self, motif_id: UUID) -> list[dict[str, Any]]:
        """Which languages this motif already reads in, and whether each is current.

        The detail drawer needs this because it deliberately shows the motif as
        AUTHORED, not localized: it is the surface the owner edits from, and the PATCH
        is whole-object — rendering a translation there and saving would write the
        translated wording onto the source row and destroy the original. So the drawer
        states the original language and lists the translations alongside it, instead of
        silently becoming one of them.
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(
                "SELECT t.language_code, t.source, t.translated_by, t.updated_at, "
                "  t.source_content_hash AS made_from, "
                "  m.name, m.summary, m.emotion_target, m.roles, m.beats, "
                "  m.preconditions, m.effects, m.examples "
                "FROM motif_translation t JOIN motif m ON m.id = t.motif_id "
                "WHERE t.motif_id = $1 ORDER BY t.language_code",
                motif_id,
            )
        out: list[dict[str, Any]] = []
        for r in rows:
            data = dict(r)
            for f in _JSONB_FIELDS:
                if isinstance(data.get(f), str):
                    data[f] = json.loads(data[f])
            out.append({
                "language_code": data["language_code"],
                "source": data["source"],
                "translated_by": data["translated_by"],
                "updated_at": data["updated_at"],
                "stale": (data.get("made_from") or "") != source_hash(data),
            })
        return out

    async def get_translation_state(
        self, motif_id: UUID, language_code: str,
    ) -> dict[str, Any] | None:
        """`{source, stale}` for an existing translation, or None if there is none.

        `stale` compares the hash the translation was MADE from against the motif's
        current translatable payload — the same signal the read path badges with. It is
        what lets a re-translate be free when nothing moved and paid when it did.
        """
        # Every translatable column exists on BOTH tables, so each one is qualified —
        # an unqualified `name` here is an ambiguous-column error, not a wrong answer.
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT t.source AS tr_source, t.source_content_hash AS made_from, "
                "  m.name, m.summary, m.emotion_target, m.roles, m.beats, "
                "  m.preconditions, m.effects, m.examples "
                "FROM motif_translation t JOIN motif m ON m.id = t.motif_id "
                "WHERE t.motif_id = $1 AND t.language_code = $2",
                motif_id, language_code,
            )
        if row is None:
            return None
        data = dict(row)
        for f in _JSONB_FIELDS:
            if isinstance(data.get(f), str):
                data[f] = json.loads(data[f])
        return {
            "source": data["tr_source"],
            "stale": (data.get("made_from") or "") != source_hash(data),
        }

    async def upsert_translation(
        self, motif_id: UUID, language_code: str, payload: dict[str, Any],
        *, source_content_hash: str, translated_by: str,
    ) -> bool:
        """Write a MACHINE translation. False when an `authored` row refused it.

        The conflict rule is the seeder's, byte for byte: machine output never lands on
        top of a hand-written translation. The 84 Vietnamese motifs were written by a
        person, and a user idly re-translating their library must not be able to
        overwrite them — nor a user's own hand-corrected wording.
        """
        async with self._pool.acquire() as c:
            res = await c.execute(
                """
                INSERT INTO motif_translation (
                  motif_id, language_code, name, summary, emotion_target,
                  roles, beats, preconditions, effects, examples,
                  source_content_hash, source, translated_by
                ) VALUES (
                  $1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8::jsonb, $9::jsonb,
                  $10::jsonb, $11, 'machine', $12
                )
                ON CONFLICT (motif_id, language_code) DO UPDATE SET
                  name = EXCLUDED.name, summary = EXCLUDED.summary,
                  emotion_target = EXCLUDED.emotion_target,
                  roles = EXCLUDED.roles, beats = EXCLUDED.beats,
                  preconditions = EXCLUDED.preconditions, effects = EXCLUDED.effects,
                  examples = EXCLUDED.examples,
                  source_content_hash = EXCLUDED.source_content_hash,
                  source = EXCLUDED.source, translated_by = EXCLUDED.translated_by,
                  updated_at = now()
                WHERE motif_translation.source <> 'authored'
                """,
                motif_id, language_code,
                payload.get("name") or "", payload.get("summary") or "",
                payload.get("emotion_target") or None,
                _jsonb(payload.get("roles") or []), _jsonb(payload.get("beats") or []),
                _jsonb(payload.get("preconditions") or []),
                _jsonb(payload.get("effects") or []),
                _jsonb(payload.get("examples") or []),
                source_content_hash, translated_by,
            )
        # asyncpg returns "INSERT 0 <n>" — n == 0 means the authored guard held.
        return not res.endswith(" 0")

    async def list_in_book(
        self, caller_id: UUID, book_id: UUID, *, genre: str | None = None,
        kind: str | None = None, status: str | None = "active", q: str | None = None,
        display_language: str | None = None, limit: int = 100,
    ) -> list[Motif]:
        """Book-context list (D-MOTIF-ADOPT-BOOK-COLLAB-TIER). The CALLER MUST have VIEW-gated
        `book_id` first — the grant is resolved at the router/tool, NEVER here. Returns, for this
        book: the caller's OWN rows (their globals + this book's model-A private labels) PLUS the
        book's SHARED tier (book_shared rows owned by ANY collaborator) PLUS system rows. A foreign
        user's globals, another book's rows, and others' public rows are EXCLUDED."""
        params: list[Any] = [caller_id, book_id]   # $1 caller, $2 book
        where = [
            # own (any) | system | this book's shared tier — NOT public/foreign.
            "(owner_user_id IS NULL OR owner_user_id = $1 OR (book_shared AND book_id = $2))",
            # narrow to this book's rows + globals (own globals + system have book_id NULL).
            "(book_id IS NULL OR book_id = $2)",
        ]
        if genre is not None:
            params.append(genre)
            where.append(f"${len(params)} = ANY(genre_tags)")
        if kind is not None:
            params.append(kind)
            where.append(f"kind = ${len(params)}")
        if status is not None:
            params.append(status)
            where.append(f"status = ${len(params)}")
        # NOTE: `display_language` is deliberately NOT a WHERE clause. It used to be —
        # and a filter can only ever SUBTRACT, so asking for Vietnamese hid every motif
        # not stored in Vietnamese instead of showing them translated. It is applied
        # after selection, as a re-wording with fallback.
        if q:
            ranked = await self._rank_by_query(
                where, params, q, limit, "book_shared DESC, owner_user_id NULLS FIRST, name",
                caller_id=caller_id)
            if ranked is not None:
                return await self._localize(ranked, display_language)
            params.append(f"%{q}%")
            where.append(f"(name ILIKE ${len(params)} OR summary ILIKE ${len(params)})")
        params.append(max(0, limit))
        query = f"""
        SELECT {_SELECT_COLS} FROM motif
        WHERE {" AND ".join(where)}
        ORDER BY book_shared DESC, owner_user_id NULLS FIRST, name
        LIMIT ${len(params)}
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, *params)
            return await apply_display_language(
                c, [_row_to_motif(r) for r in rows], display_language)

    async def get_in_book(
        self, caller_id: UUID, motif_id: UUID, book_id: UUID,
    ) -> Motif | None:
        """Single read inside a (VIEW-gated) book context: the row IFF it's the caller's OWN, a
        SYSTEM row, or this book's SHARED tier. A foreign-private or another-book shared row → None
        (H13, no oracle). The caller MUST have VIEW-gated `book_id` at the router/tool."""
        query = f"""
        SELECT {_SELECT_COLS} FROM motif
        WHERE id = $3
          AND (owner_user_id IS NULL OR owner_user_id = $1 OR (book_shared AND book_id = $2))
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, caller_id, book_id, motif_id)
        return _row_to_motif(row) if row is not None else None

    async def _warm_stale_vectors(
        self, rows: list[asyncpg.Record], caller_id: UUID | None, platform_ref: str | None,
    ) -> dict[UUID, list[float]]:
        """Re-embed, bounded and concurrently, the rows a search could not judge.

        Returns {motif_id: vector} for the ones that succeeded; a failure is simply absent (the
        row then rides on its literal hit alone — never invented into the results).

        BOUNDED because this rides an interactive request: at most `_WARM_CAP` rows, and they
        are gathered so the wall-clock is about one round-trip rather than N of them. The
        library therefore self-heals over the first few searches after a deploy instead of
        staying semantically dark until an unrelated planning run happens to touch it.

        TENANCY: the UPDATE is scoped `owner_user_id IS NULL OR owner_user_id = $2`, so a read
        by one user can never rewrite another tenant's vector — the same scope the retrieve
        path's back-fill uses."""
        if platform_ref is None:
            return {}                          # no platform model → nothing legitimate to write
        stale = [
            r for r in rows
            if (r["embedding"] is None
                or r["embedding_model"] != platform_ref
                or r["embedded_summary_hash"] != summary_hash(
                    motif_summary_text(_row_to_motif(r))))
            and (r["owner_user_id"] is None or r["owner_user_id"] == caller_id)
        ][:_WARM_CAP]
        if not stale:
            return {}

        async def _one(row) -> tuple[UUID, list[float]] | None:
            try:
                text = motif_summary_text(_row_to_motif(row))
                if not text:
                    return None
                res = await embed_motif_summary(text)
                vec = res.embeddings[0]
                async with self._pool.acquire() as c:
                    await c.execute(
                        "UPDATE motif SET embedding = $3::real[], embedding_model = $4, "
                        "embedding_dim = $5, embedded_summary_hash = $6 "
                        "WHERE id = $1 AND (owner_user_id IS NULL OR owner_user_id = $2)",
                        row["id"], caller_id, list(vec), platform_ref, len(vec),
                        summary_hash(text))
                return row["id"], vec
            except (EmbeddingError, EmbedConfigError, TimeoutError) as exc:
                logger.info("motif search: warm skipped for %s (%r)", row["id"], exc)
                return None

        try:
            done = await asyncio.wait_for(
                asyncio.gather(*(_one(r) for r in stale), return_exceptions=True),
                timeout=_WARM_BUDGET_S)
        except TimeoutError:
            logger.info("motif search: vector warm exceeded %.1fs — ranking on what is fresh",
                        _WARM_BUDGET_S)
            return {}
        out: dict[UUID, list[float]] = {}
        for res in done:
            if isinstance(res, tuple):
                out[res[0]] = res[1]
            elif isinstance(res, BaseException):
                # `return_exceptions=True` must not become a silent swallow — an unexpected
                # failure here is a defect to see in the logs, not a quietly missing motif.
                logger.warning("motif search: unexpected warm failure: %r", res)
        return out

    async def _rank_by_query(
        self, where: list[str], params: list[Any], q: str, limit: int, order_by: str,
        *, caller_id: UUID | None = None,
    ) -> list[Motif] | None:
        """THE text-query ranker, shared by every list surface. Returns None when it cannot
        rank (no query vector) so the caller keeps its literal-ILIKE behaviour.

        WHY THIS EXISTS. `q` was an ILIKE in the WHERE clause on all three list methods — and a
        WHERE clause can only ever SUBTRACT. Type a phrase whose words are not literally in a
        name or summary and you get nothing: searching `witness contradicts testimony` returned
        0 rows while `mystery.witness_who_lies` sat right there, because the user has to guess
        which words the author happened to use. The PLANNER, meanwhile, has been ranking the
        same library by cosine since the premise-seeding fix — so the human had a strictly
        weaker instrument than the model did. This is the same bug shape as the genre/language
        hard filters on retrieval, and it gets the same treatment: move `q` from FILTER to RANK.

        The rules, in order:
          · a LITERAL hit always outranks a semantic one (+1.0). Someone typing an exact name or
            code wants that row, not something merely similar — precision beats fuzziness, and
            this is what makes the change purely ADDITIVE: every row the old ILIKE returned is
            still returned, still at the top.
          · a semantic hit below `motif_min_score` is dropped. Same knob the planner uses — the
            question ("is this motif actually about that?") is the same question, so it gets one
            name and one home rather than a second threshold to keep in sync.
          · a row whose vector is MISSING or STALE cannot be judged semantically, so it rides on
            its literal hit alone and is never invented into the results. A just-created motif is
            therefore findable by its own words immediately, and semantically once the retrieve
            path's back-fill has embedded it.
        """
        qvec = await _query_vector(q)
        if qvec is None:
            return None
        platform_ref = None
        try:
            platform_ref = _platform_embed_model()[1]
        except EmbedConfigError:
            pass
        rank_params = [*params, _SEARCH_CEILING]
        sql = f"""
        SELECT {_SEARCH_COLS} FROM motif
        WHERE {" AND ".join(where)}
        ORDER BY {order_by}
        LIMIT ${len(rank_params)}
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(sql, *rank_params)

        # Rows whose vector is missing or no longer describes their text cannot be judged
        # semantically. That is now a ROUTINE state, not an edge case: the boot seeder updates
        # pack content on a `source_version` bump, which by design leaves the stored vector
        # stale — so after every deploy that edits a pack, exactly the motifs whose wording was
        # just improved would be invisible to semantic search until some unrelated planning run
        # happened to back-fill them. Warm them here, bounded and CONCURRENTLY (so the cost is
        # about one round-trip, not N), and the library self-heals on the first search.
        needle = q.strip().casefold()
        floor = settings.motif_min_score
        warmed = await self._warm_stale_vectors(rows, caller_id, platform_ref)
        # TWO TIERS, not one arithmetic score. A literal hit scoring `1.0 + cosine` can TIE a
        # perfect semantic match at 1.0 (and cosine may be negative, putting a literal hit
        # BELOW one), at which point the winner is decided by alphabetical tie-break — which is
        # exactly the accidental-ordering bug this session already fixed once in retrieval.
        # Ranking by (tier, score) says the rule instead of encoding it in a magic constant.
        scored: list[tuple[int, float, str, Motif]] = []
        for r in rows:
            motif = _row_to_motif(r)
            literal = needle in f"{motif.name} {motif.summary} {motif.code}".casefold()
            # A stored vector counts only if it is a platform vector AND still describes the
            # row's CURRENT text (the same staleness rule the retrieve path enforces).
            usable = (
                r["embedding"] is not None
                and (platform_ref is None or r["embedding_model"] == platform_ref)
                and r["embedded_summary_hash"] == summary_hash(motif_summary_text(motif))
            )
            vec = list(r["embedding"]) if usable else warmed.get(r["id"])
            usable = vec is not None
            cos = _cosine(qvec, vec) if usable else 0.0
            if literal:
                tier = 1                       # precise: always above anything merely similar
            elif usable and cos >= floor:
                tier = 0
            else:
                continue                       # unjudgeable and not a literal hit → never invented
            scored.append((tier, cos, motif.code, motif))
        scored.sort(key=lambda t: (-t[0], -t[1], t[2]))
        return [m for _t, _s, _c, m in scored[: max(0, limit)]]

    async def list_for_caller(
        self, caller_id: UUID, *, scope: str = "all", genre: str | None = None,
        kind: str | None = None, status: str | None = "active", q: str | None = None,
        display_language: str | None = None, book_id: UUID | None = None, limit: int = 100,
        offset: int = 0,
    ) -> list[Motif]:
        """Tier-merged list under the read predicate (system | public | owner).
        `scope` narrows the predicate: 'system' (owner NULL), 'user' (owner=caller),
        'public' (visibility=public), 'all' (the full predicate). genre filters the
        GIN array; q is an ILIKE on name/summary; status/kind are exact. `display_language`
        is a re-wording applied AFTER selection, never a filter — see `apply_display_language`.
        System rows sort first (NULLS FIRST), then name."""
        # caller_id is bound as $1 ONLY when the scope's SQL references it. A
        # 'system'/'public' scope filters on owner_user_id/visibility alone — binding an
        # UNUSED $1 makes asyncpg raise IndeterminateDatatypeError (it can't infer the
        # type of a parameter no clause uses). R-NODE-P1 caught this 500 on
        # GET /motifs?scope=system; the default 'all' path masked it (it uses $1).
        params: list[Any] = []
        if scope == "system":
            where = ["owner_user_id IS NULL"]
        elif scope == "public":
            where = ["visibility = 'public'"]
        elif scope == "user":
            params.append(caller_id)            # $1
            where = ["owner_user_id = $1"]
        else:  # 'all' — the tier-merged predicate references $1 (caller_id)
            params.append(caller_id)            # $1
            where = [_VISIBLE_PREDICATE]
        if genre is not None:
            params.append(genre)
            where.append(f"${len(params)} = ANY(genre_tags)")
        if kind is not None:
            params.append(kind)
            where.append(f"kind = ${len(params)}")
        if status is not None:
            params.append(status)
            where.append(f"status = ${len(params)}")
        if book_id is not None:
            # The book-library view (D-MOTIF-ADOPT-PER-BOOK): motifs AVAILABLE to this book
            # = its per-book clones PLUS the caller's globals (book_id NULL). Combined with
            # the tier predicate above (so a system/public global still surfaces here).
            params.append(book_id)
            where.append(f"(book_id = ${len(params)} OR book_id IS NULL)")
        if q:
            # RANK, not filter (see `_rank_by_query`). Offset is meaningless on a ranked set,
            # so paging past page 1 keeps the literal path — the ranked answer is the top-N.
            if not offset:
                ranked = await self._rank_by_query(
                    where, params, q, limit, "owner_user_id NULLS FIRST, name",
                    caller_id=caller_id)
                if ranked is not None:
                    return await self._localize(ranked, display_language)
            params.append(f"%{q}%")
            where.append(f"(name ILIKE ${len(params)} OR summary ILIKE ${len(params)})")
        params.append(max(0, limit))
        limit_pos = len(params)
        params.append(max(0, offset))
        query = f"""
        SELECT {_SELECT_COLS} FROM motif
        WHERE {" AND ".join(where)}
        ORDER BY owner_user_id NULLS FIRST, name
        LIMIT ${limit_pos} OFFSET ${len(params)}
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, *params)
            return await apply_display_language(
                c, [_row_to_motif(r) for r in rows], display_language)

    async def clone(
        self, caller_id: UUID, src_motif_id: UUID, *, target_owner: UUID,
        retag_genres: list[str] | None = None, book_id: UUID | None = None,
        book_shared: bool = False,
    ) -> Motif:
        """The ONE clone primitive (= adopt = clone-to-customize = cross-genre retag;
        R1.1.1). Reads the SOURCE under the read predicate (so you may only clone what
        you can see — public/system/own), then INSERTs a NEW private row owned by
        target_owner: id/version reset, source='adopted', source_ref='lineage:'||src.id,
        source_version=src.version, embedding + embedded_summary_hash COPIED (same
        platform space → cosine valid AND the copied vector reads as FRESH, so W3 does
        NOT redundantly re-embed an unchanged-summary clone — the W3↔W1 seam; a later
        summary edit clears the hash via patch()), genre_tags retagged if given. Raises
        UniqueViolationError on a code collision in target's tier (the caller owns the
        rename policy — W1 adopt suffixes). Raises LookupError if the source isn't
        visible to the caller."""
        async with self._pool.acquire() as c:
            src = await c.fetchrow(
                f"""
                SELECT {_SELECT_COLS}, embedding, embedded_summary_hash FROM motif
                WHERE id = $2 AND {_VISIBLE_PREDICATE}
                """,
                caller_id, src_motif_id,
            )
            if src is None:
                raise LookupError("source motif not found or not accessible")
            s = dict(src)
            genres = retag_genres if retag_genres is not None else list(s["genre_tags"])
            # B-3 lineage taint: a clone of an imported (or already-tainted) motif stays
            # tainted so the publish-strip trigger fires on an adopted-from-imported
            # publish; adopted-from-AUTHORED stays false (those examples are shareable).
            tainted = s["source"] == "imported" or bool(s["imported_derived"])
            # D-MOTIF-SYNC-3WAY-BASE: snapshot the upstream's mergeable fields AT adopt
            # time = the true merge base. A later sync diffs base↔ours (local edits) ↔
            # theirs (upstream current) for per-field conflict detection. genre_tags is the
            # SOURCE's tags (a retag at adopt is a local change vs this base).
            adopted_base = _jsonb({
                "summary": s["summary"],
                "genre_tags": list(s["genre_tags"]),
                "beats": _coerce_jsonb_value(s["beats"]),
                "roles": _coerce_jsonb_value(s["roles"]),
                "preconditions": _coerce_jsonb_value(s["preconditions"]),
                "effects": _coerce_jsonb_value(s["effects"]),
            })
            row = await c.fetchrow(
                f"""
                INSERT INTO motif
                  (owner_user_id, book_id, book_shared, code, original_language, visibility, kind, category, name,
                   summary, genre_tags, roles, beats, preconditions, effects,
                   info_asymmetry, annotations, tension_target, emotion_target,
                   examples, abstraction_confidence, source, imported_derived,
                   source_ref, source_version,
                   embedding, embedding_model, embedding_dim, embedded_summary_hash,
                   adopted_base)
                VALUES ($1,$27,$28,$2,$3,'private',$4,$5,$6,$7,$8,
                        $9::jsonb,$10::jsonb,$11::jsonb,$12::jsonb,$13::jsonb,$14::jsonb,
                        $15,$16,$17::jsonb,$18,'adopted',$25,$19,$20,
                        $21,$22,$23,$24,$26::jsonb)
                RETURNING {_SELECT_COLS}
                """,
                target_owner, s["code"], s["original_language"], s["kind"], s["category"],
                s["name"], s["summary"], genres,
                _passthru_jsonb(s["roles"]), _passthru_jsonb(s["beats"]),
                _passthru_jsonb(s["preconditions"]), _passthru_jsonb(s["effects"]),
                _passthru_jsonb(s["info_asymmetry"]), _passthru_jsonb(s["annotations"]),
                s["tension_target"], s["emotion_target"], _passthru_jsonb(s["examples"]),
                s["abstraction_confidence"], f"lineage:{src_motif_id}", s["version"],
                s["embedding"], s["embedding_model"], s["embedding_dim"],
                s["embedded_summary_hash"], tainted, adopted_base, book_id, book_shared,
            )
        return _row_to_motif(row)

    # ────────────────────────────────────────────────────────────────────────
    # W1 EXTENSIONS (adopt/publish/catalog/quotas) — added post-F0-freeze. These
    # build ON the F0 primitives above WITHOUT re-keying the CRUD/clone signatures.
    # ────────────────────────────────────────────────────────────────────────

    # The PUBLIC catalog projection (B-3): an EXPLICIT allow-list, NEVER SELECT *
    # / model_dump — the three never-leak fields (embedding, examples, raw
    # source_ref) are structurally excluded so even a future careless refactor on
    # the public path cannot ship them. Mirrors catalog-service's catalogItem
    # struct. The full meso content (roles/beats/preconditions/effects) is also
    # excluded from the LIGHT catalog list (MD-1(a)) — it is one get_visible away.
    _CATALOG_COLS = (
        "id", "code", "original_language", "kind", "category", "name", "summary",
        "genre_tags", "tension_target", "emotion_target", "source",
        "abstraction_confidence", "judge_score", "version", "updated_at",
    )

    async def adopt(
        self, caller_id: UUID, src_motif_id: UUID,
        *, retag_genres: list[str] | None = None, book_id: UUID | None = None,
        book_shared: bool = False,
    ) -> tuple[Motif, bool]:
        """The HTTP/MCP adopt op = clone into the caller's OWN tier with a
        deterministic code-suffix on collision (F0's clone() raises on a code
        collision and leaves the rename policy to the caller — F0 §6-F). Returns
        (motif, created).

        Serialized per-OWNER (NOT a global lock / hash(NULL)) by a
        pg_advisory_xact_lock keyed on the caller id, so two users adopting the
        same source never block each other while one user double-submitting is
        ordered (the uniqueness it protects — uq_motif_user on
        (owner_user_id, code) — is per-owner, so the lock is too; H-7).

        `created` is True for a fresh adopt and False when an identical adopt of
        the SAME source already exists in the caller's tier (matched by the
        lineage source_ref → re-read, no duplicate; idempotent re-adopt, MD-6(a)).
        Raises LookupError if the source isn't visible to the caller."""
        async with self._pool.acquire() as c, c.transaction():
            # SHARED adopt serializes per-BOOK (concurrent grantees adopting the same source into
            # the same book must not each create a fork — the shared tier dedups per (book, code)).
            # Model-A / global adopt serializes per-OWNER (its uniqueness is per-owner).
            lock_key = f"motif-adopt-book:{book_id}" if book_shared else f"motif-adopt:{caller_id}"
            await c.execute("SELECT pg_advisory_xact_lock(hashtext($1))", lock_key)
            src = await c.fetchrow(
                f"SELECT code, original_language FROM motif WHERE id = $2 AND {_VISIBLE_PREDICATE}",
                caller_id, src_motif_id,
            )
            if src is None:
                raise LookupError("source motif not found or not accessible")
            base_code = src["code"]
            lineage = f"lineage:{src_motif_id}"
            # Idempotency (MD-6(a)): an existing adopt of the SAME source already in the SAME tier →
            # return it, no duplicate.
            #  • SHARED tier: keyed on (book_shared, book_id, source_ref) with NO owner filter — one
            #    shared clone of a source per book, whichever grantee adopts first wins.
            #  • Model-A / global: keyed on (owner, source_ref, book_id) — per-user, per-book.
            if book_shared:
                existing = await c.fetchrow(
                    f"SELECT {_SELECT_COLS} FROM motif "
                    "WHERE book_shared AND book_id = $1 AND source = 'adopted' AND source_ref = $2 "
                    "ORDER BY created_at LIMIT 1",
                    book_id, lineage,
                )
            else:
                existing = await c.fetchrow(
                    f"SELECT {_SELECT_COLS} FROM motif "
                    "WHERE owner_user_id = $1 AND source = 'adopted' AND source_ref = $2 "
                    "AND book_id IS NOT DISTINCT FROM $3 AND NOT book_shared "
                    "ORDER BY created_at LIMIT 1",
                    caller_id, lineage, book_id,
                )
            if existing is not None:
                return _row_to_motif(existing), False
            # Fresh adopt: try the source code, suffix deterministically on a code collision
            # (per-owner for the global/model-A tier, per-book for the shared tier). Bounded retry —
            # a degenerate tier saturated on every suffix raises out (router maps to 409).
            for attempt in range(0, 50):
                code = base_code if attempt == 0 else f"{base_code}-{attempt + 1}"
                row = await self._clone_with_code(
                    c, caller_id, src_motif_id, code, retag_genres,
                    book_id=book_id, book_shared=book_shared,
                )
                if row is not None:
                    return _row_to_motif(row), True
            raise asyncpg.UniqueViolationError(
                "no free code suffix for adopt within 50 attempts",
            )

    async def _clone_with_code(
        self, c: asyncpg.Connection, caller_id: UUID, src_motif_id: UUID,
        code: str, retag_genres: list[str] | None, *, book_id: UUID | None = None,
        book_shared: bool = False,
    ) -> asyncpg.Record | None:
        """One adopt INSERT...SELECT under an already-open connection/txn (the
        advisory lock is held by the caller). Column-enumerated copy (glossary
        adoptBookOntology precedent), single-target (user tier only — book tier
        dropped, H-7), the read predicate inlined so you may only adopt what you
        can see. Returns the new row, or None if the (owner, code)
        collides on uq_motif_user (caller retries with the next suffix). Any other
        UniqueViolationError propagates. Raises LookupError if the source vanished."""
        src = await c.fetchrow(
            f"SELECT {_SELECT_COLS}, embedding, embedded_summary_hash FROM motif "
            f"WHERE id = $2 AND {_VISIBLE_PREDICATE}",
            caller_id, src_motif_id,
        )
        if src is None:
            raise LookupError("source motif not found or not accessible")
        s = dict(src)
        genres = retag_genres if retag_genres is not None else list(s["genre_tags"])
        tainted = s["source"] == "imported" or bool(s["imported_derived"])
        try:
            # SAVEPOINT (nested c.transaction()) around the INSERT: a code
            # collision aborts only THIS attempt, not the outer adopt txn — so the
            # suffix-retry loop can issue the next INSERT instead of dying on
            # InFailedSQLTransactionError (asyncpg poisons the whole txn on error).
            async with c.transaction():
                return await c.fetchrow(
                    f"""
                    INSERT INTO motif
                      (owner_user_id, book_id, book_shared, code, original_language, visibility, kind, category, name,
                       summary, genre_tags, roles, beats, preconditions, effects,
                       info_asymmetry, annotations, tension_target, emotion_target,
                       examples, abstraction_confidence, source, imported_derived,
                       source_ref, source_version,
                       embedding, embedding_model, embedding_dim, embedded_summary_hash)
                    VALUES ($1,$26,$27,$2,$3,'private',$4,$5,$6,$7,$8,
                            $9::jsonb,$10::jsonb,$11::jsonb,$12::jsonb,$13::jsonb,$14::jsonb,
                            $15,$16,$17::jsonb,$18,'adopted',$25,$19,$20,
                            $21,$22,$23,$24)
                    RETURNING {_SELECT_COLS}
                    """,
                    caller_id, code, s["original_language"], s["kind"], s["category"],
                    s["name"], s["summary"], genres,
                    _passthru_jsonb(s["roles"]), _passthru_jsonb(s["beats"]),
                    _passthru_jsonb(s["preconditions"]), _passthru_jsonb(s["effects"]),
                    _passthru_jsonb(s["info_asymmetry"]), _passthru_jsonb(s["annotations"]),
                    s["tension_target"], s["emotion_target"], _passthru_jsonb(s["examples"]),
                    s["abstraction_confidence"], f"lineage:{src_motif_id}", s["version"],
                    s["embedding"], s["embedding_model"], s["embedding_dim"],
                    s["embedded_summary_hash"], tainted, book_id, book_shared,
                )
        except asyncpg.UniqueViolationError as exc:
            # A code collision in the target tier — global uq_motif_user, model-A
            # uq_motif_user_book, OR the shared uq_motif_book_shared — is the "retry with a
            # suffix" condition.
            if getattr(exc, "constraint_name", "") in (
                "uq_motif_user", "uq_motif_user_book", "uq_motif_book_shared",
            ):
                return None
            raise

    async def adopt_pattern_members(
        self, caller_id: UUID, src_motif_id: UUID, cloned_root_id: UUID,
    ) -> int:
        """MD-2(b): when a `pattern` is adopted, adopt its DIRECT `composed_of`
        members the caller doesn't already own, then re-point the composed_of
        edges at the caller's OWN copies (H-3 — a user edge may never touch a
        system/foreign motif; the F0 motif_link_guard enforces same-tier). One
        level deep (deep nesting is W10). Idempotent: a member already adopted (by
        lineage) is reused, and an edge that exists is skipped. Returns the count
        of member edges (re)created on the caller's copies."""
        async with self._pool.acquire() as c, c.transaction():
            await c.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                f"motif-adopt:{caller_id}",
            )
            members = await c.fetch(
                "SELECT to_motif_id, ord FROM motif_link "
                "WHERE from_motif_id = $1 AND kind = 'composed_of' ORDER BY ord",
                src_motif_id,
            )
            edges = 0
            for m in members:
                member_id = m["to_motif_id"]
                lineage = f"lineage:{member_id}"
                existing = await c.fetchrow(
                    "SELECT id FROM motif WHERE owner_user_id = $1 "
                    "AND source = 'adopted' AND source_ref = $2 LIMIT 1",
                    caller_id, lineage,
                )
                if existing is not None:
                    my_member_id = existing["id"]
                else:
                    src_code = await c.fetchval(
                        "SELECT code FROM motif WHERE id = $1", member_id,
                    )
                    if src_code is None:
                        continue
                    my_member_id = None
                    for attempt in range(0, 50):
                        code = src_code if attempt == 0 else f"{src_code}-{attempt + 1}"
                        row = await self._clone_with_code(
                            c, caller_id, member_id, code, None,
                        )
                        if row is not None:
                            my_member_id = row["id"]
                            break
                    if my_member_id is None:
                        continue
                # re-point the composed_of edge at the caller's OWN copies.
                await c.execute(
                    "INSERT INTO motif_link (from_motif_id, to_motif_id, kind, ord) "
                    "VALUES ($1,$2,'composed_of',$3) "
                    "ON CONFLICT (from_motif_id, to_motif_id, kind) DO NOTHING",
                    cloned_root_id, my_member_id, m["ord"],
                )
                edges += 1
            return edges

    async def list_public(
        self, *, genre: str | None = None, kind: str | None = None,
        q: str | None = None, display_language: str | None = None,
        sort: str = "recent", limit: int = 50, offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """The PUBLIC catalog (B-3). visibility='public' AND status='active' ONLY
        — `unlisted` is link-only (MD-3(a)), `private`/system/archived excluded.
        Returns (rows, total) where each row is the _CATALOG_COLS allow-list
        (NEVER the full motif), so embedding/examples/raw source_ref never reach a
        non-owner. Any authed caller may read it (no grant)."""
        where = ["visibility = 'public'", "status = 'active'"]
        params: list[Any] = []
        if genre is not None:
            params.append(genre)
            where.append(f"${len(params)} = ANY(genre_tags)")
        if kind is not None:
            params.append(kind)
            where.append(f"kind = ${len(params)}")
        if q:
            params.append(f"%{q}%")
            where.append(f"(name ILIKE ${len(params)} OR summary ILIKE ${len(params)})")
        where_sql = " AND ".join(where)
        order = "name" if sort == "name" else "updated_at DESC"
        cols = ", ".join(self._CATALOG_COLS)
        # count over the SAME filters (before limit/offset params are appended).
        count_q = f"SELECT count(*) FROM motif WHERE {where_sql}"
        count_params = list(params)
        params.append(max(0, min(limit, 100)))
        limit_pos = len(params)
        params.append(max(0, offset))
        offset_pos = len(params)
        list_q = (
            f"SELECT {cols} FROM motif WHERE {where_sql} "
            f"ORDER BY {order} LIMIT ${limit_pos} OFFSET ${offset_pos}"
        )
        async with self._pool.acquire() as c:
            rows = await c.fetch(list_q, *params)
            total = await c.fetchval(count_q, *count_params)
            out = [dict(r) for r in rows]
            # The catalog is a narrow allow-list of columns, not a Motif model, so it
            # gets the same treatment by hand: overlay only its three text fields.
            # Most rows here are user-published motifs, which are NEVER machine-
            # translated on the platform's dime — so falling back to the author's
            # original language is the expected outcome, not a degradation.
            want = normalize_display_language(display_language)
            ids = [r["id"] for r in out if r.get("original_language") != want] if want else []
            if ids:
                trs = {
                    t["motif_id"]: t
                    for t in await c.fetch(
                        "SELECT motif_id, name, summary, emotion_target FROM motif_translation "
                        "WHERE language_code = $1 AND motif_id = ANY($2::uuid[])",
                        want, ids,
                    )
                }
                for r in out:
                    if r.get("original_language") == want:
                        r["text_language"] = want
                        continue
                    t = trs.get(r["id"])
                    if t:
                        for f in ("name", "summary", "emotion_target"):
                            if t[f]:
                                r[f] = t[f]
                    r["text_language"] = want if t else r.get("original_language")
                    r["text_fallback"] = t is None
        return out, int(total or 0)

    async def count_shared_by_owner(self, owner_id: UUID) -> int:
        """The publish-ceiling input (B-4): motifs the user holds at a SHAREABLE
        visibility (public|unlisted), archived excluded (MD-4(a) — archiving frees
        quota). Shares the predicate the catalog 'mine published' view uses."""
        async with self._pool.acquire() as c:
            return int(await c.fetchval(
                "SELECT count(*) FROM motif WHERE owner_user_id = $1 "
                "AND visibility IN ('public','unlisted') AND status <> 'archived'",
                owner_id,
            ) or 0)

    async def count_adopted_by_owner(self, owner_id: UUID) -> int:
        """The adopt-ceiling input (B-4): ADOPTED motifs the user holds, archived
        excluded (MD-4(a))."""
        async with self._pool.acquire() as c:
            return int(await c.fetchval(
                "SELECT count(*) FROM motif WHERE owner_user_id = $1 "
                "AND source = 'adopted' AND status <> 'archived'",
                owner_id,
            ) or 0)


def _passthru_jsonb(value: Any) -> str | None:
    """A value read from a JSONB column is either a json string (asyncpg) or already
    a list/dict — normalize to a json string for the re-INSERT ::jsonb (NULL stays
    NULL for nullable columns like info_asymmetry)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value)
