"""Deterministic IR → render-target mappers (M0 / Phase-1 §C3).

  - :func:`ir_to_tiptap`    — the STORED body (TipTap ProseMirror JSON the FE reader
                              already consumes); citations become a ``citation`` mark
                              (the anti-hallucination provenance — FE extension is M7a).
  - :func:`ir_to_markdown`  — for feedback-gold before/after diffs (§4.11); round-trips
                              with the parser (emits the ORIGINAL cite_id labels, not
                              the display numbers).
  - :func:`ir_to_plaintext` — for search / embedding (lossy-ok).

Citation display numbers are assigned by FIRST APPEARANCE in the body (standard refs);
the inline marker shows ``[n]`` while the ``citation`` mark carries the structured source
(``cite_id``/``chapter_id``/``block_index``/``snippet``..) the FE resolves to a hover-preview
+ jump-to-source. The jump URL is built FE-side (it knows the book context); the mark only
carries ``chapter_id`` + ``block_index``.
"""

from __future__ import annotations

from typing import Any

from app.wiki.ir import Span, WikiArticleIR

_REFERENCES_HEADING = "引用来源 · References"


def _number_citations(ir: WikiArticleIR) -> dict[str, int]:
    """cite_id → 1-based display number, in first-appearance order over the body."""
    order: dict[str, int] = {}
    for b in ir.blocks:
        for sp in b.all_spans():
            for cid in sp.cites:
                if cid not in order and ir.source_by_id(cid) is not None:
                    order[cid] = len(order) + 1
    return order


# ── IR → TipTap ──────────────────────────────────────────────────────────────

def _inline_nodes(spans: list[Span], ir: WikiArticleIR, num: dict[str, int]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for sp in spans:
        if sp.text:
            nodes.append({"type": "text", "text": sp.text})
        for cid in sp.cites:
            n = num.get(cid)
            src = ir.source_by_id(cid)
            if n is None or src is None:
                continue
            nodes.append({
                "type": "text",
                "text": f"[{n}]",
                "marks": [
                    {"type": "citation", "attrs": {
                        "cite_id": cid,
                        "n": n,
                        "source_type": src.kind,
                        "chapter_id": src.chapter_id,
                        "block_index": src.block_index,
                        "score": src.score,
                        "snippet": src.snippet,
                    }},
                    {"type": "superscript"},
                ],
            })
    return nodes


def _paragraph(spans: list[Span], ir: WikiArticleIR, num: dict[str, int]) -> dict[str, Any]:
    content = _inline_nodes(spans, ir, num)
    node: dict[str, Any] = {"type": "paragraph"}
    if content:
        node["content"] = content
    return node


def _references_nodes(ir: WikiArticleIR, num: dict[str, int]) -> list[dict[str, Any]]:
    if not num:
        return []
    items: list[dict[str, Any]] = []
    for cid, n in sorted(num.items(), key=lambda kv: kv[1]):
        src = ir.source_by_id(cid)
        if src is None:
            continue
        label = src.snippet or (
            f"chapter {src.chapter_id} · block {src.block_index}"
            if src.chapter_id is not None else src.kind
        )
        items.append({
            "type": "listItem",
            "content": [{
                "type": "paragraph",
                "content": [{
                    "type": "text",
                    "text": f"[{n}] {label}",
                    "marks": [{"type": "citation", "attrs": {
                        "cite_id": cid, "n": n, "source_type": src.kind,
                        "chapter_id": src.chapter_id, "block_index": src.block_index,
                        "score": src.score, "snippet": src.snippet,
                    }}],
                }],
            }],
        })
    return [
        {"type": "heading", "attrs": {"level": 2},
         "content": [{"type": "text", "text": _REFERENCES_HEADING}]},
        {"type": "bulletList", "content": items},
    ]


def ir_to_tiptap(ir: WikiArticleIR) -> dict[str, Any]:
    """Map the IR to a TipTap ``doc`` (the stored ``body_json``)."""
    num = _number_citations(ir)
    content: list[dict[str, Any]] = []
    for b in ir.blocks:
        if b.type in ("lead", "paragraph"):
            content.append(_paragraph(b.spans, ir, num))
        elif b.type == "heading":
            content.append({
                "type": "heading", "attrs": {"level": b.level or 2},
                "content": _inline_nodes(b.spans, ir, num),
            })
        elif b.type == "enriched":
            content.append({
                "type": "callout", "attrs": {"source_type": "enriched"},
                "content": [_paragraph(b.spans, ir, num)],
            })
        elif b.type == "list":
            content.append({
                "type": "orderedList" if b.ordered else "bulletList",
                "content": [
                    {"type": "listItem", "content": [_paragraph(item, ir, num)]}
                    for item in b.items
                ],
            })
    content.extend(_references_nodes(ir, num))
    return {"type": "doc", "content": content}


# ── IR → Markdown (round-trips with parse.py) ────────────────────────────────

def _spans_to_md(spans: list[Span]) -> str:
    out = ""
    for sp in spans:
        out += sp.text
        for cid in sp.cites:  # ORIGINAL labels, so a re-parse re-lifts them
            out += f" [{cid}]"
    return out.strip()


def ir_to_markdown(ir: WikiArticleIR) -> str:
    lines: list[str] = []
    for b in ir.blocks:
        if b.type in ("lead", "paragraph"):
            lines.append(_spans_to_md(b.spans))
        elif b.type == "heading":
            lines.append(("#" * (b.level or 2)) + " " + _spans_to_md(b.spans))
        elif b.type == "enriched":
            lines.append("> " + _spans_to_md(b.spans))
        elif b.type == "list":
            for idx, item in enumerate(b.items, 1):
                prefix = f"{idx}. " if b.ordered else "- "
                lines.append(prefix + _spans_to_md(item))
        lines.append("")  # blank separator
    return "\n".join(lines).strip() + "\n"


# ── IR → plaintext (search / embedding) ──────────────────────────────────────

def ir_to_plaintext(ir: WikiArticleIR) -> str:
    parts: list[str] = []
    for b in ir.blocks:
        for sp in b.all_spans():
            if sp.text:
                parts.append(sp.text)
    return "\n".join(parts).strip()
