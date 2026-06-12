"""M4a: V3 knowledge client — wiki-neighborhood fetch (Null gate + degrade-to-empty + parse)."""
import pytest

from app.workers import knowledge_client as kc
from app.workers.knowledge_client import (
    fetch_wiki_neighborhood, WikiNeighborhood, Relation, _parse_neighborhood,
)

_PAYLOAD = {
    "found": True,
    "glossary_entity_id": "e1",
    "name": "Tirami",
    "kind": "character",
    "source_types": ["glossary"],
    "entity_source_type": "glossary",
    "relations": [
        {"predicate": "leader_of", "subject_name": "Tirami", "subject_kind": "character",
         "object_name": "Paladins", "object_kind": "faction", "confidence": 0.95,
         "pending_validation": False, "source_type": "glossary"},
        {"predicate": "married_to", "subject_name": "Tirami", "subject_kind": "character",
         "object_name": "Isutansha", "object_kind": "character", "confidence": 0.7,
         "pending_validation": True, "source_type": "enriched"},
    ],
    "total_relations": 2,
    "relations_truncated": False,
}


# ── Fake httpx client ─────────────────────────────────────────────────────────

class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    """Records the last POST; returns a canned response or raises."""
    last_call = {}

    def __init__(self, resp=None, exc=None):
        self._resp = resp
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        _FakeClient.last_call = {"url": url, "json": json, "headers": headers}
        if self._exc:
            raise self._exc
        return self._resp


def _patch_client(monkeypatch, *, resp=None, exc=None):
    def factory(*a, **k):
        return _FakeClient(resp=resp, exc=exc)
    monkeypatch.setattr(kc.httpx, "AsyncClient", factory)
    _FakeClient.last_call = {}


# ── _parse_neighborhood (pure) ────────────────────────────────────────────────

def test_parse_neighborhood_full():
    nb = _parse_neighborhood(_PAYLOAD, "e1")
    assert nb.found and nb.name == "Tirami" and nb.kind == "character"
    assert len(nb.relations) == 2
    r0, r1 = nb.relations
    assert r0.predicate == "leader_of" and r0.confidence == 0.95 and not r0.pending_validation
    # faithful parse keeps the trust signals for M4b's ladder
    assert r1.pending_validation is True and r1.source_type == "enriched"
    # entity-level trust signals (§11.2): TRUST-1 = source_types ∋ 'glossary'
    assert nb.source_types == ["glossary"] and nb.entity_source_type == "glossary"


def test_parse_neighborhood_missing_source_types_defaults_empty():
    nb = _parse_neighborhood({"found": True, "relations": []}, "e1")
    assert nb.source_types == [] and nb.entity_source_type == ""


def test_parse_neighborhood_ignores_non_dict_relations():
    nb = _parse_neighborhood({"found": True, "relations": ["bad", 3, None]}, "e1")
    assert nb.relations == []


def test_parse_neighborhood_bad_confidence_coerces_zero():
    nb = _parse_neighborhood(
        {"found": True, "relations": [{"predicate": "x", "confidence": "NaNish"}]}, "e1")
    assert nb.relations[0].confidence == 0.0


# ── fetch_wiki_neighborhood (best-effort) ─────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_null_gate_when_unconfigured(monkeypatch):
    """No URL → empty neighbourhood, NO HTTP call (feature off)."""
    monkeypatch.setattr(kc.settings, "knowledge_service_internal_url", "")
    _patch_client(monkeypatch, resp=_FakeResp(200, _PAYLOAD))  # would succeed if called
    nb = await fetch_wiki_neighborhood("u1", "e1")
    assert nb == WikiNeighborhood.empty("e1")
    assert _FakeClient.last_call == {}  # proves no request was made


@pytest.mark.asyncio
async def test_fetch_success_parses(monkeypatch):
    monkeypatch.setattr(kc.settings, "knowledge_service_internal_url", "http://kn:8092")
    monkeypatch.setattr(kc.settings, "internal_service_token", "tok")
    _patch_client(monkeypatch, resp=_FakeResp(200, _PAYLOAD))
    nb = await fetch_wiki_neighborhood("u1", "e1", rel_cap=50)
    assert nb.found and len(nb.relations) == 2
    # request shape: body + internal-token header
    assert _FakeClient.last_call["json"] == {"user_id": "u1", "glossary_entity_id": "e1", "rel_cap": 50}
    assert _FakeClient.last_call["headers"]["X-Internal-Token"] == "tok"
    assert _FakeClient.last_call["url"].endswith("/internal/knowledge/wiki-neighborhood")


@pytest.mark.asyncio
async def test_fetch_non_200_degrades(monkeypatch):
    monkeypatch.setattr(kc.settings, "knowledge_service_internal_url", "http://kn:8092")
    _patch_client(monkeypatch, resp=_FakeResp(503, {}))
    nb = await fetch_wiki_neighborhood("u1", "e1")
    assert nb == WikiNeighborhood.empty("e1")


@pytest.mark.asyncio
async def test_fetch_transport_error_degrades(monkeypatch):
    monkeypatch.setattr(kc.settings, "knowledge_service_internal_url", "http://kn:8092")
    _patch_client(monkeypatch, exc=RuntimeError("connection refused"))
    nb = await fetch_wiki_neighborhood("u1", "e1")
    assert nb == WikiNeighborhood.empty("e1") and not nb.found


@pytest.mark.asyncio
async def test_fetch_malformed_body_degrades(monkeypatch):
    """A 200 with a non-JSON body (resp.json() raises) degrades, never raises."""
    class _BadResp:
        status_code = 200
        def json(self):
            raise ValueError("not json")
    monkeypatch.setattr(kc.settings, "knowledge_service_internal_url", "http://kn:8092")
    _patch_client(monkeypatch, resp=_BadResp())
    nb = await fetch_wiki_neighborhood("u1", "e1")
    assert nb == WikiNeighborhood.empty("e1")


# ── M4d-1: fetch_timeline (best-effort) ───────────────────────────────────────

from app.workers.knowledge_client import fetch_timeline, TimelineBrief

_TL_PAYLOAD = {
    "found": True,
    "events": [
        {"title": "The pact", "summary": "Two houses allied.", "event_date": "Y1",
         "participants": ["Tirami", "Aldric"]},
        {"title": "The betrayal", "summary": None, "event_date": None, "participants": []},
    ],
    "count": 2,
    "total": 2,
}


@pytest.mark.asyncio
async def test_fetch_timeline_null_gate_when_unconfigured(monkeypatch):
    monkeypatch.setattr(kc.settings, "knowledge_service_internal_url", "")
    _patch_client(monkeypatch, resp=_FakeResp(200, _TL_PAYLOAD))  # would succeed if called
    brief = await fetch_timeline("b1", 5)
    assert brief == TimelineBrief.empty()
    assert _FakeClient.last_call == {}  # no request made


@pytest.mark.asyncio
async def test_fetch_timeline_success_parses(monkeypatch):
    monkeypatch.setattr(kc.settings, "knowledge_service_internal_url", "http://kn:8092")
    monkeypatch.setattr(kc.settings, "internal_service_token", "tok")
    _patch_client(monkeypatch, resp=_FakeResp(200, _TL_PAYLOAD))
    brief = await fetch_timeline("b1", 5, limit=10)
    assert brief.found and len(brief.events) == 2
    assert brief.events[0].title == "The pact" and brief.events[0].participants == ["Tirami", "Aldric"]
    assert brief.events[1].summary is None
    assert _FakeClient.last_call["json"] == {"book_id": "b1", "chapter_order": 5, "limit": 10}
    assert _FakeClient.last_call["headers"]["X-Internal-Token"] == "tok"
    assert _FakeClient.last_call["url"].endswith("/internal/knowledge/timeline")


@pytest.mark.asyncio
async def test_fetch_timeline_non_200_degrades(monkeypatch):
    monkeypatch.setattr(kc.settings, "knowledge_service_internal_url", "http://kn:8092")
    _patch_client(monkeypatch, resp=_FakeResp(503, {}))
    assert await fetch_timeline("b1", 5) == TimelineBrief.empty()


@pytest.mark.asyncio
async def test_fetch_timeline_transport_error_degrades(monkeypatch):
    monkeypatch.setattr(kc.settings, "knowledge_service_internal_url", "http://kn:8092")
    _patch_client(monkeypatch, exc=RuntimeError("connection refused"))
    assert await fetch_timeline("b1", 5) == TimelineBrief.empty()


@pytest.mark.asyncio
async def test_fetch_timeline_ignores_non_dict_events(monkeypatch):
    monkeypatch.setattr(kc.settings, "knowledge_service_internal_url", "http://kn:8092")
    _patch_client(monkeypatch, resp=_FakeResp(200, {"found": True, "events": ["bad", 3, None]}))
    brief = await fetch_timeline("b1", 5)
    assert brief.found and brief.events == []
