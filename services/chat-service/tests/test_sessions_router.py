"""Tests for the sessions CRUD router."""
from __future__ import annotations

from uuid import uuid4

import pytest

from tests.conftest import TEST_MODEL_REF, TEST_SESSION_ID, TEST_USER_ID, make_session_record


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_create_session_returns_201(self, client, mock_pool):
        record = make_session_record()
        mock_pool.fetchrow.return_value = record

        resp = await client.post("/v1/chat/sessions", json={
            "model_source": "user_model",
            "model_ref": TEST_MODEL_REF,
            "title": "My Chat",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Test Session"
        assert data["session_id"] == TEST_SESSION_ID
        mock_pool.fetchrow.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_session_with_system_prompt(self, client, mock_pool):
        record = make_session_record(system_prompt="You are a translator")
        mock_pool.fetchrow.return_value = record

        resp = await client.post("/v1/chat/sessions", json={
            "model_source": "user_model",
            "model_ref": TEST_MODEL_REF,
            "system_prompt": "You are a translator",
        })
        assert resp.status_code == 201
        assert resp.json()["system_prompt"] == "You are a translator"

    @pytest.mark.asyncio
    async def test_create_session_with_project_ids_persists_set(self, client, mock_pool):
        """Track B B1(2): the multi-KG grounding set round-trips through create
        and the UUID[] is bound as the last INSERT arg."""
        pid_a, pid_b = str(uuid4()), str(uuid4())
        mock_pool.fetchrow.return_value = make_session_record(project_ids=[pid_a, pid_b])
        resp = await client.post("/v1/chat/sessions", json={
            "model_source": "user_model",
            "model_ref": TEST_MODEL_REF,
            "project_ids": [pid_a, pid_b],
        })
        assert resp.status_code == 201
        assert resp.json()["project_ids"] == [pid_a, pid_b]
        # bound as the final INSERT positional (a list of the two id strings)
        assert list(mock_pool.fetchrow.call_args.args[-1]) == [pid_a, pid_b]

    @pytest.mark.asyncio
    async def test_create_session_project_ids_over_cap_returns_422(self, client, mock_pool):
        """The ≤16 cap mirrors knowledge-service's ContextBuildRequest."""
        resp = await client.post("/v1/chat/sessions", json={
            "model_source": "user_model",
            "model_ref": TEST_MODEL_REF,
            "project_ids": [str(uuid4()) for _ in range(17)],
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_session_missing_model_ref_returns_422(self, client, mock_pool):
        resp = await client.post("/v1/chat/sessions", json={
            "model_source": "user_model",
        })
        assert resp.status_code == 422


class TestListSessions:
    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, client, mock_pool):
        mock_pool.fetch.return_value = []
        resp = await client.get("/v1/chat/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_list_sessions_returns_items(self, client, mock_pool):
        mock_pool.fetch.return_value = [make_session_record(), make_session_record(session_id=str(uuid4()))]
        resp = await client.get("/v1/chat/sessions")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_sessions_with_status_filter(self, client, mock_pool):
        mock_pool.fetch.return_value = []
        resp = await client.get("/v1/chat/sessions?status=archived")
        assert resp.status_code == 200
        # Verify the status filter was passed to the query
        call_args = mock_pool.fetch.call_args
        assert "archived" in call_args.args


class TestGetSession:
    @pytest.mark.asyncio
    async def test_get_session_found(self, client, mock_pool):
        mock_pool.fetchrow.return_value = make_session_record()
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}")
        assert resp.status_code == 200
        assert resp.json()["session_id"] == TEST_SESSION_ID

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, client, mock_pool):
        mock_pool.fetchrow.return_value = None
        resp = await client.get(f"/v1/chat/sessions/{uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_session_memory_mode_no_project(self, client, mock_pool):
        """K-CLEAN-5 (D-K8-04): GET response derives memory_mode from
        project_id. With no project linked, mode is 'no_project'."""
        mock_pool.fetchrow.return_value = make_session_record(project_id=None)
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] is None
        assert body["memory_mode"] == "no_project"

    @pytest.mark.asyncio
    async def test_get_session_memory_mode_static(self, client, mock_pool):
        """K-CLEAN-5 (D-K8-04): with a project linked, mode is 'static'.
        `degraded` is not representable on GET — that only ever arrives
        via the per-turn SSE memory-mode event."""
        project_id = str(uuid4())
        mock_pool.fetchrow.return_value = make_session_record(project_id=project_id)
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == project_id
        assert body["memory_mode"] == "static"

    @pytest.mark.asyncio
    async def test_get_session_memory_mode_multi(self, client, mock_pool):
        """Track B B1(2): a set of ≥2 grounding projects derives memory_mode
        'multi' on GET (a single link stays 'static')."""
        pids = [str(uuid4()), str(uuid4())]
        mock_pool.fetchrow.return_value = make_session_record(project_ids=pids)
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_ids"] == pids
        assert body["memory_mode"] == "multi"

    @pytest.mark.asyncio
    async def test_get_session_single_project_ids_is_static(self, client, mock_pool):
        """A single-element set is not 'multi' — one KG is the static path."""
        pids = [str(uuid4())]
        mock_pool.fetchrow.return_value = make_session_record(project_ids=pids)
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}")
        assert resp.status_code == 200
        assert resp.json()["memory_mode"] == "static"

    @pytest.mark.asyncio
    async def test_get_session_returns_enabled_tool_arrays(self, client, mock_pool):
        mock_pool.fetchrow.return_value = make_session_record(
            enabled_tools=["find_tools"],
            enabled_skills=["glossary"],
            activated_tools=["book_list"],
        )
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled_tools"] == ["find_tools"]
        assert body["enabled_skills"] == ["glossary"]
        assert body["activated_tools"] == ["book_list"]


class TestPatchSession:
    @pytest.mark.asyncio
    async def test_patch_session_title(self, client, mock_pool):
        original = make_session_record()
        updated = make_session_record(title="Updated Title")
        mock_pool.fetchrow.side_effect = [original, updated]

        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "title": "Updated Title",
        })
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Title"

    @pytest.mark.asyncio
    async def test_patch_session_not_found(self, client, mock_pool):
        mock_pool.fetchrow.return_value = None
        resp = await client.patch(f"/v1/chat/sessions/{uuid4()}", json={
            "title": "Nope",
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_session_archive(self, client, mock_pool):
        original = make_session_record()
        updated = make_session_record(status="archived")
        mock_pool.fetchrow.side_effect = [original, updated]

        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "status": "archived",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

    @pytest.mark.asyncio
    async def test_patch_session_enabled_tools(self, client, mock_pool):
        original = make_session_record()
        updated = make_session_record(enabled_tools=["book_get_chapter"])
        mock_pool.fetchrow.side_effect = [original, updated]

        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "enabled_tools": ["book_get_chapter"],
        })
        assert resp.status_code == 200
        assert resp.json()["enabled_tools"] == ["book_get_chapter"]

    @pytest.mark.asyncio
    async def test_patch_session_set_project_ids(self, client, mock_pool):
        """Track B B1(2): PATCH replaces the grounding set; the write flag is
        True and the UUID[] value rides the UPDATE args."""
        pids = [str(uuid4()), str(uuid4())]
        original = make_session_record()
        updated = make_session_record(project_ids=pids)
        mock_pool.fetchrow.side_effect = [original, updated]

        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "project_ids": pids,
        })
        assert resp.status_code == 200
        assert resp.json()["project_ids"] == pids
        # UPDATE args: (..., set_project_ids=True, project_ids_value=[pids])
        args = mock_pool.fetchrow.call_args.args
        assert args[-2] is True
        assert list(args[-1]) == pids

    @pytest.mark.asyncio
    async def test_patch_session_clear_project_ids(self, client, mock_pool):
        """An explicit [] clears the set back to the single-project path (write
        flag True, empty value)."""
        original = make_session_record(project_ids=[str(uuid4())])
        updated = make_session_record(project_ids=[])
        mock_pool.fetchrow.side_effect = [original, updated]

        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "project_ids": [],
        })
        assert resp.status_code == 200
        assert resp.json()["project_ids"] == []
        args = mock_pool.fetchrow.call_args.args
        assert args[-2] is True          # present in body → write
        assert list(args[-1]) == []

    @pytest.mark.asyncio
    async def test_patch_session_omitted_project_ids_leaves_alone(self, client, mock_pool):
        """Omitting project_ids leaves the column untouched (write flag False)."""
        original = make_session_record(project_ids=[str(uuid4())])
        updated = make_session_record(title="x")
        mock_pool.fetchrow.side_effect = [original, updated]

        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "title": "x",
        })
        assert resp.status_code == 200
        args = mock_pool.fetchrow.call_args.args
        assert args[-2] is False         # not in body → leave alone


class TestDeleteSession:
    @pytest.mark.asyncio
    async def test_delete_session_success(self, client, mock_pool):
        mock_pool.execute.return_value = "DELETE 1"
        resp = await client.delete(f"/v1/chat/sessions/{TEST_SESSION_ID}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_session_not_found(self, client, mock_pool):
        mock_pool.execute.return_value = "DELETE 0"
        resp = await client.delete(f"/v1/chat/sessions/{uuid4()}")
        assert resp.status_code == 404
