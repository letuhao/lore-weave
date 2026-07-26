"""Phase 5e-α + 5f tests for the video-gen-service /generate route.

Pattern: mock the loreweave_llm Client.generate_video method directly
on the app.routers.generate.Client attribute. The migrated route
constructs a Client instance per request; we replace the class with
a MagicMock that returns a fake VideoGenResult (or raises an LLM*
error class) to drive each test case.

Coverage scope:
  - Happy path: SDK called with expected args, MinIO upload mocked,
    response shape correct
  - 5 error class → HTTP status mappings
  - _aspect_to_size pure-function regression-lock (/review-impl(DESIGN) LOW#3)
  - non-default aspect ratio reaches the SDK (/review-impl(BUILD) MED#1)
  - Phase 5f G3: JWT verification — bad signature, expired, missing
    header, alg:none downgrade all return 401
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# The platform user `sub` is always a UUID (auth-service subjects) — the shared
# loreweave_authn verifier enforces that, so test tokens must use a UUID id.
TEST_USER = "00000000-0000-0000-0000-0000000000aa"


# ──────────────────────────────────────────────────────────────────────
# _aspect_to_size — pure function unit test (/review-impl(DESIGN) LOW#3)
# ──────────────────────────────────────────────────────────────────────


def test_aspect_to_size_mapping():
    """_aspect_to_size MUST return the documented mapping; default
    "1920x1080" for unknown aspect strings. Regression-lock against
    accidental mapping drift.
    """
    from app.routers.generate import _aspect_to_size

    assert _aspect_to_size("16:9") == "1920x1080"
    assert _aspect_to_size("9:16") == "1080x1920"
    assert _aspect_to_size("1:1") == "1080x1080"
    assert _aspect_to_size("4:3") == "1440x1080"
    assert _aspect_to_size("3:4") == "1080x1440"
    # Unknown → 1920x1080 default
    assert _aspect_to_size("21:9") == "1920x1080"
    assert _aspect_to_size("") == "1920x1080"


# ──────────────────────────────────────────────────────────────────────
# Helper — install a mocked Client class into app.routers.generate
# ──────────────────────────────────────────────────────────────────────


def _make_mock_client(generate_video_behavior):
    """Build a MagicMock that mirrors the Client interface used by
    generate.py. `generate_video_behavior` is either a coroutine fn
    or an awaitable side_effect (e.g., side_effect=LLMQuotaExceeded("..."))
    that drives the test case.
    """
    mock_client_instance = MagicMock()
    mock_client_instance.generate_video = AsyncMock(side_effect=generate_video_behavior) \
        if not callable(generate_video_behavior) or isinstance(generate_video_behavior, type) \
        else AsyncMock(side_effect=generate_video_behavior)
    mock_client_instance.aclose = AsyncMock()
    mock_client_cls = MagicMock(return_value=mock_client_instance)
    return mock_client_cls, mock_client_instance


# ──────────────────────────────────────────────────────────────────────
# Case 1 — happy path
# ──────────────────────────────────────────────────────────────────────


def test_generate_happy_path_uses_sdk_not_direct_httpx(client, jwt_for_user):
    """SDK call returns a VideoGenResult with a URL; the route fetches
    that URL (mocked httpx.AsyncClient.get), uploads to MinIO (mocked
    get_minio + put_object), records usage (mocked record_usage), and
    returns GenerateResponse with the MinIO-presigned URL.
    """
    from loreweave_llm import VideoGenResult, VideoGenDataItem

    fake_result = VideoGenResult(
        created=1700000000,
        data=[VideoGenDataItem(url="https://cdn.example/video.mp4")],
    )

    mock_dl_resp = MagicMock()
    mock_dl_resp.status_code = 200
    mock_dl_resp.content = b"x" * 1024  # fake mp4 bytes
    mock_dl_resp.headers = {"content-type": "video/mp4"}

    mock_minio = MagicMock()
    mock_minio.put_object = MagicMock(return_value=None)

    async def _generate_video_ok(**kwargs):
        # Verify the SDK was called with expected wire shape
        assert kwargs["prompt"] == "a serene mountain lake at dawn"
        assert kwargs["model_source"] == "user_model"
        assert kwargs["model_ref"] == "019d5e3c-1234-7890-abcd-1344e148bf7c"
        assert kwargs["size"] == "1920x1080"  # 16:9 default
        assert kwargs["duration"] == 5
        return fake_result

    mock_client_cls, _ = _make_mock_client(_generate_video_ok)

    async def _async_get(*args, **kwargs):
        return mock_dl_resp

    mock_http_ctx = MagicMock()
    mock_http_ctx.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=mock_dl_resp)))
    mock_http_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("app.routers.generate.Client", mock_client_cls), \
         patch("app.routers.generate.get_minio", return_value=mock_minio), \
         patch("app.routers.generate.record_usage", AsyncMock(return_value=None)), \
         patch("app.routers.generate.httpx.AsyncClient", return_value=mock_http_ctx):
        resp = client.post(
            "/v1/video-gen/generate",
            json={
                "prompt": "a serene mountain lake at dawn",
                "model_source": "user_model",
                "model_ref": "019d5e3c-1234-7890-abcd-1344e148bf7c",
                "duration_seconds": 5,
                "aspect_ratio": "16:9",
            },
            headers={"Authorization": f"Bearer {jwt_for_user(TEST_USER)}"},
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["video_url"].startswith(f"http://localhost:9000/loreweave-media/video-gen/{TEST_USER}/")
    assert body["video_url"].endswith(".mp4")
    assert body["content_type"] == "video/mp4"
    assert body["size_bytes"] == 1024

    # Verify SDK Client was actually constructed (not bypassed)
    mock_client_cls.assert_called_once()
    # MinIO put_object called once
    mock_minio.put_object.assert_called_once()


# ──────────────────────────────────────────────────────────────────────
# Cases 2-6 — error class → HTTP status mappings
# ──────────────────────────────────────────────────────────────────────


def _run_with_sdk_error(client, jwt_for_user, exc_class, exc_msg, *, prompt="a cat"):
    """Drive a single /generate request with the SDK raising exc_class(exc_msg)."""
    mock_client_cls, _ = _make_mock_client(exc_class(exc_msg))
    with patch("app.routers.generate.Client", mock_client_cls):
        return client.post(
            "/v1/video-gen/generate",
            json={
                "prompt": prompt,
                "model_source": "user_model",
                "model_ref": "019d5e3c-1234-7890-abcd-1344e148bf7c",
                "duration_seconds": 5,
                "aspect_ratio": "16:9",
            },
            headers={"Authorization": f"Bearer {jwt_for_user(TEST_USER)}"},
        )


def test_generate_quota_exceeded_returns_402(client, jwt_for_user):
    from loreweave_llm import LLMQuotaExceeded
    resp = _run_with_sdk_error(client, jwt_for_user, LLMQuotaExceeded, "user out of credits")
    assert resp.status_code == 402, resp.text
    assert "credits" in resp.json()["detail"]


def test_generate_content_policy_returns_400(client, jwt_for_user):
    from loreweave_llm import LLMVideoContentPolicy
    resp = _run_with_sdk_error(client, jwt_for_user, LLMVideoContentPolicy, "rejected by safety system")
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"].startswith("Content policy:")


def test_generate_model_not_found_returns_404(client, jwt_for_user):
    from loreweave_llm import LLMModelNotFound
    resp = _run_with_sdk_error(client, jwt_for_user, LLMModelNotFound, "user_model not found")
    assert resp.status_code == 404, resp.text


def test_generate_video_generation_failed_returns_502(client, jwt_for_user):
    from loreweave_llm import LLMVideoGenerationFailed
    resp = _run_with_sdk_error(client, jwt_for_user, LLMVideoGenerationFailed, "model failed to load")
    assert resp.status_code == 502, resp.text
    assert "Video generation failed:" in resp.json()["detail"]


def test_generate_rate_limited_returns_429(client, jwt_for_user):
    from loreweave_llm import LLMRateLimited
    resp = _run_with_sdk_error(client, jwt_for_user, LLMRateLimited, "slow down")
    assert resp.status_code == 429, resp.text


# ──────────────────────────────────────────────────────────────────────
# Case 8 — non-default aspect ratio actually flows through _aspect_to_size
# /review-impl(BUILD) MED#1 — the happy-path test uses "16:9" → "1920x1080"
# which is also the fallback value for unknown aspect strings. A hardcoded
# size="1920x1080" in the route would still pass that test. This test
# uses aspect_ratio="9:16" (expected size="1080x1920") so a regression
# that bypasses _aspect_to_size by hardcoding the default fails fast.
# ──────────────────────────────────────────────────────────────────────


def test_generate_non_default_aspect_ratio_reaches_sdk(client, jwt_for_user):
    """aspect_ratio="9:16" MUST produce size="1080x1920" on the SDK call —
    proves _aspect_to_size is invoked, not bypassed.
    """
    from loreweave_llm import VideoGenResult, VideoGenDataItem

    captured: dict[str, str] = {}

    async def _capture_size(**kwargs):
        captured["size"] = kwargs["size"]
        return VideoGenResult(
            created=1700000000,
            data=[VideoGenDataItem(url="https://cdn.example/v.mp4")],
        )

    mock_dl_resp = MagicMock()
    mock_dl_resp.status_code = 200
    mock_dl_resp.content = b"x" * 16
    mock_dl_resp.headers = {"content-type": "video/mp4"}

    mock_minio = MagicMock()
    mock_minio.put_object = MagicMock(return_value=None)

    mock_client_cls, _ = _make_mock_client(_capture_size)

    mock_http_ctx = MagicMock()
    mock_http_ctx.__aenter__ = AsyncMock(
        return_value=MagicMock(get=AsyncMock(return_value=mock_dl_resp))
    )
    mock_http_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("app.routers.generate.Client", mock_client_cls), \
         patch("app.routers.generate.get_minio", return_value=mock_minio), \
         patch("app.routers.generate.record_usage", AsyncMock(return_value=None)), \
         patch("app.routers.generate.httpx.AsyncClient", return_value=mock_http_ctx):
        resp = client.post(
            "/v1/video-gen/generate",
            json={
                "prompt": "a portrait video",
                "model_source": "user_model",
                "model_ref": "019d5e3c-1234-7890-abcd-1344e148bf7c",
                "duration_seconds": 5,
                "aspect_ratio": "9:16",  # NON-default → 1080x1920
            },
            headers={"Authorization": f"Bearer {jwt_for_user(TEST_USER)}"},
        )

    assert resp.status_code == 201, resp.text
    assert captured["size"] == "1080x1920", (
        f"_aspect_to_size('9:16') should produce '1080x1920'; got {captured['size']!r}. "
        "If the route hardcoded '1920x1080' or bypassed _aspect_to_size, this assertion fails."
    )


# ──────────────────────────────────────────────────────────────────────
# Phase 5f G3 — JWT signature verification (HS256)
# extract_user_id now VERIFIES the token. These cases reach extract_user_id
# only — they raise 401 before the route touches the SDK, so no Client
# mock is needed.
# ──────────────────────────────────────────────────────────────────────

_GEN_BODY = {
    "prompt": "anything",
    "model_source": "user_model",
    "model_ref": "019d5e3c-1234-7890-abcd-1344e148bf7c",
    "duration_seconds": 5,
    "aspect_ratio": "16:9",
}


def test_bad_signature_returns_401(client, jwt_for_user):
    """A token signed with the WRONG secret MUST be rejected with 401.

    Phase 5f G3 — the old code base64-decoded the payload without
    verifying the signature, so a forged token sailed through. This
    repurposes the former non-dict-payload test (PyJWT's encode can't
    even produce a non-dict payload, so that edge collapses into
    InvalidTokenError).
    """
    forged = jwt_for_user(TEST_USER, secret="a_totally_different_secret_value_32chr")
    resp = client.post(
        "/v1/video-gen/generate",
        json=_GEN_BODY,
        headers={"Authorization": f"Bearer {forged}"},
    )
    assert resp.status_code == 401, resp.text
    assert resp.json()["detail"] == "Invalid token"


def test_expired_token_returns_401(client, jwt_for_user):
    """A correctly-signed but EXPIRED token MUST return 401. P3 (SDK-first): the
    shared verifier returns a UNIFORM 'Invalid token' for every bad-token mode
    (expired/forged/malformed) — deliberately no oracle distinguishing them."""
    import time

    expired = jwt_for_user(TEST_USER, exp=int(time.time()) - 3600)
    resp = client.post(
        "/v1/video-gen/generate",
        json=_GEN_BODY,
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert resp.status_code == 401, resp.text
    assert resp.json()["detail"] == "Invalid token"


def test_missing_authorization_returns_401(client):
    """No Authorization header at all → 401 'Authorization required'."""
    resp = client.post("/v1/video-gen/generate", json=_GEN_BODY)
    assert resp.status_code == 401, resp.text
    assert resp.json()["detail"] == "Authorization required"


def test_alg_none_token_rejected(client):
    """A hand-crafted `alg:none` token MUST be rejected — regression-lock
    on the `algorithms=["HS256"]` allow-list. This is the exact downgrade
    attack the pre-5f unverified base64 decode accepted.
    """
    import base64
    import json

    header = base64.urlsafe_b64encode(
        b'{"alg":"none","typ":"JWT"}'
    ).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": "attacker"}).encode()
    ).rstrip(b"=").decode()
    alg_none_token = f"{header}.{payload}."  # empty signature

    resp = client.post(
        "/v1/video-gen/generate",
        json=_GEN_BODY,
        headers={"Authorization": f"Bearer {alg_none_token}"},
    )
    assert resp.status_code == 401, resp.text
    assert resp.json()["detail"] == "Invalid token"
