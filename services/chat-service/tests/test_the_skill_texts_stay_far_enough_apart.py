"""D-THE-INTENT-ROUTERS-TOP-K-CAP-CROWDS-OUT-THE-RIGHT-DOMAIN — the separation, guarded.

THE FAILURE, as the row recorded it 2026-08-28 on the prompt "Is my story bible out of date?
Apply the standard updates if there are any.":

    12 of 12 skills cleared ROUTER_CONFIDENCE_THRESHOLD (0.35) — the floor filtered NOTHING
    ranked  translation 0.5096 / admin 0.44 / book 0.44 / … / glossary 0.3950  (7th)
    injected_skills = ['book', 'co_write', 'translation'] on 5 of 5 runs; glossary absent

The row's own diagnosis: "either the embedding model in use discriminates poorly, or the
skill-description texts being embedded are too similar to each other."

DQ-T90 answered it (owner: "just try options and choose the best"). Arm (b) — CONTRASTIVE
embedding texts, each saying what its skill is NOT — won pooled 89.7% vs 75.4% (+14.2 points,
Fisher p=0.052), and the misses collapsed from five domains to one.

MEASURED AGAINST THE DEPLOYED ROUTER 2026-09-02, same prompt, real embeddings:

    glossary   0.3950 (7th)  ->  0.4946 (1st)
    translation 0.5096 (1st) ->  0.4118 (5th)
    cleared the floor: 12 of 12 -> 9 of 12
    route_additional_skills(...) -> ['glossary', 'book']

🔴 AND THE MECHANISM THAT BOUGHT THAT HAD NO GUARD. `_CONTRASTIVE` is a hand-written dict; a
future edit that lets two entries drift back together, or drops one so it falls back to the
colliding description, reverts the row silently — every other test stays green, because none of
them look at these texts. Cosine cannot be asserted here (no embedding model in a unit test), so
this pins the two properties that ARE checkable and that the separation rests on: every skill
carries one, and no two say nearly the same thing.
"""
from __future__ import annotations

import itertools
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.services.skill_registry import SYSTEM_SKILLS  # noqa: E402
from app.services.skill_router import _CONTRASTIVE, _skill_embedding_text  # noqa: E402

_STOP = {
    "a", "an", "and", "the", "of", "for", "to", "in", "on", "it", "its", "this", "that", "is",
    "are", "not", "never", "or", "with", "from", "as", "by", "at", "be", "you", "your", "их",
}


def _tokens(text: str) -> set[str]:
    return {w.strip(".,:;—-()'\"").lower() for w in text.split()} - _STOP - {""}


def _codes() -> list[str]:
    items = SYSTEM_SKILLS.items() if hasattr(SYSTEM_SKILLS, "items") else \
        [(getattr(s, "code", None), s) for s in SYSTEM_SKILLS]
    return [c for c, _ in items if c]


def test_every_skill_carries_a_contrastive_text():
    """🔴 A MISSING ENTRY IS A SILENT REVERT. `_skill_embedding_text` falls back to
    `skill.description` — the very text the row measured colliding — and nothing says so."""
    missing = [c for c in _codes() if not _CONTRASTIVE.get(c)]
    assert not missing, (
        f"{missing} have no contrastive text, so they embed their plain description — the shape "
        "that put glossary 7th behind translation on its own prompt"
    )


def test_no_two_skills_say_nearly_the_same_thing():
    """The separation IS the fix. Two texts that share most of their vocabulary embed close
    together however the floor is tuned, which is what '12 of 12 cleared 0.35' looked like."""
    texts = {c: _tokens(_CONTRASTIVE[c]) for c in _codes() if _CONTRASTIVE.get(c)}
    worst, worst_pair = 0.0, ("", "")
    for a, b in itertools.combinations(sorted(texts), 2):
        ta, tb = texts[a], texts[b]
        if not ta or not tb:
            continue
        jaccard = len(ta & tb) / len(ta | tb)
        if jaccard > worst:
            worst, worst_pair = jaccard, (a, b)
    assert worst < 0.35, (
        f"{worst_pair[0]} and {worst_pair[1]} share {worst:.0%} of their vocabulary — the "
        "collision this row is about, reintroduced in the texts that were written to remove it"
    )


def test_the_pair_the_row_names_is_pulled_apart():
    """book vs translation is the ORIGINAL instance: translation ranked 1st (0.5096) on a
    glossary prompt and book 3rd, both 'plausibly book/story-related in the abstract'. The
    pre-flight geometry recorded on DQ-T90 moved them 0.7715 -> 0.6491."""
    b, t = _tokens(_CONTRASTIVE["book"]), _tokens(_CONTRASTIVE["translation"])
    overlap = len(b & t) / len(b | t)
    assert overlap < 0.30, (
        f"book and translation share {overlap:.0%} of their vocabulary; they are the pair the "
        "row names as 'both plausibly book/story-related'"
    )
    # ...and each says what it is NOT, which is the whole device.
    for code in ("book", "translation"):
        assert "never" in _CONTRASTIVE[code].lower() or "not" in _CONTRASTIVE[code].lower(), (
            f"{code}'s text no longer states an exclusion — a contrastive text that contrasts "
            "with nothing is just a description"
        )


def test_the_contrastive_text_is_the_one_ACTUALLY_EMBEDDED():
    """🔴 THIS ASSERTION USED TO CHECK THE FLAG'S VALUE, AND THAT WAS VACUOUS FOR THE WIRING.
    Stubbing `_skill_embedding_text`'s branch to `if False and …` — the pre-fix control arm —
    left it GREEN, because the flag was still True while the code ignored it. A guard on a
    setting is not a guard on the behaviour the setting selects.

    DQ-T90's answer was arm (b); a default that drifts off, or a branch that stops reading it,
    ships the CONTROL arm (75.4%) while every test still passes."""
    assert settings.skill_contrastive_desc is True, (
        "skill_contrastive_desc defaults OFF — the platform would run the CONTROL arm, which "
        "measured 75.4% against arm (b)'s 89.7%"
    )
    for code in ("book", "translation", "glossary"):
        embedded = _skill_embedding_text(code)
        assert _CONTRASTIVE[code] in embedded, (
            f"{code} embeds something other than its contrastive text — the router is scoring "
            "the plain descriptions again, which is the state that ranked glossary 7th on its "
            "own prompt"
        )
