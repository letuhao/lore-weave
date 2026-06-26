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

import json
from typing import Any
from uuid import UUID

import asyncpg

from app.db.models import Motif, MotifCreateArgs, MotifPatchArgs
from app.db.repositories import VersionMismatchError

# vector + hash deliberately excluded — projection is the model shape only.
_SELECT_COLS = """
  id, owner_user_id, code, language, visibility, kind, category, name, summary,
  genre_tags, roles, beats, preconditions, effects, info_asymmetry, annotations,
  tension_target, emotion_target, examples, abstraction_confidence, source,
  imported_derived, source_ref, source_version, embedding_model, embedding_dim,
  judge_score, mining_support, status, version, created_at, updated_at
"""
# JSONB columns json.loads'd on read (asyncpg returns them as str).
_JSONB_FIELDS = (
    "roles", "beats", "preconditions", "effects", "info_asymmetry",
    "annotations", "examples",
)
# The read predicate (R1.1) — system | public | owned-by-caller. $1 = caller_id.
_VISIBLE_PREDICATE = "(owner_user_id IS NULL OR visibility = 'public' OR owner_user_id = $1)"


def _row_to_motif(row: asyncpg.Record) -> Motif:
    data = dict(row)
    for f in _JSONB_FIELDS:
        v = data.get(f)
        if isinstance(v, str):
            data[f] = json.loads(v)
    return Motif.model_validate(data)


def _jsonb(value: Any) -> str:
    """Dump a JSONB write value (list/dict/pydantic) to a json string for ::jsonb."""
    return json.dumps(value)


def _dump_models(items: list[Any]) -> list[dict[str, Any]]:
    """[MotifRole|MotifBeat|dict] → [dict] for JSONB serialization."""
    out: list[dict[str, Any]] = []
    for it in items:
        out.append(it.model_dump(mode="json") if hasattr(it, "model_dump") else it)
    return out


class MotifRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, user_id: UUID, args: MotifCreateArgs) -> Motif:
        """Create a USER-tier motif. owner_user_id is STAMPED = user_id (never an
        arg → a both-NULL/system row is impossible from this path; the DB CHECK is
        the backstop). embedding starts NULL (W3 fills it). UNIQUE(owner,code,lang)
        violation → asyncpg.UniqueViolationError (router maps to 409)."""
        info = args.info_asymmetry.model_dump(mode="json") if args.info_asymmetry else None
        query = f"""
        INSERT INTO motif
          (owner_user_id, code, language, visibility, kind, category, name, summary,
           genre_tags, roles, beats, preconditions, effects, info_asymmetry,
           annotations, tension_target, emotion_target, examples, source)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,
                $10::jsonb,$11::jsonb,$12::jsonb,$13::jsonb,$14::jsonb,$15::jsonb,
                $16,$17,$18::jsonb,'authored')
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query,
                user_id, args.code, args.language, args.visibility, args.kind,
                args.category, args.name, args.summary, args.genre_tags,
                _jsonb(_dump_models(args.roles)), _jsonb(_dump_models(args.beats)),
                _jsonb(args.preconditions), _jsonb(args.effects),
                _jsonb(info) if info is not None else None,
                _jsonb(args.annotations), args.tension_target, args.emotion_target,
                _jsonb(args.examples),
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

    async def patch(
        self, caller_id: UUID, motif_id: UUID, args: MotifPatchArgs, *, expected_version: int,
    ) -> Motif | None:
        """Optimistic-lock edit, OWNER-only (WHERE owner_user_id = caller_id — a
        system or foreign motif is never patchable here). Bumps version, sets
        updated_at. On a summary change, embedded_summary_hash is cleared so W3's
        re-embed fires. Returns None if the row isn't the caller's (router → H13);
        raises VersionMismatchError(current) on a stale expected_version.

        (Return is Motif|None to match the canon_rules/works house convention; the
        frozen CONTRACT is the parameter names + the version-mismatch raise.)"""
        sets: list[str] = []
        params: list[Any] = [caller_id, motif_id]
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
        sets.append("version = version + 1")
        sets.append("updated_at = now()")
        params.append(expected_version)
        query = f"""
        UPDATE motif SET {", ".join(sets)}
        WHERE owner_user_id = $1 AND id = $2 AND version = ${len(params)}
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, *params)
            if row is not None:
                return _row_to_motif(row)
            # distinguish not-owned/not-found (→ None) from a stale version (→ raise).
            current = await c.fetchrow(
                f"SELECT {_SELECT_COLS} FROM motif WHERE owner_user_id = $1 AND id = $2",
                caller_id, motif_id,
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

    async def list_for_caller(
        self, caller_id: UUID, *, scope: str = "all", genre: str | None = None,
        kind: str | None = None, status: str | None = "active", q: str | None = None,
        language: str | None = None, limit: int = 100,
    ) -> list[Motif]:
        """Tier-merged list under the read predicate (system | public | owner).
        `scope` narrows the predicate: 'system' (owner NULL), 'user' (owner=caller),
        'public' (visibility=public), 'all' (the full predicate). genre filters the
        GIN array; q is an ILIKE on name/summary; language/status/kind are exact.
        System rows sort first (NULLS FIRST), then name."""
        params: list[Any] = [caller_id]
        if scope == "system":
            where = ["owner_user_id IS NULL"]
        elif scope == "user":
            where = ["owner_user_id = $1"]
        elif scope == "public":
            where = ["visibility = 'public'"]
        else:
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
        if language is not None:
            params.append(language)
            where.append(f"language = ${len(params)}")
        if q:
            params.append(f"%{q}%")
            where.append(f"(name ILIKE ${len(params)} OR summary ILIKE ${len(params)})")
        params.append(max(0, limit))
        query = f"""
        SELECT {_SELECT_COLS} FROM motif
        WHERE {" AND ".join(where)}
        ORDER BY owner_user_id NULLS FIRST, name
        LIMIT ${len(params)}
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, *params)
        return [_row_to_motif(r) for r in rows]

    async def clone(
        self, caller_id: UUID, src_motif_id: UUID, *, target_owner: UUID,
        retag_genres: list[str] | None = None,
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
            row = await c.fetchrow(
                f"""
                INSERT INTO motif
                  (owner_user_id, code, language, visibility, kind, category, name,
                   summary, genre_tags, roles, beats, preconditions, effects,
                   info_asymmetry, annotations, tension_target, emotion_target,
                   examples, abstraction_confidence, source, imported_derived,
                   source_ref, source_version,
                   embedding, embedding_model, embedding_dim, embedded_summary_hash)
                VALUES ($1,$2,$3,'private',$4,$5,$6,$7,$8,
                        $9::jsonb,$10::jsonb,$11::jsonb,$12::jsonb,$13::jsonb,$14::jsonb,
                        $15,$16,$17::jsonb,$18,'adopted',$25,$19,$20,
                        $21,$22,$23,$24)
                RETURNING {_SELECT_COLS}
                """,
                target_owner, s["code"], s["language"], s["kind"], s["category"],
                s["name"], s["summary"], genres,
                _passthru_jsonb(s["roles"]), _passthru_jsonb(s["beats"]),
                _passthru_jsonb(s["preconditions"]), _passthru_jsonb(s["effects"]),
                _passthru_jsonb(s["info_asymmetry"]), _passthru_jsonb(s["annotations"]),
                s["tension_target"], s["emotion_target"], _passthru_jsonb(s["examples"]),
                s["abstraction_confidence"], f"lineage:{src_motif_id}", s["version"],
                s["embedding"], s["embedding_model"], s["embedding_dim"],
                s["embedded_summary_hash"], tainted,
            )
        return _row_to_motif(row)


def _passthru_jsonb(value: Any) -> str | None:
    """A value read from a JSONB column is either a json string (asyncpg) or already
    a list/dict — normalize to a json string for the re-INSERT ::jsonb (NULL stays
    NULL for nullable columns like info_asymmetry)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value)
