"""P2 — the rules-path merge-not-duplicate (PROPOSE-BLIND). Deterministic, no LLM."""

from __future__ import annotations

from app.engine.plan_forge.existing_state import (
    ArcSummary,
    CastMember,
    ExistingState,
    merge_existing_into_spec,
    title_key,
)
from app.engine.plan_forge.propose import propose_spec


def _state(*, arcs=(), cast=(), chapter_count=1) -> ExistingState:
    return ExistingState(
        chapter_count=chapter_count,
        recent_chapters=[], cast=list(cast), arcs=list(arcs),
        variables=[], motifs=[], notes={}, grounded_fingerprint="fp",
    )


def _doc(md_arcs: str, char: str = "") -> dict:
    """A minimal PlanDocument with an arc_overview section (+ optional character_seed)."""
    sections = [{"kind": "arc_overview", "title": "Arcs", "body": md_arcs}]
    if char:
        sections.append({"kind": "character_seed", "title": "Char", "body": char})
    return {"sections": sections, "source": {"checksum_sha256": "abc"}}


def test_title_key_is_lower_strip():
    assert title_key("  The Iron Court ") == "the iron court"
    assert title_key(None) == ""


def test_cold_start_is_BYTE_IDENTICAL_to_braindump_only():
    doc = _doc("## Arc 1: The Iron Court\n**Theme:** intrigue\n")
    without = propose_spec(doc)
    with_empty = propose_spec(doc, existing=None)
    with_coldstart = propose_spec(doc, existing=_state(chapter_count=0))  # is_empty() → no-op
    assert without == with_empty == with_coldstart


def test_a_proposed_arc_matching_an_existing_one_is_annotated_continues_existing():
    doc = _doc("## The Iron Court\n**Theme:** intrigue\n## A Brand New Arc\n**Theme:** fresh\n")
    st = _state(arcs=[ArcSummary(title="the iron court", one_line="x")])
    spec = propose_spec(doc, existing=st)
    by_title = {a["title"]: a for a in spec["arcs"]}
    assert by_title["The Iron Court"]["continues_existing"] is True     # matched → continuation
    assert by_title["A Brand New Arc"]["continues_existing"] is False   # genuinely new


def test_a_proposed_character_matching_an_existing_cast_carries_its_entity_id():
    doc = _doc("## Arc 1\n", char="**Name:** Ling Wei\n**Role:** protagonist\n")
    st = _state(cast=[CastMember(name="Ling Wei", glossary_entity_id="ent-42")])
    spec = propose_spec(doc, existing=st)
    ch = spec["layers"]["characters"][0]
    assert ch["glossary_entity_id"] == "ent-42"   # resolves to the SAME entity, not a duplicate
    assert ch["continues_existing"] is True


def test_a_new_character_gets_no_entity_id():
    doc = _doc("## Arc 1\n", char="**Name:** Someone New\n**Role:** protagonist\n")
    st = _state(cast=[CastMember(name="Ling Wei", glossary_entity_id="ent-42")])
    spec = propose_spec(doc, existing=st)
    ch = spec["layers"]["characters"][0]
    assert "glossary_entity_id" not in ch


def test_merge_is_pure_over_the_dict_and_case_insensitive():
    spec = {"arcs": [{"title": "THE IRON COURT"}], "layers": {"characters": [{"name": "ling wei"}]}}
    st = _state(arcs=[ArcSummary(title="The Iron Court", one_line="")],
                cast=[CastMember(name="Ling Wei", glossary_entity_id="e1")])
    out = merge_existing_into_spec(spec, st)
    assert out["arcs"][0]["continues_existing"] is True                 # case-insensitive arc match
    assert out["layers"]["characters"][0]["glossary_entity_id"] == "e1"  # case-insensitive cast match
