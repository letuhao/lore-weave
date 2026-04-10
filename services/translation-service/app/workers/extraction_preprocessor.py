"""
GEP-BE-07: Extraction preprocessor.

Converts Tiptap JSON to structured plain text for entity extraction.
Unlike translation pipeline's extract_translatable_text() which strips
all structure, this preserves markdown-like cues (headings, quotes, lists)
that help the LLM understand context.

Design reference: GLOSSARY_EXTRACTION_PIPELINE.md §6.3
"""
from __future__ import annotations


def tiptap_to_extraction_text(body: dict) -> str:
    """Convert Tiptap JSON to markdown-like text for extraction.

    Preserves structure cues that help LLM understand context,
    but strips all Tiptap-specific markup.

    Input:  Tiptap JSON {"type":"doc","content":[...blocks...]}
    Output: Structured plain text with minimal formatting markers
    """
    lines: list[str] = []
    for block in body.get("content", []):
        btype = block.get("type", "")

        if btype == "heading":
            level = block.get("attrs", {}).get("level", 1)
            text = _extract_text(block)
            lines.append(f"{'#' * level} {text}")
            lines.append("")

        elif btype == "paragraph":
            text = _extract_text(block)
            if text.strip():
                lines.append(text)
                lines.append("")

        elif btype == "blockquote":
            for child in block.get("content", []):
                text = _extract_text(child)
                lines.append(f"> {text}")
            lines.append("")

        elif btype in ("bulletList", "orderedList"):
            for i, li in enumerate(block.get("content", []), 1):
                text = _extract_text_from_list_item(li)
                prefix = f"{i}." if btype == "orderedList" else "-"
                lines.append(f"{prefix} {text}")
            lines.append("")

        elif btype == "callout":
            for child in block.get("content", []):
                text = _extract_text(child)
                lines.append(f"[!] {text}")
            lines.append("")

        elif btype in ("horizontalRule", "codeBlock"):
            pass  # skip non-content blocks

        elif btype in ("imageBlock", "videoBlock", "audioBlock"):
            caption = block.get("attrs", {}).get("caption", "")
            if caption:
                lines.append(f"[image: {caption}]")
                lines.append("")

        else:
            # Unknown block: try to extract text, skip if empty
            text = _extract_text(block)
            if text.strip():
                lines.append(text)
                lines.append("")

    return "\n".join(lines).strip()


def _extract_text(block: dict) -> str:
    """Extract plain text from a block's inline content. Strips all marks."""
    parts: list[str] = []
    for node in block.get("content", []):
        if node.get("type") == "hardBreak":
            parts.append("\n")
        elif node.get("type") == "text":
            parts.append(node.get("text", ""))
    return "".join(parts)


def _extract_text_from_list_item(li: dict) -> str:
    """Extract text from a Tiptap listItem node.

    A listItem wraps one or more paragraph/blockquote children.
    Nested lists are flattened (depth > 1 is rare in novels).
    """
    parts: list[str] = []
    for child in li.get("content", []):
        ctype = child.get("type", "")
        if ctype in ("paragraph", "blockquote"):
            parts.append(_extract_text(child))
        elif ctype in ("bulletList", "orderedList"):
            for nested_li in child.get("content", []):
                parts.append(_extract_text_from_list_item(nested_li))
    return " ".join(p for p in parts if p.strip())


def prepare_chapter_text(chapter: dict) -> str:
    """Convert chapter content to plain text for extraction prompt."""
    body = chapter.get("body")
    if isinstance(body, dict) and isinstance(body.get("content"), list):
        return tiptap_to_extraction_text(body)
    return chapter.get("text_content", "")
