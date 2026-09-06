"""T37b-planforge — the cast plan carries STRUCTURED roles (SPEC §4.2c).

WHY THE FIELD EXISTS
--------------------
`ProposedChar.relationships` is free text — the code comment's own example is
`"huynh trưởng of Lâm Uyển"`  # doc-language-gate: ok -- the field's own code comment quoted
verbatim; paraphrasing it would hide that the field holds prose, which is the whole finding.
`append_role_fact` needs `attr_or_predicate` and `value` as
separate fields, so plan-time authorship had **nothing of the right shape to send**: measured
before building, nothing else in the engine carried a structured tie either.

The decision (§4.2c) was to ask the model for the structure it is already producing, rather
than parse the prose back out. Parsing would need an LLM pass on data the first pass already
had, or a heuristic over multilingual free text — and a heuristic of exactly that kind is what
promoted an event phrase to a character in the acceptance book's betrayal edge. **A role fact
minted from a mis-parse is worse than no role fact: it is a canon claim the guard enforces.**

So these rules are about tolerance, not happy-path shape: the parser must never turn a sloppy
model into a confident false claim, and must never lose a cast because the field is absent.
"""
from __future__ import annotations

import json

from app.engine.cast_plan import ProposedChar, build_propose_cast_messages, parse_cast


def _row(**kw) -> dict:
    base = {"name": "Kai", "role": "protagonist", "archetype": "a", "traits": ["x"],
            "relationships": "brother of Mira", "summary": "s", "is_new": False}
    base.update(kw)
    return base


def test_the_prompt_asks_for_roles_AND_still_asks_for_the_prose():
    """Additive, not a replacement. `relationships` is prose the packer already uses for
    grounding; dropping it to make room for structure would degrade the draft prompt to serve
    the graph, which is a trade the graph does not get to make."""
    msgs = build_propose_cast_messages(premise="p", known_cast=[])
    blob = json.dumps(msgs)
    assert '\\"roles\\"' in blob or '"roles"' in blob, "the prompt never asks for roles"
    assert "relationships" in blob, (
        "the prompt stopped asking for the prose ties — the packer grounds on those")
    assert "predicate" in blob and "object" in blob, (
        "the prompt asks for `roles` without saying what shape a role is")


def test_a_structured_role_survives_the_parse():
    out = parse_cast(json.dumps([_row(roles=[{"predicate": "betrayed", "object": "Mira"}])]))
    assert out[0].roles == [{"predicate": "betrayed", "object": "Mira"}]


def test_a_cast_with_NO_roles_still_parses():
    """🔴 The tolerance that matters most. An older model, a prompt predating the field, or a
    truncated array all yield no `roles` key — and a plan that lost its whole cast because the
    graph wanted a new field would be a far worse regression than a plan with no roles."""
    out = parse_cast(json.dumps([_row()]))
    assert len(out) == 1 and out[0].name == "Kai"
    assert out[0].roles == [], "a missing `roles` key must default to empty, never None"
    assert ProposedChar(name="x").roles == [], "the default must not be shared mutable state"


def test_HALF_a_role_is_DROPPED_not_written_as_a_blank_claim():
    """A role with a blank side is a canon claim about nothing, and every layer below would
    accept it: `attr_or_predicate` and `value` are plain strings from here to Postgres. The
    model is the thing being tolerated, so it is dropped at the parse rather than left for the
    producer to re-litigate."""
    out = parse_cast(json.dumps([_row(roles=[
        {"predicate": "betrayed", "object": "Mira"},   # keep
        {"predicate": "", "object": "Mira"},           # no verb
        {"predicate": "allied_with", "object": "  "},  # no target
        {"predicate": "allied_with"},                  # no object at all
        "not-an-object",                               # not even a dict
    ])]))
    assert out[0].roles == [{"predicate": "betrayed", "object": "Mira"}], (
        f"a half-formed role survived the parse: {out[0].roles}")


def test_roles_that_are_not_a_list_do_not_take_the_cast_down():
    """Models emit a string where a list was asked for. `parse_cast`'s whole contract is
    'never raises' — a malformed `roles` must degrade to `[]`, not lose the character."""
    for junk in ("betrayed Mira", {"predicate": "x"}, 7, None):
        out = parse_cast(json.dumps([_row(roles=junk)]))
        assert len(out) == 1, f"a {type(junk).__name__} in `roles` dropped the character"
        assert out[0].roles == []
