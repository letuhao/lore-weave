"""HTML-to-plaintext conversion locked at spec D4 (H2 fix).

This is the ONE HTML-to-text path in P1. Any change here perturbs
scene.leaf_text bytes — and the regression-pinned round-trip test in
tests/test_loreweave_parse_roundtrip.py will catch it. That is the
intent: a canary against silent drift.

Algorithm:
  1. BeautifulSoup(html, "html.parser") — M4 fix, lenient stdlib parser.
  2. Drop <script> / <style> entirely.
  3. Replace <br/> with literal newline so intra-paragraph breaks survive.
  4. Walk the soup at BLOCK-level granularity:
       - block-level tag (p, div, h1-h6, li, blockquote, pre, section,
         article, header, footer, nav, ul, ol, table, tr, td, th):
         -> emit `tag.get_text(separator="", strip=True)` as one paragraph
       - inline / text nodes outside any block tag at the top level:
         -> collect into a synthetic paragraph (rare in pandoc output)
  5. Join paragraphs with "\\n\\n".
  6. Collapse runs of blank lines (>1 consecutive) to exactly one.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString, Tag

_WS_RUN = re.compile(r"\n[ \t]*(?:\n[ \t]*)+")

_BLOCK_TAGS: set[str] = {
    "p",
    "div",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "blockquote",
    "pre",
    "section",
    "article",
    "header",
    "footer",
    "nav",
    "ul",
    "ol",
    "table",
    "tr",
    "td",
    "th",
    "figure",
    "figcaption",
    "details",
    "summary",
    "address",
    "hr",
}


def _direct_text(tag: Tag) -> str:
    """Concatenate direct NavigableString children of `tag`, ignoring text
    inside nested tags. Whitespace stripped + single-spaced.

    Used by _collect_paragraphs (M1 fix from /review-impl round 2) to
    recover the outer-text of a block that contains other blocks — e.g.
    <li>outer<ul><li>inner</li></ul></li> would otherwise lose "outer".
    """
    parts: list[str] = []
    for child in tag.children:
        if isinstance(child, NavigableString):
            s = str(child).strip()
            if s:
                parts.append(s)
    return " ".join(parts)


def _collect_paragraphs(root: Tag) -> list[str]:
    """Walk the root's descendants; emit one paragraph per innermost block.

    M1 fix: also emit the DIRECT TEXT of skipped (non-innermost) blocks, so
    loose text in a container or text-before-nested-list survives. Without
    this, `<div>loose<p>para</p></div>` would drop "loose"; nested lists
    would drop the outer-item text.
    """
    paragraphs: list[str] = []
    for descendant in root.descendants:
        if isinstance(descendant, Tag) and descendant.name in _BLOCK_TAGS:
            has_nested_block = any(
                isinstance(d, Tag) and d.name in _BLOCK_TAGS
                for d in descendant.descendants
            )
            if has_nested_block:
                # M1 fix — direct-text-only of this skipped block.
                direct = _direct_text(descendant)
                if direct:
                    paragraphs.append(direct)
                continue
            # Innermost block — full inline text.
            text = descendant.get_text(separator="", strip=False).strip()
            if text:
                paragraphs.append(text)
    if not paragraphs:
        text = root.get_text(separator="", strip=False).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def html_to_leaf_text(html: str) -> str:
    """Convert HTML to plain leaf text — see spec D4 'HTML→text algorithm'."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with(NavigableString("\n"))
    paragraphs = _collect_paragraphs(soup)
    joined = "\n\n".join(paragraphs)
    collapsed = _WS_RUN.sub("\n\n", joined)
    return collapsed.strip()


__all__ = ["html_to_leaf_text"]
