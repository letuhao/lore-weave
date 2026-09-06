"""D-ENRICHMENT-LANGUAGE-FALLBACK (issue #222).

``resolve_effective_language`` resolves an unset enrichment profile's language
(``""``/``"auto"``) to the book's REAL stored language via book-service, so
``generate.py``'s prompt builder gets a concrete instruction instead of
falling back to the vague, ignorable phrase "the book's language" — confirmed
live to produce fully Chinese output for an English book with no profile.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.clients.book import BookServiceError
from app.db.book_profile import NEUTRAL_PROFILE
from app.services import profile_language as pl

pytestmark = pytest.mark.asyncio


class _FakeProjection:
    def __init__(self, original_language: str) -> None:
        self.original_language = original_language


class _FakeBookClient:
    def __init__(self, *, language: str = "en", raises: Exception | None = None) -> None:
        self._language = language
        self._raises = raises
        self.closed = False

    async def get_projection(self, *, book_id):
        if self._raises is not None:
            raise self._raises
        return _FakeProjection(self._language)

    async def aclose(self) -> None:
        self.closed = True


def _client_factory(*, language: str = "en", raises: Exception | None = None, calls: list | None = None):
    def _factory(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        return _FakeBookClient(language=language, raises=raises)
    return _factory


async def test_resolves_auto_to_the_books_real_language(monkeypatch):
    monkeypatch.setattr(pl, "BookClient", _client_factory(language="en"))
    resolved = await pl.resolve_effective_language(NEUTRAL_PROFILE, book_id=str(uuid4()))
    assert resolved.language == "en"


async def test_an_already_set_language_is_untouched_and_makes_no_call(monkeypatch):
    calls: list = []
    monkeypatch.setattr(pl, "BookClient", _client_factory(calls=calls))
    profile = NEUTRAL_PROFILE.model_copy(update={"language": "vi"})
    resolved = await pl.resolve_effective_language(profile, book_id=str(uuid4()))
    assert resolved.language == "vi"
    assert calls == []  # a profile that already declares a language is never looked up


async def test_no_book_id_is_a_noop_and_makes_no_call(monkeypatch):
    calls: list = []
    monkeypatch.setattr(pl, "BookClient", _client_factory(calls=calls))
    resolved = await pl.resolve_effective_language(NEUTRAL_PROFILE, book_id=None)
    assert resolved is NEUTRAL_PROFILE
    assert calls == []


async def test_book_service_error_leaves_the_profile_unchanged(monkeypatch):
    monkeypatch.setattr(pl, "BookClient", _client_factory(raises=BookServiceError("boom")))
    resolved = await pl.resolve_effective_language(NEUTRAL_PROFILE, book_id=str(uuid4()))
    assert resolved.language == "auto"  # best-effort: generation still runs, unblocked


async def test_empty_original_language_leaves_the_profile_unchanged(monkeypatch):
    monkeypatch.setattr(pl, "BookClient", _client_factory(language=""))
    resolved = await pl.resolve_effective_language(NEUTRAL_PROFILE, book_id=str(uuid4()))
    assert resolved.language == "auto"  # nothing real to resolve to; keep the existing fallback


async def test_the_book_client_is_always_closed(monkeypatch):
    made: list[_FakeBookClient] = []

    def _factory(**kwargs):
        c = _FakeBookClient(language="en")
        made.append(c)
        return c

    monkeypatch.setattr(pl, "BookClient", _factory)
    await pl.resolve_effective_language(NEUTRAL_PROFILE, book_id=str(uuid4()))
    assert made and made[0].closed
