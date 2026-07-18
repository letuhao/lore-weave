"""Tiptap (ProseMirror) walker — spec 26 IX-6.

Walks a Tiptap `{type:'doc', content:[…]}` document (the chapter body the
studio editor persists) and produces the same StructuralTree shape as the HTML
walker — book -> part -> chapter -> scene — using **identical heading/`hr` scene
splits** (SCOPE-4: scene-splitting exists once, in this SDK, so import and
re-parse can never disagree about where a scene starts). The one addition over
the HTML walker is `Scene.anchor_scene_id`: each scene carries the
`data-scene-id` (ProseMirror `attrs.sceneId`) of the heading that opens it, so
book-service's re-parser can back-link `scenes.source_scene_id` (IX-5 rule 1).

Node mapping (mirrors html_walker's h1/h2/h3):
- heading level 1 = part, level 2 = chapter, level 3 = scene-within-chapter.
- `horizontalRule` within a chapter = scene break (configurable, like `<hr/>`).
- Single top-level heading level 1 = book title.
- No structural heading -> single-everything tree (walker_path=fallback_single).

Additive + pure: `anchor_scene_id` defaults None, so nothing about the html /
plain paths changes; no HTTP, no LLM, no DB (spec D9).
"""

from __future__ import annotations

import hashlib
import json
import re

from loreweave_parse._types import (
    Chapter,
    ParseOptions,
    Part,
    Scene,
    StructuralTree,
)

# Runs of >1 blank line collapse to exactly one — mirrors _text_strip's canary.
_WS_RUN = re.compile(r"\n[ \t]*(?:\n[ \t]*)+")

# ProseMirror inline leaf types (a text-block's only permitted children).
_INLINE_TYPES = frozenset({"text", "hardBreak"})

# Tiptap StarterKit's rule node; a couple of aliases for robustness.
_HR_TYPES = frozenset({"horizontalRule", "horizontal_rule", "hr"})

# A ``Node`` here is always a ProseMirror node dict.
Node = dict


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _load_doc(content: str) -> Node:
    """Parse the tiptap JSON string into a ProseMirror doc dict.

    Raises ValueError (→ 400 at the router) on malformed JSON or a non-object.
    """
    try:
        doc = json.loads(content)
    except (json.JSONDecodeError, TypeError) as e:
        raise ValueError(f"tiptap content is not valid JSON: {e}") from e
    if not isinstance(doc, dict):
        raise ValueError("tiptap content must be a JSON object (a ProseMirror doc)")
    return doc


def _top_blocks(doc: Node) -> list[Node]:
    """The doc's top-level block nodes, dropping any non-dict entries."""
    content = doc.get("content")
    if not isinstance(content, list):
        return []
    return [b for b in content if isinstance(b, dict)]


def _heading_level(node: Node) -> int | None:
    """Return 1/2/3 for a structural heading node, else None.

    Levels beyond 3 (and non-heading nodes) are None — treated as ordinary
    content, exactly as html_walker treats <h4>-<h6>.
    """
    if not isinstance(node, dict) or node.get("type") != "heading":
        return None
    attrs = node.get("attrs")
    level = attrs.get("level", 1) if isinstance(attrs, dict) else 1
    if isinstance(level, bool):  # bool is an int subclass — reject it
        return None
    if isinstance(level, int) and level in (1, 2, 3):
        return level
    return None


def _is_hr(node: Node) -> bool:
    return isinstance(node, dict) and node.get("type") in _HR_TYPES


def _scene_id(node: Node | None) -> str | None:
    """The opening heading's scene anchor: ProseMirror `attrs.sceneId`
    (falls back to the HTML-rendered `data-scene-id` for robustness)."""
    if not isinstance(node, dict):
        return None
    attrs = node.get("attrs")
    if not isinstance(attrs, dict):
        return None
    sid = attrs.get("sceneId")
    if sid is None:
        sid = attrs.get("data-scene-id")
    if sid is None:
        return None
    s = str(sid).strip()
    return s or None


def _block_text(node: Node) -> str:
    """Plain text of one block node.

    Prefers the top-level `_text` snapshot book-service/composition write on
    every block (keeps parity with the repo's other tiptap→text extractors),
    else concatenates inline text runs (`hardBreak` -> newline), recursing into
    container blocks (blockquote / lists) so nested prose is never dropped.
    """
    if not isinstance(node, dict):
        return ""
    snapshot = node.get("_text")
    if isinstance(snapshot, str):
        return snapshot
    content = node.get("content")
    if not isinstance(content, list):
        return ""
    # Text block: inline children only.
    if all(isinstance(c, dict) and c.get("type") in _INLINE_TYPES for c in content):
        parts: list[str] = []
        for c in content:
            if c.get("type") == "text":
                txt = c.get("text")
                if isinstance(txt, str):
                    parts.append(txt)
            elif c.get("type") == "hardBreak":
                parts.append("\n")
        return "".join(parts)
    # Container block: recurse over child blocks, joining with a blank line.
    child_texts: list[str] = []
    for c in content:
        if isinstance(c, dict):
            ct = _block_text(c)
            if ct.strip():
                child_texts.append(ct)
    return "\n\n".join(child_texts)


def _heading_title(node: Node | None) -> str | None:
    if not isinstance(node, dict):
        return None
    return _block_text(node).strip() or None


def _leaf_text(blocks: list[Node]) -> str:
    """Join a scene's block nodes into leaf text, mirroring html_to_leaf_text's
    tail: blocks separated by a blank line, runs of blank lines collapsed."""
    out: list[str] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        t = _block_text(b)
        if t.strip():
            out.append(t)
    joined = "\n\n".join(out)
    collapsed = _WS_RUN.sub("\n\n", joined)
    return collapsed.strip()


def _split_scenes_by_h3(
    boundary_heading: Node | None,
    blocks: list[Node],
) -> list[tuple[Node | None, list[Node]]]:
    """Split a chapter's blocks into (opening_heading, blocks) pairs at level-3
    heading boundaries.

    The preamble group (content before the first h3) opens under the chapter's
    own heading. If no h3 is present, returns a single (boundary, blocks) group.
    """
    has_h3 = any(_heading_level(b) == 3 for b in blocks)
    if not has_h3:
        return [(boundary_heading, blocks)]
    groups: list[tuple[Node | None, list[Node]]] = []
    current_heading: Node | None = None
    current: list[Node] = []
    for b in blocks:
        if _heading_level(b) == 3:
            if current or current_heading is not None:
                groups.append((current_heading, current))
            current_heading = b
            current = []
        else:
            current.append(b)
    groups.append((current_heading, current))
    # The preamble group opens under the chapter heading, not "no heading".
    if groups and groups[0][0] is None:
        groups[0] = (boundary_heading, groups[0][1])
    return groups


def _split_scenes_by_hr(
    blocks: list[Node],
    scene_break_on_hr: bool,
) -> list[list[Node]]:
    """Split a chapter's blocks into scene-groups on `horizontalRule` if enabled."""
    if not scene_break_on_hr:
        return [blocks]
    groups: list[list[Node]] = [[]]
    for b in blocks:
        if _is_hr(b):
            if groups[-1]:
                groups.append([])
            continue
        groups[-1].append(b)
    if groups and not groups[-1]:
        groups.pop()
    return groups or [[]]


def _build_scenes(
    boundary_heading: Node | None,
    chapter_blocks: list[Node],
    part_idx: int,
    ch_idx: int,
    options: ParseOptions,
) -> list[Scene]:
    """Build a chapter's scene list. Priority: h3 headings; else `horizontalRule`
    breaks; else one scene = whole chapter. Each scene carries its opening
    heading's anchor (IX-6)."""

    def _make(sc_idx: int, opening: Node | None, blocks: list[Node]) -> Scene:
        leaf_text = _leaf_text(blocks)
        return Scene(
            sort_order=sc_idx,
            path=f"book/part-{part_idx}/chapter-{ch_idx}/scene-{sc_idx}",
            leaf_text=leaf_text,
            content_hash=_sha256_hex(leaf_text),
            anchor_scene_id=_scene_id(opening),
        )

    h3_groups = _split_scenes_by_h3(boundary_heading, chapter_blocks)
    if len(h3_groups) > 1:
        return [
            _make(sc_idx, opening, blocks)
            for sc_idx, (opening, blocks) in enumerate(h3_groups, start=1)
        ]
    # No h3 split — the chapter heading opens scene 1; hr breaks open the rest.
    hr_groups = _split_scenes_by_hr(chapter_blocks, options.scene_break_on_hr)
    return [
        _make(sc_idx, boundary_heading if sc_idx == 1 else None, blocks)
        for sc_idx, blocks in enumerate(hr_groups, start=1)
    ]


def _partition_by_headings(
    blocks: list[Node],
) -> tuple[list[tuple[Node, list[Node]]] | None, list[Node]]:
    """Partition blocks into top-level heading groups.

    Returns (groups, preamble): groups is a list of (heading_node, content),
    keyed on the top level present (level 1 if any, else level 2); None when no
    level-1/level-2 heading exists. `preamble` is the content before the first
    such heading.
    """
    has_h1 = any(_heading_level(b) == 1 for b in blocks)
    has_h2 = any(_heading_level(b) == 2 for b in blocks)
    if not has_h1 and not has_h2:
        return None, blocks
    top_level = 1 if has_h1 else 2
    preamble: list[Node] = []
    groups: list[tuple[Node, list[Node]]] = []
    current: list[Node] = []
    current_heading: Node | None = None
    for b in blocks:
        if _heading_level(b) == top_level:
            if current_heading is not None:
                groups.append((current_heading, current))
            elif current:
                preamble = current
            current_heading = b
            current = []
        else:
            current.append(b)
    if current_heading is not None:
        groups.append((current_heading, current))
    return groups, preamble


def _build_tree_from_groups(
    part_groups: list[tuple[str | None, list[tuple[Node, list[Node]]]]],
    book_title: str | None,
    opts: ParseOptions,
) -> StructuralTree:
    """Assemble StructuralTree from already-partitioned part/chapter groups."""
    parts: list[Part] = []
    for part_idx, (part_title, chapter_groups) in enumerate(part_groups, start=1):
        chapters: list[Chapter] = []
        for ch_idx, (h_node, ch_content) in enumerate(chapter_groups, start=1):
            chapters.append(
                Chapter(
                    sort_order=ch_idx,
                    title=_heading_title(h_node),
                    path=f"book/part-{part_idx}/chapter-{ch_idx}",
                    html="",  # tiptap source has no post-pandoc HTML slice; re-parse reads scenes.
                    scenes=_build_scenes(h_node, ch_content, part_idx, ch_idx, opts),
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
        source_format="tiptap",
        walker_path="headings",
        book_title=book_title,
        parts=parts,
    )


def _fallback_single(blocks: list[Node], book_title: str | None) -> StructuralTree:
    leaf_text = _leaf_text(blocks)
    return StructuralTree(
        source_format="tiptap",
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
                        html="",
                        scenes=[
                            Scene(
                                sort_order=1,
                                path="book/part-1/chapter-1/scene-1",
                                leaf_text=leaf_text,
                                content_hash=_sha256_hex(leaf_text),
                                anchor_scene_id=None,
                            )
                        ],
                    )
                ],
            )
        ],
    )


def parse_tiptap(
    content: str,
    options: ParseOptions | None = None,
    filename: str | None = None,
) -> StructuralTree:
    """Parse a Tiptap ProseMirror doc into a StructuralTree (spec 26 IX-6)."""
    opts = options or ParseOptions()
    doc = _load_doc(content)
    blocks = _top_blocks(doc)

    # Tiptap has no <head><title>; book_title falls back to the filename only.
    book_title: str | None = None
    if filename:
        book_title = filename.rsplit(".", 1)[0] or filename

    groups, _preamble = _partition_by_headings(blocks)

    if groups is None:
        return _fallback_single(blocks, book_title)

    top_level = _heading_level(groups[0][0])  # 1 or 2

    # Single level-1 heading -> book title; chapters come from level-2 within.
    if top_level == 1 and len(groups) == 1:
        h1_node, h1_content = groups[0]
        h1_title = _heading_title(h1_node)
        if h1_title:
            book_title = h1_title
        sub_groups, _ = _partition_by_headings(h1_content)
        if sub_groups is None:
            # Single level-1, no level-2 — the whole content is one chapter.
            return StructuralTree(
                source_format="tiptap",
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
                                html="",
                                scenes=_build_scenes(h1_node, h1_content, 1, 1, opts),
                            )
                        ],
                    )
                ],
            )
        # level-1 = book title; level-2s = chapters under an implicit part-1.
        return _build_tree_from_groups(
            part_groups=[(None, sub_groups)],
            book_title=book_title,
            opts=opts,
        )

    if top_level == 1:
        # Multi-part book: each level-1 = part; level-2s within = chapters.
        part_groups: list[tuple[str | None, list[tuple[Node, list[Node]]]]] = []
        for h1_node, h1_content in groups:
            part_title = _heading_title(h1_node)
            sub_groups, _ = _partition_by_headings(h1_content)
            if sub_groups is None:
                # level-1 with no level-2 inside — its content is one chapter.
                part_groups.append((part_title, [(h1_node, h1_content)]))
            else:
                part_groups.append((part_title, sub_groups))
        return _build_tree_from_groups(
            part_groups=part_groups,
            book_title=book_title,
            opts=opts,
        )

    # top_level == 2: no level-1 present. Implicit single-part with level-2 chapters.
    return _build_tree_from_groups(
        part_groups=[(None, groups)],
        book_title=book_title,
        opts=opts,
    )


__all__ = ["parse_tiptap"]
