"""Tests for extraction evidence provenance validation (PROV/M3 — INV-7 / T1).

The defense under test: a model evidence quote is grounded to the REAL chapter text
by authoritative search, a model-supplied offset is a HINT verified before trust, and
an unverifiable quote NEVER gets a fabricated offset (the confidently-wrong-citation
failure mode). Status taxonomy: exact / resolved / ambiguous / unmatched.
"""
from app.workers.extraction_provenance import (
    PROV_AMBIGUOUS,
    PROV_EXACT,
    PROV_RESOLVED,
    PROV_UNMATCHED,
    build_block_offset_map,
    stamp_entity_provenance,
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
