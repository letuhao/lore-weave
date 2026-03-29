"""Tests for the outputs CRUD router."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from tests.conftest import TEST_SESSION_ID, TEST_USER_ID, make_output_record


class TestListSessionOutputs:
    @pytest.mark.asyncio
    async def test_list_outputs_empty(self, client, mock_pool):
        mock_pool.fetchval.return_value = True  # session exists
        mock_pool.fetch.return_value = []
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}/outputs")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    @pytest.mark.asyncio
    async def test_list_outputs_with_items(self, client, mock_pool):
        mock_pool.fetchval.return_value = True
        mock_pool.fetch.return_value = [make_output_record(), make_output_record(output_id=str(uuid4()))]
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}/outputs")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_outputs_session_not_found(self, client, mock_pool):
        mock_pool.fetchval.return_value = None
        resp = await client.get(f"/v1/chat/sessions/{uuid4()}/outputs")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_outputs_filter_by_type(self, client, mock_pool):
        mock_pool.fetchval.return_value = True
        mock_pool.fetch.return_value = [make_output_record(output_type="code")]
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}/outputs?type=code")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1


class TestGetOutput:
    @pytest.mark.asyncio
    async def test_get_output_found(self, client, mock_pool):
        oid = str(uuid4())
        mock_pool.fetchrow.return_value = make_output_record(output_id=oid)
        resp = await client.get(f"/v1/chat/outputs/{oid}")
        assert resp.status_code == 200
        assert resp.json()["output_id"] == oid

    @pytest.mark.asyncio
    async def test_get_output_not_found(self, client, mock_pool):
        mock_pool.fetchrow.return_value = None
        resp = await client.get(f"/v1/chat/outputs/{uuid4()}")
        assert resp.status_code == 404


class TestPatchOutput:
    @pytest.mark.asyncio
    async def test_patch_output_title(self, client, mock_pool):
        oid = str(uuid4())
        original = make_output_record(output_id=oid)
        updated = make_output_record(output_id=oid, title="New Title")
        mock_pool.fetchrow.side_effect = [original, updated]

        resp = await client.patch(f"/v1/chat/outputs/{oid}", json={"title": "New Title"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "New Title"

    @pytest.mark.asyncio
    async def test_patch_output_not_found(self, client, mock_pool):
        mock_pool.fetchrow.return_value = None
        resp = await client.patch(f"/v1/chat/outputs/{uuid4()}", json={"title": "X"})
        assert resp.status_code == 404


class TestDeleteOutput:
    @pytest.mark.asyncio
    async def test_delete_output_success(self, client, mock_pool):
        mock_pool.execute.return_value = "DELETE 1"
        resp = await client.delete(f"/v1/chat/outputs/{uuid4()}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_output_not_found(self, client, mock_pool):
        mock_pool.execute.return_value = "DELETE 0"
        resp = await client.delete(f"/v1/chat/outputs/{uuid4()}")
        assert resp.status_code == 404


class TestDownloadOutput:
    @pytest.mark.asyncio
    async def test_download_text_output(self, client, mock_pool):
        oid = str(uuid4())
        mock_pool.fetchrow.return_value = make_output_record(
            output_id=oid, content_text="print('hello')", file_name="script.py",
        )
        resp = await client.get(f"/v1/chat/outputs/{oid}/download")
        assert resp.status_code == 200
        assert resp.text == "print('hello')"
        assert "script.py" in resp.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_download_text_default_filename(self, client, mock_pool):
        oid = str(uuid4())
        mock_pool.fetchrow.return_value = make_output_record(
            output_id=oid, content_text="data", file_name=None,
        )
        resp = await client.get(f"/v1/chat/outputs/{oid}/download")
        assert resp.status_code == 200
        assert "output.txt" in resp.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    @patch("app.routers.outputs.generate_presigned_url", new_callable=AsyncMock)
    async def test_download_binary_redirects_to_minio(self, mock_presign, client, mock_pool):
        oid = str(uuid4())
        mock_pool.fetchrow.return_value = make_output_record(
            output_id=oid, content_text=None, storage_key="chat/artifacts/file.bin",
        )
        mock_presign.return_value = "https://minio.local/presigned-url"
        resp = await client.get(f"/v1/chat/outputs/{oid}/download", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "https://minio.local/presigned-url"
        mock_presign.assert_awaited_once_with("chat/artifacts/file.bin")

    @pytest.mark.asyncio
    async def test_download_no_content(self, client, mock_pool):
        oid = str(uuid4())
        mock_pool.fetchrow.return_value = make_output_record(
            output_id=oid, content_text=None, storage_key=None,
        )
        resp = await client.get(f"/v1/chat/outputs/{oid}/download")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_download_not_found(self, client, mock_pool):
        mock_pool.fetchrow.return_value = None
        resp = await client.get(f"/v1/chat/outputs/{uuid4()}/download")
        assert resp.status_code == 404


class TestExportSession:
    @pytest.mark.asyncio
    async def test_export_markdown(self, client, mock_pool):
        mock_pool.fetchval.return_value = "My Session"
        mock_pool.fetch.return_value = [
            {"role": "user", "content": "Hi", "created_at": "2026-01-01"},
            {"role": "assistant", "content": "Hello!", "created_at": "2026-01-01"},
        ]
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}/export")
        assert resp.status_code == 200
        assert "**User**" in resp.text
        assert "**Assistant**" in resp.text
        assert "chat_export.md" in resp.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_export_json(self, client, mock_pool):
        mock_pool.fetchval.return_value = "My Session"
        mock_pool.fetch.return_value = [
            {"role": "user", "content": "Hi", "created_at": "2026-01-01"},
        ]
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}/export?format=json")
        assert resp.status_code == 200
        assert "chat_export.json" in resp.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_export_session_not_found(self, client, mock_pool):
        mock_pool.fetchval.return_value = None
        resp = await client.get(f"/v1/chat/sessions/{uuid4()}/export")
        assert resp.status_code == 404
