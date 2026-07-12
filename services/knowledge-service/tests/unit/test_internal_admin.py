"""P3 D-P3-INDEX-PRUNE-ENDPOINT — unit tests for prune orphan
summary vector indexes admin endpoint.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db.neo4j_helpers import (
    drop_summary_index,
    parse_summary_index_name,
    summary_index_name,
)
from app.main import app


import os as _os

# Cycle 73f: pick up container env (compose sets dev_internal_token)
# AND host conftest setdefault (default_test_token). Same header works
# in both contexts.
_INTERNAL_TOKEN_HEADER = {
    "X-Internal-Token": _os.environ.get(
        "INTERNAL_SERVICE_TOKEN", "default_test_token",
    ),
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ── Parser unit tests ─────────────────────────────────────────────────


def test_parse_summary_index_name_round_trip_chapter():
    """parse(summary_index_name(...)) → matches input components."""
    proj = "abc12345-6789-abcd-ef01-234567890abc"
    emb = "deadbeef-0000-1111-2222-333344445555"
    name = summary_index_name(proj, emb, "chapter")
    out = parse_summary_index_name(name)
    assert out == {
        "level": "chapter",
        "project_id": proj.replace("-", "").lower(),
        "embedding_model_uuid": emb.replace("-", "").lower(),
    }


def test_parse_summary_index_name_round_trip_part_book():
    """Both `part` and `book` levels round-trip too — locks the regex
    in lockstep with `_SUMMARY_LEVELS`."""
    proj = "11111111-1111-1111-1111-111111111111"
    emb = "22222222-2222-2222-2222-222222222222"
    for level in ("part", "book"):
        out = parse_summary_index_name(summary_index_name(proj, emb, level))
        assert out is not None
        assert out["level"] == level


def test_parse_summary_index_name_rejects_non_summary():
    """Non-P3 indexes (entity-emb, glossary-emb, raw text) → None.

    Critical safety property: the prune endpoint relies on this to
    avoid DROP-ing unrelated indexes when SHOW returns the full list.
    """
    for bad in [
        "chapter_emb_p123_e456",                    # missing _summary_ infix
        "ent_emb_idx_001",                          # entity index
        "chapter_summary_emb_p123_e456",            # wrong hex length
        "chapter_summary_emb_pXXX_e" + "f" * 32,    # non-hex
        "weird_summary_emb_p" + "0" * 32 + "_e" + "0" * 32,  # bad level
        "",
    ]:
        assert parse_summary_index_name(bad) is None, f"should reject: {bad!r}"


# ── drop_summary_index guard ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_drop_summary_index_rejects_non_summary_name():
    """Defense-in-depth: drop helper refuses non-summary index names so
    a caller bug can't accidentally DROP an entity-embedding index."""
    session = MagicMock()
    session.run = AsyncMock()
    with pytest.raises(ValueError, match="non-summary"):
        await drop_summary_index(session, "entity_emb_idx_001")
    session.run.assert_not_called()


@pytest.mark.asyncio
async def test_drop_summary_index_uses_if_exists():
    """Idempotency check — the cypher must use IF EXISTS so concurrent
    drops don't error."""
    session = MagicMock()
    session.run = AsyncMock()
    proj = "0" * 32
    emb = "f" * 32
    name = f"chapter_summary_emb_p{proj}_e{emb}"
    await drop_summary_index(session, name)
    session.run.assert_awaited_once()
    cypher = session.run.await_args.args[0]
    assert "IF EXISTS" in cypher
    assert name in cypher


# ── Endpoint tests ─────────────────────────────────────────────────────


def _make_neo4j_session_with_indexes(index_rows: list[dict]):
    """Build a MagicMock that behaves like neo4j_session() context manager
    returning a session whose `run()` returns an async-iterable of records.

    `index_rows` is the list of {name: str, ...} dicts SHOW VECTOR INDEXES
    will yield.
    """
    async def _run(_cypher, **_kwargs):
        if _cypher.startswith("SHOW VECTOR INDEXES"):
            class _AsyncIter:
                def __init__(self, rows):
                    self._rows = rows
                def __aiter__(self):
                    self._iter = iter(self._rows)
                    return self
                async def __anext__(self):
                    try:
                        return next(self._iter)
                    except StopIteration:
                        raise StopAsyncIteration
            return _AsyncIter(index_rows)
        # DROP / other queries — return a benign awaitable result.
        return MagicMock()

    session = MagicMock()
    session.run = AsyncMock(side_effect=_run)

    # neo4j_session() is an async context manager.
    class _Ctx:
        async def __aenter__(self):
            return session
        async def __aexit__(self, *_a):
            return None

    return _Ctx(), session


def _patch_pool_with_projects(project_rows: list[dict]) -> AsyncMock:
    """Mock the asyncpg pool.fetch to return the given knowledge_projects
    rows (each {proj_hex, emb_hex})."""
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=project_rows)
    return pool


def test_prune_endpoint_requires_internal_token(client: TestClient):
    resp = client.post("/internal/admin/summary-indexes/prune")
    assert resp.status_code == 401


def test_prune_endpoint_empty_neo4j_returns_zero(client: TestClient):
    """No summary indexes at all → empty response, no pool call."""
    ctx, _ = _make_neo4j_session_with_indexes([])
    with patch(
        "app.routers.internal_admin.neo4j_session",
        return_value=ctx,
    ):
        resp = client.post(
            "/internal/admin/summary-indexes/prune",
            headers=_INTERNAL_TOKEN_HEADER,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {
        "dry_run": True,
        "total_summary_indexes": 0,
        "orphan_indexes": [],
        "dropped_count": 0,
    }


def test_prune_dry_run_lists_orphans_without_dropping(client: TestClient):
    """Default dry_run=true: returns orphans, calls only SHOW (no DROP).

    Setup: 3 indexes (chapter level, 3 different projects).
      - proj A: matches current model → KEEP
      - proj B: project's embedding_model differs → orphan (changed)
      - proj C: project deleted (no row) → orphan (project_deleted)
    """
    proj_a = "a" * 32
    proj_b = "b" * 32
    proj_c = "c" * 32
    emb_old = "0" * 32
    emb_a_current = "0" * 32  # matches old → A is active
    emb_b_current = "1" * 32  # different → B is orphan

    index_rows = [
        {"name": f"chapter_summary_emb_p{proj_a}_e{emb_old}"},
        {"name": f"chapter_summary_emb_p{proj_b}_e{emb_old}"},
        {"name": f"chapter_summary_emb_p{proj_c}_e{emb_old}"},
    ]
    ctx, session = _make_neo4j_session_with_indexes(index_rows)
    pool = _patch_pool_with_projects([
        {"proj_hex": proj_a, "emb_hex": emb_a_current},
        {"proj_hex": proj_b, "emb_hex": emb_b_current},
        # proj_c absent → project_deleted
    ])

    with patch(
        "app.routers.internal_admin.neo4j_session", return_value=ctx,
    ), patch(
        "app.routers.internal_admin.get_knowledge_pool", return_value=pool,
    ):
        resp = client.post(
            "/internal/admin/summary-indexes/prune",
            headers=_INTERNAL_TOKEN_HEADER,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dry_run"] is True
    assert body["total_summary_indexes"] == 3
    assert body["dropped_count"] == 0
    orphans = {o["project_id"]: o for o in body["orphan_indexes"]}
    assert set(orphans.keys()) == {proj_b, proj_c}
    assert orphans[proj_b]["reason"] == "embedding_model_changed"
    assert orphans[proj_c]["reason"] == "project_deleted"

    # SHOW VECTOR INDEXES was invoked but NO DROP cypher.
    cyphers = [c.args[0] for c in session.run.await_args_list]
    assert any(c.startswith("SHOW VECTOR INDEXES") for c in cyphers)
    assert not any(c.startswith("DROP INDEX") for c in cyphers)


def test_prune_non_dry_run_drops_orphans(client: TestClient):
    """dry_run=false: orphans DROPped via Cypher, dropped_count matches."""
    proj_orphan = "d" * 32
    emb_stale = "0" * 32
    index_rows = [
        {"name": f"book_summary_emb_p{proj_orphan}_e{emb_stale}"},
    ]
    ctx, session = _make_neo4j_session_with_indexes(index_rows)
    pool = _patch_pool_with_projects([])  # project deleted

    with patch(
        "app.routers.internal_admin.neo4j_session", return_value=ctx,
    ), patch(
        "app.routers.internal_admin.get_knowledge_pool", return_value=pool,
    ):
        resp = client.post(
            "/internal/admin/summary-indexes/prune?dry_run=false",
            headers=_INTERNAL_TOKEN_HEADER,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dry_run"] is False
    assert body["total_summary_indexes"] == 1
    assert body["dropped_count"] == 1
    assert len(body["orphan_indexes"]) == 1

    # DROP cypher must have fired with the orphan's name.
    drop_calls = [
        c for c in session.run.await_args_list
        if c.args[0].startswith("DROP INDEX")
    ]
    assert len(drop_calls) == 1
    assert f"book_summary_emb_p{proj_orphan}_e{emb_stale}" in drop_calls[0].args[0]


def test_prune_classifies_unset_embedding_model_distinctly(client: TestClient):
    """A project that exists but has embedding_model=NULL → reason
    'project_model_unset' (distinct from project_deleted + changed)."""
    proj = "e" * 32
    emb_stale = "0" * 32
    index_rows = [
        {"name": f"part_summary_emb_p{proj}_e{emb_stale}"},
    ]
    ctx, _ = _make_neo4j_session_with_indexes(index_rows)
    pool = _patch_pool_with_projects([
        {"proj_hex": proj, "emb_hex": None},  # column is NULL
    ])
    with patch(
        "app.routers.internal_admin.neo4j_session", return_value=ctx,
    ), patch(
        "app.routers.internal_admin.get_knowledge_pool", return_value=pool,
    ):
        resp = client.post(
            "/internal/admin/summary-indexes/prune",
            headers=_INTERNAL_TOKEN_HEADER,
        )
    body = resp.json()
    assert len(body["orphan_indexes"]) == 1
    assert body["orphan_indexes"][0]["reason"] == "project_model_unset"


def test_prune_ignores_non_summary_indexes(client: TestClient):
    """If SHOW VECTOR INDEXES returns non-summary indexes, the parser
    filters them out — they're never classified or dropped."""
    proj = "f" * 32
    emb = "0" * 32
    index_rows = [
        # The one summary index — active model, will be kept.
        {"name": f"chapter_summary_emb_p{proj}_e{emb}"},
        # Non-summary vector indexes — must be IGNORED entirely.
        {"name": "entity_name_emb_idx_001"},
        {"name": "glossary_embedding_idx"},
    ]
    ctx, _ = _make_neo4j_session_with_indexes(index_rows)
    pool = _patch_pool_with_projects([
        {"proj_hex": proj, "emb_hex": emb},
    ])
    with patch(
        "app.routers.internal_admin.neo4j_session", return_value=ctx,
    ), patch(
        "app.routers.internal_admin.get_knowledge_pool", return_value=pool,
    ):
        resp = client.post(
            "/internal/admin/summary-indexes/prune",
            headers=_INTERNAL_TOKEN_HEADER,
        )
    body = resp.json()
    # Only the summary index was counted (entity + glossary filtered out).
    assert body["total_summary_indexes"] == 1
    # And it matches current model → no orphans.
    assert body["orphan_indexes"] == []


# ─────────────────────────────────────────────────────────────────────
# Cycle 73f — /internal/admin/precision-filter/reload
# ─────────────────────────────────────────────────────────────────────


import os

# Container env can override `default_test_token` (e.g. compose sets
# INTERNAL_SERVICE_TOKEN=dev_internal_token). Read at test time so both
# host pytest + container pytest pass without env-fiddling.
_C73F_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "default_test_token")
_C73F_HEADER = {"X-Internal-Token": _C73F_TOKEN}


def _counter_value(source: str, outcome: str) -> float:
    from app.metrics import knowledge_extraction_filter_reload_total
    return knowledge_extraction_filter_reload_total.labels(
        source=source, outcome=outcome,
    )._value.get()


def test_filter_reload_requires_internal_token(client: TestClient):
    """Auth: no X-Internal-Token header → 401."""
    resp = client.post(
        "/internal/admin/precision-filter/reload",
        json={"model_ref": "x"},
    )
    assert resp.status_code == 401


def test_filter_reload_sets_config_from_body(client: TestClient):
    """Happy path: model_ref + categories override env defaults; Redis
    set_filter_config + local set_precision_filter_config both fire."""
    mock_redis = MagicMock()
    mock_redis.set = AsyncMock()
    mock_redis.publish = AsyncMock()
    mock_redis.aclose = AsyncMock()

    pre_applied = _counter_value("api", "applied")

    with patch(
        "app.routers.internal_admin.aioredis.from_url",
        return_value=mock_redis,
    ), patch(
        "app.extraction.pass2_orchestrator.set_precision_filter_config",
        side_effect=lambda cfg: cfg,  # echo input so endpoint can asdict() it
    ) as mock_set_local:
        resp = client.post(
            "/internal/admin/precision-filter/reload",
            headers=_INTERNAL_TOKEN_HEADER,
            json={
                "model_ref": "claude-uuid",
                "partial_policy": "drop",
                "categories": ["relation", "event"],
            },
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["redis_publish_status"] == "published"
    assert body["knowledge_service_config"]["model_ref"] == "claude-uuid"
    assert body["knowledge_service_config"]["categories"] == ["relation", "event"]
    assert body["knowledge_service_config"]["partial_policy"] == "drop"
    assert "T" in body["reloaded_at"]  # ISO8601 server-generated

    mock_redis.set.assert_called_once()
    mock_redis.publish.assert_called_once()
    mock_set_local.assert_called_once()
    assert _counter_value("api", "applied") == pre_applied + 1


def test_filter_reload_disable_true_reverts_to_env_config(client: TestClient):
    """Cycle 74b: disable=true is a clear-the-override op — Redis DELETE +
    local cache reverts to ENV config (NOT None) when a filter env is set,
    matching startup-hydrate + pubsub semantics. Closes the cycle-73f
    live-smoke finding (runtime set None while restart reloaded env)."""
    from loreweave_extraction import PrecisionFilterConfig

    env_config = PrecisionFilterConfig(
        model_ref="env-filter-uuid",
        categories=("relation",),
        partial_policy="drop",
    )

    mock_redis = MagicMock()
    mock_redis.delete = AsyncMock(return_value=1)
    mock_redis.publish = AsyncMock()
    mock_redis.aclose = AsyncMock()

    with patch(
        "app.routers.internal_admin.aioredis.from_url",
        return_value=mock_redis,
    ), patch(
        "app.extraction.pass2_orchestrator._load_precision_filter_config",
        return_value=env_config,
    ), patch(
        "app.extraction.pass2_orchestrator.set_precision_filter_config",
        side_effect=lambda cfg: cfg,  # echo input so endpoint can asdict() it
    ) as mock_set_local:
        resp = client.post(
            "/internal/admin/precision-filter/reload",
            headers=_INTERNAL_TOKEN_HEADER,
            json={"disable": True},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Reverted to env config, NOT None.
    assert body["knowledge_service_config"]["model_ref"] == "env-filter-uuid"
    assert body["knowledge_service_config"]["categories"] == ["relation"]
    assert body["redis_publish_status"] == "published"
    mock_redis.delete.assert_called_once()
    mock_set_local.assert_called_once_with(env_config)


def test_filter_reload_disable_true_none_when_no_filter_env(client: TestClient):
    """Cycle 74b: disable=true with NO filter env set → env config is itself
    None → local cache None + response config null. The genuinely-no-filter
    deployment still ends disabled (the env-revert rule is uniform)."""
    mock_redis = MagicMock()
    mock_redis.delete = AsyncMock(return_value=1)
    mock_redis.publish = AsyncMock()
    mock_redis.aclose = AsyncMock()

    with patch(
        "app.routers.internal_admin.aioredis.from_url",
        return_value=mock_redis,
    ), patch(
        "app.extraction.pass2_orchestrator._load_precision_filter_config",
        return_value=None,
    ), patch(
        "app.extraction.pass2_orchestrator.set_precision_filter_config",
        side_effect=lambda cfg: cfg,  # echo input so endpoint can asdict() it
    ) as mock_set_local:
        resp = client.post(
            "/internal/admin/precision-filter/reload",
            headers=_INTERNAL_TOKEN_HEADER,
            json={"disable": True},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["knowledge_service_config"] is None
    assert body["redis_publish_status"] == "published"
    mock_redis.delete.assert_called_once()
    mock_set_local.assert_called_once_with(None)


def test_filter_reload_both_disable_and_model_ref_returns_422(client: TestClient):
    """r1 H2 fold: disable=true AND model_ref both set → ambiguous → 422."""
    resp = client.post(
        "/internal/admin/precision-filter/reload",
        headers=_INTERNAL_TOKEN_HEADER,
        json={"disable": True, "model_ref": "x"},
    )
    assert resp.status_code == 422


def test_filter_reload_empty_body_returns_422(client: TestClient):
    """r1 H5 fold: no field set → 422 (no implicit fall-through)."""
    resp = client.post(
        "/internal/admin/precision-filter/reload",
        headers=_INTERNAL_TOKEN_HEADER,
        json={},
    )
    assert resp.status_code == 422


def test_filter_reload_redis_publish_failure_returns_status_failed(client: TestClient):
    """r1 H4 fold: Redis SET fails → 200 with redis_publish_status='failed'.
    Local cache still applied; counter bumps 'failed' outcome."""
    mock_redis = MagicMock()
    mock_redis.set = AsyncMock(side_effect=RuntimeError("redis down"))
    mock_redis.aclose = AsyncMock()

    pre_failed = _counter_value("api", "failed")
    pre_applied = _counter_value("api", "applied")

    with patch(
        "app.routers.internal_admin.aioredis.from_url",
        return_value=mock_redis,
    ), patch(
        "app.extraction.pass2_orchestrator.set_precision_filter_config",
        side_effect=lambda cfg: cfg,  # echo input so endpoint can asdict() it
    ) as mock_set_local:
        resp = client.post(
            "/internal/admin/precision-filter/reload",
            headers=_INTERNAL_TOKEN_HEADER,
            json={"model_ref": "x"},
        )

    assert resp.status_code == 200  # NOT 502 per H4 fold; ops must check status field
    body = resp.json()
    assert body["redis_publish_status"] == "failed"
    # Local cache STILL applied (cycle 73f intentional — KS reflects new config
    # even if propagation to workers fails; ops sees drift via status field).
    mock_set_local.assert_called_once()
    # r3 M1 fold: BOTH counter outcomes fire additively for the redis-failed
    # branch. `failed` records the publish error; `applied` records the
    # successful local-apply. Dashboards summing outcomes = total attempts.
    assert _counter_value("api", "failed") == pre_failed + 1
    assert _counter_value("api", "applied") == pre_applied + 1


def test_filter_reload_invalid_max_items_per_batch_returns_422(client: TestClient):
    """Pydantic Field(ge=1) catches bad value BEFORE PrecisionFilterConfig
    construction (r1 M2 fold)."""
    resp = client.post(
        "/internal/admin/precision-filter/reload",
        headers=_INTERNAL_TOKEN_HEADER,
        json={"model_ref": "x", "max_items_per_batch": 0},
    )
    assert resp.status_code == 422


# ── WS-2.2 (structured s/p/o) — the semantic dedup key ─────────────────────────
# The distiller re-runs on every "End my day" at temperature > 0, so it re-phrases the SAME fact
# across runs. A text-only dedup key drifts with wording (double-queues); the structured s/p/o key
# is stable, so a re-phrased-but-same fact collides. These prove the helper directly (pure fn).

from app.routers.internal_admin import _DiaryFactIn, _diary_fact_dedup_key  # noqa: E402


def _fact(**kw):
    kw.setdefault("kind", "decision")
    kw.setdefault("text", "")
    return _DiaryFactIn(**kw)


_D = "2026-06-15"  # a shared day for the within-day dedup tests


def test_dedup_key_is_stable_across_text_rephrasing_when_spo_present():
    # Same subject/predicate/object + SAME day, DIFFERENT free text + case/whitespace → SAME key.
    a = _fact(text="Minh froze the Q3 budget until billing ships.",
              subject="Minh", predicate="froze", object="the Q3 budget")
    b = _fact(text="The Q3 budget was frozen by Minh pending the billing revamp.",
              subject="  minh ", predicate="FROZE", object="The  Q3   Budget")
    k1 = _diary_fact_dedup_key("proj-1", a.kind, a.text.strip(), a, _D)
    k2 = _diary_fact_dedup_key("proj-1", b.kind, b.text.strip(), b, _D)
    assert k1 == k2, "a re-phrasing of the same s/p/o fact on the same day must dedup"


def test_dedup_key_is_per_day():
    # audit MED-2: the SAME s/p/o on TWO different days is a DISTINCT fact (a re-affirmation isn't
    # dropped; a Monday reject doesn't tombstone Friday's). Different day → different key.
    a = _fact(subject="Alice", predicate="said", object="the budget is frozen")
    assert _diary_fact_dedup_key("p", "decision", "x", a, "2026-06-15") != \
           _diary_fact_dedup_key("p", "decision", "x", a, "2026-06-19")


def test_dedup_key_differs_for_different_object():
    a = _fact(subject="Minh", predicate="froze", object="the Q3 budget")
    b = _fact(subject="Minh", predicate="froze", object="the Q4 budget")
    assert _diary_fact_dedup_key("p", "decision", "x", a, _D) != _diary_fact_dedup_key("p", "decision", "x", b, _D)


def test_dedup_key_is_project_scoped():
    a = _fact(subject="Minh", predicate="froze", object="the Q3 budget")
    assert _diary_fact_dedup_key("proj-1", "decision", "x", a, _D) != _diary_fact_dedup_key("proj-2", "decision", "x", a, _D)


def test_dedup_key_falls_back_to_text_when_no_spo():
    # No structured trio → key on (kind, text). Same text → same; different text → different (same day).
    a = _fact(kind="event", text="Shipped the release.")
    b = _fact(kind="event", text="Shipped the release.")
    c = _fact(kind="event", text="Something else entirely.")
    assert _diary_fact_dedup_key("p", a.kind, a.text, a, _D) == _diary_fact_dedup_key("p", b.kind, b.text, b, _D)
    assert _diary_fact_dedup_key("p", a.kind, a.text, a, _D) != _diary_fact_dedup_key("p", c.kind, c.text, c, _D)


def test_dedup_key_text_fallback_when_subject_but_no_object():
    # A partial trio (subject only, no object) is NOT enough to anchor — fall back to text so we don't
    # collide two unrelated subject-only facts under an empty-object key.
    a = _fact(text="A", subject="Minh")
    b = _fact(text="B", subject="Minh")
    assert _diary_fact_dedup_key("p", "decision", "A", a, _D) != _diary_fact_dedup_key("p", "decision", "B", b, _D)


def test_parse_iso_date_tolerates_garbage_and_none():
    from datetime import date as _date
    from app.routers.internal_admin import _parse_iso_date
    assert _parse_iso_date("2026-07-12") == _date(2026, 7, 12)
    assert _parse_iso_date("2026-07-12T09:30:00Z") == _date(2026, 7, 12)  # datetime → date part
    assert _parse_iso_date(None) is None
    assert _parse_iso_date("") is None
    assert _parse_iso_date("not-a-date") is None
