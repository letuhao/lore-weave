"""
Unit tests for Translation Pipeline V2 features.

Covers:
- validate_translation_output: block count, missing/extra indices, length sanity
- extract_token_counts: OpenAI, Anthropic, Ollama, LM Studio, missing data
"""
import pytest

from app.workers.session_translator import (
    validate_translation_output,
    extract_token_counts,
    ValidationResult,
)


# ── validate_translation_output ──────────────────────────────────────────────

class TestValidateTranslationOutput:
    def test_valid_output(self):
        parsed = {0: "Hello", 1: "World"}
        result = validate_translation_output(
            parsed, [0, 1], {0: "你好", 1: "世界"}
        )
        assert result.valid is True
        assert result.errors == []

    def test_block_count_mismatch(self):
        parsed = {0: "Hello"}  # expected 2
        result = validate_translation_output(
            parsed, [0, 1], {0: "你好", 1: "世界"}
        )
        assert result.valid is False
        assert any("block_count_mismatch" in e for e in result.errors)

    def test_missing_blocks(self):
        parsed = {0: "Hello"}
        result = validate_translation_output(
            parsed, [0, 1], {0: "你好", 1: "世界"}
        )
        assert any("missing_blocks" in e for e in result.errors)

    def test_extra_blocks(self):
        parsed = {0: "Hello", 1: "World", 99: "Extra"}
        result = validate_translation_output(
            parsed, [0, 1], {0: "你好", 1: "世界"}
        )
        assert any("extra_blocks" in e for e in result.errors)

    def test_length_too_long_warning(self):
        # Output 5x longer than input → warning
        parsed = {0: "x" * 500}
        result = validate_translation_output(
            parsed, [0], {0: "y" * 100}
        )
        assert result.valid is True  # warnings don't invalidate
        assert any("too_long" in w for w in result.warnings)

    def test_length_too_short_warning(self):
        # Output 0.1x of input → warning
        parsed = {0: "x"}
        result = validate_translation_output(
            parsed, [0], {0: "y" * 100}
        )
        assert result.valid is True
        assert any("too_short" in w for w in result.warnings)

    def test_empty_input_no_crash(self):
        """Empty input text shouldn't cause division by zero."""
        parsed = {0: "Hello"}
        result = validate_translation_output(
            parsed, [0], {0: ""}
        )
        assert result.valid is True

    def test_perfect_match(self):
        parsed = {0: "Chương một", 3: "Đoạn thứ hai", 7: "Kết thúc"}
        result = validate_translation_output(
            parsed, [0, 3, 7],
            {0: "第一章", 3: "第二段", 7: "结束"},
        )
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_all_missing(self):
        parsed = {}
        result = validate_translation_output(
            parsed, [0, 1, 2], {0: "a", 1: "b", 2: "c"}
        )
        assert result.valid is False
        assert any("block_count_mismatch" in e for e in result.errors)
        assert any("missing_blocks" in e for e in result.errors)


# ── extract_token_counts ─────────────────────────────────────────────────────

class TestExtractTokenCounts:
    def test_openai_format(self):
        """OpenAI: usage.prompt_tokens + usage.completion_tokens"""
        response = {
            "usage": {"prompt_tokens": 1500, "completion_tokens": 2000}
        }
        in_tok, out_tok = extract_token_counts(response)
        assert in_tok == 1500
        assert out_tok == 2000

    def test_anthropic_format(self):
        """Anthropic: usage.input_tokens + usage.output_tokens"""
        response = {
            "usage": {"input_tokens": 1200, "output_tokens": 1800}
        }
        in_tok, out_tok = extract_token_counts(response)
        assert in_tok == 1200
        assert out_tok == 1800

    def test_ollama_format(self):
        """Ollama: top-level prompt_eval_count + eval_count"""
        response = {
            "prompt_eval_count": 4676,
            "eval_count": 7000,
        }
        in_tok, out_tok = extract_token_counts(response)
        assert in_tok == 4676
        assert out_tok == 7000

    def test_lm_studio_format(self):
        """LM Studio: same as OpenAI (usage.prompt_tokens)"""
        response = {
            "usage": {"prompt_tokens": 900, "completion_tokens": 1100}
        }
        in_tok, out_tok = extract_token_counts(response)
        assert in_tok == 900
        assert out_tok == 1100

    def test_empty_response(self):
        """No token info → (0, 0)."""
        in_tok, out_tok = extract_token_counts({})
        assert in_tok == 0
        assert out_tok == 0

    def test_partial_response(self):
        """Only input tokens available."""
        response = {"usage": {"input_tokens": 500}}
        in_tok, out_tok = extract_token_counts(response)
        assert in_tok == 500
        assert out_tok == 0

    def test_ollama_mixed_with_usage(self):
        """If both top-level and usage exist, usage takes priority."""
        response = {
            "usage": {"input_tokens": 100, "output_tokens": 200},
            "prompt_eval_count": 999,
            "eval_count": 888,
        }
        in_tok, out_tok = extract_token_counts(response)
        # usage.input_tokens matches first
        assert in_tok == 100
        assert out_tok == 200

    def test_string_values_converted(self):
        """String token counts should be converted to int."""
        response = {"usage": {"prompt_tokens": "1500", "completion_tokens": "2000"}}
        in_tok, out_tok = extract_token_counts(response)
        assert in_tok == 1500
        assert out_tok == 2000
