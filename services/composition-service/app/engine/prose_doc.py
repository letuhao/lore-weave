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


def _block_text(block: dict[str, Any]) -> str:
    """One block's plain text — the same `_text`-snapshot-then-inline-runs order
    `tiptap_doc_to_text` uses, so the two can never disagree about emptiness."""
    snapshot = block.get("_text")
    if isinstance(snapshot, str):
        return snapshot
    runs = block.get("content")
    if isinstance(runs, list):
        return "".join(
            r.get("text", "") for r in runs
            if isinstance(r, dict) and isinstance(r.get("text"), str)
        )
    return ""


def scene_prose_presence(
    doc: Any, scenes: list[dict[str, Any]],
) -> dict[str, int]:
    """T8 — which scenes actually have PROSE under them in the saved manuscript.

    Returns ``{scene_id: word_count}`` for scenes with a non-empty body, keyed by
    the scene ids in ``scenes`` (``[{"id", "title"}, …]``). A scene with a heading
    but nothing under it is ABSENT from the result, not present-with-zero — the
    caller's question is "is this written", and an empty section is not.

    WHY THIS EXISTS. Conformance had two ways to call a scene realized and a human
    could reach neither: a completed per-scene ``generation_job`` (only an automated
    generation path creates one) and ``outline_node.written_*`` (only a book-service
    parse/import populates it). An author who drafted in chat and pasted into the
    editor — the path a 2026-09-06 run used for an entire 5-arc novel — got
    "Not written yet" on every finished scene. This reads the manuscript itself, so
    prose counts as prose regardless of who typed it.

    Anchoring deliberately reuses ``_attach_scene_ids``' rules rather than
    re-deriving them: a heading anchors a scene only when EXACTLY ONE free heading
    carries that title, and it anchors at most once. Matching those rules matters
    more than matching more scenes — the editor draws its own anchors the same way,
    so a looser rule here would report a scene as written that the author's own
    Scene Rail shows as unanchored.

    A scene's body runs from its heading to the next HEADING OF THE SAME OR HIGHER
    level (a deeper heading is a subsection of this scene, not the start of the
    next one)."""
    if not isinstance(doc, dict):
        return {}
    blocks = doc.get("content")
    if not isinstance(blocks, list):
        return {}

    # Work on a shallow copy: _attach_scene_ids MUTATES attrs, and this is a read.
    nodes = [dict(b) for b in blocks if isinstance(b, dict)]
    for n in nodes:
        n["attrs"] = dict(n.get("attrs") or {})
        if n.get("type") == "heading" and "_text" not in n:
            n["_text"] = _block_text(n)

    # Honour ids the document already carries (the editor writes them on save);
    # fall back to title matching for a document that predates them.
    already = {
        str(n["attrs"].get("sceneId")) for n in nodes
        if n.get("type") == "heading" and n["attrs"].get("sceneId")
    }
    unresolved = [s for s in scenes if str(s.get("id")) not in already]
    if unresolved:
        _attach_scene_ids(nodes, unresolved)

    wanted = {str(s.get("id")) for s in scenes if s.get("id")}
    out: dict[str, int] = {}
    i = 0
    while i < len(nodes):
        node = nodes[i]
        scene_id = node["attrs"].get("sceneId") if node.get("type") == "heading" else None
        if not scene_id or str(scene_id) not in wanted:
            i += 1
            continue
        level = int(node.get("attrs", {}).get("level") or 1)
        words = 0
        j = i + 1
        while j < len(nodes):
            nxt = nodes[j]
            if nxt.get("type") == "heading":
                nxt_level = int(nxt.get("attrs", {}).get("level") or 1)
                if nxt_level <= level:
                    break
                # A SUB-heading belongs to this scene, but its title is not prose. Counting it
                # would let a scene containing nothing but a sub-heading read as written — the
                # same false positive the bare-heading case guards against, one level down.
                j += 1
                continue
            words += len(_block_text(nxt).split())
            j += 1
        if words > 0:
            out[str(scene_id)] = words
        i = j if j > i else i + 1
    return out
