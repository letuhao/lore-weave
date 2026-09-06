"""D-NAME-GROUNDING-MISSES-DIACRITIC-NAMES — diagnosed (T46i), FIXED (T46n). §2.1b.

The defect, measured 2026-08-21: `audit_names` compared WORD against WORD. The cast was
tokenised to its syllables (three names -> eight known entries) and the draft to individual
capitalised words, so an invented name assembled from syllables that each appear in some OTHER
character's name matched on every token:

    known   {"Lam Trach", "Lam Uyen", "To Thanh Dao"}
    draft   "The door opened. Thanh Trach Uyen entered, and no one spoke."
    result  unanchored: []      <- CLEAN, on an invented character

The syllable expansion is not the bug — `audit_names` documents it as a deliberate trade,
*"an invented full name whose FAMILY name matches a canon character will now anchor on that
part, trading some recall for a large precision gain"*. `extract_name_runs` is the half that
buys the recall back: compare the whole RUN against the whole NAME, and fall through to the
per-word pass for anything a run did not cover.

The two false-accusation constraints §2.1b set, and how each is met — both learned the hard
way, because the first implementation violated both and the existing suite caught it:

  1. **A run matching a known full name anchors ALL of its words.** The run side trims leading
     function words (`The Grey Wren` -> `Grey Wren`), so the KNOWN side is trimmed identically.
     Trimming only one side reported the book's own authored alias as invented.
  2. **Sentence-initial ambiguity cannot manufacture a run.** `The door opened` is not a run
     because `door` is not capitalised; `Then Blorpnax` trims to one word and falls through to
     the per-word pass. `_FUNCTION_WORDS` does this rather than "does it appear lowercase in
     the corpus", which fails on a short passage where `then` never occurs lowercased.
"""

from __future__ import annotations

from app.engine.name_grounding import (
    audit_names,
    extract_name_runs,
    extract_names,
    known_names_from_cast,
)

_KNOWN_ROWS = [{"name": "Lam Trach"}, {"name": "Lam Uyen"}, {"name": "To Thanh Dao"}]
_PROMPT = "Lam Uyen is the protagonist. To Thanh Dao betrayed him."
#: every syllable is a real syllable of a DIFFERENT character; the combination is invented
_INVENTED = "The door opened. Thanh Trach Uyen entered, and no one spoke."
_FRAGMENT_CASE = "Lam Uyen turned. Trinh Hac Vu stood in the doorway, saying nothing."


def _known():
    return known_names_from_cast(_KNOWN_ROWS)


def test_an_invented_name_built_from_KNOWN_SYLLABLES_is_now_REPORTED():
    """The defect, fixed. Each syllable is real; the combination is not, and the whole run is
    what reaches the author."""
    audit = audit_names(_INVENTED, _PROMPT, "vi", known_names=_known())
    assert audit.unanchored == ["Thanh Trach Uyen"], (
        f"the invented combination should be reported whole, got {audit.unanchored}"
    )


def test_the_author_gets_the_WHOLE_name_not_a_syllable_of_it():
    """`Trinh Hac Vu` has one unknown syllable, so the old code fired — and reported `Hac`.
    A reader who looks `Hac` up in the glossary and finds nothing still does not know which
    name was invented."""
    audit = audit_names(_FRAGMENT_CASE, _PROMPT, "vi", known_names=_known())
    assert audit.unanchored == ["Trinh Hac Vu"], f"got {audit.unanchored}"


def test_a_KNOWN_multi_word_name_in_the_draft_is_NOT_accused():
    """Constraint 1. `Lam Uyen` is canon and appears in both drafts above; if the run pass
    reported it, the fix would have traded a miss for a false accusation — the error direction
    this module says matters."""
    for draft in (_INVENTED, _FRAGMENT_CASE):
        audit = audit_names(draft, _PROMPT, "vi", known_names=_known())
        assert "Lam Uyen" not in audit.unanchored, f"canon accused in {draft!r}"


def test_sentence_initial_prose_does_NOT_become_a_run():
    """Constraint 2, isolated. `The door opened` is a capitalised word followed by lowercase
    ones; treating it as a two-word name would accuse the prose itself."""
    runs = extract_name_runs(_INVENTED, _INVENTED + _PROMPT)
    assert not any(r.startswith("The ") for r in runs), runs
    assert "Thanh Trach Uyen" in runs


def test_a_leading_function_word_is_trimmed_on_BOTH_sides():
    """The bug the first implementation shipped: the run side trimmed `The` and the known side
    did not, so the authored alias `The Grey Wren` was reported as invented."""
    known = known_names_from_cast([{"name": "Aurelia", "aliases": ["The Grey Wren"]}])
    audit = audit_names("The Grey Wren crossed the bridge.", "Aurelia waited.", "en",
                        known_names=known)
    assert audit.unanchored == [], f"an authored alias was accused: {audit.unanchored}"


def test_a_run_that_trims_to_ONE_word_falls_through_to_the_per_word_pass():
    """`Then Blorpnax` is not a two-word name. Trimming leaves one word, which the per-word
    pass owns — that is where plural tolerance and near-miss logic already live."""
    known = known_names_from_cast([{"name": "Aurelia"}])
    audit = audit_names("Aurelia waited. Then Blorpnax arrived.", "Aurelia waited.", "en",
                        known_names=known)
    assert audit.unanchored == ["Blorpnax"], f"got {audit.unanchored}"


def test_the_per_word_pass_still_runs_for_single_word_names():
    """The fix must not replace the old behaviour, only cover what it missed."""
    known = known_names_from_cast([{"name": "Aurelia"}])
    audit = audit_names("Aurelia met Varenne alone.", "Aurelia waited.", "en",
                        known_names=known)
    assert "Varenne" in audit.unanchored


def test_the_check_still_ANNOUNCES_itself_honestly():
    """Unchanged by the fix, and the reason the defect was visible at all."""
    audit = audit_names(_INVENTED, _PROMPT, "vi", known_names=_known())
    assert audit.truth_source == "glossary"
    assert audit.method == "capitalised_latin"
    assert audit_names(_INVENTED, _PROMPT, "zh", known_names=_known()).method == "caseless_script"


def test_extract_names_is_untouched_so_the_per_word_contract_holds():
    """`extract_name_runs` is additive: the word extractor still emits words, so every existing
    caller and assertion keeps its meaning."""
    got = extract_names(_INVENTED, _INVENTED + _PROMPT)
    assert "Thanh Trach Uyen" not in got
