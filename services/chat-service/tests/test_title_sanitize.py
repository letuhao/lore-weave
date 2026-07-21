"""Unit tests for the auto-title sanitizer (_sanitize_title).

Pure — no DB/port. Guards the live bug where a title-gen model's list-marker /
prompt-echo output ("4.", "* Eerie Lighthouse…", the instruction itself) was
saved verbatim as the chat title.
"""

from app.services.stream_service import _sanitize_title


def test_rejects_bare_number_marker():
    # The exact live bug: session titled "4."
    assert _sanitize_title("4.") == ""
    assert _sanitize_title("1)") == ""
    assert _sanitize_title("  12. ") == ""


def test_strips_leading_list_and_markdown_noise():
    assert _sanitize_title("* Eerie Lighthouse Foreshadowing") == "Eerie Lighthouse Foreshadowing"
    assert _sanitize_title("1. The Tidewright Begins") == "The Tidewright Begins"
    assert _sanitize_title("- A Harbor of Glass") == "A Harbor of Glass"
    assert _sanitize_title("# Chapter Planning") == "Chapter Planning"


def test_strips_wrapping_quotes_and_emphasis():
    assert _sanitize_title('"The Glass Tide"') == "The Glass Tide"
    assert _sanitize_title("*Harbor Girl*") == "Harbor Girl"
    assert _sanitize_title("`New Book Setup`") == "New Book Setup"


def test_peels_stacked_markers():
    assert _sanitize_title("* 1. The Drowning Port") == "The Drowning Port"


def test_rejects_prompt_echo():
    assert _sanitize_title('The system instruction says: "Generate a concise title"') == ""
    assert _sanitize_title("Generate a concise title for this conversation") == ""
    assert _sanitize_title("Title:") == ""


def test_rejects_single_word_and_punctuation():
    assert _sanitize_title("Untitled") == ""      # 1 word — ambiguous, keep New Chat
    assert _sanitize_title("...") == ""
    assert _sanitize_title("- •") == ""


def test_rejects_refusals():
    assert _sanitize_title("I cannot generate a title for that.") == ""
    assert _sanitize_title("As an AI, I don't have enough context") == ""


def test_takes_first_line_only():
    assert _sanitize_title("The Tidewright\n(a fantasy novel)") == "The Tidewright"


def test_keeps_a_good_title_untouched():
    assert _sanitize_title("The Tidewright: Harbor of Glass") == "The Tidewright: Harbor of Glass"


def test_rejects_over_length():
    assert _sanitize_title("word " * 40) == ""
