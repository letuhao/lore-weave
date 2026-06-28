"""D-W8-MOTIF-BEAT-EXTRACTOR — unit tests for the motif-beat sequence endpoint
+ the Option-A deriver.

POST /internal/extraction/motif-beats — the server side of composition-service's
frozen `get_motif_beat_sequences` client. Two layers tested:

  * **route** (`test_route_*`) — auth, the frozen `{sequences: [[step,…],…]}`
    wire shape (field names beat/thread/tension/role_mentions), empty-corpus →
    [], Neo4j-unconfigured degrade. The deriver is patched so these run
    hermetically.
  * **deriver** (`test_derive_*` / `test_tension_*`) — the pure event→beat
    mapping + tension banding + per-book grouping + tenant scoping, with the pg
    pool + neo4j session + event list mocked.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.extraction import motif_beat as deriver_mod
from app.routers import internal_extraction as route_mod

_TOKEN = "default_test_token"  # conftest INTERNAL_SERVICE_TOKEN default


def _client() -> TestClient:
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


def _post(client, body, *, token=_TOKEN):
    headers = {"X-Internal-Token": token} if token is not None else {}
    return client.post("/internal/extraction/motif-beats", json=body, headers=headers)


# ── route: registration ───────────────────────────────────────────────────────


def test_route_is_registered_on_app():
    """Prove the frozen path is mounted (a 404 would mean main.py wiring drift)."""
    from app.main import app
    paths = {r.path for r in app.routes}
    assert "/internal/extraction/motif-beats" in paths


# ── route: auth ───────────────────────────────────────────────────────────────


def test_route_requires_internal_token():
    resp = _post(_client(), {"user_id": str(uuid4()), "corpus": True}, token=None)
    assert resp.status_code == 401


def test_route_wrong_token_401():
    resp = _post(_client(), {"user_id": str(uuid4()), "corpus": True}, token="nope")
    assert resp.status_code == 401


# ── route: frozen wire shape ──────────────────────────────────────────────────


@patch("app.routers.internal_extraction.settings")
def test_route_returns_frozen_sequence_shape(mock_settings):
    """The response is `{sequences: [[{beat,thread,tension,role_mentions}…]…]}`
    — the EXACT keys knowledge_client.get_motif_beat_sequences reads."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TOKEN

    async def _fake(**kwargs):
        return [
            [
                {"beat": "The pact", "thread": "ch-1", "tension": 5,
                 "role_mentions": ["Tirami", "Aldric"]},
                {"beat": "The betrayal", "thread": "ch-2", "tension": 3,
                 "role_mentions": []},
            ],
        ]
    with patch("app.extraction.motif_beat.derive_motif_beat_sequences", _fake):
        resp = _post(_client(), {"user_id": str(uuid4()), "book_id": str(uuid4())})

    assert resp.status_code == 200
    data = resp.json()
    assert "sequences" in data
    seqs = data["sequences"]
    assert len(seqs) == 1 and len(seqs[0]) == 2
    step = seqs[0][0]
    assert set(step.keys()) == {"beat", "thread", "tension", "role_mentions"}
    assert step == {
        "beat": "The pact", "thread": "ch-1", "tension": 5,
        "role_mentions": ["Tirami", "Aldric"],
    }
    assert seqs[0][1]["role_mentions"] == []


@patch("app.routers.internal_extraction.settings")
def test_route_empty_corpus_returns_empty_list(mock_settings):
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TOKEN

    async def _fake(**kwargs):
        return []
    with patch("app.extraction.motif_beat.derive_motif_beat_sequences", _fake):
        resp = _post(_client(), {"user_id": str(uuid4()), "corpus": True})
    assert resp.status_code == 200
    assert resp.json() == {"sequences": []}


@patch("app.routers.internal_extraction.settings")
def test_route_neo4j_unconfigured_degrades_to_empty(mock_settings):
    """No Neo4j → `{sequences: []}` (contract-shaped degrade), NOT a 503 — the
    composition client treats it as the deferred-extractor empty path."""
    mock_settings.neo4j_uri = ""
    mock_settings.internal_service_token = _TOKEN
    # deriver must NOT be called when Neo4j is absent.
    sentinel = AsyncMock()
    with patch("app.extraction.motif_beat.derive_motif_beat_sequences", sentinel):
        resp = _post(_client(), {"user_id": str(uuid4()), "corpus": True})
    assert resp.status_code == 200
    assert resp.json() == {"sequences": []}
    sentinel.assert_not_awaited()


def test_route_rejects_missing_user_id():
    resp = _post(_client(), {"corpus": True})
    assert resp.status_code == 422  # pydantic: user_id required


# ── deriver: event → beat-step mapping + tension banding ──────────────────────


def _event(
    title, *, chapter_id="ch-1", participants=None, confidence=0.0,
    mention_count=0, narrative_thread=None,
):
    """A minimal :Event projection. `importance` is a computed_field on the real
    Event, so we replicate its derivation here for the fake."""
    participants = participants or []

    def _importance():
        pc = len(participants)
        if (pc >= 3 and confidence >= 0.75) or mention_count >= 5:
            return "pivotal"
        if (pc >= 2 and confidence >= 0.6) or mention_count >= 3:
            return "major"
        return None

    return SimpleNamespace(
        title=title,
        chapter_id=chapter_id,
        narrative_thread=narrative_thread,
        participants=participants,
        confidence=confidence,
        mention_count=mention_count,
        importance=_importance(),
    )


def test_beat_step_prefers_narrative_thread_over_chapter_id():
    """D-W10-ARC-CONFORMANCE-THREAD-TAG — once a classifier tags narrative_thread, the
    beat step uses it; absent a tag it falls back to chapter_id (the Option-A proxy)."""
    from app.extraction.motif_beat import _event_to_beat_step
    tagged = _event_to_beat_step(_event("Duel at dawn", chapter_id="ch-9", narrative_thread="combat"))
    assert tagged["thread"] == "combat"
    untagged = _event_to_beat_step(_event("Quiet talk", chapter_id="ch-9"))
    assert untagged["thread"] == "ch-9"  # fallback to chapter proxy


@pytest.mark.parametrize(
    "event,expected",
    [
        # pivotal hinge (≥3 participants + high confidence) → 5
        (_event("hinge", participants=["a", "b", "c"], confidence=0.8), 5),
        # heavily re-mentioned → pivotal → 5
        (_event("recurring", mention_count=5), 5),
        # major (2 participants + conf 0.6) → 4
        (_event("major", participants=["a", "b"], confidence=0.6), 4),
        # mention_count 3 → major → 4
        (_event("major2", mention_count=3), 4),
        # multi-party but not major/pivotal → 3
        (_event("notable", participants=["a", "b"], confidence=0.1), 3),
        # confident single-party → 3
        (_event("confident", confidence=0.5), 3),
        # lightly attested → 2
        (_event("light", confidence=0.2), 2),
        (_event("light2", mention_count=1), 2),
        # one-off single-party, no signal → 1 (floor)
        (_event("tail"), 1),
    ],
)
def test_tension_band(event, expected):
    assert deriver_mod._tension_band(event) == expected


def test_event_to_beat_step_shape():
    step = deriver_mod._event_to_beat_step(
        _event("The duel", chapter_id="ch-7", participants=["Kai", "Zhao"],
               confidence=0.9, mention_count=2)
    )
    assert step["beat"] == "The duel"
    assert step["thread"] == "ch-7"
    assert step["role_mentions"] == ["Kai", "Zhao"]
    assert isinstance(step["tension"], int) and 1 <= step["tension"] <= 5


def test_event_to_beat_step_threadless_event_uses_empty_string():
    step = deriver_mod._event_to_beat_step(_event("global", chapter_id=None))
    assert step["thread"] == ""  # never null — miner can still partition


# ── deriver: scoping + grouping (pg pool + neo4j mocked) ──────────────────────


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, *a, **k):
        return self._rows


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        return False


class _FakePool:
    def __init__(self, rows):
        self._rows = rows

    def acquire(self):
        return _FakeAcquire(_FakeConn(self._rows))


class _FakeNeo4jSession:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *a):
        return False


def _patch_deriver(monkeypatch, *, project_rows, events_by_project):
    """project_rows: list of asyncpg-style row dicts (project_id, book_id).
    events_by_project: dict[str(project_id)] -> list[event]."""
    monkeypatch.setattr(deriver_mod, "get_knowledge_pool", lambda: _FakePool(project_rows))
    monkeypatch.setattr(deriver_mod, "neo4j_session", lambda: _FakeNeo4jSession())

    async def _list(session, *, user_id, project_id, limit):
        return list(events_by_project.get(project_id, []))

    monkeypatch.setattr(deriver_mod, "list_events_in_order", AsyncMock(side_effect=_list))


@pytest.mark.asyncio
async def test_derive_corpus_one_sequence_per_book(monkeypatch):
    uid = uuid4()
    p1, p2 = uuid4(), uuid4()
    rows = [
        {"project_id": p1, "book_id": uuid4()},
        {"project_id": p2, "book_id": uuid4()},
    ]
    events = {
        str(p1): [_event("a"), _event("b")],
        str(p2): [_event("c")],
    }
    _patch_deriver(monkeypatch, project_rows=rows, events_by_project=events)

    seqs = await deriver_mod.derive_motif_beat_sequences(user_id=uid, corpus=True)
    assert len(seqs) == 2
    assert [s["beat"] for s in seqs[0]] == ["a", "b"]
    assert [s["beat"] for s in seqs[1]] == ["c"]


@pytest.mark.asyncio
async def test_derive_skips_book_with_no_events(monkeypatch):
    uid = uuid4()
    p1, p2 = uuid4(), uuid4()
    rows = [
        {"project_id": p1, "book_id": uuid4()},
        {"project_id": p2, "book_id": uuid4()},  # cold-start book — no events
    ]
    events = {str(p1): [_event("a")]}  # p2 absent → []
    _patch_deriver(monkeypatch, project_rows=rows, events_by_project=events)

    seqs = await deriver_mod.derive_motif_beat_sequences(user_id=uid, corpus=True)
    assert len(seqs) == 1  # the empty book contributes no sequence
    assert [s["beat"] for s in seqs[0]] == ["a"]


@pytest.mark.asyncio
async def test_derive_no_projects_returns_empty(monkeypatch):
    """A cross-user book / empty corpus → no project rows → [] (tenancy: the
    SQL filters by user_id so another user's book yields nothing here)."""
    _patch_deriver(monkeypatch, project_rows=[], events_by_project={})
    seqs = await deriver_mod.derive_motif_beat_sequences(
        user_id=uuid4(), book_id=uuid4()
    )
    assert seqs == []


@pytest.mark.asyncio
async def test_derive_book_query_scopes_to_user_and_book(monkeypatch):
    """The book-scoped SQL must bind BOTH user_id and book_id (tenancy)."""
    uid, book = uuid4(), uuid4()
    captured = {}

    class _Conn:
        async def fetch(self, sql, *params):
            captured["sql"] = sql
            captured["params"] = params
            return []

    class _Acq:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def acquire(self):
            return _Acq()

    monkeypatch.setattr(deriver_mod, "get_knowledge_pool", lambda: _Pool())
    await deriver_mod.derive_motif_beat_sequences(user_id=uid, book_id=book)
    assert "user_id = $1" in captured["sql"]
    assert "book_id = $2" in captured["sql"]
    assert captured["params"] == (uid, book)


@pytest.mark.asyncio
async def test_derive_neither_book_nor_corpus_returns_empty(monkeypatch):
    """Malformed call (no book_id, corpus=False) → [] without querying neo4j."""
    rows_sentinel = []
    _patch_deriver(monkeypatch, project_rows=rows_sentinel, events_by_project={})
    seqs = await deriver_mod.derive_motif_beat_sequences(user_id=uuid4())
    assert seqs == []
