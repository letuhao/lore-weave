"""Wiki LLM-generation module (knowledge-service).

M0 = the render-agnostic Wiki Article IR + the constrained-Markdown parser + the
IR→{TipTap, Markdown, plaintext} mappers. Pure, no I/O. Downstream milestones (M2-M6)
add context-gathering, the LLM call, verify/cite, and the glossary writeback.
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
