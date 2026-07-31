"""S0 — the corpus a citation is verified *against*, and the verifier itself.

Doc 39 §4.2's second half:

> **`PGN-A14` — a citation is verified, never trusted.** The gate never renders
> ``says_json.quote``. It renders bytes fetched live from the sealed corpus at
> ``[chunk_id, span]``; a mismatch is an S2 **refusal**. Otherwise the model
> supplies both the claim and the evidence for the claim, and the human compares
> the model against itself.

Everything before this slice made a citation *nameable* — a span, disjoint from
its siblings, pointing at a chunk id, under a seal. **Nothing had ever read the
bytes**, because the corpus had never been ingested. The fixture was ten markdown
files on disk. So `T1b` was half built by construction, not by omission.

## What is reused, and the one thing that is not

Chunking is :func:`app.retrieval.chunker.chunk_text` — the CJK-aware sentence
window this service already owns. Reimplementing it would be the copy-paste
`SDK-First` forbids, and worse: a *second* chunker would produce different
offsets for the same text, so a citation verified under one and stored under the
other would drift silently.

What is **not** reused is ``ingest_corpus``: it embeds, and embedding needs a
resolved model. A gamegen citation is verified by **byte comparison at an
offset**; nothing in this pipeline retrieves semantically. Requiring a provider
call to seal a corpus would couple S0 to a model for a vector no stage reads —
and would make the fixture un-ingestable on a machine with no BYOK credential.
The chunk rows are identical either way; only the ``embedding`` column stays NULL,
which the schema already permits.

## Offsets are CHARACTERS, and that is checked, not asserted

``content[start:end]`` in Python and ``substring()`` in Postgres are both
character-based, and S2's ``length(quote) = end - start`` CHECK already refuses a
byte offset at insert. This module closes the loop: it compares the *actual*
substring to the *stored* quote, so a citation that survived the length check by
coincidence still fails here.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from app.retrieval.chunker import chunk_text

__all__ = [
    "CitationVerdict",
    "CorpusIngestResult",
    "GamegenCorpus",
    "read_fixture_corpus",
]


@dataclass(frozen=True)
class CorpusIngestResult:
    corpus_id: UUID
    chunks_inserted: int
    chunks_total: int


@dataclass(frozen=True)
class CitationVerdict:
    """Why a citation was accepted or refused. **Never a bare bool** — a refusal a
    reviewer cannot act on sends them back to the model's own quote, which is the
    comparison `PGN-A14` exists to break."""

    ok: bool
    reason: str | None = None
    actual: str | None = None


def read_fixture_corpus(root: Path) -> list[tuple[str, str]]:
    """``(relative path, text)`` for every markdown file under ``root``, sorted.

    Sorted because the chunk ordinals derived from it are part of the seal: an
    ingest whose file order depended on the filesystem would produce a different
    ``corpus_digest`` on a different machine, and a citation checked against one
    would not resolve against the other.
    """
    files = sorted(p for p in root.rglob("*.md"))
    return [(str(p.relative_to(root)).replace("\\", "/"), p.read_text(encoding="utf-8"))
            for p in files]


class GamegenCorpus:
    """Ingest a corpus for gamegen, and verify citations against it."""

    def __init__(self, pool) -> None:
        self._pool = pool

    async def ingest(
        self,
        *,
        owner_user_id: UUID,
        project_id: UUID,
        book_id: UUID,
        name: str,
        documents: list[tuple[str, str]],
        license: str = "unknown",
    ) -> CorpusIngestResult:
        """Chunk and store ``documents`` as one corpus.

        ``license`` defaults to ``'unknown'``, which the C17 licensing gate
        REFUSES — fail-closed, inherited from `source_corpus`'s own default. A
        corpus the author owns must be tagged explicitly.

        Documents are concatenated **with their titles**, in sorted order, and
        chunked as one text. Per-file chunking would make a chunk ordinal mean
        *"the n-th chunk of file f"*, and a citation would then need the filename
        too — one more thing to get wrong at a seam that already has a span.
        """
        text = "\n\n".join(f"# {title}\n\n{body}".strip() for title, body in documents)
        chunks = chunk_text(text)
        if not chunks:
            raise ValueError(
                f"corpus {name!r} produced no chunks. Refused rather than sealed empty: "
                f"an empty corpus seals to a digest that attests to nothing, and every "
                f"citation against it would name a chunk it never covered."
            )

        async with self._pool.acquire() as conn:
            corpus_id = await conn.fetchval(
                """
                INSERT INTO source_corpus (project_id, user_id, name, kind, license,
                                           provenance_json)
                VALUES ($1,$2,$3,'other',$4,$5::jsonb)
                RETURNING corpus_id
                """,
                project_id, owner_user_id, name, license,
                f'{{"book_id": "{book_id}", "documents": {len(documents)}}}',
            )
            inserted = 0
            for ch in chunks:
                status = await conn.execute(
                    """
                    INSERT INTO source_corpus_chunk
                      (corpus_id, project_id, chunk_index, content, content_sha256)
                    VALUES ($1,$2,$3,$4,$5)
                    ON CONFLICT (corpus_id, chunk_index) DO NOTHING
                    """,
                    corpus_id, project_id, ch.index, ch.content, ch.sha256,
                )
                if status.endswith(" 1"):
                    inserted += 1
        return CorpusIngestResult(corpus_id, inserted, len(chunks))

    async def verify_citation(
        self, *, seal_id: UUID, chunk_id: UUID, start: int, end: int, quote: str
    ) -> CitationVerdict:
        """**`PGN-A14`.** Fetch the bytes at ``[chunk_id, start:end)`` from the
        corpus this seal covers and compare them to ``quote``.

        Three ways this refuses, and each is a different lie:

        * the chunk is **not in the sealed corpus** — the citation points at text
          the seal never attested, so the seal grounds nothing;
        * the span is **out of range** — a citation to bytes that do not exist;
        * the bytes **differ** — the quote was written, not read.

        Returns the ACTUAL substring on a mismatch. That is the whole point: a
        reviewer must see what the corpus says, not what the model said it says.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT c.content
                  FROM source_corpus_chunk c
                  JOIN gamegen_corpus_seal s ON s.corpus_id = c.corpus_id
                 WHERE c.chunk_id = $1 AND s.seal_id = $2
                """,
                chunk_id, seal_id,
            )
        if row is None:
            return CitationVerdict(
                False,
                f"chunk {chunk_id} is not in the corpus sealed by {seal_id}. The seal is "
                f"what grounds a citation; one pointing outside it grounds nothing.",
            )

        content = row["content"]
        if not (0 <= start < end <= len(content)):
            return CitationVerdict(
                False,
                f"span [{start}, {end}) is outside chunk {chunk_id}, which is "
                f"{len(content)} characters. A citation to bytes that do not exist.",
            )

        actual = content[start:end]
        if actual != quote:
            return CitationVerdict(
                False,
                f"the corpus does not say this. At [{start}, {end}) it says {actual!r}; "
                f"the citation claims {quote!r}. The quote was written, not read - and "
                f"rendering the claimed quote to a reviewer would have them compare the "
                f"model against itself.",
                actual,
            )
        return CitationVerdict(True, actual=actual)

    async def corpus_digest_of(self, corpus_id: UUID) -> str:
        """The digest `seal_corpus` derives, computed here for a caller that wants
        to check a seal without writing one. Same canonical form —
        ``chunk_id:chunk_index:content`` per chunk, newline-joined in index order,
        SHA-256 — because two implementations of *"what the corpus is"* would
        disagree the first time one of them changed."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT chunk_id, chunk_index, content FROM source_corpus_chunk "
                "WHERE corpus_id=$1 ORDER BY chunk_index",
                corpus_id,
            )
        joined = "\n".join(f"{r['chunk_id']}:{r['chunk_index']}:{r['content']}" for r in rows)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()
