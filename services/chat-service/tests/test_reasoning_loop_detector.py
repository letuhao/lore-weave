"""Unit tests for the streaming reasoning-loop detector (D-REASONING-LOOP).

Pure — no DB/port, no xdist_group needed.
"""

from app.services.reasoning_loop_detector import ReasoningLoopDetector, _normalize


# The EXACT shape captured live from the Gemma-4 26B hang (book The Tidewright,
# chat 019f82b3): a period-2 oscillation between two tool choices.
REAL_LOOP = (
    "The user wants to update the book's description.\n"
    "I have the book_id already.\n"
    + (
        "Actually, I'll try to use book_update_meta first.\n"
        "Wait, I'll try to use propose_record_edit with the book_id and see if it works.\n"
    )
    * 20
)


def _feed_all(det: ReasoningLoopDetector, text: str, chunk: int = 7) -> bool:
    """Feed the text in small arbitrary chunks (simulate stream deltas split
    mid-line) and return whether the detector tripped."""
    for i in range(0, len(text), chunk):
        if det.feed(text[i : i + chunk]):
            return True
    return False


def test_trips_on_the_real_captured_loop():
    det = ReasoningLoopDetector()
    assert _feed_all(det, REAL_LOOP) is True
    assert det.tripped
    assert "cycle" in det.reason or "repeated" in det.reason


def test_period_two_oscillation_trips():
    det = ReasoningLoopDetector()
    text = ("Use tool A now.\n" "No, use tool B instead.\n") * 6
    assert _feed_all(det, text) is True


def test_single_line_stuck_repeat_trips():
    det = ReasoningLoopDetector(repeat_threshold=4)
    text = "I am not sure which tool to call here.\n" * 6
    assert _feed_all(det, text) is True
    assert "repeated" in det.reason


def test_normal_reasoning_does_not_trip():
    det = ReasoningLoopDetector()
    text = (
        "The user wants a dramatic description.\n"
        "The book is a fantasy about a harbor girl.\n"
        "I should call book_update_meta with the new description.\n"
        "The book_id is known from the earlier create.\n"
        "I will set description and summary together.\n"
        "Then I will confirm the change to the user.\n"
    )
    assert _feed_all(det, text) is False
    assert not det.tripped


def test_normalization_folds_case_whitespace_and_markers():
    # Cosmetic variation between repeats must still hash equal.
    assert _normalize("  Actually, use `book_update_meta`. ") == _normalize(
        "actually, use book_update_meta"
    )
    det = ReasoningLoopDetector(repeat_threshold=3)
    text = (
        "Actually, use book_update_meta.\n"
        "  Actually,   use `book_update_meta`.  \n"
        "ACTUALLY, USE book_update_meta\n"
    )
    assert _feed_all(det, text) is True


def test_short_filler_never_trips():
    # blank lines / tiny tokens repeated must be ignored (below min_segment_len).
    det = ReasoningLoopDetector()
    text = ("ok.\n" "\n" "- \n" ".\n") * 10
    assert _feed_all(det, text) is False


def test_sentence_split_catches_loop_without_newlines():
    # A loop streamed as ONE long line (no newlines) must still decompose.
    det = ReasoningLoopDetector()
    text = (
        "Actually I will use book_update_meta. Wait I will use propose_record_edit. "
    ) * 8
    assert _feed_all(det, text, chunk=5) is True


def test_feed_is_idempotent_after_trip():
    det = ReasoningLoopDetector()
    assert _feed_all(det, REAL_LOOP) is True
    # Further feeds keep returning True and never raise.
    assert det.feed("anything at all here.\n") is True
    assert det.tripped


def test_window_eviction_keeps_counts_bounded():
    # A repeat spread PAST the window must not trip (old occurrences evicted),
    # proving the count bookkeeping decrements on eviction.
    det = ReasoningLoopDetector(window=6, repeat_threshold=4)
    # 5 distinct filler lines between each occurrence -> occurrences never
    # coexist in a window of 6.
    lines = []
    for i in range(8):
        lines.append("The one recurring but well-spaced sentence here.")
        for j in range(5):
            lines.append(f"Distinct filler sentence number {i}-{j} here.")
    text = "\n".join(lines) + "\n"
    assert _feed_all(det, text) is False
