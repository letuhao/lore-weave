"""T0.6 + T0.7 (M0): pipeline_version flag routing + V3 skeleton parity.

The V3 orchestrator delegates to V2 in M0, so selecting pipeline_version='v3'
must produce identical behavior while routing through the new package.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx

from tests.test_chapter_worker import _make_pool, _chapter_msg, _patched_book_http


def _block_book_resp():
    body = {
        "original_language": "en",
        "body": {"content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Hello."}]},
        ]},
        "text_content": "Hello.",
    }
    r = MagicMock(spec=httpx.Response)
    r.status_code = 200
    r.is_success = True
    r.raise_for_status = MagicMock()
    r.json.return_value = body
    return r


# ── T0.7: V3 orchestrator delegates to V2 (parity) ────────────────────────────

@pytest.mark.asyncio
async def test_translate_chapter_blocks_v3_delegates_to_v2():
    sentinel = (["RESULT"], 11, 7, 1, 1)
    with patch("app.workers.session_translator.translate_chapter_blocks",
               new_callable=AsyncMock, return_value=sentinel) as v2:
        from app.workers.v3.orchestrator import translate_chapter_blocks_v3
        out = await translate_chapter_blocks_v3(
            [{"type": "paragraph"}], "zh", {"x": 1}, MagicMock(), uuid4(),
            llm_client=MagicMock(), context_window=4096,
        )
    v2.assert_awaited_once()
    assert out == sentinel
    assert v2.call_args.kwargs["context_window"] == 4096  # config forwarded intact


@pytest.mark.asyncio
async def test_translate_chapter_v3_delegates_to_v2():
    sentinel = ("BODY", 5, 9)
    with patch("app.workers.session_translator.translate_chapter",
               new_callable=AsyncMock, return_value=sentinel) as v2:
        from app.workers.v3.orchestrator import translate_chapter_v3
        out = await translate_chapter_v3(
            "source text", "zh", {"x": 1}, MagicMock(), uuid4(),
            llm_client=MagicMock(), context_window=4096,
        )
    v2.assert_awaited_once()
    assert out == sentinel


# ── T0.6: chapter_worker routes by pipeline_version ───────────────────────────

@pytest.mark.asyncio
async def test_pipeline_version_v3_routes_to_v3_orchestrator():
    pool, _ = _make_pool()
    msg = _chapter_msg(pipeline_version="v3")
    translated_blocks = [
        {"type": "paragraph", "content": [{"type": "text", "text": "こんにちは。"}]},
    ]

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls, \
         patch("app.workers.chapter_worker._get_model_context_window",
               new_callable=AsyncMock, return_value=8192), \
         patch("app.workers.v3.orchestrator.translate_chapter_blocks_v3",
               new_callable=AsyncMock,
               return_value=(translated_blocks, 10, 8, 1, 1)) as v3fn, \
         patch("app.workers.session_translator.translate_chapter_blocks",
               new_callable=AsyncMock) as v2fn:
        mock_cls.return_value.__aenter__ = AsyncMock(
            return_value=_patched_book_http(book_resp=_block_book_resp()))
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.workers.chapter_worker import handle_chapter_message
        await handle_chapter_message(msg, pool, AsyncMock(), MagicMock(), retry_count=0)

    v3fn.assert_awaited_once()
    v2fn.assert_not_awaited()


@pytest.mark.asyncio
async def test_default_pipeline_version_routes_to_v2():
    pool, _ = _make_pool()
    msg = _chapter_msg()  # no pipeline_version → default 'v2'
    translated_blocks = [
        {"type": "paragraph", "content": [{"type": "text", "text": "こんにちは。"}]},
    ]

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls, \
         patch("app.workers.chapter_worker._get_model_context_window",
               new_callable=AsyncMock, return_value=8192), \
         patch("app.workers.v3.orchestrator.translate_chapter_blocks_v3",
               new_callable=AsyncMock) as v3fn, \
         patch("app.workers.session_translator.translate_chapter_blocks",
               new_callable=AsyncMock,
               return_value=(translated_blocks, 10, 8, 1, 1)) as v2fn:
        mock_cls.return_value.__aenter__ = AsyncMock(
            return_value=_patched_book_http(book_resp=_block_book_resp()))
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.workers.chapter_worker import handle_chapter_message
        await handle_chapter_message(msg, pool, AsyncMock(), MagicMock(), retry_count=0)

    v2fn.assert_awaited_once()
    v3fn.assert_not_awaited()


# ── M1a: rule-tier verification persists issues ───────────────────────────────

@pytest.mark.asyncio
async def test_v3_orchestrator_persists_rule_issues():
    """M1a: after delegating to V2, the v3 orchestrator runs the deterministic
    rule-tier and persists Issues + the chapter rollup. A seeded CJK-leak draft
    must produce an INSERT into translation_quality_issues + a rollup UPDATE."""
    from app.workers.v3 import orchestrator

    blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "魔王來了。"}]}]
    # Seeded error: residual CJK in a vi target.
    result_blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "魔王 đã đến."}]}]

    pool, db = _make_pool()
    msg = _chapter_msg()  # target_language='vi', has book_id

    with patch("app.workers.session_translator.translate_chapter_blocks",
               new_callable=AsyncMock, return_value=(result_blocks, 10, 8, 1, 1)), \
         patch("app.workers.glossary_client.fetch_translation_glossary",
               new_callable=AsyncMock, return_value=[]):
        await orchestrator.translate_chapter_blocks_v3(
            blocks, "zh", msg, pool, uuid4(), llm_client=MagicMock(), context_window=8192,
        )

    sql = " ".join(c.args[0] for c in db.execute.call_args_list)
    assert "translation_quality_issues" in sql   # issues inserted
    assert "quality_score" in sql                # chapter rollup updated


@pytest.mark.asyncio
async def test_v3_rule_issues_attributed_to_correct_block():
    """review-impl LOW-2/3: with multiple blocks, an issue must be attributed to
    the RIGHT block_index (proves the source↔draft zip alignment, not just that
    *some* row was written)."""
    from app.workers.v3 import orchestrator

    blocks = [
        {"type": "paragraph", "content": [{"type": "text", "text": "你好。"}]},      # 0 clean
        {"type": "paragraph", "content": [{"type": "text", "text": "魔王來了。"}]},   # 1 source
    ]
    result_blocks = [
        {"type": "paragraph", "content": [{"type": "text", "text": "Xin chào."}]},   # 0 clean draft
        {"type": "paragraph", "content": [{"type": "text", "text": "魔王 đã đến."}]}, # 1 CJK leak
    ]
    pool, db = _make_pool()
    msg = _chapter_msg()

    with patch("app.workers.session_translator.translate_chapter_blocks",
               new_callable=AsyncMock, return_value=(result_blocks, 10, 8, 2, 2)), \
         patch("app.workers.glossary_client.fetch_translation_glossary",
               new_callable=AsyncMock, return_value=[]):
        await orchestrator.translate_chapter_blocks_v3(
            blocks, "zh", msg, pool, uuid4(), llm_client=MagicMock(), context_window=8192,
        )

    inserts = [
        c for c in db.execute.call_args_list
        if "INSERT INTO translation_quality_issues" in c.args[0]
    ]
    assert len(inserts) == 1                 # only the leaked block
    assert inserts[0].args[2] == 1           # block_index = the leaked block, not the clean one
