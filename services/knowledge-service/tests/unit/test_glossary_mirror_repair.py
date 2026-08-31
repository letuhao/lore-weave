"""The mirror REPAIR route (D-GLOSSARY-KG-MIRROR-HAS-NO-RECONCILER).

The dangerous outcome here is not an exception. It is a repair endpoint that returns 200
with an encouraging number while nothing was re-emitted — after which the divergence is
believed closed and nobody looks again.
"""
from __future__ import annotations

import pytest

import app.routers.internal_mirror as mirror_route
from app.mirror.glossary_mirror import MirrorDrift

PROJECT = "11111111-1111-1111-1111-111111111111"
BOOK = "22222222-2222-2222-2222-222222222222"
USER = "33333333-3333-3333-3333-333333333333"


class _Client:
    def __init__(self, result):
        self._result = result
        self.calls: list[tuple] = []

    async def reemit_mirror(self, book_id, entity_ids):
        self.calls.append((book_id, list(entity_ids)))
        return self._result


class _Session:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *a):
        return False


@pytest.fixture
def wired(monkeypatch):
    """Wire the route's collaborators; each test supplies drift + client behaviour."""
    def _install(drift, client):
        class _Pool:
            async def fetchrow(self, *a, **kw):
                return {"book_id": BOOK, "user_id": USER}

        monkeypatch.setattr(mirror_route, "get_knowledge_pool", lambda: _Pool())
        monkeypatch.setattr(mirror_route, "get_glossary_client", lambda: client)
        monkeypatch.setattr(mirror_route.settings, "neo4j_uri", "bolt://x")

        async def _detect(**kw):
            return drift

        monkeypatch.setattr(mirror_route, "detect_mirror_drift", _detect)
        import app.db.neo4j as neo4j_mod
        monkeypatch.setattr(neo4j_mod, "graph_session", lambda *a, **k: _Session())
    return _install


def _drift(missing: list[str]) -> MirrorDrift:
    d = MirrorDrift(project_id=PROJECT, book_id=BOOK, truth_total=len(missing) + 1,
                    mirrorable=len(missing) + 1, mirrored=1)
    d.missing_ids = list(missing)
    return d


@pytest.mark.asyncio
async def test_repair_hands_the_missing_ids_to_the_SSOT(wired):
    """The KG must not gain a second writer. The repair's only action is asking the
    glossary to re-publish through the outbox the consumer already reads."""
    client = _Client({"reemitted": 2, "skipped_ids": [], "failed_ids": []})
    wired(_drift(["a", "b"]), client)

    out = await mirror_route.glossary_mirror_repair(PROJECT)

    assert client.calls == [(BOOK, ["a", "b"])]
    assert out["detected_missing"] == 2 and out["reemitted"] == 2


@pytest.mark.asyncio
async def test_a_failed_reemit_is_never_reported_as_a_repair(wired):
    """`reemit_mirror` returning None means the events were NOT written. Rendering that
    as a 200 with reemitted=0 would leave the divergence open and believed closed."""
    from fastapi import HTTPException

    client = _Client(None)
    wired(_drift(["a"]), client)

    with pytest.raises(HTTPException) as exc:
        await mirror_route.glossary_mirror_repair(PROJECT)
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_repair_is_bounded_and_names_what_it_deferred(wired):
    """An unbounded repair turns one operator action into an outbox burst. A SILENT
    bound is worse: the caller reads 'repaired' and never learns 83 were left."""
    client = _Client({"reemitted": 3, "skipped_ids": [], "failed_ids": []})
    wired(_drift([str(i) for i in range(10)]), client)

    out = await mirror_route.glossary_mirror_repair(PROJECT, max_repairs=3)

    assert client.calls[0][1] == ["0", "1", "2"]
    assert out["deferred_ids"] == ["3", "4", "5", "6", "7", "8", "9"]


@pytest.mark.asyncio
async def test_nothing_missing_calls_nobody(wired):
    client = _Client({"reemitted": 99})
    wired(_drift([]), client)

    out = await mirror_route.glossary_mirror_repair(PROJECT)

    assert client.calls == [], "a repair with nothing to repair still called the SSOT"
    assert out["reemitted"] == 0


@pytest.mark.asyncio
async def test_repair_does_not_report_a_fresh_divergence_count(wired):
    """Convergence is eventual — the relay ships asynchronously. A post-repair 'missing'
    number in this response would be measuring the repair with the repair, and would read
    as either a false zero or a false failure depending on relay timing."""
    client = _Client({"reemitted": 1, "skipped_ids": [], "failed_ids": []})
    wired(_drift(["a"]), client)

    out = await mirror_route.glossary_mirror_repair(PROJECT)

    assert "missing" not in out
    assert "re-run the drift probe" in out["note"]
