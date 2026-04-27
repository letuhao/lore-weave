"""K20α — unit tests for the public regenerate endpoints.

Covers the HTTP mapping layer on top of the regen helper:
  - JWT-scoped user_id (body cannot spoof)
  - 200 for `regenerated`, `no_op_similarity`, `no_op_empty_source`
  - 409 for `user_edit_lock` and `regen_concurrent_edit`
  - 422 for `no_op_guardrail`
  - 502 for ProviderError
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.clients.llm_client import ProviderUpstreamError
from app.db.models import Summary
from app.jobs.regenerate_summaries import RegenerationResult


_TEST_USER = uuid4()
_PROJECT_ID = uuid4()


def _summary_stub(version: int = 5, scope_type: str = "global") -> Summary:
    return Summary(
        summary_id=uuid4(),
        user_id=_TEST_USER,
        scope_type=scope_type,  # type: ignore[arg-type]
        scope_id=None if scope_type == "global" else _PROJECT_ID,
        content="regenerated bio",
        token_count=10,
        version=version,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _make_client(*, cooldown=None) -> TestClient:
    """Wire common overrides. `cooldown` lets a test inject a fake
    Redis client (or leave None to exercise the no-Redis degrade path).
    """
    from app.main import app
    from app.middleware.jwt_auth import get_current_user
    from app.deps import (
        get_llm_client,
        get_summaries_repo,
        get_summary_spending_repo,
    )
    from app.routers.public.summaries import get_cooldown_client

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_llm_client] = lambda: MagicMock()
    app.dependency_overrides[get_summaries_repo] = lambda: MagicMock()
    # C16-BUILD: stub the spending repo so get_knowledge_pool() isn't hit.
    app.dependency_overrides[get_summary_spending_repo] = lambda: MagicMock()
    app.dependency_overrides[get_cooldown_client] = lambda: cooldown
    return TestClient(app, raise_server_exceptions=False)


# ── global regenerate ────────────────────────────────────────────────


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_global_happy_path(mock_regen):
    summary = _summary_stub()
    mock_regen.return_value = RegenerationResult(
        status="regenerated", summary=summary
    )
    client = _make_client()
    resp = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["status"] == "regenerated"
    assert body["summary"]["version"] == 5
    # JWT user_id is what reaches the helper, not anything from the body.
    assert mock_regen.await_args.kwargs["user_id"] == _TEST_USER


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_global_user_edit_lock_maps_409(mock_regen):
    mock_regen.return_value = RegenerationResult(
        status="user_edit_lock", skipped_reason="recent manual edit"
    )
    client = _make_client()
    resp = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["detail"]["error_code"] == "user_edit_lock"
    assert "recent manual edit" in body["detail"]["message"]


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_global_concurrent_edit_maps_409(mock_regen):
    mock_regen.return_value = RegenerationResult(
        status="regen_concurrent_edit", skipped_reason="version bumped"
    )
    client = _make_client()
    resp = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error_code"] == "regen_concurrent_edit"


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_global_guardrail_maps_422(mock_regen):
    mock_regen.return_value = RegenerationResult(
        status="no_op_guardrail", skipped_reason="empty_output"
    )
    client = _make_client()
    resp = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["error_code"] == "regen_guardrail_failed"


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_global_empty_source_returns_200(mock_regen):
    mock_regen.return_value = RegenerationResult(
        status="no_op_empty_source", skipped_reason="no source"
    )
    client = _make_client()
    resp = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "no_op_empty_source"
    assert resp.json()["summary"] is None


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_global_provider_error_maps_502(mock_regen):
    mock_regen.side_effect = ProviderUpstreamError("upstream boom")
    client = _make_client()
    resp = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp.status_code == 502
    assert resp.json()["detail"]["error_code"] == "provider_error"


def test_regenerate_global_rejects_missing_model_ref():
    client = _make_client()
    resp = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model"},  # model_ref required
    )
    assert resp.status_code == 422


# ── project regenerate ───────────────────────────────────────────────


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_project_summary", new_callable=AsyncMock)
def test_regenerate_project_passes_project_id(mock_regen):
    summary = _summary_stub(scope_type="project")
    mock_regen.return_value = RegenerationResult(
        status="regenerated", summary=summary
    )
    client = _make_client()
    resp = client.post(
        f"/v1/knowledge/projects/{_PROJECT_ID}/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp.status_code == 200, resp.json()
    assert mock_regen.await_args.kwargs["project_id"] == _PROJECT_ID
    assert mock_regen.await_args.kwargs["user_id"] == _TEST_USER


# ── C16-BUILD: spending repo wire-through (review-impl HIGH-1) ──────


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_global_forwards_spending_repo_to_helper(mock_regen):
    """C16-BUILD review-impl regression lock: the public global regen
    endpoint MUST pass ``summary_spending_repo`` to the helper so the
    budget pre-check + post-success recorder are not silently bypassed
    on manual regen (the most common trigger path). A regression that
    drops the kwarg would re-open D-K20α-01 — the user could blow
    through their cap by spamming the regenerate button. Locks the
    DI plumbing that the 25-test cascade exposed during review-impl."""
    sentinel = MagicMock(name="SummarySpendingRepoSentinel")
    from app.deps import get_summary_spending_repo
    from app.main import app

    mock_regen.return_value = RegenerationResult(
        status="regenerated", summary=_summary_stub(),
    )
    client = _make_client()
    # Override AFTER _make_client — it sets a default stub for the same
    # key, and dict assignment is last-write-wins.
    app.dependency_overrides[get_summary_spending_repo] = lambda: sentinel
    resp = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp.status_code == 200, resp.json()
    assert mock_regen.await_args.kwargs["summary_spending_repo"] is sentinel


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_project_summary", new_callable=AsyncMock)
def test_regenerate_project_forwards_spending_repo_to_helper(mock_regen):
    """Same regression lock for the project-scope public endpoint —
    pre-check applies even though project regen records via the K16.11
    path; without the kwarg the pre-check is gated off entirely."""
    sentinel = MagicMock(name="SummarySpendingRepoSentinel")
    from app.deps import get_summary_spending_repo
    from app.main import app

    mock_regen.return_value = RegenerationResult(
        status="regenerated", summary=_summary_stub(scope_type="project"),
    )
    client = _make_client()
    app.dependency_overrides[get_summary_spending_repo] = lambda: sentinel
    resp = client.post(
        f"/v1/knowledge/projects/{_PROJECT_ID}/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp.status_code == 200, resp.json()
    assert mock_regen.await_args.kwargs["summary_spending_repo"] is sentinel


# ── C2 — cooldown (D-K20α-02) ────────────────────────────────────────


class _FakeRedis:
    """In-memory SETNX + TTL emulator. No real Redis dep in unit tests.

    Only covers the operations the cooldown helper uses: `set(nx=, ex=)`,
    `ttl`, and `delete`. TTL defaults to the value we were asked to
    store since the helper reads it immediately after SETNX returns
    False — no monotonic clock needed for most coverage. The
    ``expired_keys`` option lets a test force TTL to return -2 for the
    matching keys so the "race between SETNX and TTL" floor-to-1
    defensive branch becomes reachable.
    """

    def __init__(self, *, expired_keys: set[str] | None = None) -> None:
        self._store: dict[str, int] = {}
        self._expired_keys = expired_keys or set()

    async def set(
        self, key: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> bool | None:
        if nx and key in self._store:
            return None
        self._store[key] = ex if ex is not None else -1
        return True

    async def ttl(self, key: str) -> int:
        if key in self._expired_keys:
            # Simulates the race where the key expired between SETNX
            # (returned False) and TTL read. Real Redis returns -2
            # for "key does not exist".
            return -2
        return self._store.get(key, -2)

    async def delete(self, key: str) -> int:
        # redis-py returns the number of keys deleted (0 or 1 here).
        return 1 if self._store.pop(key, None) is not None else 0


class _BoomRedis:
    """Simulates Redis errors on every call — lets us assert the
    graceful-degrade path without depending on socket behaviour."""

    async def set(self, *args, **kwargs) -> None:
        raise ConnectionError("simulated redis outage")

    async def ttl(self, *args, **kwargs) -> int:
        raise ConnectionError("simulated redis outage")

    async def delete(self, *args, **kwargs) -> int:
        raise ConnectionError("simulated redis outage")


class _HalfBoomRedis:
    """SET + DELETE succeed like a real Redis, but TTL always raises.
    Exercises the ``try/except`` around ``client.ttl(key)`` that a
    regression removing the guard wouldn't otherwise trip."""

    def __init__(self) -> None:
        self._store: dict[str, int] = {}

    async def set(
        self, key: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> bool | None:
        if nx and key in self._store:
            return None
        self._store[key] = ex if ex is not None else -1
        return True

    async def ttl(self, *args, **kwargs) -> int:
        raise ConnectionError("simulated redis TTL outage")

    async def delete(self, key: str) -> int:
        return 1 if self._store.pop(key, None) is not None else 0


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_global_cooldown_blocks_second_call(mock_regen):
    """C2 acceptance: second regen within the cooldown window returns
    429 + Retry-After. First call must succeed + arm the cooldown; the
    regen helper must NOT be invoked for the second call (rate limit
    short-circuits before the LLM is touched)."""
    mock_regen.return_value = RegenerationResult(
        status="regenerated", summary=_summary_stub()
    )
    fake_redis = _FakeRedis()
    client = _make_client(cooldown=fake_redis)

    resp1 = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp1.status_code == 200, resp1.json()
    assert mock_regen.await_count == 1

    resp2 = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp2.status_code == 429
    body = resp2.json()
    assert body["detail"]["error_code"] == "regen_cooldown"
    retry_after = resp2.headers["Retry-After"]
    assert 1 <= int(retry_after) <= 60
    # Regen helper was NOT called a second time — rate limit armed
    # before the LLM path.
    assert mock_regen.await_count == 1


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_project_summary", new_callable=AsyncMock)
def test_regenerate_project_cooldown_per_project_scope(mock_regen):
    """C2: cooldown is keyed on project_id, so a user on cooldown for
    project A can still regen project B. Locks the
    `_cooldown_key({user}:{scope}:{scope_id})` contract."""
    mock_regen.return_value = RegenerationResult(
        status="regenerated", summary=_summary_stub(scope_type="project")
    )
    other_project = uuid4()
    fake_redis = _FakeRedis()
    client = _make_client(cooldown=fake_redis)

    resp_a1 = client.post(
        f"/v1/knowledge/projects/{_PROJECT_ID}/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp_a1.status_code == 200, resp_a1.json()

    resp_a2 = client.post(
        f"/v1/knowledge/projects/{_PROJECT_ID}/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp_a2.status_code == 429

    # Different project_id → separate cooldown key → succeeds.
    resp_b = client.post(
        f"/v1/knowledge/projects/{other_project}/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp_b.status_code == 200, resp_b.json()
    # Regen helper fired exactly twice (A1 + B) — A2's 429 short-
    # circuited before the LLM path. Locks the ordering contract per
    # project endpoint: a regression moving the cooldown check after
    # the regen helper would make this count 3 rather than 2.
    assert mock_regen.await_count == 2


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_global_no_redis_skips_cooldown(mock_regen):
    """C2: when Redis isn't configured (cooldown client is None),
    back-to-back regens both succeed. Availability > abuse protection
    on hobby-scale Track 1 deploys without Redis."""
    mock_regen.return_value = RegenerationResult(
        status="regenerated", summary=_summary_stub()
    )
    client = _make_client(cooldown=None)

    for _ in range(3):
        resp = client.post(
            "/v1/knowledge/me/summary/regenerate",
            json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
        )
        assert resp.status_code == 200
    assert mock_regen.await_count == 3


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_cooldown_redis_error_degrades_to_no_cooldown(mock_regen):
    """C2: a Redis hiccup should NOT surface as a 500 to the user.
    Log + proceed. Catches the try/except inside _check_regen_cooldown."""
    mock_regen.return_value = RegenerationResult(
        status="regenerated", summary=_summary_stub()
    )
    client = _make_client(cooldown=_BoomRedis())

    resp = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp.status_code == 200, resp.json()
    assert mock_regen.await_count == 1


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_global_passes_trigger_manual(mock_regen):
    """C2: public edge forwards trigger='manual' so the counter series
    splits cleanly vs the K20.3 scheduler's 'scheduled' trigger."""
    mock_regen.return_value = RegenerationResult(
        status="regenerated", summary=_summary_stub()
    )
    client = _make_client()
    resp = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp.status_code == 200, resp.json()
    assert mock_regen.await_args.kwargs["trigger"] == "manual"


# ── /review-impl fixes ──────────────────────────────────────────────


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_cooldown_retry_after_floor_when_ttl_expired_mid_race(mock_regen):
    """/review-impl LOW-2: the defensive branch
    ``int(remaining) if remaining and remaining > 0 else 1`` fires when
    Redis TTL returns -2 because the key expired between SETNX=False
    and TTL read. FakeRedis's ``expired_keys`` mode forces that race
    so we can assert Retry-After floors at 1 (not 0 / negative / the
    full budget).

    A regression like ``retry_after = int(remaining)`` (dropping the
    floor) would return Retry-After=-2, violating RFC 7231 §7.1.3
    non-negative integer requirement.
    """
    mock_regen.return_value = RegenerationResult(
        status="regenerated", summary=_summary_stub()
    )
    # Pre-arm the FakeRedis with the key, but also flag it as expired
    # so TTL returns -2 on the 2nd call's read.
    uid = _TEST_USER
    expired_key = f"knowledge:regen:cooldown:{uid}:global:-"
    fake_redis = _FakeRedis(expired_keys={expired_key})
    fake_redis._store[expired_key] = 60  # pre-SETNX → 2nd call hits NX-fail branch
    client = _make_client(cooldown=fake_redis)

    resp = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp.status_code == 429
    retry_after = resp.headers["Retry-After"]
    assert int(retry_after) == 1, f"expected floor-to-1, got {retry_after}"


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_cooldown_ttl_exception_falls_back_to_full_budget(mock_regen):
    """/review-impl LOW-3: a regression removing the try/except around
    ``client.ttl(key)`` would crash when TTL reads hiccup. HalfBoomRedis
    succeeds on SET + DELETE but raises on TTL — assert we still return
    a well-formed 429 with the full-budget Retry-After fallback."""
    mock_regen.return_value = RegenerationResult(
        status="regenerated", summary=_summary_stub()
    )
    fake_redis = _HalfBoomRedis()
    # Pre-arm: first request's SETNX already happened in a prior call.
    # Inject directly into the store so the next endpoint call is the
    # "2nd" one — SETNX returns None, TTL raises, fallback fires.
    uid = _TEST_USER
    fake_redis._store[f"knowledge:regen:cooldown:{uid}:global:-"] = 60
    client = _make_client(cooldown=fake_redis)

    resp = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp.status_code == 429
    body = resp.json()
    assert body["detail"]["error_code"] == "regen_cooldown"
    # Fallback: full budget when TTL read raised.
    assert int(resp.headers["Retry-After"]) == 60


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_cooldown_released_on_provider_error(mock_regen):
    """/review-impl MED-1: ProviderError means the user's BYOK config
    is bad — they should retry immediately after fixing it, not wait
    60s. Locks that a 502 releases the cooldown so the next call can
    succeed without a 429.

    A regression that removed the `except ProviderError` release
    would leave the 2nd call 429'd instead of hitting the mock again
    (which now returns a happy result).
    """
    fake_redis = _FakeRedis()
    client = _make_client(cooldown=fake_redis)

    mock_regen.side_effect = ProviderUpstreamError("bad api key")
    resp_fail = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp_fail.status_code == 502

    # Cooldown key should have been deleted on failure.
    uid = _TEST_USER
    key = f"knowledge:regen:cooldown:{uid}:global:-"
    assert key not in fake_redis._store, "cooldown should have been released"

    # Now a successful retry goes through without 429.
    mock_regen.side_effect = None
    mock_regen.return_value = RegenerationResult(
        status="regenerated", summary=_summary_stub()
    )
    resp_ok = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp_ok.status_code == 200, resp_ok.json()


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_cooldown_released_on_server_side_exception(mock_regen):
    """/review-impl MED-1: a 500-class server-side fault (Neo4j down,
    pool exhausted, etc.) should also release the cooldown — punishing
    the user for our own bugs is bad UX. The same retry-immediately
    contract as ProviderError."""
    fake_redis = _FakeRedis()
    client = _make_client(cooldown=fake_redis)

    mock_regen.side_effect = RuntimeError("Neo4j driver not configured")
    resp_fail = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp_fail.status_code == 500

    uid = _TEST_USER
    key = f"knowledge:regen:cooldown:{uid}:global:-"
    assert key not in fake_redis._store, (
        "cooldown should be released after a server-side exception"
    )

    mock_regen.side_effect = None
    mock_regen.return_value = RegenerationResult(
        status="regenerated", summary=_summary_stub()
    )
    resp_ok = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp_ok.status_code == 200, resp_ok.json()


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_cooldown_stays_armed_on_business_outcomes(mock_regen):
    """/review-impl MED-1 counter-test: cooldown MUST stay armed when
    the regen helper returned a business status (edit-lock / guardrail /
    similarity / empty / regenerated) — those represent a completed
    attempt and subsequent calls within the window get 429 as
    designed. A regression releasing cooldown on 409/422 HTTPExceptions
    would break the primary anti-spam contract."""
    fake_redis = _FakeRedis()
    client = _make_client(cooldown=fake_redis)

    # First call hits user_edit_lock → 409 + RegenerationResult
    # returned by the helper (no exception raised to release the key).
    mock_regen.return_value = RegenerationResult(
        status="user_edit_lock", skipped_reason="recent manual edit"
    )
    resp_409 = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp_409.status_code == 409

    # Second call within 60s MUST be 429 — cooldown still armed.
    resp_429 = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp_429.status_code == 429, (
        "business outcomes must NOT release the cooldown"
    )
    assert mock_regen.await_count == 1
