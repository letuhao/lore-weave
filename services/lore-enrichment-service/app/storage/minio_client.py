"""MinIO (S3-compatible) storage for mode-F uploaded files.

Mirrors chat-service's `minio_client.py` (boto3 + run_in_executor so the blocking
S3 calls don't stall the event loop). The raw uploaded bytes live here; the
extracted text is persisted in `enrichment_upload`. Bucket is per-service
(`settings.minio_bucket`, default `lore-enrichment-uploads`).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import BinaryIO

import boto3
from botocore.config import Config as BotoConfig

from app.config import settings


@dataclass(frozen=True)
class StoredObject:
    """One object in the uploads bucket (key + last-modified), for the reaper's
    orphan sweep (an object whose ``enrichment_upload`` row never landed)."""

    key: str
    last_modified: datetime


@lru_cache(maxsize=1)
def _s3_client():
    scheme = "https" if settings.minio_use_ssl else "http"
    return boto3.client(
        "s3",
        endpoint_url=f"{scheme}://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )


async def ensure_bucket() -> None:
    """Create the uploads bucket if absent (idempotent). Called at startup."""
    client = _s3_client()
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, lambda: client.head_bucket(Bucket=settings.minio_bucket))
    except Exception:  # noqa: BLE001 — 404 shape varies MinIO/AWS; create on any miss
        await loop.run_in_executor(None, lambda: client.create_bucket(Bucket=settings.minio_bucket))


async def upload_file(key: str, data: BinaryIO, content_type: str = "application/octet-stream") -> str:
    """Upload binary data to MinIO under `key`. Returns the storage key."""
    client = _s3_client()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: client.upload_fileobj(
            data, settings.minio_bucket, key, ExtraArgs={"ContentType": content_type}
        ),
    )
    return key


async def delete_object(key: str) -> None:
    """Best-effort delete of an object (cleanup)."""
    client = _s3_client()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: client.delete_object(Bucket=settings.minio_bucket, Key=key))


async def list_objects() -> list[StoredObject]:
    """List every object in the uploads bucket (key + LastModified). Paginated so
    a large bucket is fully enumerated. Used by the reaper's orphan sweep; returns
    [] when the bucket is empty or absent (never raises on a clean miss)."""
    client = _s3_client()
    loop = asyncio.get_running_loop()

    def _list() -> list[StoredObject]:
        out: list[StoredObject] = []
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=settings.minio_bucket):
            for obj in page.get("Contents", []):
                out.append(StoredObject(key=obj["Key"], last_modified=obj["LastModified"]))
        return out

    return await loop.run_in_executor(None, _list)
