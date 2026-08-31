"""Name grounding across cased scripts — D-NAME-GROUNDING-MISSES-DIACRITIC-NAMES.  # doc-language-gate: ok -- Vietnamese fixture; this script IS the subject under test

Found by QC-5's own acceptance run (job `019ff423`): the drafter invented a Vietnamese
character with ZERO canon entities, and this check — the cheap deterministic one whose entire  # doc-language-gate: ok -- Vietnamese fixture; this script IS the subject under test
job is catching exactly that — reported `name_grounding: "checked"` with `unanchored_names: []`.  # doc-language-gate: ok -- Vietnamese fixture; this script IS the subject under test
The LLM canon check caught the invention; this one could not see it.

Cause: the tokeniser was `[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ-]+`, i.e. Latin-1 only. Vietnamese is a CASED
LATIN script whose letters live in Latin Extended Additional (U+1E00-U+1EFF), so the words
containing them were never tokenised at all.
"""
from __future__ import annotations

from app.engine.name_grounding import audit_names, extract_names

_CANON = {"Lâm Uyên", "Lâm Trạch", "Tô Thanh Dao", "Huyết Chủ"}  # doc-language-gate: ok -- Vietnamese fixture; this script IS the subject under test


def test_a_vietnamese_name_is_extracted_at_all():
    """🔴 The blindness itself. Before the fix these words produced NOTHING."""  # doc-language-gate: ok -- Vietnamese fixture; this script IS the subject under test
    names = extract_names("Sảnh chính im lặng. Kẻ tên Lục Vô Tội bước vào.", corpus="")  # doc-language-gate: ok -- Vietnamese fixture; this script IS the subject under test
    assert "Tội" in names, (  # doc-language-gate: ok -- Vietnamese fixture; this script IS the subject under test
        f"got {sorted(names)} — a Latin-1 tokeniser cannot see U+1EC7/U+1EE5, so the check "  # doc-language-gate: ok -- Vietnamese fixture; this script IS the subject under test
        "reports 'checked' while blind to the very names it exists to catch"
    )


def test_an_invented_vietnamese_name_is_reported_unanchored():
    draft = "Lâm Uyên đứng lặng. Kẻ tên Lục Vô Tội bước tới và cười."  # doc-language-gate: ok -- Vietnamese fixture; this script IS the subject under test
    audit = audit_names(draft, grounding="", language="vi", known_names=_CANON)
    # §2.1b — the WHOLE invented run is now reported, not a syllable of it. Reporting
    # a fragment is not merely less useful: an author who looks the fragment up in the
    # glossary and finds nothing still does not know which name was invented.
    assert audit.unanchored == ["Lục Vô Tội"], (  # doc-language-gate: ok -- the invented name IS the assertion
        f"invented name not reported as a whole: {audit.unanchored}")


def test_canon_names_are_NOT_reported_unanchored():
    """The half that makes the fix shippable rather than merely louder.

    The extractor emits single WORDS while the glossary holds full names, so `Lâm Uyên` in
    canon never matched the extracted `Lâm`/`Uyên` and the check accused the book's own
    protagonist. A check that flags canon as invented trains an author to ignore it — worse  # doc-language-gate: ok -- Vietnamese fixture; this script IS the subject under test
    than the blindness it replaced.
    """
    draft = "Lâm Uyên gặp Tô Thanh Dao trong thư phòng."  # doc-language-gate: ok -- Vietnamese fixture; this script IS the subject under test
    audit = audit_names(draft, grounding="", language="vi", known_names=_CANON)
    assert audit.unanchored == [], f"canon names falsely reported: {audit.unanchored}"


def test_a_multi_word_english_name_anchors_its_parts_too():
    """Not a Vietnamese bug. `Zaphod Beeblebrox` broke identically; it stayed invisible only
    because the Latin-1 tokeniser produced no Vietnamese extractions to mismatch."""
    audit = audit_names("Zaphod Beeblebrox met Trillian. Then Blorpnax arrived.",
                        grounding="", language="en",
                        known_names={"Zaphod Beeblebrox", "Trillian"})
    assert audit.unanchored == ["Blorpnax"], f"got {audit.unanchored}"


def test_english_extraction_is_unchanged_by_the_widening():
    names = extract_names("Elara walked to the Scribe. Bob greeted Zaphod Beeblebrox warmly.",
                          corpus="")
    assert {"Beeblebrox", "Scribe", "Zaphod"} <= names, sorted(names)


def test_a_caseless_script_still_reports_its_blindness_rather_than_a_clean_bill():
    """The widening must NOT make CJK look checkable. `.isupper()` is False for every
    character there, and the honest `caseless_script` branch is what those books get."""
    audit = audit_names("林渊走进书房。", grounding="", language="zh", known_names={"林渊"})  # doc-language-gate: ok -- Vietnamese fixture; this script IS the subject under test
    assert audit.method == "caseless_script"
    assert audit.unanchored == []


def test_ALLCAPS_is_emphasis_not_a_name():
    names = extract_names("He SHOUTED at Elara.", corpus="")
    assert "SHOUTED" not in names, sorted(names)
