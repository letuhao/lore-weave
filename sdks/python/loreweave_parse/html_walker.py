"""HTML walker — spec D4.

Walks pandoc HTML output and produces a StructuralTree.

Locked rules (M1+M2+M4 from /review-impl round 1):
- BeautifulSoup with html.parser backend (lenient, stdlib-only).
- Walk children of <body> only; never descend into <head>.
- <head><title> text -> book_title fallback when no <h1>.
- Strip pandoc's <nav class="toc"> generated ToC before heading walk.
- No EPUB <nav> priority parsing — headings-only for P1.
- <h1>=part, <h2>=chapter, <h3>=scene. Single-<h1> = book title.
- <hr/> within an <h2> chapter creates scene break (configurable).
"""

from __future__ import annotations

import hashlib

from bs4 import BeautifulSoup, NavigableString, Tag

from loreweave_parse._text_strip import html_to_leaf_text
from loreweave_parse._types import (
    Chapter,
    ParseOptions,
    Part,
    Scene,
    StructuralTree,
)


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _strip_generated_nav(body: Tag) -> None:
    """Pandoc --standalone inserts <nav class="toc">…</nav> as the first child of <body>.

    That nav contains anchors that would confuse heading detection. Remove
    in-place before walking.
    """
    for nav in body.find_all("nav", class_="toc"):
        nav.decompose()


def _heading_level(tag: Tag) -> int | None:
    """Return 1/2/3 for h1/h2/h3, else None."""
    name = tag.name
    if name in ("h1", "h2", "h3"):
        return int(name[1])
    return None


def _slice_html(elements: list[Tag | NavigableString]) -> str:
    """Concatenate the outer HTML of an ordered list of elements (skipping
    strings that are purely whitespace).
    """
    parts: list[str] = []
    for el in elements:
        if isinstance(el, NavigableString):
            s = str(el)
            if s.strip():
                parts.append(s)
        else:
            parts.append(str(el))
    return "".join(parts)


def _split_scenes_by_hr(
    elements: list[Tag | NavigableString],
    scene_break_on_hr: bool,
) -> list[list[Tag | NavigableString]]:
    """Within a chapter block, split into scene-groups on <hr/> if enabled.

    Returns a list of element-lists; each inner list is one scene's elements.
    If no <hr/> present, returns [elements] (one scene = full chapter).
    """
    if not scene_break_on_hr:
        return [elements]
    groups: list[list[Tag | NavigableString]] = [[]]
    for el in elements:
        if isinstance(el, Tag) and el.name == "hr":
            # Start a new scene group; skip the <hr/> itself.
            if groups[-1]:
                groups.append([])
            continue
        groups[-1].append(el)
    # Drop trailing empty group from a final <hr/>.
    if groups and not groups[-1]:
        groups.pop()
    return groups or [[]]


def _split_scenes_by_h3(
    elements: list[Tag | NavigableString],
) -> list[tuple[str | None, list[Tag | NavigableString]]]:
    """Within a chapter block, split into (title, elements) pairs at <h3> boundaries.

    Returns a list of (scene_title, elements). If no <h3> present, returns
    [(None, elements)] (one scene = full chapter, no title).
    """
    has_h3 = any(isinstance(el, Tag) and el.name == "h3" for el in elements)
    if not has_h3:
        return [(None, elements)]
    scenes: list[tuple[str | None, list[Tag | NavigableString]]] = []
    current_title: str | None = None
    current_elements: list[Tag | NavigableString] = []
    for el in elements:
        if isinstance(el, Tag) and el.name == "h3":
            if current_elements or current_title is not None:
                scenes.append((current_title, current_elements))
            current_title = el.get_text(strip=True) or None
            current_elements = []
        else:
            current_elements.append(el)
    scenes.append((current_title, current_elements))
    return scenes


def _build_scenes(
    chapter_elements: list[Tag | NavigableString],
    part_idx: int,
    ch_idx: int,
    options: ParseOptions,
) -> list[Scene]:
    """Build the scene list for a single chapter's body elements.

    Priority: <h3> headings first; if none, <hr/> scene breaks (if enabled);
    if none, one scene = full chapter.
    """
    h3_groups = _split_scenes_by_h3(chapter_elements)
    if len(h3_groups) > 1:
        # h3 path — each group is one scene with its title.
        scenes: list[Scene] = []
        for sc_idx, (_title, els) in enumerate(h3_groups, start=1):
            scene_html = _slice_html(els)
            leaf_text = html_to_leaf_text(scene_html)
            scenes.append(
                Scene(
                    sort_order=sc_idx,
                    path=f"book/part-{part_idx}/chapter-{ch_idx}/scene-{sc_idx}",
                    leaf_text=leaf_text,
                    content_hash=_sha256_hex(leaf_text),
                )
            )
        return scenes
    # No h3 — try hr split.
    hr_groups = _split_scenes_by_hr(chapter_elements, options.scene_break_on_hr)
    scenes = []
    for sc_idx, els in enumerate(hr_groups, start=1):
        scene_html = _slice_html(els)
        leaf_text = html_to_leaf_text(scene_html)
        scenes.append(
            Scene(
                sort_order=sc_idx,
                path=f"book/part-{part_idx}/chapter-{ch_idx}/scene-{sc_idx}",
                leaf_text=leaf_text,
                content_hash=_sha256_hex(leaf_text),
            )
        )
    return scenes


def _body_children(body: Tag) -> list[Tag | NavigableString]:
    """Direct children of <body>, in document order, dropping pure-whitespace strings."""
    out: list[Tag | NavigableString] = []
    for child in body.children:
        if isinstance(child, NavigableString):
            if str(child).strip():
                out.append(child)
        else:
            out.append(child)
    return out


def _partition_by_headings(
    elements: list[Tag | NavigableString],
) -> tuple[list[tuple[Tag, list[Tag | NavigableString]]] | None, list[Tag | NavigableString]]:
    """Partition body elements into top-level heading groups.

    Returns (groups, preamble) where:
      - groups: list of (heading_tag, content_elements) — heading is h1 or h2
        (whichever is the top level present). None when no h1/h2.
      - preamble: elements appearing before the first heading.

    Top-level chosen by: presence of any <h1> -> top is h1; else <h2> -> top is h2.
    """
    has_h1 = any(isinstance(el, Tag) and el.name == "h1" for el in elements)
    has_h2 = any(isinstance(el, Tag) and el.name == "h2" for el in elements)
    if not has_h1 and not has_h2:
        return None, elements
    top_level = "h1" if has_h1 else "h2"
    preamble: list[Tag | NavigableString] = []
    groups: list[tuple[Tag, list[Tag | NavigableString]]] = []
    current: list[Tag | NavigableString] = []
    current_heading: Tag | None = None
    for el in elements:
        if isinstance(el, Tag) and el.name == top_level:
            if current_heading is not None:
                groups.append((current_heading, current))
            elif current:
                preamble = current
            current_heading = el
            current = []
        else:
            current.append(el)
    if current_heading is not None:
        groups.append((current_heading, current))
    return groups, preamble


def parse_html(
    content: str,
    options: ParseOptions | None = None,
    filename: str | None = None,
) -> StructuralTree:
    """Parse pandoc HTML output into a StructuralTree."""
    opts = options or ParseOptions()
    soup = BeautifulSoup(content, "html.parser")

    # <body> may be absent for fragments (rare; pandoc with --standalone always emits one).
    body = soup.body
    if body is None:
        body = soup  # treat the whole soup as the body

    _strip_generated_nav(body)
    body_elements = _body_children(body)

    # Book title fallback: <head><title>, else filename without extension.
    title_tag = soup.find("title")
    book_title: str | None = None
    if title_tag is not None:
        t = title_tag.get_text(strip=True)
        if t:
            book_title = t
    if book_title is None and filename:
        book_title = filename.rsplit(".", 1)[0] or filename

    groups, preamble = _partition_by_headings(body_elements)

    if groups is None:
        # No headings at all — single-everything tree (walker_path=fallback_single).
        full_html = _slice_html(body_elements)
        leaf_text = html_to_leaf_text(full_html)
        return StructuralTree(
            source_format="html",
            walker_path="fallback_single",
            book_title=book_title,
            parts=[
                Part(
                    sort_order=1,
                    title=None,
                    path="book/part-1",
                    chapters=[
                        Chapter(
                            sort_order=1,
                            title=book_title,
                            path="book/part-1/chapter-1",
                            html=full_html,
                            scenes=[
                                Scene(
                                    sort_order=1,
                                    path="book/part-1/chapter-1/scene-1",
                                    leaf_text=leaf_text,
                                    content_hash=_sha256_hex(leaf_text),
                                )
                            ],
                        )
                    ],
                )
            ],
        )

    top_level = groups[0][0].name  # "h1" or "h2"

    # Special case: exactly one <h1> -> book title; chapters come from <h2> within.
    if top_level == "h1" and len(groups) == 1:
        h1_tag, h1_content = groups[0]
        h1_title = h1_tag.get_text(strip=True) or None
        if h1_title:
            book_title = h1_title
        # Now partition h1_content by h2.
        sub_groups, _ = _partition_by_headings(h1_content)
        if sub_groups is None:
            # Single h1, no h2 — entire content is one chapter.
            full_html = _slice_html(h1_content)
            return StructuralTree(
                source_format="html",
                walker_path="headings",
                book_title=book_title,
                parts=[
                    Part(
                        sort_order=1,
                        title=None,
                        path="book/part-1",
                        chapters=[
                            Chapter(
                                sort_order=1,
                                title=book_title,
                                path="book/part-1/chapter-1",
                                html=full_html,
                                scenes=_build_scenes(h1_content, 1, 1, opts),
                            )
                        ],
                    )
                ],
            )
        # h1 = book title; h2s = chapters under implicit part-1.
        return _build_tree_from_groups(
            part_groups=[(None, sub_groups)],
            book_title=book_title,
            opts=opts,
        )

    if top_level == "h1":
        # Multi-part book: each h1 = part; h2s within each h1 group = chapters.
        part_groups: list[tuple[str | None, list[tuple[Tag, list[Tag | NavigableString]]]]] = []
        for h1_tag, h1_content in groups:
            part_title = h1_tag.get_text(strip=True) or None
            sub_groups, _ = _partition_by_headings(h1_content)
            if sub_groups is None:
                # h1 with no h2 inside — treat the h1's content as one chapter under this part.
                # Synthesise a single-chapter group using a fake heading tag-like wrapper.
                synth: list[tuple[Tag, list[Tag | NavigableString]]] = [(h1_tag, h1_content)]
                part_groups.append((part_title, synth))
            else:
                part_groups.append((part_title, sub_groups))
        return _build_tree_from_groups(
            part_groups=part_groups,
            book_title=book_title,
            opts=opts,
        )

    # top_level == "h2": no h1 present. Treat as implicit single-part with h2 chapters.
    return _build_tree_from_groups(
        part_groups=[(None, groups)],
        book_title=book_title,
        opts=opts,
    )


def _build_tree_from_groups(
    part_groups: list[tuple[str | None, list[tuple[Tag, list[Tag | NavigableString]]]]],
    book_title: str | None,
    opts: ParseOptions,
) -> StructuralTree:
    """Assemble StructuralTree from already-partitioned part/chapter groups."""
    parts: list[Part] = []
    for part_idx, (part_title, chapter_groups) in enumerate(part_groups, start=1):
        chapters: list[Chapter] = []
        for ch_idx, (h_tag, ch_content) in enumerate(chapter_groups, start=1):
            ch_title = h_tag.get_text(strip=True) or None
            ch_html = _slice_html(ch_content)
            scenes = _build_scenes(ch_content, part_idx, ch_idx, opts)
            chapters.append(
                Chapter(
                    sort_order=ch_idx,
                    title=ch_title,
                    path=f"book/part-{part_idx}/chapter-{ch_idx}",
                    html=ch_html,
                    scenes=scenes,
                )
            )
        parts.append(
            Part(
                sort_order=part_idx,
                title=part_title,
                path=f"book/part-{part_idx}",
                chapters=chapters,
            )
        )
    return StructuralTree(
        source_format="html",
        walker_path="headings",
        book_title=book_title,
        parts=parts,
    )


__all__ = ["parse_html"]
