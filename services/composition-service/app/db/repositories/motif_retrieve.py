"""motif retrieval — the planner's select-candidates core (R1.4 / W3 implements).

The signature is FROZEN in F0 so W2 (planner) builds against it concurrently and
mocks retrieve() until W3 lands. The impl (W3):

  1. SQL PRE-FILTER (audit data-R1) — bound the candidate set in SQL BEFORE loading any
     vector: status='active' AND language=$lang AND (genre_tags && $genres) AND the
     R1.1 read predicate (system | public | owned). Cheap pre-rank (own-tier, popularity,
     quality, recency) + a HARD `LIMIT motif_candidate_ceiling` so the brute-force pass
     is O(ceiling), never O(table) even as the library grows.
  2. BRUTE-FORCE COSINE (the reference_source precedent, now over a BOUNDED set) — embed
     the chapter-intent query with the ONE platform model (engine/motif_embed), cosine
     each candidate's vector, drop below `motif_min_score`.
  3. match_reason breakdown {tension, genre, precond, cosine} (+ a `degraded` marker).

ONE platform embedding model for ALL vectors (B-1) → every cosine is same-space.

RECONCILE D4 (NULL-embedding tolerance): seeds insert embedding=NULL and the platform
embed may be down at boot, so a candidate row may have a NULL embedding. W3 SKIPs such a
row (never 0.0-rank it as a real miss) and QUEUES it for a lazy platform back-fill keyed
on embedded_summary_hash. The queue is drained by the back-fill worker / next write path.

R4 (degrade, don't invent): if the query vector can't be produced (provider outage),
retrieve() degrades to genre+tension ordering over the SAME pre-filtered set — never
500, never []. The candidates carry match_reason.degraded=True + cosine=0.0.
"""

from __future__ import annotations

import json
import math
from typing import Any
from uuid import UUID

import asyncpg

from app.clients.embedding_client import EmbeddingError
from app.config import settings
from app.db.models import Motif, MotifCandidate
from app.engine.motif_embed import EmbedConfigError, embed_query

# The retrieve projection — same columns as MotifRepo._SELECT_COLS PLUS `embedding`
# (loaded ONLY for the bounded candidate set; the vector never leaves this repo — the
# returned Motif omits it, the reference_source rule).
_RETRIEVE_COLS = """
  id, owner_user_id, code, language, visibility, kind, category, name, summary,
  genre_tags, roles, beats, preconditions, effects, info_asymmetry, annotations,
  tension_target, emotion_target, examples, abstraction_confidence, source,
  imported_derived, source_ref, source_version, embedding_model, embedding_dim,
  judge_score, mining_support, status, version, created_at, updated_at,
  embedded_summary_hash, embedding
"""
# JSONB columns asyncpg returns as str → json.loads on read (mirrors motif_repo).
_JSONB_FIELDS = (
    "roles", "beats", "preconditions", "effects", "info_asymmetry",
    "annotations", "examples",
)
# THE read predicate (R1.1) — system | public | owned-by-caller. BYTE-IDENTICAL to
# MotifRepo's _VISIBLE_PREDICATE (one predicate, two call sites → a retrieved candidate
# is provably also get_visible by id; no ghost, no IDOR via the rank path; audit B-2).
_VISIBLE_PREDICATE = "(owner_user_id IS NULL OR visibility = 'public' OR owner_user_id = $1)"

# Map a motif tension_target (SMALLINT 1..5) to the EXISTING chapter 0..100 scale
# (plan_high_tension_threshold=70). W3 only REPORTS this band-fit in match_reason; W2
# owns the authoritative tension reconcile + the bind decision (MD-6).
_TENSION_BAND_MID = {1: 10.0, 2: 30.0, 3: 50.0, 4: 70.0, 5: 90.0}


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine of two equal-length vectors; 0.0 for empty/zero/mismatched-length
    (a degenerate row never out-ranks a real hit). Copy of references.py:_cosine —
    kept local so motif_retrieve has no cross-repo coupling (MD-4). If a 3rd cosine
    site appears, F0 promotes this to db/repositories/_vec.py."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _build_query_text(beat_role: str | None, prev_effects: list[str] | None) -> str:
    """Join the beat intent + the prior-motif effects into one short chapter-intent
    string so the query vector reflects BOTH what this beat is for and the state that
    precedes it. Mirrors the references router's auto-query seed; drops empties."""
    parts: list[str] = [beat_role or ""]
    parts.extend(prev_effects or [])
    return " ".join(p for p in parts if p).strip()


def _genre_overlap(motif_genres: list[str] | None, query_genres: list[str] | None) -> float:
    """|motif ∩ query| / |query| — overlap strength as a fraction of the BOOK's genres
    (so a motif matching all the book's genres scores 1.0). 0.0 when the book has no
    genres (no signal) or they're disjoint."""
    q = set(query_genres or [])
    if not q:
        return 0.0
    m = set(motif_genres or [])
    return len(m & q) / len(q)


def _tension_band(motif_tension_target: int | None, chapter_tension: int | None) -> float:
    """Closeness of the motif's 1..5 tension band (mapped to a 0..100 midpoint) to the
    chapter's existing 0..100 tension: 1 - |band_mid - tension| / 100. Neutral 0.5 when
    either side is unknown (no signal either way)."""
    if motif_tension_target is None or chapter_tension is None:
        return 0.5
    mid = _TENSION_BAND_MID.get(int(motif_tension_target), 50.0)
    return 1.0 - abs(mid - float(chapter_tension)) / 100.0


def _precond_overlap(preconditions: list[dict[str, Any]] | None,
                     prev_effects: list[str] | None) -> float:
    """Jaccard token-overlap of the motif's precondition texts against the previous
    motif's effects (a soft "does the prior state set up this motif" signal). 0.0 when
    there are no prev_effects (R1.3-6: precond is 0.0 when prev_effects is None) or no
    preconditions."""
    if not prev_effects or not preconditions:
        return 0.0
    pre_tokens: set[str] = set()
    for p in preconditions:
        text = p.get("text", "") if isinstance(p, dict) else str(p)
        pre_tokens |= _tokens(text)
    eff_tokens: set[str] = set()
    for e in prev_effects:
        eff_tokens |= _tokens(e)
    if not pre_tokens or not eff_tokens:
        return 0.0
    return len(pre_tokens & eff_tokens) / len(pre_tokens | eff_tokens)


def _tokens(text: str) -> set[str]:
    return {t for t in text.lower().split() if t}


def _row_to_motif(row: dict[str, Any] | asyncpg.Record) -> Motif:
    """Build a Motif WITHOUT the embedding/hash (server-side only). Mirrors
    motif_repo._row_to_motif but drops the retrieve-only columns from the projection."""
    data = dict(row)
    data.pop("embedding", None)
    data.pop("embedded_summary_hash", None)
    for f in _JSONB_FIELDS:
        v = data.get(f)
        if isinstance(v, str):
            data[f] = json.loads(v)
    return Motif.model_validate(data)


class MotifRetriever:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        # RECONCILE D4 — rows seen with a NULL embedding during a retrieve are queued
        # here for a lazy platform back-fill. Drained by the back-fill worker (or
        # inspected in tests). Keyed by id so repeats collapse.
        self._backfill: dict[UUID, dict[str, Any]] = {}

    def drain_backfill_queue(self) -> list[dict[str, Any]]:
        """Return + clear the back-fill queue (NULL-vector rows seen since the last
        drain). Each entry carries {id, code, embedded_summary_hash} — enough for the
        worker to re-embed via engine/motif_embed without re-reading the row."""
        items = list(self._backfill.values())
        self._backfill.clear()
        return items

    def _queue_backfill(self, row: dict[str, Any] | asyncpg.Record) -> None:
        self._backfill[row["id"]] = {
            "id": row["id"],
            "code": row["code"],
            "embedded_summary_hash": row["embedded_summary_hash"],
        }

    async def retrieve(
        self, caller_id: UUID, *, book_id: UUID, project_id: UUID,
        genre_tags: list[str], language: str,
        beat_role: str | None, tension: int | None,
        prev_effects: list[str] | None = None, limit: int = 10,
    ) -> list[MotifCandidate]:
        """Tier-merged, SQL-pre-filtered, cosine-ranked motif candidates for a chapter's
        beat. Returns up to `limit` MotifCandidate (motif + score + match_reason=
        {tension,genre,precond,cosine[,degraded]}), highest score first. W3 impl."""
        min_score = settings.motif_min_score
        ceiling = settings.motif_candidate_ceiling

        # (1) SQL pre-filter → BOUNDED candidate rows (with vectors). data-R1.
        rows = await self._fetch_candidates(caller_id, genre_tags, language, ceiling)
        if not rows:
            return []  # no in-genre/in-language motif → W2 falls back to invent

        # (2) Query vector (the chapter-intent embedding). Embed-DOWN → degrade (R4).
        qtext = _build_query_text(beat_role, prev_effects)
        qvec: list[float] | None = None
        if qtext:
            try:
                qvec = await embed_query(qtext)
            except (EmbeddingError, EmbedConfigError):
                # Degrade, do NOT 500/[]. EmbedConfigError (unset platform model) ALSO
                # degrades the READ path — a planner read must never hard-fail on a
                # config gap; the WRITE path (engine/motif_embed) is where the config gap
                # fails closed.
                qvec = None

        # (3) Score every BOUNDED candidate; build match_reason.
        scored: list[tuple[float, str, MotifCandidate]] = []
        for r in rows:
            genre_s = _genre_overlap(list(r["genre_tags"]), genre_tags)
            tension_s = _tension_band(r["tension_target"], tension)
            precond_s = _precond_overlap(_loads(r["preconditions"]), prev_effects)
            vec = r["embedding"]
            if vec is None:
                # RECONCILE D4 — NULL vector: queue a lazy back-fill, NEVER 0.0-rank it
                # against scored rows. In the cosine path SKIP it; in the degrade path
                # (no query vector) it can still rank on genre+tension.
                self._queue_backfill(r)
                if qvec is not None:
                    continue

            if qvec is not None:
                cos = _cosine(qvec, list(vec))
                rank = cos
                degraded = False
            else:
                cos = 0.0
                rank = 0.6 * genre_s + 0.4 * tension_s  # DEGRADE: genre+tension order (R4)
                degraded = True

            if (qvec is not None) and rank < min_score:
                continue  # min_score floor → no force-bind of an unrelated motif

            motif = _row_to_motif(r)  # WITHOUT embedding (server-side only)
            reason: dict[str, Any] = {
                "tension": tension_s, "genre": genre_s,
                "precond": precond_s, "cosine": cos,
            }
            if degraded:
                reason["degraded"] = True
            scored.append((rank, motif.code, MotifCandidate(
                motif=motif, score=rank, match_reason=reason,
            )))

        # (4) Rank desc + deterministic tie-break (reproducible top-1 for W2's eval):
        # rank DESC, then mining_support DESC, judge_score DESC, code ASC.
        scored.sort(key=lambda t: (
            -t[0],
            -(t[2].motif.mining_support or 0),
            -float(t[2].motif.judge_score or 0.0),
            t[1],
        ))
        return [c for _rank, _code, c in scored[: max(0, limit)]]

    async def _fetch_candidates(
        self, caller_id: UUID, genre_tags: list[str], language: str, ceiling: int,
    ) -> list[asyncpg.Record]:
        """The BOUNDING query (data-R1). Loads `embedding` for the bounded set ONLY.
        $1 caller_id · $2 language · $3 ceiling · $4 genres (only when non-empty).

        A genre-less book ([]) OMITS the `&&` clause (MD-2) — an empty array && is always
        false and would zero out retrieval; a language+tier+ceiling bound still applies."""
        params: list[Any] = [caller_id, language, max(0, ceiling)]
        genre_clause = ""
        if genre_tags:
            params.append(list(genre_tags))
            genre_clause = f"  AND genre_tags && ${len(params)}::text[]\n"
        sql = f"""
        SELECT {_RETRIEVE_COLS}
        FROM motif
        WHERE status = 'active'
          AND language = $2
{genre_clause}          AND {_VISIBLE_PREDICATE}
        ORDER BY
          (owner_user_id = $1) DESC NULLS LAST,
          mining_support DESC NULLS LAST,
          judge_score DESC NULLS LAST,
          updated_at DESC
        LIMIT $3
        """
        async with self._pool.acquire() as c:
            return await c.fetch(sql, *params)


def _loads(value: Any) -> list[dict[str, Any]]:
    """A JSONB column read by asyncpg is a json string (or already a list)."""
    if isinstance(value, str):
        return json.loads(value)
    return value or []
