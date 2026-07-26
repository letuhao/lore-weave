"""ML-1 / ML-4 enforcement — per-language golden-fixture coverage.

The multilingual standard mandates ≥1 golden fixture per *first-class extraction
language* so an unproven language reads RED (checklist ≠ enforcement — a language
can be "supported" in `patterns/` yet have zero gold proving it works). Before
this test the corpus had 6 en / 2 zh / 2 vi and **0 ja / 0 ko** despite ja/ko
being first-class, and nothing failed.

Two scopes deliberately differ (do NOT conflate):
  • **Extraction** languages = `patterns.SUPPORTED_LANGUAGES` (en/vi/zh/ja/ko +
    degrade-open) — the languages with rule-based pattern sets. This is what
    needs golden proof.
  • **UI-locale** set = the 18-locale frontend Registry (`lib/languages.ts`).
    Rendering the UI / translating INTO a language needs no extraction patterns,
    so that set is larger and is NOT what this test governs.

Enforcement contract: every extraction language must be either PROVEN (has a
golden fixture) or listed in KNOWN_GAPS with a tracked deferral. A first-class
language that is neither fails the build — you can't silently add an unproven
language. When gold is finally adjudicated for a KNOWN_GAP language, the
"not-both" assertion fails and tells you to promote it to required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.extraction.patterns import SUPPORTED_LANGUAGES

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
_GOLDEN_DIRS = (_FIXTURES / "golden_chapters", _FIXTURES / "golden_candidates")

# Languages that are first-class in patterns/ but have NO golden fixture yet.
# Adjudicated gold needs a human native-speaker pass (never LLM-graded-by-LLM),
# so an agent can't just fabricate it — the gap is tracked, not hidden.
KNOWN_GAPS: dict[str, str] = {
    "ja": "D-ML-JAKO-GOLDEN-ADJUDICATION — needs a human-adjudicated ja gold chapter",
    "ko": "D-ML-JAKO-GOLDEN-ADJUDICATION — needs a human-adjudicated ko gold chapter",
}


def _lang_of_dir(name: str) -> str:
    """Infer a fixture's language from its dir name (`journey_west_zh_ch01` → zh,
    `luc_van_tien_vi` → vi, `alice_ch01` → en). Language is an explicit
    `_<code>` token; absence means English (the un-suffixed default)."""
    tokens = set(name.split("_"))
    for lang in SUPPORTED_LANGUAGES:
        if lang != "en" and lang in tokens:
            return lang
    return "en"


def _proven_languages() -> set[str]:
    proven: set[str] = set()
    for base in _GOLDEN_DIRS:
        if not base.is_dir():
            continue
        for child in base.iterdir():
            if child.is_dir() and (child / "chapter.txt").is_file():
                proven.add(_lang_of_dir(child.name))
    return proven


def test_every_extraction_language_is_proven_or_a_tracked_gap():
    proven = _proven_languages()
    for lang in SUPPORTED_LANGUAGES:
        assert lang in proven or lang in KNOWN_GAPS, (
            f"extraction language {lang!r} has no golden fixture and is not a "
            f"tracked KNOWN_GAP — add a golden fixture or a tracked deferral row."
        )


def test_core_languages_have_gold():
    # en/vi/zh are proven today — lock it so a fixture deletion reads RED.
    proven = _proven_languages()
    for lang in ("en", "vi", "zh"):
        assert lang in proven, f"{lang!r} lost its golden fixture coverage"


def test_known_gaps_are_still_gaps_and_in_scope():
    proven = _proven_languages()
    for lang in KNOWN_GAPS:
        assert lang in SUPPORTED_LANGUAGES, (
            f"KNOWN_GAP {lang!r} is not a first-class extraction language — stale entry"
        )
        # When gold is finally adjudicated for this language, this fails ON PURPOSE:
        # remove it from KNOWN_GAPS so the first test starts requiring it.
        assert lang not in proven, (
            f"{lang!r} now HAS a golden fixture — remove it from KNOWN_GAPS so "
            f"coverage becomes required, not merely tracked."
        )


@pytest.mark.parametrize("lang", sorted(KNOWN_GAPS))
def test_known_gap_is_documented(lang: str):
    assert KNOWN_GAPS[lang].strip(), f"KNOWN_GAP {lang!r} needs a tracked reason"
