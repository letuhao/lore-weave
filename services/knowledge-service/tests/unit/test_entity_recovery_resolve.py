"""KN model-roles A-wire — the endpoint's per-job entity-recovery resolver.

`_resolve_entity_recovery_config` gates enablement (per-project opt-in OR env
floor) and resolves the model via the precedence chain. These pin: OFF by default
(back-compat), env-floor on, per-project enable → job model (project default),
role override wins, user-global fallback, explicit disable.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

_MOD = "app.routers.internal_extraction"
_USER = "00000000-0000-0000-0000-0000000000aa"
_PROJECT = "00000000-0000-0000-0000-0000000000bb"


def _fake_projects_repo(extraction_config: dict | None):
    class _Repo:
        def __init__(self, _pool):
            ...

        async def get(self, _uid, _pid):
            return SimpleNamespace(extraction_config=extraction_config)

    return _Repo


async def _resolve(extraction_config, *, user_default=None, env=None,
                   job_ref="job-model", job_source="user_model"):
    from app.routers.internal_extraction import _resolve_entity_recovery_config

    saved = {k: os.environ.get(k) for k in (
        "KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MODEL_REF",
        "KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MODEL_SOURCE")}
    if env:
        os.environ["KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MODEL_REF"] = env
    else:
        os.environ.pop("KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MODEL_REF", None)
    try:
        with patch(f"{_MOD}.get_knowledge_pool", lambda: object()), \
             patch(f"{_MOD}.ProjectsRepo", _fake_projects_repo(extraction_config)), \
             patch(f"{_MOD}.resolve_user_default_model", new=_async_ret(user_default)):
            return await _resolve_entity_recovery_config(
                user_id=_USER, project_id=_PROJECT,
                job_model_source=job_source, job_model_ref=job_ref,
            )
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _async_ret(value):
    async def _fn(*_a, **_k):
        return value
    return _fn


@pytest.mark.asyncio
async def test_off_by_default_no_config_no_env():
    assert await _resolve({}, env=None) is None


@pytest.mark.asyncio
async def test_env_floor_enables_recovery_backcompat():
    got = await _resolve({}, env="env-model")
    assert got is not None and got.model_ref == "env-model"


@pytest.mark.asyncio
async def test_per_project_enabled_uses_job_model_as_project_default():
    # enabled=True, no per-role model → falls to the project default = job model.
    got = await _resolve({"entity_recovery": {"enabled": True}})
    assert got is not None and got.model_ref == "job-model"


@pytest.mark.asyncio
async def test_role_override_model_wins():
    got = await _resolve({"entity_recovery": {"enabled": True, "model_ref": "role-model"}})
    assert got is not None and got.model_ref == "role-model"


@pytest.mark.asyncio
async def test_persisted_project_default_wins_over_job_model():
    # extraction_config.llm_model (FE "Default LLM", object form) is the project
    # default — it beats THIS job's extraction model for an unset role.
    got = await _resolve({
        "llm_model": {"model_ref": "persisted-default", "model_source": "user_model"},
        "entity_recovery": {"enabled": True},
    })
    assert got is not None and got.model_ref == "persisted-default"


@pytest.mark.asyncio
async def test_user_global_fallback_when_no_project_default_and_no_job_model():
    # Enabled via env floor, but user-global default takes precedence over env when
    # there's no role override and no project default; job model IS the project
    # default though — so to reach user-global we drop the job model.
    got = await _resolve({"entity_recovery": {"enabled": True}},
                         user_default="user-global", job_ref="")
    assert got is not None and got.model_ref == "user-global"


@pytest.mark.asyncio
async def test_explicit_disable_off_even_with_env():
    assert await _resolve({"entity_recovery": {"enabled": False}}, env="env-model") is None


@pytest.mark.asyncio
async def test_per_project_max_batch_honored():
    got = await _resolve({"entity_recovery": {"enabled": True, "max_items_per_batch": 9}})
    assert got is not None and got.max_items_per_batch == 9


def test_entity_recovery_override_contract_accepts_bounded_max_batch():
    """KN model-roles — the FE-facing contract now carries max_items_per_batch
    (was env/default only). Bounded 1-20; None = default."""
    from pydantic import ValidationError

    from app.db.models import EntityRecoveryOverride

    assert EntityRecoveryOverride(enabled=True, max_items_per_batch=20).max_items_per_batch == 20
    assert EntityRecoveryOverride(max_items_per_batch=1).max_items_per_batch == 1
    assert EntityRecoveryOverride().max_items_per_batch is None
    for bad in (0, 21, -1):
        with pytest.raises(ValidationError):
            EntityRecoveryOverride(max_items_per_batch=bad)
