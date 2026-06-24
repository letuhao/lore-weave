"""KM6 — `kg_schema_edit` descriptor effect + preview (the class-C canary, spec §13.5).

A `kg_schema_edit` confirm-token carries the schema_id + the schema_version the agent
saw at MINT. This module re-validates against CURRENT state at confirm time
(optimistic concurrency — drift since mint → re-proposable) and then applies the edit
via the existing :class:`OntologyMutationsRepo` (which bumps schema_version + rehashes).
Preview recomputes the card from current state, non-consuming.

M1 levels: ``edge_type`` + ``fact_type`` (symmetric add/deprecate, code+label). Other
levels (node_kind/vocab_value) are additive follow-ons.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.db.repositories.graph_schemas import GraphSchemasRepo
from app.db.repositories.ontology_mutations import (
    ChildNotFoundError,
    DuplicateChildError,
    OntologyMutationsRepo,
    SchemaNotWritableError,
)

__all__ = [
    "SchemaEditParams",
    "SchemaEditDrift",
    "apply_schema_edit",
    "preview_schema_edit",
]

_VERBS = ("add", "deprecate")
_LEVELS = ("edge_type", "fact_type")


class SchemaEditDrift(Exception):
    """Confirm-time re-validation failed: the project schema vanished or its
    schema_version moved since mint → the human must re-propose (422)."""


class SchemaEditParams(BaseModel):
    """Opaque params captured at mint (inside the HMAC) + re-validated at confirm.

    ``schema_id`` + ``expected_schema_version`` are the optimistic-concurrency anchor:
    confirm rejects if the project's active schema is no longer this id, or its
    version moved. ``label`` is required for ``add`` (ignored for ``deprecate``)."""

    verb: Literal["add", "deprecate"]
    level: Literal["edge_type", "fact_type"]
    code: str
    label: str = ""
    schema_id: str
    expected_schema_version: int

    @field_validator("code")
    @classmethod
    def _code_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("code is required")
        return v.strip()


async def _revalidate(
    schemas: GraphSchemasRepo, project_id: str, params: SchemaEditParams
) -> UUID:
    """Re-resolve the project's active schema and assert it has not drifted since
    mint. Returns the live schema_id to write against; raises SchemaEditDrift on a
    vanished/replaced/bumped schema (§13.5 #4)."""
    current = await schemas.active_project_schema(project_id)
    if current is None:
        raise SchemaEditDrift("the project has no active schema — propose again")
    if str(current.schema_id) != params.schema_id:
        raise SchemaEditDrift("the project schema was replaced — propose again")
    if current.schema_version != params.expected_schema_version:
        raise SchemaEditDrift("the schema changed since you proposed — propose again")
    return current.schema_id


async def apply_schema_edit(
    schemas: GraphSchemasRepo,
    mutations: OntologyMutationsRepo,
    project_id: str,
    params: SchemaEditParams,
) -> dict:
    """Re-validate (drift) then apply the edit. Raises SchemaEditDrift (re-proposable),
    DuplicateChildError (add a code that exists), ChildNotFoundError (deprecate a code
    that's gone), or SchemaNotWritableError (the schema turned non-writable). The caller
    (router) maps these to 422/409. Returns the new schema_version."""
    schema_id = await _revalidate(schemas, project_id, params)

    if params.verb == "add":
        if not params.label.strip():
            raise SchemaEditDrift("label is required to add a type")
        if params.level == "edge_type":
            await mutations.add_edge_type(schema_id, code=params.code, label=params.label)
        else:  # fact_type
            await mutations.add_fact_type(schema_id, code=params.code, label=params.label)
    else:  # deprecate
        if params.level == "edge_type":
            await mutations.deprecate_edge_type(schema_id, params.code)
        else:  # fact_type
            await mutations.deprecate_fact_type(schema_id, params.code)

    after = await schemas.active_project_schema(project_id)
    return {
        "applied": True,
        "verb": params.verb,
        "level": params.level,
        "code": params.code,
        "schema_version": after.schema_version if after else None,
    }


async def preview_schema_edit(
    schemas: GraphSchemasRepo, project_id: str, params: SchemaEditParams
) -> dict:
    """Non-consuming current-state render of the confirm card (§5.1 #5). Surfaces a
    `drift` flag so the FE can warn before the human confirms (the confirm itself
    re-checks authoritatively)."""
    current = await schemas.active_project_schema(project_id)
    title = f"{params.verb.capitalize()} {params.level.replace('_', ' ')} '{params.code}'"
    if current is None:
        return {
            "descriptor": "kg_schema_edit",
            "title": title,
            "destructive": False,
            "drift": True,
            "preview_rows": [
                {"label": "status", "value": "no active schema",
                 "note": "the project has no schema to edit — propose again"},
            ],
        }
    drift = (
        str(current.schema_id) != params.schema_id
        or current.schema_version != params.expected_schema_version
    )
    rows = [
        {"label": "verb", "value": params.verb},
        {"label": "level", "value": params.level},
        {"label": "code", "value": params.code},
        {"label": "current schema_version", "value": str(current.schema_version)},
        {"label": "will bump to", "value": str(current.schema_version + 1)},
    ]
    if params.verb == "add" and params.label:
        rows.insert(3, {"label": "label", "value": params.label})
    if drift:
        rows.append({"label": "⚠ drift", "value": "yes",
                     "note": "the schema changed since you proposed — confirming will be rejected"})
    return {
        "descriptor": "kg_schema_edit",
        "title": title,
        "destructive": params.verb == "deprecate",
        "drift": drift,
        "preview_rows": rows,
    }
