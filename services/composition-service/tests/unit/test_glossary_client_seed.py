"""Unit tests for GlossaryClient.seed_entities (planning Stage 0 cast seeding).

Guards the payload SHAPE — the extract-entities decoder is strict (extra fields →
422, found live), so this pins the minimal {source_language, default_tags,
entities:[{kind_code, name}]} contract + the name-filter + the degrade path.
"""

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.clients.glossary_client import GlossaryClient

BOOK = UUID("019f1783-ebb4-78de-ac9d-0dfba6539b7c")


class _FakeHTTP:
    def __init__(self, status, body):
        self._status, self._body = status, body
        self.calls: list[dict] = []

    async def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json})
        return SimpleNamespace(status_code=self._status, json=lambda: self._body)


def _client(fake) -> GlossaryClient:
    c = GlossaryClient.__new__(GlossaryClient)  # skip __init__ (no real httpx)
    c._base_url = "http://glossary"
    c._http = fake
    c._headers = lambda: None
    return c


async def test_seed_entities_attributes_and_actions_and_name_filter():
    fake = _FakeHTTP(200, {"created": 2, "entities": [
        {"name": "Lâm Uyển", "entity_id": "e1"}, {"name": "Tô Yến", "entity_id": "e2"}]})
    c = _client(fake)
    out = await c.seed_entities(BOOK, source_language="vi", entities=[
        {"kind_code": "character", "name": "Lâm Uyển",
         "attributes": {"role": "protagonist", "personality": "kiên cường"}},
        {"name": "Tô Yến"},                       # kind defaults to character; no attrs
        {"kind_code": "character", "name": ""},   # nameless → filtered
    ])
    assert len(out) == 2
    sent = fake.calls[0]["json"]
    # D-PLAN-CAST-ATTRS: attributes carried + attribute_actions auto-built (fill) per attr sent
    assert set(sent.keys()) == {"source_language", "default_tags", "entities", "attribute_actions"}
    assert sent["entities"] == [
        {"kind_code": "character", "name": "Lâm Uyển",
         "attributes": {"role": "protagonist", "personality": "kiên cường"}},
        {"kind_code": "character", "name": "Tô Yến", "attributes": {}},
    ]
    assert sent["attribute_actions"] == {"character": {"role": "fill", "personality": "fill"}}
    assert fake.calls[0]["url"].endswith(f"/internal/books/{BOOK}/extract-entities")


async def test_seed_entities_no_attributes_omits_actions():
    fake = _FakeHTTP(200, {"entities": []})
    c = _client(fake)
    await c.seed_entities(BOOK, source_language="vi", entities=[{"kind_code": "character", "name": "X"}])
    sent = fake.calls[0]["json"]
    assert "attribute_actions" not in sent       # no attrs sent → no actions block
    assert sent["entities"] == [{"kind_code": "character", "name": "X", "attributes": {}}]


async def test_seed_entities_empty_input_makes_no_call():
    fake = _FakeHTTP(200, {})
    c = _client(fake)
    assert await c.seed_entities(BOOK, source_language="vi", entities=[]) == []
    assert fake.calls == []


async def test_seed_entities_degrades_on_non_200():
    fake = _FakeHTTP(422, {"code": "GLOSS_BOOK_NOT_SCAFFOLDED"})
    c = _client(fake)
    out = await c.seed_entities(BOOK, source_language="vi",
                                entities=[{"kind_code": "character", "name": "X"}])
    assert out == []
