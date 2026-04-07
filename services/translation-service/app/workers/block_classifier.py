"""
Block classifier for Tiptap JSON translation.

Classifies each block as:
- 'translate'    — text content should be translated (paragraph, heading, etc.)
- 'passthrough'  — keep as-is (horizontalRule, codeBlock)
- 'caption_only' — translate only the caption attr (imageBlock, videoBlock, audioBlock)

Also handles inline mark serialization: Tiptap marks ↔ markdown-ish text
for round-trip through the LLM.
"""
from __future__ import annotations

import copy
import re
from typing import Literal

BlockAction = Literal["translate", "passthrough", "caption_only"]

# Block types that contain translatable text content
_TRANSLATE_TYPES = frozenset({
    "paragraph", "heading", "blockquote", "callout",
    "bulletList", "orderedList", "listItem",
})

# Block types to pass through unchanged
_PASSTHROUGH_TYPES = frozenset({
    "horizontalRule", "codeBlock",
})

# Block types where only the caption attribute should be translated
_CAPTION_ONLY_TYPES = frozenset({
    "imageBlock", "videoBlock", "audioBlock",
})


def classify_block(block: dict) -> BlockAction:
    """Classify a top-level Tiptap block by its type."""
    btype = block.get("type", "")
    if btype in _PASSTHROUGH_TYPES:
        return "passthrough"
    if btype in _CAPTION_ONLY_TYPES:
        return "caption_only"
    if btype in _TRANSLATE_TYPES:
        return "translate"
    # Unknown block types: pass through to be safe
    return "passthrough"


# ── Inline mark serialization ────────────────────────────────────────────────

def _inline_to_text(content: list[dict] | None) -> str:
    """Convert Tiptap inline content array to markdown-ish text.

    Marks are serialized as:
      bold      → **text**
      italic    → *text*
      code      → `text`
      strike    → ~~text~~
      underline → __text__
      link      → [text](href)

    Nested marks are applied from outermost to innermost.
    """
    if not content:
        return ""
    parts = []
    for node in content:
        if node.get("type") == "hardBreak":
            parts.append("\n")
            continue
        text = node.get("text", "")
        marks = node.get("marks", [])
        for mark in reversed(marks):
            mtype = mark.get("type", "")
            if mtype == "bold":
                text = f"**{text}**"
            elif mtype == "italic":
                text = f"*{text}*"
            elif mtype == "code":
                text = f"`{text}`"
            elif mtype == "strike":
                text = f"~~{text}~~"
            elif mtype == "underline":
                text = f"__{text}__"
            elif mtype == "link":
                href = mark.get("attrs", {}).get("href", "")
                text = f"[{text}]({href})"
        parts.append(text)
    return "".join(parts)


def _text_to_inline(text: str, original_content: list[dict] | None = None) -> list[dict]:
    """Convert markdown-ish text back to Tiptap inline content array.

    Parses: **bold**, *italic*, `code`, ~~strike~~, __underline__, [text](url)

    Falls back to plain text node if parsing produces nothing.
    """
    if not text:
        return []

    nodes: list[dict] = []
    # Regex for inline marks — order matters (longer patterns first)
    pattern = re.compile(
        r'\*\*(.+?)\*\*'        # **bold**
        r'|__(.+?)__'           # __underline__
        r'|~~(.+?)~~'           # ~~strike~~
        r'|\*(.+?)\*'           # *italic*
        r'|`(.+?)`'             # `code`
        r'|\[(.+?)\]\((.+?)\)'  # [text](url)
    )

    pos = 0
    for m in pattern.finditer(text):
        # Add plain text before this match
        if m.start() > pos:
            plain = text[pos:m.start()]
            if plain:
                nodes.append({"type": "text", "text": plain})

        if m.group(1) is not None:  # **bold**
            nodes.append({"type": "text", "text": m.group(1), "marks": [{"type": "bold"}]})
        elif m.group(2) is not None:  # __underline__
            nodes.append({"type": "text", "text": m.group(2), "marks": [{"type": "underline"}]})
        elif m.group(3) is not None:  # ~~strike~~
            nodes.append({"type": "text", "text": m.group(3), "marks": [{"type": "strike"}]})
        elif m.group(4) is not None:  # *italic*
            nodes.append({"type": "text", "text": m.group(4), "marks": [{"type": "italic"}]})
        elif m.group(5) is not None:  # `code`
            nodes.append({"type": "text", "text": m.group(5), "marks": [{"type": "code"}]})
        elif m.group(6) is not None:  # [text](url)
            nodes.append({
                "type": "text",
                "text": m.group(6),
                "marks": [{"type": "link", "attrs": {"href": m.group(7)}}],
            })
        pos = m.end()

    # Trailing plain text
    if pos < len(text):
        remaining = text[pos:]
        if remaining:
            nodes.append({"type": "text", "text": remaining})

    # Handle newlines → hardBreak
    expanded: list[dict] = []
    for node in nodes:
        t = node.get("text", "")
        if "\n" in t and node.get("type") == "text":
            parts = t.split("\n")
            for i, part in enumerate(parts):
                if part:
                    n = {"type": "text", "text": part}
                    if "marks" in node:
                        n["marks"] = node["marks"]
                    expanded.append(n)
                if i < len(parts) - 1:
                    expanded.append({"type": "hardBreak"})
        else:
            expanded.append(node)

    return expanded if expanded else [{"type": "text", "text": text}]


# ── Block text extraction ────────────────────────────────────────────────────

def extract_translatable_text(block: dict) -> str:
    """Extract translatable text from a block as markdown-ish string.

    For text blocks: serializes inline content with marks.
    For list blocks: joins list items with newlines.
    For caption_only blocks: returns the caption attribute.
    """
    action = classify_block(block)
    btype = block.get("type", "")

    if action == "caption_only":
        return block.get("attrs", {}).get("caption", "") or ""

    if action == "passthrough":
        return ""

    # List blocks: recurse into listItem → paragraph
    if btype in ("bulletList", "orderedList"):
        items = []
        for li in block.get("content", []):
            li_parts = []
            for child in li.get("content", []):
                li_parts.append(_inline_to_text(child.get("content")))
            items.append(" ".join(li_parts))
        return "\n".join(items)

    # Callout: may have nested paragraphs
    if btype == "callout":
        parts = []
        for child in block.get("content", []):
            parts.append(_inline_to_text(child.get("content")))
        return "\n".join(parts)

    # Blockquote: may have nested paragraphs
    if btype == "blockquote":
        parts = []
        for child in block.get("content", []):
            parts.append(_inline_to_text(child.get("content")))
        return "\n".join(parts)

    # Simple text blocks: paragraph, heading
    return _inline_to_text(block.get("content"))


# ── Block rebuilding ─────────────────────────────────────────────────────────

def rebuild_block(original: dict, translated_text: str) -> dict:
    """Rebuild a block with translated text, preserving structure.

    Returns a deep copy of the original with text content replaced.
    """
    block = copy.deepcopy(original)
    action = classify_block(block)
    btype = block.get("type", "")

    if action == "passthrough":
        return block

    if action == "caption_only":
        if "attrs" not in block:
            block["attrs"] = {}
        block["attrs"]["caption"] = translated_text
        return block

    # List blocks
    if btype in ("bulletList", "orderedList"):
        lines = translated_text.split("\n")
        items = block.get("content", [])
        for i, li in enumerate(items):
            if i < len(lines):
                for child in li.get("content", []):
                    child["content"] = _text_to_inline(lines[i])
        return block

    # Callout / blockquote with nested paragraphs
    if btype in ("callout", "blockquote"):
        lines = translated_text.split("\n")
        children = block.get("content", [])
        for i, child in enumerate(children):
            if i < len(lines):
                child["content"] = _text_to_inline(lines[i])
        return block

    # Simple text blocks: paragraph, heading
    block["content"] = _text_to_inline(translated_text)

    # Update _text snapshot if present
    if block.get("attrs", {}).get("_text") is not None:
        block["attrs"]["_text"] = translated_text

    return block
