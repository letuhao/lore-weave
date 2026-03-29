"""Tests for MinIO storage client (mocked boto3)."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch
from io import BytesIO

import pytest

# Patch settings before importing minio_client
import os
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests")


class TestMinIOClient:
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear the lru_cache between tests."""
        from app.storage.minio_client import _s3_client
        _s3_client.cache_clear()
        yield
        _s3_client.cache_clear()

    @pytest.mark.asyncio
    @patch("app.storage.minio_client.boto3")
    async def test_upload_file(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        from app.storage.minio_client import upload_file

        data = BytesIO(b"test data")
        result = await upload_file("test/key.bin", data, "application/pdf")

        assert result == "test/key.bin"
        mock_client.upload_fileobj.assert_called_once()
        call_args = mock_client.upload_fileobj.call_args
        assert call_args.args[2] == "test/key.bin"  # key

    @pytest.mark.asyncio
    @patch("app.storage.minio_client.boto3")
    async def test_generate_presigned_url(self, mock_boto3):
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "https://minio/presigned"
        mock_boto3.client.return_value = mock_client

        from app.storage.minio_client import generate_presigned_url

        url = await generate_presigned_url("test/key.bin", expiry=600)
        assert url == "https://minio/presigned"
        mock_client.generate_presigned_url.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.storage.minio_client.boto3")
    async def test_delete_object(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        from app.storage.minio_client import delete_object

        await delete_object("test/key.bin")
        mock_client.delete_object.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.storage.minio_client.boto3")
    async def test_ensure_bucket_creates_when_missing(self, mock_boto3):
        mock_client = MagicMock()
        mock_client.exceptions.NoSuchBucket = type("NoSuchBucket", (Exception,), {})
        mock_client.head_bucket.side_effect = mock_client.exceptions.NoSuchBucket()
        mock_boto3.client.return_value = mock_client

        from app.storage.minio_client import ensure_bucket

        await ensure_bucket()
        mock_client.create_bucket.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.storage.minio_client.boto3")
    async def test_ensure_bucket_noop_when_exists(self, mock_boto3):
        mock_client = MagicMock()
        mock_client.head_bucket.return_value = {}
        mock_boto3.client.return_value = mock_client

        from app.storage.minio_client import ensure_bucket

        await ensure_bucket()
        mock_client.create_bucket.assert_not_called()
