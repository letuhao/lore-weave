"""MinIO (S3-compatible) storage client for binary chat output artifacts."""
from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import BinaryIO

import boto3
from botocore.config import Config as BotoConfig

from app.config import settings

_PRESIGN_EXPIRY = 3600  # 1 hour


@lru_cache(maxsize=1)
def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=f"{'https' if settings.minio_use_ssl else 'http'}://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )


@lru_cache(maxsize=1)
def _presign_client():
    """S3 client for generating browser-accessible presigned URLs.
    Uses MINIO_EXTERNAL_URL (e.g. http://localhost:9123) instead of internal endpoint."""
    external = settings.minio_external_url
    if not external:
        return _s3_client()  # Fallback to internal if not configured
    return boto3.client(
        "s3",
        endpoint_url=external,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )


async def ensure_bucket() -> None:
    """Create the output bucket if it doesn't exist (idempotent)."""
    client = _s3_client()
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(
            None, lambda: client.head_bucket(Bucket=settings.minio_bucket),
        )
    except client.exceptions.NoSuchBucket:
        await loop.run_in_executor(
            None, lambda: client.create_bucket(Bucket=settings.minio_bucket),
        )
    except Exception:
        # ClientError for 404 varies between MinIO and AWS
        await loop.run_in_executor(
            None, lambda: client.create_bucket(Bucket=settings.minio_bucket),
        )


async def upload_file(
    key: str,
    data: BinaryIO,
    content_type: str = "application/octet-stream",
) -> str:
    """Upload binary data to MinIO. Returns the storage key."""
    client = _s3_client()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: client.upload_fileobj(
            data,
            settings.minio_bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        ),
    )
    return key


async def generate_presigned_url(key: str, expiry: int = _PRESIGN_EXPIRY) -> str:
    """Generate a presigned download URL for an object (browser-accessible)."""
    client = _presign_client()
    loop = asyncio.get_running_loop()
    url = await loop.run_in_executor(
        None,
        lambda: client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.minio_bucket, "Key": key},
            ExpiresIn=expiry,
        ),
    )
    return url


async def delete_object(key: str) -> None:
    """Delete an object from MinIO."""
    client = _s3_client()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: client.delete_object(Bucket=settings.minio_bucket, Key=key),
    )
