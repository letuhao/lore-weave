"""T38 B8 — the by-ids read goes through the KAL, and the setting it needs EXISTS.

⚠️ This file exists because the migration passed 4216 tests while
`settings.knowledge_gateway_url` did not exist at all. Every one of those tests was green
because none of them executed the line that builds the URL — the migrated call would have
raised `AttributeError` on the first real request. A suite that cannot reach a line cannot
defend it, which is why the first assertion here is about the SETTING and not the request.
"""
from __future__ import annotations

import pytest

from app.config import settings


def test_the_kal_base_url_setting_exists_and_is_non_empty():
    """The assertion that would have caught the missing setting.

    Non-empty matters as much as present: translation-service defaults its copy to `""` and
    its client reads unset as "feature off, return nothing", which turns a missing env var
    into a silently disabled read rather than a loud one.
    """
    assert hasattr(settings, "knowledge_gateway_url"), (
        "knowledge-service has no knowledge_gateway_url — the migrated by-ids read builds its "
        "URL from it and would raise AttributeError on the first request"
    )
    assert settings.knowledge_gateway_url, "the KAL base URL is empty"


@pytest.mark.asyncio
async def test_fetch_entities_by_ids_calls_the_KAL_and_maps_the_vocabulary(monkeypatch):
    """The KAL speaks `kind` / `aliases`; this model speaks `kind_code` / `cached_aliases`.

    Unmapped, `kind_code` would silently fall back to its default and every consumer reading
    it would see an empty string — the `kind_code` vs `kind` mismatch that B6's live smoke
    caught in worker-ai, here caught before it shipped.
    """
    from uuid import uuid4

    from app.clients.glossary_client import GlossaryClient

    seen: dict = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"items": [{
                "entity_id": "e1", "cached_name": "Kai", "kind": "character",
                "aliases": ["the heir"], "short_description": "the betrayed heir",
                "attributes": [{"code": "rank", "value": "inner disciple"}],
            }]}

    class _Http:
        async def post(self, url, json=None):
            seen["url"], seen["body"] = url, json
            return _Resp()

    c = GlossaryClient.__new__(GlossaryClient)
    c._base_url = "http://glossary-service:8088"      # type: ignore[attr-defined]
    c._http = _Http()                                  # type: ignore[attr-defined]

    rows = await c.fetch_entities_by_ids(
        book_id=uuid4(), entity_ids=["e1"], include_attributes=True)

    assert "/v1/kal/books/" in seen["url"] and seen["url"].endswith("/cast/by-ids"), (
        f"the read did not go through the KAL: {seen['url']}"
    )
    assert seen["body"]["include_attributes"] is True
    assert rows[0].kind_code == "character", "the KAL's `kind` was not mapped to `kind_code`"
    assert rows[0].cached_aliases == ["the heir"]
    assert rows[0].attributes[0].value == "inner disciple"
