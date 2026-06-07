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
    sentinel = (["RESULT"], 11, 7, 1, 1, {})
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
               return_value=(translated_blocks, 10, 8, 1, 1, {})) as v3fn, \
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
               return_value=(translated_blocks, 10, 8, 1, 1, {})) as v2fn:
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
    # INSERT binds: ($1 ct, $2 block_index, $3 round, ...). Filter to round 0 — M1b
    # may add a round-1 row for the same block when correction can't fix it.
    round0 = [c for c in inserts if c.args[3] == 0]
    assert len(round0) == 1                   # only the leaked block, in round 0
    assert round0[0].args[2] == 1             # block_index = the leaked block, not the clean one


@pytest.mark.asyncio
async def test_v3_corrector_retranslates_and_splices_high_severity():
    """M1b: a high-severity rule issue triggers ONE targeted re-translate; the
    corrected text is spliced into the returned blocks and the rollup records the
    correction round."""
    from app.workers.v3 import orchestrator
    from app.workers.block_classifier import extract_translatable_text
    from tests.test_session_translator import FakeLLMClient

    blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "提拉米来了。"}]}]
    # Seeded error: wrong target name (glossary wants 'Tirami').
    result_blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "Tirana đã đến."}]}]
    glossary = [{"zh": ["提拉米"], "vi": ["Tirami"], "kind": "character"}]

    pool, db = _make_pool()
    msg = _chapter_msg(qa_depth="rule_only")  # isolate the rule-triggered corrector
    fake = FakeLLMClient()
    fake.queue_translation(content="Tirami đã đến.")  # the corrected re-translation

    with patch("app.workers.session_translator.translate_chapter_blocks",
               new_callable=AsyncMock, return_value=(result_blocks, 10, 8, 1, 1)), \
         patch("app.workers.glossary_client.fetch_translation_glossary",
               new_callable=AsyncMock, return_value=glossary):
        result = await orchestrator.translate_chapter_blocks_v3(
            blocks, "zh", msg, pool, uuid4(), llm_client=fake, context_window=8192,
        )

    assert len(fake.calls) == 1                                  # corrector ran exactly once
    assert "Tirami" in extract_translatable_text(result[0][0])   # corrected block spliced back
    sql = " ".join(c.args[0] for c in db.execute.call_args_list)
    assert "qa_rounds_used" in sql                              # rollup written


@pytest.mark.asyncio
async def test_v3_verifier_trusts_only_canon_glossary():
    """D-TRANSL-M1D wiring lock: a glossary term with confidence='machine' is
    demoted by the trust ladder, so the V3 verifier must NOT hard-fail on it and
    the corrector must NOT run — even though the draft mistranslates the name.

    Contrast with test_v3_corrector_retranslates_and_splices_high_severity, which
    uses the SAME draft+name but NO confidence key (legacy → trusted → corrected).
    That pair proves the suppression is caused by the confidence demotion, and
    guards orchestrator.py:175 (cmap=gctx.verified_map) against a silent revert to
    correction_map."""
    from app.workers.v3 import orchestrator
    from app.workers.block_classifier import extract_translatable_text
    from tests.test_session_translator import FakeLLMClient

    blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "提拉米来了。"}]}]
    result_blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "Tirana đã đến."}]}]
    # Same name, but machine-confidence → soft hint, not a hard rule.
    glossary = [{"zh": ["提拉米"], "vi": ["Tirami"], "kind": "character", "confidence": "machine"}]

    pool, db = _make_pool()
    msg = _chapter_msg(qa_depth="rule_only")  # isolate the rule-tier (no LLM verifier)
    fake = FakeLLMClient()  # nothing queued — the corrector must never be invoked

    with patch("app.workers.session_translator.translate_chapter_blocks",
               new_callable=AsyncMock, return_value=(result_blocks, 10, 8, 1, 1)), \
         patch("app.workers.glossary_client.fetch_translation_glossary",
               new_callable=AsyncMock, return_value=glossary):
        result = await orchestrator.translate_chapter_blocks_v3(
            blocks, "zh", msg, pool, uuid4(), llm_client=fake, context_window=8192,
        )

    assert len(fake.calls) == 0                                   # corrector never ran
    assert "Tirana đã đến." in extract_translatable_text(result[0][0])  # draft untouched
    # No HIGH wrong_name issue should have been persisted for the demoted term.
    wrong_name_high = [
        c for c in db.execute.call_args_list
        if "INSERT INTO translation_quality_issues" in c.args[0]
        and "wrong_name" in c.args and "high" in c.args
    ]
    assert wrong_name_high == []


@pytest.mark.asyncio
async def test_v3_corrector_rejected_when_not_improved():
    """review-impl MED-1 (keep-if-improved): a correction that does NOT reduce the
    block's high-severity count is rejected — the original draft is kept, never a
    worse one."""
    from app.workers.v3 import orchestrator
    from app.workers.block_classifier import extract_translatable_text
    from tests.test_session_translator import FakeLLMClient

    blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "提拉米来了。"}]}]
    result_blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "Tirana đã đến."}]}]
    glossary = [{"zh": ["提拉米"], "vi": ["Tirami"], "kind": "character"}]

    pool, _ = _make_pool()
    msg = _chapter_msg(qa_depth="rule_only")  # isolate the rule-triggered corrector
    fake = FakeLLMClient()
    fake.queue_translation(content="Tirana vẫn đến.")  # STILL wrong (no 'Tirami') → not improved

    with patch("app.workers.session_translator.translate_chapter_blocks",
               new_callable=AsyncMock, return_value=(result_blocks, 10, 8, 1, 1)), \
         patch("app.workers.glossary_client.fetch_translation_glossary",
               new_callable=AsyncMock, return_value=glossary):
        result = await orchestrator.translate_chapter_blocks_v3(
            blocks, "zh", msg, pool, uuid4(), llm_client=fake, context_window=8192,
        )

    text = extract_translatable_text(result[0][0])
    assert "Tirana đã đến." in text   # original draft kept
    assert "vẫn" not in text          # the not-improved correction was rejected


@pytest.mark.asyncio
async def test_v3_zh_vi_injects_romanization_into_translation():
    """M1c: the v3 path passes the Hán-Việt romanization instruction to the V2
    translator for zh→vi (the unit tests cover other pairs returning '')."""
    from app.workers.v3 import orchestrator

    blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "你好。"}]}]
    pool, _ = _make_pool()
    msg = _chapter_msg()  # target_language='vi'

    with patch("app.workers.session_translator.translate_chapter_blocks",
               new_callable=AsyncMock, return_value=(blocks, 0, 0, 0, 0)) as v2, \
         patch("app.workers.glossary_client.fetch_translation_glossary",
               new_callable=AsyncMock, return_value=[]):
        await orchestrator.translate_chapter_blocks_v3(
            blocks, "zh", msg, pool, uuid4(), llm_client=MagicMock(), context_window=8192,
        )

    assert "Hán-Việt" in v2.call_args.kwargs["extra_system"]


@pytest.mark.asyncio
async def test_v3_injects_timeline_memo_into_translation(monkeypatch):
    """M4d-1: the cross-chapter "story so far" timeline memo is injected into the
    Translator extra_system (continuity context, Translator-side only)."""
    from app.workers.v3 import orchestrator
    from app.workers.knowledge_client import TimelineBrief, TimelineEvent

    async def fake_timeline(book_id, chapter_index, limit=25):
        return TimelineBrief(found=True, events=[
            TimelineEvent("The siege of Eld", "The northern army fell.", "Y2", ["Tirami"]),
        ])
    monkeypatch.setattr("app.workers.v3.knowledge_context.fetch_timeline", fake_timeline)

    blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "你好。"}]}]
    pool, _ = _make_pool()
    msg = _chapter_msg()  # target_language='vi'
    # M4d-1: the timeline keys on the book-service global sort_order, NOT the
    # job-local chapter_index. The worker threads it onto the msg.
    msg["chapter_sort_order"] = 12

    with patch("app.workers.session_translator.translate_chapter_blocks",
               new_callable=AsyncMock, return_value=(blocks, 0, 0, 0, 0)) as v2, \
         patch("app.workers.glossary_client.fetch_translation_glossary",
               new_callable=AsyncMock, return_value=[]):
        await orchestrator.translate_chapter_blocks_v3(
            blocks, "zh", msg, pool, uuid4(), llm_client=MagicMock(), context_window=8192,
        )

    extra = v2.call_args.kwargs["extra_system"]
    assert "RECENT STORY EVENTS" in extra
    assert "The siege of Eld" in extra


@pytest.mark.asyncio
async def test_v3_skips_timeline_when_no_sort_order(monkeypatch):
    """M4d-1 review-impl MED-1: without a book-service sort_order on the msg, the
    timeline is SKIPPED (not windowed on the wrong job-local axis)."""
    from app.workers.v3 import orchestrator

    called = {"n": 0}

    async def fake_timeline(book_id, chapter_order, limit=25):
        called["n"] += 1
        from app.workers.knowledge_client import TimelineBrief, TimelineEvent
        return TimelineBrief(found=True, events=[TimelineEvent("X", None, None, [])])
    monkeypatch.setattr("app.workers.v3.knowledge_context.fetch_timeline", fake_timeline)

    blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "你好。"}]}]
    pool, _ = _make_pool()
    msg = _chapter_msg()  # NO chapter_sort_order

    with patch("app.workers.session_translator.translate_chapter_blocks",
               new_callable=AsyncMock, return_value=(blocks, 0, 0, 0, 0)) as v2, \
         patch("app.workers.glossary_client.fetch_translation_glossary",
               new_callable=AsyncMock, return_value=[]):
        await orchestrator.translate_chapter_blocks_v3(
            blocks, "zh", msg, pool, uuid4(), llm_client=MagicMock(), context_window=8192,
        )

    assert called["n"] == 0  # never fetched — no wrong-axis window
    assert "RECENT STORY EVENTS" not in v2.call_args.kwargs["extra_system"]


# ── M2: LLM verifier (standard) + multi-round loop (thorough) ─────────────────

@pytest.mark.asyncio
async def test_v3_standard_persists_llm_advisory_capped():
    """M2: in 'standard', the LLM verifier's issues are persisted (detected_by='llm')
    and CAPPED at 'med' — an LLM-only flag does NOT trigger re-translate."""
    from app.workers.v3 import orchestrator
    from tests.test_session_translator import FakeLLMClient

    blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "提拉米来了。"}]}]
    # Clean draft (correct name, no leak) → the rule-tier finds nothing.
    result_blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "Tirami đã đến."}]}]
    glossary = [{"zh": ["提拉米"], "vi": ["Tirami"], "kind": "character"}]
    pool, db = _make_pool()
    msg = _chapter_msg(qa_depth="standard")
    fake = FakeLLMClient()
    # The LLM verifier flags a 'high' omission → must be capped to 'med' (advisory).
    fake.queue_translation(content='[{"block":0,"type":"omission","severity":"high","detail":"dropped"}]')

    with patch("app.workers.session_translator.translate_chapter_blocks",
               new_callable=AsyncMock, return_value=(result_blocks, 10, 8, 1, 1)), \
         patch("app.workers.glossary_client.fetch_translation_glossary",
               new_callable=AsyncMock, return_value=glossary):
        await orchestrator.translate_chapter_blocks_v3(
            blocks, "zh", msg, pool, uuid4(), llm_client=fake, context_window=8192)

    assert len(fake.calls) == 1   # only the verifier ran; no corrector (advisory flag)
    inserts = [c for c in db.execute.call_args_list
               if "INSERT INTO translation_quality_issues" in c.args[0]]
    llm_inserts = [c for c in inserts if c.args[8] == "llm"]   # detected_by ($8 → args[8])
    assert llm_inserts
    assert llm_inserts[0].args[5] == "med"   # severity ($5) capped from 'high'
    # review-impl MED-2: a clean-slate delete (no round filter) ran first.
    assert any(
        "DELETE FROM translation_quality_issues" in c.args[0] and "round" not in c.args[0]
        for c in db.execute.call_args_list
    )


@pytest.mark.asyncio
async def test_v3_thorough_loops_to_max_rounds():
    """M2: 'thorough' loops verify→correct up to max_qa_rounds when a rule-high
    persists (the correction never improves here)."""
    from app.workers.v3 import orchestrator
    from tests.test_session_translator import FakeLLMClient

    blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "魔王來了。"}]}]
    result_blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "魔王 đã đến."}]}]  # CJK leak (rule-high)
    pool, db = _make_pool()
    msg = _chapter_msg(qa_depth="thorough", max_qa_rounds=2)
    fake = FakeLLMClient()
    # Per round: verify(LLM)='[]' then correct=still-leaky. Order: v0,c1,v1,c2,v2.
    for content in ("[]", "魔王 vẫn đến.", "[]", "魔王 vẫn đến.", "[]"):
        fake.queue_translation(content=content)

    with patch("app.workers.session_translator.translate_chapter_blocks",
               new_callable=AsyncMock, return_value=(result_blocks, 10, 8, 1, 1)), \
         patch("app.workers.glossary_client.fetch_translation_glossary",
               new_callable=AsyncMock, return_value=[]):
        await orchestrator.translate_chapter_blocks_v3(
            blocks, "zh", msg, pool, uuid4(), llm_client=fake, context_window=8192)

    rollup = [c for c in db.execute.call_args_list if "qa_rounds_used" in c.args[0]]
    assert rollup
    assert rollup[-1].args[3] == 2   # qa_rounds_used ($3 → args[3]) — looped to max


@pytest.mark.asyncio
async def test_v3_thorough_caps_rounds_at_ceiling():
    """review-impl MED-1: max_qa_rounds is capped at the hard ceiling (5) regardless
    of a large configured value."""
    from app.workers.v3 import orchestrator
    from tests.test_session_translator import FakeLLMClient

    blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "魔王來了。"}]}]
    result_blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "魔王 đã đến."}]}]
    pool, db = _make_pool()
    msg = _chapter_msg(qa_depth="thorough", max_qa_rounds=99)
    fake = FakeLLMClient()
    for content in (["[]"] + ["魔王 vẫn đến.", "[]"] * 10):  # plenty (> ceiling worth)
        fake.queue_translation(content=content)

    with patch("app.workers.session_translator.translate_chapter_blocks",
               new_callable=AsyncMock, return_value=(result_blocks, 10, 8, 1, 1)), \
         patch("app.workers.glossary_client.fetch_translation_glossary",
               new_callable=AsyncMock, return_value=[]):
        await orchestrator.translate_chapter_blocks_v3(
            blocks, "zh", msg, pool, uuid4(), llm_client=fake, context_window=8192)

    rollup = [c for c in db.execute.call_args_list if "qa_rounds_used" in c.args[0]]
    assert rollup[-1].args[3] == 5   # capped at _MAX_QA_ROUNDS, not 99
