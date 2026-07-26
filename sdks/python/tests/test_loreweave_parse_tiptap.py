"""Tiptap walker tests — spec 26 IX-6.

Covers the ProseMirror walker: h1/h2/h3 mapping identical to the html walker,
`horizontalRule` scene breaks, fallback_single, and — the reason this walker
exists — `Scene.anchor_scene_id` carried from each scene's opening heading
(`attrs.sceneId`, the persisted form of `data-scene-id`). Plus determinism
round-trips and the additive guarantee (non-tiptap formats keep anchor None).
"""

from __future__ import annotations

import hashlib
import json

import pytest

from loreweave_parse import parse, parse_html, parse_tiptap


# ─── fixture builders ────────────────────────────────────────────────────────


def _h(level: int, text: str, scene_id: str | None = None) -> dict:
    attrs: dict = {"level": level}
    if scene_id is not None:
        attrs["sceneId"] = scene_id
    return {"type": "heading", "attrs": attrs, "content": [{"type": "text", "text": text}]}


def _p(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _hr() -> dict:
    return {"type": "horizontalRule"}


def _doc(*blocks: dict) -> str:
    return json.dumps({"type": "doc", "content": list(blocks)})


def _all_scenes(tree):
    return [s for p in tree.parts for c in p.chapters for s in c.scenes]


# ─── tree shape (html-walker parity) ─────────────────────────────────────────


_MULTI_PART = _doc(
    _h(1, "Part One"),
    _h(2, "Chapter Alpha"),
    _h(3, "Scene A1", "scene-a1"),
    _p("Scene A1 body."),
    _h(3, "Scene A2", "scene-a2"),
    _p("Scene A2 body."),
    _h(2, "Chapter Beta"),
    _p("Beta p1."),
    _h(1, "Part Two"),
    _h(2, "Chapter Gamma"),
    _p("Gamma p1."),
)


def test_tiptap_h1h2h3_tree():
    """level-1 parts, level-2 chapters, level-3 scenes — same shape as html_walker."""
    tree = parse_tiptap(_MULTI_PART)
    assert tree.source_format == "tiptap"
    assert tree.walker_path == "headings"
    assert len(tree.parts) == 2
    p1 = tree.parts[0]
    assert p1.title == "Part One"
    assert p1.path == "book/part-1"
    assert len(p1.chapters) == 2
    assert p1.chapters[0].title == "Chapter Alpha"
    assert p1.chapters[0].path == "book/part-1/chapter-1"
    assert len(p1.chapters[0].scenes) == 2
    assert p1.chapters[0].scenes[0].path == "book/part-1/chapter-1/scene-1"
    # h3 heading text is the boundary/title, NOT scene leaf text.
    assert p1.chapters[0].scenes[0].leaf_text == "Scene A1 body."
    assert p1.chapters[1].title == "Chapter Beta"
    assert len(p1.chapters[1].scenes) == 1
    p2 = tree.parts[1]
    assert p2.title == "Part Two"
    assert p2.path == "book/part-2"
    assert len(p2.chapters) == 1
    assert p2.chapters[0].path == "book/part-2/chapter-1"


def test_tiptap_h3_scenes_carry_anchor():
    """Each level-3 scene carries its heading's `attrs.sceneId` (IX-6)."""
    tree = parse_tiptap(_MULTI_PART)
    alpha = tree.parts[0].chapters[0]
    assert alpha.scenes[0].anchor_scene_id == "scene-a1"
    assert alpha.scenes[1].anchor_scene_id == "scene-a2"
    # Chapter Beta has no h3 and no sceneId on its own heading -> no anchor.
    assert tree.parts[0].chapters[1].scenes[0].anchor_scene_id is None


# ─── the re-parse case: scenes marked at the chapter (level-2) heading ────────


_REPARSE_BODY = _doc(
    _h(2, "The Arrival", "node-1"),
    _p("She stepped off the train."),
    _h(2, "The Meeting", "node-2"),
    _p("He was waiting."),
)


def test_tiptap_chapter_heading_anchor_carries_to_single_scene():
    """A chapter whose own heading is scene-anchored (no inner h3) carries that
    anchor onto its single scene — the common publish/sweep re-parse shape."""
    tree = parse_tiptap(_REPARSE_BODY)
    assert tree.walker_path == "headings"
    chapters = tree.parts[0].chapters
    assert len(chapters) == 2
    assert chapters[0].scenes[0].anchor_scene_id == "node-1"
    assert chapters[0].scenes[0].leaf_text == "She stepped off the train."
    assert chapters[1].scenes[0].anchor_scene_id == "node-2"
    assert chapters[1].scenes[0].leaf_text == "He was waiting."


# ─── horizontalRule scene breaks ─────────────────────────────────────────────


_HR_BODY = _doc(
    _h(2, "Chapter With Breaks", "chap-anchor"),
    _p("Scene one prose."),
    _hr(),
    _p("Scene two prose."),
    _hr(),
    _p("Scene three prose."),
)


def test_tiptap_hr_scene_breaks_enabled():
    """`horizontalRule` splits scenes; only the first opens under the chapter
    heading, so only it inherits the chapter's anchor."""
    tree = parse_tiptap(_HR_BODY)
    chapter = tree.parts[0].chapters[0]
    assert len(chapter.scenes) == 3
    assert chapter.scenes[0].leaf_text == "Scene one prose."
    assert chapter.scenes[1].leaf_text == "Scene two prose."
    assert chapter.scenes[2].leaf_text == "Scene three prose."
    assert chapter.scenes[0].anchor_scene_id == "chap-anchor"
    assert chapter.scenes[1].anchor_scene_id is None
    assert chapter.scenes[2].anchor_scene_id is None


def test_tiptap_hr_scene_breaks_disabled():
    from loreweave_parse import ParseOptions

    tree = parse_tiptap(_HR_BODY, options=ParseOptions(scene_break_on_hr=False))
    chapter = tree.parts[0].chapters[0]
    assert len(chapter.scenes) == 1
    assert "Scene one prose." in chapter.scenes[0].leaf_text
    assert "Scene three prose." in chapter.scenes[0].leaf_text


# ─── fallback_single ─────────────────────────────────────────────────────────


def test_tiptap_no_headings_fallback_single():
    tree = parse_tiptap(_doc(_p("Just prose, no headings."), _p("Another paragraph.")))
    assert tree.walker_path == "fallback_single"
    assert len(tree.parts) == 1
    assert len(tree.parts[0].chapters) == 1
    scenes = tree.parts[0].chapters[0].scenes
    assert len(scenes) == 1
    assert scenes[0].anchor_scene_id is None
    assert "Just prose, no headings." in scenes[0].leaf_text
    assert "Another paragraph." in scenes[0].leaf_text


# ─── leaf-text extraction: _text snapshot + hardBreak + nested container ──────


def test_tiptap_leaf_prefers_text_snapshot():
    """book-service writes a `_text` snapshot on every block; the walker uses it."""
    doc = _doc(
        _h(2, "Scene", "s1"),
        {"type": "paragraph", "_text": "Snapshot wins.", "content": [{"type": "text", "text": "ignored"}]},
    )
    scene = _all_scenes(parse_tiptap(doc))[0]
    assert scene.leaf_text == "Snapshot wins."
    assert scene.anchor_scene_id == "s1"


def test_tiptap_hardbreak_becomes_newline():
    doc = _doc(
        _h(2, "Scene", "s1"),
        {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Line one."},
                {"type": "hardBreak"},
                {"type": "text", "text": "Line two."},
            ],
        },
    )
    scene = _all_scenes(parse_tiptap(doc))[0]
    assert scene.leaf_text == "Line one.\nLine two."


def test_tiptap_nested_container_text_not_dropped():
    """Blockquote/list prose (block children, no `_text`) survives the walk."""
    doc = _doc(
        _h(2, "Scene", "s1"),
        {
            "type": "blockquote",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Quoted line."}]},
            ],
        },
    )
    scene = _all_scenes(parse_tiptap(doc))[0]
    assert "Quoted line." in scene.leaf_text


# ─── determinism (spec A1 round-trip) ────────────────────────────────────────


def test_tiptap_deterministic_paths_hashes_anchors():
    t1 = parse_tiptap(_MULTI_PART)
    t2 = parse_tiptap(_MULTI_PART)

    def _tuples(tree):
        return [
            (s.path, s.content_hash, s.anchor_scene_id, s.leaf_text)
            for s in _all_scenes(tree)
        ]

    assert _tuples(t1) == _tuples(t2)


def test_tiptap_content_hash_is_sha256_of_leaf():
    for scene in _all_scenes(parse_tiptap(_MULTI_PART)):
        expected = hashlib.sha256(scene.leaf_text.encode("utf-8")).hexdigest()
        assert scene.content_hash == expected


# ─── dispatcher + additive guarantees ────────────────────────────────────────


def test_dispatcher_routes_tiptap():
    tree = parse("tiptap", _REPARSE_BODY)
    assert tree.source_format == "tiptap"
    assert _all_scenes(tree)[0].anchor_scene_id == "node-1"


def test_html_scenes_have_none_anchor():
    """Additive: the html walker never sets anchor_scene_id (defaults None)."""
    tree = parse_html("<html><body><h2>C</h2><p>x</p></body></html>")
    assert _all_scenes(tree)[0].anchor_scene_id is None


def test_tiptap_malformed_json_raises_valueerror():
    """Bad JSON -> ValueError (the router translates it to 400)."""
    with pytest.raises(ValueError):
        parse_tiptap("not-json{")
    with pytest.raises(ValueError):
        parse_tiptap('["a list is not a doc"]')
