"""S0's real half — the 武俠 fixture, ingested, sealed, and **cited against**.

Until this file, every citation in the pipeline was *nameable* and none had ever
been *read*: the fixture was ten markdown files on disk and `source_corpus_chunk`
was empty. `T1b` was half built by construction.

The tests that matter are the three refusals in :meth:`verify_citation` — a chunk
outside the seal, a span outside the chunk, and bytes that differ. A verifier that
only ever confirmed a citation it was handed correctly would be `PGN-A14` written
as a function call.

Destructive-ops note: cleanup is the ``pool`` fixture's down→up migration, guarded
by this directory's ``conftest.py`` (``db-safety-gate: guarded-dir``).
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.db.repositories.gamegen import GamegenS2Repo
from app.gamegen.corpus import GamegenCorpus, read_fixture_corpus

from .test_gamegen_s2 import BOOK, OTHER_OWNER, OWNER

pytestmark = pytest.mark.asyncio

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "wuxia"


async def _ingested(pool, *, owner=OWNER, docs=None):
    c = GamegenCorpus(pool)
    res = await c.ingest(
        owner_user_id=owner, project_id=BOOK, book_id=BOOK,
        name="寒潭劍錄 + wiki",
        documents=docs if docs is not None else read_fixture_corpus(FIXTURE),
        license="public-domain",
    )
    seal = await GamegenS2Repo(pool).seal_corpus(
        corpus_id=res.corpus_id, owner_user_id=owner, book_id=BOOK, sealed_by=owner)
    return c, res, seal


async def _a_chunk(pool, corpus_id, index=0):
    async with pool.acquire() as c:
        return await c.fetchrow(
            "SELECT chunk_id, content FROM source_corpus_chunk "
            "WHERE corpus_id=$1 AND chunk_index=$2", corpus_id, index)


# ── the fixture finally has a home ──────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="function")
async def test_the_fixture_is_on_disk_and_non_trivial() -> None:
    """Not a DB test. If the fixture moved or emptied, everything below would pass
    against nothing — the `NV-3` shape where the scope never reaches the check."""
    docs = read_fixture_corpus(FIXTURE)
    assert len(docs) >= 8, [t for t, _ in docs]
    assert sum(len(b) for _, b in docs) > 5000
    assert any("內功" in b for _, b in docs), "the corpus is the 武俠 one"


@pytest.mark.asyncio(loop_scope="function")
async def test_reading_the_fixture_is_ORDER_STABLE() -> None:
    """Chunk ordinals derived from file order are part of the seal. An ingest whose
    order depended on the filesystem would produce a different `corpus_digest` on a
    different machine, and a citation checked against one would not resolve against
    the other.

    The order is by ``Path``, not by title string — ``book/ch03.md`` precedes
    ``README.md``. That is deterministic, which is the property; asserting
    lexicographic title order instead was asserting the wrong thing, and did.
    """
    once = read_fixture_corpus(FIXTURE)
    assert once == read_fixture_corpus(FIXTURE), "same bytes, same order, every call"
    paths = [Path(t) for t, _ in once]
    assert paths == sorted(paths), "a pure function of the sorted paths"


async def test_the_wuxia_fixture_ingests_and_seals(pool):
    """**The first time a book reaches this pipeline's database.**"""
    _, res, seal = await _ingested(pool)
    assert res.chunks_inserted == res.chunks_total > 0
    async with pool.acquire() as c:
        n, cnt = await c.fetchval(
            "SELECT chunk_count FROM gamegen_corpus_seal WHERE seal_id=$1", seal), res.chunks_total
    assert n == cnt, "the seal counted what was ingested"


async def test_the_chunks_carry_the_CJK_text_unmangled(pool):
    """ML-2/ML-3. A chunker that split on spaces or normalised away the script
    would leave every citation unverifiable, and the failure would look like a
    model problem."""
    _, res, _ = await _ingested(pool)
    async with pool.acquire() as c:
        joined = "".join(
            r["content"] for r in await c.fetch(
                "SELECT content FROM source_corpus_chunk WHERE corpus_id=$1 "
                "ORDER BY chunk_index", res.corpus_id))
    assert "內功" in joined and "寒潭" in joined


async def test_the_ingest_refuses_a_corpus_with_NO_content(pool):
    """The genuine empty case is *no documents*. A document with an empty body
    still chunks, because the ingest prepends ``# {title}`` and a title IS
    content — worth stating, since the first version of this test asserted the
    opposite and failed for that reason."""
    c = GamegenCorpus(pool)
    with pytest.raises(ValueError) as e:
        await c.ingest(owner_user_id=OWNER, project_id=BOOK, book_id=BOOK,
                       name="empty", documents=[])
    assert "attests to nothing" in str(e.value)


async def test_a_title_only_document_still_chunks(pool):
    """Documented rather than guarded: a title is real text a citation could
    legitimately point at."""
    c = GamegenCorpus(pool)
    res = await c.ingest(owner_user_id=OWNER, project_id=BOOK, book_id=BOOK,
                         name="titles", documents=[("寒潭劍錄", "  ")])
    assert res.chunks_total == 1


async def test_the_derived_digest_matches_the_one_the_seal_stored(pool):
    """Two implementations of *"what the corpus is"* would disagree the first time
    one of them changed. This asserts there is only one."""
    corpus, res, seal = await _ingested(pool)
    async with pool.acquire() as c:
        stored = await c.fetchval(
            "SELECT corpus_digest FROM gamegen_corpus_seal WHERE seal_id=$1", seal)
    assert await corpus.corpus_digest_of(res.corpus_id) == stored


# ── PGN-A14: a citation is VERIFIED, never trusted ──────────────────────────


async def test_a_TRUE_citation_verifies_against_the_sealed_bytes(pool):
    """The happy path, and it is the one that had never run: before the ingest
    there were no bytes to fetch."""
    corpus, res, seal = await _ingested(pool)
    row = await _a_chunk(pool, res.corpus_id)
    quote = row["content"][3:11]
    v = await corpus.verify_citation(
        seal_id=seal, chunk_id=row["chunk_id"], start=3, end=11, quote=quote)
    assert v.ok, v.reason
    assert v.actual == quote


async def test_a_FABRICATED_quote_is_refused_and_the_corpus_ANSWERS(pool):
    """**The headline refusal.** The verdict carries what the corpus actually says
    — rendering the *claimed* quote to a reviewer would have them compare the model
    against itself, which is the comparison `PGN-A14` exists to break."""
    corpus, res, seal = await _ingested(pool)
    row = await _a_chunk(pool, res.corpus_id)
    v = await corpus.verify_citation(
        seal_id=seal, chunk_id=row["chunk_id"], start=0, end=6,
        quote="內功分為九層")  # plausible, and not what is there at [0,6)
    if row["content"][0:6] == "內功分為九層":
        pytest.skip("the fixture happens to say exactly this at [0,6)")
    assert not v.ok
    assert "the corpus does not say this" in v.reason
    assert v.actual == row["content"][0:6], "the reviewer is shown the real bytes"


async def test_a_span_OUTSIDE_the_chunk_is_refused(pool):
    corpus, res, seal = await _ingested(pool)
    row = await _a_chunk(pool, res.corpus_id)
    n = len(row["content"])
    v = await corpus.verify_citation(
        seal_id=seal, chunk_id=row["chunk_id"], start=n - 2, end=n + 500, quote="x" * 502)
    assert not v.ok
    assert "outside chunk" in v.reason


async def test_a_chunk_OUTSIDE_the_seal_is_refused(pool):
    """A citation pointing at text the seal never attested. The seal is what
    grounds a citation; one pointing outside it grounds nothing."""
    corpus, res, seal_a = await _ingested(pool)
    _, res_b, _ = await _ingested(
        pool, docs=[("other", "完全不同的內容，與寒潭劍錄無關。" * 20)])
    other = await _a_chunk(pool, res_b.corpus_id)
    v = await corpus.verify_citation(
        seal_id=seal_a, chunk_id=other["chunk_id"], start=0, end=4,
        quote=other["content"][0:4])
    assert not v.ok
    assert "is not in the corpus sealed by" in v.reason


async def test_a_BYTE_offset_over_CJK_is_refused_by_the_verifier_too(pool):
    """S2's ``length(quote) = end - start`` CHECK refuses a byte offset at insert.
    This is the other end of the same rule: a citation that survived the length
    check by coincidence still fails when the bytes are actually read."""
    corpus, res, seal = await _ingested(pool)
    row = await _a_chunk(pool, res.corpus_id)
    content = row["content"]
    # Chunk 0 opens with an ASCII markdown heading, so offset 0 is NOT CJK — the
    # first version asserted `len(encode) > len` there and failed for that reason.
    start = next(i for i, ch in enumerate(content[:-8]) if ord(ch) > 0x2E80)
    quote = content[start:start + 6]
    assert len(quote.encode("utf-8")) > len(quote), f"CJK at {start}: {quote!r}"
    # A byte-offset citation: same start, end advanced by the BYTE length.
    v = await corpus.verify_citation(
        seal_id=seal, chunk_id=row["chunk_id"], start=start,
        end=start + len(quote.encode("utf-8")), quote=quote)
    assert not v.ok
    assert "does not say this" in v.reason


async def test_a_verdict_is_never_a_bare_bool(pool):
    """A refusal a reviewer cannot act on sends them back to the model's own
    quote."""
    corpus, res, seal = await _ingested(pool)
    row = await _a_chunk(pool, res.corpus_id)
    v = await corpus.verify_citation(
        seal_id=seal, chunk_id=row["chunk_id"], start=0, end=4, quote="錯誤引用")
    assert v.ok is False and v.reason and len(v.reason) > 40


async def test_an_unknown_chunk_id_is_refused_rather_than_crashing(pool):
    corpus, res, seal = await _ingested(pool)
    v = await corpus.verify_citation(
        seal_id=seal, chunk_id=uuid4(), start=0, end=2, quote="ab")
    assert not v.ok and "not in the corpus sealed by" in v.reason
