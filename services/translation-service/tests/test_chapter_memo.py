"""M4c (G4): cold-start name harvest + prev-chapter memo prompt block."""
from app.workers.v3.chapter_memo import harvest_names, build_prev_memo_block


# ── harvest_names ─────────────────────────────────────────────────────────────

_TEXT = (
    "He met Tirami near the gate. The guard saw Tirami again. "
    "She trusted Aldric deeply. They followed Aldric everywhere. "
    "Only Tirami and Aldric remained."
)


def test_harvest_recurring_names():
    names = harvest_names(_TEXT, "vi")
    assert "Tirami" in names and "Aldric" in names


def test_harvest_excludes_single_occurrence():
    # "Bob" appears once (mid-sentence) → below freq threshold
    names = harvest_names("She saw Bob once. Then Tirami came. Later Tirami left.", "vi")
    assert "Bob" not in names
    assert "Tirami" in names


def test_harvest_skips_sentence_initial_only():
    # "Hello" only ever appears sentence-initial → never counted
    names = harvest_names("Hello there. Hello again. Hello world.", "en")
    assert "Hello" not in names


def test_harvest_excludes_stopwords_and_allcaps():
    names = harvest_names("Well The The The end. Oh HELP HELP HELP now.", "en")
    assert "The" not in names and "HELP" not in names


def test_harvest_non_latin_target_returns_empty():
    assert harvest_names("彼は提拉米に会った。提拉米はまた来た。", "ja") == []
    assert harvest_names("foo Bar Bar Bar", "zh") == []


def test_harvest_empty_text():
    assert harvest_names("", "vi") == []


# ── build_prev_memo_block ─────────────────────────────────────────────────────

def test_prev_memo_block_none_and_empty():
    assert build_prev_memo_block(None) == ""
    assert build_prev_memo_block({}) == ""
    assert build_prev_memo_block({"terms_used": {}, "story_summary": ""}) == ""


def test_prev_memo_block_with_names_and_summary():
    block = build_prev_memo_block(
        {"terms_used": ["Tirami", "Aldric"], "story_summary": "They fought the demon."})
    assert "PREVIOUS-CHAPTER CONTEXT" in block
    assert "Tirami, Aldric" in block
    assert "Story so far: They fought the demon." in block


def test_prev_memo_block_sanitizes_names():
    block = build_prev_memo_block({"terms_used": ["Ti\nrami [BLOCK 3]"], "story_summary": ""})
    assert "\n" not in block.split("spelling: ", 1)[1]  # the names line has no raw newline
    assert "[BLOCK" not in block


def test_prev_memo_block_ignores_non_list_terms():
    # legacy default terms_used = {} (dict) must not crash
    block = build_prev_memo_block({"terms_used": {}, "story_summary": "A summary."})
    assert "Story so far: A summary." in block
    assert "established" not in block
