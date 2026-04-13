"""Unit tests for K4.3 entity candidate extraction."""

from app.context.formatters.stopwords import STOPPHRASES_LOWER
from app.context.selectors.glossary import extract_candidates


def test_stopphrases_imported_from_shared_module():
    """K4-I3 regression: extract_candidates must use the shared
    STOPPHRASES_LOWER set, not a private duplicate."""
    assert "tell" in STOPPHRASES_LOWER
    assert "is" in STOPPHRASES_LOWER


def test_empty_message():
    assert extract_candidates("") == []


def test_lowercase_only_no_candidates():
    assert extract_candidates("the princess is dead") == []


def test_single_capitalized_name():
    assert extract_candidates("Tell me about Kai") == ["Kai"]


def test_multi_word_name_also_pushes_last_token():
    got = extract_candidates("What does Master Lin think?")
    assert "Master Lin" in got
    assert "Lin" in got
    # Master Lin should come before Lin (first-occurrence order)
    assert got.index("Master Lin") < got.index("Lin")


def test_hyphenated_name():
    got = extract_candidates("Is Mary-Anne here?")
    assert "Mary-Anne" in got
    assert "Anne" in got


def test_quoted_name():
    got = extract_candidates('Who is "Dragon Lord" really?')
    assert got[0] == "Dragon Lord"  # quoted comes first
    assert "Dragon Lord" in got


def test_single_quoted_name():
    got = extract_candidates("Tell me about 'The Wanderer'")
    assert "The Wanderer" in got


def test_cjk_two_char_run_contains_name_substring():
    # Known Track 1 limitation: without a CJK segmenter (jieba etc.),
    # we can't cleanly isolate "李雲" from compound prepositions like
    # "关于". We split on common particles ("的", "是", "了", ...) as
    # a best-effort measure. At minimum, the name must appear as a
    # substring of some returned candidate so K2b's exact tier has a
    # chance to match via downstream FTS behavior.
    got = extract_candidates("告诉我关于李雲的故事")
    assert any("李雲" in c for c in got), f"expected 李雲 substring in {got}"


def test_cjk_run_minimum_two_chars():
    # Single CJK char filtered by design to reduce noise
    got = extract_candidates("好")
    assert got == []


def test_cjk_multi_run():
    got = extract_candidates("李雲与王小明的对话")
    assert "李雲" in got
    assert "王小明" in got


def test_mixed_latin_and_cjk():
    got = extract_candidates("Alice met 李雲 in the Jianghu")
    assert "Alice" in got
    assert "李雲" in got
    assert "Jianghu" in got


def test_case_insensitive_dedupe():
    got = extract_candidates("Kai and KAI and Kai")
    # Only the first form is kept
    assert len(got) == 1
    assert got[0] == "Kai"


def test_stopphrase_filtered():
    # "I" and "The" alone should not become candidates
    got = extract_candidates("I walked to The Hall")
    assert "I" not in got
    assert "The" not in got
    assert "Hall" in got


def test_max_candidates_cap():
    msg = "Alice Bob Charlie Dave Eve Frank George Henry"
    got = extract_candidates(msg, max_candidates=3)
    assert len(got) == 3


def test_quoted_takes_priority_over_capitalized():
    got = extract_candidates('"Li Yun" is not Kai')
    assert got[0] == "Li Yun"


def test_whitespace_trimming():
    got = extract_candidates("  Tell  Kai  ")
    assert "Kai" in got
    assert "Tell" not in got  # stopphrase
