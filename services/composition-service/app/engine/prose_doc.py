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
