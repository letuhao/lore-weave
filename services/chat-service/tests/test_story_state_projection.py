"""T4 (D4/D5) — `project_story_state` orchestration decision logic.

Effect-proving unit tests for the maintain-vs-project control flow, with the two DB
collaborators (`get_block`/`refresh_block`) mocked so this runs with NO Postgres (the
real SQL is proven separately in test_session_blocks_db.py). What each test asserts is
the DECISION the orchestrator makes: does it refresh the cache this turn, and what does
it project.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.db import session_blocks
from app.db.session_blocks import SessionBlock, project_story_state
from app.services.story_state import (
    DEFAULT_CADENCE_TURNS,
    distill_story_state,
    render_story_state_block,
    source_hash,
)

pytestmark = pytest.mark.asyncio


async def _run(*, cached, stable, full, current_turn=5, lore_gate=False, scene_change=False):
    """Drive project_story_state with get_block→`cached` and refresh_block mocked;
    return (projected_text, refresh_mock)."""
    with patch.object(session_blocks, "get_block", AsyncMock(return_value=cached)), patch.object(
        session_blocks, "refresh_block", AsyncMock(return_value=1)
    ) as rb:
        out = await project_story_state(
            AsyncMock(),
            session_id="s",
            owner_user_id="o",
            stable_context=stable,
            full_context=full,
            current_turn=current_turn,
            lore_gate=lore_gate,
            scene_change=scene_change,
        )
    return out, rb


def _cached(value="CACHED BIBLE", *, refreshed_turn, src_hash):
    return SessionBlock(
        label="story_state", value=value, token_estimate=3,
        refreshed_turn=refreshed_turn, source_hash=src_hash, version=1,
    )


async def test_no_cache_live_present_refreshes_and_does_not_project():
    stable = "Lâm Uyển — betrayed heiress.\nĐại Việt is the setting."
    out, rb = await _run(cached=None, stable=stable, full=stable)
    rb.assert_awaited_once()
    # refreshed from the distilled prefix, at the current turn
    kwargs = rb.await_args.kwargs
    assert kwargs["value"] == distill_story_state(stable)[0]
    assert kwargs["refreshed_turn"] == 5
    assert kwargs["source_hash"] == source_hash(stable)
    # live prefix already in the prompt → nothing extra projected
    assert out == ""


async def test_same_hash_within_cadence_uses_cache_no_refresh():
    stable = "bible text"
    cached = _cached(refreshed_turn=4, src_hash=source_hash(stable))
    out, rb = await _run(cached=cached, stable=stable, full=stable, current_turn=5)
    rb.assert_not_awaited()  # (5-4) < cadence and hash unchanged
    assert out == ""


async def test_changed_hash_refreshes():
    cached = _cached(refreshed_turn=4, src_hash="stale")
    out, rb = await _run(cached=cached, stable="new bible", full="new bible", current_turn=5)
    rb.assert_awaited_once()
    assert out == ""


async def test_cadence_elapsed_refreshes_even_same_hash():
    stable = "bible text"
    cached = _cached(refreshed_turn=0, src_hash=source_hash(stable))
    out, rb = await _run(cached=cached, stable=stable, full=stable,
                         current_turn=DEFAULT_CADENCE_TURNS)
    rb.assert_awaited_once()
    assert out == ""


async def test_lore_gate_forces_refresh_within_cadence():
    stable = "bible text"
    cached = _cached(refreshed_turn=4, src_hash=source_hash(stable))
    out, rb = await _run(cached=cached, stable=stable, full=stable, current_turn=5,
                         lore_gate=True)
    rb.assert_awaited_once()
    assert out == ""


async def test_multi_project_empty_prefix_but_full_present_does_not_false_project():
    """Regression: multi_project mode has stable_context='' but a full live `context`.
    The orchestrator must key the projection on `full_context` (not the prefix) so it
    refreshes from the full context and projects NOTHING — else it would DUPLICATE the
    live lore already in the prompt."""
    full = "<memory>lots of live union lore</memory>"
    out, rb = await _run(cached=None, stable="", full=full)
    rb.assert_awaited_once()
    assert rb.await_args.kwargs["value"] == distill_story_state(full)[0]
    assert out == ""  # NOT the cached block — live grounding is present


async def test_degraded_empty_grounding_projects_cached_block_no_refresh():
    """The safety net: no live grounding this turn (degraded) → project the last-good
    cached bible; do NOT refresh (nothing fresh to distill)."""
    cached = _cached(value="entities: A, B", refreshed_turn=3, src_hash="h")
    out, rb = await _run(cached=cached, stable="", full="")
    rb.assert_not_awaited()
    assert out == render_story_state_block("entities: A, B")


async def test_degraded_with_no_cache_projects_nothing():
    out, rb = await _run(cached=None, stable="", full="")
    rb.assert_not_awaited()
    assert out == ""


async def test_degraded_with_blank_cache_projects_nothing():
    cached = _cached(value="   ", refreshed_turn=3, src_hash="h")
    out, rb = await _run(cached=cached, stable="", full="")
    rb.assert_not_awaited()
    assert out == ""
