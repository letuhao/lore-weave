"""`/v1/jobs/fairness` — P5 fair-scheduling depth surface (M5).

Owner-scoped, reports per-lane running/queued from the WFQ Redis depth. The FairScheduler
observer is patched (its real-Redis behavior is proven in the SDK suite + the per-service
live-redis proofs); these lock the router contract: off→disabled, owner forwarded as the
WFQ key, only active lanes surfaced, redis blip degrades (never 500)."""

from unittest.mock import AsyncMock, patch

from tests.conftest import TEST_USER


def test_fairness_disabled_when_p5_off(client):
    with patch("app.routers.jobs.settings.p5_sched_enabled", False):
        r = client.get("/v1/jobs/fairness", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False and body["lanes"] == []


def test_fairness_reports_active_lanes_owner_scoped(client):
    obs = AsyncMock()
    # translation: 2 running + 5 queued; knowledge: 1 running; lore_enrichment: idle.
    inflight = {"translation:chapter": 2, "knowledge:extraction": 1, "lore-enrichment:job": 0}
    ready = {"translation:chapter": 5, "knowledge:extraction": 0, "lore-enrichment:job": 0}
    obs.inflight_count = AsyncMock(side_effect=lambda lane, owner: inflight[lane])
    obs.ready_len = AsyncMock(side_effect=lambda lane, owner: ready[lane])
    with (
        patch("app.routers.jobs.settings.p5_sched_enabled", True),
        patch("app.routers.jobs.settings.p5_owner_cap", 2),
        patch("app.routers.jobs._p5_observer", return_value=obs),
    ):
        r = client.get("/v1/jobs/fairness", headers={"Authorization": "Bearer x"})
    body = r.json()
    assert body["enabled"] is True and body["owner_cap"] == 2
    lanes = {l["lane"]: l for l in body["lanes"]}
    # idle lore_enrichment is omitted; the two active lanes are present.
    assert set(lanes) == {"translation", "knowledge"}
    assert lanes["translation"] == {"lane": "translation", "running": 2, "queued": 5, "cap": 2}
    assert lanes["knowledge"]["running"] == 1 and lanes["knowledge"]["queued"] == 0
    # owner scoping: every depth read keyed the JWT sub as the WFQ owner.
    for call in obs.inflight_count.await_args_list:
        assert call.args[1] == TEST_USER


def test_fairness_degrades_on_redis_blip(client):
    obs = AsyncMock()
    obs.inflight_count = AsyncMock(side_effect=RuntimeError("redis down"))
    obs.ready_len = AsyncMock(return_value=0)
    with (
        patch("app.routers.jobs.settings.p5_sched_enabled", True),
        patch("app.routers.jobs._p5_observer", return_value=obs),
    ):
        r = client.get("/v1/jobs/fairness", headers={"Authorization": "Bearer x"})
    # never 500s — enabled with whatever lanes were computed before the blip (none here).
    assert r.status_code == 200
    assert r.json() == {"enabled": True, "owner_cap": 5, "lanes": []}
