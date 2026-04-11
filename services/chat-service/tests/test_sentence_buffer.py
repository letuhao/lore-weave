"""Unit tests for SentenceBuffer — voice TTS sentence splitting."""
import pytest

from app.services.sentence_buffer import SentenceBuffer


class TestBasicSentences:
    def test_single_sentence(self):
        buf = SentenceBuffer()
        result = buf.push("Hello world. ")
        assert result == ["Hello world."]

    def test_two_sentences(self):
        buf = SentenceBuffer()
        result = buf.push("First sentence. Second sentence. ")
        assert len(result) == 2
        assert result[0] == "First sentence."
        assert result[1] == "Second sentence."

    def test_incremental_tokens(self):
        buf = SentenceBuffer()
        assert buf.push("Hello ") == []
        assert buf.push("world") == []
        result = buf.push(". ")
        assert result == ["Hello world."]

    def test_question_mark(self):
        buf = SentenceBuffer()
        result = buf.push("How are you? ")
        assert result == ["How are you?"]

    def test_exclamation(self):
        buf = SentenceBuffer()
        result = buf.push("That's great! ")
        assert result == ["That's great!"]

    def test_flush_remaining(self):
        buf = SentenceBuffer()
        buf.push("Hello world")
        remaining = buf.flush()
        assert remaining == "Hello world"

    def test_flush_empty(self):
        buf = SentenceBuffer()
        assert buf.flush() is None

    def test_flush_after_sentence(self):
        buf = SentenceBuffer()
        buf.push("First. Second")
        remaining = buf.flush()
        assert remaining == "Second"

    def test_pending_property(self):
        buf = SentenceBuffer()
        buf.push("Hello world")
        assert buf.pending == "Hello world"


class TestCJK:
    def test_chinese_period(self):
        buf = SentenceBuffer()
        result = buf.push("你好世界。")
        assert result == ["你好世界。"]

    def test_chinese_question(self):
        buf = SentenceBuffer()
        result = buf.push("你好吗？")
        assert result == ["你好吗？"]

    def test_chinese_exclamation(self):
        buf = SentenceBuffer()
        result = buf.push("太好了！")
        assert result == ["太好了！"]

    def test_japanese_mixed(self):
        buf = SentenceBuffer()
        result = buf.push("これはテストです。次の文。")
        assert len(result) == 2


class TestClauseMode:
    def test_clause_mode_off_no_split(self):
        buf = SentenceBuffer(clause_mode=False)
        text = "Well, I think the translation looks good, but you might reconsider"
        result = buf.push(text)
        assert result == []  # No sentence boundary, no clause split

    def test_clause_mode_comma_split(self):
        buf = SentenceBuffer(clause_mode=True)
        text = "Well, I think the translation looks really good, but you might want to reconsider the wording"
        result = buf.push(text)
        assert len(result) >= 1
        # Should split at a comma after 40+ chars

    def test_clause_mode_respects_min_length(self):
        buf = SentenceBuffer(clause_mode=True)
        result = buf.push("Short, text")
        assert result == []  # Too short for clause split

    def test_clause_mode_semicolon(self):
        buf = SentenceBuffer(clause_mode=True)
        text = "The first part of the response is quite detailed; the second part needs more work"
        result = buf.push(text)
        assert len(result) >= 1

    def test_clause_mode_em_dash(self):
        buf = SentenceBuffer(clause_mode=True)
        text = "This is a really long clause that goes on and on — and then there is more text after it"
        result = buf.push(text)
        assert len(result) >= 1

    def test_cjk_clause_comma(self):
        buf = SentenceBuffer(clause_mode=True)
        # Need 40+ chars before the comma for clause split to trigger
        # Each CJK char is 1 Python char, so we need a long sentence
        long_text = "这是一个非常非常非常非常非常非常非常非常非常非常非常长的句子，它包含了很多很多的内容和非常详细的描述信息，然后我们继续说更多的话"
        result = buf.push(long_text)
        assert len(result) >= 1


class TestAbbreviations:
    def test_mr_not_split(self):
        buf = SentenceBuffer()
        result = buf.push("Hello Mr. Smith. ")
        assert len(result) == 1
        assert "Mr. Smith" in result[0]

    def test_dr_not_split(self):
        buf = SentenceBuffer()
        result = buf.push("See Dr. Jones today. ")
        assert len(result) == 1
        assert "Dr. Jones" in result[0]

    def test_eg_not_split(self):
        buf = SentenceBuffer()
        result = buf.push("Use a framework e.g. React or Vue. ")
        assert len(result) == 1


class TestMaxLength:
    def test_force_split_long_text(self):
        buf = SentenceBuffer()
        # Generate text > 300 chars with no sentence boundary
        text = "word " * 80  # 400 chars
        result = buf.push(text)
        assert len(result) >= 1
        for s in result:
            assert len(s) <= 310  # some tolerance for word boundary

    def test_split_at_natural_point(self):
        buf = SentenceBuffer()
        text = "a " * 100 + ", " + "b " * 100  # comma around 200
        result = buf.push(text)
        assert len(result) >= 1


class TestEdgeCases:
    def test_empty_token(self):
        buf = SentenceBuffer()
        assert buf.push("") == []

    def test_only_whitespace(self):
        buf = SentenceBuffer()
        buf.push("   ")
        assert buf.flush() is None

    def test_sentence_end_no_trailing_space(self):
        """Sentence end without trailing space should NOT emit (more text may come)."""
        buf = SentenceBuffer()
        result = buf.push("Hello world.")
        assert result == []  # No trailing space = boundary not confirmed

    def test_multiple_periods(self):
        buf = SentenceBuffer()
        result = buf.push("Wait... Really? ")
        assert len(result) >= 1

    def test_quoted_sentence(self):
        buf = SentenceBuffer()
        result = buf.push('She said "hello." ')
        assert len(result) == 1

    def test_incremental_two_sentences(self):
        """Simulate real LLM token streaming across two sentences."""
        buf = SentenceBuffer()
        tokens = ["Hello", " world", ".", " ", "How", " are", " you", "?", " "]
        all_sentences = []
        for tok in tokens:
            all_sentences.extend(buf.push(tok))
        assert len(all_sentences) == 2
        assert all_sentences[0] == "Hello world."
        assert all_sentences[1] == "How are you?"

    def test_clause_forward_search(self):
        """Clause mode should emit the FIRST clause >= 40 chars (forward search)."""
        buf = SentenceBuffer(clause_mode=True)
        text = "First part of the sentence is quite long enough, second part also long enough, tiny end"
        result = buf.push(text)
        assert len(result) >= 1
        # First emitted clause should end at the first comma (not the last)
        assert result[0].endswith(",")
