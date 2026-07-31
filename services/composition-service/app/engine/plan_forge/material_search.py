"""Look for a MISSING planning kind in what the author already wrote — in their own words.

The board (`coverage.spec_coverage_board`) says which kinds the read recovered and which it did not.
This asks the next question: for a kind reported absent, **is it actually in the document and the
read simply missed it?** Measured on the author's real planning document (POC §6e Arm 1), that is the
common case — `planner_variables` came back absent and the search found it already written. The loop
must not ask an author for something they have already given you.

## Three constraints, each of them a measured result rather than a preference

- **Quote-first, verbatim.** The model returns LINES FROM THE DOCUMENT, not a paraphrase and not an
  answer. Anything it returns can then be checked against the source, which is what makes the whole
  step safe to show.
- **No yes/no gate.** The obvious shape — "is there a variable in here? if yes, find it" — was tried
  in three framings and each collapsed to a constant (all-yes or all-no); adding it cost recall and
  bought nothing. Ask for the lines directly.
- **No worked example.** A hand-written example in the prompt took recall to **zero** in a controlled
  arm, and a hand-written tie-break rule cost 0.26 F1 elsewhere in the same POC. The prompt says what
  the kind is and stops.

## And it does not conclude

`search_material` returns candidates for a human keep-or-drop. It is deliberately incapable of
settling anything, because the measured failure mode is that the retrieval is **good enough to show
and not good enough to trust**: when the loop offered three lines for `planner_variables`, all three
were tone and world rules, not state variables, and the author drops them in seconds (§6f). A step
that auto-concluded on those would have silently swallowed the real question.
"""

from __future__ import annotations

from app.packer.sanitize import neutralize

import json
import logging
import re
from typing import Any

from app.engine.llm_json import call_json

logger = logging.getLogger(__name__)

#: What each kind IS, in the plainest words available — no example, deliberately.
_KIND_MEANING: dict[str, str] = {
    "character_seed": "a person in the story: a name, who they are, what they want, how they relate "
                      "to others",
    "mechanics": "a rule of how this world works — a power system, a law, a constraint the story "
                 "obeys",
    "planner_variables": "something that CHANGES over the story and can be tracked as a value going "
                         "up or down — a resource, a stat, a level of trust, a countdown",
    "arc_overview": "the shape of the plot: an arc, a stretch of the story, a sequence of events",
    "writing_principles": "how the prose itself should be written — voice, tone, pacing, what to "
                          "avoid",
    "open_questions": "something the author has not decided yet, or has explicitly left open",
    "premise": "what this story IS in a sentence or two — the hook, the core idea, what it is about",
}

_SYSTEM = (
    "You find lines in an author's planning document. You do not write, summarise, judge or "
    "invent. Every string you return must be COPIED EXACTLY from the document, character for "
    "character. If the document contains nothing of the kind asked for, return an empty list — "
    "that is a correct and expected answer."
)

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "quotes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quote": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["quote"],
            },
        },
    },
    "required": ["quotes"],
}

#: Above this a "quote" is a paraphrase of a whole section, not a line — and it stops being something
#: an author can judge at a glance, which is the entire point of the review surface.
_QUOTE_MAX_CHARS = 400
_DEFAULT_MAX = 5


def kinds_worth_searching(board: dict[str, Any]) -> list[dict[str, str]]:
    """Everything the read did not recover — `absent` AND `unknown` — each tagged with which it was.

    **This originally returned `absent` only, and that was backwards.** The reasoning was "an
    `unknown` kind is probably sitting in a section the matcher could not place, so do not go looking"
    — which inverts itself the moment you write it down: if the material is probably there, finding it
    is the whole job. The search reads the RAW document, not the classified sections, so it is exactly
    the instrument that resolves `unknown` into either "here, you already wrote this" or "genuinely
    not there".

    Caught by a live run on the author's real document, where all three empty kinds are `unknown` and
    the loop consequently searched **nothing** — on the very document whose measured result (POC §6e
    Arm 1) is that the absent kind was *already written*. The unit test did not catch it because it
    asserted the same wrong contract.

    What must never happen without a search is **asking**. That belongs to the ask step, and this is
    why each entry carries `status`: a candidate found under `absent` answers a confident gap, while
    one found under `unknown` also tells the author their document was read incompletely.
    """
    return (
        [{"kind": k, "status": "absent"} for k in (board.get("absent") or [])]
        + [{"kind": k, "status": "unknown"} for k in (board.get("unknown") or [])]
    )


def _normalize(text: str) -> str:
    """Whitespace-flattened and casefolded — the only differences a grounding check should forgive."""
    return re.sub(r"\s+", " ", text).strip().casefold()


def _ground(quote: str, haystack_norm: str) -> bool:
    q = _normalize(quote)
    return bool(q) and q in haystack_norm


async def search_material(
    llm: Any,
    *,
    user_id: str,
    model_source: str,
    model_ref: str,
    document_markdown: str,
    kind: str,
    max_candidates: int = _DEFAULT_MAX,
    seed: int | None = 7,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Candidate lines from the author's own document for one absent `kind`.

    Returns `{kind, candidates: [{quote, why}], dropped_ungrounded, note}`. Never raises for a model
    problem — a failed search reports itself and offers nothing, because "we could not look" and
    "there is nothing there" must not look the same to whatever renders this.
    """
    meaning = _KIND_MEANING.get(kind)
    if meaning is None:
        # A kind outside the closed set is a caller bug, and returning empty would hide it as "the
        # document has none of that" — the silent-no-op shape.
        raise ValueError(f"unknown planning kind {kind!r}; expected one of {sorted(_KIND_MEANING)}")
    if not document_markdown.strip():
        return {"kind": kind, "candidates": [], "dropped_ungrounded": 0,
                "note": "no source document to search"}

    # D-INJECTION-COVERAGE (2026-07-31): the document is an author's own file or an
    # IMPORT — arbitrary text — and it goes straight into a prompt.
    # `injection-coverage-lint` has flagged this module all along; it simply never ran.
    #
    # The care needed here: the prompt asks the model to copy lines VERBATIM, and the
    # grounding gate below re-matches each quote against the document. Neutralising only
    # the prompt side would make every quote fail to ground — a security fix that
    # silently breaks the feature. The SAME transformed text feeds both, so the two stay
    # in lockstep by construction rather than by comment.
    _safe_doc = neutralize(document_markdown)
    user = (
        f"Below is an author's planning document.\n\n"
        f"Find up to {max_candidates} lines in it that are: {meaning}.\n\n"
        f"Copy each line EXACTLY as it appears. Do not rewrite, translate or shorten it. "
        f"If there are none, return an empty list.\n\n"
        f"--- DOCUMENT ---\n{_safe_doc}\n--- END ---"
    )

    raw = await call_json(
        llm, user_id=user_id, model_source=model_source, model_ref=model_ref,
        messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
        max_tokens=1500,
        job_meta={"usage_purpose": "plan_forge", "extractor": f"material_search:{kind}"},
        # BARE schema: `call_json` wraps it with `json_format(schema_name, ...)` itself. Passing a
        # pre-wrapped one nests `json_schema` inside `json_schema`, the provider rejects it, and the
        # call silently falls back to free-form — which the mock-based tests cannot see, because a
        # stub ignores the input shape entirely.
        schema=_SCHEMA, schema_name=f"material_{kind}",
        temperature=0.2, seed=seed, trace_id=trace_id,
    )
    if not raw:
        return {"kind": kind, "candidates": [], "dropped_ungrounded": 0,
                "note": "the search did not complete — this is NOT evidence the document lacks it"}
    try:
        parsed = json.loads(raw)
        quotes = parsed.get("quotes") or []
    except (json.JSONDecodeError, AttributeError):
        logger.warning("material_search %s: unparseable response (%d chars)", kind, len(raw))
        return {"kind": kind, "candidates": [], "dropped_ungrounded": 0,
                "note": "the search returned nothing readable — this is NOT evidence the document "
                        "lacks it"}

    # THE GROUNDING GATE. A quote that is not in the document is an invention, and an invented line
    # shown to the author under "here is what you already wrote" is worse than showing nothing: they
    # would keep it, and it would enter their plan as their own material. Dropped, never rendered —
    # and counted, so a search that invented everything cannot pass for a search that found nothing.
    hay = _normalize(_safe_doc)  # the same transform the model was shown
    candidates: list[dict[str, str]] = []
    dropped = 0
    seen: set[str] = set()
    for item in quotes:
        if not isinstance(item, dict):
            dropped += 1
            continue
        quote = str(item.get("quote") or "").strip()[:_QUOTE_MAX_CHARS]
        if not quote or not _ground(quote, hay):
            dropped += 1
            continue
        key = _normalize(quote)
        if key in seen:
            continue
        seen.add(key)
        candidates.append({"quote": quote, "why": str(item.get("why") or "").strip()[:300]})
        if len(candidates) >= max_candidates:
            break

    note = ""
    if dropped and not candidates:
        note = (f"every line the search returned ({dropped}) was absent from the document, so all "
                f"were dropped as invented — treat this as a FAILED search, not an empty one")
    elif dropped:
        note = f"{dropped} returned line(s) were not in the document and were dropped as invented"
    return {"kind": kind, "candidates": candidates, "dropped_ungrounded": dropped, "note": note}
