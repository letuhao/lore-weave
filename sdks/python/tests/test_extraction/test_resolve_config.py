"""B2-A — resolve_effective_config + config_hash + base_default_version."""

from __future__ import annotations

import hashlib
import json

import pytest

from loreweave_extraction import (
    PROMPT_OPS,
    EntityRecoveryConfig,
    PrecisionFilterConfig,
    ResolvedConfig,
    base_default_version,
    config_hash,
    resolve_effective_config,
)


def _globals(**over):
    base = {
        "model_ref": "model-global",
        "model_source": "user_model",
        "precision_filter": PrecisionFilterConfig(
            model_ref="filter-global", categories=("relation",), partial_policy="keep",
        ),
        "entity_recovery": EntityRecoveryConfig(model_ref="recovery-global"),
        "writer_autocreate": True,
    }
    base.update(over)
    return base


# ── empty override = pure global ───────────────────────────────────────

def test_empty_override_mirrors_global():
    rc = resolve_effective_config(global_defaults=_globals(), project_overrides={})
    assert rc.model_ref == "model-global"
    assert rc.model_source == "user_model"
    assert rc.precision_filter is not None
    assert rc.precision_filter.categories == ("relation",)
    assert rc.entity_recovery is not None
    assert rc.writer_autocreate is True
    # every op gets a (default file-hash) version
    assert set(rc.prompt_versions) == set(PROMPT_OPS)
    assert all(not v.startswith("custom-") for v in rc.prompt_versions.values())


def test_none_override_treated_as_empty():
    rc = resolve_effective_config(global_defaults=_globals(), project_overrides=None)
    assert rc.model_ref == "model-global"


# ── hash stability / canonicalization ──────────────────────────────────

def test_config_hash_is_full_sha256_hex():
    rc = resolve_effective_config(global_defaults=_globals(), project_overrides={})
    h = config_hash(rc)
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)


def test_config_hash_stable_within_process():
    g = _globals()
    a = config_hash(resolve_effective_config(global_defaults=g, project_overrides={}))
    b = config_hash(resolve_effective_config(global_defaults=g, project_overrides={}))
    assert a == b


def test_config_hash_pins_sha256_of_canonical_not_pythonhash():
    """Pins the algorithm to sha256-of-canonical-JSON (host-independent).

    Builds an explicit ResolvedConfig (no file-derived prompt_versions, so the
    expected digest is stable across environments), then asserts config_hash
    equals an INDEPENDENT sha256 of the canonical field set. If the impl ever
    used Python's hash() (PYTHONHASHSEED-randomized) or its canonical form
    drifted, this mismatches. Replaces the subprocess seed-variance probe,
    which can't import the package in a fresh interpreter on this Windows host
    (loreweave_llm -> asyncio winsock WinError 10106)."""
    rc = ResolvedConfig(
        model_ref="m",
        model_source="user_model",
        precision_filter=PrecisionFilterConfig(
            model_ref="f", categories=("relation",), partial_policy="keep",
        ),
        entity_recovery=EntityRecoveryConfig(model_ref="r"),
        writer_autocreate=True,
        prompts={},
        prompt_versions={"entity": "v1-entity-aaaaaaaa"},
    )
    canonical = {
        "model_ref": "m",
        "model_source": "user_model",
        "precision_filter": {
            "model_ref": "f", "model_source": "user_model",
            "categories": ["relation"], "partial_policy": "keep",
        },
        "entity_recovery": {"model_ref": "r", "model_source": "user_model"},
        "writer_autocreate": True,
        "prompt_versions": {"entity": "v1-entity-aaaaaaaa"},
    }
    expected = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    assert config_hash(rc) == expected


def test_category_order_does_not_change_hash():
    g = _globals(precision_filter=PrecisionFilterConfig(
        model_ref="f", categories=("entity", "relation", "event"),
    ))
    rc1 = resolve_effective_config(
        global_defaults=g,
        project_overrides={"precision_filter": {"categories": ["event", "entity", "relation"]}},
    )
    rc2 = resolve_effective_config(
        global_defaults=g,
        project_overrides={"precision_filter": {"categories": ["relation", "event", "entity"]}},
    )
    assert config_hash(rc1) == config_hash(rc2)


def test_embedding_model_in_override_is_ignored():
    g = _globals()
    base = config_hash(resolve_effective_config(global_defaults=g, project_overrides={}))
    withemb = config_hash(resolve_effective_config(
        global_defaults=g, project_overrides={"embedding_model": "emb-xyz", "rerank_model": "rk"},
    ))
    assert base == withemb


def test_structural_change_changes_hash():
    g = _globals()
    base = config_hash(resolve_effective_config(global_defaults=g, project_overrides={}))
    changed = config_hash(resolve_effective_config(
        global_defaults=g, project_overrides={"precision_filter": {"categories": ["entity"]}},
    ))
    assert base != changed


# ── precedence ──────────────────────────────────────────────────────────

def test_project_model_overrides_global():
    rc = resolve_effective_config(
        global_defaults=_globals(),
        project_overrides={"llm_model": {"model_ref": "model-project", "model_source": "platform_model"}},
    )
    assert rc.model_ref == "model-project"
    assert rc.model_source == "platform_model"


def test_partial_filter_override_keeps_global_model():
    rc = resolve_effective_config(
        global_defaults=_globals(),
        project_overrides={"precision_filter": {"categories": ["entity", "event"]}},
    )
    assert rc.precision_filter is not None
    # categories from override, model_ref falls through to global filter
    assert set(rc.precision_filter.categories) == {"entity", "event"}
    assert rc.precision_filter.model_ref == "filter-global"


def test_empty_categories_override_falls_through_to_global():
    """LOW-2: explicit categories:[] is falsy → keep global categories (an empty
    tuple would otherwise trip PrecisionFilterConfig's non-empty guard)."""
    rc = resolve_effective_config(
        global_defaults=_globals(precision_filter=PrecisionFilterConfig(
            model_ref="f", categories=("entity", "relation"),
        )),
        project_overrides={"precision_filter": {"categories": []}},
    )
    assert rc.precision_filter is not None
    assert set(rc.precision_filter.categories) == {"entity", "relation"}


def test_filter_disabled_by_override():
    rc = resolve_effective_config(
        global_defaults=_globals(),
        project_overrides={"precision_filter": {"enabled": False}},
    )
    assert rc.precision_filter is None


def test_recovery_disabled_by_override():
    rc = resolve_effective_config(
        global_defaults=_globals(),
        project_overrides={"entity_recovery": {"enabled": False}},
    )
    assert rc.entity_recovery is None


def test_autocreate_override():
    rc = resolve_effective_config(
        global_defaults=_globals(writer_autocreate=True),
        project_overrides={"writer_autocreate": {"enabled": False}},
    )
    assert rc.writer_autocreate is False


def test_filter_enabled_without_model_ref_raises():
    g = _globals(precision_filter=None)
    with pytest.raises(ValueError, match="precision_filter enabled but no model_ref"):
        resolve_effective_config(
            global_defaults=g,
            project_overrides={"precision_filter": {"enabled": True, "categories": ["entity"]}},
        )


# ── prompt override → custom version ─────────────────────────────────────

def test_prompt_override_yields_custom_version_only_for_overridden_op():
    rc = resolve_effective_config(
        global_defaults=_globals(),
        project_overrides={"prompts": {"entity": {"system": "MY CUSTOM SYSTEM PROMPT"}}},
    )
    assert rc.prompt_versions["entity"].startswith("custom-")
    # other ops stay on the default file-hash
    assert not rc.prompt_versions["relation"].startswith("custom-")
    assert rc.prompts["entity"]["system"] == "MY CUSTOM SYSTEM PROMPT"


def test_prompt_override_changes_hash():
    g = _globals()
    base = config_hash(resolve_effective_config(global_defaults=g, project_overrides={}))
    custom = config_hash(resolve_effective_config(
        global_defaults=g, project_overrides={"prompts": {"entity": {"user": "different"}}},
    ))
    assert base != custom


def test_different_custom_prompts_differ():
    g = _globals()
    a = config_hash(resolve_effective_config(
        global_defaults=g, project_overrides={"prompts": {"entity": {"system": "A"}}}))
    b = config_hash(resolve_effective_config(
        global_defaults=g, project_overrides={"prompts": {"entity": {"system": "B"}}}))
    assert a != b


# ── base_default_version ─────────────────────────────────────────────────

def test_base_default_version_is_8_hex():
    bv = base_default_version(_globals())
    assert len(bv) == 8 and all(c in "0123456789abcdef" for c in bv)


def test_base_default_version_changes_when_default_changes():
    a = base_default_version(_globals(model_ref="m1"))
    b = base_default_version(_globals(model_ref="m2"))
    assert a != b


def test_base_default_version_stable_for_same_defaults():
    assert base_default_version(_globals()) == base_default_version(_globals())
