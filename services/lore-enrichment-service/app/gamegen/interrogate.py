"""S1→S2 — the interrogation. **The one stage where a model runs.**

Doc 39 §4. A sealed corpus plus the brief's questions become *proposed* answers,
each carrying either evidence (a span in the corpus) or an admission that it was
invented. Nothing here is trusted; everything is verified before it can be stored.

## The design decision this stage turns on: the model never supplies an offset

The obvious shape is to ask for ``[start, end)`` and store it. It is also wrong
twice over. Models cannot count characters — over CJK the offsets would be wrong
almost every time, and a pipeline whose evidence layer fails constantly gets its
evidence layer switched off. And worse, an offset the model supplies is *another
self-reported input*: the same class already removed six times in this pipeline
(``chunk_count``, ``merkle_root``, ``schema_fingerprint``, ``question_paths``,
``policy_hash``, the pin's parent).

So the model emits a **chunk id and a short ANCHOR** — 4-15 characters, just
enough to point. The span is **derived** by finding that anchor in the sealed text
and then **widening it to the sentence** out of the source. Which makes
fabrication structural rather than detected:

> **a quote that is not in the chunk cannot be given a span at all.**

There is no code path that stores an unverified citation, because a citation
without an offset is not a citation and the only source of offsets is the corpus.

**Anchors replaced long quotes after three measured runs.** Asking for a verbatim
quote asks a model to do the thing it is worst at — transcription — and the numbers
said so: across three end-to-end runs the dominant refusal was a quote that
abridged the middle of a passage or reformatted a list, and eight fixes moved the
answered count from 4 to 5 to 4 to 3. Pointing is a task a model is good at. The
evidence is *better* too: the stored citation is a whole sentence lifted from the
source, not the fragment a model chose to copy.

## What the model is allowed to say

Three shapes, and no fourth (`PGN-A3`, `PGN-A4`):

``extracted``   a value the book states, with quotes to prove it
``invented``    a value the model proposes, marked, no evidence claimed
``not_stated``  the corpus does not say, with a reason from the closed set

A claim of ``extracted`` whose quotes do not verify becomes a **refusal**, not a
silent downgrade to ``invented``. Downgrading would be laundering run backwards:
the model would learn that claiming evidence is free.

## Retrieval, and its stated limit

Every chunk of the sealed corpus is shown, with its id. At POC scale (§10's
fixture is ~12 KB) that is a few thousand tokens and it is *exhaustive* — no
retrieval step can drop the one paragraph that answers the question. A corpus
large enough to need selection would need a retrieval stage here, and that stage
would become a place evidence can go missing without anyone noticing;
:func:`build_prompt` refuses above :data:`MAX_PROMPT_CHUNKS` rather than silently
truncating, so the day that limit is reached is a loud one.

## Standards

Non-agentic single-shot generation, so the **MCP-first invariant does not apply**
(it exempts LLM *pipelines*); the **provider-gateway invariant** does, and is
honoured by taking an injected ``CompleteFn`` — the seam
``app/generation/complete.py`` binds to provider-registry's ``/internal/llm/stream``.
No provider SDK, no model name: the model is a ``model_ref`` on the context.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Sequence

from app.gamegen.answer_hash import NOT_STATED_REASONS, AnswerEvidence, Citation
from app.gamegen.brief import Question

__all__ = [
    "MAX_PROMPT_CHUNKS",
    "expand_to_sentence",
    "Chunk",
    "InterrogationRefusal",
    "Proposal",
    "build_prompt",
    "interrogate",
    "parse_proposal",
]

#: Above this the exhaustive prompt stops being honest and a retrieval stage is
#: needed. Refused rather than truncated: silent truncation is how the paragraph
#: that answered the question disappears with every gate still green.
MAX_PROMPT_CHUNKS = 200

SHAPES = ("extracted", "invented", "not_stated")


class InterrogationRefusal(Exception):
    """The model's output cannot become an answer, and the message says why."""


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    content: str


@dataclass(frozen=True)
class Proposal:
    """What the model said, **before** anything is checked."""

    shape: str
    value: Any = None
    quotes: tuple[tuple[str, str], ...] = ()      # (chunk_id, quote)
    proposed_text: str | None = None
    not_stated_reason: str | None = None


_PROMPT = """\
You are answering ONE question about a book, for a game-rules pipeline.

You may answer in exactly one of three shapes:

1. "extracted" - the book states this. Give the value AND one or more ANCHORS.

   An ANCHOR is a SHORT run of 4-15 characters copied EXACTLY from a passage
   below - just enough to point at the place that says it. You are pointing, not
   transcribing: the pipeline reads the full sentence around your anchor out of
   the source itself, so a short anchor gives BETTER evidence than a long quote
   and is far easier to copy without a slip.

   * copy it character-for-character from ONE continuous run - no joining lines,
     no renumbering, no leaving words out of the middle
   * it must appear ONLY ONCE in that chunk; if it repeats, extend it a little
   * give the bare chunk_id UUID, exactly as printed after "chunk_id:"

   An anchor that does not appear in the chunk is REFUSED.
2. "invented"  - the book does not state it, and you propose a value anyway.
   Say so. This is legitimate and it is recorded as your proposal, not the
   book's. Do not attach quotes.
3. "not_stated" - the book does not say, and you are not proposing. Give a
   reason from exactly this set: {reasons}.

QUESTION ({question_id}): {ask}
ANSWER SHAPE: {answer_shape}{options}

Reply with ONE JSON object and nothing else. "shape" is ONE OF THE THREE WORDS
above - it is not the answer; the answer goes in "value".
{{"shape": "extracted|invented|not_stated",
  "value": <the answer, or null for not_stated>,
  "quotes": [{{"chunk_id": "...", "quote": "<4-15 char anchor>"}}],
  "proposed_text": "<your reasoning, only for invented>",
  "not_stated_reason": "<only for not_stated>"}}

PASSAGES:
{passages}
"""


def build_prompt(question: Question, chunks: Sequence[Chunk]) -> str:
    """The exhaustive prompt. See the module docstring on retrieval's limit."""
    if not chunks:
        raise InterrogationRefusal(
            "no corpus chunks to interrogate. An empty corpus cannot support a citation, "
            "so every answer would be `invented` and the run would look like a book that "
            "says nothing rather than a corpus that was never ingested."
        )
    if len(chunks) > MAX_PROMPT_CHUNKS:
        raise InterrogationRefusal(
            f"{len(chunks)} chunks exceeds MAX_PROMPT_CHUNKS ({MAX_PROMPT_CHUNKS}). Refused "
            f"rather than truncated: silent truncation is how the paragraph that answered "
            f"the question disappears with every gate still green. A corpus this size needs "
            f"a retrieval stage, and that stage needs its own accountability."
        )
    # `chunk_id: <uuid>` on its own line, NOT `[chunk <uuid>]`. **Found by the
    # first live run:** the bracketed form made a model answer with the literal
    # `"chunk 0191f2a0-…"` as the id — it copied the label along with the value,
    # and the citation was refused for naming a chunk that does not exist. The
    # prompt invited that, so the prompt is what changed.
    passages = "\n\n".join(
        f"chunk_id: {c.chunk_id}\ntext:\n{c.content}" for c in chunks
    )
    options = ""
    if question.options:
        # `PGN-A13` — a closed set is shown as its members, so the model cannot
        # answer "stage-ish" and the reviewer never sees a free string.
        options = "\nCHOOSE EXACTLY ONE OF: " + ", ".join(question.options)
    return _PROMPT.format(
        reasons=", ".join(sorted(NOT_STATED_REASONS)),
        question_id=question.id,
        ask=question.ask,
        answer_shape=question.answer_shape,
        options=options,
        passages=passages,
    )


def parse_proposal(raw: str, question: Question) -> Proposal:
    """Read the model's JSON, and refuse anything that is not one of the shapes.

    Tolerant of the usual wrappers (a fenced block, prose either side) because a
    model that answers correctly inside a code fence has answered correctly.
    Intolerant of everything else: a shape outside the closed set, a closed-set
    answer outside its options, or a claim of evidence with no quotes.
    """
    obj = _extract_json_object(raw)

    shape = str(obj.get("shape", "")).strip().lower()
    if shape not in SHAPES:
        raise InterrogationRefusal(
            f"the model answered with shape {shape!r}, which is not one of {list(SHAPES)}. "
            f"There is no fourth shape: every answer is evidence, an admitted invention, "
            f"or an accountable silence."
        )

    if shape == "not_stated":
        reason = obj.get("not_stated_reason")
        if reason not in NOT_STATED_REASONS:
            raise InterrogationRefusal(
                f"not_stated with reason {reason!r}, which is not in "
                f"{sorted(NOT_STATED_REASONS)}. `PGN-A4` keeps 'the book does not say' one "
                f"click AND accountable; a free-text reason is neither."
            )
        return Proposal(shape=shape, not_stated_reason=reason)

    value = obj.get("value")
    if value is None or value == "":
        raise InterrogationRefusal(
            f"shape {shape!r} with no value. An answer that states nothing is not an "
            f"answer, and `not_stated` is the shape for having nothing to say."
        )
    if question.options and isinstance(value, str) and value not in question.options:
        raise InterrogationRefusal(
            f"{value!r} is not one of {list(question.options)}. `PGN-A13`: a closed-set "
            f"question's options are generated from the engine's enum, so an answer "
            f"outside them names a variant the engine does not have."
        )

    if shape == "invented":
        return Proposal(shape=shape, value=value,
                        proposed_text=str(obj.get("proposed_text") or "(no rationale given)"))

    quotes = tuple(
        (str(q.get("chunk_id", "")), str(q.get("quote", "")))
        for q in (obj.get("quotes") or [])
        if isinstance(q, Mapping)
    )
    if not quotes:
        raise InterrogationRefusal(
            "the model claimed `extracted` and attached no quotes. Refused rather than "
            "recorded as `invented`: downgrading a false evidence claim teaches that "
            "claiming evidence is free, which is laundering run backwards."
        )
    return Proposal(shape=shape, value=value, quotes=quotes)


#: Punctuation a model routinely re-renders. **NFKC does not fold these** — it
#: leaves 。 as 。 — so the shared normalisation spine is necessary and not
#: sufficient here.
#:
#: **Measured, not guessed.** The first end-to-end run against a real model
#: refused 4 of 7 failures on this alone: the corpus says 氣初入脈。 and the model
#: writes 氣初入脈. — one character, ASCII full stop for ideographic. Every
#: citation touching a sentence end was refused as a fabrication.
_PUNCT_FOLD = {
    "。": ".", "，": ",", "、": ",", "；": ";", "：": ":",
    "！": "!", "？": "?", "（": "(", "）": ")",
    "「": '"', "」": '"', "『": '"', "』": '"',
    "《": '"', "》": '"', "—": "-", "–": "-", "－": "-",
    "‘": "'", "’": "'", "“": '"', "”": '"',
}


#: Characters that carry FORMATTING rather than meaning, ignored when matching.
#: A model reading a markdown table quotes the cell and drops the pipes; one
#: reading a bolded term quotes the term. Ignoring these at match time is safe —
#: they cannot make two different sentences equal — and it is where the tolerance
#: belongs, because being wrong here costs a variant rather than a damaged corpus.
_FOLD_IGNORE = set("*_`|#>")


def _fold(text: str) -> tuple[str, list[int]]:
    """A comparison projection of ``text``, plus a map back to original offsets.

    Folds NFKC, then CJK punctuation, then drops whitespace entirely — models
    reflow lines and renumber lists, and none of that changes what the book says.
    The returned list maps each folded character to the index it came from, which
    is what makes the recovered span point at the ORIGINAL text.
    """
    out: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(text):
        if ch.isspace() or ch in _FOLD_IGNORE:
            continue
        folded = _PUNCT_FOLD.get(ch) or unicodedata.normalize("NFKC", ch)
        for c in folded:
            out.append(c)
            idx.append(i)
    return "".join(out), idx


#: Sentence terminators, CJK and ASCII. A newline ends a sentence too — the corpus
#: carries list entries and table rows, where the line IS the unit.
_SENTENCE_END = set("。！？!?\n")


def expand_to_sentence(content: str, start: int, end: int) -> tuple[int, int]:
    """Widen an anchor span to the sentence containing it.

    **This is what makes a short anchor better evidence than a long quote.** The
    model points at 4-15 characters it can copy without slipping; the pipeline
    reads the whole sentence out of the source. The reviewer sees a complete
    statement from the corpus, and the model never had to transcribe it.

    Deterministic and source-only: no model output reaches this, so the widened
    span is as trustworthy as the anchor that seeded it.
    """
    s = start
    while s > 0 and content[s - 1] not in _SENTENCE_END:
        s -= 1
    e = end
    while e < len(content) and content[e - 1] not in _SENTENCE_END:
        e += 1
    # Trim leading whitespace the widening swept up; the trailing terminator stays,
    # because a sentence without its full stop reads as a fragment.
    while s < e and content[s].isspace():
        s += 1
    return s, max(e, end)


def locate(chunks: Mapping[str, str], chunk_id: str, quote: str) -> tuple[int, int]:
    """Derive the span by finding ``quote`` in the sealed chunk.

    **The model never supplies an offset**, and — after the first real run — it
    does not supply the stored quote either. Matching happens on a folded
    projection (punctuation rendered differently, whitespace reflowed); the span
    that comes back indexes the **original** text, so what gets stored is always
    the corpus's own characters. The model's rendition is discarded.

    That makes the check *stronger*, not looser. Before, a model that wrote a
    correct quote with an ASCII full stop was recorded as a fabricator; now the
    stored evidence is the source's bytes in every case, and a quote whose
    *characters* differ still fails. Folding punctuation and whitespace cannot
    make two different sentences match — it only stops one sentence from failing
    to match itself.

    :raises InterrogationRefusal: quote absent, chunk unknown, or the quote
        appearing more than once (ambiguous — two different passages could be
        meant, and picking the first would silently choose for the reviewer).
    """
    content = chunks.get(chunk_id)
    if content is None:
        raise InterrogationRefusal(
            f"the model cited chunk {chunk_id!r}, which is not in the sealed corpus. A "
            f"citation to a chunk that was never shown is a citation to nothing."
        )
    if not quote:
        raise InterrogationRefusal(f"an empty quote for chunk {chunk_id}")

    # Exact first: unambiguous, and the common case once a model copies well.
    first = content.find(quote)
    if first >= 0:
        if content.find(quote, first + 1) >= 0:
            raise InterrogationRefusal(
                f"the quote {quote[:40]!r} appears more than once in chunk {chunk_id}. "
                f"Refused rather than resolved to the first: two different passages "
                f"could be meant, and choosing one would decide for the reviewer."
            )
        return first, first + len(quote)

    fc, fmap = _fold(content)
    fq, _ = _fold(quote)
    if not fq:
        raise InterrogationRefusal(
            f"the quote for chunk {chunk_id} is only punctuation and whitespace, which "
            f"cites nothing."
        )
    hit = fc.find(fq)
    if hit < 0:
        raise InterrogationRefusal(
            f"the quote {quote[:40]!r} does not appear in chunk {chunk_id}, even allowing "
            f"for punctuation and line breaks. THE CORPUS DOES NOT SAY THIS. Refused "
            f"rather than stored with a guessed span: a citation whose characters are "
            f"not in the source is the fabrication `PGN-A14` exists to make impossible."
        )
    if fc.find(fq, hit + 1) >= 0:
        raise InterrogationRefusal(
            f"the quote {quote[:40]!r} appears more than once in chunk {chunk_id}. "
            f"Refused rather than resolved to the first: two different passages could be "
            f"meant, and choosing one would decide for the reviewer."
        )
    # Map the folded span back to the ORIGINAL text. `end` is the character after
    # the last matched one, so a trailing 。 the model wrote as . is included.
    start = fmap[hit]
    end = fmap[hit + len(fq) - 1] + 1
    return start, end


def to_evidence(
    *, proposal: Proposal, question: Question, target_ref: str,
    chunks: Mapping[str, str], seal_id: str,
) -> AnswerEvidence:
    """Turn a parsed proposal into storable evidence, deriving every span.

    The result is exactly what `S2` stores — and `answer_hash` validates it again
    on the way in, so a shape this function got wrong cannot reach the table.
    """
    if proposal.shape == "not_stated":
        return AnswerEvidence(
            question_id=question.id, target_ref=target_ref, value=None, says=(),
            proposed_text=None, not_stated=True,
            not_stated_reason=proposal.not_stated_reason,
            verified_against_seal_id=None,
        )
    if proposal.shape == "invented":
        return AnswerEvidence(
            question_id=question.id, target_ref=target_ref, value=proposal.value,
            says=(), proposed_text=proposal.proposed_text, not_stated=False,
            not_stated_reason=None, verified_against_seal_id=None,
        )

    says: list[Citation] = []
    seen: set[tuple[str, int, int]] = set()
    for chunk_id, quote in proposal.quotes:
        start, end = locate(chunks, chunk_id, quote)
        start, end = expand_to_sentence(chunks[chunk_id], start, end)
        key = (chunk_id, start, end)
        if key in seen:
            # The same span twice is one piece of evidence dressed as two, and
            # `says_wellformed`'s disjointness CHECK would refuse it downstream —
            # refused here so the message names the model's mistake, not the DB's.
            raise InterrogationRefusal(
                f"the model cited the same span [{start}, {end}) of chunk {chunk_id} "
                f"twice. One piece of evidence dressed as two."
            )
        seen.add(key)
        # **The corpus's own characters, not the model's.** `locate` matched on a
        # folded projection, so the model may have written `.` where the book
        # writes 。 — storing its rendition would put text in the evidence column
        # that the source does not contain, and `verify_citation` would then
        # refuse the pipeline's own output.
        says.append(Citation(chunk_id=chunk_id, start=start, end=end,
                             quote=chunks[chunk_id][start:end]))

    return AnswerEvidence(
        question_id=question.id, target_ref=target_ref, value=proposal.value,
        says=tuple(says), proposed_text=None, not_stated=False,
        not_stated_reason=None, verified_against_seal_id=seal_id,
    )


async def interrogate(
    *,
    question: Question,
    target_ref: str,
    chunks: Sequence[Chunk],
    seal_id: str,
    complete_fn: Callable[..., Awaitable[str]],
    context: Any,
) -> AnswerEvidence:
    """Ask one question of the corpus and return **verified** evidence.

    ``complete_fn`` is the injected provider seam
    (``app/generation/complete.py``), so this module never imports a provider SDK
    and never names a model — the model is a ``model_ref`` on ``context``.
    """
    prompt = build_prompt(question, chunks)
    raw = await complete_fn(prompt, context)
    proposal = parse_proposal(raw, question)
    return to_evidence(
        proposal=proposal, question=question, target_ref=target_ref,
        chunks={c.chunk_id: c.content for c in chunks}, seal_id=seal_id,
    )


_FENCE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL)


def _unclosed(text: str) -> bool:
    """True when ``text`` opens more braces than it closes — i.e. the reply stopped
    mid-object.

    String-aware, because a `}` inside a quoted Chinese passage is not a brace.
    Cheap and sufficient: this only has to tell *truncated* from *malformed* so
    the error message points at the right cause.
    """
    depth = 0
    in_str = False
    escaped = False
    for ch in text:
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
    return depth > 0 or in_str


def _extract_json_object(raw: str) -> dict:
    """Tolerant JSON read. Mirrors the shape `llm_judge` and `entity_recovery`
    already use in this repo — a model that answers correctly inside a code fence
    has answered correctly, and refusing that would be refusing the format rather
    than the content."""
    if not raw or not raw.strip():
        raise InterrogationRefusal("the model returned nothing")
    text = raw.strip()
    m = _FENCE.search(text)
    if m:
        text = m.group(1).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0:
            raise InterrogationRefusal(f"the model's reply is not JSON: {raw[:200]!r}")
        if _unclosed(text[start:]):
            # **Found by the live run, twice.** Replies that were plainly
            # well-formed JSON up to the point they stopped were reported as "not
            # JSON", which points the reader at the model's competence instead of
            # at the token limit that actually caused it.
            #
            # Detected by brace DEPTH, not by "is there a closing brace": the
            # first version checked `rfind("}") <= start` and missed every
            # truncation that happened to stop after a nested object closed —
            # which is most of them, since `quotes` is a list of objects.
            raise InterrogationRefusal(
                f"the model's reply was TRUNCATED mid-object - the JSON opens and never "
                f"closes, which is a token limit rather than a malformed answer. Reply "
                f"began: {raw[:160]!r}"
            ) from None
        try:
            obj = json.loads(text[start : end + 1])
        except json.JSONDecodeError as e:
            raise InterrogationRefusal(
                f"the model's reply is not JSON: {raw[:200]!r}"
            ) from e
    if not isinstance(obj, dict):
        raise InterrogationRefusal(f"the model returned {type(obj).__name__}, not an object")
    return obj
