"""Shared test fixtures for video-gen-service.

Phase 5e-α — first test suite for this service.
Phase 5f — JWTs are now signature-verified (HS256), so test tokens must
be properly signed; the `client` fixture neutralizes the MinIO lifespan
bootstrap so tests don't hit a real MinIO host.

Sets up required env vars BEFORE app modules import (Settings would
otherwise fail at module load with pydantic ValidationError).
"""

from __future__ import annotations

import os
import time

# A realistic >=32-char secret (auth-service requires that length). Used
# below to sign test JWTs.
TEST_JWT_SECRET = "test_jwt_secret_at_least_32_chars_long_x"

# Set required env vars BEFORE any app import. Mirror chat-service
# conftest pattern.
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test_internal_token")
os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("MINIO_EXTERNAL_URL", "http://localhost:9000")
os.environ.setdefault("PROVIDER_REGISTRY_INTERNAL_URL", "http://provider-registry.test")
os.environ.setdefault("USAGE_BILLING_SERVICE_URL", "")  # disable billing in tests
os.environ.setdefault("MINIO_ENDPOINT", "minio.test:9000")

# The secret the app's Settings will actually verify against — capture
# whatever ended up in the environment (our default, or a pre-existing
# value) so the test signer and the app verifier always agree.
EFFECTIVE_JWT_SECRET = os.environ["JWT_SECRET"]

from typing import Callable, Iterator, Optional
from unittest.mock import patch

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_bucket_ready():
    """Reset the module-level `_bucket_ready` flag around every test so
    MinIO-bootstrap state never leaks between tests or test files
    (/review-impl(BUILD) LOW#5).
    """
    from app.routers import generate
    generate._bucket_ready = False
    yield
    generate._bucket_ready = False


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient against the FastAPI app.

    Imports happen inside the fixture (not at module level) so the env
    setup above takes effect first. `bootstrap_minio` is patched out so
    the FastAPI lifespan startup does not attempt a real connection to
    the bogus `minio.test` host (/review-impl(DESIGN) MED#3). Tests that
    exercise the bucket logic call it directly with a mock Minio — see
    test_bucket_bootstrap.py.
    """
    with patch("app.main.bootstrap_minio"):
        from app.main import app
        with TestClient(app) as c:
            yield c


@pytest.fixture
def jwt_for_user() -> Callable[..., str]:
    """Returns a function that produces a real HS256-signed JWT.

    Phase 5f: video-gen-service now verifies the signature, so test
    tokens must be signed with the same secret the app reads. Optional
    kwargs:
      - `exp`:    set an `exp` claim (epoch seconds) — pass a past value
                  to drive the expired-token test.
      - `secret`: sign with a different secret — drives the
                  bad-signature test.
    """
    def _make(user_id: str, *, exp: Optional[int] = None, secret: Optional[str] = None) -> str:
        # The shared loreweave_authn verifier REQUIRES `exp` (real auth-service tokens
        # always carry it), so default to a valid future exp; the expired-token test
        # passes an explicit past value.
        now = int(time.time())
        payload: dict = {"sub": user_id, "iat": now, "exp": exp if exp is not None else now + 300}
        return pyjwt.encode(payload, secret or EFFECTIVE_JWT_SECRET, algorithm="HS256")
    return _make
