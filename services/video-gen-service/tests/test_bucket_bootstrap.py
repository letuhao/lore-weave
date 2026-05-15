"""Phase 5f G4 — behavioral tests for the MinIO bucket bootstrap.

The bug (G4): video-gen-service created the shared `loreweave-media`
bucket without a public-read policy, so if it won the create race the
bucket was private and generated video URLs 403'd in the browser.

These tests exercise `_ensure_bucket` / `bootstrap_minio` directly with
a mock Minio client — no real MinIO instance needed (the logic is pure
orchestration). /review-impl(DESIGN) MED#4.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from minio.error import S3Error

from app.routers import generate

# The `_bucket_ready` flag is reset around every test by the autouse
# `_reset_bucket_ready` fixture in conftest.py.


def _s3_error() -> S3Error:
    """A minimal real S3Error — e.g. the BucketAlreadyOwnedByYou raised
    when a concurrent creator (book-service) won the create race."""
    return S3Error(
        code="BucketAlreadyOwnedByYou",
        message="bucket already owned",
        resource="/loreweave-media",
        request_id="test-req",
        host_id="test-host",
        response=MagicMock(),
    )


def test_ensure_bucket_sets_public_read_policy():
    """Bucket absent → make_bucket once + set_bucket_policy with the
    public-read policy + `_bucket_ready` flips True."""
    mc = MagicMock()
    mc.bucket_exists.return_value = False
    with patch("app.routers.generate.get_minio", return_value=mc):
        generate._ensure_bucket()

    mc.make_bucket.assert_called_once_with(generate.MINIO_BUCKET)
    mc.set_bucket_policy.assert_called_once()
    bucket_arg, policy_arg = mc.set_bucket_policy.call_args[0]
    assert bucket_arg == generate.MINIO_BUCKET
    # The policy MUST be valid JSON — substring checks alone pass on a
    # malformed string (/review-impl(BUILD) LOW#2).
    parsed = json.loads(policy_arg)
    stmt = parsed["Statement"][0]
    assert stmt["Effect"] == "Allow"
    assert stmt["Action"] == ["s3:GetObject"]
    assert stmt["Resource"] == [f"arn:aws:s3:::{generate.MINIO_BUCKET}/*"]
    assert generate._bucket_ready is True


def test_ensure_bucket_existing_bucket_still_sets_policy():
    """Bucket already exists → make_bucket NOT called, but the public-read
    policy is STILL asserted — this is the G4 fix: even when another
    service created the bucket, video-gen-service re-asserts public-read."""
    mc = MagicMock()
    mc.bucket_exists.return_value = True
    with patch("app.routers.generate.get_minio", return_value=mc):
        generate._ensure_bucket()

    mc.make_bucket.assert_not_called()
    mc.set_bucket_policy.assert_called_once()
    assert generate._bucket_ready is True


def test_ensure_bucket_tolerates_make_bucket_race():
    """make_bucket raises S3Error but a re-check shows the bucket now
    exists (a concurrent creator won) → no exception, policy still set."""
    mc = MagicMock()
    # 1st bucket_exists → False (triggers make_bucket); 2nd (re-check) → True
    mc.bucket_exists.side_effect = [False, True]
    mc.make_bucket.side_effect = _s3_error()
    with patch("app.routers.generate.get_minio", return_value=mc):
        generate._ensure_bucket()  # must NOT raise

    mc.set_bucket_policy.assert_called_once()
    assert generate._bucket_ready is True


def test_ensure_bucket_propagates_genuine_make_bucket_failure():
    """make_bucket raises S3Error AND the re-check still shows no bucket
    → the error is genuine and propagates; `_bucket_ready` stays False.
    Regression-lock on /review-impl(DESIGN) MED#2 — the failure must NOT
    be blanket-swallowed, and set_bucket_policy must not run against a
    nonexistent bucket."""
    mc = MagicMock()
    mc.bucket_exists.side_effect = [False, False]  # never exists
    mc.make_bucket.side_effect = _s3_error()
    with patch("app.routers.generate.get_minio", return_value=mc):
        with pytest.raises(S3Error):
            generate._ensure_bucket()

    mc.set_bucket_policy.assert_not_called()
    assert generate._bucket_ready is False


def test_bootstrap_minio_swallows_errors():
    """bootstrap_minio is best-effort — a failure in _ensure_bucket is
    logged, not raised, so app startup never crashes on a MinIO outage."""
    with patch(
        "app.routers.generate._ensure_bucket",
        side_effect=RuntimeError("minio down"),
    ):
        generate.bootstrap_minio()  # must NOT raise

    assert generate._bucket_ready is False


def test_ensure_bucket_ready_short_circuits_when_ready():
    """When `_bucket_ready` is True, ensure_bucket_ready() is a no-op —
    proves the G2 per-request hot-path short-circuit (no MinIO call on
    every request). /review-impl(BUILD) MED#1."""
    generate._bucket_ready = True
    mc = MagicMock()
    with patch("app.routers.generate.get_minio", return_value=mc):
        generate.ensure_bucket_ready()

    mc.bucket_exists.assert_not_called()
    mc.make_bucket.assert_not_called()
    mc.set_bucket_policy.assert_not_called()


def test_ensure_bucket_ready_self_heals_when_not_ready():
    """When `_bucket_ready` is False (startup bootstrap failed),
    ensure_bucket_ready() runs the full _ensure_bucket — the self-heal
    that the /review-impl(DESIGN) HIGH#1 fix introduced. MED#1."""
    generate._bucket_ready = False
    mc = MagicMock()
    mc.bucket_exists.return_value = True
    with patch("app.routers.generate.get_minio", return_value=mc):
        generate.ensure_bucket_ready()

    mc.set_bucket_policy.assert_called_once()
    assert generate._bucket_ready is True
