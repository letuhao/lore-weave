"""Wiki LLM-generation module (knowledge-service).

M0 = the render-agnostic Wiki Article IR + the constrained-Markdown parser + the
IR→{TipTap, Markdown, plaintext} mappers. This package surface stays PURE (no I/O)
so the IR can be imported without the service's DB/HTTP deps.

M2 added `context.py` (per-entity grounding gather) — it touches clients/db, so it
is imported DIRECTLY (`from app.wiki.context import gather_entity_context`), NOT
re-exported here, to keep this surface dependency-light. Later milestones (M3-M6)
add the LLM call, verify/cite, and the glossary writeback the same way.
"""

from app.wiki.ir import Block, Source, Span, WikiArticleIR
from app.wiki.mappers import ir_to_markdown, ir_to_plaintext, ir_to_tiptap
from app.wiki.parse import has_grounded_content, parse_article, parse_blocks

__all__ = [
    "WikiArticleIR",
    "Block",
    "Span",
    "Source",
    "parse_article",
    "parse_blocks",
    "has_grounded_content",
    "ir_to_tiptap",
    "ir_to_markdown",
    "ir_to_plaintext",
]
