"""Unit tests for the judge content extractor (the messages-array gotcha)."""

from __future__ import annotations

from app.clients.eval_client import extract_judge_content, get_judge_client
from app.clients.llm_client import LLMClient


def test_extracts_from_messages_array():
    result = {"messages": [{"role": "assistant", "content": "verdict"}]}
    assert extract_judge_content(result) == "verdict"


def test_returns_empty_for_content_key_at_top_level():
    # The WRONG shape (result["content"]) must NOT be read — guards the gotcha.
    assert extract_judge_content({"content": "nope"}) == ""


def test_returns_empty_for_missing_or_malformed():
    assert extract_judge_content(None) == ""
    assert extract_judge_content({}) == ""
    assert extract_judge_content({"messages": []}) == ""
    assert extract_judge_content({"messages": ["not-a-dict"]}) == ""
    assert extract_judge_content({"messages": [{"role": "x"}]}) == ""  # no content key


def test_judge_client_is_the_llm_client():
    assert isinstance(get_judge_client(), LLMClient)
