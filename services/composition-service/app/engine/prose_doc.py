"""Plain prose → Tiptap doc (LOOM chapter-assembly-modes, B3 persistence / MED-2).

book-service's chapter-draft PATCH stores the body verbatim and does NOT convert
plain text → Tiptap (its `plainTextToTiptapJSON` runs only on import/create). So
to write an AI-assembled chapter into the book draft, composition must build the
SAME doc shape book-service produces, including the top-level `_text` snapshot the
`chapter_blocks` extraction trigger reads via JSON_TABLE.

This MIRRORS services/book-service/internal/api/tiptap.go — keep them in lockstep
(a divergence silently breaks downstream extraction / the editor's plain-text
projection). The unit test pins the exact shape.
"""

from __future__ import annotations

from typing import Any


def text_to_tiptap_doc(text: str) -> dict[str, Any]:
    """Convert plain prose into a Tiptap `{type:'doc', content:[paragraph…]}`.

    Each paragraph (split on a blank line) becomes a paragraph node carrying a
    top-level `_text` snapshot. An empty paragraph → `{type:'paragraph',
    _text:''}` (no content), matching book-service's tiptap.go byte-for-byte."""
    text = text.replace("\r\n", "\n")
    nodes: list[dict[str, Any]] = []
    for p in text.split("\n\n"):
        p = p.rstrip("\n")
        if p == "":
            nodes.append({"type": "paragraph", "_text": ""})
            continue
        nodes.append({
            "type": "paragraph",
            "_text": p,
            "content": [{"type": "text", "text": p}],
        })
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
