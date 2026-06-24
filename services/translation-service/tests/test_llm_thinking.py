"""Unit tests for thinking_llm_fields helper."""
from app.workers.llm_thinking import thinking_llm_fields


def test_thinking_off_disables_reasoning():
    fields = thinking_llm_fields(enabled=False)
    assert fields["reasoning_effort"] == "none"
    assert fields["chat_template_kwargs"]["enable_thinking"] is False
    assert fields["chat_template_kwargs"]["thinking"] is False


def test_thinking_on_enables_reasoning():
    fields = thinking_llm_fields(enabled=True)
    assert fields["reasoning_effort"] == "medium"
    assert fields["chat_template_kwargs"]["enable_thinking"] is True
    assert fields["chat_template_kwargs"]["thinking"] is True
