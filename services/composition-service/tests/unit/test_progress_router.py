"""LOOM T4.2 — writing-progress router tests (TestClient + overrides).

Covers the shaping logic that has no DB (streak walk-back, dense sparkline, goal
coercion, local-date parsing) plus the GET/POST endpoints against a stub repo. The
SQL snapshot-differencing itself is exercised in the integration repo tests.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.db.models import CompositionWork
from app.db.repositories.daily_progress import ProgressAggregate
from app.routers.progress import (
    _coerce_goal,
    _current_streak,
    _parse_local_date,
    _sparkline,
)

USER = uuid.uuid4()
BOOK = uuid.uuid4()
PROJECT = uuid.uuid4()
CHAPTER = uuid.uuid4()


def _work(settings=None) -> CompositionWork:
    return CompositionWork(
        project_id=PROJECT, created_by=USER, book_id=BOOK, id=uuid.uuid4(),
        version=1, status="active", settings=settings or {},
    )


class StubWorks:
    def __init__(self, work=None):
        self.work = work

    async def get(self, project_id):
        return self.work


class StubProgress:
    def __init__(self, agg=None, goal=None):
        self.agg = agg or ProgressAggregate()
        self.goal = goal  # BE-P2 — the per-user daily goal (composition_progress_goal), None = unset
        self.reported: list[tuple] = []
        self.baselined: list[tuple] = []

    async def read_aggregate(self, user_id, project_id, on_or_before):
        return self.agg

    async def get_goal(self, user_id, project_id):
        # mirrors DailyProgressRepo.get_goal — the router reads this before the legacy fallback
        return self.goal

    async def set_goal(self, user_id, project_id, goal):
        self.goal = goal

    async def report(self, user_id, project_id, chapter_id, words, snapshot_date):
        self.reported.append((chapter_id, words, snapshot_date))

    async def ensure_baseline(self, user_id, project_id, chapter_id, words):
        self.baselined.append((chapter_id, words))


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())
    from app.main import app
    from app.deps import get_daily_progress_repo, get_grant_client_dep, get_works_repo
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_current_user

    # E0 book-grant authority stubbed at OWNER (the gate's deny paths live in
    # test_grant_gate); the router now resolves the Work's book then gates VIEW.
    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER
        async def resolve_access(self, book_id, user_id):
            return GrantLevel.OWNER, "active"

    works, progress = StubWorks(_work()), StubProgress()
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_works_repo] = lambda: works
    app.dependency_overrides[get_daily_progress_repo] = lambda: progress
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    with TestClient(app) as c:
        yield c, works, progress
    app.dependency_overrides.clear()


# ── pure helpers ──

def test_streak_counts_today_back_to_first_gap():
    today = date(2026, 6, 24)
    dw = {date(2026, 6, 24): 300, date(2026, 6, 23): 100, date(2026, 6, 22): 50,
          # gap on the 21st
          date(2026, 6, 20): 10}
    assert _current_streak(dw, today) == 3


def test_streak_alive_from_yesterday_when_today_empty():
    today = date(2026, 6, 24)
    dw = {date(2026, 6, 23): 100, date(2026, 6, 22): 50}
    assert _current_streak(dw, today) == 2  # not yet written today, but streak holds


def test_streak_zero_when_neither_today_nor_yesterday():
    today = date(2026, 6, 24)
    dw = {date(2026, 6, 22): 50, date(2026, 6, 21): 50}
    assert _current_streak(dw, today) == 0


def test_sparkline_is_dense_30_days_zero_filled_ascending():
    today = date(2026, 6, 24)
    spark = _sparkline({date(2026, 6, 24): 7, date(2026, 6, 20): 3}, today)
    assert len(spark) == 30
    assert spark[-1] == {"date": "2026-06-24", "words": 7}
    assert spark[0]["date"] == "2026-05-26"  # today-29
    # a day with no writing is zero-filled, not missing
    assert {"date": "2026-06-23", "words": 0} in spark


def test_coerce_goal_only_positive_int():
    assert _coerce_goal({"daily_goal": 500}) == 500
    assert _coerce_goal({"daily_goal": 0}) is None
    assert _coerce_goal({"daily_goal": -5}) is None
    assert _coerce_goal({"daily_goal": True}) is None  # bool is not a goal
    assert _coerce_goal({"daily_goal": "500"}) is None
    assert _coerce_goal({}) is None


def test_parse_local_date_rejects_bad_format():
    from fastapi import HTTPException
    assert _parse_local_date("2026-06-24") == date(2026, 6, 24)
    with pytest.raises(HTTPException) as ei:
        _parse_local_date("06/24/2026")
    assert ei.value.status_code == 422


# ── endpoints ──

def test_get_progress_shapes_response(ctx):
    client, works, progress = ctx
    works.work = _work(settings={"daily_goal": 400})
    progress.agg = ProgressAggregate(
        day_words=[(date(2026, 6, 23), 100), (date(2026, 6, 24), 250)],
        book_total=1350,
    )
    r = client.get(f"/v1/composition/works/{PROJECT}/progress", params={"today": "2026-06-24"})
    assert r.status_code == 200
    body = r.json()
    assert body["today"] == "2026-06-24"
    assert body["today_words"] == 250
    assert body["book_total"] == 1350
    assert body["daily_goal"] == 400
    assert body["current_streak"] == 2
    assert len(body["sparkline"]) == 30


def test_the_PER_USER_goal_wins_over_the_legacy_work_setting(ctx):
    # BE-P2 — the per-user composition_progress_goal shadows the legacy shared work.settings.daily_goal,
    # and the response surfaces the source tier (SET-1). This exercises the get_goal path the stale stub
    # broke (C1).
    client, works, progress = ctx
    works.work = _work(settings={"daily_goal": 400})  # legacy shared
    progress.goal = 750                                # the caller's own per-user goal
    r = client.get(f"/v1/composition/works/{PROJECT}/progress", params={"today": "2026-06-24"})
    assert r.status_code == 200
    body = r.json()
    assert body["daily_goal"] == 750                   # per-user WINS
    assert body.get("daily_goal_source") == "user"     # and the source tier is surfaced


def test_get_progress_404_on_unknown_work(ctx):
    client, works, _ = ctx
    works.work = None
    r = client.get(f"/v1/composition/works/{PROJECT}/progress", params={"today": "2026-06-24"})
    assert r.status_code == 404


def test_get_progress_requires_today_param(ctx):
    client, _, _ = ctx
    r = client.get(f"/v1/composition/works/{PROJECT}/progress")
    assert r.status_code == 422


def test_report_upserts_snapshot(ctx):
    client, _, progress = ctx
    r = client.post(
        f"/v1/composition/works/{PROJECT}/progress/report",
        json={"chapter_id": str(CHAPTER), "words": 1200, "date": "2026-06-24"},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "date": "2026-06-24", "words": 1200}
    assert progress.reported == [(CHAPTER, 1200, date(2026, 6, 24))]


def test_report_rejects_bad_date(ctx):
    client, _, progress = ctx
    r = client.post(
        f"/v1/composition/works/{PROJECT}/progress/report",
        json={"chapter_id": str(CHAPTER), "words": 10, "date": "not-a-date"},
    )
    assert r.status_code == 422
    assert progress.reported == []


def test_report_rejects_negative_words(ctx):
    client, _, _ = ctx
    r = client.post(
        f"/v1/composition/works/{PROJECT}/progress/report",
        json={"chapter_id": str(CHAPTER), "words": -1, "date": "2026-06-24"},
    )
    assert r.status_code == 422


def test_report_404_on_unknown_work(ctx):
    client, works, progress = ctx
    works.work = None
    r = client.post(
        f"/v1/composition/works/{PROJECT}/progress/report",
        json={"chapter_id": str(CHAPTER), "words": 10, "date": "2026-06-24"},
    )
    assert r.status_code == 404
    assert progress.reported == []


def test_report_rejects_out_of_range_words(ctx):
    client, _, progress = ctx
    r = client.post(
        f"/v1/composition/works/{PROJECT}/progress/report",
        json={"chapter_id": str(CHAPTER), "words": 5_000_001, "date": "2026-06-24"},
    )
    assert r.status_code == 422
    assert progress.reported == []


def test_baseline_records_chapter_count(ctx):
    client, _, progress = ctx
    r = client.post(
        f"/v1/composition/works/{PROJECT}/progress/baseline",
        json={"chapter_id": str(CHAPTER), "words": 5000},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert progress.baselined == [(CHAPTER, 5000)]


def test_baseline_404_on_unknown_work(ctx):
    client, works, progress = ctx
    works.work = None
    r = client.post(
        f"/v1/composition/works/{PROJECT}/progress/baseline",
        json={"chapter_id": str(CHAPTER), "words": 5000},
    )
    assert r.status_code == 404
    assert progress.baselined == []


def test_baseline_rejects_negative_words(ctx):
    client, _, progress = ctx
    r = client.post(
        f"/v1/composition/works/{PROJECT}/progress/baseline",
        json={"chapter_id": str(CHAPTER), "words": -1},
    )
    assert r.status_code == 422
    assert progress.baselined == []
