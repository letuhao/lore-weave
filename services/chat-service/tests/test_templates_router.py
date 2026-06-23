"""Tests for the session_templates router (M2) — CRUD, tenancy, charter seed.

Router-level tenancy: write endpoints filter `owner_user_id = caller`, so a
System row (owner NULL) or another user's row never matches → 404. (The DB-level
partial-unique + check constraints are verified live in M1.)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from tests.conftest import TEST_MODEL_REF, TEST_USER_ID, FakeRecord, make_session_record


def make_template_record(owner_user_id=TEST_USER_ID, tier="user", **over) -> FakeRecord:
    now = datetime.now(timezone.utc)
    base = {
        "template_id": str(uuid4()),
        "owner_user_id": owner_user_id,
        "tier": tier,
        "code": "faang_swe",
        "name": "FAANG SWE",
        "description": "Senior backend interview",
        "system_prompt": "You are a strict but fair senior interviewer.",
        "model_source": "user_model",
        "model_ref": TEST_MODEL_REF,
        "scenario": json.dumps({
            "goal": "Assess senior backend skill",
            "phases": ["warmup", "technical", "behavioral", "wrap"],
            "checklist": ["system design", "conflict story"],
            "time_budget_min": 60,
            "language": "vi",
        }),
        "rubric": None,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    base.update(over)
    return FakeRecord(base)


class TestCreateTemplate:
    @pytest.mark.asyncio
    async def test_create_returns_201_as_user_tier(self, client, mock_pool):
        mock_pool.fetchrow.return_value = make_template_record()
        resp = await client.post("/v1/chat/templates", json={
            "code": "faang_swe",
            "name": "FAANG SWE",
            "system_prompt": "You are a strict but fair senior interviewer.",
            "scenario": {
                "goal": "Assess senior backend skill",
                "phases": ["warmup", "technical"],
                "checklist": ["system design"],
                "language": "vi",
            },
        })
        assert resp.status_code == 201
        assert resp.json()["tier"] == "user"
        # The INSERT hard-codes tier='user' — the API cannot create a System row.
        q = mock_pool.fetchrow.call_args.args[0]
        assert "'user'" in q and "owner_user_id" in q


class TestListTemplates:
    @pytest.mark.asyncio
    async def test_list_merges_system_and_own(self, client, mock_pool):
        mock_pool.fetch.return_value = [
            make_template_record(owner_user_id=None, tier="system", code="behavioral"),
            make_template_record(code="faang_swe"),
        ]
        resp = await client.get("/v1/chat/templates")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2
        # The query must scope to System (NULL) + the caller only.
        q = mock_pool.fetch.call_args.args[0]
        assert "owner_user_id IS NULL OR owner_user_id = $1" in q


class TestTenancyDeny:
    @pytest.mark.asyncio
    async def test_patch_system_template_is_404(self, client, mock_pool):
        # WHERE owner_user_id = user_id matches nothing for a System row → None.
        mock_pool.fetchrow.return_value = None
        resp = await client.patch(f"/v1/chat/templates/{uuid4()}", json={"name": "hijacked"})
        assert resp.status_code == 404
        # Prove the filter is wired: the UPDATE scopes by owner = caller.
        q = mock_pool.fetchrow.call_args.args[0]
        assert "owner_user_id = $2" in q
        assert TEST_USER_ID in mock_pool.fetchrow.call_args.args

    @pytest.mark.asyncio
    async def test_delete_system_template_is_404(self, client, mock_pool):
        mock_pool.execute.return_value = "DELETE 0"
        resp = await client.delete(f"/v1/chat/templates/{uuid4()}")
        assert resp.status_code == 404
        q = mock_pool.execute.call_args.args[0]
        assert "owner_user_id = $2" in q
        assert TEST_USER_ID in mock_pool.execute.call_args.args


class TestStartPractice:
    @pytest.mark.asyncio
    async def test_start_seeds_frozen_charter(self, client, mock_pool):
        # 1st fetchrow = load template (visible), 2nd = INSERT session.
        mock_pool.fetchrow.side_effect = [
            make_template_record(),
            make_session_record(title="FAANG SWE"),
        ]
        resp = await client.post(f"/v1/chat/templates/{uuid4()}/start", json={})
        assert resp.status_code == 201

        insert_args = mock_pool.fetchrow.call_args_list[1].args
        # working_memory_seed is the last bound param (JSON string).
        seed = json.loads(insert_args[-1])
        assert seed["version"] == 1
        assert seed["charter"]["goal"] == "Assess senior backend skill"
        assert seed["charter"]["checklist"] == ["system design", "conflict story"]
        assert seed["charter"]["language"] == "vi"
        # state starts empty — the executive fills it later, never the seed.
        assert seed["state"]["covered"] == []

    @pytest.mark.asyncio
    async def test_start_unknown_template_is_404(self, client, mock_pool):
        mock_pool.fetchrow.return_value = None
        resp = await client.post(f"/v1/chat/templates/{uuid4()}/start", json={})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_start_no_model_is_400(self, client, mock_pool):
        # Template with no default model, and the request provides none.
        mock_pool.fetchrow.side_effect = [
            make_template_record(model_source=None, model_ref=None),
        ]
        resp = await client.post(f"/v1/chat/templates/{uuid4()}/start", json={})
        assert resp.status_code == 400
