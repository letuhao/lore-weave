"""Constrained-Markdown → :class:`WikiArticleIR` parser (M0 / Phase-1 §C2).

The LLM is instructed to emit a SMALL, fixed Markdown subset, so this is a dependency-
free, deterministic, line-oriented parser (no CommonMark lib — we fully control the input
shape, and a hand parser has no surprise edge cases + no new runtime dep):

  ``## Heading`` / ``### Heading``   → heading block (level clamped to 2/3)
  blank-line-separated text          → paragraph (the FIRST one, before any heading → ``lead``)
  ``- `` / ``* `` / ``1. `` lines    → list block (ordered iff numbered)
  ``> `` lines                       → ``enriched`` block (H0 quarantine, ``source_type='enriched'``)
  inline ``[P1]``/``[G2]``/``[K1]``  → lifted into ``Span.cites``

**Cite labels are OURS** (we assign them in ``sources`` and hand them to the LLM), so a
bracket token NOT in ``sources`` is a hallucinated reference: it is DROPPED (never trusted)
and, if it left a non-trivial span with zero resolved cites, that span is flagged
``grounded=False`` for the rule-gate (M3). The parser is TOTAL — it never raises on the
constrained subset; "retry on malformed" is an M3-level re-prompt concern, surfaced here
via :func:`has_grounded_content`.
"""

from __future__ import annotations

import re

from app.wiki.ir import Block, Source, Span, WikiArticleIR

#: a cite token, e.g. ``[P1]`` / ``[G12]`` / ``[K3]``.
_CITE_RE = re.compile(r"\[([A-Za-z]+\d+)\]")
#: split text keeping the cite tokens as delimiters.
_CITE_SPLIT_RE = re.compile(r"(\[[A-Za-z]+\d+\])")
#: a list-item line (bullet or ordered).
_LIST_RE = re.compile(r"^(?:[-*]|\d+\.)\s+(.*)$")
_ORDERED_RE = re.compile(r"^\d+\.\s+")
#: emphasis markers we flatten to plain text (rich inline = follow-up if ever needed).
_EMPHASIS_RE = re.compile(r"(\*\*|__|\*|_)")
#: "content" chars = anything that is not whitespace or common CJK/Latin punctuation.
_PUNCT = " \t\r\n.,;:!?。，、；：！？“”‘’（）()[]{}-—…·「」《》〈〉·"
_CONTENT_RE = re.compile(r"[^" + re.escape(_PUNCT) + r"]")

#: a span shorter than this many CONTENT chars never needs a cite (punctuation, connectors).
_NONTRIVIAL_MIN = 6


def _is_nontrivial(text: str) -> bool:
    """Coarse "is this a claim worth a cite?" heuristic (LOW-4): >= _NONTRIVIAL_MIN
    content chars. Punctuation/connectors stay grounded; a very short uncited claim can
    slip the flag — the M3 rule-gate (CanonVerifier) is the real backstop, so this is
    only a coarse pre-signal, intentionally permissive on short text."""
    return len(_CONTENT_RE.findall(text)) >= _NONTRIVIAL_MIN


def _clean(text: str) -> str:
    return _EMPHASIS_RE.sub("", text).strip()


def _is_block_start(stripped: str) -> bool:
    """A line that begins a new block (stops a paragraph run without a blank line)."""
    return (
        stripped.startswith("#")
        or stripped.startswith(">")
        or bool(_LIST_RE.match(stripped))
    )


def _parse_inline(text: str, valid_ids: set[str], source_type: str | None = None) -> list[Span]:
    """Split inline text into spans, lifting ``[Pn]`` tokens into ``Span.cites``.

    A run of text plus the cite(s) that immediately follow it form one span; new text
    after a cite flushes the previous span. Unknown labels are dropped; a non-trivial
    span left with zero resolved cites is flagged ``grounded=False``.
    """
    spans: list[Span] = []
    buf = ""
    cites: list[str] = []

    def flush() -> None:
        nonlocal buf, cites
        cleaned = _clean(buf)
        if cleaned or cites:
            grounded = True
            if not cites and _is_nontrivial(cleaned):
                grounded = False
            spans.append(
                Span(text=cleaned, cites=list(cites), source_type=source_type, grounded=grounded)
            )
        buf, cites = "", []

    for part in _CITE_SPLIT_RE.split(text):
        m = re.fullmatch(_CITE_RE, part)
        if m:
            label = m.group(1)
            # Known label → lift to a cite (the token text is consumed, not rendered).
            # Unknown label → DROPPED ON PURPOSE (LOW-3): the LLM is told to cite ONLY
            # with our P/G/K labels, so an unknown cite-shaped token is a hallucinated
            # reference — we remove the dangling marker rather than render a fake [n].
            # (A genuine non-cite "[Xn]" in prose — which the LLM is instructed not to
            # emit — would also lose that one bracket; an accepted, very-rare trade.)
            if label in valid_ids:
                cites.append(label)
            continue
        # plain text: if cites are already pending, the buf+cites span closes first.
        if cites:
            flush()
        buf += part
    flush()
    return spans


def parse_blocks(markdown: str, sources: list[Source]) -> list[Block]:
    """Parse the constrained Markdown body into ordered IR blocks + compute each block's
    ``source_chapter_max`` (spoiler horizon) from its cited passages."""
    valid_ids = {s.cite_id for s in sources}
    src_by_id = {s.cite_id: s for s in sources}
    lines = markdown.split("\n")
    blocks: list[Block] = []
    seen_heading = False
    i = 0
    n = len(lines)

    while i < n:
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue

        if stripped.startswith("#"):
            hashes = len(stripped) - len(stripped.lstrip("#"))
            level = min(max(hashes, 2), 3)
            spans = _parse_inline(stripped[hashes:].strip(), valid_ids)
            blocks.append(Block(type="heading", level=level, spans=spans))
            seen_heading = True
            i += 1

        elif stripped.startswith(">"):
            quote: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            spans = _parse_inline(" ".join(quote), valid_ids, source_type="enriched")
            blocks.append(Block(type="enriched", spans=spans))

        elif _LIST_RE.match(stripped):
            ordered = bool(_ORDERED_RE.match(stripped))
            items: list[list[Span]] = []
            while i < n:
                m = _LIST_RE.match(lines[i].strip())
                if not m:
                    break
                items.append(_parse_inline(m.group(1), valid_ids))
                i += 1
            blocks.append(Block(type="list", ordered=ordered, items=items))

        else:
            para: list[str] = []
            while i < n and lines[i].strip() and not _is_block_start(lines[i].strip()):
                para.append(lines[i].strip())
                i += 1
            btype = "lead" if (not seen_heading and not blocks) else "paragraph"
            spans = _parse_inline(" ".join(para), valid_ids)
            blocks.append(Block(type=btype, spans=spans))

    for b in blocks:
        chapters = [
            src.chapter_sort_order
            for s in b.all_spans()
            for cid in s.cites
            if (src := src_by_id.get(cid)) and src.chapter_sort_order is not None
        ]
        b.source_chapter_max = max(chapters) if chapters else None

    return blocks


def parse_article(
    markdown: str,
    *,
    entity_id: str,
    display_name: str,
    kind: str = "",
    language: str = "auto",
    sources: list[Source],
) -> WikiArticleIR:
    """Parse an LLM Markdown article into a :class:`WikiArticleIR` (the M0 entry point)."""
    return WikiArticleIR(
        entity_id=entity_id,
        display_name=display_name,
        kind=kind,
        language=language,
        blocks=parse_blocks(markdown, sources),
        sources=sources,
    )


def has_grounded_content(ir: WikiArticleIR) -> bool:
    """True iff the article has ≥1 grounded, cited span. M3 re-prompts / skips when
    False (the zero-grounded → no-hollow-stub rule)."""
    return ir.grounded_claim_count > 0
