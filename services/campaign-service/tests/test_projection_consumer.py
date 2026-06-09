"""Projection consumer tests — event → campaign_chapters advancement (G7)."""

from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.events.consumer import handle_event, EVENT_STAGE

USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
BOOK = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
CHAP = "cccccccc-cccc-cccc-cccc-cccccccccccc"


def _payload(**over):
    p = {"user_id": USER, "book_id": BOOK, "chapter_id": CHAP}
    p.update(over)
    return p


@pytest.mark.parametrize(
    "event_type,stage",
    [
        ("knowledge.chapter_extracted", "knowledge"),
        ("chapter.translated", "translation"),
        ("chapter.translation_skipped", "translation"),  # S2 idempotency skip done-signal
        ("translation.quality", "eval"),
    ],
)
async def test_known_event_advances_correct_stage(fake_pool, mocker, event_type, stage):
    mark = mocker.patch(
        "app.events.consumer.repo.mark_stage_done_by_chapter",
        new_callable=AsyncMock, return_value=1,
    )
    handled = await handle_event(fake_pool, event_type, _payload())
    assert handled is True
    mark.assert_awaited_once()
    assert mark.call_args.kwargs["stage"] == stage
    assert mark.call_args.kwargs["chapter_id"] == UUID(CHAP)


async def test_translation_event_passes_target_language_guard(fake_pool, mocker):
    # The language guard: translation/eval events carry target_language and must
    # forward it so a different-language translation can't falsely complete a
    # campaign (adversarial finding #1).
    mark = mocker.patch(
        "app.events.consumer.repo.mark_stage_done_by_chapter",
        new_callable=AsyncMock, return_value=1,
    )
    await handle_event(fake_pool, "chapter.translated", _payload(target_language="vi"))
    assert mark.call_args.kwargs["target_language"] == "vi"


async def test_knowledge_event_has_no_language_guard(fake_pool, mocker):
    # knowledge.chapter_extracted is language-agnostic → no target_language key →
    # guard is None (no filter).
    mark = mocker.patch(
        "app.events.consumer.repo.mark_stage_done_by_chapter",
        new_callable=AsyncMock, return_value=1,
    )
    await handle_event(fake_pool, "knowledge.chapter_extracted", _payload())
    assert mark.call_args.kwargs["target_language"] is None


async def test_unknown_event_ignored(fake_pool, mocker):
    mark = mocker.patch(
        "app.events.consumer.repo.mark_stage_done_by_chapter", new_callable=AsyncMock
    )
    assert await handle_event(fake_pool, "chapter.saved", _payload()) is False
    mark.assert_not_called()


async def test_missing_ids_ignored(fake_pool, mocker):
    mark = mocker.patch(
        "app.events.consumer.repo.mark_stage_done_by_chapter", new_callable=AsyncMock
    )
    assert await handle_event(fake_pool, "chapter.translated", {"user_id": USER}) is False
    mark.assert_not_called()


async def test_malformed_uuid_ignored(fake_pool, mocker):
    mocker.patch(
        "app.events.consumer.repo.mark_stage_done_by_chapter", new_callable=AsyncMock
    )
    assert await handle_event(
        fake_pool, "chapter.translated", _payload(chapter_id="not-a-uuid")
    ) is False


def test_event_stage_map_covers_three_stages():
    assert set(EVENT_STAGE.values()) == {"knowledge", "translation", "eval"}
