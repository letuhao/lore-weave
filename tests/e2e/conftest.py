"""Shared fixtures for the T01-T20 Track 1 cross-service e2e suite.

These tests hit a live compose stack — postgres, auth-service,
book-service, glossary-service, knowledge-service, chat-service,
and api-gateway-bff all running in docker-compose. Each test
function creates throwaway users + projects + books, asserts the
cross-service contract, and cleans up after itself.

Run with:
    cd tests/e2e
    python -m pytest -v

Or from repo root:
    python -m pytest tests/e2e -v

Skips the whole suite if the gateway is unreachable so unit test
runs on machines without the stack don't fail.
"""

from __future__ import annotations

import os
import secrets
import string
from dataclasses import dataclass
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio

GATEWAY_URL = os.environ.get("E2E_GATEWAY_URL", "http://localhost:3123")
KNOWLEDGE_INTERNAL_URL = os.environ.get(
    "E2E_KNOWLEDGE_INTERNAL_URL", "http://localhost:8216"
)
INTERNAL_TOKEN = os.environ.get("E2E_INTERNAL_TOKEN", "dev_internal_token")


@dataclass
class E2eUser:
    """A freshly registered throwaway user. `token` is a live access
    token for `user_id`; both are valid for the lifetime of the test.

    Renamed from `TestUser` so pytest doesn't try to collect the
    dataclass as a test class (pytest's default collector picks up
    anything prefixed with `Test`)."""

    user_id: str
    email: str
    token: str
    username: str


def _rand_suffix(n: int = 10) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


async def _register_user(client: httpx.AsyncClient) -> E2eUser:
    """Register a fresh throwaway user, then log in to obtain an
    access token. auth-service's /register returns the user profile
    only (verification_required semantics); /login returns the JWT.
    Username + email are randomised so parallel test runs do not
    conflict."""
    suffix = _rand_suffix()
    username = f"e2e{suffix}"
    email = f"{username}@e2e.test"
    password = "E2eTest1234!"
    reg = await client.post(
        f"{GATEWAY_URL}/v1/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    reg.raise_for_status()
    reg_body = reg.json()
    user_id = reg_body["user_id"]

    login = await client.post(
        f"{GATEWAY_URL}/v1/auth/login",
        json={"email": email, "password": password},
    )
    login.raise_for_status()
    return E2eUser(
        user_id=user_id,
        email=email,
        token=login.json()["access_token"],
        username=username,
    )


@pytest_asyncio.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    """One shared httpx client per test function. Gateway URL baked in
    as the base so tests can use relative paths."""
    async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=10.0) as client:
        # Pre-flight: if the gateway is unreachable, skip the test
        # instead of erroring out. Matches the knowledge-service
        # integration conftest pattern.
        try:
            r = await client.get("/health")
            if r.status_code != 200:
                pytest.skip(f"gateway /health = {r.status_code}")
        except httpx.RequestError as exc:
            pytest.skip(f"gateway unreachable: {exc}")
        yield client


@pytest_asyncio.fixture
async def internal_http() -> AsyncIterator[httpx.AsyncClient]:
    """Direct client to knowledge-service's internal port for
    /internal/context/build. Internal token baked in."""
    async with httpx.AsyncClient(
        base_url=KNOWLEDGE_INTERNAL_URL,
        timeout=10.0,
        headers={"X-Internal-Token": INTERNAL_TOKEN},
    ) as client:
        try:
            r = await client.get("/health")
            if r.status_code != 200:
                pytest.skip(f"knowledge-service /health = {r.status_code}")
        except httpx.RequestError as exc:
            pytest.skip(f"knowledge-service unreachable: {exc}")
        yield client


@pytest_asyncio.fixture
async def user_a(http: httpx.AsyncClient) -> E2eUser:
    return await _register_user(http)


@pytest_asyncio.fixture
async def user_b(http: httpx.AsyncClient) -> E2eUser:
    return await _register_user(http)


def auth(user: E2eUser) -> dict[str, str]:
    """Bearer-token header dict for an httpx call."""
    return {"Authorization": f"Bearer {user.token}"}
