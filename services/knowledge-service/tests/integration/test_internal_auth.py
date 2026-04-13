import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.routers.ping import internal_router


@pytest.fixture
def client_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    # Force the live settings singleton to a known token for this test only;
    # monkeypatch.setattr auto-restores after the test ends.
    monkeypatch.setattr(settings, "internal_service_token", "unit_test_token")
    app = FastAPI()
    app.include_router(internal_router)
    return app


@pytest.mark.asyncio
async def test_internal_ping_rejects_missing_token(client_app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=client_app), base_url="http://test") as c:
        r = await c.get("/internal/ping")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_internal_ping_rejects_wrong_token(client_app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=client_app), base_url="http://test") as c:
        r = await c.get("/internal/ping", headers={"X-Internal-Token": "nope"})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_internal_ping_accepts_correct_token(client_app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=client_app), base_url="http://test") as c:
        r = await c.get("/internal/ping", headers={"X-Internal-Token": "unit_test_token"})
        assert r.status_code == 200
        assert r.json() == {"pong": True}
