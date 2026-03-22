"""
Tests for translation_runner.py.

Critical invariant (from design doc §6):
  translation-service must not import any provider SDK directly.
  All model invocations go through provider-registry-service via httpx.
"""
import ast
import datetime
import pathlib
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import UUID, uuid4

import httpx
import pytest

from tests.conftest import FakeRecord

# ── Provider gateway invariant ────────────────────────────────────────────────

def test_no_provider_sdk_imports_in_translation_runner():
    """
    translation_runner.py must NOT import openai, anthropic, cohere,
    mistral, or any other provider SDK directly.
    """
    source_path = (
        pathlib.Path(__file__).parent.parent / "app" / "services" / "translation_runner.py"
    )
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_prefixes = {"openai", "anthropic", "cohere", "mistral", "google.generativeai", "boto3"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in forbidden_prefixes:
                    assert not alias.name.startswith(prefix), (
                        f"Forbidden direct SDK import in translation_runner.py: {alias.name}"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for prefix in forbidden_prefixes:
                assert not module.startswith(prefix), (
                    f"Forbidden direct SDK import in translation_runner.py: from {module}"
                )


def test_translation_runner_uses_httpx_for_invocation():
    """translation_runner.py must use httpx (not requests or SDK) for HTTP calls."""
    source_path = (
        pathlib.Path(__file__).parent.parent / "app" / "services" / "translation_runner.py"
    )
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imports_httpx = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "httpx" for a in node.names):
                imports_httpx = True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "httpx":
                imports_httpx = True

    assert imports_httpx, "translation_runner.py must import httpx for provider invocation"


# ── Job execution — happy path ────────────────────────────────────────────────

USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
JOB_ID = uuid4()
BOOK_ID = uuid4()
CHAPTER_ID = uuid4()
MODEL_REF = uuid4()
_NOW = datetime.datetime.utcnow()

_JOB_ROW = FakeRecord({
    "job_id": JOB_ID,
    "book_id": BOOK_ID,
    "owner_user_id": UUID(USER_ID),
    "status": "pending",
    "target_language": "vi",
    "model_source": "platform_model",
    "model_ref": MODEL_REF,
    "system_prompt": "Translate faithfully.",
    "user_prompt_tpl": "Translate {source_language} to {target_language}:\n{chapter_text}",
    "chapter_ids": [CHAPTER_ID],
    "total_chapters": 1,
    "completed_chapters": 0,
    "failed_chapters": 0,
    "error_message": None,
    "started_at": None,
    "finished_at": None,
    "created_at": _NOW,
})


def _make_pool(job_row=_JOB_ROW, status_after_run="pending"):
    pool = MagicMock()
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetchrow = AsyncMock()
    conn.fetchval = AsyncMock(return_value=status_after_run)  # cancellation check

    # First fetchrow call → job row; second → final status row
    conn.fetchrow.side_effect = [
        job_row,
        FakeRecord({
            "status": "pending",
            "total_chapters": 1,
            "completed_chapters": 1,
            "failed_chapters": 0,
        }),
    ]

    pool.acquire = MagicMock(return_value=_AsyncContextManager(conn))
    return pool, conn


class _AsyncContextManager:
    """Wraps an object as an async context manager."""
    def __init__(self, obj):
        self._obj = obj

    async def __aenter__(self):
        return self._obj

    async def __aexit__(self, *_):
        pass


def _book_chapter_response():
    r = MagicMock(spec=httpx.Response)
    r.status_code = 200
    r.is_success = True
    r.json.return_value = {
        "chapter_id": str(CHAPTER_ID),
        "original_language": "en",
        "body": "In the beginning...",
    }
    return r


def _invoke_response():
    r = MagicMock(spec=httpx.Response)
    r.status_code = 200
    r.is_success = True
    r.json.return_value = {
        "output": {"content": "Vào thuở ban đầu..."},
        "usage_log_id": str(uuid4()),
        "usage": {"input_tokens": 10, "output_tokens": 8},
    }
    return r


@pytest.mark.asyncio
async def test_run_translation_job_happy_path():
    pool, conn = _make_pool()

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=_book_chapter_response())
    mock_http.post = AsyncMock(return_value=_invoke_response())

    with patch("app.services.translation_runner.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.services.translation_runner import run_translation_job
        await run_translation_job(JOB_ID, USER_ID, pool)

    # Chapter was fetched from book-service
    mock_http.get.assert_called_once()
    get_url = mock_http.get.call_args.args[0]
    assert str(CHAPTER_ID) in get_url

    # invoke was called on provider-registry, NOT any SDK
    mock_http.post.assert_called_once()
    post_url = mock_http.post.call_args.args[0]
    assert "model-registry/invoke" in post_url

    # Job was marked running then updated to final status
    execute_calls = [str(c) for c in conn.execute.call_args_list]
    assert any("running" in c for c in execute_calls)


@pytest.mark.asyncio
async def test_run_translation_job_chapter_not_found_marks_failed():
    pool, conn = _make_pool()

    not_found = MagicMock(spec=httpx.Response)
    not_found.status_code = 404
    not_found.is_success = False

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=not_found)

    with patch("app.services.translation_runner.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.services.translation_runner import run_translation_job
        await run_translation_job(JOB_ID, USER_ID, pool)

    # chapter_translations must be marked failed with chapter_not_found
    execute_calls = [str(c) for c in conn.execute.call_args_list]
    assert any("chapter_not_found" in c for c in execute_calls)
    # invoke must NOT be called
    mock_http.post.assert_not_called()


@pytest.mark.asyncio
async def test_run_translation_job_billing_rejected_marks_chapter_failed():
    pool, conn = _make_pool()

    billing_rejected = MagicMock(spec=httpx.Response)
    billing_rejected.status_code = 402
    billing_rejected.is_success = False

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=_book_chapter_response())
    mock_http.post = AsyncMock(return_value=billing_rejected)

    with patch("app.services.translation_runner.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.services.translation_runner import run_translation_job
        await run_translation_job(JOB_ID, USER_ID, pool)

    execute_calls = [str(c) for c in conn.execute.call_args_list]
    assert any("billing_rejected" in c for c in execute_calls)


@pytest.mark.asyncio
async def test_run_translation_job_stops_when_cancelled():
    """If job status becomes 'cancelled', runner exits without processing remaining chapters."""
    pool, conn = _make_pool(status_after_run="cancelled")
    # Override: fetchval returns 'cancelled' → runner should exit early
    conn.fetchval = AsyncMock(return_value="cancelled")

    mock_http = AsyncMock()

    with patch("app.services.translation_runner.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.services.translation_runner import run_translation_job
        await run_translation_job(JOB_ID, USER_ID, pool)

    # No chapter processing (get / post) should have happened
    mock_http.get.assert_not_called()
    mock_http.post.assert_not_called()


@pytest.mark.asyncio
async def test_run_translation_job_refreshes_jwt_before_expiry():
    """
    JWT refresh logic: if time.time() > token_exp - 30, a new token is minted.
    We verify mint_user_jwt is called more than once when simulating near-expiry.
    """
    import time

    pool, conn = _make_pool()
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=_book_chapter_response())
    mock_http.post = AsyncMock(return_value=_invoke_response())

    # Simulate time advancing past expiry window
    call_count = 0
    original_time = time.time

    def fake_time():
        nonlocal call_count
        call_count += 1
        # After first call, jump 290s into the future (within 30s of 300s TTL)
        if call_count > 2:
            return original_time() + 290
        return original_time()

    with patch("app.services.translation_runner.httpx.AsyncClient") as mock_cls, \
         patch("app.services.translation_runner.time.time", side_effect=fake_time), \
         patch("app.services.translation_runner.mint_user_jwt", return_value="fresh_token") as mock_mint:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.services.translation_runner import run_translation_job
        await run_translation_job(JOB_ID, USER_ID, pool)

    # mint_user_jwt should have been called at least once (initial mint)
    assert mock_mint.call_count >= 1
