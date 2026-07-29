"""Between finding material and asking for it: the step where the AUTHOR decides.

`coverage.spec_coverage_board` says what the read recovered. `material_search` looks for the rest in
the author's own words. This assembles both into something a person can act on, and — only after they
have — works out what is actually still worth asking.

## Why there is a review step at all, and why it is not optional

Measured (POC §6f). The loop's earlier version concluded by itself: it searched for the one kind it
thought was missing, found three lines, and treated them as the answer. **All three were wrong** —
tone and world rules, not state variables — so it silently swallowed a question it should have asked.
The retrieval is *good enough to show and not good enough to trust*, and the only thing that
distinguishes those two is a human looking at it.

Confirmed again on first contact with the second corpus: the search offered one line for BOTH
`mechanics` and `planner_variables`. Not an invention — over-retrieval, which no grounding gate can
catch because the line is genuinely in the document. Only the author knows which slot it belongs in.

## Three buckets, not two

The obvious shape is "found it" / "ask for it". That loses the case that matters most:

- **`review`** — candidates were found; the author keeps or drops them.
- **`ask`** — the search ran and honestly found nothing, so the material is not in the document.
- **`unavailable`** — the search could not run or returned only inventions. This must NOT become a
  question: asking an author to write something they may already have written, because a model call
  failed, is the failure this whole cycle has been removing. It is reported as its own state.

`unavailable` collapsing into `ask` is the same bug as `absent` collapsing into `unknown` one layer
up, and it is worth the extra bucket for exactly the same reason.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from app.engine.plan_forge.coverage import spec_coverage_board
from app.engine.plan_forge.material_search import kinds_worth_searching, search_material

logger = logging.getLogger(__name__)

#: One question per kind. Plain, and deliberately without an example — the same measured reason the
#: search prompt has none: a hand-written example took recall to zero in a controlled arm, and an
#: example in a QUESTION also tells the author what answer is expected, which is worse than useless
#: when the point is to learn what THEY think.
_QUESTION: dict[str, str] = {
    "character_seed": "Who is in this story? A name and a sentence about each is enough to start.",
    "mechanics": "What are the rules of this world — the power system, the law, the constraint the "
                 "story has to obey?",
    "planner_variables": "What changes over the course of this story that you would want tracked as "
                         "it goes up or down?",
    "arc_overview": "What is the shape of the plot — the arcs, or the stretch you can see so far?",
    "writing_principles": "How should the prose itself read? Voice, pacing, anything you never want "
                          "to see on the page.",
    "open_questions": "What have you not decided yet?",
    "premise": "In a sentence or two, what is this story about?",
}


def question_for(kind: str) -> str:
    q = _QUESTION.get(kind)
    if q is None:
        raise ValueError(f"no question for planning kind {kind!r}")
    return q


async def find_missing_material(
    llm: Any,
    *,
    user_id: str,
    model_source: str,
    model_ref: str,
    spec: dict[str, Any],
    document_markdown: str,
    max_candidates: int = 5,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """The board, plus a grounded search for everything it did not recover, sorted into the three
    buckets above.

    Searches run concurrently: they are independent, one per kind, and a serial loop over six kinds
    on a local model is a minute of wall-clock for no reason. A search that raises is caught per-kind
    and lands in `unavailable` — one kind failing must not lose the other five.
    """
    board = spec_coverage_board(spec)
    targets = kinds_worth_searching(board)

    async def _one(entry: dict[str, str]) -> tuple[dict[str, str], dict[str, Any] | None]:
        try:
            return entry, await search_material(
                llm, user_id=user_id, model_source=model_source, model_ref=model_ref,
                document_markdown=document_markdown, kind=entry["kind"],
                max_candidates=max_candidates, trace_id=trace_id,
            )
        except Exception:
            logger.warning("find_missing_material: search failed for %s", entry["kind"],
                           exc_info=True)
            return entry, None

    results = await asyncio.gather(*(_one(e) for e in targets)) if targets else []

    review: list[dict[str, Any]] = []
    ask: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    for entry, out in results:
        kind = entry["kind"]
        if out is None:
            unavailable.append({"kind": kind, "status": entry["status"],
                                "reason": "the search raised"})
            continue
        if out["candidates"]:
            review.append({
                "kind": kind, "status": entry["status"],
                "candidates": out["candidates"],
                # Carried so a reviewer can see the search was partly inventing even when some
                # candidates survived — a list that looks clean can still come from a bad call.
                "dropped_ungrounded": out["dropped_ungrounded"],
                "note": out["note"],
            })
        elif out["note"]:
            # A note with no candidates means the search did not honestly conclude "nothing here":
            # it failed to complete, returned nothing readable, or invented everything it returned.
            unavailable.append({"kind": kind, "status": entry["status"], "reason": out["note"]})
        else:
            ask.append({"kind": kind, "status": entry["status"], "question": question_for(kind)})

    return {
        "version": 1,
        "recovered": board["recovered"],
        "review": review,
        "ask": ask,
        "unavailable": unavailable,
        "read": board["read"],
    }


#: Kinds whose spec slot is a plain list of strings, so a kept line lands there AS the author wrote
#: it. Everything else needs a structured object (`{code, name}`, `{id, title}`) that a raw line is
#: not, and guessing that structure is how a quote stops being a quote.
_DIRECT_SLOT: dict[str, tuple[str, str]] = {
    "writing_principles": ("charter", "style_constraints"),
    "open_questions": ("meta", "open_questions"),
    "premise": ("charter", "premise_notes"),
}

#: The four structured kinds, and what a kept line is missing to become a row there.
#:
#: Reading the schemas back, every one of them is short **exactly one field a human has to decide**:
#: a LABEL. `character_seed` needs `{id, name}`, `mechanics` `{name, rules}`, `planner_variables`
#: `{code, name}`, `arc_overview` `{id, title}` — and in each case the quote supplies the body while
#: only the name/title requires judgement. The identity (`id`/`code`) is machine-owned and derived
#: from the label, which is bookkeeping, not a guess about meaning.
#:
#: So the honest fix is to ASK for that one field, never to infer it. With a label the line lands
#: structurally; without one it still becomes an author note — which now genuinely reaches the pass
#: prompts (`PassContext.grounding`), so the fallback is a real outcome rather than a shrug.
#:
#: `(parent, key, label_field, body_field, id_field)`
_LABELLED_SLOT: dict[str, tuple[str, str, str, str, str]] = {
    "character_seed": ("layers", "characters", "name", "baseline_notes", "id"),
    "mechanics": ("layers", "mechanics", "name", "rules", "id"),
    "planner_variables": ("layers", "variables", "name", "transition_rules", "code"),
    "arc_overview": ("", "arcs", "title", "summary", "id"),
}

#: `rules` / `transition_rules` are string ARRAYS in the schema; the others are plain strings.
_LIST_BODY = {"rules", "transition_rules"}


def _slug(label: str, *, upper: bool = False) -> str:
    """A stable identity from the author's label. Machine bookkeeping, not interpretation."""
    s = re.sub(r"[^\w]+", "_", label.strip(), flags=re.UNICODE).strip("_")
    s = s[:48] or "item"
    return s.upper() if upper else s.lower()


def apply_kept_material(
    spec: dict[str, Any], kept: dict[str, list[str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Put what the author KEPT into the plan — deterministically, in their exact words.

    Returns `(new_spec, report)`. The input spec is not mutated.

    ## No model runs here, and that is the point

    These lines survived a grounding gate precisely because they are the author's own text. Sending
    them through the LLM refine path to be "structured" would invite the model to rewrite them, which
    is the thing every other fix this cycle has been undoing (`post_normalize_spec` replacing authored
    mechanic rules; `_pad_traits_from_analyze` inventing a protagonist). A keep must be a keep.

    ## Two destinations, because a line is not always a slot

    `writing_principles` and `open_questions` are plain string lists in the spec, so a kept line goes
    straight in. The others need a structured object — a variable is `{code, name}`, an arc is
    `{id, title}` — and a raw sentence is not one. Rather than invent the missing fields, those lines
    are carried into **`author_notes`**, the existing channel `compile` already threads into
    `planning_package.author_notes` where the LLM passes read them. Nothing is dropped, nothing is
    guessed, and the next propose sees material the author has explicitly confirmed.

    The report says which of the two happened per kind, so "we filed it as a note" can never be
    mistaken for "we added your variable".
    """
    import copy

    out = copy.deepcopy(spec)
    applied: dict[str, int] = {}
    noted: dict[str, int] = {}

    for kind, entries in (kept or {}).items():
        # An entry is either the bare quote (today's shape, kept working) or `{quote, label}` — the
        # label being the ONE field a structured kind needs and nobody may invent.
        lines: list[str] = []
        labelled: list[tuple[str, str]] = []
        for e in entries or []:
            if isinstance(e, str):
                if e.strip():
                    lines.append(e.strip())
            elif isinstance(e, dict):
                q = str(e.get("quote") or "").strip()
                lab = str(e.get("label") or "").strip()
                if not q:
                    continue
                (labelled.append((q, lab)) if lab else lines.append(q))

        if labelled and kind not in _LABELLED_SLOT:
            # A LABEL ON A STRING-SLOT KIND IS SURPLUS, NOT A REASON TO DROP THE LINE.
            # `premise` / `writing_principles` / `open_questions` land as plain strings, so they have
            # no use for a label — but routing the entry to the labelled branch and finding no slot
            # there silently discarded it. Caught live: a labelled `premise` keep returned
            # `changed: false, applied_to_slot: {}` and the author's line simply vanished. Exactly
            # the silent-no-op class this whole cycle has been removing, introduced by the fix for
            # the previous one. The label is dropped; the author's words are not.
            lines.extend(q for q, _ in labelled)
            labelled = []

        if labelled and kind in _LABELLED_SLOT:
            parent, key, label_field, body_field, id_field = _LABELLED_SLOT[kind]
            bucket = (out.setdefault(parent, {}) if parent else out).setdefault(key, [])
            if not isinstance(bucket, list):
                bucket = []
                (out[parent] if parent else out)[key] = bucket
            taken = {str(r.get(id_field) or "") for r in bucket if isinstance(r, dict)}
            have_labels = {str(r.get(label_field) or "").strip().casefold()
                           for r in bucket if isinstance(r, dict)}
            for quote, label in labelled:
                if label.casefold() in have_labels:
                    continue          # the author already has a row by that name — do not duplicate
                ident = _slug(label, upper=(id_field == "code"))
                base, n = ident, 2
                while ident in taken:
                    ident, n = f"{base}_{n}", n + 1
                taken.add(ident)
                have_labels.add(label.casefold())
                bucket.append({
                    id_field: ident, label_field: label,
                    body_field: [quote] if body_field in _LIST_BODY else quote,
                })
                applied[kind] = applied.get(kind, 0) + 1

        if not lines:
            continue
        slot = _DIRECT_SLOT.get(kind)
        if slot:
            parent, key = slot
            bucket = out.setdefault(parent, {}).setdefault(key, [])
            if not isinstance(bucket, list):
                bucket = []
                out[parent][key] = bucket
            existing = {str(x).strip() for x in bucket}
            added = [ln for ln in lines if ln not in existing]
            bucket.extend(added)
            if added:
                applied[kind] = applied.get(kind, 0) + len(added)
            continue

        notes = out.setdefault("author_notes", [])
        if not isinstance(notes, list):
            notes = []
            out["author_notes"] = notes
        have = {(n.get("text") or "").strip() for n in notes if isinstance(n, dict)}
        added_notes = [ln for ln in lines if ln not in have]
        notes.extend({"title": f"{kind} — kept by the author", "text": ln} for ln in added_notes)
        if added_notes:
            noted[kind] = noted.get(kind, 0) + len(added_notes)

    return out, {"applied_to_slot": applied, "carried_as_author_notes": noted}


def kinds_to_ask(packet: dict[str, Any], kept: dict[str, list[str]] | None = None) -> list[dict[str, str]]:
    """What is STILL worth asking once the author has kept or dropped the candidates.

    `kept` maps a kind to the quotes the author kept. A kind whose candidates were all dropped is
    back to genuinely missing, and becomes a question — which is the entire point of the review step:
    the POC's auto-conclude treated three wrong lines as an answer and never asked.

    A kind in `unavailable` is NEVER returned here, whatever the author did. We do not know that the
    material is missing, so asking for it may be asking them to rewrite what they already wrote.
    """
    kept = kept or {}
    out = [dict(a) for a in packet.get("ask") or []]
    for row in packet.get("review") or []:
        if not (kept.get(row["kind"]) or []):
            out.append({
                "kind": row["kind"], "status": row["status"], "question": question_for(row["kind"]),
                # Said out loud: the author has already seen and rejected these, and a question that
                # arrives with no memory of that reads as not having listened.
                "after_review": "all candidates were dropped",
            })
    return out
