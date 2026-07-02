"""REG-P1-05 — degrade-contract tests for the user-skills (agent-registry) client.

Mirrors test_book_steering_client.py: an httpx.MockTransport is injected via the
constructor. EVERY failure path must return the EMPTY UserSkills — never raise
into the chat turn (fallback to the built-in SYSTEM_SKILLS).
"""
from __future__ import annotations

import os
from typing import Callable

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests")
os.environ.setdefault("MINIO_SECRET_KEY", "test-minio-secret")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-internal-token")

from app.client.user_skills_client import UserSkills, UserSkillsClient  # noqa: E402

USER_ID = "0d0b7c1e-0000-7000-8000-000000000abc"


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> UserSkillsClient:
    return UserSkillsClient(
        base_url="http://agent-registry-service:8099",
        internal_token="unit-test-token",
        timeout_s=0.5,
        transport=httpx.MockTransport(handler),
    )


def _resp(payload: dict) -> Callable[[httpx.Request], httpx.Response]:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)
    return handler


@pytest.mark.asyncio
async def test_success_parses_skills_and_overrides():
    payload = {
        "catalog_version": 5,
        "skills": [
            {"slug": "recap", "description": "recap", "body_md": "# Recap", "l1_line": "· recap — recap"},
        ],
        "system_overrides": {"plan_forge": False},
        "shadowed_system": ["glossary"],
    }
    c = _client(_resp(payload))
    try:
        out = await c.get_skills(USER_ID, surface="chat")
    finally:
        await c.aclose()
    assert len(out.skills) == 1
    assert out.skills[0]["slug"] == "recap"
    assert out.system_disabled("plan_forge") is True
    assert out.system_disabled("knowledge") is False
    assert out.shadows("glossary") is True
    assert out.l1_lines == ["· recap — recap"]


@pytest.mark.asyncio
async def test_empty_user_id_returns_empty():
    c = _client(_resp({"skills": [{"slug": "x"}]}))
    try:
        out = await c.get_skills("")
    finally:
        await c.aclose()
    assert out == UserSkills()


@pytest.mark.asyncio
async def test_non_200_degrades_to_empty():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")
    c = _client(handler)
    try:
        out = await c.get_skills(USER_ID)
    finally:
        await c.aclose()
    assert out.skills == [] and out.system_overrides == {}


@pytest.mark.asyncio
async def test_transport_error_degrades_to_empty():
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")
    c = _client(handler)
    try:
        out = await c.get_skills(USER_ID)
    finally:
        await c.aclose()
    assert out.skills == []


@pytest.mark.asyncio
async def test_malformed_shape_degrades():
    c = _client(_resp({"skills": "not-a-list", "system_overrides": "nope"}))
    try:
        out = await c.get_skills(USER_ID)
    finally:
        await c.aclose()
    assert out.skills == [] and out.system_overrides == {}


@pytest.mark.asyncio
async def test_drops_non_dict_skill_entries():
    c = _client(_resp({"skills": [{"slug": "ok", "body_md": "b"}, "garbage", {"no_slug": 1}]}))
    try:
        out = await c.get_skills(USER_ID)
    finally:
        await c.aclose()
    assert [s["slug"] for s in out.skills] == ["ok"]
