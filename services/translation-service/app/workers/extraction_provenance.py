"""Extraction evidence provenance — validate model evidence quotes against the
REAL chapter text (INV-7 / threat T1: model-supplied offsets are HINTS, never
trusted).

The extraction prompt asks the model for a short EXACT QUOTE per entity (the
``evidence`` field). To make that quote a *verifiable citation* we must know where
in the source it occurs — but the model is untrusted DATA (INV-6), so any offset
or block index it volunteers is a hint that gets validated against the text before
it is believed, and is otherwise discovered by authoritative search. We NEVER
persist an offset we could not verify, and we NEVER fabricate one for a quote we
cannot find (that would manufacture a confidently-wrong citation — the exact T1
failure mode).

The worker is the only component that holds the prepared chapter text, so the
validation lives here; glossary-service receives the *validated* offsets + a trust
status and persists them defensively (clamp + enum-gate). The trust taxonomy
mirrors ``evidences.provenance_status`` (glossary migration 0033):

    exact      — a model-supplied offset was verified to point at the quote
    resolved   — the quote occurs exactly once in the text → offset found by search
    ambiguous  — the quote occurs multiple times → flagged, no blind pick (NULL offset)
    unmatched  — the quote was not found → likely hallucination (kept, NULL offset)

Design reference: extraction-pipeline-architecture rev 2 §8.5 (provenance trust),
detailed-design §4 INV-7.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# The block sentinel the prompt prefixes onto each numbered paragraph (⟦B3⟧). Stripped
# from a model's evidence quote before validation so a model that accidentally copies the
# marker into the quote still matches the clean source text (graceful degradation).
_BLOCK_MARKER_RE = re.compile(r"⟦B\d+⟧\s*")


def strip_block_markers(s: str) -> str:
    return _BLOCK_MARKER_RE.sub("", s)


def _coerce_block(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None

# provenance_status taxonomy — keep in sync with glossary evidences.provenance_status.
PROV_EXACT = "exact"
PROV_RESOLVED = "resolved"
PROV_AMBIGUOUS = "ambiguous"
PROV_UNMATCHED = "unmatched"


@dataclass
class EvidenceProvenance:
    """The validated location of an evidence quote in the chapter text.

    ``char_start``/``char_end``/``block_or_line`` are populated ONLY for
    ``exact``/``resolved`` (a single, verified location); ``ambiguous``/
    ``unmatched`` carry the status but no offset (None) — never a blind pick.
    """

    provenance_status: str
    char_start: int | None = None
    char_end: int | None = None
    block_or_line: int | None = None


@dataclass
class _Block:
    index: int
    start: int  # inclusive char offset into the chapter text
    end: int    # exclusive char offset (the newline / end-of-text)


def build_block_offset_map(chapter_text: str) -> list[_Block]:
    """Split the chapter text into blocks (newline-delimited paragraphs/lines),
    each carrying its ``[start, end)`` char range in the ORIGINAL text.

    Blank segments are skipped (they are not citable blocks) but their characters
    still advance the offset, so every block's range indexes the chapter text
    verbatim — a returned block index therefore maps back to exact source
    coordinates. Computed once per chapter (the text is identical for every entity).
    """
    blocks: list[_Block] = []
    n = len(chapter_text)
    idx = 0
    start = 0
    pos = 0
    while pos <= n:
        if pos == n or chapter_text[pos] == "\n":
            if chapter_text[start:pos].strip():
                blocks.append(_Block(index=idx, start=start, end=pos))
                idx += 1
            start = pos + 1
        pos += 1
    return blocks


def _block_for_offset(blocks: list[_Block], off: int) -> int | None:
    for b in blocks:
        if b.start <= off < b.end:
            return b.index
    return None


def _normalize_ws(text: str) -> tuple[str, list[int]]:
    """Collapse each run of whitespace to a single space.

    Returns ``(normalized, idx_map)`` where ``idx_map[i]`` is the index in the
    ORIGINAL ``text`` of the first character that produced normalized char ``i`` —
    so an offset found in the normalized view maps back to a real source offset.
    """
    out: list[str] = []
    idx_map: list[int] = []
    prev_ws = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if prev_ws:
                continue
            out.append(" ")
            idx_map.append(i)
            prev_ws = True
        else:
            out.append(ch)
            idx_map.append(i)
            prev_ws = False
    return "".join(out), idx_map


def validate_evidence(
    quote: str,
    chapter_text: str,
    blocks: list[_Block],
    *,
    model_hint: int | None = None,
    block_hint: int | None = None,
) -> EvidenceProvenance:
    """Locate ``quote`` in ``chapter_text`` and return its validated provenance.

    Order of trust (INV-7 — validate, never trust a raw number):
      0. If the model CITED a block (``block_hint``), verify the quote occurs uniquely
         WITHIN that block's real text. Only a verified citation is ``exact``; a wrong
         citation is discarded (falls through to search). (D-PROV-MODEL-OFFSET-HINT.)
      1. If the model volunteered a char offset hint, VERIFY the text at that offset
         equals the quote (after clamping to ``[0, len]``). Only then ``exact``.
      2. Authoritative raw substring search — a single occurrence is ``resolved``;
         multiple occurrences are ``ambiguous`` (flag, no blind pick).
      3. Whitespace-normalized search (prose may differ only in whitespace), mapping
         the match back to real source offsets — single match ``resolved``.
      4. Otherwise ``unmatched`` — keep the evidence, fabricate no offset.
    """
    if not quote or not chapter_text:
        return EvidenceProvenance(PROV_UNMATCHED)

    n = len(chapter_text)

    # 0) Model-supplied BLOCK citation — verified against that block's real text. A unique
    #    occurrence in the cited block confirms the model's citation → 'exact'. This both
    #    disambiguates an otherwise-ambiguous quote and upgrades a confirmed cite. A wrong
    #    cite (quote not uniquely there) is distrusted → fall through to authoritative search.
    if block_hint is not None and 0 <= block_hint < len(blocks):
        blk = blocks[block_hint]
        seg = chapter_text[blk.start:blk.end]
        pos = seg.find(quote)
        if pos != -1 and seg.find(quote, pos + 1) == -1:
            start = blk.start + pos
            return EvidenceProvenance(PROV_EXACT, start, start + len(quote), block_hint)

    # 1) Model-supplied hint — a HINT only, verified against the real text.
    if model_hint is not None:
        try:
            h = int(model_hint)
        except (TypeError, ValueError):
            h = None
        if h is not None:
            h = max(0, min(h, n))  # clamp to [0, len] (INV-7: no OOB slice)
            if chapter_text[h:h + len(quote)] == quote:
                return EvidenceProvenance(
                    PROV_EXACT, h, h + len(quote), _block_for_offset(blocks, h)
                )
            # hint did not verify → distrust it and fall through to search

    # 2) Authoritative raw substring search.
    first = chapter_text.find(quote)
    if first != -1:
        if chapter_text.find(quote, first + 1) == -1:
            return EvidenceProvenance(
                PROV_RESOLVED, first, first + len(quote), _block_for_offset(blocks, first)
            )
        return EvidenceProvenance(PROV_AMBIGUOUS)  # multi-match → flag, don't pick

    # 3) Whitespace-normalized fallback (offsets mapped back to the real text).
    norm_quote, _ = _normalize_ws(quote)
    norm_quote = norm_quote.strip()
    if norm_quote:
        norm_text, idx_map = _normalize_ws(chapter_text)
        nfirst = norm_text.find(norm_quote)
        if nfirst != -1:
            if norm_text.find(norm_quote, nfirst + 1) == -1:
                raw_start = idx_map[nfirst]
                raw_end = idx_map[nfirst + len(norm_quote) - 1] + 1
                return EvidenceProvenance(
                    PROV_RESOLVED, raw_start, raw_end, _block_for_offset(blocks, raw_start)
                )
            return EvidenceProvenance(PROV_AMBIGUOUS)

    # 4) Not found anywhere → unmatched (never fabricate an offset).
    return EvidenceProvenance(PROV_UNMATCHED)


def stamp_entity_provenance(entities: list[dict], chapter_text: str) -> None:
    """Validate each entity's ``evidence`` quote against ``chapter_text`` and stamp
    the validated provenance fields the glossary writeback consumes (in place).

    Adds ``evidence_provenance_status`` always; ``evidence_char_start``/
    ``evidence_char_end``/``evidence_block_or_line`` only when a single verified
    location exists. Entities without an ``evidence`` quote are marked ``unmatched``
    (no quote to ground). The block map is built once for the whole chapter.
    """
    blocks = build_block_offset_map(chapter_text)
    for ent in entities:
        # Strip any ⟦B#⟧ block marker the model may have copied into the quote, then pass its
        # optional block citation (D-PROV-MODEL-OFFSET-HINT) — validated, never trusted.
        quote = strip_block_markers(ent.get("evidence", "") or "")
        block_hint = _coerce_block(ent.get("evidence_block"))
        prov = validate_evidence(quote, chapter_text, blocks, block_hint=block_hint)
        ent["evidence_provenance_status"] = prov.provenance_status
        if prov.char_start is not None:
            ent["evidence_char_start"] = prov.char_start
        if prov.char_end is not None:
            ent["evidence_char_end"] = prov.char_end
        if prov.block_or_line is not None:
            ent["evidence_block_or_line"] = prov.block_or_line
