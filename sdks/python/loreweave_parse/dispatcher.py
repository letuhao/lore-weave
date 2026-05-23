"""2-branch format dispatcher — spec D3.

Routes html -> html_walker.parse_html; plain -> plaintext_parser.parse_plain.
"""

from __future__ import annotations

from loreweave_parse._types import (
    ParseOptions,
    SourceFormat,
    StructuralTree,
)
from loreweave_parse.html_walker import parse_html
from loreweave_parse.plaintext_parser import parse_plain


def parse(
    source_format: SourceFormat,
    content: str,
    *,
    language: str | None = None,
    filename: str | None = None,
    options: ParseOptions | None = None,
) -> StructuralTree:
    """Parse content into a StructuralTree.

    Raises ValueError on unknown source_format (caller — typically the HTTP
    router — should translate to 400).
    """
    if source_format == "html":
        return parse_html(content, options=options, filename=filename)
    if source_format == "plain":
        return parse_plain(content, language=language, filename=filename)
    raise ValueError(f"unknown source_format: {source_format!r}")


__all__ = ["parse"]
