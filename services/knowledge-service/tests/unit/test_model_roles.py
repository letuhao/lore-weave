"""KN model-roles — the pure role→model precedence resolver.

Each precedence rung is pinned so a dropped fallback fails a test (the
nil-tolerant-wrapper lesson), not silently no-ops in live extraction.
"""
from __future__ import annotations

from app.extraction.model_roles import RoleModel, resolve_role_model


def test_role_override_wins_over_everything():
    cfg = {
        "llm_model": "proj-default",
        "entity_recovery": {"model_ref": "role-ref", "model_source": "user_model"},
    }
    got = resolve_role_model(cfg, "entity_recovery",
                             user_default_ref="user-global", env_ref="env-floor")
    assert got == RoleModel("user_model", "role-ref")


def test_falls_to_project_default_when_no_role_override():
    cfg = {"llm_model": "proj-default"}
    got = resolve_role_model(cfg, "entity_recovery",
                             user_default_ref="user-global", env_ref="env-floor")
    assert got == RoleModel("user_model", "proj-default")


def test_project_default_object_form_carries_source():
    cfg = {"llm_model": {"model_ref": "proj-ref", "model_source": "platform_model"}}
    assert resolve_role_model(cfg, "precision_filter") == RoleModel("platform_model", "proj-ref")


def test_project_default_honors_explicit_source_key():
    cfg = {"llm_model": "proj-ref", "llm_model_source": "platform_model"}
    assert resolve_role_model(cfg, "extraction") == RoleModel("platform_model", "proj-ref")


def test_falls_to_user_global_when_no_project_default():
    got = resolve_role_model({}, "entity_recovery",
                             user_default_ref="user-global", env_ref="env-floor")
    assert got == RoleModel("user_model", "user-global")


def test_falls_to_env_floor_when_no_user_global():
    got = resolve_role_model({}, "entity_recovery",
                             user_default_ref=None, env_source="platform_model", env_ref="env-floor")
    assert got == RoleModel("platform_model", "env-floor")


def test_off_when_nothing_configured():
    assert resolve_role_model({}, "entity_recovery") is None
    assert resolve_role_model(None, "precision_filter") is None


def test_disabled_override_falls_through_to_default():
    # An override present but enabled=False is an off-switch for the OVERRIDE,
    # so the role still resolves to the project default (not None).
    cfg = {"llm_model": "proj-default",
           "entity_recovery": {"enabled": False, "model_ref": "ignored"}}
    assert resolve_role_model(cfg, "entity_recovery") == RoleModel("user_model", "proj-default")


def test_extraction_role_skips_override_slot_uses_llm_model():
    # For 'extraction' the override slot IS llm_model — a stray extraction_config
    # key named 'extraction' must NOT shadow the project default.
    cfg = {"llm_model": "proj-default", "extraction": {"model_ref": "should-not-win"}}
    assert resolve_role_model(cfg, "extraction") == RoleModel("user_model", "proj-default")


def test_override_missing_ref_is_ignored():
    cfg = {"llm_model": "proj-default", "entity_recovery": {"model_source": "user_model"}}
    assert resolve_role_model(cfg, "entity_recovery") == RoleModel("user_model", "proj-default")
