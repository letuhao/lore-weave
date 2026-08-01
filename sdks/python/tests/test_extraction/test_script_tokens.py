"""`script_tokens` — the ML-3 overlap tokenizer.

It exists because a word-token set is not an overlap test for every language. The code it
replaced used a 4-or-more word-character regex, which LOOKS language-neutral (that class
does match Han) and was dead for every script without spaces: a Chinese clause comes back
as ONE token, so an intersection against it can only fire on a byte-identical string.
Every test here is written against that failure mode.
"""
from loreweave_extraction.name_normalize import script_tokens


def test_spaced_script_yields_words_and_drops_short_noise():
    t = script_tokens("The revenge must cost the avenger something")
    assert {"revenge", "avenger", "cost", "must"} <= t
    assert "the" not in t, "a 3-letter stopword is noise, not an overlap signal"


def test_two_chinese_clauses_that_SHARE_a_term_actually_overlap():
    """THE bug. Neither string contains the other and they are not byte-identical, so a
    whole-token intersection returned nothing — the anchor-echo link was structurally
    unreachable for a Chinese author."""
    a = script_tokens("复仇必须让复仇者付出代价")
    b = script_tokens("这一章讲复仇的代价")
    assert a & b, "no overlap found between two clauses that plainly share terms"
    assert {"复仇", "代价"} <= a & b


def test_two_unrelated_chinese_clauses_do_not_overlap_on_content():
    a = script_tokens("修真世界的宗门规则")
    b = script_tokens("咖啡馆的下午")
    assert not (a & b)


def test_a_two_character_term_is_reachable():
    """Most Chinese words are two characters (发布, 会议, 计划), so 3-grams alone would
    make a two-character query unmatchable — both widths are load-bearing."""
    assert "会议" in script_tokens("明天的会议安排")


def test_japanese_and_korean_produce_tokens_at_all():
    assert script_tokens("復讐者は代償を求める")
    assert script_tokens("복수자는 대가를 요구한다")


def test_vietnamese_keeps_its_diacritics_and_folds_case():
    t = script_tokens("Uyển phải trả giá cho việc báo thù")
    assert "uyển" in t, "a diacritic is part of the word, not noise to strip"
    assert "viec" not in t


def test_full_width_latin_folds_to_the_same_token():
    assert script_tokens("Ｒｅｖｅｎｇｅ") == script_tokens("revenge")


def test_ngrams_never_span_a_run_boundary():
    """n-grams are computed PER RUN. Spanning them would manufacture tokens the source
    never contained — two terms sitting apart would match a query that needs them
    adjacent (the review-impl finding on the crypto tokenizer of the same shape)."""
    t = script_tokens("复仇 代价")          # a space between the two runs
    assert "仇代" not in t


def test_empty_and_non_string_are_safe():
    assert script_tokens("") == set()
    assert script_tokens("   ") == set()
    assert script_tokens(None) == set()      # type: ignore[arg-type]
    assert script_tokens("1234 !!!") == set(), "digits and punctuation are not words"
