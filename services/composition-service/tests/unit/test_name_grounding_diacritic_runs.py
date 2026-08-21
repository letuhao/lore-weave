"""D-NAME-GROUNDING-MISSES-DIACRITIC-NAMES — DIAGNOSED and pinned (T46i, 2026-08-21).

The deferral said: *"Inspect `audit_names` against Vietnamese diacritic names —
`capitalised_latin` is the suspect: either its extractor does not treat the diacritic run as
one name, or a partial match against a real entity anchors it."* It is **both, and the second
is the one that produces the reported symptom**.

The reported symptom was `name_grounding: "checked"` with `unanchored_names: []` on a draft
that introduced an invented three-syllable Vietnamese character name. Reproduced minimally:

    known   {"Lam Trach", "Lam Uyen", "To Thanh Dao"}      -> known_count 8, NOT 3
    draft   "The door opened. Thanh Trach Uyen entered, and no one spoke."
    result  unanchored: []   near_misses: []   <- CLEAN, on an invented character

THE MECHANISM. `audit_names` tokenises BOTH sides to WORDS: the known cast becomes its
individual syllables (plus the full forms) and the draft becomes individual capitalised words.
The comparison is therefore word-against-word. Vietnamese names are compositions of a small
pool of recurring syllables, so an invented name assembled from syllables that each appear in
some OTHER character's name matches on every token and the novel COMBINATION is never
examined. `Thanh`, `Trach` and `Uyen` are each real; `Thanh Trach Uyen` is not, and nothing in
the check ever looks at that string.

Two amplifiers, neither of them the root cause:
  * `len(word) < 3` drops short syllables outright — `Vu` in the fixture below, and `Kỵ`/`Vô`  # doc-language-gate: ok -- the 2-char diacritic syllables ARE the measurement
    in the real corpus, so those cannot be flagged even in principle;
  * `_is_name` discounts sentence-initial capitals, removing a run's head.

WHY THIS PINS THE BUG INSTEAD OF FIXING IT — decided, see §2.1b.
The fix is to compare the capitalised RUN against the known FULL names, not syllables against
syllables. That is a design change to a check whose own note says which error direction
matters — *"a name missing from `known` becomes a false accusation an author reads"* — and
run-joining manufactures exactly that risk ("The Grey Wren", a title followed by a name, a
sentence-initial verb phrase). It touches 35 assertions and 3 production call sites. These
tests fail the moment the behaviour changes, so the fix arrives deliberately with its own
evidence rather than drifting in.
"""

from __future__ import annotations

from app.engine.name_grounding import audit_names, extract_names, known_names_from_cast

_KNOWN_ROWS = [{"name": "Lam Trach"}, {"name": "Lam Uyen"}, {"name": "To Thanh Dao"}]
_PROMPT = "Lam Uyen is the protagonist. To Thanh Dao betrayed him."
#: every syllable is a real syllable of a DIFFERENT character; the combination is invented
_INVENTED = "The door opened. Thanh Trach Uyen entered, and no one spoke."
_FRAGMENT_CASE = "Lam Uyen turned. Trinh Hac Vu stood in the doorway, saying nothing."


def _known():
    return known_names_from_cast(_KNOWN_ROWS)


def test_an_invented_name_built_from_KNOWN_SYLLABLES_reads_CLEAN():
    """The reported symptom, reproduced. This is the whole deferral in one assertion.

    If it starts failing, the run-level comparison landed — that is the fix, not a
    regression. Update §2.1b and delete these pins in the SAME commit.
    """
    audit = audit_names(_INVENTED, _PROMPT, "vi", known_names=_known())
    assert audit.unanchored == [], (
        f"the invented-combination case now reports {audit.unanchored} — the run-level fix for "
        "D-NAME-GROUNDING-MISSES-DIACRITIC-NAMES appears to have landed. Re-read §2.1b and "
        "remove these pins in the same commit, so the plan and the code stop disagreeing."
    )
    assert audit.near_misses == []


def test_the_known_side_is_tokenised_to_SYLLABLES_which_is_why():
    """The cause, isolated from the symptom. Three cast names yield EIGHT known entries: the
    individual syllables of ≥3 characters plus the full forms. Word-against-word comparison
    follows from this, and so does the miss above.
    """
    audit = audit_names(_INVENTED, _PROMPT, "vi", known_names=_known())
    assert len(_known()) == 3, "the cast really is three names"
    assert audit.known_count == 8, (
        f"known_count is {audit.known_count}; the syllable-splitting that causes this defect "
        "may have changed. Re-derive the diagnosis in §2.1b before trusting it."
    )


def test_the_multi_syllable_name_is_never_ONE_candidate():
    """Amplifier 1 — there is no run-joining, so the invented string is never compared."""
    assert "Thanh Trach Uyen" not in extract_names(_INVENTED, _INVENTED + _PROMPT)


def test_a_two_character_syllable_is_invisible_to_the_extractor():
    """Amplifier 2, with its control: a 3-character sibling from the SAME name IS seen, so the
    length floor is what excluded `Vu` rather than some other filter."""
    got = extract_names(_FRAGMENT_CASE, _FRAGMENT_CASE + _PROMPT)
    assert "Vu" not in got
    assert "Hac" in got


def test_when_a_syllable_IS_unknown_the_author_gets_a_FRAGMENT():
    """The other half of the harm. `Trinh Hac Vu` contains one unknown syllable, so the check
    does fire — and reports `Hac`. A reader who looks `Hac` up in the glossary and finds
    nothing still does not know which name was invented.
    """
    audit = audit_names(_FRAGMENT_CASE, _PROMPT, "vi", known_names=_known())
    assert audit.unanchored == ["Hac"], (
        f"got {audit.unanchored}; if this now names the whole run, the fix landed — see §2.1b"
    )


def test_the_check_still_ANNOUNCES_itself_honestly():
    """The control that stops the pins above being read as 'the check is broken'. It is not:
    `truth_source` and `method` are reported truthfully, which is the only reason this defect
    is visible at all. A check that misreported its own coverage would be far worse.
    """
    audit = audit_names(_INVENTED, _PROMPT, "vi", known_names=_known())
    assert audit.truth_source == "glossary"
    assert audit.method == "capitalised_latin"
    caseless = audit_names(_INVENTED, _PROMPT, "zh", known_names=_known())
    assert caseless.method == "caseless_script", (
        "a caseless script must say it cannot check, not report a clean result"
    )
