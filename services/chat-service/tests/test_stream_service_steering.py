"""RAID C1 (DR-C1) — stream_service wiring tests for per-book steering.

Proves the <steering> system part (fetched from book-service, selected per
DR-C1) lands right after the main system prompt on BOTH assembly paths —
Anthropic structured `parts` and plain-string `system_parts` — for a
book-scoped turn, is ABSENT for a plain chat turn, and that any steering
failure leaves the turn unaffected (guarded degrade).

Mirrors test_stream_service.py's K18.9 harness: knowledge client + gateway
patched, messages captured from the gateway call.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.stream_service import stream_response
from tests.conftest import TEST_MODEL_REF, TEST_SESSION_ID, TEST_USER_ID
from tests.test_stream_service import (
    _make_chunk,
    _make_creds,
    _make_pool_with_conn,
    _patched_knowledge,
)

BOOK_ID = "0d0b7c1e-0000-7000-8000-0000000000b1"

ENTRIES = [
    {"id": "1", "name": "tone", "body": "Keep the prose wry.", "inclusion_mode": "always", "match_pattern": None},
    {"id": "2", "name": "combat", "body": "Fast cuts.", "inclusion_mode": "scene_match", "match_pattern": "battle"},
    {"id": "3", "name": "lore", "body": "Deep lore.", "inclusion_mode": "manual", "match_pattern": None},
]


def _steering_client(entries=None, exc: Exception | None = None) -> MagicMock:
    client = MagicMock()
    if exc is not None:
        client.get_steering = AsyncMock(side_effect=exc)
    else:
        client.get_steering = AsyncMock(return_value=entries if entries is not None else ENTRIES)
    return client


async def _run_turn(
    *,
    steering_client: MagicMock,
    provider_kind: str = "openai",
    stable: str = "",
    system_prompt: str | None = None,
    message: str = "hello",
    book_context: dict | None = None,
    editor_context: dict | None = None,
) -> list[dict]:
    """Drive one stream_response turn with the harness patched; returns the
    messages array captured from the gateway call."""
    pool, conn = _make_pool_with_conn()
    pool.fetchrow.return_value = {
        "system_prompt": system_prompt,
        "generation_params": {},
    }
    pool.fetch.return_value = []
    conn.fetchval.return_value = 1

    captured: list[dict] = []

    async def fake_acompletion(**kwargs):
        captured.extend(kwargs.get("messages", []))
        yield _make_chunk("ok")
        yield _make_chunk(None)

    def fake_wrapper(**kwargs):
        return fake_acompletion(**kwargs)

    with patch(
        "app.services.stream_service.get_knowledge_client",
        return_value=_patched_knowledge(stable=stable, volatile="v" if stable else ""),
    ), patch(
        "app.services.stream_service._stream_via_gateway",
        side_effect=fake_wrapper,
    ), patch(
        "app.client.book_steering_client.get_book_steering_client",
        return_value=steering_client,
    ):
        async for _ in stream_response(
            session_id=TEST_SESSION_ID,
            user_message_content=message,
            user_id=TEST_USER_ID,
            model_source="user_model",
            model_ref=TEST_MODEL_REF,
            creds=_make_creds(provider_kind=provider_kind),
            pool=pool,
            billing=AsyncMock(),
            book_context=book_context,
            editor_context=editor_context,
        ):
            pass
    return captured


def _system_text(messages: list[dict]) -> str:
    system = next((m for m in messages if m["role"] == "system"), None)
    assert system is not None, "no system message captured"
    content = system["content"]
    if isinstance(content, str):
        return content
    return "\n\n".join(p["text"] for p in content)


class TestSteeringWiring:
    @pytest.mark.asyncio
    async def test_book_scoped_turn_gets_steering_part_plain_path(self):
        """Plain system_parts path (non-Anthropic): the <steering> block lands
        in the system message, right after the session system prompt."""
        sc = _steering_client()
        msgs = await _run_turn(
            steering_client=sc,
            system_prompt="Write like a pirate.",
            book_context={"book_id": BOOK_ID},
        )
        text = _system_text(msgs)
        assert "<steering>" in text and "</steering>" in text
        assert "## tone\nKeep the prose wry." in text
        # placement: immediately after the main system prompt
        assert text.index("Write like a pirate.") < text.index("<steering>")
        # only 'always' matched (no #lore, no battle title)
        assert "Deep lore." not in text and "Fast cuts." not in text
        sc.get_steering.assert_awaited_once_with(BOOK_ID)

    @pytest.mark.asyncio
    async def test_book_scoped_turn_gets_steering_part_anthropic_parts_path(self):
        """Anthropic structured `parts` path: the steering part is its own text
        part placed immediately after the system_prompt part."""
        msgs = await _run_turn(
            steering_client=_steering_client(),
            provider_kind="anthropic",
            stable="<memory/>",
            system_prompt="Write like a pirate.",
            book_context={"book_id": BOOK_ID},
        )
        system = next(m for m in msgs if m["role"] == "system")
        parts = system["content"]
        assert isinstance(parts, list)
        texts = [p["text"] for p in parts]
        steer_idx = next(i for i, t in enumerate(texts) if t.startswith("<steering>"))
        prompt_idx = texts.index("Write like a pirate.")
        assert steer_idx == prompt_idx + 1, "steering must sit right after the system prompt"

    @pytest.mark.asyncio
    async def test_plain_chat_turn_has_no_steering_and_no_fetch(self):
        """No book_context/editor_context → steering is never fetched and the
        system content carries no <steering> part."""
        sc = _steering_client()
        msgs = await _run_turn(steering_client=sc, system_prompt="p")
        assert "<steering>" not in _system_text(msgs)
        sc.get_steering.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_manual_entry_triggered_by_hash_name_in_message(self):
        msgs = await _run_turn(
            steering_client=_steering_client(),
            message="expand this using #lore",
            book_context={"book_id": BOOK_ID},
        )
        text = _system_text(msgs)
        assert "Deep lore." in text
        # order inside the block: always before manual
        assert text.index("Keep the prose wry.") < text.index("Deep lore.")

    @pytest.mark.asyncio
    async def test_scene_match_uses_editor_context_chapter_title(self):
        msgs = await _run_turn(
            steering_client=_steering_client(),
            editor_context={"book_id": BOOK_ID, "chapter_id": "c1", "chapter_title": "The Battle of Dawn"},
        )
        text = _system_text(msgs)
        assert "Fast cuts." in text

    @pytest.mark.asyncio
    async def test_steering_failure_leaves_turn_unaffected(self):
        """Guarded degrade: even a client that RAISES (contract breach — it
        should degrade to []) must not break the turn."""
        msgs = await _run_turn(
            steering_client=_steering_client(exc=RuntimeError("boom")),
            system_prompt="p",
            book_context={"book_id": BOOK_ID},
        )
        text = _system_text(msgs)
        assert "<steering>" not in text
        assert msgs, "gateway was never called — the steering failure broke the turn"

    @pytest.mark.asyncio
    async def test_empty_steering_list_adds_no_part(self):
        msgs = await _run_turn(
            steering_client=_steering_client(entries=[]),
            system_prompt="p",
            book_context={"book_id": BOOK_ID},
        )
        assert "<steering>" not in _system_text(msgs)
