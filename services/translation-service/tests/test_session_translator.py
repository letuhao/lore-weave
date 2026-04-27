"""
Unit tests for session_translator — Plan §9 (Verification).

Phase 4c-β: rewritten to mock the loreweave_llm SDK via FakeLLMClient
instead of the legacy /v1/model-registry/invoke httpx + JWT path.

Covers:
- Single-chunk chapter: one SDK call, body returned as-is
- Multi-chunk chapter: chunks concatenated with double-newline
- Compaction trigger: fires when history tokens exceed context_window // 2
- Compact model fallback: uses translation model when compact_model_ref is None
- Compact failure is non-fatal: translation completes even when compact call fails
- Chunk rows written to DB for each chunk
- Token counts aggregated across all chunks
"""
from typing import Any
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4, UUID

from loreweave_llm.errors import LLMError
from loreweave_llm.models import Job, JobError

from app.workers.chunk_splitter import split_chapter, TOKEN_CHAR_RATIO, _LATIN_CHARS_PER_TOKEN


# ── Helpers ────────────────────────────────────────────────────────────────────

_DEFAULT_COMPACT_SYSTEM_EXCERPT = "Translation Memo"   # from _DEFAULT_COMPACT_SYSTEM


class FakeLLMClient:
    """Stand-in for app.llm_client.LLMClient. Captures submit_and_wait
    kwargs + replays scripted Jobs (or pre-queued exceptions).

    Phase 4c-β replacement for the legacy httpx.AsyncClient.stream(...)
    mocks. Mirrors knowledge-service's _FakeLLMClient pattern.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.queued_jobs: list[Any] = []

    def queue_translation(
        self,
        *,
        content: str = "",
        status: str = "completed",
        input_tokens: int = 100,
        output_tokens: int = 50,
        error_code: str | None = None,
        error_message: str = "",
    ) -> None:
        result: dict[str, Any] | None
        if status == "completed":
            result = {
                "messages": [{"role": "assistant", "content": content}],
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            }
        else:
            result = None
        error = JobError(code=error_code, message=error_message) if error_code else None
        self.queued_jobs.append(Job(
            job_id="00000000-0000-0000-0000-000000000001",
            operation="translation",
            status=status,  # type: ignore[arg-type]
            result=result,
            error=error,
            submitted_at="2026-04-27T00:00:00Z",
        ))

    def queue_exception(self, exc: Exception) -> None:
        self.queued_jobs.append(exc)

    async def submit_and_wait(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self.queued_jobs:
            raise AssertionError("FakeLLMClient: no queued response")
        item = self.queued_jobs.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


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


def _is_compact_call(call_kwargs: dict) -> bool:
    """Return True if a submit_and_wait call kwargs is a compact (not translation) request."""
    messages = call_kwargs.get("input", {}).get("messages", [])
    return any(
        _DEFAULT_COMPACT_SYSTEM_EXCERPT in m.get("content", "")
        for m in messages
        if m.get("role") == "system"
    )


# ── Single-chunk chapter ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_single_chunk_returns_translated_body():
    """Short chapter fits in one chunk → exactly one SDK call, body returned."""
    pool = _make_pool()
    msg  = _make_msg(chunk_size_tokens=1000)   # huge chunk — whole chapter fits
    chapter_text = "Hello world. This is a short chapter."

    fake = FakeLLMClient()
    fake.queue_translation(content="Xin chào thế giới.")

    from app.workers.session_translator import translate_chapter
    body, in_tok, out_tok = await translate_chapter(
        chapter_text=chapter_text,
        source_lang="en",
        msg=msg,
        pool=pool,
        chapter_translation_id=uuid4(),
        llm_client=fake,
        context_window=8192,
    )

    assert body == "Xin chào thế giới."
    assert len(fake.calls) == 1   # exactly one SDK call — no compaction


@pytest.mark.asyncio
async def test_single_chunk_aggregates_token_counts():
    """Token counts from the SDK Job result are returned."""
    pool = _make_pool()
    msg  = _make_msg(chunk_size_tokens=1000)

    fake = FakeLLMClient()
    fake.queue_translation(content="Translated.", input_tokens=42, output_tokens=17)

    from app.workers.session_translator import translate_chapter
    _, in_tok, out_tok = await translate_chapter(
        chapter_text="Short.",
        source_lang="en",
        msg=msg,
        pool=pool,
        chapter_translation_id=uuid4(),
        llm_client=fake,
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

    fake = FakeLLMClient()
    # Pre-queue one job per expected translation chunk (compaction won't fire — context_window=8192)
    for i in range(chunk_count):
        fake.queue_translation(content=f"TRANSLATED_{i}")

    from app.workers.session_translator import translate_chapter
    body, _, _ = await translate_chapter(
        chapter_text=chapter_text,
        source_lang="en",
        msg=msg,
        pool=pool,
        chapter_translation_id=uuid4(),
        llm_client=fake,
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

    fake = FakeLLMClient()

    # Override submit_and_wait to differentiate compact vs translation jobs on the fly
    async def _smart_submit(**kwargs: Any) -> Any:
        fake.calls.append(kwargs)
        if _is_compact_call(kwargs):
            return Job(
                job_id="00000000-0000-0000-0000-0000000000c0",
                operation="translation",
                status="completed",
                result={
                    "messages": [{"role": "assistant", "content": "[memo]"}],
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
                error=None,
                submitted_at="2026-04-27T00:00:00Z",
            )
        return Job(
            job_id="00000000-0000-0000-0000-000000000001",
            operation="translation",
            status="completed",
            result={
                "messages": [{"role": "assistant", "content": "Translated."}],
                "usage": {"input_tokens": 5, "output_tokens": 3},
            },
            error=None,
            submitted_at="2026-04-27T00:00:00Z",
        )

    fake.submit_and_wait = _smart_submit  # type: ignore[assignment]

    from app.workers.session_translator import translate_chapter
    _, in_tok, out_tok = await translate_chapter(
        chapter_text=chapter_text,
        source_lang="en",
        msg=msg,
        pool=pool,
        chapter_translation_id=uuid4(),
        llm_client=fake,
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

    pool = _make_pool()
    msg  = _make_msg(chunk_size_tokens=chunk_tokens)

    fake = FakeLLMClient()

    async def _smart_submit(**kwargs: Any) -> Any:
        fake.calls.append(kwargs)
        if _is_compact_call(kwargs):
            text = "[MEMO: key names]"
        else:
            text = "Translated chunk."
        return Job(
            job_id="00000000-0000-0000-0000-000000000001",
            operation="translation",
            status="completed",
            result={
                "messages": [{"role": "assistant", "content": text}],
                "usage": {"input_tokens": 10, "output_tokens": 8},
            },
            error=None,
            submitted_at="2026-04-27T00:00:00Z",
        )

    fake.submit_and_wait = _smart_submit  # type: ignore[assignment]

    from unittest.mock import patch
    with patch("app.workers.session_translator.estimate_tokens", return_value=60):
        from app.workers.session_translator import translate_chapter
        body, _, _ = await translate_chapter(
            chapter_text=chapter_text,
            source_lang="en",
            msg=msg,
            pool=pool,
            chapter_translation_id=uuid4(),
            llm_client=fake,
            context_window=200,   # threshold = 100; history 120 > 100 → compact
        )

    compact_calls = [c for c in fake.calls if _is_compact_call(c)]

    assert len(compact_calls) >= 1, (
        f"Expected at least 1 compact call, got {len(compact_calls)}. "
        f"Total SDK calls: {len(fake.calls)}"
    )


@pytest.mark.asyncio
async def test_no_compaction_when_history_below_threshold():
    """With a large context_window, history never triggers compaction."""
    chapter_text = "Sentence one. Sentence two. Sentence three." * 5
    chunk_tokens = 10   # many small chunks

    pool = _make_pool()
    msg  = _make_msg(chunk_size_tokens=chunk_tokens)

    fake = FakeLLMClient()

    async def _smart_submit(**kwargs: Any) -> Any:
        fake.calls.append(kwargs)
        return Job(
            job_id="00000000-0000-0000-0000-000000000001",
            operation="translation",
            status="completed",
            result={
                "messages": [{"role": "assistant", "content": "Translated."}],
                "usage": {"input_tokens": 5, "output_tokens": 3},
            },
            error=None,
            submitted_at="2026-04-27T00:00:00Z",
        )

    fake.submit_and_wait = _smart_submit  # type: ignore[assignment]

    from app.workers.session_translator import translate_chapter
    await translate_chapter(
        chapter_text=chapter_text,
        source_lang="en",
        msg=msg,
        pool=pool,
        chapter_translation_id=uuid4(),
        llm_client=fake,
        context_window=1_000_000,   # huge — compact never fires
    )

    compact_calls = [c for c in fake.calls if _is_compact_call(c)]
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

    fake = FakeLLMClient()

    async def _smart_submit(**kwargs: Any) -> Any:
        fake.calls.append(kwargs)
        text = "[memo]" if _is_compact_call(kwargs) else "Translated."
        return Job(
            job_id="00000000-0000-0000-0000-000000000001",
            operation="translation",
            status="completed",
            result={
                "messages": [{"role": "assistant", "content": text}],
                "usage": {"input_tokens": 10, "output_tokens": 8},
            },
            error=None,
            submitted_at="2026-04-27T00:00:00Z",
        )

    fake.submit_and_wait = _smart_submit  # type: ignore[assignment]

    from unittest.mock import patch
    with patch("app.workers.session_translator.estimate_tokens", return_value=60):
        from app.workers.session_translator import translate_chapter
        await translate_chapter(
            chapter_text=chapter_text,
            source_lang="en",
            msg=msg,
            pool=pool,
            chapter_translation_id=uuid4(),
            llm_client=fake,
            context_window=200,
        )

    compact_calls = [c for c in fake.calls if _is_compact_call(c)]
    assert compact_calls, "Expected at least one compact call to occur"
    for cp in compact_calls:
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

    fake = FakeLLMClient()

    async def _smart_submit(**kwargs: Any) -> Any:
        fake.calls.append(kwargs)
        text = "[memo]" if _is_compact_call(kwargs) else "Translated."
        return Job(
            job_id="00000000-0000-0000-0000-000000000001",
            operation="translation",
            status="completed",
            result={
                "messages": [{"role": "assistant", "content": text}],
                "usage": {"input_tokens": 10, "output_tokens": 8},
            },
            error=None,
            submitted_at="2026-04-27T00:00:00Z",
        )

    fake.submit_and_wait = _smart_submit  # type: ignore[assignment]

    from unittest.mock import patch
    with patch("app.workers.session_translator.estimate_tokens", return_value=60):
        from app.workers.session_translator import translate_chapter
        await translate_chapter(
            chapter_text=chapter_text,
            source_lang="en",
            msg=msg,
            pool=pool,
            chapter_translation_id=uuid4(),
            llm_client=fake,
            context_window=200,
        )

    compact_calls = [c for c in fake.calls if _is_compact_call(c)]
    assert compact_calls, "Expected at least one compact call to occur"
    for cp in compact_calls:
        assert cp["model_source"] == "user_model"
        assert cp["model_ref"]    == compact_model_ref


# ── Compact failure is non-fatal ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compact_failure_does_not_abort_translation():
    """
    Plan §9: If the compact model call raises an exception (or returns
    a non-completed Job), translation must continue to completion —
    compaction is best-effort.
    """
    chunk_tokens = 50
    chunk_chars  = int(chunk_tokens * _LATIN_CHARS_PER_TOKEN)
    chapter_text = "A" * (chunk_chars + 5) + "\n\n" + "B" * (chunk_chars + 5)

    pool = _make_pool()
    msg  = _make_msg(chunk_size_tokens=chunk_tokens)

    fake = FakeLLMClient()

    async def _smart_submit(**kwargs: Any) -> Any:
        fake.calls.append(kwargs)
        if _is_compact_call(kwargs):
            # Compact call fails hard — _compact_history must swallow it
            raise Exception("compact model unreachable")
        return Job(
            job_id="00000000-0000-0000-0000-000000000001",
            operation="translation",
            status="completed",
            result={
                "messages": [{"role": "assistant", "content": "Translated."}],
                "usage": {"input_tokens": 10, "output_tokens": 8},
            },
            error=None,
            submitted_at="2026-04-27T00:00:00Z",
        )

    fake.submit_and_wait = _smart_submit  # type: ignore[assignment]

    from unittest.mock import patch
    with patch("app.workers.session_translator.estimate_tokens", return_value=60):
        from app.workers.session_translator import translate_chapter
        # Must NOT raise — compact errors are swallowed
        body, _, _ = await translate_chapter(
            chapter_text=chapter_text,
            source_lang="en",
            msg=msg,
            pool=pool,
            chapter_translation_id=uuid4(),
            llm_client=fake,
            context_window=200,
        )

    # Both chunk translations must still be present in the output
    assert "Translated." in body
    parts = body.split("\n\n")
    assert len(parts) == 2


@pytest.mark.asyncio
async def test_compact_http_error_does_not_abort_translation():
    """Compact returning a non-completed Job (failed status) must be
    swallowed; translation continues."""
    chunk_tokens = 50
    chunk_chars  = int(chunk_tokens * _LATIN_CHARS_PER_TOKEN)
    chapter_text = "A" * (chunk_chars + 5) + "\n\n" + "B" * (chunk_chars + 5)

    pool = _make_pool()
    msg  = _make_msg(chunk_size_tokens=chunk_tokens)

    fake = FakeLLMClient()

    async def _smart_submit(**kwargs: Any) -> Any:
        fake.calls.append(kwargs)
        if _is_compact_call(kwargs):
            # Compact returns a failed Job — _compact_history returns old_memo
            return Job(
                job_id="00000000-0000-0000-0000-0000000000c0",
                operation="translation",
                status="failed",
                result=None,
                error=JobError(code="LLM_UPSTREAM_ERROR", message="500"),
                submitted_at="2026-04-27T00:00:00Z",
            )
        return Job(
            job_id="00000000-0000-0000-0000-000000000001",
            operation="translation",
            status="completed",
            result={
                "messages": [{"role": "assistant", "content": "Translated."}],
                "usage": {"input_tokens": 10, "output_tokens": 8},
            },
            error=None,
            submitted_at="2026-04-27T00:00:00Z",
        )

    fake.submit_and_wait = _smart_submit  # type: ignore[assignment]

    from unittest.mock import patch
    with patch("app.workers.session_translator.estimate_tokens", return_value=60):
        from app.workers.session_translator import translate_chapter
        body, _, _ = await translate_chapter(
            chapter_text=chapter_text,
            source_lang="en",
            msg=msg,
            pool=pool,
            chapter_translation_id=uuid4(),
            llm_client=fake,
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

    fake = FakeLLMClient()

    async def _smart_submit(**kwargs: Any) -> Any:
        fake.calls.append(kwargs)
        text = "[memo]" if _is_compact_call(kwargs) else "Translated."
        return Job(
            job_id="00000000-0000-0000-0000-000000000001",
            operation="translation",
            status="completed",
            result={
                "messages": [{"role": "assistant", "content": text}],
                "usage": {"input_tokens": 10, "output_tokens": 8},
            },
            error=None,
            submitted_at="2026-04-27T00:00:00Z",
        )

    fake.submit_and_wait = _smart_submit  # type: ignore[assignment]

    from app.workers.session_translator import translate_chapter
    await translate_chapter(
        chapter_text=chapter_text,
        source_lang="en",
        msg=msg,
        pool=pool,
        chapter_translation_id=uuid4(),
        llm_client=fake,
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

    fake = FakeLLMClient()

    async def _smart_submit(**kwargs: Any) -> Any:
        fake.calls.append(kwargs)
        return Job(
            job_id="00000000-0000-0000-0000-000000000001",
            operation="translation",
            status="completed",
            result={
                "messages": [{"role": "assistant", "content": "T."}],
                "usage": {"input_tokens": 10, "output_tokens": 8},
            },
            error=None,
            submitted_at="2026-04-27T00:00:00Z",
        )

    fake.submit_and_wait = _smart_submit  # type: ignore[assignment]

    from app.workers.session_translator import translate_chapter
    await translate_chapter(
        chapter_text=chapter_text,
        source_lang="en",
        msg=msg,
        pool=pool,
        chapter_translation_id=uuid4(),
        llm_client=fake,
        context_window=context_window,
    )

    translation_calls = [c for c in fake.calls if not _is_compact_call(c)]
    assert len(translation_calls) == clamped_chunks, (
        f"Expected {clamped_chunks} translation SDK calls (chunk_size clamped to "
        f"context_window//4={clamped_size}), got {len(translation_calls)}"
    )


# ── Phase 4c-β /review-impl MED#1 — wire-format pin tests ──────────────────────

@pytest.mark.asyncio
async def test_translate_chapter_sdk_request_body_shape():
    """Phase 4c-β /review-impl MED#1 — pin the full submit_and_wait
    kwargs shape against server-side gateway PersistJobRequest. If a
    future SDK rename or settings drift breaks model_source / model_ref
    / chunking / job_meta, this catches it in CI rather than at
    production submit time (where it would silently 422)."""
    pool = _make_pool()
    msg  = _make_msg(
        chunk_size_tokens=1000,
        model_source="user_model",
        model_ref="qwen-test-translation",
    )

    fake = FakeLLMClient()
    fake.queue_translation(content="translated")

    from app.workers.session_translator import translate_chapter
    await translate_chapter(
        chapter_text="One short paragraph.",
        source_lang="en",
        msg=msg,
        pool=pool,
        chapter_translation_id=uuid4(),
        llm_client=fake,
        context_window=8192,
    )

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["operation"] == "translation"
    assert call["model_source"] == "user_model"
    assert call["model_ref"] == "qwen-test-translation"
    # Caller already chunked via split_chapter — gateway must not re-chunk
    assert call["chunking"] is None
    # job_meta carries reverse-lookup keys per Phase 4a ADR §3.3 D6
    assert "chapter_translation_id" in call["job_meta"]
    assert "chunk_idx" in call["job_meta"]
    assert call["job_meta"]["chunk_idx"] == 0
    # 2-message structure (system + user) — matches gateway chunker
    # SubstituteLastUserMessage invariant
    msgs = call["input"]["messages"]
    assert len(msgs) >= 2
    assert msgs[0]["role"] == "system"
    assert msgs[-1]["role"] == "user"


# ── Phase 4c-β /review-impl HIGH#1 — permanent-error mapping ──────────────────

@pytest.mark.asyncio
async def test_translate_chunk_quota_exceeded_raises_permanent_billing_rejected():
    """Phase 4c-β /review-impl HIGH#1 — LLMQuotaExceeded (402 billing)
    must surface as _PermanentError('billing_rejected'), NOT as
    _TransientError. Otherwise the runner's 3-retry loop wastes calls
    on misconfigured BYOK that will never resolve."""
    from loreweave_llm.errors import LLMQuotaExceeded
    from app.workers.chapter_worker import _PermanentError

    pool = _make_pool()
    msg  = _make_msg(chunk_size_tokens=1000)

    fake = FakeLLMClient()
    fake.queue_exception(LLMQuotaExceeded("402 billing rejected"))

    from app.workers.session_translator import translate_chapter
    with pytest.raises(_PermanentError, match="billing_rejected"):
        await translate_chapter(
            chapter_text="text",
            source_lang="en",
            msg=msg,
            pool=pool,
            chapter_translation_id=uuid4(),
            llm_client=fake,
            context_window=8192,
        )


@pytest.mark.asyncio
async def test_translate_chunk_model_not_found_raises_permanent_model_not_found():
    """Phase 4c-β /review-impl HIGH#1 — LLMModelNotFound (404) must
    surface as _PermanentError('model_not_found'), NOT transient."""
    from loreweave_llm.errors import LLMModelNotFound
    from app.workers.chapter_worker import _PermanentError

    pool = _make_pool()
    fake = FakeLLMClient()
    fake.queue_exception(LLMModelNotFound("404 model not found"))

    from app.workers.session_translator import translate_chapter
    with pytest.raises(_PermanentError, match="model_not_found"):
        await translate_chapter(
            chapter_text="text",
            source_lang="en",
            msg=_make_msg(chunk_size_tokens=1000),
            pool=pool,
            chapter_translation_id=uuid4(),
            llm_client=fake,
            context_window=8192,
        )


@pytest.mark.asyncio
async def test_translate_chunk_auth_failed_raises_permanent():
    """Phase 4c-β /review-impl HIGH#1 — LLMAuthFailed (401/403) is a
    config error; PERMANENT, no retry."""
    from loreweave_llm.errors import LLMAuthFailed
    from app.workers.chapter_worker import _PermanentError

    pool = _make_pool()
    fake = FakeLLMClient()
    fake.queue_exception(LLMAuthFailed("401 unauthorized"))

    from app.workers.session_translator import translate_chapter
    with pytest.raises(_PermanentError, match="LLMAuthFailed"):
        await translate_chapter(
            chapter_text="text",
            source_lang="en",
            msg=_make_msg(chunk_size_tokens=1000),
            pool=pool,
            chapter_translation_id=uuid4(),
            llm_client=fake,
            context_window=8192,
        )


@pytest.mark.asyncio
async def test_translate_chunk_invalid_request_raises_permanent():
    """Phase 4c-β /review-impl HIGH#1 — LLMInvalidRequest (400) is
    body-validation; PERMANENT, no retry."""
    from loreweave_llm.errors import LLMInvalidRequest
    from app.workers.chapter_worker import _PermanentError

    pool = _make_pool()
    fake = FakeLLMClient()
    fake.queue_exception(LLMInvalidRequest("400 bad body"))

    from app.workers.session_translator import translate_chapter
    with pytest.raises(_PermanentError, match="LLMInvalidRequest"):
        await translate_chapter(
            chapter_text="text",
            source_lang="en",
            msg=_make_msg(chunk_size_tokens=1000),
            pool=pool,
            chapter_translation_id=uuid4(),
            llm_client=fake,
            context_window=8192,
        )


@pytest.mark.asyncio
async def test_translate_chunk_upstream_error_remains_transient():
    """Phase 4c-β /review-impl HIGH#1 — generic LLMError (transport,
    upstream 5xx, etc.) STAYS transient so the runner retries.
    Regression-locks the existing semantic — only the permanent
    subclasses got demoted to _PermanentError."""
    from loreweave_llm.errors import LLMUpstreamError
    from app.workers.chapter_worker import _TransientError

    pool = _make_pool()
    fake = FakeLLMClient()
    fake.queue_exception(LLMUpstreamError("502 bad gateway"))

    from app.workers.session_translator import translate_chapter
    with pytest.raises(_TransientError, match="invoke unreachable"):
        await translate_chapter(
            chapter_text="text",
            source_lang="en",
            msg=_make_msg(chunk_size_tokens=1000),
            pool=pool,
            chapter_translation_id=uuid4(),
            llm_client=fake,
            context_window=8192,
        )
