"""Plain prose → Tiptap doc (LOOM chapter-assembly-modes, B3 persistence / MED-2).

book-service's chapter-draft PATCH stores the body verbatim and does NOT convert
plain text → Tiptap (its `plainTextToTiptapJSON` runs only on import/create). So
to write an AI-assembled chapter into the book draft, composition must build the
SAME doc shape book-service produces, including the top-level `_text` snapshot the
`chapter_blocks` extraction trigger reads via JSON_TABLE.

This MIRRORS services/book-service/internal/api/tiptap.go — keep them in lockstep
(a divergence silently breaks downstream extraction / the editor's plain-text
projection). The unit test pins the exact shape.

F4 (D-SCENEMARKER-EMIT): generated prose carries ATX `### <scene title>` lines.
Leading heading lines per block are lifted into heading nodes (tiptap.go's
`tiptapHeadingNode` shape); when the caller supplies the chapter's scenes, a
heading whose normalized title UNIQUELY matches a scene title gets
`attrs.sceneId` — the same marker the FE `SceneAnchorExtension` declares, so the
Scene Rail / navigator jump lands without a manual ⚓ backfill. The block
remainder keeps the original paragraph shape byte-identical (intra-block
newlines preserved — deliberately NOT tiptap.go's markdown line-join, which
would reshape existing prose).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# tiptap.go atxHeadingRe: a leading Markdown ATX heading line (#, ##, ### ...).
ATX_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")

# Port of the FE normalizeTitle (SceneAnchor.ts) — keep in lockstep. Diacritics
# are PRESERVED (Vietnamese tone marks are significant); only case, whitespace
# runs, and trailing punctuation are folded.
_WS_RE = re.compile(r"[\s ]+")
_TRAILING_PUNCT_RE = re.compile(r"[\s.,:;!?…–—-]+$")


def normalize_title(s: str) -> str:
    """NFC → casefold-lower → collapse whitespace → strip trailing punctuation."""
    s = unicodedata.normalize("NFC", s).lower()
    s = _WS_RE.sub(" ", s)
    s = _TRAILING_PUNCT_RE.sub("", s)
    return s.strip()


def _heading_node(level: int, text: str) -> dict[str, Any]:
    """tiptap.go tiptapHeadingNode — level clamped to 3 (StarterKit config)."""
    return {
        "type": "heading",
        "attrs": {"level": min(level, 3)},
        "_text": text,
        "content": [{"type": "text", "text": text}],
    }


def _attach_scene_ids(nodes: list[dict[str, Any]], scenes: list[dict[str, Any]]) -> None:
    """Set `attrs.sceneId` on headings whose normalized text uniquely matches a
    scene title — the FE applySceneAnchors algorithm: a scene anchors only when
    EXACTLY ONE free heading carries its title, and a heading anchors at most
    once. Ambiguous/unmatched stay unmarked (never a wrong marker)."""
    free_by_text: dict[str, list[dict[str, Any]]] = {}
    for n in nodes:
        if n.get("type") != "heading":
            continue
        key = normalize_title(n.get("_text") or "")
        if key:
            free_by_text.setdefault(key, []).append(n)
    for scene in scenes:
        scene_id, title = scene.get("id"), scene.get("title")
        if not scene_id or not title:
            continue
        key = normalize_title(str(title))
        candidates = free_by_text.get(key)
        if candidates and len(candidates) == 1:
            candidates[0]["attrs"]["sceneId"] = str(scene_id)
            del free_by_text[key]  # a heading anchors at most once


def text_to_tiptap_doc(
    text: str, scenes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Convert plain prose into a Tiptap `{type:'doc', content:[…]}`.

    Each paragraph (split on a blank line) becomes a paragraph node carrying a
    top-level `_text` snapshot. An empty paragraph → `{type:'paragraph',
    _text:''}` (no content), matching book-service's tiptap.go byte-for-byte.
    LEADING ATX heading lines in a block become heading nodes (tiptap.go's
    markdown variant); with `scenes` ([{id, title}]), a unique title match sets
    `attrs.sceneId` (F4 scene-marker emit)."""
    text = text.replace("\r\n", "\n")
    nodes: list[dict[str, Any]] = []
    for p in text.split("\n\n"):
        p = p.rstrip("\n")
        if p == "":
            nodes.append({"type": "paragraph", "_text": ""})
            continue
        lines = p.split("\n")
        i = 0
        # Leading heading lines become heading nodes (handles "### Title" on its
        # own block AND "### Title\nprose..." in one block) — tiptap.go loop.
        while i < len(lines):
            m = ATX_HEADING_RE.match(lines[i].strip())
            if m is None:
                break
            nodes.append(_heading_node(len(m.group(1)), m.group(2).strip()))
            i += 1
        if i == 0:
            para = p  # no heading — keep the whole block byte-identical
        else:
            para = "\n".join(lines[i:]).strip("\n")
            if para == "":
                continue
        nodes.append({
            "type": "paragraph",
            "_text": para,
            "content": [{"type": "text", "text": para}],
        })
    if scenes:
        _attach_scene_ids(nodes, scenes)
    return {"type": "doc", "content": nodes}


def tiptap_doc_to_text(doc: Any) -> str:
    """C27 — flatten a Tiptap `{type:'doc', content:[…]}` draft back to plain prose
    for extraction. Reads the top-level `_text` snapshot per block (the same field
    `text_to_tiptap_doc` / book-service's tiptap.go write), falling back to walking
    `content[].text` for blocks that lack a snapshot (e.g. imported docs). Blocks
    are joined by a blank line, mirroring the paragraph split on the way in.

    Degrade-safe: a non-dict / missing-content doc → "" (the caller skips a
    flywheel dispatch on empty text rather than 500-ing)."""
    if not isinstance(doc, dict):
        return ""
    blocks = doc.get("content")
    if not isinstance(blocks, list):
        return ""
    out: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        snapshot = block.get("_text")
        if isinstance(snapshot, str):
            out.append(snapshot)
            continue
        # Fallback: concatenate inline text runs for a block with no snapshot.
        runs = block.get("content")
        if isinstance(runs, list):
            parts = [
                r.get("text", "") for r in runs
                if isinstance(r, dict) and isinstance(r.get("text"), str)
            ]
            out.append("".join(parts))
    return "\n\n".join(out).strip()
