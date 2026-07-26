"""K25 (2026-07-24) — OUT-5: composition_arc_template_list must not silently truncate.

It returned only `{"arc_templates": [...capped slice...], "scope": ...}`: no total, no
`more` flag. A caller with 31 templates asking `limit=5` read the result as "you have 5
templates" — a silent truncation, the exact failure OUT-5 forbids.

Fixed with the fetch-`limit+1` trick the sibling `kg_project_list` already uses ("the repo
fetches limit+1 to signal `more`"): honest without a second COUNT round-trip.

Tool-level unit tests (mocked repo), mirroring test_motif_mcp's `_patched`/`_Ctx`.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

TEST_USER = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


class _Ctx:
    def __init__(self, user_id=TEST_USER):
        self.user_id = user_id
        self.session_id = "sess-1"
        self.project_id = None
        self.trace_id = None
        self.internal_token = "tok"


def _arc(**kw):
    from app.db.models import ArcTemplate

    base = dict(
        id=uuid.uuid4(), owner_user_id=TEST_USER, code=f"arc.{uuid.uuid4().hex[:6]}",
        name="An Arc",
    )
    base.update(kw)
    return ArcTemplate(**base)


async def _call_with_repo_returning(n_rows: int, *, limit: int):
    """Drive composition_arc_template_list with a repo that returns `n_rows` rows, capturing
    the `limit` the tool actually asked the repo for."""
    import app.mcp.server as srv

    seen_limit = {}

    async def list_for_caller(caller_id, *, limit, **kw):
        seen_limit["limit"] = limit
        return [_arc() for _ in range(n_rows)]

    repo = AsyncMock()
    repo.list_for_caller = AsyncMock(side_effect=list_for_caller)

    with patch.object(srv, "_ctx", side_effect=lambda ctx: ctx), \
         patch.object(srv, "get_pool", return_value=object()), \
         patch.object(srv, "ArcTemplateRepo", return_value=repo):
        res = await srv.composition_arc_template_list(_Ctx(), scope="all", limit=limit)
    return res, seen_limit["limit"]


@pytest.mark.asyncio
async def test_fetches_one_more_than_the_cap_to_detect_overflow():
    # The whole mechanism: to know if there is a 6th, ask for 6.
    _res, asked = await _call_with_repo_returning(3, limit=5)
    assert asked == 6, "must fetch limit+1 to detect a further page without a COUNT"


@pytest.mark.asyncio
async def test_reports_more_true_and_trims_to_the_cap_when_capped():
    # Repo returns limit+1 → there IS more; the tool must trim to `limit` AND flag it.
    res, _ = await _call_with_repo_returning(6, limit=5)
    assert len(res["arc_templates"]) == 5, "must not leak the probe row past the cap"
    assert res["returned"] == 5
    assert res["more"] is True, (
        "a capped list that dropped rows must say so — else the agent reads it as complete"
    )
    assert "more exist" in res["guidance"].lower()


@pytest.mark.asyncio
async def test_reports_more_false_when_everything_fits():
    # Repo returns <= limit → complete; the tool must AFFIRMATIVELY say so.
    res, _ = await _call_with_repo_returning(3, limit=5)
    assert len(res["arc_templates"]) == 3
    assert res["returned"] == 3
    assert res["more"] is False
    assert "complete" in res["guidance"].lower()


@pytest.mark.asyncio
async def test_exactly_full_page_is_not_falsely_flagged():
    # Boundary: exactly `limit` real rows exist. limit+1 fetch returns `limit` (no extra), so
    # `more` must be False — off-by-one here would nag the agent to page an empty next page.
    res, _ = await _call_with_repo_returning(5, limit=5)
    assert len(res["arc_templates"]) == 5
    assert res["more"] is False
