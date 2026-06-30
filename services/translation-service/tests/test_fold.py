"""Unit tests for the F2-app canonical fold pass (no live LLM/glossary)."""
from __future__ import annotations

import pytest

from app.workers.fold import _build_messages, run_fold_pass


def test_build_messages_includes_facts_and_source_language():
    msgs = _build_messages(
        "张若尘",
        [{"attr": "境界", "value": "黄极境"}, {"attr": "宗门", "value": "蛮荒祖地"}],
        "zh",
    )
    assert msgs[0]["role"] == "system"
    assert "zh" in msgs[0]["content"]  # source language pinned (no silent translation)
    assert "do NOT translate" in msgs[0]["content"]
    user = msgs[1]["content"]
    assert "张若尘" in user
    assert "境界: 黄极境" in user
    assert "宗门: 蛮荒祖地" in user


def test_build_messages_skips_empty_values():
    msgs = _build_messages("X", [{"attr": "a", "value": ""}, {"attr": "b", "value": "v"}], "en")
    assert "b: v" in msgs[1]["content"]
    assert "a: " not in msgs[1]["content"]


@pytest.mark.asyncio
async def test_run_fold_pass_no_dirty_is_noop(monkeypatch):
    async def _empty(_book_id, limit=100):
        return []

    monkeypatch.setattr("app.workers.fold.fetch_fold_dirty", _empty)
    out = await run_fold_pass(
        book_id="b", owner_user_id="u", model_source="byok",
        model_ref="m", source_language="zh", llm_client=object(),
    )
    assert out == {"dirty": 0, "folded": 0, "failed": 0}
