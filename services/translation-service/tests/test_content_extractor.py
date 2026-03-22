"""
Unit tests for content_extractor — validates B2 fix.

B2 root cause: old runner accessed resp["output"]["content"] but LM Studio / OpenAI
returns choices[0].message.content, causing KeyError that silently killed the job.
These tests enforce that extract_content handles every provider format.
"""
import pytest
from app.workers.content_extractor import extract_content


# ── OpenAI / LM Studio format ─────────────────────────────────────────────────

def test_extract_openai_format():
    output = {"choices": [{"message": {"content": "Hello world"}}]}
    assert extract_content(output) == "Hello world"


def test_extract_openai_empty_content_returns_empty_string():
    output = {"choices": [{"message": {"content": ""}}]}
    assert extract_content(output) == ""


def test_extract_openai_multiple_choices_uses_first():
    output = {"choices": [
        {"message": {"content": "first"}},
        {"message": {"content": "second"}},
    ]}
    assert extract_content(output) == "first"


# ── Anthropic format ──────────────────────────────────────────────────────────

def test_extract_anthropic_format():
    output = {"content": [{"type": "text", "text": "Xin chào thế giới"}]}
    assert extract_content(output) == "Xin chào thế giới"


def test_extract_anthropic_returns_first_content_block():
    output = {"content": [
        {"type": "text", "text": "block one"},
        {"type": "text", "text": "block two"},
    ]}
    assert extract_content(output) == "block one"


# ── Ollama chat format ────────────────────────────────────────────────────────

def test_extract_ollama_format():
    output = {"message": {"content": "Bonjour monde"}}
    assert extract_content(output) == "Bonjour monde"


# ── Raw string content ────────────────────────────────────────────────────────

def test_extract_raw_string_content():
    output = {"content": "Plain string content"}
    assert extract_content(output) == "Plain string content"


# ── Priority rules ────────────────────────────────────────────────────────────

def test_choices_takes_priority_over_content_list():
    """When both choices and content are present, choices wins (OpenAI format)."""
    output = {
        "choices": [{"message": {"content": "from choices"}}],
        "content": [{"type": "text", "text": "from content"}],
    }
    assert extract_content(output) == "from choices"


def test_content_list_takes_priority_over_message():
    """Anthropic list-content takes priority over Ollama message."""
    output = {
        "content": [{"type": "text", "text": "from content list"}],
        "message": {"content": "from message"},
    }
    assert extract_content(output) == "from content list"


# ── Error cases ───────────────────────────────────────────────────────────────

def test_raises_on_unknown_format():
    with pytest.raises(ValueError, match="Unknown invoke output format"):
        extract_content({"data": "something", "result": "something else"})


def test_raises_on_empty_dict():
    with pytest.raises(ValueError):
        extract_content({})


def test_empty_choices_list_falls_through_to_error():
    """Empty choices list is not a valid OpenAI response; should raise."""
    with pytest.raises(ValueError):
        extract_content({"choices": []})
