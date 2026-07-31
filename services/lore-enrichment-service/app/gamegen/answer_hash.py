"""`PGN-A9` — the answer hash, which is what makes the provenance chain hash-linked.

Doc 39 v1 referenced answers by bare id. The consequence it names is concrete:
an ``UPDATE`` on ``gamegen_answer`` after the creative structure was pinned could
retroactively convert an **invented** tier into an **extracted** one, with every
hop of the chain still resolving and every trust property still green. Two things
close that, and both are needed:

* the DB trigger that makes answers append-only (``gamegen_answer_append_only``);
* this hash, recomputed by S5 and compared, so that even a chain assembled by
  hand cannot claim an answer said something it did not.

## What is hashed, and what deliberately is not

The hash covers the **evidence**: what a source says, what the model proposed,
whether the corpus was silent and why, and which sealed corpus the citation was
checked against. It does **not** cover lineage
(``superseded_by_answer_id``), because supersession is the one legal mutation and
hashing it would mean superseding an answer changed what that answer said.

## The scope problem, and its mechanism

A hash over a hand-listed subset of a row's fields has the `NV-3` shape: *what
happens to a field added tomorrow?* Nothing — it is silently outside the promise,
and the hash keeps verifying while the row means something new. Python cannot
destructure exhaustively the way ``CanonEncode for Ruleset`` does, so the guard
here is explicit instead: :data:`HASHED_FIELDS` and :data:`UNHASHED_FIELDS`
partition :class:`AnswerEvidence`'s fields, and
:func:`assert_fields_are_partitioned` refuses any field belonging to neither. A
new field is a **test failure** until somebody decides which side it is on.

## Encoding

Length-prefixed, not JSON. A separator-joined encoding has a collision class
(``a="x|y", b=""`` vs ``a="x", b="y|"``), and JSON has several more once
non-ASCII, key order, and float formatting are in play — and this corpus is
Chinese. Every field is written as ``u32 big-endian length || UTF-8 bytes``, so
no value can be mistaken for a boundary.

``blake2b(digest_size=32)`` rather than BLAKE3: it is stdlib, and this digest is
never compared against a Rust-side hash. The engine's digests stay BLAKE3; this
one lives entirely in the pipeline DB, and adding a compiled dependency to a
service that does not otherwise need one would be the larger change.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, fields
from typing import Any, Sequence
from uuid import UUID

__all__ = [
    "AnswerEvidence",
    "Citation",
    "HASHED_FIELDS",
    "UNHASHED_FIELDS",
    "NOT_STATED_REASONS",
    "AnswerShapeError",
    "answer_hash",
    "assert_fields_are_partitioned",
]

_DOMAIN = b"lw.gamegen.answer.v1"

#: `PGN-A4` — the closed set, mirrored from the DB CHECK
#: ``gamegen_answer_not_stated_reason_closed``. Kept here so the repository can
#: refuse before the round trip and name the legal values; the DB is still the
#: enforcement point, this is the good error message.
NOT_STATED_REASONS = frozenset({"absent_from_corpus", "contradicted", "out_of_scope"})


class AnswerShapeError(ValueError):
    """An answer's shape is inadmissible before it ever reaches the DB."""


@dataclass(frozen=True)
class Citation:
    """One span of one chunk of a sealed corpus, with the text it is said to hold.

    ``quote`` is stored, and `PGN-A14` says the gate must never *render* it —
    it renders text fetched live at ``[chunk_id, span]`` and refuses on a
    mismatch. Storing it anyway is what makes that comparison possible; a
    citation with no recorded quote can only ever be checked for existence.

    **``start``/``end`` are CHARACTER offsets, half-open ``[start, end)``.** The
    corpus is Chinese and a byte offset differs from a character offset by 3× on
    every CJK chunk, so leaving the unit to convention would mean a citation that
    verifies against the wrong substring — the Multilingual standard's exact
    class. It is not left to convention: :func:`_validate` requires
    ``len(quote) == end - start``, so a byte-offset citation fails at insert
    rather than mis-verifying later. Python ``str`` slicing and Postgres
    ``length()``/``substring()`` are both character-based, so the verifier's
    ``content[start:end]`` agrees by construction.
    """

    chunk_id: str
    start: int
    end: int
    quote: str

    def as_json(self) -> dict[str, Any]:
        return {"chunk_id": self.chunk_id, "span": [self.start, self.end], "quote": self.quote}


@dataclass(frozen=True)
class AnswerEvidence:
    """The content of one answer. Lineage and identity live on the row, not here."""

    question_id: str
    target_ref: str
    says: tuple[Citation, ...]
    proposed_text: str | None
    not_stated: bool
    not_stated_reason: str | None
    verified_against_seal_id: str | None


#: Every field of :class:`AnswerEvidence` that the hash commits to.
HASHED_FIELDS = frozenset(
    {
        "question_id",
        "target_ref",
        "says",
        "proposed_text",
        "not_stated",
        "not_stated_reason",
        "verified_against_seal_id",
    }
)

#: Fields deliberately outside the promise. Empty today, and named rather than
#: omitted: an empty set with a home is auditable, an implicit one is not.
UNHASHED_FIELDS: frozenset[str] = frozenset()


def assert_fields_are_partitioned() -> None:
    """Every field of :class:`AnswerEvidence` is hashed or explicitly not.

    Called from the test suite. Its value is that a field added to the dataclass
    and forgotten here is a red test rather than a silent hole in what
    ``answer_hash`` promises.
    """
    present = {f.name for f in fields(AnswerEvidence)}
    classified = HASHED_FIELDS | UNHASHED_FIELDS

    unclassified = sorted(present - classified)
    if unclassified:
        raise AssertionError(
            f"AnswerEvidence field(s) {unclassified} are neither in HASHED_FIELDS nor in "
            f"UNHASHED_FIELDS. A field outside both is outside the hash's promise: "
            f"answer_hash keeps verifying while the row means something new, which is "
            f"exactly the retroactive-rewrite PGN-A9 exists to stop. Decide which side "
            f"it is on."
        )

    phantom = sorted(classified - present)
    if phantom:
        raise AssertionError(
            f"{phantom} are classified but no longer exist on AnswerEvidence. A stale "
            f"entry makes the partition look total when it is not."
        )

    both = sorted(HASHED_FIELDS & UNHASHED_FIELDS)
    if both:
        raise AssertionError(f"{both} are in BOTH sets; the partition is not a partition.")


def _w(h: "hashlib._Hash", value: str | bytes) -> None:
    b = value.encode("utf-8") if isinstance(value, str) else value
    h.update(len(b).to_bytes(4, "big"))
    h.update(b)


def _validate(ev: AnswerEvidence) -> None:
    """The shape rules, mirrored from the DB CHECKs.

    The DB is the enforcement point — these constraints exist as CHECKs precisely
    so that a writer bypassing this module cannot evade them. Repeating them here
    buys a named error before the round trip, and nothing more; if the two ever
    disagree the DB wins, and ``test_gamegen_s2`` asserts they do not.
    """
    if ev.not_stated:
        if ev.says:
            raise AnswerShapeError(
                "not_stated answer carries citations. `the book does not say` and `the "
                "book says this` are different answers; PGN-A4 makes the first complete, "
                "not partial."
            )
        if ev.proposed_text is not None:
            raise AnswerShapeError(
                "not_stated answer carries proposed_text. If the model has a proposal, "
                "the honest answer is the proposal - marking it not_stated hides an "
                "invention behind a silence."
            )
        if ev.not_stated_reason not in NOT_STATED_REASONS:
            raise AnswerShapeError(
                f"not_stated_reason={ev.not_stated_reason!r} is not one of "
                f"{sorted(NOT_STATED_REASONS)}. PGN-A4 keeps not_stated one click and "
                f"makes it accountable; a free-text reason is neither."
            )
    else:
        if ev.not_stated_reason is not None:
            raise AnswerShapeError("not_stated_reason set on an answer that is not not_stated")
        if not ev.says and ev.proposed_text is None:
            raise AnswerShapeError(
                "an answer with no citations, no proposal and no not_stated states "
                "nothing. S3's consumption ledger would faithfully record it as consumed."
            )

    if ev.says and ev.verified_against_seal_id is None:
        raise AnswerShapeError(
            "citations with no verified_against_seal_id. PGN-A14: a citation is verified "
            "against a SEALED corpus, never trusted - an answer that names no seal is one "
            "nobody could have checked."
        )

    seen: dict[str, list[tuple[int, int]]] = {}
    for c in ev.says:
        if not (0 <= c.start < c.end):
            raise AnswerShapeError(
                f"span [{c.start}, {c.end}) on chunk {c.chunk_id} is empty or backwards. "
                f"A zero-width span verifies against the empty string, i.e. against "
                f"anything."
            )
        if not c.quote:
            raise AnswerShapeError(f"citation to chunk {c.chunk_id} has an empty quote")
        try:
            UUID(c.chunk_id)
        except (ValueError, AttributeError, TypeError):
            raise AnswerShapeError(
                f"chunk_id {c.chunk_id!r} is not a UUID. It names a source_corpus_chunk "
                f"and cannot be a foreign key (it lives inside JSONB), so its format is "
                f"the only thing between a citation and a chunk that does not exist."
            ) from None
        if len(c.quote) != c.end - c.start:
            raise AnswerShapeError(
                f"span [{c.start}, {c.end}) is {c.end - c.start} long but the quote is "
                f"{len(c.quote)} characters. Spans are CHARACTER offsets, half-open - a "
                f"byte offset over Chinese text is ~3x the character count, and left "
                f"unchecked it would verify against the wrong substring instead of "
                f"failing here."
            )
        for s, e in seen.setdefault(c.chunk_id, []):
            if c.start < e and s < c.end:
                raise AnswerShapeError(
                    f"spans [{s}, {e}) and [{c.start}, {c.end}) on chunk {c.chunk_id} "
                    f"OVERLAP. PGN-A14 requires disjoint spans for an ordered list: one "
                    f"span cited N times is one piece of evidence dressed as N."
                )
        seen[c.chunk_id].append((c.start, c.end))


def answer_hash(ev: AnswerEvidence) -> str:
    """The 64-hex digest committed to by ``gamegen_answer.answer_hash``.

    Validates first: a hash over an inadmissible answer is a well-formed name for
    something that must not exist, and it would be accepted by every later check.
    """
    _validate(ev)

    h = hashlib.blake2b(digest_size=32)
    _w(h, _DOMAIN)
    _w(h, ev.question_id)
    _w(h, ev.target_ref)

    # Citation ORDER is part of the answer, not an implementation detail: for an
    # ordered list (`tier 1 is X, tier 2 is Y`) reordering the spans reorders the
    # claim. So no sort - the sequence is hashed as given.
    h.update(len(ev.says).to_bytes(4, "big"))
    for c in ev.says:
        _w(h, c.chunk_id)
        h.update(c.start.to_bytes(8, "big"))
        h.update(c.end.to_bytes(8, "big"))
        _w(h, c.quote)

    # A present-but-empty string and an absent value are different answers, so
    # each nullable field gets a one-byte presence tag rather than collapsing to
    # "".
    for optional in (ev.proposed_text, ev.not_stated_reason, ev.verified_against_seal_id):
        if optional is None:
            h.update(b"\x00")
        else:
            h.update(b"\x01")
            _w(h, optional)

    h.update(b"\x01" if ev.not_stated else b"\x00")
    return h.hexdigest()


def says_json(says: Sequence[Citation]) -> list[dict[str, Any]]:
    """The JSONB form the DB stores. Kept beside the hash so the two cannot drift."""
    return [c.as_json() for c in says]
