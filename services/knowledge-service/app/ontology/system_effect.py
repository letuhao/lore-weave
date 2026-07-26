"""KM5-M2 — `kg_system_{create,patch,delete}` descriptor effects + preview.

The admin (System-tier) class-C effects. A `kg_system_*` confirm-token carries
`auth=admin` (the route re-verifies the RS256 admin JWT + binds `asub` BEFORE
consuming) and the opaque template params captured at mint. This module
re-validates against CURRENT state at confirm time (optimistic concurrency for
patch; code-still-free for create) and applies via :class:`SystemTemplatesRepo`.

Mirrors `schema_edit_effect` (grant tier) but on the System tier: drift →
re-proposable 422; duplicate code → 409; vanished target → 422.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator

from app.db.repositories.system_templates import (
    DuplicateSystemTemplate,
    SystemTemplateNotFound,
    SystemTemplatesRepo,
)

__all__ = [
    "SystemTemplateParams",
    "SystemEffectDrift",
    "apply_system_template",
    "preview_system_template",
    "DESCRIPTOR_BY_VERB",
    "VERB_BY_DESCRIPTOR",
]

DESCRIPTOR_BY_VERB = {
    "create": "kg_system_create",
    "patch": "kg_system_patch",
    "delete": "kg_system_delete",
}
VERB_BY_DESCRIPTOR = {v: k for k, v in DESCRIPTOR_BY_VERB.items()}


class SystemEffectDrift(Exception):
    """Confirm-time re-validation failed: the target template vanished or its
    schema_version moved since mint (patch), or the code was taken (create) →
    the admin must re-propose (422)."""


class SystemTemplateParams(BaseModel):
    """Opaque params captured at mint (inside the HMAC) + re-validated at confirm.

    create: ``code`` (new, unique) + ``name`` required. patch/delete: ``schema_id``
    required; patch carries ``expected_schema_version`` (optimistic-concurrency
    anchor) + the fields to change."""

    verb: Literal["create", "patch", "delete"]
    code: str = ""
    name: str = ""
    description: str | None = None
    allow_free_edges: bool | None = None
    schema_id: str = ""
    expected_schema_version: int | None = None

    @model_validator(mode="after")
    def _check_required(self) -> "SystemTemplateParams":
        if self.verb == "create":
            if not self.code.strip():
                raise ValueError("code is required to create a system template")
            if not self.name.strip():
                raise ValueError("name is required to create a system template")
        else:  # patch / delete
            if not self.schema_id.strip():
                raise ValueError(f"schema_id is required to {self.verb} a system template")
        return self


async def _revalidate_target(repo: SystemTemplatesRepo, params: SystemTemplateParams):
    """patch/delete: re-resolve the system template + assert no version drift.
    Returns the live schema; raises SystemEffectDrift on a vanished/bumped row."""
    from uuid import UUID

    try:
        sid = UUID(params.schema_id)
    except (ValueError, AttributeError):
        raise SystemEffectDrift("invalid system template id — propose again")
    current = await repo.get_system_template(sid)
    if current is None:
        raise SystemEffectDrift("the system template no longer exists — propose again")
    if (
        params.expected_schema_version is not None
        and current.schema_version != params.expected_schema_version
    ):
        raise SystemEffectDrift("the system template changed since you proposed — propose again")
    return current


async def apply_system_template(repo: SystemTemplatesRepo, params: SystemTemplateParams) -> dict:
    """Re-validate then apply. Raises SystemEffectDrift (re-proposable),
    DuplicateSystemTemplate (create a code that exists), SystemTemplateNotFound
    (target gone mid-apply). The router maps these to 422/409."""
    if params.verb == "create":
        schema = await repo.create_template(
            code=params.code.strip(),
            name=params.name.strip(),
            description=(params.description or ""),
            allow_free_edges=True if params.allow_free_edges is None else params.allow_free_edges,
        )
        return {
            "applied": True, "verb": "create", "code": schema.code,
            "schema_id": str(schema.schema_id), "schema_version": schema.schema_version,
        }

    current = await _revalidate_target(repo, params)
    if params.verb == "patch":
        updated = await repo.patch_template(
            current.schema_id,
            name=params.name.strip() if params.name.strip() else None,
            description=params.description,
            allow_free_edges=params.allow_free_edges,
        )
        return {
            "applied": True, "verb": "patch", "code": updated.code,
            "schema_id": str(updated.schema_id), "schema_version": updated.schema_version,
        }
    # delete
    await repo.deprecate_template(current.schema_id)
    return {
        "applied": True, "verb": "delete", "code": current.code,
        "schema_id": str(current.schema_id),
    }


async def preview_system_template(repo: SystemTemplatesRepo, params: SystemTemplateParams) -> dict:
    """Non-consuming current-state render of the confirm card (§5.1 #5)."""
    descriptor = DESCRIPTOR_BY_VERB[params.verb]
    if params.verb == "create":
        # Drift for create = the code is already taken (confirm would 409).
        drift = await repo.code_exists(params.code.strip())
        rows = [
            {"label": "verb", "value": "create"},
            {"label": "code", "value": params.code.strip()},
            {"label": "name", "value": params.name.strip()},
        ]
        if drift:
            rows.append({"label": "⚠ conflict", "value": "code already exists",
                         "note": "a system template with this code exists — confirming will be rejected"})
        return {
            "descriptor": descriptor, "title": f"Create system template '{params.code.strip()}'",
            "destructive": False, "drift": drift, "preview_rows": rows,
        }

    # patch / delete — show current target + drift flag
    from uuid import UUID

    try:
        sid = UUID(params.schema_id)
        current = await repo.get_system_template(sid)
    except (ValueError, AttributeError):
        current = None
    if current is None:
        return {
            "descriptor": descriptor, "title": f"{params.verb.capitalize()} system template",
            "destructive": params.verb == "delete", "drift": True,
            "preview_rows": [{"label": "status", "value": "not found",
                              "note": "the system template no longer exists — propose again"}],
        }
    drift = (
        params.expected_schema_version is not None
        and current.schema_version != params.expected_schema_version
    )
    rows = [
        {"label": "verb", "value": params.verb},
        {"label": "code", "value": current.code},
        {"label": "current name", "value": current.name},
        {"label": "current schema_version", "value": str(current.schema_version)},
    ]
    if params.verb == "patch" and params.name.strip():
        rows.append({"label": "new name", "value": params.name.strip()})
    if drift:
        rows.append({"label": "⚠ drift", "value": "yes",
                     "note": "the template changed since you proposed — confirming will be rejected"})
    return {
        "descriptor": descriptor,
        "title": f"{params.verb.capitalize()} system template '{current.code}'",
        "destructive": params.verb == "delete",
        "drift": drift,
        "preview_rows": rows,
    }
