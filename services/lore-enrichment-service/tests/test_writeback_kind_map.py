"""_glossary_kind_code — enrichment entity_kind → glossary kind_code mapping.

Pins the live-surfaced fix (D-COMPOSE-S1-LIVE-SMOKE): glossary has no `generic`
or `faction` kind, so a NEW-entity promote under those 502'd. The C1 kinds that
share the glossary code pass through; the two that differ are translated.
"""

from __future__ import annotations

import pytest

from app.clients.writeback import UnplaceableEntityError, WritebackError
from app.services.writeback import _DEFAULT_GLOSSARY_KIND, WritebackService, _glossary_kind_code

pytestmark_async = pytest.mark.asyncio


@pytest.mark.parametrize(
    "enrichment_kind, expected",
    [
        ("character", "character"),
        ("location", "location"),
        ("item", "item"),
        ("event", "event"),
        ("faction", "organization"),   # glossary names a faction 'organization'
        ("generic", "terminology"),    # the glossary catch-all for a concept/entry
        ("species", "species"),        # a glossary-native kind passes through
        ("", "location"),              # legacy empty fallback (unchanged)
    ],
)
def test_glossary_kind_code_maps_to_a_real_glossary_kind(enrichment_kind, expected):
    assert _glossary_kind_code(enrichment_kind) == expected


# ── reactive catch-all fallback (no hardcoded glossary taxonomy) ──────────────
class _FakePorts:
    """Records the kind_codes write_entity_through_glossary was called with; raises
    UnplaceableEntityError for any kind in ``unplaceable`` (simulating glossary
    silently skipping an unknown kind), else returns a stub entity_id."""

    def __init__(self, unplaceable: set[str], *, default_also_fails: bool = False):
        self.unplaceable = unplaceable
        self.default_also_fails = default_also_fails
        self.calls: list[str] = []

    async def write_entity_through_glossary(self, *, book_id, kind_code, name, attributes, source_language):
        self.calls.append(kind_code)
        if kind_code in self.unplaceable:
            raise UnplaceableEntityError(f"glossary could not place {kind_code!r}", status_code=502)
        return "019e0000-0000-7000-8000-000000000001"


def _svc(ports) -> WritebackService:
    return WritebackService(repo=object(), ports=ports)  # repo unused by the helper


@pytest.mark.asyncio
async def test_anchor_write_retries_under_catch_all_when_kind_unplaceable():
    from uuid import uuid4
    ports = _FakePorts(unplaceable={"power_system"})  # glossary can't place it → retry
    eid = await _svc(ports)._write_glossary_anchor(
        book_id=uuid4(), kind_code="power_system", name="渾天宝鑑", source_language="zh",
    )
    assert eid  # resolved on the retry
    assert ports.calls == ["power_system", _DEFAULT_GLOSSARY_KIND]  # tried real kind, then catch-all


@pytest.mark.asyncio
async def test_anchor_write_no_retry_when_kind_placeable():
    from uuid import uuid4
    ports = _FakePorts(unplaceable=set())  # glossary places it first try
    await _svc(ports)._write_glossary_anchor(
        book_id=uuid4(), kind_code="character", name="姜子牙", source_language="zh",
    )
    assert ports.calls == ["character"]  # no fallback call


@pytest.mark.asyncio
async def test_anchor_write_reraises_when_catch_all_itself_unplaceable():
    from uuid import uuid4
    ports = _FakePorts(unplaceable={"generic", _DEFAULT_GLOSSARY_KIND})
    with pytest.raises(UnplaceableEntityError):
        await _svc(ports)._write_glossary_anchor(
            book_id=uuid4(), kind_code="generic", name="X", source_language="zh",
        )


@pytest.mark.asyncio
async def test_anchor_write_propagates_a_transport_error_without_retry():
    from uuid import uuid4

    class _BoomPorts:
        def __init__(self):
            self.calls = 0

        async def write_entity_through_glossary(self, **_kw):
            self.calls += 1
            raise WritebackError("glossary 503", retryable=True, status_code=503)

    ports = _BoomPorts()
    with pytest.raises(WritebackError):
        await _svc(ports)._write_glossary_anchor(
            book_id=uuid4(), kind_code="character", name="X", source_language="zh",
        )
    assert ports.calls == 1  # a transport failure is NOT retried under the catch-all
