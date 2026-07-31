"""S1→S2 — the interrogation, and every way a model's answer is refused.

No DB, no network: the provider seam is injected (`CompleteFn`), which is the same
reason the rest of this service can be tested without a model. A test that needed
a live LLM to prove *"a fabricated quote is refused"* would be a test nobody runs.

The load-bearing property is that **the model never supplies an offset**. Every
span is derived by finding the quote in the sealed chunk, so a fabricated citation
is not detected — it is *inexpressible*.
"""

from __future__ import annotations

import json

import pytest

from app.gamegen.brief import Question
from app.gamegen.interrogate import (
    MAX_PROMPT_CHUNKS,
    Chunk,
    InterrogationRefusal,
    build_prompt,
    interrogate,
    locate,
    parse_proposal,
    to_evidence,
)

SEAL = "0191f2a0-0000-7000-8000-000000000001"
C1 = "0191f2a0-0000-7000-8000-00000000000a"
C2 = "0191f2a0-0000-7000-8000-00000000000b"

CORPUS = [
    Chunk(C1, "內功分為九層，練氣一層至九層。陳玄一在寒潭閉關三年，終於破入築基。"),
    Chunk(C2, "劍術者，以悟性為根。悟性愈高，習劍愈速。"),
]
CHUNK_MAP = {c.chunk_id: c.content for c in CORPUS}

Q_OPEN = Question(id="tier_count", path="kind.tier_count", ask="How many tiers?",
                  answer_shape="count")
Q_CLOSED = Question(id="curve", path="kind.curve", ask="Which curve?",
                    answer_shape="closed set", options=("linear", "log", "stage"))


def reply(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False)


async def _run(raw, question=Q_OPEN, chunks=CORPUS):
    async def fake_complete(prompt, ctx):
        return raw
    return await interrogate(
        question=question, target_ref="kind:internal_energy", chunks=chunks,
        seal_id=SEAL, complete_fn=fake_complete, context=object(),
    )


# ── the prompt ──────────────────────────────────────────────────────────────


def test_the_prompt_shows_EVERY_chunk_with_its_id() -> None:
    """Exhaustive at POC scale: no retrieval step can drop the one paragraph that
    answers the question."""
    p = build_prompt(Q_OPEN, CORPUS)
    assert C1 in p and C2 in p
    assert "內功分為九層" in p and "以悟性為根" in p


def test_a_closed_set_question_shows_its_OPTIONS(*_) -> None:
    """`PGN-A13` — the model cannot answer *"stage-ish"* and the reviewer never
    sees a free string."""
    p = build_prompt(Q_CLOSED, CORPUS)
    assert "CHOOSE EXACTLY ONE OF: linear, log, stage" in p


def test_the_prompt_names_the_closed_set_of_not_stated_reasons() -> None:
    p = build_prompt(Q_OPEN, CORPUS)
    for r in ("absent_from_corpus", "contradicted", "out_of_scope"):
        assert r in p


def test_an_EMPTY_corpus_is_refused_rather_than_prompted() -> None:
    """Otherwise every answer would be `invented` and the run would look like a
    book that says nothing rather than a corpus that was never ingested."""
    with pytest.raises(InterrogationRefusal) as e:
        build_prompt(Q_OPEN, [])
    assert "never ingested" in str(e.value)


def test_a_corpus_TOO_LARGE_to_show_exhaustively_is_refused_not_truncated() -> None:
    """Silent truncation is how the paragraph that answered the question
    disappears with every gate still green."""
    big = [Chunk(f"{i:032x}", "x") for i in range(MAX_PROMPT_CHUNKS + 1)]
    with pytest.raises(InterrogationRefusal) as e:
        build_prompt(Q_OPEN, big)
    assert "needs a retrieval stage" in str(e.value)


# ── the model never supplies an offset ──────────────────────────────────────


def test_a_span_is_DERIVED_from_the_sealed_text() -> None:
    """Models cannot count characters, and an offset they supplied would be one
    more self-reported input — the class already removed six times here."""
    start, end = locate(CHUNK_MAP, C1, "寒潭閉關三年")
    assert CHUNK_MAP[C1][start:end] == "寒潭閉關三年"
    assert end - start == 6, "CHARACTER offsets, and the S2 CHECK depends on it"


def test_a_FABRICATED_quote_cannot_be_given_a_span_at_all() -> None:
    """**The headline.** Fabrication is not detected here — it is inexpressible: a
    citation without an offset is not a citation, and the only source of offsets
    is the corpus."""
    with pytest.raises(InterrogationRefusal) as e:
        locate(CHUNK_MAP, C1, "陳玄一在火山閉關十年")
    assert "THE CORPUS DOES NOT SAY THIS" in str(e.value)


def test_a_quote_that_appears_TWICE_is_refused_rather_than_resolved(*_) -> None:
    """Two different passages could be meant, and choosing the first would decide
    for the reviewer."""
    chunks = {C1: "一層。二層。一層。"}
    with pytest.raises(InterrogationRefusal) as e:
        locate(chunks, C1, "一層")
    assert "more than once" in str(e.value)


def test_a_citation_to_a_chunk_that_was_never_shown_is_refused() -> None:
    with pytest.raises(InterrogationRefusal) as e:
        locate(CHUNK_MAP, "0191f2a0-0000-7000-8000-0000000000ff", "內功")
    assert "not in the sealed corpus" in str(e.value)


# ── the three shapes, and no fourth ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_EXTRACTED_answer_carries_verified_spans() -> None:
    ev = await _run(reply(shape="extracted", value=9,
                          quotes=[{"chunk_id": C1, "quote": "內功分為九層"}]))
    assert ev.value == 9 and not ev.not_stated and ev.proposed_text is None
    assert len(ev.says) == 1
    c = ev.says[0]
    assert CHUNK_MAP[C1][c.start:c.end] == c.quote
    assert ev.verified_against_seal_id == SEAL


@pytest.mark.asyncio
async def test_an_INVENTED_answer_is_marked_and_carries_NO_seal() -> None:
    """`PGN-A3`: provenance stays derivable — says[] empty with proposed_text means
    the model made it up, and nothing about the row can later be read as evidence."""
    ev = await _run(reply(shape="invented", value="log",
                          proposed_text="the book implies a slowing curve"),
                    question=Q_CLOSED)
    assert ev.says == () and ev.proposed_text
    assert ev.verified_against_seal_id is None, "an invention cites no corpus"


@pytest.mark.asyncio
async def test_a_NOT_STATED_answer_is_accountable() -> None:
    ev = await _run(reply(shape="not_stated", value=None,
                          not_stated_reason="absent_from_corpus"))
    assert ev.not_stated and ev.value is None
    assert ev.not_stated_reason == "absent_from_corpus"


@pytest.mark.asyncio
async def test_a_FOURTH_shape_is_refused() -> None:
    with pytest.raises(InterrogationRefusal) as e:
        await _run(reply(shape="probably", value=9))
    assert "There is no fourth shape" in str(e.value)


@pytest.mark.asyncio
async def test_claiming_EXTRACTED_with_no_quotes_is_refused_not_downgraded() -> None:
    """**Not silently recorded as `invented`.** Downgrading a false evidence claim
    teaches that claiming evidence is free — laundering run backwards."""
    with pytest.raises(InterrogationRefusal) as e:
        await _run(reply(shape="extracted", value=9, quotes=[]))
    assert "laundering run backwards" in str(e.value)


@pytest.mark.asyncio
async def test_claiming_EXTRACTED_with_a_fabricated_quote_is_refused() -> None:
    """End to end: the model asserts the book says something it does not, and the
    answer never becomes storable evidence."""
    with pytest.raises(InterrogationRefusal) as e:
        await _run(reply(shape="extracted", value=12,
                         quotes=[{"chunk_id": C1, "quote": "內功分為十二層"}]))
    assert "THE CORPUS DOES NOT SAY THIS" in str(e.value)


@pytest.mark.asyncio
async def test_a_free_text_not_stated_reason_is_refused() -> None:
    with pytest.raises(InterrogationRefusal) as e:
        await _run(reply(shape="not_stated", not_stated_reason="couldn't find it"))
    assert "PGN-A4" in str(e.value)


@pytest.mark.asyncio
async def test_a_closed_set_answer_OUTSIDE_its_options_is_refused() -> None:
    """`PGN-A13`: the options come from the engine's enum, so an answer outside
    them names a variant the engine does not have."""
    with pytest.raises(InterrogationRefusal) as e:
        await _run(reply(shape="invented", value="stage-ish"), question=Q_CLOSED)
    assert "does not have" in str(e.value)


@pytest.mark.asyncio
async def test_an_answer_with_NO_value_is_refused() -> None:
    with pytest.raises(InterrogationRefusal) as e:
        await _run(reply(shape="extracted", value=None,
                         quotes=[{"chunk_id": C1, "quote": "內功"}]))
    assert "`not_stated` is the shape for having nothing to say" in str(e.value)


@pytest.mark.asyncio
async def test_the_same_span_cited_twice_is_refused_by_NAME(*_) -> None:
    """The DB's disjointness CHECK would refuse this downstream; refused here so
    the message names the model's mistake rather than the schema's."""
    with pytest.raises(InterrogationRefusal) as e:
        await _run(reply(shape="extracted", value=9, quotes=[
            {"chunk_id": C1, "quote": "內功分為九層"},
            {"chunk_id": C1, "quote": "內功分為九層"},
        ]))
    assert "one piece of evidence dressed as two" in str(e.value).lower()


# ── reading the model's reply ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_FENCED_json_reply_is_accepted() -> None:
    """A model that answers correctly inside a code fence has answered correctly;
    refusing it would be refusing the format rather than the content."""
    body = reply(shape="not_stated", not_stated_reason="contradicted")
    ev = await _run(f"Here is my answer:\n```json\n{body}\n```\nHope that helps.")
    assert ev.not_stated


@pytest.mark.asyncio
async def test_prose_around_a_bare_object_is_tolerated() -> None:
    body = reply(shape="not_stated", not_stated_reason="out_of_scope")
    ev = await _run(f"I think:\n{body}")
    assert ev.not_stated_reason == "out_of_scope"


@pytest.mark.asyncio
async def test_a_non_JSON_reply_is_refused_with_the_reply_quoted() -> None:
    with pytest.raises(InterrogationRefusal) as e:
        await _run("The book says nine tiers, I think.")
    assert "not JSON" in str(e.value)


@pytest.mark.asyncio
async def test_an_EMPTY_reply_is_refused() -> None:
    with pytest.raises(InterrogationRefusal) as e:
        await _run("   ")
    assert "returned nothing" in str(e.value)


# ── the provider boundary ───────────────────────────────────────────────────


def test_this_module_imports_no_provider_sdk_and_names_no_model() -> None:
    """Provider-gateway invariant, asserted rather than assumed. The seam is an
    injected ``CompleteFn``; ``app/generation/complete.py`` is the one place that
    talks to provider-registry."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app" / "gamegen" / "interrogate.py"
    text = src.read_text(encoding="utf-8")
    for banned in ("import openai", "import anthropic", "from openai", "gpt-4", "claude-",
                   "OPENAI_API_KEY", "httpx.post"):
        assert banned not in text, f"{banned!r} in interrogate.py"
    assert "complete_fn" in text, "the seam is injected"


# ── found by the live run ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_TRUNCATED_reply_is_named_as_truncation_not_bad_JSON() -> None:
    """**Found live, twice.** Replies that were well-formed JSON up to the point
    they stopped were reported as *"not JSON"*, which points the reader at the
    model's competence instead of at the token limit that caused it.

    Detected by brace DEPTH, not by *"is there a closing brace"*: the first
    version checked ``rfind("}") <= start`` and missed every truncation that
    stopped after a nested object closed — which is most of them, since ``quotes``
    is a list of objects."""
    cut = '{"shape": "extracted", "value": 12, "quotes": [{"chunk_id": "x", "quote": "y"}'
    with pytest.raises(InterrogationRefusal) as e:
        await _run(f"```json\n{cut}")
    assert "TRUNCATED" in str(e.value)
    assert "token limit" in str(e.value)


@pytest.mark.asyncio
async def test_genuinely_malformed_JSON_is_still_called_malformed() -> None:
    """The truncation branch must not swallow the real thing, or the message stops
    telling the two apart — which is the whole point of adding it."""
    with pytest.raises(InterrogationRefusal) as e:
        await _run("{{{ not json at all }}}")
    assert "TRUNCATED" not in str(e.value)


def test_the_prompt_asks_for_a_UNIQUE_quote_not_merely_a_short_one() -> None:
    """The prompt said *keep quotes SHORT* while :func:`locate` refuses an
    ambiguous one — two instructions in direct conflict, and the live run hit it:
    a model quoted 引氣 (2 characters) and it appeared many times."""
    p = build_prompt(Q_OPEN, CORPUS)
    assert "UNIQUE in its chunk" in p
    assert "extend it until" in p
    assert "SHORT" not in p, "the conflicting instruction is gone"


def test_the_prompt_forbids_joining_lines_or_adding_markup() -> None:
    """Live, a model answered with ``1. **引氣**\n2. **凝脈**`` — a list it had
    assembled itself, with emphasis the corpus does not contain. Correctly refused
    as a fabrication, and worth telling the model up front."""
    p = build_prompt(Q_OPEN, CORPUS)
    assert "do not join lines" in p
    assert "markup that is not there" in p
