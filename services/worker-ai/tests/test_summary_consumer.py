"""P3 D-P3-WORKER-AI-CONSUMER-WIRING — tests for the summary consumer
loop + KnowledgeClient.process_summarize_message.

Mocks redis.asyncio + the underlying httpx call so we can drive the
consumer through full dispatch / ACK / retryable-no-ACK paths without
a live Redis or knowledge-service.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.clients import KnowledgeClient, SummarizeMessageResult
from app.summary_consumer import _dispatch_one_message, SummaryConsumer


# ── _dispatch_one_message unit tests ────────────────────────────────


def _fields(**overrides):
    """Bytes-keyed mock Redis fields (matches real XREADGROUP shape)."""
    defaults = {
        "level": "chapter",
        "node_path": "book/part-1/chapter-3",
        "node_id": str(uuid4()),
        "book_id": str(uuid4()),
        "user_id": str(uuid4()),
        "project_id": str(uuid4()),
        "job_id": str(uuid4()),
        "model_ref": "gemma-4-26b",
        "embedding_model_uuid": str(uuid4()),
        "embedding_dimension": "1024",
        "retry_at_epoch": "0.0",
        "retried_n": "0",
    }
    defaults.update(overrides)
    # Mimic redis-py byte-encoded values.
    return {k.encode(): v.encode() if isinstance(v, str) else v
            for k, v in defaults.items()}


@pytest.mark.asyncio
async def test_dispatch_happy_path_returns_ack():
    """200 with no error → consumer XACKs (returns True)."""
    kc = MagicMock(spec=KnowledgeClient)
    kc.process_summarize_message = AsyncMock(return_value=SummarizeMessageResult(
        level="chapter", node_id="n1",
        cache_hit=False, race_winner=True,
        re_enqueued=False, skipped_retry_exhausted=False,
        summary_id="sum-1",
    ))
    should_ack = await _dispatch_one_message(
        knowledge_client=kc,
        fields=_fields(node_id="n1"),
        message_id="1-0",
    )
    assert should_ack is True
    kc.process_summarize_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_forwards_billing_identity_when_present():
    """E0-3 2a-2: a collaborator-enqueued summary message carries billing
    fields on the redis record → the consumer forwards them to the HTTP
    dispatch so knowledge-service bills the caller's key."""
    kc = MagicMock(spec=KnowledgeClient)
    kc.process_summarize_message = AsyncMock(return_value=SummarizeMessageResult(
        level="chapter", node_id="n1", cache_hit=False, race_winner=True,
        re_enqueued=False, skipped_retry_exhausted=False, summary_id="s1",
    ))
    await _dispatch_one_message(
        knowledge_client=kc,
        fields=_fields(
            billing_user_id="collab-B",
            billing_llm_model="collab-llm",
            billing_embedding_model="collab-emb",
        ),
        message_id="1-2",
    )
    kw = kc.process_summarize_message.await_args.kwargs
    assert kw["billing_user_id"] == "collab-B"
    assert kw["billing_llm_model"] == "collab-llm"
    assert kw["billing_embedding_model"] == "collab-emb"


@pytest.mark.asyncio
async def test_dispatch_billing_absent_forwards_empty():
    """Legacy / owner-triggered message (no billing keys) → "" forwarded."""
    kc = MagicMock(spec=KnowledgeClient)
    kc.process_summarize_message = AsyncMock(return_value=SummarizeMessageResult(
        level="chapter", node_id="n1", cache_hit=False, race_winner=True,
        re_enqueued=False, skipped_retry_exhausted=False, summary_id="s1",
    ))
    await _dispatch_one_message(
        knowledge_client=kc, fields=_fields(), message_id="1-3",
    )
    kw = kc.process_summarize_message.await_args.kwargs
    assert kw["billing_user_id"] == ""
    assert kw["billing_embedding_model"] == ""


@pytest.mark.asyncio
async def test_dispatch_retryable_error_returns_noack():
    """Retryable HTTP error → leave un-ACKed for PEL re-delivery."""
    kc = MagicMock(spec=KnowledgeClient)
    kc.process_summarize_message = AsyncMock(return_value=SummarizeMessageResult(
        level="chapter", node_id="n1",
        cache_hit=False, race_winner=False,
        re_enqueued=False, skipped_retry_exhausted=False,
        summary_id=None,
        retryable=True, error="HTTP 503: service unavailable",
    ))
    should_ack = await _dispatch_one_message(
        knowledge_client=kc, fields=_fields(), message_id="1-1",
    )
    assert should_ack is False


@pytest.mark.asyncio
async def test_dispatch_non_retryable_error_acks_poison():
    """Non-retryable error → drop poison off the stream by XACKing."""
    kc = MagicMock(spec=KnowledgeClient)
    kc.process_summarize_message = AsyncMock(return_value=SummarizeMessageResult(
        level="chapter", node_id="n1",
        cache_hit=False, race_winner=False,
        re_enqueued=False, skipped_retry_exhausted=False,
        summary_id=None,
        retryable=False, error="HTTP 422: validation error",
    ))
    should_ack = await _dispatch_one_message(
        knowledge_client=kc, fields=_fields(), message_id="1-2",
    )
    assert should_ack is True


@pytest.mark.asyncio
async def test_dispatch_malformed_message_acks_to_drop():
    """Missing required field → ACK (drop poison) without calling the API."""
    kc = MagicMock(spec=KnowledgeClient)
    kc.process_summarize_message = AsyncMock()
    bad_fields = _fields()
    del bad_fields[b"level"]
    should_ack = await _dispatch_one_message(
        knowledge_client=kc, fields=bad_fields, message_id="1-3",
    )
    assert should_ack is True
    kc.process_summarize_message.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_zero_dimension_rejected_as_malformed():
    """embedding_dimension=0 fails Pydantic on the server side; reject
    client-side too to avoid the round-trip."""
    kc = MagicMock(spec=KnowledgeClient)
    kc.process_summarize_message = AsyncMock()
    bad = _fields(embedding_dimension="0")
    should_ack = await _dispatch_one_message(
        knowledge_client=kc, fields=bad, message_id="1-4",
    )
    assert should_ack is True
    kc.process_summarize_message.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_tolerates_string_typed_fields():
    """Some Redis clients return str instead of bytes; ensure both work."""
    kc = MagicMock(spec=KnowledgeClient)
    kc.process_summarize_message = AsyncMock(return_value=SummarizeMessageResult(
        level="part", node_id="p1",
        cache_hit=True, race_winner=False,
        re_enqueued=False, skipped_retry_exhausted=False,
        summary_id="s1",
    ))
    str_fields = {
        "level": "part",
        "node_path": "book/part-1",
        "node_id": "p1",
        "book_id": str(uuid4()),
        "user_id": str(uuid4()),
        "project_id": str(uuid4()),
        "job_id": str(uuid4()),
        "model_ref": "gemma",
        "embedding_model_uuid": str(uuid4()),
        "embedding_dimension": "1024",
        "retry_at_epoch": "0.0",
        "retried_n": "0",
    }
    should_ack = await _dispatch_one_message(
        knowledge_client=kc, fields=str_fields, message_id="2-0",
    )
    assert should_ack is True
    kwargs = kc.process_summarize_message.call_args.kwargs
    assert kwargs["level"] == "part"
    assert kwargs["embedding_dimension"] == 1024


@pytest.mark.asyncio
async def test_dispatch_propagates_dispatcher_crash_as_noack():
    """Unexpected exceptions are caught above _dispatch_one_message;
    if the client itself raises, the dispatcher returns False so the
    caller leaves the message un-ACKed."""
    kc = MagicMock(spec=KnowledgeClient)
    kc.process_summarize_message = AsyncMock(side_effect=RuntimeError("boom"))
    # The outer consume_summary_stream catches this; for direct
    # _dispatch_one_message call the exception propagates.
    with pytest.raises(RuntimeError, match="boom"):
        await _dispatch_one_message(
            knowledge_client=kc, fields=_fields(), message_id="3-0",
        )


# ── KnowledgeClient.process_summarize_message unit tests ────────────


@pytest.mark.asyncio
async def test_knowledge_client_dispatch_parses_200():
    kc = KnowledgeClient("http://ks", "tok", timeout_s=5.0)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "level": "chapter", "node_id": "n1",
        "cache_hit": False, "race_winner": True,
        "re_enqueued": False, "skipped_retry_exhausted": False,
        "summary_id": "abc-123",
    }
    with patch.object(kc._summarize_http, "post",
                      AsyncMock(return_value=mock_resp)):
        result = await kc.process_summarize_message(
            level="chapter", node_path="book/p/c1", node_id="n1",
            book_id="b1", user_id="u1", project_id="proj1",
            job_id="job1", model_ref="m", embedding_model_uuid="emb1",
            embedding_dimension=1024,
        )
    assert result.race_winner is True
    assert result.summary_id == "abc-123"
    assert result.error is None
    await kc.aclose()


@pytest.mark.asyncio
async def test_knowledge_client_dispatch_503_is_retryable():
    kc = KnowledgeClient("http://ks", "tok", timeout_s=5.0)
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.text = "neo4j unreachable"
    with patch.object(kc._summarize_http, "post",
                      AsyncMock(return_value=mock_resp)):
        result = await kc.process_summarize_message(
            level="chapter", node_path="p", node_id="n",
            book_id="b", user_id="u", project_id="p",
            job_id="j", model_ref="m", embedding_model_uuid="e",
            embedding_dimension=1024,
        )
    assert result.retryable is True
    assert "503" in result.error
    await kc.aclose()


@pytest.mark.asyncio
async def test_knowledge_client_dispatch_422_is_non_retryable():
    kc = KnowledgeClient("http://ks", "tok", timeout_s=5.0)
    mock_resp = MagicMock()
    mock_resp.status_code = 422
    mock_resp.text = "bad payload"
    with patch.object(kc._summarize_http, "post",
                      AsyncMock(return_value=mock_resp)):
        result = await kc.process_summarize_message(
            level="chapter", node_path="p", node_id="n",
            book_id="b", user_id="u", project_id="p",
            job_id="j", model_ref="m", embedding_model_uuid="e",
            embedding_dimension=1024,
        )
    assert result.retryable is False
    assert "422" in result.error
    await kc.aclose()


@pytest.mark.asyncio
async def test_knowledge_client_dispatch_http_error_retryable():
    import httpx
    kc = KnowledgeClient("http://ks", "tok", timeout_s=5.0)
    with patch.object(kc._summarize_http, "post",
                      AsyncMock(side_effect=httpx.ConnectError("refused"))):
        result = await kc.process_summarize_message(
            level="chapter", node_path="p", node_id="n",
            book_id="b", user_id="u", project_id="p",
            job_id="j", model_ref="m", embedding_model_uuid="e",
            embedding_dimension=1024,
        )
    assert result.retryable is True
    assert "HTTP error" in result.error
    await kc.aclose()


@pytest.mark.asyncio
async def test_knowledge_client_separate_summarize_timeout_when_set():
    """summarize_message_timeout_s != None → dedicated httpx client."""
    kc = KnowledgeClient(
        "http://ks", "tok", timeout_s=5.0,
        summarize_message_timeout_s=300.0,
    )
    assert kc._summarize_http is not kc._http
    await kc.aclose()


@pytest.mark.asyncio
async def test_knowledge_client_shares_http_when_no_explicit_summarize_timeout():
    kc = KnowledgeClient("http://ks", "tok", timeout_s=5.0)
    assert kc._summarize_http is kc._http
    await kc.aclose()


# ── SummaryConsumer wiring (transport is SDK-tested centrally) ────────
# The Redis transport (xack-on-success, idle-TimeoutError-continue, BUSYGROUP-safe group,
# bounded-retry/poison, startup PEL drain) is now owned + unit-tested by the shared
# loreweave_jobs.BaseTerminalConsumer. Here we only cover the SummaryConsumer SEAM: that
# handle() wires _dispatch_one_message → ack on should_ack, raise on retryable.


def _summary_consumer(kc):
    return SummaryConsumer("redis://test", kc, consumer_group="g", consumer_name="c")


@pytest.mark.asyncio
async def test_handle_acks_on_success(monkeypatch):
    kc = MagicMock(spec=KnowledgeClient)
    kc.process_summarize_message = AsyncMock(return_value=SummarizeMessageResult(
        level="chapter", node_id="n1", cache_hit=False, race_winner=True,
        re_enqueued=False, skipped_retry_exhausted=False, summary_id="s1",
    ))
    consumer = _summary_consumer(kc)
    r = AsyncMock()
    await consumer._process_msg(r, "1-0", _fields())
    r.xack.assert_awaited_once()  # should_ack=True → base acks


@pytest.mark.asyncio
async def test_handle_retryable_leaves_unacked(monkeypatch):
    kc = MagicMock(spec=KnowledgeClient)
    kc.process_summarize_message = AsyncMock(return_value=SummarizeMessageResult(
        level="chapter", node_id="n1", cache_hit=False, race_winner=False,
        re_enqueued=False, skipped_retry_exhausted=False, summary_id=None,
        retryable=True, error="HTTP 503",
    ))
    consumer = _summary_consumer(kc)
    r = AsyncMock()
    r.incr = AsyncMock(return_value=1)  # below max_retries → redelivered
    await consumer._process_msg(r, "1-0", _fields())
    r.xack.assert_not_called()  # retryable → handle raises → base leaves un-acked


@pytest.mark.asyncio
async def test_handle_malformed_acks_as_poison(monkeypatch):
    kc = MagicMock(spec=KnowledgeClient)
    kc.process_summarize_message = AsyncMock()
    consumer = _summary_consumer(kc)
    r = AsyncMock()
    # missing required fields → _dispatch returns True (drop poison) → ack, no HTTP call
    await consumer._process_msg(r, "1-0", {"event_type": "x"})
    r.xack.assert_awaited_once()
    kc.process_summarize_message.assert_not_awaited()
