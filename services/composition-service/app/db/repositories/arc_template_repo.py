"""arc_template repository — W10 CRUD + the clone primitive (= adopt), mirroring
motif_repo verbatim (same 2-tier tenancy, same read predicate, same optimistic lock,
same catalog allow-list discipline).

TENANCY (the kinds-bug fix + R1.1): an arc_template is system (owner_user_id NULL,
seed/migrate-only) or user-owned (owner set). The read predicate (R1.1) lives in
get_visible/list_for_caller SELECTs — an arc is visible IFF
  owner_user_id IS NULL (system) OR visibility = 'public' OR owner_user_id = caller.
The user-write path (create) SERVER-STAMPS owner_user_id = caller and can never write
a both-NULL (system) row (the DB arc_template_user_owned CHECK is the backstop). patch/
archive are OWNER-only (a system or foreign row never matches → the router's uniform
H13 404, no existence oracle).

CONDITIONAL-PARAM BINDING (R-NODE-P1 lesson, copied from motif_repo.list_for_caller):
caller_id is bound as $1 ONLY when the scope's SQL references it. A 'system'/'public'
scope filters on owner_user_id/visibility alone — binding an UNUSED $1 makes asyncpg
raise IndeterminateDatatypeError (the scope=system 500). Do NOT bind it unless used.

EMBEDDING: the `embedding` column is NEVER projected into a returned ArcTemplate
(stays server-side, motif precedent); W9/embed fills it out of band. clone() COPIES the
source vector (same platform space → cross-tier cosine stays correct).

The arc_template TABLE is F0-frozen (app/db/migrate.py) — this repo consumes it; it adds
NO migration.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from app.db.models import ArcTemplate, ArcTemplateCreateArgs, ArcTemplatePatchArgs
from app.db.repositories import VersionMismatchError

# embedding + raw embed cols deliberately excluded — projection is the model shape only.
_SELECT_COLS = """
  id, owner_user_id, code, language, visibility, name, summary, genre_tags,
  chapter_span, threads, layout, pacing, arc_roster, source, imported_derived,
  source_ref, source_version, embedding_model, embedding_dim, status, version,
  created_at, updated_at
"""
# JSONB columns json.loads'd on read (asyncpg returns them as str).
_JSONB_FIELDS = ("threads", "layout", "pacing", "arc_roster")
# The read predicate (R1.1) — system | public | owned-by-caller. $1 = caller_id.
_VISIBLE_PREDICATE = "(owner_user_id IS NULL OR visibility = 'public' OR owner_user_id = $1)"


def _row_to_arc(row: asyncpg.Record) -> ArcTemplate:
    data = dict(row)
    for f in _JSONB_FIELDS:
        v = data.get(f)
        if isinstance(v, str):
            data[f] = json.loads(v)
    return ArcTemplate.model_validate(data)


def _jsonb(value: Any) -> str:
    """Dump a JSONB write value (list/dict/pydantic) to a json string for ::jsonb."""
    return json.dumps(value)


def _dump_models(items: list[Any]) -> list[dict[str, Any]]:
    """[ArcThread|ArcPlacement|ArcRosterEntry|dict] → [dict] for JSONB serialization."""
    out: list[dict[str, Any]] = []
    for it in items:
        out.append(it.model_dump(mode="json") if hasattr(it, "model_dump") else it)
    return out


def _passthru_jsonb(value: Any) -> str | None:
    """A value read from a JSONB column is either a json string (asyncpg) or already a
    list/dict — normalize to a json string for the re-INSERT ::jsonb."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value)


class ArcTemplateRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self, user_id: UUID, args: ArcTemplateCreateArgs,
        *, source: str = "authored", status: str = "active",
        imported_derived: bool = False,
    ) -> ArcTemplate:
        """Create a USER-tier arc_template. owner_user_id is STAMPED = user_id (never an
        arg → a both-NULL/system row is impossible from this path; the DB CHECK is the
        backstop). embedding starts NULL (W9 fills it). UNIQUE(owner,code,lang) violation
        → asyncpg.UniqueViolationError (router maps to 409).

        `source`/`status` default to the authored-active path (every existing caller is
        unchanged). W9's deconstruct passes source='imported', status='draft' so the
        proposed arc lands as a reviewable draft (§12.3); the arc_template.source CHECK
        allows ('authored','mined','imported')."""
        query = f"""
        INSERT INTO arc_template
          (owner_user_id, code, language, visibility, name, summary, genre_tags,
           chapter_span, threads, layout, pacing, arc_roster, source, status,
           imported_derived)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,
                $9::jsonb,$10::jsonb,$11::jsonb,$12::jsonb,$13,$14,$15)
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query,
                user_id, args.code, args.language, args.visibility, args.name,
                args.summary, args.genre_tags, args.chapter_span,
                _jsonb(_dump_models(args.threads)), _jsonb(_dump_models(args.layout)),
                _jsonb(args.pacing), _jsonb(_dump_models(args.arc_roster)), source, status,
                imported_derived,
            )
        return _row_to_arc(row)

    async def get_visible(self, caller_id: UUID, arc_id: UUID) -> ArcTemplate | None:
        """THE read predicate (R1.1): returns the arc IFF system | public | owned by
        caller. A foreign PRIVATE arc returns None (IDOR-safe — the router maps None →
        the H13 uniform 'not found or not accessible', no existence oracle)."""
        query = f"""
        SELECT {_SELECT_COLS} FROM arc_template
        WHERE id = $2 AND {_VISIBLE_PREDICATE}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, caller_id, arc_id)
        return _row_to_arc(row) if row is not None else None

    async def patch(
        self, caller_id: UUID, arc_id: UUID, args: ArcTemplatePatchArgs,
        *, expected_version: int | None,
    ) -> ArcTemplate | None:
        """Optimistic-lock edit, OWNER-only (WHERE owner_user_id = caller_id — a system
        or foreign arc is never patchable here). Bumps version, sets updated_at. On a
        summary change, embedded_summary_hash is cleared so the re-embed fires. Returns
        None if the row isn't the caller's (router → H13); raises VersionMismatchError(
        current) on a stale expected_version (None skips the version guard)."""
        sets: list[str] = []
        params: list[Any] = [caller_id, arc_id]
        data = args.model_dump(exclude_unset=True)
        for field, value in data.items():
            if field in ("threads", "layout", "arc_roster"):
                value = _dump_models(getattr(args, field) or [])
            if field in _JSONB_FIELDS:
                params.append(_jsonb(value) if value is not None else None)
                sets.append(f"{field} = ${len(params)}::jsonb")
            else:
                params.append(value)
                sets.append(f"{field} = ${len(params)}")
        if "summary" in data:
            sets.append("embedded_summary_hash = NULL")  # re-embed on next retrieve
        sets.append("version = version + 1")
        sets.append("updated_at = now()")
        version_clause = ""
        if expected_version is not None:
            params.append(expected_version)
            version_clause = f" AND version = ${len(params)}"
        query = f"""
        UPDATE arc_template SET {", ".join(sets)}
        WHERE owner_user_id = $1 AND id = $2{version_clause}
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, *params)
            if row is not None:
                return _row_to_arc(row)
            # distinguish not-owned/not-found (→ None) from a stale version (→ raise).
            current = await c.fetchrow(
                f"SELECT {_SELECT_COLS} FROM arc_template "
                "WHERE owner_user_id = $1 AND id = $2",
                caller_id, arc_id,
            )
        if current is None:
            return None
        if expected_version is None:
            # no version guard but still no row updated — treat as not-found (defensive).
            return None
        raise VersionMismatchError(_row_to_arc(current))

    async def archive(self, caller_id: UUID, arc_id: UUID) -> None:
        """Soft-archive (status='archived'), OWNER-only. Idempotent. A foreign/missing
        id is a no-op the router maps to H13 (no oracle)."""
        async with self._pool.acquire() as c:
            await c.execute(
                "UPDATE arc_template SET status = 'archived', updated_at = now() "
                "WHERE owner_user_id = $1 AND id = $2 AND status <> 'archived'",
                caller_id, arc_id,
            )

    async def list_for_caller(
        self, caller_id: UUID, *, scope: str = "all", genre: str | None = None,
        status: str | None = "active", q: str | None = None,
        language: str | None = None, limit: int = 100,
    ) -> list[ArcTemplate]:
        """Tier-merged list under the read predicate (system | public | owner). `scope`
        narrows: 'system' (owner NULL), 'user' (owner=caller), 'public' (visibility=
        public), 'all' (the full predicate). genre filters the GIN array; q is an ILIKE
        on name/summary; language/status are exact. System rows sort first.

        caller_id is bound as $1 ONLY when the scope's SQL references it (R-NODE-P1: a
        'system'/'public' scope binding an UNUSED $1 makes asyncpg raise
        IndeterminateDatatypeError — the scope=system 500). Copied from motif_repo."""
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
        if status is not None:
            params.append(status)
            where.append(f"status = ${len(params)}")
        if language is not None:
            params.append(language)
            where.append(f"language = ${len(params)}")
        if q:
            params.append(f"%{q}%")
            where.append(f"(name ILIKE ${len(params)} OR summary ILIKE ${len(params)})")
        params.append(max(0, limit))
        query = f"""
        SELECT {_SELECT_COLS} FROM arc_template
        WHERE {" AND ".join(where)}
        ORDER BY owner_user_id NULLS FIRST, name
        LIMIT ${len(params)}
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, *params)
        return [_row_to_arc(r) for r in rows]

    async def clone(
        self, caller_id: UUID, src_arc_id: UUID, *, target_owner: UUID,
        retag_genres: list[str] | None = None,
    ) -> ArcTemplate:
        """The clone primitive (= adopt = clone-to-customize = cross-genre retag).
        Reads the SOURCE under the read predicate (so you may only clone what you can
        see — public/system/own), then INSERTs a NEW private row owned by target_owner:
        id/version reset, source='adopted'? — NOTE the arc_template.source CHECK only
        allows ('authored','mined','imported'), so an adopt KEEPS the source value and
        records lineage via source_ref='lineage:'||src.id + source_version=src.version
        (an imported lineage stays 'imported' so the copyright split holds). embedding is
        COPIED (same platform space). Raises UniqueViolationError on a code collision in
        target's tier; LookupError if the source isn't visible to the caller."""
        async with self._pool.acquire() as c:
            src = await c.fetchrow(
                f"""
                SELECT {_SELECT_COLS}, embedding, embedded_summary_hash
                FROM arc_template
                WHERE id = $2 AND {_VISIBLE_PREDICATE}
                """,
                caller_id, src_arc_id,
            )
            if src is None:
                raise LookupError("source arc_template not found or not accessible")
            s = dict(src)
            genres = retag_genres if retag_genres is not None else list(s["genre_tags"])
            # B-3 taint propagation: an adopt of an imported (or already-tainted) arc
            # stays tainted so the publish-strip trigger fires on the clone too;
            # adopt-of-authored stays false (the strip isn't over-broad).
            tainted = bool(s["source"] == "imported" or s["imported_derived"])
            row = await c.fetchrow(
                f"""
                INSERT INTO arc_template
                  (owner_user_id, code, language, visibility, name, summary, genre_tags,
                   chapter_span, threads, layout, pacing, arc_roster, source, source_ref,
                   source_version, embedding, embedding_model, embedding_dim,
                   embedded_summary_hash, imported_derived)
                VALUES ($1,$2,$3,'private',$4,$5,$6,$7,
                        $8::jsonb,$9::jsonb,$10::jsonb,$11::jsonb,$12,$13,$14,
                        $15,$16,$17,$18,$19)
                RETURNING {_SELECT_COLS}
                """,
                target_owner, s["code"], s["language"], s["name"], s["summary"], genres,
                s["chapter_span"], _passthru_jsonb(s["threads"]),
                _passthru_jsonb(s["layout"]), _passthru_jsonb(s["pacing"]),
                _passthru_jsonb(s["arc_roster"]), s["source"], f"lineage:{src_arc_id}",
                s["version"], s["embedding"], s["embedding_model"], s["embedding_dim"],
                s["embedded_summary_hash"], tainted,
            )
        return _row_to_arc(row)

    # The PUBLIC catalog projection (B-3 analogue): an EXPLICIT allow-list, NEVER
    # SELECT */model_dump — embedding + raw source_ref + the heavy layout/arc_roster
    # JSONB are structurally excluded from the LIGHT catalog list (one get_visible
    # away). Mirrors motif_repo._CATALOG_COLS.
    _CATALOG_COLS = (
        "id", "code", "language", "name", "summary", "genre_tags", "chapter_span",
        "threads", "source", "version", "updated_at",
    )

    async def list_public(
        self, *, genre: str | None = None, q: str | None = None,
        language: str | None = None, sort: str = "recent",
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """The PUBLIC catalog (B-3 analogue). visibility='public' AND status='active'
        ONLY. Returns (rows, total) where each row is the _CATALOG_COLS allow-list
        (NEVER the full arc), so embedding / raw source_ref never reach a non-owner.
        `threads` is included (the at-a-glance track skeleton) but `layout`/`arc_roster`
        (the full placement detail) are NOT — those are a get_visible away."""
        where = ["visibility = 'public'", "status = 'active'"]
        params: list[Any] = []
        if genre is not None:
            params.append(genre)
            where.append(f"${len(params)} = ANY(genre_tags)")
        if language is not None:
            params.append(language)
            where.append(f"language = ${len(params)}")
        if q:
            params.append(f"%{q}%")
            where.append(f"(name ILIKE ${len(params)} OR summary ILIKE ${len(params)})")
        where_sql = " AND ".join(where)
        order = "name" if sort == "name" else "updated_at DESC"
        cols = ", ".join(self._CATALOG_COLS)
        count_q = f"SELECT count(*) FROM arc_template WHERE {where_sql}"
        count_params = list(params)
        params.append(max(0, min(limit, 100)))
        limit_pos = len(params)
        params.append(max(0, offset))
        offset_pos = len(params)
        list_q = (
            f"SELECT {cols} FROM arc_template WHERE {where_sql} "
            f"ORDER BY {order} LIMIT ${limit_pos} OFFSET ${offset_pos}"
        )
        async with self._pool.acquire() as c:
            rows = await c.fetch(list_q, *params)
            total = await c.fetchval(count_q, *count_params)
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            # threads is a JSONB column → asyncpg may return it as a json string.
            t = d.get("threads")
            if isinstance(t, str):
                d["threads"] = json.loads(t)
            out.append(d)
        return out, int(total or 0)

    async def count_shared_by_owner(self, owner_id: UUID) -> int:
        """The publish-ceiling input (B-4 analogue): arc_templates the user holds at a
        SHAREABLE visibility (public|unlisted), archived excluded (archiving frees
        quota)."""
        async with self._pool.acquire() as c:
            return int(await c.fetchval(
                "SELECT count(*) FROM arc_template WHERE owner_user_id = $1 "
                "AND visibility IN ('public','unlisted') AND status <> 'archived'",
                owner_id,
            ) or 0)
