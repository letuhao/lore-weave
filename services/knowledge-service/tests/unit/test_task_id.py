"""P2 — tests for compute_task_id (D2)."""

from __future__ import annotations

from app.jobs.task_id import compute_task_id


def test_same_inputs_same_hash():
    a = compute_task_id("alice ran", "entity", "v1-abcdef01", "model-uuid")
    b = compute_task_id("alice ran", "entity", "v1-abcdef01", "model-uuid")
    assert a == b


def test_different_text_different_hash():
    a = compute_task_id("alice ran", "entity", "v1-abcdef01", "m")
    b = compute_task_id("bob walked", "entity", "v1-abcdef01", "m")
    assert a != b


def test_different_op_different_hash():
    a = compute_task_id("alice ran", "entity", "v1-abcdef01", "m")
    b = compute_task_id("alice ran", "relation", "v1-abcdef01", "m")
    assert a != b


def test_different_extractor_version_different_hash():
    """D2 implicit invalidation property."""
    a = compute_task_id("alice ran", "entity", "v1-abcdef01", "m")
    b = compute_task_id("alice ran", "entity", "v1-99999999", "m")
    assert a != b


def test_different_model_ref_different_hash():
    """SR-2 fix — model_ref part of hash to prevent cross-model cache poisoning."""
    a = compute_task_id("alice ran", "entity", "v1-abcdef01", "qwen-uuid")
    b = compute_task_id("alice ran", "entity", "v1-abcdef01", "gemma-uuid")
    assert a != b


def test_task_id_case_insensitive_model_ref():
    """M2 regression-lock: UPPERCASE vs lowercase model_ref UUID -> same hash."""
    upper = compute_task_id(
        "alice ran", "entity", "v1-abcdef01",
        "019DC3DF-7CC5-7E6A-8B27-1344E148BF7C",
    )
    lower = compute_task_id(
        "alice ran", "entity", "v1-abcdef01",
        "019dc3df-7cc5-7e6a-8b27-1344e148bf7c",
    )
    assert upper == lower


def test_task_id_case_insensitive_op():
    """M2 — op.lower() normalization."""
    upper = compute_task_id("x", "ENTITY", "v1-abc", "m")
    lower = compute_task_id("x", "entity", "v1-abc", "m")
    assert upper == lower


def test_task_id_format_is_sha256_hex():
    """64-char lowercase hex."""
    h = compute_task_id("x", "entity", "v1-abc", "m")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)
