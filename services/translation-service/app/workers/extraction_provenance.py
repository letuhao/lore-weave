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
    abridged   — the quote is an ELLIPSIS-JOINED citation whose every fragment occurs,
                 in order, in the text. Grounded, but no single span equals it, so it
                 carries NO offset (BOOK_TO_GAME/13 §5.1).
    partial    — a contiguous run covering >= NEAR_MATCH_RATIO of the quote occurs, but
                 the whole quote does not. Grounded in part; NO offset (the located run
                 is a SUBSET of the quote, and persisting its span would claim a
                 citation the quote does not support).
    ambiguous  — the quote occurs multiple times → flagged, no blind pick (NULL offset)
    unmatched  — the quote was not found → likely hallucination (kept, NULL offset)

`abridged` and `partial` were added after measuring this validator against a real
corpus (BOOK_TO_GAME/13): it reported 44.6% `unmatched` on 1,739 rows where only 2.4%
of quotes were fully absent from their chapter. 39% of the "failures" differed from
the source ONLY in punctuation or character width, and 19% were faithful quotations
the model had abridged with an ellipsis. An instrument whose noise floor is an order
of magnitude above the defect it measures cannot rank two pipelines, so the fold below
is a MEASUREMENT fix, not a leniency: the fully-absent quotes must stay `unmatched`,
and `test_extraction_provenance.py` asserts exactly that.

Design reference: extraction-pipeline-architecture rev 2 §8.5 (provenance trust),
detailed-design §4 INV-7.
"""
from __future__ import annotations

import re
import unicodedata
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
# The Go side (glossary-service `evidenceProvenanceFields`) gates on this exact set;
# a status it does not know degrades to 'unverified', which would silently erase the
# distinction this taxonomy exists to draw. Both sides move together — the parity is
# asserted by `test_extraction_provenance.py::test_taxonomy_matches_glossary_enum_gate`.
PROV_EXACT = "exact"
PROV_RESOLVED = "resolved"
PROV_ABRIDGED = "abridged"
PROV_PARTIAL = "partial"
PROV_AMBIGUOUS = "ambiguous"
PROV_UNMATCHED = "unmatched"

#: Statuses that carry a single verified span, and therefore an offset.
PROV_WITH_OFFSET = frozenset({PROV_EXACT, PROV_RESOLVED})
#: Statuses that record grounding without a locatable span (offsets stay NULL).
PROV_GROUNDED_NO_OFFSET = frozenset({PROV_ABRIDGED, PROV_PARTIAL})
PROV_ALL = frozenset({PROV_EXACT, PROV_RESOLVED, PROV_ABRIDGED, PROV_PARTIAL,
                      PROV_AMBIGUOUS, PROV_UNMATCHED})

#: A contiguous run must cover this share of the normalised quote to earn `partial`.
#: Chosen from the measured distribution in BOOK_TO_GAME/13 §5.1, where the fully-absent
#: quotes average 9.2 characters and share no long run with their chapter. Raising it
#: toward 1.0 collapses `partial` into `unmatched`; lowering it toward 0 is the vacuity
#: failure — every quote near-matches something in 5,000 characters of prose.
NEAR_MATCH_RATIO = 0.7
#: …and the run must be at least this long in absolute terms, so a short quote cannot
#: clear the ratio on a handful of common characters (a 4-char quote at 70% is 3 chars,
#: and any 3 Chinese characters occur somewhere).
NEAR_MATCH_MIN_CHARS = 8

#: Ellipsis forms a model uses to abridge a quotation.
_ELLIPSIS_RE = re.compile(r"\.{2,}|…+|…")
#: A fragment shorter than this is not evidence that the abridgement is faithful —
#: it is a connective, and requiring it to match would be noise in both directions.
_MIN_FRAGMENT_CHARS = 4


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


#: Dash-like and separator characters that Unicode classifies as SYMBOLS rather than
#: punctuation, so `category().startswith("P")` misses them. `──` (BOX DRAWINGS LIGHT
#: HORIZONTAL, category So) is the CJK typographic dash used throughout this corpus, and
#: a model rendering it as `——` (EM DASH, category Pd) was the single most common way a
#: faithful quote failed to match.
_EXTRA_DROP = frozenset("─━│┃‧・|")


def _fold(text: str) -> tuple[str, list[int]]:
    """Drop presentation and keep content, preserving a map back to real offsets.

    Returns ``(folded, idx_map)`` where ``idx_map[i]`` is the index in the ORIGINAL
    ``text`` of the character that produced folded char ``i``. Characters are only
    DROPPED or replaced 1:1 — never expanded — because an expansion would break that
    map and the whole point of this function is that a match can be mapped back to a
    verifiable source span.

    Dropped: all whitespace, every Unicode punctuation category, and the dash-like
    symbols above. Width/compatibility variants are folded via per-character NFKC,
    which is applied ONLY when it yields exactly one character.
    """
    out: list[str] = []
    idx_map: list[int] = []
    for i, ch in enumerate(text):
        if ch.isspace() or ch in _EXTRA_DROP or unicodedata.category(ch).startswith("P"):
            continue
        folded = unicodedata.normalize("NFKC", ch)
        out.append(folded if len(folded) == 1 else ch)
        idx_map.append(i)
    return "".join(out), idx_map


def _locate_folded(
    folded_quote: str, folded_text: str, idx_map: list[int], blocks: list[_Block]
) -> EvidenceProvenance | None:
    """Find ``folded_quote`` in ``folded_text`` and map the hit back to real offsets."""
    first = folded_text.find(folded_quote)
    if first == -1:
        return None
    if folded_text.find(folded_quote, first + 1) != -1:
        return EvidenceProvenance(PROV_AMBIGUOUS)
    raw_start = idx_map[first]
    raw_end = idx_map[first + len(folded_quote) - 1] + 1
    return EvidenceProvenance(
        PROV_RESOLVED, raw_start, raw_end, _block_for_offset(blocks, raw_start)
    )


def _has_near_match(folded_quote: str, folded_text: str) -> bool:
    """Does a contiguous run covering >= NEAR_MATCH_RATIO of the quote occur verbatim?

    Slides a window of exactly the threshold length rather than searching for the
    longest common substring: the question is a yes/no about a threshold, and the
    window form is O(len(quote)) substring searches instead of O(len(quote)^2).
    """
    need = max(NEAR_MATCH_MIN_CHARS, int(NEAR_MATCH_RATIO * len(folded_quote)))
    if need > len(folded_quote):
        return False
    return any(folded_quote[i:i + need] in folded_text
               for i in range(len(folded_quote) - need + 1))


def validate_evidence(
    quote: str,
    chapter_text: str,
    blocks: list[_Block],
    *,
    model_hint: int | None = None,
    block_hint: int | None = None,
    folded_chapter: tuple[str, list[int]] | None = None,
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
      3b. FOLDED search — whitespace, punctuation and width differences removed from
         both sides, the match mapped back to a real span. A quote that differs from the
         source only in how it renders a dash or whether it kept a trailing full stop is
         a faithful citation, and calling it a hallucination made this validator unable
         to measure hallucination (module docstring).
      4. ELLIPSIS-abridged citation — every fragment of an `A...B` quote occurs, in
         order, in the text → ``abridged``, no offset (no single span equals the quote).
      5. NEAR match — a contiguous run covering >= NEAR_MATCH_RATIO of the quote occurs
         → ``partial``, no offset (the run is a subset of what the quote claims).
      6. Otherwise ``unmatched`` — keep the evidence, fabricate no offset.

    Steps 3b-5 only ever move a quote OUT of ``unmatched``; none of them can turn an
    absent quote into a located one, because every one of them still requires its text
    to occur in the chapter. That is what keeps the tolerance from becoming vacuous.
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

    # 3b) Folded search — punctuation/width/whitespace differences removed from both
    #     sides. Still an occurrence test against the real text, so a quote that is not
    #     in the chapter cannot pass it.
    #     `folded_chapter` is precomputed once per chapter by `stamp_entity_provenance`
    #     — same pattern as `blocks`. Folding is O(len(chapter)), and computing it per
    #     ENTITY would redo it ~40 times per chapter in a pipeline whose cost is the
    #     thing under study.
    folded_text, fold_map = folded_chapter if folded_chapter is not None else _fold(chapter_text)
    folded_quote, _ = _fold(quote)
    if folded_quote and folded_text:
        hit = _locate_folded(folded_quote, folded_text, fold_map, blocks)
        if hit is not None:
            return hit

    # 4) Ellipsis-abridged citation: `A...B` where A and B both occur, in order. The
    #    model shortened a long quotation rather than inventing one, so it is grounded —
    #    but no contiguous span equals it, so it carries no offset.
    if _ELLIPSIS_RE.search(quote):
        frags = [f for f in (_fold(p)[0] for p in _ELLIPSIS_RE.split(quote))
                 if len(f) >= _MIN_FRAGMENT_CHARS]
        if frags:
            cursor = 0
            for frag in frags:
                found = folded_text.find(frag, cursor)
                if found == -1:
                    break
                cursor = found + len(frag)
            else:
                return EvidenceProvenance(PROV_ABRIDGED)

    # 5) Near match — most of the quote occurs contiguously, the rest does not.
    if folded_quote and _has_near_match(folded_quote, folded_text):
        return EvidenceProvenance(PROV_PARTIAL)

    # 6) Not found anywhere → unmatched (never fabricate an offset).
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
    folded_chapter = _fold(chapter_text)
    for ent in entities:
        # Strip any ⟦B#⟧ block marker the model may have copied into the quote, then pass its
        # optional block citation (D-PROV-MODEL-OFFSET-HINT) — validated, never trusted.
        quote = strip_block_markers(ent.get("evidence", "") or "")
        block_hint = _coerce_block(ent.get("evidence_block"))
        prov = validate_evidence(quote, chapter_text, blocks, block_hint=block_hint,
                                 folded_chapter=folded_chapter)
        ent["evidence_provenance_status"] = prov.provenance_status
        if prov.char_start is not None:
            ent["evidence_char_start"] = prov.char_start
        if prov.char_end is not None:
            ent["evidence_char_end"] = prov.char_end
        if prov.block_or_line is not None:
            ent["evidence_block_or_line"] = prov.block_or_line
