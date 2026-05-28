"""HTML walker tests — spec §4.1 HTML rows.

Covers spec D4 walker semantics (`<body>`-only walk, h1/h2/h3 mapping,
single-h1-as-book-title, no-headings fallback, hr scene breaks).
"""

from __future__ import annotations

from loreweave_parse import ParseOptions, parse, parse_html

# ─── fixtures ────────────────────────────────────────────────────────────────

_HTML_MULTI_PART = """\
<html><head><title>Test Book</title></head>
<body>
  <h1>Part One</h1>
  <h2>Chapter Alpha</h2>
  <h3>Scene A1</h3>
  <p>Scene A1 body.</p>
  <h3>Scene A2</h3>
  <p>Scene A2 body.</p>
  <h2>Chapter Beta</h2>
  <p>Beta p1.</p>
  <h1>Part Two</h1>
  <h2>Chapter Gamma</h2>
  <p>Gamma p1.</p>
</body></html>
"""

_HTML_SINGLE_H1_BOOK = """\
<html><head><title>fallback</title></head>
<body>
  <h1>The Real Book Title</h1>
  <h2>Chapter 1</h2>
  <p>Body 1</p>
  <h2>Chapter 2</h2>
  <p>Body 2</p>
</body></html>
"""

_HTML_NO_HEADINGS = """\
<html><head><title>Mystery</title></head>
<body>
  <p>Just a paragraph.</p>
  <p>And another.</p>
</body></html>
"""

_HTML_HR_SCENE_BREAKS = """\
<html><body>
  <h2>Chapter With HR Breaks</h2>
  <p>Scene 1 paragraph.</p>
  <hr/>
  <p>Scene 2 paragraph.</p>
  <hr/>
  <p>Scene 3 paragraph.</p>
</body></html>
"""

_HTML_GENERATED_NAV = """\
<html><head><title>Nav Book</title></head>
<body>
  <nav class="toc"><ul><li><a href="#ch1">Chapter 1</a></li></ul></nav>
  <h2>Chapter 1</h2>
  <p>Real body 1.</p>
</body></html>
"""

_HTML_HEAD_ONLY = """\
<html><head><title>Just Head</title></head><body></body></html>
"""


# ─── tests ───────────────────────────────────────────────────────────────────


def test_html_walker_h1h2h3_tree():
    """Multi-part book with h1 parts, h2 chapters, h3 scenes."""
    tree = parse_html(_HTML_MULTI_PART)
    assert tree.source_format == "html"
    assert tree.walker_path == "headings"
    assert tree.book_title == "Test Book"
    assert len(tree.parts) == 2
    # Part 1: 2 chapters; Chapter Alpha has 2 scenes (h3), Chapter Beta has 1 (no h3).
    p1 = tree.parts[0]
    assert p1.title == "Part One"
    assert p1.path == "book/part-1"
    assert len(p1.chapters) == 2
    assert p1.chapters[0].title == "Chapter Alpha"
    assert p1.chapters[0].path == "book/part-1/chapter-1"
    assert len(p1.chapters[0].scenes) == 2
    assert p1.chapters[0].scenes[0].path == "book/part-1/chapter-1/scene-1"
    assert p1.chapters[1].title == "Chapter Beta"
    assert len(p1.chapters[1].scenes) == 1
    # Part 2: 1 chapter.
    p2 = tree.parts[1]
    assert p2.title == "Part Two"
    assert p2.path == "book/part-2"
    assert len(p2.chapters) == 1
    assert p2.chapters[0].path == "book/part-2/chapter-1"


def test_html_walker_single_h1_book():
    """One <h1> -> book title; <h2> siblings become chapters under implicit part-1."""
    tree = parse_html(_HTML_SINGLE_H1_BOOK)
    assert tree.walker_path == "headings"
    assert tree.book_title == "The Real Book Title"
    assert len(tree.parts) == 1
    assert tree.parts[0].title is None
    assert len(tree.parts[0].chapters) == 2
    assert tree.parts[0].chapters[0].title == "Chapter 1"
    assert tree.parts[0].chapters[1].title == "Chapter 2"


def test_html_walker_no_headings_fallback_single():
    """Zero structural headings -> walker_path=fallback_single + 1/1/1 tree."""
    tree = parse_html(_HTML_NO_HEADINGS)
    assert tree.walker_path == "fallback_single"
    assert tree.book_title == "Mystery"  # from <title>
    assert len(tree.parts) == 1
    assert len(tree.parts[0].chapters) == 1
    assert len(tree.parts[0].chapters[0].scenes) == 1
    leaf = tree.parts[0].chapters[0].scenes[0].leaf_text
    assert "Just a paragraph." in leaf
    assert "And another." in leaf


def test_html_walker_hr_scene_breaks_enabled():
    """<hr/> within an h2 chapter creates scene boundary by default."""
    tree = parse_html(_HTML_HR_SCENE_BREAKS)
    chapter = tree.parts[0].chapters[0]
    assert chapter.title == "Chapter With HR Breaks"
    assert len(chapter.scenes) == 3
    assert "Scene 1 paragraph" in chapter.scenes[0].leaf_text
    assert "Scene 2 paragraph" in chapter.scenes[1].leaf_text
    assert "Scene 3 paragraph" in chapter.scenes[2].leaf_text


def test_html_walker_hr_scene_breaks_disabled():
    """scene_break_on_hr=False collapses to single scene."""
    tree = parse_html(_HTML_HR_SCENE_BREAKS, options=ParseOptions(scene_break_on_hr=False))
    chapter = tree.parts[0].chapters[0]
    assert len(chapter.scenes) == 1
    assert "Scene 1 paragraph" in chapter.scenes[0].leaf_text
    assert "Scene 3 paragraph" in chapter.scenes[0].leaf_text


def test_html_walker_strips_generated_nav():
    """Pandoc's <nav class='toc'> is removed before heading walk so its anchors
    don't confuse the walker.
    """
    tree = parse_html(_HTML_GENERATED_NAV)
    # Without nav-strip, walker might pick up the anchor as a heading-like
    # element. With strip, we cleanly see exactly 1 chapter.
    assert tree.walker_path == "headings"
    assert len(tree.parts) == 1
    assert len(tree.parts[0].chapters) == 1
    assert tree.parts[0].chapters[0].title == "Chapter 1"


def test_html_walker_body_only_walk_ignores_head():
    """<head><title> is the only thing read from <head>; never as h1 candidate."""
    tree = parse_html(_HTML_HEAD_ONLY)
    # Empty <body> -> fallback_single with title from <head>
    assert tree.walker_path == "fallback_single"
    assert tree.book_title == "Just Head"


def test_html_walker_filename_fallback_title():
    """When no <title> in <head>, filename (sans ext) becomes book_title."""
    html = "<html><body><p>x</p></body></html>"
    tree = parse_html(html, filename="my_novel.epub")
    assert tree.book_title == "my_novel"


def test_dispatcher_routes_html():
    """The format dispatcher routes html -> parse_html."""
    tree = parse("html", _HTML_NO_HEADINGS)
    assert tree.source_format == "html"
