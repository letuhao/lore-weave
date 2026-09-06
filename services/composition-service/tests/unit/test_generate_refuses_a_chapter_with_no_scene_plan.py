"""D-APPROVE-THEN-FAIL, chapter target — composition_generate carded chapters it never checked.

Measured 2026-08-24 over MCP: a chapter_id that does not exist, and a chapter belonging to a
DIFFERENT book, both minted a cost-bearing confirm card. The SCENE target has always been
validated at propose (and the source argues for it); the CHAPTER target deliberately was not,
because the check was believed to need book-service.

It does not. The engine's own chapter path refuses `NO_CHAPTER_PLAN` when
`scenes_for_chapter(project_id, chapter_id)` is empty, so non-empty scenes is a necessary
precondition of the whole operation — a LOCAL, project-scoped query. Checking it at propose
refuses exactly what the confirm would refuse, before the author approves a spend.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.mcp.server as srv

PROJECT = "dddddddd-dddd-dddd-dddd-dddddddddddd"
CHAPTER = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"


class _Ctx:
    user_id = None
    session_id = "s"
    project_id = None
    trace_id = None
    internal_token = "t"


def _args(**kw):
    base = dict(project_id=PROJECT, model_source="user_model", model_ref=MODEL,
                chapter_id=CHAPTER)
    base.update(kw)
    return srv._GenerateArgs(**base)


def _patched(scenes):
    """Only the scene-plan lookup varies; everything before it is stubbed."""
    outline = MagicMock()
    outline.return_value.scenes_for_chapter = AsyncMock(return_value=scenes)
    meta = MagicMock(book_id=PROJECT, project_id=PROJECT)
    return (patch.object(srv, "_ctx", MagicMock(return_value=MagicMock(user_id=None))),
            patch.object(srv, "get_pool", MagicMock()),
            patch.object(srv, "WorksRepo", MagicMock()),
            patch.object(srv, "_book_or_deny", AsyncMock(return_value=meta)),
            patch.object(srv, "_require_project", MagicMock(return_value=PROJECT)),
            patch.object(srv, "OutlineRepo", outline))


async def _call(scenes, **kw):
    a, b, c, d, e, f = _patched(scenes)
    with a, b, c, d, e, f:
        return await srv.composition_generate(_Ctx(), _args(**kw))


async def test_a_chapter_with_no_scene_plan_is_refused_at_propose():
    """The measured defect: an absent chapter, and a chapter of another book, both have no
    scenes IN THIS PROJECT — one predicate covers both."""
    with pytest.raises(ValueError, match="no scene plan"):
        await _call(scenes=[])


async def test_the_refusal_says_what_to_do_about_it():
    """A refusal the model cannot act on becomes a retry of the same call."""
    with pytest.raises(ValueError) as e:
        await _call(scenes=[])
    msg = str(e.value)
    assert "decompose" in msg, "the remedy is not named"
    assert "outline_node_id" in msg, "the single-scene alternative is not offered"


async def test_a_chapter_WITH_a_scene_plan_is_not_refused_by_this_check():
    """🔴 THE CONTROL, AND IT IS NOT OPTIONAL. If this predicate were the wrong one, the test
    above would still pass while the tool had been broken for every real caller. The call may
    fail LATER for its own reasons — what must not happen is the scene-plan refusal."""
    try:
        await _call(scenes=[MagicMock(parent_id=None)])
    except Exception as exc:  # noqa: BLE001 — downstream minting is out of scope here
        assert "no scene plan" not in str(exc), (
            "a chapter that HAS a scene plan was refused as having none"
        )


async def test_the_scene_target_is_untouched_by_this_check():
    """outline_node_id goes down the pre-existing branch, which validates differently. The new
    check must not fire on it — passing a scene target with no chapter scenes is normal."""
    outline = MagicMock()
    outline.return_value.scenes_for_chapter = AsyncMock(return_value=[])
    outline.return_value.get_node = AsyncMock(return_value=None)
    meta = MagicMock(book_id=PROJECT, project_id=PROJECT)
    with patch.object(srv, "_ctx", MagicMock(return_value=MagicMock(user_id=None))), \
         patch.object(srv, "get_pool", MagicMock()), \
         patch.object(srv, "WorksRepo", MagicMock()), \
         patch.object(srv, "_book_or_deny", AsyncMock(return_value=meta)), \
         patch.object(srv, "_require_project", MagicMock(return_value=PROJECT)), \
         patch.object(srv, "OutlineRepo", outline):
        with pytest.raises(Exception) as e:
            await srv.composition_generate(
                _Ctx(), srv._GenerateArgs(project_id=PROJECT, model_source="user_model",
                                          model_ref=MODEL, outline_node_id=CHAPTER))
        assert "no scene plan" not in str(e.value), (
            "the chapter check fired on a SCENE target"
        )
