"""Model-role resolution for the extraction pipeline (KN model-roles).

ONE pure precedence chain every extraction LLM role resolves through, so pass2 /
summarize / dispatch all agree on "which model does this role use". Highest tier
wins; a tier that yields nothing falls to the next:

    1. role override   — extraction_config[<role>].model_ref (+ model_source)
    2. project default — extraction_config.llm_model (+ llm_model_source)
    3. user-global     — the user's default `chat` model (provider-registry
                         user_default_models; resolved by the caller and passed
                         in as `user_default_ref`)
    4. env floor       — a legacy per-role env override (back-compat; deprecated)
    5. None            — the role is OFF (recovery/precision are optional)

Pure + total: no I/O (the user-global + env values are resolved by the caller and
passed in), so every rung is unit-testable. The recurring
`nil-tolerant-wrapper-needs-wiring-test` lesson: a dropped fallback rung must fail
a test, not silently no-op.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NamedTuple

# Roles that resolve through this chain. `extraction` is the primary drafting LLM
# (its project default IS llm_model); the others are optional refinement passes.
ROLES = ("extraction", "precision_filter", "entity_recovery", "summarize")

_DEFAULT_SOURCE = "user_model"


class RoleModel(NamedTuple):
    model_source: str
    model_ref: str


def _override_ref(section: Any) -> RoleModel | None:
    """Pull (source, ref) from a role override sub-object. An override that is
    present but explicitly disabled (`enabled: false`) yields None so the role
    falls through to the default — an off-switch, not a model choice."""
    if not isinstance(section, Mapping):
        return None
    if section.get("enabled") is False:
        return None
    ref = section.get("model_ref")
    if not ref:
        return None
    source = section.get("model_source") or _DEFAULT_SOURCE
    return RoleModel(str(source), str(ref))


def _project_default(config: Mapping[str, Any]) -> RoleModel | None:
    """The project's default LLM = extraction_config.llm_model. Accepts either a
    bare ref string (source defaults to user_model) or an object with
    model_ref/model_source."""
    llm = config.get("llm_model")
    if isinstance(llm, Mapping):
        return _override_ref(llm)
    if isinstance(llm, str) and llm:
        source = config.get("llm_model_source") or _DEFAULT_SOURCE
        return RoleModel(str(source), llm)
    return None


def resolve_role_model(
    extraction_config: Mapping[str, Any] | None,
    role: str,
    *,
    user_default_ref: str | None = None,
    env_source: str | None = None,
    env_ref: str | None = None,
) -> RoleModel | None:
    """Resolve the (model_source, model_ref) for `role`, or None if the role has
    no model and is therefore OFF. See the module docstring for the precedence.

    `user_default_ref` is the user-global default (already resolved to a
    `user_model` ref by the caller). `env_*` is the legacy per-role env floor.
    For `role='extraction'` the project default (llm_model) and the role override
    are the same slot — the override tier is skipped and llm_model is the source
    of truth."""
    config = extraction_config or {}

    # 1. role override (skipped for `extraction`: its override IS llm_model).
    if role != "extraction":
        hit = _override_ref(config.get(role))
        if hit is not None:
            return hit

    # 2. project default (llm_model).
    hit = _project_default(config)
    if hit is not None:
        return hit

    # 3. user-global default (BYOK chat default).
    if user_default_ref:
        return RoleModel(_DEFAULT_SOURCE, str(user_default_ref))

    # 4. env floor (deprecated).
    if env_ref:
        return RoleModel(str(env_source or _DEFAULT_SOURCE), str(env_ref))

    # 5. off.
    return None
