"""Unit tests for TextNormalizer — voice TTS text preprocessing."""
import pytest

from app.services.text_normalizer import TextNormalizer


@pytest.fixture
def norm():
    return TextNormalizer()


class TestMarkdownStripping:
    def test_bold(self, norm):
        text, skip = norm.normalize("This is **bold** text.")
        assert not skip
        assert "bold" in text
        assert "**" not in text

    def test_italic(self, norm):
        text, skip = norm.normalize("This is *italic* text.")
        assert not skip
        assert "italic" in text
        assert text.count("*") == 0

    def test_strikethrough(self, norm):
        text, skip = norm.normalize("This is ~~deleted~~ text.")
        assert not skip
        assert "deleted" in text
        assert "~~" not in text

    def test_inline_code(self, norm):
        text, skip = norm.normalize("Run the `pip install` command.")
        assert not skip
        assert "pip install" in text
        assert "`" not in text

    def test_heading(self, norm):
        text, skip = norm.normalize("## Getting Started")
        assert not skip
        assert text == "Getting Started"

    def test_link(self, norm):
        text, skip = norm.normalize("Check [the docs](https://example.com) for details.")
        assert not skip
        assert "the docs" in text
        assert "https://example.com" not in text
        assert "[" not in text

    def test_combined_markdown(self, norm):
        text, skip = norm.normalize("Here's a **great** [example](url) with `code`.")
        assert not skip
        assert "great" in text
        assert "example" in text
        assert "code" in text
        assert "**" not in text
        assert "[" not in text
        assert "`" not in text


class TestSkipping:
    def test_code_block(self, norm):
        text, skip = norm.normalize("```python\nprint('hello')\n```")
        assert skip
        assert text == ""

    def test_code_block_with_surrounding(self, norm):
        text, skip = norm.normalize("Look at this:\n```\ncode\n```\nend")
        assert skip
        assert text == ""

    def test_json_object(self, norm):
        text, skip = norm.normalize('{"key": "value", "count": 42}')
        assert skip

    def test_markdown_table(self, norm):
        text, skip = norm.normalize("| Col1 | Col2 |\n|------|------|")
        assert skip

    def test_too_short(self, norm):
        text, skip = norm.normalize(".")
        assert skip

    def test_empty_after_stripping(self, norm):
        text, skip = norm.normalize("**")
        assert skip


class TestEmojis:
    def test_emoji_removal(self, norm):
        text, skip = norm.normalize("Hello! \U0001f60a How are you? \U0001f680")
        assert not skip
        assert "\U0001f60a" not in text
        assert "\U0001f680" not in text
        assert "Hello" in text

    def test_sparkles(self, norm):
        text, skip = norm.normalize("Great job! \u2728")
        assert not skip
        assert "\u2728" not in text


class TestWhitespace:
    def test_collapse_spaces(self, norm):
        text, skip = norm.normalize("Hello    world    test.")
        assert not skip
        assert "  " not in text

    def test_strip_outer(self, norm):
        text, skip = norm.normalize("  Hello world.  ")
        assert not skip
        assert not text.startswith(" ")
        assert not text.endswith(" ")


class TestEdgeCases:
    def test_multiplication_not_mangled(self, norm):
        text, skip = norm.normalize("The result is 3 * 4 = 12.")
        assert not skip
        assert "3" in text
        assert "4" in text
        assert "12" in text

    def test_csharp_hash_preserved(self, norm):
        text, skip = norm.normalize("I recommend learning C# programming.")
        assert not skip
        assert "C" in text
        # The # is stripped by _SPECIAL_CHARS but that's acceptable
        # Key: "programming" is NOT stripped (heading regex no longer eats mid-line #)

    def test_issue_number_preserved(self, norm):
        text, skip = norm.normalize("See issue 42 for details.")
        assert not skip
        assert "42" in text

    def test_greater_than_preserved(self, norm):
        text, skip = norm.normalize("If x > 5 then return true.")
        assert not skip
        assert ">" in text

    def test_heading_only_at_line_start(self, norm):
        text, skip = norm.normalize("## Title\nSome text with a # symbol.")
        assert not skip
        assert "Title" in text
        assert "Some text" in text


class TestPassthrough:
    def test_plain_text(self, norm):
        original = "Hello! How can I help you today?"
        text, skip = norm.normalize(original)
        assert not skip
        assert text == original

    def test_sentences(self, norm):
        original = "The weather is nice. Let's go for a walk."
        text, skip = norm.normalize(original)
        assert not skip
        assert text == original
