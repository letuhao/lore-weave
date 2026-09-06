"""The §4 "speak plainly" guard must translate WORDS, never half-translate a NAME.

🔴 **MEASURED 2026-08-25, 5 of 5 runs (`docs/eval/toolloop/2026-08-14/c-regwf4.json`).** Asked
what workflows the studio surface offers, every reply named the right six and then presented two
of them as `story bible-bootstrap` and `element-triage`. Neither name exists. The user cannot
type them and a follow-up `workflow_load(slug)` cannot resolve them.

The cause is that `_JARGON_SUBS` are word-boundary regexes and `-` is a word boundary, so a rule
meant for prose fired inside an identifier. The guard's own comment already reasons about not
mangling ordinary prose (`kind`/`tool`/`spec` are excluded for that reason); names were simply
never the case it was asked about.

**Translating a whole name is a deliberate relabel and MUST keep working** — the
`vision-to-book` rule matches its entire token and is how the reader hears "book-building". What
is forbidden is rewriting PART of a hyphenated name, which yields a word-salad identifier.
"""
from __future__ import annotations

import json

from app.services.stream_events import AgUiEmitter, scrub_jargon

# Real workflow slugs from `loreweave_agent_registry.workflows`. The first three contain a §4
# jargon word; the last two contain none and are here so a regression that simply disabled the
# guard cannot pass this file.
SLUGS_WITH_JARGON_WORDS = ["glossary-bootstrap", "entity-triage", "canon-check"]


def test_a_slug_containing_a_jargon_word_survives_the_guard_intact():
    for slug in SLUGS_WITH_JARGON_WORDS:
        assert scrub_jargon(slug) == slug, (
            f"the guard rewrote the identifier {slug!r} into {scrub_jargon(slug)!r}, which is "
            f"not a workflow that exists"
        )


def test_the_deliberate_whole_name_relabel_still_fires():
    # vision-to-book is relabelled ON PURPOSE — the rule matches the entire token, so neither
    # neighbour is a hyphen and the part-of-a-name guard correctly leaves it alone.
    assert scrub_jargon("vision-to-book") == "book-building"


def test_the_guard_still_translates_the_words_it_exists_for():
    # If this file could pass by neutering the guard it would be worthless.
    assert scrub_jargon("Set up the glossary for this book") == (
        "Set up the story bible for this book")
    assert scrub_jargon("I will extract the entities") == "I will extract the elements"
    assert scrub_jargon("the knowledge graph") == "the connection map"
    assert scrub_jargon("Glossary") == "Story bible"


def _stream(text: str) -> str:
    """Feed `text` through the real emitter ONE CHARACTER at a time and return what a client
    would concatenate. One char per delta is the worst case for the hold-back buffer."""
    em = AgUiEmitter(thread_id="t", message_id="m")
    lines: list[str] = []
    for ch in text:
        lines += em.text_delta(ch)
    lines += em._close_open()
    out = []
    for line in lines:
        payload = json.loads(line.removeprefix("data: ").strip())
        if payload.get("type") == "TEXT_MESSAGE_CONTENT":
            out.append(payload["delta"])
    return "".join(out)


def test_a_slug_split_across_deltas_still_arrives_intact():
    # The scrubber runs per-delta on a hold-back buffer, so guarding the function alone would
    # not be enough if a name could reach it in pieces. It cannot: the buffer holds a trailing
    # partial word until whitespace, so the whole hyphenated token is scrubbed at once. This
    # pins that, because the fix DEPENDS on it.
    body = "Try the `glossary-bootstrap` recipe, or `entity-triage` if it is messy."
    assert _stream(body) == body


def test_streaming_still_translates_prose_split_across_deltas():
    assert _stream("Set up the glossary now") == "Set up the story bible now"
