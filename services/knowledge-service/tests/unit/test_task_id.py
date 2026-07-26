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


# --- D-KG-LB-CACHE-SCHEMA-KEY: schema-aware cache key ---------------------

import hashlib  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from app.jobs.task_id import _SEP  # noqa: E402
from app.extraction.pass2_orchestrator import _p2_schema_key  # noqa: E402

_SK_ARGS = ("the priestess worshipped the storm-god", "entity", "v1-entity-abcd1234", "MODEL-UUID")


def _legacy_hash(text, op, ver, model):
    """The exact pre-change 4-field hash (no schema segment)."""
    payload = f"{text}{_SEP}{op.lower()}{_SEP}{ver}{_SEP}{model.lower()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_empty_schema_key_is_byte_identical_to_legacy():
    # Default (omitted) and explicit "" both reproduce the pre-change hash.
    assert compute_task_id(*_SK_ARGS) == _legacy_hash(*_SK_ARGS)
    assert compute_task_id(*_SK_ARGS, schema_key="") == _legacy_hash(*_SK_ARGS)


def test_non_empty_schema_key_changes_the_hash():
    assert compute_task_id(*_SK_ARGS, schema_key="proj-a@v3") != compute_task_id(*_SK_ARGS)


def test_distinct_schemas_do_not_collide():
    # Same text/op/version/model but three different schemas → three keys.
    a = compute_task_id(*_SK_ARGS, schema_key="proj-a@v3")
    b = compute_task_id(*_SK_ARGS, schema_key="proj-a@v4")  # version bump
    c = compute_task_id(*_SK_ARGS, schema_key="proj-b@v3")  # other project, same version
    assert len({a, b, c}) == 3


def test_same_schema_key_is_stable():
    assert compute_task_id(*_SK_ARGS, schema_key="p@v3") == compute_task_id(*_SK_ARGS, schema_key="p@v3")


def test_schema_key_none_is_empty():
    assert _p2_schema_key(None) == ""


def test_schema_key_prefers_label():
    assert _p2_schema_key(SimpleNamespace(label="1111-2222@v77", schema_version=77)) == "1111-2222@v77"


def test_schema_key_falls_back_to_version_when_label_blank():
    assert _p2_schema_key(SimpleNamespace(label="", schema_version=42)) == "v42"


def test_schema_key_blank_label_no_version_is_empty():
    assert _p2_schema_key(SimpleNamespace(label="", schema_version=None)) == ""
