"""D-GENERATED-FACT-HAS-NO-HOME — a fact the drafter invents gets somewhere to live.

The gap, stated exactly
-----------------------
A scene's prose can assert things no spec contains: a character's gender, a name, a role, an
object. Measured 2026-08-01 on a fresh book, scene 2 invented *"there was **a man**"* and scene
3 correctly carried `he`/`his` — the architecture DOES carry a generated fact forward, in the
14,314 characters of prose the packer put in `<recent>`.

That is the whole problem. It carries the fact **as prose**, and prose is the first thing the
budget compresses. There is no ledger, nothing keyed, nothing an author can correct, and nothing
a later check can compare against. So the same architecture that carried `he` correctly in one
run let scene 2 end *"**He** is the anchor"* and scene 3 open *"**She's** a Scribe"* in another.

`outline_node.exit_state` was designed for this — its provenance enum literally reads
`'generator' (the drafting seam emitted it)` — and nothing ever wrote it. This module is the
write-back.

Why the recorded rows beat the prose that already carries them
--------------------------------------------------------------
They are an **incompressible floor** (InkOS F5, adopted here in `packer/pack.py`): compress what
the next step must merely KNOW, never what it must MATCH. Three lines of `who/pronoun/role`
survive a budget squeeze that drops the paragraph they came from, and they survive it in a shape
a comparison can key on.

What this does NOT do — said plainly, because the temptation is to overclaim
----------------------------------------------------------------------------
It does not link an UNNAMED referent. The measured anchor→Scribe defect has no name on either
side, so recording `who="the anchor"` and later extracting `who="She"` still does not link, and
`cross_scene_check` still reports it as unlinked rather than clean. What the recording buys
there is PREVENTION, not detection: the next scene's prompt now carries `the anchor — he` as a
stated fact instead of as a sentence 14,000 characters back. Detection improves only for people
the prose actually names.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.db.models import MAX_EXIT_CAST

logger = logging.getLogger(__name__)

#: Mirrors `db.models.CastPronoun`. Anything else the extractor returns — a Vietnamese `anh ấy`,
#: a stray article, a hallucinated phrase — normalises to `none` rather than being stored raw,
#: so a downstream membership test never has to know about languages.
_PRONOUNS = frozenset({"he", "she", "they", "none"})

_ARTICLE = re.compile(r"^(the|a|an)\s+", re.I)
_POSSESSIVE = re.compile(r"['’]s$")

#: Pronouns and bare role nouns are not identities. Recording `who="She"` as a cast row would
#: create a key that matches every woman in the book. Kept in sync with
#: `cross_scene_check._NOT_A_NAME` by being the same list — the two ends of this pipe MUST
#: agree on what counts as a name, or a row written here is unmatchable there.
_NOT_A_NAME = frozenset("""
he she it they him her them his hers its their someone somebody anyone everyone nobody
man woman girl boy child person figure shape voice stranger
""".split())


def norm_key(who: str) -> str:
    """The comparison key for a cast row. Empty ⇒ this is not an identity, do not record it."""
    w = _POSSESSIVE.sub("", _ARTICLE.sub("", (who or "").strip())).strip().lower()
    return "" if w in _NOT_A_NAME or len(w) < 3 else w


def cast_rows_from_people(people: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Extractor rows → storable cast rows. Deterministic: no model, no network.

    Records ONLY people the passage NAMES. A row is stored under its proper name, deduplicated
    on that name (first wins — a model that lists one person twice must not produce two rows
    that then "contradict" each other), with the pronoun clamped to the closed set.

    The name requirement is not fussiness, it is what the live run forced. Keying on the
    passage's own referring expression recorded ten Vietnamese rows — *Anh ta*, *Người đàn ông*,
    *ngươi*, *Ánh mắt họ* ("their gaze") — and every one of them would have been handed to the
    next scene as a fact about a character. See `cross_scene_check.identity_of` for the full
    measurement. An unnamed person is carried by the prose; they are not carried by a key,
    because there is no key that would mean them and only them.
    """
    from app.engine.cross_scene_check import identity_of

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for p in people or []:
        if not isinstance(p, dict):
            continue
        key = identity_of(p)
        if not key:
            continue
        # A model that echoes a pronoun into the `name` slot is caught by the English list too.
        # Belt and braces: this is the field that reaches a prompt as an assertion.
        if key in _NOT_A_NAME or key in seen:
            continue
        seen.add(key)
        pron = str(p.get("pronoun") or "none").strip().lower()
        out.append({
            "who": str(p.get("name") or "").strip()[:500],
            "pronoun": pron if pron in _PRONOUNS else "none",
            "role": str(p.get("role") or "").strip()[:500],
        })
        if len(out) >= MAX_EXIT_CAST:
            break
    return out


def merge_generated_cast(
    existing: dict[str, Any] | None, cast: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, str]:
    """Fold a generator-written `cast` into whatever is already stored.

    Returns `(envelope_to_write, reason)`. A `None` envelope means DO NOT WRITE, and `reason`
    always says which of the cases it was — a caller must be able to tell "recorded" from
    "declined" from "nothing to record" in its output, never infer it from a silence.

    Two rules, both load-bearing:

    1. **An author's curated cast is never overwritten.** `source` is the provenance of `cast`
       specifically — it is the only field with two possible writers, so it needs no per-field
       companion for the prose buckets, which only a human ever writes.
    2. **The authored prose buckets are preserved byte-for-byte.** This writes ONE key. A
       regeneration that quietly reset an author's `plot` note would be the same class of
       data loss as overwriting their cast, just harder to notice.
    """
    if not cast:
        return None, "no_cast_extracted"
    base = dict(existing or {})
    if base.get("source") == "author" and base.get("cast"):
        # Not an error and not a failure — a deliberate deferral to the human. It is returned
        # rather than logged-and-forgotten because the envelope reports it.
        return None, "author_owned"
    base["v"] = 1
    base["source"] = "generator"
    base["cast"] = cast[:MAX_EXIT_CAST]
    return base, "recorded"


def merge_authored_exit_state(
    existing: dict[str, Any] | None, incoming: dict[str, Any],
) -> dict[str, Any]:
    """Fold an AUTHORING-door write (MCP scene create/update) onto what is stored.

    A write through this door REPLACES the envelope — that is the pre-existing semantic and
    changing it would surprise every current caller. The one thing it must not replace is a
    `cast` the author did not send: the drafter records one on every generate, and silently
    dropping it because someone edited `plot` would break the continuity floor by accident.

    So: `cast is None` (omitted) carries the stored cast AND its provenance forward untouched.
    Any other value is the author speaking about the cast, and is stamped `author` — which is
    what makes "never overwrite an author's correction" enforceable. `source` is decided HERE,
    server-side, and is absent from the wire model: a caller that could choose its own
    provenance could stamp a generator write as authored and freeze the record forever.
    """
    out = {k: v for k, v in incoming.items() if k != "cast"}
    out["v"] = 1
    if incoming.get("cast") is None:
        prior = existing or {}
        out["cast"] = prior.get("cast") or []
        # Untouched cast keeps the provenance that produced it. Claiming `author` here would
        # mark a generator's rows as human-curated and permanently block the next write-back.
        out["source"] = prior.get("source") or "generator"
    else:
        out["cast"] = incoming["cast"][:MAX_EXIT_CAST]
        out["source"] = "author"
    return out


def render_carried_cast(exit_state: dict[str, Any] | None, *, limit: int = 12) -> str:
    """The prior scene's recorded cast, as one prompt line.

    Deliberately terse and deliberately NOT a sentence: the drafter is being handed facts to
    match, and a fluent paraphrase is the shape a later summariser feels free to rewrite.
    """
    rows = (exit_state or {}).get("cast")
    if not isinstance(rows, list):
        return ""
    parts: list[str] = []
    for r in rows[:limit]:
        if not isinstance(r, dict):
            continue
        who = str(r.get("who") or "").strip()
        if not who:
            continue
        pron = str(r.get("pronoun") or "none").strip().lower()
        role = str(r.get("role") or "").strip()
        bits = [who]
        if pron in _PRONOUNS and pron != "none":
            bits.append(pron)
        if role:
            bits.append(role)
        parts.append(" — ".join(bits) if len(bits) > 1 else who)
    return "; ".join(parts)


def recorded_people(exit_state: dict[str, Any] | None) -> list[dict[str, Any]] | None:
    """The stored cast in the shape `cross_scene_check.compare_people` consumes.

    `None` (not `[]`) when there is nothing recorded, so the caller falls back to extracting
    from prose instead of comparing against an empty list and calling the seam clean.
    """
    rows = (exit_state or {}).get("cast")
    if not isinstance(rows, list) or not rows:
        return None
    out = [
        {"who": str(r.get("who") or ""), "pronoun": str(r.get("pronoun") or "none"),
         "role": str(r.get("role") or "")}
        for r in rows if isinstance(r, dict) and str(r.get("who") or "").strip()
    ]
    return out or None
