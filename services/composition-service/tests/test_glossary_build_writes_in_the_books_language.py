"""The glossary is written in the BOOK's language, not one this file picked.

🔴 **MEASURED 2026-08-25.** `glossary_build/prompts.py` says the intent plainly — "language adapts
to the book's source language via `lang` (the POC ran 'vi')" — but the MCP boundary carried the
POC's value as its DEFAULT (`lang: str = "vi"`) and the op=start handler passed it into
`create_run` with no fallback to the book. The argument also had no description, so no model ever
set it.

Net effect: a build against the harness fixture, created with `original_language="en"`, returned
Vietnamese entities — "Ấn Chương Tro (Ashen Sigil)", "Hộ Vệ của Pale (Wardens of the Pale)".

The default has to be **None**, not some other string: with a string default there is no way to
tell "the caller asked for Vietnamese" from "the caller said nothing".
"""
from __future__ import annotations

import types
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.mcp.server import _GlossaryBuildArgs, _resolve_build_lang


def _tc():
    return types.SimpleNamespace(user_id=str(uuid4()))


def test_lang_defaults_to_None_so_absence_is_distinguishable():
    # A string default cannot be told apart from a deliberate choice — that is the whole bug.
    assert _GlossaryBuildArgs(op="status").lang is None


@pytest.mark.asyncio
async def test_an_unsupplied_lang_resolves_to_the_books_own_language():
    book = AsyncMock(return_value={"title": "X", "original_language": "en"})
    with patch("app.mcp.server.get_book_client",
               return_value=types.SimpleNamespace(get_book=book)), \
         patch("app.mcp.server.mint_service_bearer", return_value="tok"):
        assert await _resolve_build_lang(_tc(), uuid4(), None) == "en"


@pytest.mark.asyncio
async def test_an_explicit_lang_still_wins():
    # Resolution must never override a caller who asked for something on purpose.
    book = AsyncMock(return_value={"original_language": "en"})
    with patch("app.mcp.server.get_book_client",
               return_value=types.SimpleNamespace(get_book=book)), \
         patch("app.mcp.server.mint_service_bearer", return_value="tok"):
        assert await _resolve_build_lang(_tc(), uuid4(), "vi") == "vi"
        book.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_unreadable_book_falls_back_rather_than_failing_the_build():
    # The error path keeps today's behaviour deliberately — a different guess would be a silent
    # change of its own — and it logs.
    book = AsyncMock(side_effect=RuntimeError("book-service down"))
    with patch("app.mcp.server.get_book_client",
               return_value=types.SimpleNamespace(get_book=book)), \
         patch("app.mcp.server.mint_service_bearer", return_value="tok"):
        assert await _resolve_build_lang(_tc(), uuid4(), None) == "vi"


@pytest.mark.asyncio
async def test_a_book_with_no_language_recorded_falls_back():
    book = AsyncMock(return_value={"title": "X"})
    with patch("app.mcp.server.get_book_client",
               return_value=types.SimpleNamespace(get_book=book)), \
         patch("app.mcp.server.mint_service_bearer", return_value="tok"):
        assert await _resolve_build_lang(_tc(), uuid4(), None) == "vi"
