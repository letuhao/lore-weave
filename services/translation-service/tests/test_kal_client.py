"""X5 (temporal-knowledge): KAL client — get_facts / get_canonical reads.

Covers: Null gate (feature off → no HTTP call), as-of-N param threading, parse,
degrade-to-empty (non-200 / transport / malformed), the immutable-once cache
(content_hash + as_of keyed; cache hit skips the second HTTP call; failure not
cached), and the X-Internal-Token + X-User-Id auth headers.
"""
import pytest

from app.workers import kal_client as kal
from app.workers.kal_client import (
    get_facts, get_canonical, get_facts_cached, get_canonical_cached,
    FactsResult, CanonicalSnapshot, Fact, clear_cache, _parse_fact,
)

_FACTS_PAYLOAD = {
    "items": [
        {"fact_kind": "attribute", "attr_or_predicate": "rank", "value": "captain",
         "valid_from_ordinal": 3, "valid_to_ordinal": 9, "cardinality": "single"},
        {"fact_kind": "relation", "attr_or_predicate": "leads", "value": "Paladins",
         "valid_from_ordinal": 1, "valid_to_ordinal": None, "cardinality": "multi"},
    ],
    "temporal_capability": {"glossary": "ordinal_valid_time", "kg": "temporal_unsupported"},
}

_CANON_PAYLOAD = {
    "entity_id": "e1",
    "content": "A stoic captain of the Paladins as of this point in the story.",
    "as_of_ordinal": 7,
    "fold_algo_version": 1,
    "canonical_status": "current",
}


# ── Fake httpx client (records last GET; counts calls) ────────────────────────

class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    last_call: dict = {}
    call_count: int = 0
    factory_kwargs: dict = {}  # W5: build_internal_client(...) kwargs (token baked here)

    def __init__(self, resp=None, exc=None):
        self._resp = resp
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None):
        _FakeClient.call_count += 1
        _FakeClient.last_call = {"url": url, "params": params, "headers": headers}
        if self._exc:
            raise self._exc
        return self._resp


def _patch_client(monkeypatch, *, resp=None, exc=None):
    def factory(*a, **k):
        _FakeClient.factory_kwargs = k
        return _FakeClient(resp=resp, exc=exc)
    # W5: kal_client builds its client via build_internal_client (X-Internal-Token
    # baked there; X-User-Id stays a per-request header via _headers).
    monkeypatch.setattr(kal, "build_internal_client", factory)
    _FakeClient.last_call = {}
    _FakeClient.call_count = 0


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


# ── _parse_fact (pure) ────────────────────────────────────────────────────────

def test_parse_fact_full():
    f = _parse_fact(_FACTS_PAYLOAD["items"][0])
    assert f is not None
    assert f.attr_or_predicate == "rank" and f.value == "captain"
    assert f.valid_from_ordinal == 3 and f.valid_to_ordinal == 9


def test_parse_fact_open_interval_keeps_none():
    f = _parse_fact(_FACTS_PAYLOAD["items"][1])
    assert f.valid_to_ordinal is None and f.cardinality == "multi"


def test_parse_fact_missing_attr_is_dropped():
    assert _parse_fact({"value": "x"}) is None


def test_parse_fact_non_dict_is_dropped():
    assert _parse_fact("bad") is None


def test_parse_fact_bad_ordinal_coerces_none():
    f = _parse_fact({"attr_or_predicate": "a", "value": "v", "valid_from_ordinal": "NaNish"})
    assert f.valid_from_ordinal is None


# ── get_facts ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_facts_null_gate(monkeypatch):
    """No KAL URL → empty result, NO HTTP call (feature off, pre-X5 behavior)."""
    monkeypatch.setattr(kal.settings, "knowledge_gateway_url", "")
    _patch_client(monkeypatch, resp=_FakeResp(200, _FACTS_PAYLOAD))
    res = await get_facts("b1", "e1", as_of=7)
    assert res == FactsResult.empty()
    assert _FakeClient.call_count == 0


@pytest.mark.asyncio
async def test_get_facts_success_threads_as_of_and_attrs(monkeypatch):
    monkeypatch.setattr(kal.settings, "knowledge_gateway_url", "http://kg:3000")
    monkeypatch.setattr(kal.settings, "internal_service_token", "tok")
    _patch_client(monkeypatch, resp=_FakeResp(200, _FACTS_PAYLOAD))
    res = await get_facts("b1", "e1", as_of=7, user_id="u1", attrs=["rank", "leads"])
    assert res.found and len(res.items) == 2
    assert res.temporal_capability["glossary"] == "ordinal_valid_time"
    # as_of + attrs threaded; URL is the KAL route (not glossary /internal/*)
    assert _FakeClient.last_call["params"] == {"as_of": "7", "attrs": "rank,leads"}
    assert _FakeClient.last_call["url"].endswith("/v1/kal/books/b1/entities/e1/facts")
    # auth: internal token + forwarded user id
    assert _FakeClient.factory_kwargs["internal_token"] == "tok"
    assert _FakeClient.last_call["headers"]["X-User-Id"] == "u1"


@pytest.mark.asyncio
async def test_get_facts_omitting_as_of_sends_no_param(monkeypatch):
    """as_of omitted ⇒ current head ⇒ no as_of query param (default-identical)."""
    monkeypatch.setattr(kal.settings, "knowledge_gateway_url", "http://kg:3000")
    _patch_client(monkeypatch, resp=_FakeResp(200, _FACTS_PAYLOAD))
    await get_facts("b1", "e1")
    assert "as_of" not in _FakeClient.last_call["params"]


@pytest.mark.asyncio
async def test_get_facts_non_200_degrades(monkeypatch):
    monkeypatch.setattr(kal.settings, "knowledge_gateway_url", "http://kg:3000")
    _patch_client(monkeypatch, resp=_FakeResp(503, {}))
    assert await get_facts("b1", "e1", as_of=7) == FactsResult.empty()


@pytest.mark.asyncio
async def test_get_facts_transport_error_degrades(monkeypatch):
    monkeypatch.setattr(kal.settings, "knowledge_gateway_url", "http://kg:3000")
    _patch_client(monkeypatch, exc=RuntimeError("connection refused"))
    assert await get_facts("b1", "e1") == FactsResult.empty()


@pytest.mark.asyncio
async def test_get_facts_malformed_body_degrades(monkeypatch):
    class _BadResp:
        status_code = 200
        def json(self):
            raise ValueError("not json")
    monkeypatch.setattr(kal.settings, "knowledge_gateway_url", "http://kg:3000")
    _patch_client(monkeypatch, resp=_BadResp())
    assert await get_facts("b1", "e1") == FactsResult.empty()


# ── get_canonical ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_canonical_null_gate(monkeypatch):
    monkeypatch.setattr(kal.settings, "knowledge_gateway_url", "")
    _patch_client(monkeypatch, resp=_FakeResp(200, _CANON_PAYLOAD))
    assert await get_canonical("b1", "e1", as_of=7) == CanonicalSnapshot.empty()
    assert _FakeClient.call_count == 0


@pytest.mark.asyncio
async def test_get_canonical_success_parses_and_threads_as_of(monkeypatch):
    monkeypatch.setattr(kal.settings, "knowledge_gateway_url", "http://kg:3000")
    monkeypatch.setattr(kal.settings, "internal_service_token", "tok")
    snap = None
    _patch_client(monkeypatch, resp=_FakeResp(200, _CANON_PAYLOAD))
    snap = await get_canonical("b1", "e1", as_of=7, user_id="u1")
    assert snap.found and snap.as_of_ordinal == 7 and snap.canonical_status == "current"
    assert "stoic captain" in snap.content
    assert _FakeClient.last_call["params"] == {"as_of": "7"}
    assert _FakeClient.last_call["url"].endswith("/v1/kal/books/b1/entities/e1/canonical")
    assert _FakeClient.last_call["headers"]["X-User-Id"] == "u1"


@pytest.mark.asyncio
async def test_get_canonical_unbuildable_still_found(monkeypatch):
    """A degrade-safe unbuildable snapshot is returned (found=True) so the caller
    can choose to fall back to facts — it is NOT an error."""
    monkeypatch.setattr(kal.settings, "knowledge_gateway_url", "http://kg:3000")
    _patch_client(monkeypatch, resp=_FakeResp(200, {"content": "", "canonical_status": "unbuildable"}))
    snap = await get_canonical("b1", "e1", as_of=7)
    assert snap.found and snap.canonical_status == "unbuildable" and snap.content == ""


@pytest.mark.asyncio
async def test_get_canonical_non_200_degrades(monkeypatch):
    monkeypatch.setattr(kal.settings, "knowledge_gateway_url", "http://kg:3000")
    _patch_client(monkeypatch, resp=_FakeResp(404, {}))
    assert await get_canonical("b1", "e1") == CanonicalSnapshot.empty()


# ── immutable-once cache (§12.1 / D8) ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_canonical_cache_hit_skips_second_fetch(monkeypatch):
    """Same (book, entity, content_hash, as_of) ⇒ second call served from cache,
    NO second HTTP request (immutable-once reuse)."""
    monkeypatch.setattr(kal.settings, "knowledge_gateway_url", "http://kg:3000")
    _patch_client(monkeypatch, resp=_FakeResp(200, _CANON_PAYLOAD))
    a = await get_canonical_cached("b1", "e1", content_hash="h1", as_of=7)
    b = await get_canonical_cached("b1", "e1", content_hash="h1", as_of=7)
    assert a.found and b.found and b.content == a.content
    assert _FakeClient.call_count == 1  # second call hit the cache


@pytest.mark.asyncio
async def test_canonical_cache_misses_on_different_content_hash(monkeypatch):
    """A changed content_hash (edited chapter) busts the cache → re-fetch."""
    monkeypatch.setattr(kal.settings, "knowledge_gateway_url", "http://kg:3000")
    _patch_client(monkeypatch, resp=_FakeResp(200, _CANON_PAYLOAD))
    await get_canonical_cached("b1", "e1", content_hash="h1", as_of=7)
    await get_canonical_cached("b1", "e1", content_hash="h2", as_of=7)
    assert _FakeClient.call_count == 2


@pytest.mark.asyncio
async def test_canonical_cache_misses_on_different_as_of(monkeypatch):
    """A different as_of is a different temporal slice → distinct cache entry."""
    monkeypatch.setattr(kal.settings, "knowledge_gateway_url", "http://kg:3000")
    _patch_client(monkeypatch, resp=_FakeResp(200, _CANON_PAYLOAD))
    await get_canonical_cached("b1", "e1", content_hash="h1", as_of=7)
    await get_canonical_cached("b1", "e1", content_hash="h1", as_of=8)
    assert _FakeClient.call_count == 2


@pytest.mark.asyncio
async def test_canonical_cache_does_not_store_failure(monkeypatch):
    """A degrade-to-empty (feature off / failure) result is NOT cached, so a later
    recovery is picked up rather than pinned to empty."""
    monkeypatch.setattr(kal.settings, "knowledge_gateway_url", "http://kg:3000")
    _patch_client(monkeypatch, resp=_FakeResp(503, {}))
    first = await get_canonical_cached("b1", "e1", content_hash="h1", as_of=7)
    assert first == CanonicalSnapshot.empty()
    # Recover: now the KAL returns 200 — must re-fetch (not serve the empty).
    _patch_client(monkeypatch, resp=_FakeResp(200, _CANON_PAYLOAD))
    second = await get_canonical_cached("b1", "e1", content_hash="h1", as_of=7)
    assert second.found and _FakeClient.call_count == 1


@pytest.mark.asyncio
async def test_facts_cache_hit_skips_second_fetch(monkeypatch):
    monkeypatch.setattr(kal.settings, "knowledge_gateway_url", "http://kg:3000")
    _patch_client(monkeypatch, resp=_FakeResp(200, _FACTS_PAYLOAD))
    a = await get_facts_cached("b1", "e1", content_hash="h1", as_of=7)
    b = await get_facts_cached("b1", "e1", content_hash="h1", as_of=7)
    assert a.found and b.found and _FakeClient.call_count == 1


@pytest.mark.asyncio
async def test_facts_cache_attrs_order_insensitive(monkeypatch):
    """attrs order must not fragment the cache (same set ⇒ same key)."""
    monkeypatch.setattr(kal.settings, "knowledge_gateway_url", "http://kg:3000")
    _patch_client(monkeypatch, resp=_FakeResp(200, _FACTS_PAYLOAD))
    await get_facts_cached("b1", "e1", content_hash="h1", as_of=7, attrs=["rank", "leads"])
    await get_facts_cached("b1", "e1", content_hash="h1", as_of=7, attrs=["leads", "rank"])
    assert _FakeClient.call_count == 1
