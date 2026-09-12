"""T8 — the manuscript-derived "realized" signal.

WHY THIS EXISTS. Conformance had exactly two ways to call a scene realized, and a human could
reach NEITHER: a completed per-scene ``generation_job`` (only an automated generation path creates
one) and ``outline_node.written_*`` (only a book-service parse/import populates it). A 2026-09-06
human-sim run drafted a 5-arc novel in chat and pasted it into the editor — every finished scene
reported "Not written yet", including one of 1718 words that had been reviewed and accepted.

``scene_prose_presence`` reads the saved manuscript itself, so prose counts as prose regardless of
who typed it. These pin the properties that make it trustworthy: it must not claim a scene is
written when it isn't, and it must follow the SAME anchoring rules the editor draws with — a
looser rule would report a scene as written that the author's own Scene Rail shows as unanchored.
"""
from __future__ import annotations

from app.engine.prose_doc import scene_prose_presence


def _h(text: str, level: int = 3, scene_id: str | None = None) -> dict:
    node: dict = {"type": "heading", "attrs": {"level": level}, "_text": text}
    if scene_id:
        node["attrs"]["sceneId"] = scene_id
    return node


def _p(text: str) -> dict:
    return {"type": "paragraph", "_text": text}


def _doc(*blocks: dict) -> dict:
    return {"type": "doc", "content": list(blocks)}


SCENES = [
    {"id": "s1", "title": "The Gate of Ash"},
    {"id": "s2", "title": "Rain on the Ledger"},
]


def test_prose_under_a_matched_heading_counts_as_written():
    """The case the whole task exists for: hand-pasted prose, no generation job anywhere."""
    doc = _doc(
        _h("The Gate of Ash"),
        _p("The gate stood open, and no one had opened it."),
    )
    assert scene_prose_presence(doc, SCENES) == {"s1": 10}


def test_a_heading_with_no_body_is_NOT_written():
    """An outlined-but-unwritten scene must stay unwritten.

    This is the property that makes the signal worth anything: if a bare heading counted, every
    scene would read as realized the moment the rail anchored it, and the panel would be decorative.
    """
    doc = _doc(_h("The Gate of Ash"), _h("Rain on the Ledger"), _p("Water, and a column of sums."))
    out = scene_prose_presence(doc, SCENES)
    assert "s1" not in out, "an empty section was reported as written"
    assert out["s2"] == 6


def test_an_explicit_sceneId_on_the_heading_wins_over_title_matching():
    """The editor stamps `attrs.sceneId` on save; honour it rather than re-deriving by title,
    so a renamed scene keeps its anchor exactly as the editor shows it."""
    doc = _doc(_h("A Title That Matches Nothing", scene_id="s1"), _p("Three words here."))
    assert scene_prose_presence(doc, SCENES) == {"s1": 3}


def test_an_ambiguous_title_anchors_nothing():
    """`_attach_scene_ids`' rule: a scene anchors only when EXACTLY ONE free heading carries its
    title. Two identical headings are ambiguous, and guessing would mark the wrong one written."""
    doc = _doc(
        _h("The Gate of Ash"), _p("First body."),
        _h("The Gate of Ash"), _p("Second body."),
    )
    assert scene_prose_presence(doc, SCENES) == {}


def test_a_deeper_heading_is_part_of_the_scene_not_the_next_one():
    """A subsection belongs to its scene; only a same-or-higher heading ends it."""
    doc = _doc(
        _h("The Gate of Ash", level=2),
        _p("One two three."),
        _h("A sub-beat", level=3),
        _p("Four five."),
        _h("Rain on the Ledger", level=2),
        _p("Six."),
    )
    out = scene_prose_presence(doc, SCENES)
    assert out["s1"] == 5, "a deeper heading wrongly ended the scene"
    assert out["s2"] == 1


def test_unmatched_scenes_are_simply_absent():
    doc = _doc(_h("Something Else Entirely"), _p("Body."))
    assert scene_prose_presence(doc, SCENES) == {}


def test_degrades_safely_on_junk_input():
    """Conformance is advisory — malformed input must return nothing, never raise."""
    for junk in (None, "", 42, {}, {"type": "doc"}, {"type": "doc", "content": "nope"}):
        assert scene_prose_presence(junk, SCENES) == {}


def test_does_not_mutate_the_caller_document():
    """`_attach_scene_ids` mutates; this is a READ and must not leave anchors behind on a
    document the caller may go on to save."""
    doc = _doc(_h("The Gate of Ash"), _p("Body text here."))
    scene_prose_presence(doc, SCENES)
    assert "sceneId" not in doc["content"][0]["attrs"], "the read stamped ids onto the caller's doc"
