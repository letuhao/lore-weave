"""
Unit tests for session_translator — Plan §9 (Verification).

Covers:
- Single-chunk chapter: one invoke call, body returned as-is
- Multi-chunk chapter: chunks concatenated with double-newline
- Compaction trigger: fires when history tokens exceed context_window // 2
- Compact model fallback: uses translation model when compact_model_ref is None
- Compact failure is non-fatal: translation completes even when compact call fails
- Chunk rows written to DB for each chunk
- Token counts aggregated across all chunks
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4, UUID

from app.workers.chunk_splitter import split_chapter, TOKEN_CHAR_RATIO, _LATIN_CHARS_PER_TOKEN


# ── Helpers ────────────────────────────────────────────────────────────────────

_DEFAULT_COMPACT_SYSTEM_EXCERPT = "Translation Memo"   # from _DEFAULT_COMPACT_SYSTEM


def _invoke_response(text: str, in_tok: int = 10, out_tok: int = 8) -> bytes:
    """Serialise a provider-registry invoke response (OpenAI format)."""
    return json.dumps({
        "output": {"choices": [{"message": {"content": text}}]},
        "usage":  {"input_tokens": in_tok, "output_tokens": out_tok},
    }).encode()


class _StreamCM:
    """Fake async context manager returned by client.stream(...)."""
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *_):
        pass


def _make_stream_resp(text: str, status: int = 200, in_tok: int = 10, out_tok: int = 8) -> MagicMock:
    """Build a fake httpx Response for streaming."""
    async def _aiter():
        yield json.dumps({
            "output": {"choices": [{"message": {"content": text}}]},
            "usage":  {"input_tokens": in_tok, "output_tokens": out_tok},
        }).encode()

    r = MagicMock()
    r.status_code = status
    r.raise_for_status = MagicMock()
    r.aiter_bytes = MagicMock(return_value=_aiter())
    return r


def _make_pool(chunk_row_id: UUID | None = None) -> MagicMock:
    """Fake asyncpg pool — supports fetchrow (INSERT chunk row) and execute (UPDATE)."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={"id": chunk_row_id or uuid4()})
    pool.execute  = AsyncMock()
    return pool


def _make_msg(**overrides) -> dict:
    base = {
        "job_id":              str(uuid4()),
        "user_id":             "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "book_id":             str(uuid4()),
        "model_source":        "platform_model",
        "model_ref":           str(uuid4()),
        "system_prompt":       "Translate faithfully.",
        "user_prompt_tpl":     (
            "Translate {source_language} to {target_language}:\n{chapter_text}"
        ),
        "target_language":     "vi",
        "chunk_size_tokens":   50,
        "invoke_timeout_secs": 30,
        "compact_model_source": None,
        "compact_model_ref":   None,
    }
    return {**base, **overrides}


def _is_compact_call(payload: dict) -> bool:
    """Return True if a stream() call payload is a compact (not translation) request."""
    messages = payload.get("input", {}).get("messages", [])
    return any(
        _DEFAULT_COMPACT_SYSTEM_EXCERPT in m.get("content", "")
        for m in messages
        if m.get("role") == "system"
    )


def _build_mock_http_client(stream_side_effect):
    """
    Build a mock httpx.AsyncClient that delegates client.stream() calls
    to stream_side_effect(method, url, **kwargs).
    """
    mock_client = MagicMock()
    mock_client.stream = MagicMock(side_effect=stream_side_effect)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    return mock_client


# ── Single-chunk chapter ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_single_chunk_returns_translated_body():
    """Short chapter fits in one chunk → exactly one invoke call, body returned."""
    pool = _make_pool()
    msg  = _make_msg(chunk_size_tokens=1000)   # huge chunk — whole chapter fits
    chapter_text = "Hello world. This is a short chapter."

    stream_calls = []

    def side_effect(method, url, **kwargs):
        stream_calls.append(kwargs.get("json", {}))
        return _StreamCM(_make_stream_resp("Xin chào thế giới."))

    mock_client = _build_mock_http_client(side_effect)

    with patch("app.workers.session_translator.httpx.AsyncClient", return_value=mock_client), \
         patch("app.workers.session_translator.mint_user_jwt", return_value="jwt"):
        from app.workers.session_translator import translate_chapter
        body, in_tok, out_tok = await translate_chapter(
            chapter_text=chapter_text,
            source_lang="en",
            msg=msg,
            pool=pool,
            chapter_translation_id=uuid4(),
            context_window=8192,
        )

    assert body == "Xin chào thế giới."
    assert len(stream_calls) == 1   # exactly one invoke — no compaction


@pytest.mark.asyncio
async def test_single_chunk_aggregates_token_counts():
    """Token counts from the invoke response are returned."""
    pool = _make_pool()
    msg  = _make_msg(chunk_size_tokens=1000)

    async def _aiter():
        yield json.dumps({
            "output": {"choices": [{"message": {"content": "Translated."}}]},
            "usage":  {"input_tokens": 42, "output_tokens": 17},
        }).encode()

    stream_resp = MagicMock()
    stream_resp.status_code = 200
    stream_resp.raise_for_status = MagicMock()
    stream_resp.aiter_bytes = MagicMock(return_value=_aiter())

    def side_effect(method, url, **kwargs):
        return _StreamCM(stream_resp)

    mock_client = _build_mock_http_client(side_effect)

    with patch("app.workers.session_translator.httpx.AsyncClient", return_value=mock_client), \
         patch("app.workers.session_translator.mint_user_jwt", return_value="jwt"):
        from app.workers.session_translator import translate_chapter
        _, in_tok, out_tok = await translate_chapter(
            chapter_text="Short.",
            source_lang="en",
            msg=msg,
            pool=pool,
            chapter_translation_id=uuid4(),
            context_window=8192,
        )

    assert in_tok  == 42
    assert out_tok == 17


# ── Multi-chunk chapter ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_multi_chunk_concatenated_with_double_newline():
    """
    A chapter split into N chunks must be returned as
    chunk_0 + '\\n\\n' + chunk_1 + ... (joined by double newline).

    Uses chunk_tokens=200 (above the 100-token internal floor) so that
    split_chapter() and translate_chapter() agree on the chunk count.
    """
    chunk_tokens  = 200                             # 700 chars per chunk (above 100-token floor)
    chunk_chars   = int(chunk_tokens * _LATIN_CHARS_PER_TOKEN)
    # 3 paragraphs, each clearly larger than one chunk
    chapter_text  = "\n\n".join(["Paragraph " + str(i) + ". " + "X" * (chunk_chars + 50)
                                  for i in range(3)])

    pool = _make_pool()
    msg  = _make_msg(chunk_size_tokens=chunk_tokens)
    chunk_count   = len(split_chapter(chapter_text, chunk_tokens))
    assert chunk_count >= 2, "Test setup: chapter must produce multiple chunks"

    call_idx = 0

    def side_effect(method, url, **kwargs):
        nonlocal call_idx
        text = f"TRANSLATED_{call_idx}"
        call_idx += 1
        return _StreamCM(_make_stream_resp(text))

    mock_client = _build_mock_http_client(side_effect)

    with patch("app.workers.session_translator.httpx.AsyncClient", return_value=mock_client), \
         patch("app.workers.session_translator.mint_user_jwt", return_value="jwt"):
        from app.workers.session_translator import translate_chapter
        body, _, _ = await translate_chapter(
            chapter_text=chapter_text,
            source_lang="en",
            msg=msg,
            pool=pool,
            chapter_translation_id=uuid4(),
            context_window=8192,
        )

    parts = body.split("\n\n")
    assert len(parts) == chunk_count
    assert all(p.startswith("TRANSLATED_") for p in parts)


@pytest.mark.asyncio
async def test_multi_chunk_token_counts_summed():
    """Input/output tokens must be summed across all chunks."""
    # Use chunk_tokens=200 (above 100-token floor) so translate_chapter uses the same size
    chunk_tokens = 200
    chapter_text = "Word. " * 300   # ~1800 chars → ~3 chunks at 200 tokens each

    pool = _make_pool()
    msg  = _make_msg(chunk_size_tokens=chunk_tokens)
    # Compute expected chunks using the SAME size translate_chapter will use
    effective_chunk = max(min(chunk_tokens, 8192 // 4), 100)
    num_chunks = len(split_chapter(chapter_text, effective_chunk))
    assert num_chunks >= 2

    def side_effect(method, url, **kwargs):
        payload = kwargs.get("json", {})
        if _is_compact_call(payload):
            return _StreamCM(_make_stream_resp("[memo]", in_tok=1, out_tok=1))
        return _StreamCM(_make_stream_resp("Translated.", in_tok=5, out_tok=3))

    mock_client = _build_mock_http_client(side_effect)

    with patch("app.workers.session_translator.httpx.AsyncClient", return_value=mock_client), \
         patch("app.workers.session_translator.mint_user_jwt", return_value="jwt"):
        from app.workers.session_translator import translate_chapter
        _, in_tok, out_tok = await translate_chapter(
            chapter_text=chapter_text,
            source_lang="en",
            msg=msg,
            pool=pool,
            chapter_translation_id=uuid4(),
            context_window=8192,
        )

    # Compact calls contribute 1 each; translation calls contribute 5/3 each
    assert in_tok  >= num_chunks * 5
    assert out_tok >= num_chunks * 3


# ── Compaction ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compaction_fires_when_history_exceeds_half_context():
    """
    Plan §9: Compact must be called when history tokens > context_window // 2.

    Strategy: patch estimate_tokens to always return 60. With context_window=200
    (threshold=100), after the first chunk the history = 2 messages × 60 = 120 > 100,
    so compact fires after chunk 0.
    """
    # Chapter that splits into exactly 2 chunks at chunk_size=50 tokens
    chunk_tokens = 50
    chunk_chars  = int(chunk_tokens * _LATIN_CHARS_PER_TOKEN)         # 175 chars
    chapter_text = "A" * (chunk_chars + 10) + "\n\n" + "B" * (chunk_chars + 10)

    pool        = _make_pool()
    msg         = _make_msg(chunk_size_tokens=chunk_tokens)
    stream_calls: list[dict] = []

    def side_effect(method, url, **kwargs):
        payload = kwargs.get("json", {})
        stream_calls.append(payload)
        is_compact = _is_compact_call(payload)
        text = "[MEMO: key names]" if is_compact else "Translated chunk."
        return _StreamCM(_make_stream_resp(text))

    mock_client = _build_mock_http_client(side_effect)

    with patch("app.workers.session_translator.httpx.AsyncClient", return_value=mock_client), \
         patch("app.workers.session_translator.mint_user_jwt", return_value="jwt"), \
         patch("app.workers.session_translator.estimate_tokens", return_value=60):
        from app.workers.session_translator import translate_chapter
        body, _, _ = await translate_chapter(
            chapter_text=chapter_text,
            source_lang="en",
            msg=msg,
            pool=pool,
            chapter_translation_id=uuid4(),
            context_window=200,   # threshold = 100; history 120 > 100 → compact
        )

    num_chunks = len(split_chapter(chapter_text, chunk_tokens))
    compact_calls = [c for c in stream_calls if _is_compact_call(c)]

    assert len(compact_calls) >= 1, (
        f"Expected at least 1 compact call, got {len(compact_calls)}. "
        f"Total stream calls: {len(stream_calls)}"
    )


@pytest.mark.asyncio
async def test_no_compaction_when_history_below_threshold():
    """With a large context_window, history never triggers compaction."""
    chapter_text = "Sentence one. Sentence two. Sentence three." * 5
    chunk_tokens = 10   # many small chunks

    pool = _make_pool()
    msg  = _make_msg(chunk_size_tokens=chunk_tokens)
    stream_calls: list[dict] = []

    def side_effect(method, url, **kwargs):
        stream_calls.append(kwargs.get("json", {}))
        return _StreamCM(_make_stream_resp("Translated."))

    mock_client = _build_mock_http_client(side_effect)

    with patch("app.workers.session_translator.httpx.AsyncClient", return_value=mock_client), \
         patch("app.workers.session_translator.mint_user_jwt", return_value="jwt"):
        from app.workers.session_translator import translate_chapter
        await translate_chapter(
            chapter_text=chapter_text,
            source_lang="en",
            msg=msg,
            pool=pool,
            chapter_translation_id=uuid4(),
            context_window=1_000_000,   # huge — compact never fires
        )

    compact_calls = [c for c in stream_calls if _is_compact_call(c)]
    assert compact_calls == [], "Compaction must NOT fire when context window is huge"


# ── Compact model fallback ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compact_uses_translation_model_when_compact_ref_is_none():
    """
    Plan §9: When compact_model_ref is None, the compact call must use
    the same model_source / model_ref as the translation.
    """
    translation_model_ref = str(uuid4())
    msg = _make_msg(
        model_source="platform_model",
        model_ref=translation_model_ref,
        compact_model_source=None,
        compact_model_ref=None,
        chunk_size_tokens=50,
    )
    chunk_tokens = 50
    chunk_chars  = int(chunk_tokens * _LATIN_CHARS_PER_TOKEN)
    chapter_text = "A" * (chunk_chars + 5) + "\n\n" + "B" * (chunk_chars + 5)

    pool = _make_pool()
    compact_payload_seen: list[dict] = []

    def side_effect(method, url, **kwargs):
        payload = kwargs.get("json", {})
        if _is_compact_call(payload):
            compact_payload_seen.append(payload)
        return _StreamCM(_make_stream_resp("[memo]" if _is_compact_call(payload) else "Translated."))

    mock_client = _build_mock_http_client(side_effect)

    with patch("app.workers.session_translator.httpx.AsyncClient", return_value=mock_client), \
         patch("app.workers.session_translator.mint_user_jwt", return_value="jwt"), \
         patch("app.workers.session_translator.estimate_tokens", return_value=60):
        from app.workers.session_translator import translate_chapter
        await translate_chapter(
            chapter_text=chapter_text,
            source_lang="en",
            msg=msg,
            pool=pool,
            chapter_translation_id=uuid4(),
            context_window=200,
        )

    assert compact_payload_seen, "Expected at least one compact call to occur"
    for cp in compact_payload_seen:
        assert cp["model_source"] == "platform_model"
        assert cp["model_ref"]    == translation_model_ref


@pytest.mark.asyncio
async def test_compact_uses_dedicated_compact_model_when_configured():
    """When compact_model_source/ref are set, the compact call must use them."""
    compact_model_ref = str(uuid4())
    msg = _make_msg(
        model_source="platform_model",
        model_ref=str(uuid4()),
        compact_model_source="user_model",
        compact_model_ref=compact_model_ref,
        chunk_size_tokens=50,
    )
    chunk_tokens = 50
    chunk_chars  = int(chunk_tokens * _LATIN_CHARS_PER_TOKEN)
    chapter_text = "A" * (chunk_chars + 5) + "\n\n" + "B" * (chunk_chars + 5)

    pool = _make_pool()
    compact_payload_seen: list[dict] = []

    def side_effect(method, url, **kwargs):
        payload = kwargs.get("json", {})
        if _is_compact_call(payload):
            compact_payload_seen.append(payload)
        return _StreamCM(_make_stream_resp("[memo]" if _is_compact_call(payload) else "Translated."))

    mock_client = _build_mock_http_client(side_effect)

    with patch("app.workers.session_translator.httpx.AsyncClient", return_value=mock_client), \
         patch("app.workers.session_translator.mint_user_jwt", return_value="jwt"), \
         patch("app.workers.session_translator.estimate_tokens", return_value=60):
        from app.workers.session_translator import translate_chapter
        await translate_chapter(
            chapter_text=chapter_text,
            source_lang="en",
            msg=msg,
            pool=pool,
            chapter_translation_id=uuid4(),
            context_window=200,
        )

    assert compact_payload_seen, "Expected at least one compact call to occur"
    for cp in compact_payload_seen:
        assert cp["model_source"] == "user_model"
        assert cp["model_ref"]    == compact_model_ref


# ── Compact failure is non-fatal ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compact_failure_does_not_abort_translation():
    """
    Plan §9: If the compact model call raises an exception (or returns 4xx/5xx),
    translation must continue to completion — compaction is best-effort.
    """
    chunk_tokens = 50
    chunk_chars  = int(chunk_tokens * _LATIN_CHARS_PER_TOKEN)
    chapter_text = "A" * (chunk_chars + 5) + "\n\n" + "B" * (chunk_chars + 5)

    pool = _make_pool()
    msg  = _make_msg(chunk_size_tokens=chunk_tokens)

    def side_effect(method, url, **kwargs):
        payload = kwargs.get("json", {})
        if _is_compact_call(payload):
            # Compact call fails hard
            raise Exception("compact model unreachable")
        return _StreamCM(_make_stream_resp("Translated."))

    mock_client = _build_mock_http_client(side_effect)

    with patch("app.workers.session_translator.httpx.AsyncClient", return_value=mock_client), \
         patch("app.workers.session_translator.mint_user_jwt", return_value="jwt"), \
         patch("app.workers.session_translator.estimate_tokens", return_value=60):
        from app.workers.session_translator import translate_chapter
        # Must NOT raise — compact errors are swallowed
        body, _, _ = await translate_chapter(
            chapter_text=chapter_text,
            source_lang="en",
            msg=msg,
            pool=pool,
            chapter_translation_id=uuid4(),
            context_window=200,
        )

    # Both chunk translations must still be present in the output
    assert "Translated." in body
    parts = body.split("\n\n")
    assert len(parts) == 2


@pytest.mark.asyncio
async def test_compact_http_error_does_not_abort_translation():
    """Compact returning 500 must be swallowed; translation continues."""
    chunk_tokens = 50
    chunk_chars  = int(chunk_tokens * _LATIN_CHARS_PER_TOKEN)
    chapter_text = "A" * (chunk_chars + 5) + "\n\n" + "B" * (chunk_chars + 5)

    pool = _make_pool()
    msg  = _make_msg(chunk_size_tokens=chunk_tokens)

    def side_effect(method, url, **kwargs):
        payload = kwargs.get("json", {})
        if _is_compact_call(payload):
            return _StreamCM(_make_stream_resp("error", status=500))
        return _StreamCM(_make_stream_resp("Translated."))

    mock_client = _build_mock_http_client(side_effect)

    with patch("app.workers.session_translator.httpx.AsyncClient", return_value=mock_client), \
         patch("app.workers.session_translator.mint_user_jwt", return_value="jwt"), \
         patch("app.workers.session_translator.estimate_tokens", return_value=60):
        from app.workers.session_translator import translate_chapter
        body, _, _ = await translate_chapter(
            chapter_text=chapter_text,
            source_lang="en",
            msg=msg,
            pool=pool,
            chapter_translation_id=uuid4(),
            context_window=200,
        )

    assert "Translated." in body


# ── DB chunk rows ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chunk_rows_inserted_for_each_chunk():
    """
    _insert_chunk_row must be called once per chunk (pool.fetchrow INSERT).
    _update_chunk_row must be called once per chunk (pool.execute UPDATE).

    Uses chunk_tokens=200 (above 100-token floor) so the expected chunk count
    matches what translate_chapter will actually use.
    """
    chunk_tokens = 200
    chunk_chars  = int(chunk_tokens * _LATIN_CHARS_PER_TOKEN)
    chapter_text = "\n\n".join(["Para " + str(i) + " " + "X" * (chunk_chars + 50) for i in range(3)])

    pool = _make_pool()
    msg  = _make_msg(chunk_size_tokens=chunk_tokens)
    # Use effective chunk size (same floor logic as translate_chapter)
    effective_chunk = max(min(chunk_tokens, 8192 // 4), 100)
    num_chunks = len(split_chapter(chapter_text, effective_chunk))
    assert num_chunks >= 2

    def side_effect(method, url, **kwargs):
        payload = kwargs.get("json", {})
        if _is_compact_call(payload):
            return _StreamCM(_make_stream_resp("[memo]"))
        return _StreamCM(_make_stream_resp("Translated."))

    mock_client = _build_mock_http_client(side_effect)

    with patch("app.workers.session_translator.httpx.AsyncClient", return_value=mock_client), \
         patch("app.workers.session_translator.mint_user_jwt", return_value="jwt"):
        from app.workers.session_translator import translate_chapter
        await translate_chapter(
            chapter_text=chapter_text,
            source_lang="en",
            msg=msg,
            pool=pool,
            chapter_translation_id=uuid4(),
            context_window=8192,
        )

    # fetchrow = INSERT (one per chunk)
    assert pool.fetchrow.call_count == num_chunks, (
        f"Expected {num_chunks} INSERT calls, got {pool.fetchrow.call_count}"
    )
    # execute = UPDATE (one per chunk)
    assert pool.execute.call_count == num_chunks, (
        f"Expected {num_chunks} UPDATE calls, got {pool.execute.call_count}"
    )


# ── Chunk size clamping ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chunk_size_clamped_to_quarter_context():
    """
    Plan §4.2: chunk_size = min(chunk_size_tokens, context_window // 4).
    If the user requests a huge chunk but the model has a small context window,
    the effective chunk size must be capped, producing more chunks.

    Setup:
      context_window = 1600  →  context//4 = 400 tokens = 1400 chars
      chunk_size_tokens = 2000  →  clamped to 400 (floor 100 not reached)
      chapter = ~3000 chars  →  ~3 chunks when clamped (vs 1 chunk at 2000 tokens)
    """
    chapter_text = "Word. " * 500   # ~3000 chars

    # Without clamping: chunk_size=2000 tokens → 7000 chars per chunk → 1 chunk
    # With clamping at context//4=400 tokens → 1400 chars per chunk → ~3 chunks
    context_window   = 1600
    clamped_size     = context_window // 4                  # 400 tokens
    unclamped_chunks = len(split_chapter(chapter_text, 2000))
    clamped_chunks   = len(split_chapter(chapter_text, clamped_size))

    assert unclamped_chunks == 1,     "Without clamping, chapter must fit in one chunk"
    assert clamped_chunks   >= 2,     "With clamping, chapter must split into 2+ chunks"

    pool = _make_pool()
    msg  = _make_msg(chunk_size_tokens=2000)

    stream_calls: list = []

    def side_effect(method, url, **kwargs):
        payload = kwargs.get("json", {})
        if not _is_compact_call(payload):
            stream_calls.append(1)
        return _StreamCM(_make_stream_resp("T."))

    mock_client = _build_mock_http_client(side_effect)

    with patch("app.workers.session_translator.httpx.AsyncClient", return_value=mock_client), \
         patch("app.workers.session_translator.mint_user_jwt", return_value="jwt"):
        from app.workers.session_translator import translate_chapter
        await translate_chapter(
            chapter_text=chapter_text,
            source_lang="en",
            msg=msg,
            pool=pool,
            chapter_translation_id=uuid4(),
            context_window=context_window,
        )

    assert len(stream_calls) == clamped_chunks, (
        f"Expected {clamped_chunks} translation invoke calls (chunk_size clamped to "
        f"context_window//4={clamped_size}), got {len(stream_calls)}"
    )
