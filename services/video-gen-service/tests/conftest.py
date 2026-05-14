"""Shared test fixtures for video-gen-service. Phase 5e-α — first
test suite for this service.

Sets up required env vars BEFORE app modules import (Settings would
otherwise fail at module load with pydantic ValidationError).
"""

from __future__ import annotations

import os

# Set required env vars BEFORE any app import. Mirror chat-service
# conftest pattern.
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test_internal_token")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("MINIO_EXTERNAL_URL", "http://localhost:9000")
os.environ.setdefault("PROVIDER_REGISTRY_INTERNAL_URL", "http://provider-registry.test")
os.environ.setdefault("USAGE_BILLING_SERVICE_URL", "")  # disable billing in tests
os.environ.setdefault("MINIO_ENDPOINT", "minio.test:9000")

import base64
import json
from typing import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient against the FastAPI app. Imports happen inside the
    fixture (not at module level) so env setup above takes effect first.
    """
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def jwt_for_user() -> callable:
    """Returns a function that produces a minimal unsigned JWT with a
    given user_id (sub). video-gen-service's extract_user_id decodes
    payload only — no signature verification.
    """
    def _make(user_id: str) -> str:
        header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(
            json.dumps({"sub": user_id}).encode()
        ).rstrip(b"=").decode()
        return f"{header}.{payload}.sig"
    return _make
