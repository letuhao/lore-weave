"""``GamegenS2Repo`` — the interrogation tier's writes, shaped so the invariants
cannot be written around.

Doc 39 §3.3/§3.4. Three tables: ``gamegen_corpus_seal`` (S0),
``gamegen_decision`` (the approval unit) and ``gamegen_answer`` (the evidence).

Two things about this repository are deliberate and worth reading before
extending it.

**It never accepts an ``answer_hash``.** :meth:`record_answer` takes an
:class:`AnswerEvidence` and computes the hash itself. A caller-supplied hash is a
hash of whatever the caller *says* the answer is, and S5's recompute-and-compare
would then be comparing the row against a number derived from the same source
that wrote the row — the model marking its own homework, which is `PGN-A14`'s
objection one tier down.

**Approval is a separate call from creation, and it is the only writer of
``approved_by``.** ``review_status`` is not a settable field on
:meth:`propose_decision`; a decision is born ``proposed``. Without that, "create
it already approved" is a one-argument path around T3.

Scoping (CLAUDE.md › User Boundaries): every read filters on ``owner_user_id``,
so a cross-tenant caller gets ``None``/``[]`` rather than a leaked row. These are
**per-book** tier rows — owned by a user, scoped to a book, never shared or
globally writable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence
from uuid import UUID, uuid4

import asyncpg

from app.gamegen.answer_hash import (
    AnswerEvidence,
    AnswerShapeError,
    answer_hash,
    says_json,
)

__all__ = ["Decision", "Answer", "GamegenS2Repo", "BatchSizeMismatch"]

REVIEW_STATUSES = frozenset({"proposed", "approved", "rejected"})


class BatchSizeMismatch(ValueError):
    """A bulk approval declares a size that is not the number of decisions in it."""


@dataclass(frozen=True)
class Decision:
    decision_id: UUID
    job_id: UUID
    owner_user_id: UUID
    book_id: UUID | None
    element_kind: str
    question_class: str
    target_ref: str
    review_status: str
    approved_by: UUID | None
    approved_at: datetime | None
    rejected_reason: str | None
    batch_id: UUID | None
    batch_size: int | None


@dataclass(frozen=True)
class Answer:
    answer_id: UUID
    decision_id: UUID
    job_id: UUID
    question_id: str
    target_ref: str
    says: list[dict]
    proposed_text: str | None
    not_stated: bool
    not_stated_reason: str | None
    answer_hash: str
    verified_against_seal_id: UUID | None
    superseded_by_answer_id: UUID | None


class GamegenS2Repo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ── S0: the seal ────────────────────────────────────────────────────────

    async def seal_corpus(
        self,
        *,
        corpus_id: UUID,
        owner_user_id: UUID,
        book_id: UUID | None,
        sealed_by: UUID,
    ) -> UUID:
        """Seal a corpus, or return the existing seal for the same root.

        Re-sealing an **unchanged** corpus is idempotent by design: a second row
        with the same root and a later ``sealed_at`` would let two answers cite
        byte-identical evidence under two different seals, and the difference
        would look like it meant something.

        The ``WHERE EXISTS`` is a tenancy guard, not a foreign key: the FK proves
        the corpus exists, not that it is **this caller's**. Without it any
        authenticated user could mint a seal over another user's corpus and then
        cite it — the seal is the thing `PGN-A14` grounds a citation in, so a seal
        anyone can create over anyone's bytes grounds nothing.

        **Both the digest and the count are DERIVED, never accepted.** A seal is
        an attestation about what the corpus contained, so a caller-supplied
        digest is the attestation attesting to itself — a seal claiming 9 chunks
        over a corpus of 300 would look exactly like one that read the whole
        thing, and a caller-supplied root would let a citation be checked against
        a snapshot that never existed.

        The digest is computed **in the same statement** as the insert, so no
        concurrent ingest can slip a chunk in between "compute" and "record". The
        canonical form is ``chunk_id:chunk_index:content`` per chunk, newline-
        joined in ``chunk_index`` order, SHA-256'd — the three fields that decide
        what a citation at ``[chunk_id, span]`` resolves to.

        :raises PermissionError: when the corpus is absent or owned by someone else.
            One message for both, deliberately: distinguishing them tells a caller
            whether a corpus_id they cannot see exists.
        :raises ValueError: when the corpus has no chunks. An empty corpus seals
            to a digest that attests to nothing, and every citation against it
            would then name a chunk the seal never covered.
        """
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO gamegen_corpus_seal
                      (corpus_id, owner_user_id, book_id, corpus_digest, chunk_count, sealed_by)
                    SELECT $1,$2,$3,
                           (SELECT encode(sha256(convert_to(
                              coalesce(string_agg(
                                chunk_id::text || ':' || chunk_index::text || ':' || content,
                                E'\n' ORDER BY chunk_index
                              ), ''), 'UTF8')), 'hex')
                            FROM source_corpus_chunk WHERE corpus_id = $1),
                           (SELECT count(*) FROM source_corpus_chunk WHERE corpus_id = $1),
                           $4
                     WHERE EXISTS (
                       SELECT 1 FROM source_corpus WHERE corpus_id = $1 AND user_id = $2
                     )
                    ON CONFLICT (corpus_id, corpus_digest) DO UPDATE
                      SET corpus_id = EXCLUDED.corpus_id  -- no-op; forces RETURNING
                    RETURNING seal_id
                    """,
                    corpus_id, owner_user_id, book_id, sealed_by,
                )
        except asyncpg.CheckViolationError as exc:
            # The visible-but-empty case: the derived count is 0 and
            # `gamegen_seal_nonempty` refuses. Translated rather than propagated,
            # because "check constraint violated" does not tell a caller to ingest
            # the corpus first.
            if "nonempty" not in str(exc):
                raise
            raise ValueError(
                f"corpus {corpus_id} has no chunks. Sealing it would attest to nothing, "
                f"and every citation against that seal would name a chunk it never "
                f"covered."
            ) from exc
        if row is None:
            raise PermissionError(
                f"corpus {corpus_id} is not visible to {owner_user_id}. A seal is what "
                f"grounds a citation (PGN-A14); one that any user could mint over any "
                f"user's bytes grounds nothing."
            )
        return row["seal_id"]

    # ── S2: the approval unit ───────────────────────────────────────────────

    async def propose_decision(
        self,
        *,
        job_id: UUID,
        owner_user_id: UUID,
        book_id: UUID | None,
        element_kind: str,
        question_class: str,
        target_ref: str,
    ) -> UUID:
        """Create the decision for one ``(question_class x target)`` assertion class.

        There is no ``review_status`` argument. A decision is born ``proposed``
        and reaches ``approved`` only through :meth:`approve`, which is the only
        writer of ``approved_by`` — the property T5 rests on.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO gamegen_decision
                  (job_id, owner_user_id, book_id, element_kind, question_class, target_ref)
                VALUES ($1,$2,$3,$4,$5,$6)
                RETURNING decision_id
                """,
                job_id, owner_user_id, book_id, element_kind, question_class, target_ref,
            )
        return row["decision_id"]

    async def approve(
        self,
        *,
        decision_ids: Sequence[UUID],
        owner_user_id: UUID,
        approved_by: UUID,
    ) -> UUID | None:
        """Approve one or many decisions as a single reviewer action.

        A single-decision approval carries no batch. **Two or more is a batch**,
        and the batch is stamped with its real size — T3's "bulk is visible".
        The size is derived from the argument rather than taken as a parameter,
        so the number cannot be understated at the call site; the DEFERRED
        constraint trigger then checks it against the committed rows, which is
        what catches the case this function cannot see (a decision added to the
        batch afterwards).

        Runs in ONE transaction. A partially-approved batch would leave a
        ``batch_size`` that is honest about nothing.
        """
        ids = list(dict.fromkeys(decision_ids))  # de-dup, preserve order
        if not ids:
            return None
        batch_id = uuid4() if len(ids) > 1 else None
        batch_size = len(ids) if batch_id else None

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                updated = await conn.fetch(
                    """
                    UPDATE gamegen_decision
                       SET review_status = 'approved',
                           approved_by   = $3,
                           approved_at   = now(),
                           batch_id      = $4,
                           batch_size    = $5,
                           updated_at    = now()
                     WHERE decision_id = ANY($1::uuid[])
                       AND owner_user_id = $2
                       AND review_status = 'proposed'
                    RETURNING decision_id
                    """,
                    ids, owner_user_id, approved_by, batch_id, batch_size,
                )
                if len(updated) != len(ids):
                    # Refuse rather than approve the subset: the caller believes
                    # it approved N assertions. Approving fewer and reporting
                    # success is the silent-drop class with a signature on it.
                    raise BatchSizeMismatch(
                        f"asked to approve {len(ids)} decisions, {len(updated)} were "
                        f"eligible (wrong owner, already decided, or absent). Rolled "
                        f"back - a partial approval would record a batch_size nobody "
                        f"reviewed."
                    )
        return batch_id

    async def reject(
        self, *, decision_id: UUID, owner_user_id: UUID, reason: str
    ) -> bool:
        if not reason.strip():
            raise ValueError(
                "a rejection needs a reason: the row is the only record of why an "
                "assertion did not reach the fold"
            )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE gamegen_decision
                   SET review_status = 'rejected', rejected_reason = $3, updated_at = now()
                 WHERE decision_id = $1 AND owner_user_id = $2 AND review_status = 'proposed'
                RETURNING decision_id
                """,
                decision_id, owner_user_id, reason,
            )
        return row is not None

    # ── S2: the evidence ────────────────────────────────────────────────────

    async def record_answer(
        self,
        *,
        decision_id: UUID,
        job_id: UUID,
        owner_user_id: UUID,
        book_id: UUID | None,
        created_by: UUID,
        evidence: AnswerEvidence,
        supersedes: UUID | None = None,
    ) -> UUID:
        """Insert an answer, computing its hash.

        **Retire, then insert** — in that order, in one transaction. The reverse
        (insert then retire) is what this was written as first, and it fails: the
        partial unique index ``uq_gamegen_answer_live`` sees two live answers for
        one ``(job, question, target)`` the instant the second row lands, which is
        correct of it — that moment is exactly when the chain has two truths. So
        the old answer is pointed at an ``answer_id`` generated up front, and
        ``superseded_by_answer_id`` is a DEFERRABLE FK that resolves at COMMIT.

        :raises AnswerShapeError: before any I/O, when the evidence is
            inadmissible. The DB CHECKs say the same thing; this one says it with
            the field named.
        """
        h = answer_hash(evidence)  # validates; raises AnswerShapeError

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # From the DB, not uuid4(), so an answer_id keeps the same
                # time-ordered shape as every other id in this service.
                new_id: UUID = await conn.fetchval("SELECT uuidv7()")

                if supersedes is not None:
                    # The matched columns are the point, not defensive noise.
                    # Superseding an answer about a DIFFERENT question retires
                    # that question's only live answer and replaces it with one
                    # about something else - the question silently loses its
                    # answer, and S3's consumption ledger has nothing to notice
                    # because the row it would have counted is gone. That is the
                    # QTY-Q5 silent-drop class, reachable through a legal API.
                    done = await conn.fetchrow(
                        """
                        UPDATE gamegen_answer
                           SET superseded_by_answer_id = $2
                         WHERE answer_id = $1
                           AND owner_user_id = $3
                           AND job_id = $4
                           AND question_id = $5
                           AND target_ref = $6
                           AND superseded_by_answer_id IS NULL
                        RETURNING answer_id
                        """,
                        supersedes, new_id, owner_user_id, job_id,
                        evidence.question_id, evidence.target_ref,
                    )
                    if done is None:
                        raise ValueError(
                            f"answer {supersedes} cannot be superseded by an answer to "
                            f"({evidence.question_id!r}, {evidence.target_ref!r}) in job "
                            f"{job_id}: wrong owner, wrong job, a DIFFERENT question, or "
                            f"already superseded. Rolled back - a supersession that "
                            f"crosses questions retires one question's answer and gives "
                            f"it to another."
                        )

                await conn.execute(
                    """
                    INSERT INTO gamegen_answer
                      (answer_id, decision_id, job_id, owner_user_id, book_id,
                       question_id, target_ref, says_json, proposed_text,
                       verified_against_seal_id, not_stated, not_stated_reason,
                       answer_hash, created_by)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10,$11,$12,$13,$14)
                    """,
                    new_id, decision_id, job_id, owner_user_id, book_id,
                    evidence.question_id, evidence.target_ref,
                    json.dumps(says_json(evidence.says), ensure_ascii=False),
                    evidence.proposed_text,
                    UUID(evidence.verified_against_seal_id)
                    if evidence.verified_against_seal_id else None,
                    evidence.not_stated, evidence.not_stated_reason, h, created_by,
                )
        return new_id

    _SELECT_LIVE = """
        SELECT a.answer_id, a.decision_id, a.job_id, a.question_id, a.target_ref,
               a.says_json, a.proposed_text, a.not_stated, a.not_stated_reason,
               a.answer_hash, a.verified_against_seal_id, a.superseded_by_answer_id
          FROM gamegen_answer a
          JOIN gamegen_decision d ON d.decision_id = a.decision_id
         WHERE a.job_id = $1 AND a.owner_user_id = $2
           AND a.superseded_by_answer_id IS NULL
    """

    async def _fetch_live(self, sql: str, job_id: UUID, owner_user_id: UUID) -> list[Answer]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, job_id, owner_user_id)
        return [
            Answer(
                answer_id=r["answer_id"],
                decision_id=r["decision_id"],
                job_id=r["job_id"],
                question_id=r["question_id"],
                target_ref=r["target_ref"],
                says=json.loads(r["says_json"]),
                proposed_text=r["proposed_text"],
                not_stated=r["not_stated"],
                not_stated_reason=r["not_stated_reason"],
                answer_hash=r["answer_hash"],
                verified_against_seal_id=r["verified_against_seal_id"],
                superseded_by_answer_id=r["superseded_by_answer_id"],
            )
            for r in rows
        ]

    async def live_answers(self, *, job_id: UUID, owner_user_id: UUID) -> list[Answer]:
        """Every answer not yet superseded, for one job. Owner-scoped."""
        return await self._fetch_live(
            self._SELECT_LIVE + " ORDER BY a.created_at, a.answer_id", job_id, owner_user_id
        )

    async def approved_answers(self, *, job_id: UUID, owner_user_id: UUID) -> list[Answer]:
        """The S3 hand-off: live answers whose decision was approved.

        S3's consumption ledger is asserted over exactly this set, so what counts
        as approved here is what the fold must consume. One query rather than
        filtering :meth:`live_answers` against a second: two queries that have to
        agree on row order is a correctness property maintained by matching
        ``ORDER BY`` clauses in two places, and it fails silently.
        """
        return await self._fetch_live(
            self._SELECT_LIVE
            + " AND d.review_status = 'approved' ORDER BY a.created_at, a.answer_id",
            job_id,
            owner_user_id,
        )

    async def not_stated_ratio(
        self, *, job_id: UUID, owner_user_id: UUID
    ) -> dict[str, tuple[int, int]]:
        """``question_class -> (not_stated, total)`` over live answers.

        `PGN-A4` third constraint: the ratio is gated **per question class**, not
        globally. ``not_stated`` on a magnitude is expected; on tier names, against
        a corpus whose fixture requirement says it names the tiers, it is a red
        flag — and a single global ratio averages the second into the first.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT d.question_class,
                       count(*) FILTER (WHERE a.not_stated) AS silent,
                       count(*) AS total
                  FROM gamegen_answer a
                  JOIN gamegen_decision d ON d.decision_id = a.decision_id
                 WHERE a.job_id = $1 AND a.owner_user_id = $2
                   AND a.superseded_by_answer_id IS NULL
                 GROUP BY d.question_class
                """,
                job_id, owner_user_id,
            )
        return {r["question_class"]: (r["silent"], r["total"]) for r in rows}
