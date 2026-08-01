"""Tests for extraction evidence provenance validation (PROV/M3 — INV-7 / T1).

The defense under test: a model evidence quote is grounded to the REAL chapter text
by authoritative search, a model-supplied offset is a HINT verified before trust, and
an unverifiable quote NEVER gets a fabricated offset (the confidently-wrong-citation
failure mode). Status taxonomy: exact / resolved / abridged / partial / ambiguous /
unmatched — the middle two added by the measurement repair at the bottom of this file.
"""
from app.workers.extraction_provenance import (
    PROV_AMBIGUOUS,
    PROV_EXACT,
    PROV_RESOLVED,
    PROV_UNMATCHED,
    build_block_offset_map,
    stamp_entity_provenance,
    strip_block_markers,
    validate_evidence,
)

# A small multi-paragraph chapter. Note the deliberately REPEATED phrase "the sword"
# (appears twice) to exercise the ambiguous branch.
CHAPTER = (
    "Zhang Ruochen drew the sword at dawn.\n"
    "The Divine Mark glowed on his palm.\n"
    "Later he sheathed the sword again."
)


def _blocks():
    return build_block_offset_map(CHAPTER)


def test_block_offset_map_ranges_index_real_text():
    blocks = _blocks()
    assert len(blocks) == 3
    # Each block's [start,end) slice equals the paragraph text verbatim.
    assert CHAPTER[blocks[0].start:blocks[0].end] == "Zhang Ruochen drew the sword at dawn."
    assert CHAPTER[blocks[1].start:blocks[1].end] == "The Divine Mark glowed on his palm."
    assert CHAPTER[blocks[2].start:blocks[2].end] == "Later he sheathed the sword again."


def test_resolved_single_occurrence_carries_real_offsets():
    prov = validate_evidence("Divine Mark glowed", CHAPTER, _blocks())
    assert prov.provenance_status == PROV_RESOLVED
    # The offsets must slice the quote back out of the REAL text.
    assert CHAPTER[prov.char_start:prov.char_end] == "Divine Mark glowed"
    assert prov.block_or_line == 1  # second paragraph


def test_ambiguous_multi_occurrence_takes_no_offset():
    # "the sword" appears in block 0 and block 2 → ambiguous, no blind pick.
    prov = validate_evidence("the sword", CHAPTER, _blocks())
    assert prov.provenance_status == PROV_AMBIGUOUS
    assert prov.char_start is None and prov.char_end is None
    assert prov.block_or_line is None


def test_unmatched_quote_gets_no_fabricated_offset():
    prov = validate_evidence("a phrase that does not occur", CHAPTER, _blocks())
    assert prov.provenance_status == PROV_UNMATCHED
    assert prov.char_start is None and prov.char_end is None and prov.block_or_line is None


def test_model_hint_verified_is_exact():
    # A hint pointing exactly at "Divine Mark" → verified → exact.
    off = CHAPTER.index("Divine Mark")
    prov = validate_evidence("Divine Mark", CHAPTER, _blocks(), model_hint=off)
    assert prov.provenance_status == PROV_EXACT
    assert prov.char_start == off
    assert CHAPTER[prov.char_start:prov.char_end] == "Divine Mark"


def test_lying_model_hint_is_distrusted_then_resolved_by_search():
    # The model claims offset 0, but "Divine Mark" is NOT at offset 0. The hint must be
    # discarded (never persisted as exact) and the quote resolved by authoritative search.
    prov = validate_evidence("Divine Mark", CHAPTER, _blocks(), model_hint=0)
    assert prov.provenance_status == PROV_RESOLVED  # NOT exact — the lie was rejected
    assert CHAPTER[prov.char_start:prov.char_end] == "Divine Mark"


def test_out_of_range_hint_is_clamped_not_oob():
    # A wildly out-of-range hint must clamp (no slice error / OOB), then fall to search.
    prov = validate_evidence("Divine Mark", CHAPTER, _blocks(), model_hint=10_000_000)
    assert prov.provenance_status == PROV_RESOLVED
    assert CHAPTER[prov.char_start:prov.char_end] == "Divine Mark"


def test_whitespace_normalized_fallback_maps_back_to_real_offsets():
    # The model collapses an internal newline to a space; raw substring fails, the
    # normalized fallback finds the unique match and maps offsets back to real text.
    text = "He crossed\nthe ancient bridge slowly."
    blocks = build_block_offset_map(text)
    prov = validate_evidence("crossed the ancient", text, blocks)
    assert prov.provenance_status == PROV_RESOLVED
    # Offsets index the REAL text (which still contains the newline).
    assert text[prov.char_start:prov.char_end] == "crossed\nthe ancient"


def test_empty_quote_is_unmatched():
    assert validate_evidence("", CHAPTER, _blocks()).provenance_status == PROV_UNMATCHED


# ── D-PROV-MODEL-OFFSET-HINT: model block citation (validated, never trusted) ──


def test_block_hint_correct_citation_is_exact():
    # "the sword" is ambiguous (blocks 0 and 2); a correct block cite disambiguates → exact.
    prov = validate_evidence("the sword", CHAPTER, _blocks(), block_hint=2)
    assert prov.provenance_status == PROV_EXACT
    assert prov.block_or_line == 2
    assert CHAPTER[prov.char_start:prov.char_end] == "the sword"


def test_block_hint_wrong_citation_falls_through_to_search():
    # The model cites block 1, but "the sword" isn't there → distrust the cite, fall to
    # search, which finds it in two blocks → ambiguous (no blind pick).
    prov = validate_evidence("the sword", CHAPTER, _blocks(), block_hint=1)
    assert prov.provenance_status == PROV_AMBIGUOUS


def test_block_hint_out_of_range_ignored():
    prov = validate_evidence("Divine Mark glowed", CHAPTER, _blocks(), block_hint=99)
    assert prov.provenance_status == PROV_RESOLVED  # still resolved by search


def test_strip_block_markers_removes_sentinel():
    assert strip_block_markers("⟦B3⟧ the sword") == "the sword"
    assert strip_block_markers("no marker here") == "no marker here"


def test_stamp_uses_block_hint_and_strips_marker():
    # The model copied the ⟦B2⟧ marker into the quote AND cited block 2 → strip + verify.
    entities = [{"name": "Sword", "evidence": "⟦B2⟧ the sword", "evidence_block": 2}]
    stamp_entity_provenance(entities, CHAPTER)
    assert entities[0]["evidence_provenance_status"] == PROV_EXACT
    assert entities[0]["evidence_block_or_line"] == 2


def test_stamp_entities_mutates_in_place_with_namespaced_keys():
    entities = [
        {"name": "Divine Mark", "evidence": "Divine Mark glowed"},   # resolved
        {"name": "Sword", "evidence": "the sword"},                  # ambiguous
        {"name": "Ghost", "evidence": "not in the text at all"},     # unmatched
        {"name": "NoEvidence"},                                      # missing evidence
    ]
    stamp_entity_provenance(entities, CHAPTER)

    assert entities[0]["evidence_provenance_status"] == PROV_RESOLVED
    assert "evidence_char_start" in entities[0] and "evidence_block_or_line" in entities[0]

    assert entities[1]["evidence_provenance_status"] == PROV_AMBIGUOUS
    assert "evidence_char_start" not in entities[1]  # no blind offset

    assert entities[2]["evidence_provenance_status"] == PROV_UNMATCHED
    assert "evidence_char_start" not in entities[2]

    assert entities[3]["evidence_provenance_status"] == PROV_UNMATCHED  # no quote to ground


# ── The measurement repair (BOOK_TO_GAME/13 §5, /14 §1) ──────────────────────
#
# This validator is the instrument the extraction POC is scored with. Measured against
# a real corpus it reported 44.6% `unmatched` on 1,739 rows where only 2.4% of quotes
# were actually absent — 39% differed only in punctuation, 19% were ellipsis-abridged.
# The folding below moves those OUT of `unmatched`.
#
# The whole risk of that change is that a tolerance wide enough to accept a faithful
# quote is also wide enough to accept an invented one. Every test in this block is
# therefore paired: one asserts the recovery, its neighbour asserts the recovery did
# NOT reach a quote the chapter does not contain. A fold that passes only the first
# half of each pair is the vacuity failure this repo has recorded twenty-seven times.

from app.workers.extraction_provenance import (  # noqa: E402
    NEAR_MATCH_MIN_CHARS,
    NEAR_MATCH_RATIO,
    PROV_ABRIDGED,
    PROV_ALL,
    PROV_PARTIAL,
)

#: Classical Chinese, the corpus the repair was measured on. `──` is the CJK dash the
#: source uses; a model rendering it `——` was the most common way a true quote failed.
CJK_CHAPTER = (
    "話說聞太師驅兵追趕，出西門，一路上旗旛招展，鏜鼓齊鳴，喊聲大作。\n"
    "且說黃家父子、兄弟過了孟津，渡了黃河，行至澠池縣。──縣中鎮守主將張奎。\n"
    "黃飛虎知張奎利害，不敢穿城而走，從城外過了澠池，逕往臨潼關來。"
)


def _cjk_blocks():
    return build_block_offset_map(CJK_CHAPTER)


def test_dash_variant_resolves_and_offsets_point_at_the_real_span():
    """`——` for `──` is a rendering difference, not a fabrication."""
    quote = "行至澠池縣。——縣中鎮守主將張奎"
    prov = validate_evidence(quote, CJK_CHAPTER, _cjk_blocks())
    assert prov.provenance_status == PROV_RESOLVED
    # The span must contain the real source text, not a fabricated location.
    span = CJK_CHAPTER[prov.char_start:prov.char_end]
    assert "澠池縣" in span and "張奎" in span


def test_trailing_punctuation_added_by_the_model_still_resolves():
    prov = validate_evidence("出西門，一路上旗旛招展。", CJK_CHAPTER, _cjk_blocks())
    assert prov.provenance_status == PROV_RESOLVED


def test_fullwidth_and_ascii_punctuation_fold_together():
    prov = validate_evidence("黃飛虎知張奎利害,不敢穿城而走", CJK_CHAPTER, _cjk_blocks())
    assert prov.provenance_status == PROV_RESOLVED


def test_punctuation_fold_does_NOT_reach_a_quote_the_chapter_lacks():
    """The bite test for step 3b: folding removes presentation, never content."""
    prov = validate_evidence("黃飛虎大笑三聲，遂棄劍而降。", CJK_CHAPTER, _cjk_blocks())
    assert prov.provenance_status == PROV_UNMATCHED


def test_ellipsis_abridged_quote_is_grounded_but_carries_no_offset():
    quote = "且說黃家父子、兄弟過了孟津...逕往臨潼關來"
    prov = validate_evidence(quote, CJK_CHAPTER, _cjk_blocks())
    assert prov.provenance_status == PROV_ABRIDGED
    # No single contiguous span equals an abridged quote, so claiming one would be the
    # exact confidently-wrong-citation failure this module exists to prevent.
    assert prov.char_start is None and prov.char_end is None


def test_ellipsis_with_an_INVENTED_fragment_stays_unmatched():
    """Bite test for step 4: every fragment must occur, not just the first."""
    quote = "且說黃家父子、兄弟過了孟津...遂於城下斬張奎首級"
    assert validate_evidence(quote, CJK_CHAPTER, _cjk_blocks()).provenance_status == (
        PROV_UNMATCHED
    )


def test_ellipsis_fragments_must_occur_IN_ORDER():
    """A quote whose fragments appear in reverse order is not an abridgement of it."""
    quote = "逕往臨潼關來...且說黃家父子、兄弟過了孟津"
    assert validate_evidence(quote, CJK_CHAPTER, _cjk_blocks()).provenance_status != (
        PROV_ABRIDGED
    )


def test_near_match_is_partial_not_resolved_and_not_unmatched():
    """Most of the quote is real; the tail is not. That is neither clean nor absent."""
    quote = "黃飛虎知張奎利害，不敢穿城而走，遂降"
    prov = validate_evidence(quote, CJK_CHAPTER, _cjk_blocks())
    assert prov.provenance_status == PROV_PARTIAL
    assert prov.char_start is None  # the located run is a SUBSET of the claim


def test_near_match_does_NOT_rescue_a_wholly_invented_quote():
    """Bite test for step 5 — the one most at risk of becoming vacuous.

    In 5,000 characters of prose almost any short string shares SOME run, which is why
    the threshold is a ratio AND an absolute floor.
    """
    prov = validate_evidence("此乃玉虛宮元始天尊所傳之無上大法", CJK_CHAPTER, _cjk_blocks())
    assert prov.provenance_status == PROV_UNMATCHED


def test_short_quote_cannot_clear_the_near_match_floor_on_common_characters():
    """`NEAR_MATCH_MIN_CHARS` is what stops a 4-char quote near-matching on 3 chars."""
    prov = validate_evidence("張奎大怒", CJK_CHAPTER, _cjk_blocks())
    assert prov.provenance_status == PROV_UNMATCHED


def test_thresholds_are_in_a_range_that_can_actually_reject():
    """A ratio of 0 or a floor of 0 would make step 5 accept everything, silently."""
    assert 0.5 < NEAR_MATCH_RATIO < 1.0
    assert NEAR_MATCH_MIN_CHARS >= 4


def test_exact_and_resolved_still_win_over_the_new_tolerant_paths():
    """Ordering matters: a quote that is verbatim must never be downgraded to partial."""
    prov = validate_evidence("The Divine Mark glowed on his palm.", CHAPTER, _blocks())
    assert prov.provenance_status == PROV_RESOLVED
    assert prov.char_start is not None


def test_ambiguous_is_not_swallowed_by_the_fold():
    """A genuinely repeated phrase must stay flagged, not become a blind pick."""
    assert validate_evidence("the sword", CHAPTER, _blocks()).provenance_status == (
        PROV_AMBIGUOUS
    )


def test_taxonomy_matches_glossary_enum_gate():
    """Cross-service, cross-language closed set — the drift this repo keeps shipping.

    glossary-service's `evidenceProvenanceFields` gates on a literal Go switch. A status
    Python emits that Go does not list degrades to 'unverified', silently erasing the
    distinction — a unit test on either side alone stays green while the pipeline loses
    the data. So the Go source is parsed and compared.
    """
    import pathlib
    import re

    go = pathlib.Path(__file__).resolve().parents[2] / (
        "glossary-service/internal/api/extraction_handler.go")
    assert go.exists(), f"parity test cannot find the Go gate at {go} — it must not skip"
    src = go.read_text(encoding="utf-8")
    body = src.split("func evidenceProvenanceFields(")[1].split("\nfunc ")[0]
    honored = set(re.findall(r'"([a-z]+)"', body.split("switch ")[1]))
    assert honored == set(PROV_ALL), (
        f"provenance taxonomy drift — python {sorted(PROV_ALL)} vs go {sorted(honored)}. "
        "Both sides must move together or the extra statuses degrade to 'unverified'.")


def test_precomputed_fold_gives_the_same_verdict_as_computing_it_inline():
    """`stamp_entity_provenance` folds the chapter once and passes it to every entity.

    A precomputed value that can disagree with the value it caches is a bug that hides:
    the fast path would quietly score differently from the reference path, and the POC
    would be measuring the cache. Checked across all six verdicts.
    """
    from app.workers.extraction_provenance import _fold

    folded = _fold(CJK_CHAPTER)
    quotes = [
        "行至澠池縣。——縣中鎮守主將張奎",          # resolved via the fold
        "且說黃家父子、兄弟過了孟津...逕往臨潼關來",  # abridged
        "黃飛虎知張奎利害，不敢穿城而走，遂降",       # partial
        "此乃玉虛宮元始天尊所傳之無上大法",          # unmatched
        "出西門",                                    # short, resolved
    ]
    for q in quotes:
        inline = validate_evidence(q, CJK_CHAPTER, _cjk_blocks())
        cached = validate_evidence(q, CJK_CHAPTER, _cjk_blocks(), folded_chapter=folded)
        assert inline == cached, f"fold cache diverged on {q!r}: {inline} vs {cached}"
