"""Object-storage seam for cold-archiving extraction raw-output bodies (CACHE/M6,
D-RAWCACHE-MINIO-OFFLOAD).

`extraction_raw_outputs.raw_response` is the verbatim LLM text — a debug/provenance
artifact, never read on the replay hot path (replay uses `parsed_entities`). It is also the
table's bulkiest column. After a short hot window the offload sweep moves each body to object
storage and NULLs the DB column, keeping the row (and its parse) light.

The store is a Protocol so the sweep + retrieval are testable with an in-memory fake and the
physical backend can be swapped (the same deferred-re-home spirit as the cache itself,
`D-EXTRACTION-REHOME-KNOWLEDGE`). `MinioBlobStore` mirrors chat-service's boto3 client (the
established repo pattern): a sync boto3 client wrapped on the default executor. `get_blob_store`
returns None when MinIO is unconfigured (blank `minio_secret_key`) — offload is then simply
OFF, with no boot dependency on object storage.
"""
from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Protocol, runtime_checkable

from ..config import settings

log = logging.getLogger(__name__)


@runtime_checkable
class RawBlobStore(Protocol):
    """Minimal async blob store: archive a body, fetch it back, delete it. `put` returns the
    storage URI to persist on the row; `get` returns None on a missing object."""

    async def put(self, key: str, data: bytes) -> str: ...
    async def get(self, uri: str) -> bytes | None: ...
    async def delete(self, uri: str) -> None: ...


class InMemoryBlobStore:
    """Test/standalone store — keeps blobs in a dict. NOT for production (no durability)."""

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes) -> str:
        self._blobs[key] = data
        return key

    async def get(self, uri: str) -> bytes | None:
        return self._blobs.get(uri)

    async def delete(self, uri: str) -> None:
        self._blobs.pop(uri, None)


@lru_cache(maxsize=1)
def _s3_client():
    import boto3
    from botocore.config import Config as BotoConfig

    return boto3.client(
        "s3",
        endpoint_url=f"{'https' if settings.minio_use_ssl else 'http'}://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )


class MinioBlobStore:
    """S3/MinIO-backed store (boto3), mirroring chat-service's storage client. Sync boto3 calls
    are wrapped on the default executor so they don't block the event loop. The bucket is
    ensured once per process (idempotent)."""

    def __init__(self, bucket: str) -> None:
        self._bucket = bucket
        self._bucket_ready = False

    async def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        client = _s3_client()
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, lambda: client.head_bucket(Bucket=self._bucket))
        except Exception:
            # 404 shape differs between MinIO and AWS — just attempt create (idempotent enough;
            # a concurrent create races to a BucketAlreadyOwnedByYou, which we tolerate).
            try:
                await loop.run_in_executor(None, lambda: client.create_bucket(Bucket=self._bucket))
            except Exception as exc:  # noqa: BLE001
                log.debug("blobstore: ensure_bucket create raced/failed (%s)", exc)
        self._bucket_ready = True

    async def put(self, key: str, data: bytes) -> str:
        await self._ensure_bucket()
        client = _s3_client()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType="text/plain; charset=utf-8"),
        )
        return key

    async def get(self, uri: str) -> bytes | None:
        client = _s3_client()
        loop = asyncio.get_running_loop()
        try:
            resp = await loop.run_in_executor(
                None, lambda: client.get_object(Bucket=self._bucket, Key=uri))
            return await loop.run_in_executor(None, lambda: resp["Body"].read())
        except Exception as exc:  # noqa: BLE001 — missing object / transport ⇒ None
            log.debug("blobstore: get failed for %s (%s)", uri, exc)
            return None

    async def delete(self, uri: str) -> None:
        client = _s3_client()
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None, lambda: client.delete_object(Bucket=self._bucket, Key=uri))
        except Exception as exc:  # noqa: BLE001 — best-effort; a leaked object is not fatal
            log.debug("blobstore: delete failed for %s (%s)", uri, exc)


def get_blob_store() -> RawBlobStore | None:
    """The configured production store, or None when MinIO is not configured (blank secret) —
    offload is then disabled with no boot dependency on object storage."""
    if not settings.minio_secret_key:
        return None
    return MinioBlobStore(settings.minio_bucket)
