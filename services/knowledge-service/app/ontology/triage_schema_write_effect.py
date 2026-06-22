"""E3 — `kg_triage_schema_write` descriptor effect + preview (Lane E, class-C).

The schema-mutating triage actions (``add_to_vocab`` / ``add_to_schema`` /
``widen_target_kinds`` / ``set_multi_active``) record intent today but never touch
the schema (the resolve route sets ``new_schema_version=None``). E3 routes them
through ``OntologyMutationsRepo`` via the KM6 confirm spine: Manage-gated, the MCP
mints a ``DESC_TRIAGE_SCHEMA_WRITE`` token, the human redeems it at
`POST /v1/kg/actions/confirm`, this effect applies the matching mutation (which
bumps ``schema_version`` + rehashes), and the router stamps the returned version
onto the resolved triage items.

Optimistic concurrency mirrors ``schema_edit_effect``: the token captures the live
``schema_id`` + ``schema_version`` at mint; confirm rejects (422) if the project's
active schema vanished / was replaced / moved since.

Per-action param mapping (all read EXISTING repo methods + the two additive ones):
  * ``add_to_vocab``       → ``add_vocab_value(set_code, code, label)``
  * ``add_to_schema``      → ``add_edge_type(code, label)``
  * ``widen_target_kinds`` → ``widen_edge_target_kinds(code, add_kinds)``
  * ``set_multi_active``   → ``set_edge_cardinality(code, "multi_active")``

Spec: docs/specs/2026-06-21-kg-deferred-clearance.md §5 (E3); INV-T3.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.db.repositories.graph_schemas import GraphSchemasRepo
from app.db.repositories.ontology_mutations import OntologyMutationsRepo

__all__ = [
    "TriageSchemaWriteParams",
    "TriageSchemaWriteDrift",
    "TriageSchemaWriteUnsupported",
    "apply_triage_schema_write",
    "preview_triage_schema_write",
]

_ACTIONS = ("add_to_vocab", "add_to_schema", "widen_target_kinds", "set_multi_active")


class TriageSchemaWriteDrift(Exception):
    """Confirm-time re-validation failed: the project schema vanished / was replaced
    / moved since mint → the human must re-propose (422)."""


class TriageSchemaWriteUnsupported(Exception):
    """The action / params are not a supported schema-write shape (422)."""


class TriageSchemaWriteParams(BaseModel):
    """Opaque params captured at mint + re-validated at confirm.

    ``signature`` is the triage signature group the resolution stamps the new
    version onto; ``schema_id`` + ``expected_schema_version`` are the optimistic-
    concurrency anchor. Per-action fields:
      * add_to_vocab: ``set_code`` + ``code`` (+ ``label``)
      * add_to_schema: ``code`` (+ ``label``)  — adds an edge type
      * widen_target_kinds: ``code`` + ``add_kinds``
      * set_multi_active: ``code``"""

    action: Literal["add_to_vocab", "add_to_schema", "widen_target_kinds", "set_multi_active"]
    signature: str
    schema_id: str
    expected_schema_version: int
    code: str = ""
    label: str = ""
    set_code: str = ""
    add_kinds: list[str] = []

    @field_validator("schema_id")
    @classmethod
    def _valid_uuid(cls, v: str) -> str:
        UUID(str(v))
        return str(v)


async def _revalidate(
    schemas: GraphSchemasRepo, project_id: str, params: TriageSchemaWriteParams
) -> UUID:
    """Re-resolve the active schema + assert no drift since mint (§13.5)."""
    current = await schemas.active_project_schema(project_id)
    if current is None:
        raise TriageSchemaWriteDrift("the project has no active schema — propose again")
    if str(current.schema_id) != params.schema_id:
        raise TriageSchemaWriteDrift("the project schema was replaced — propose again")
    if current.schema_version != params.expected_schema_version:
        raise TriageSchemaWriteDrift("the schema changed since you proposed — propose again")
    return current.schema_id


async def apply_triage_schema_write(
    schemas: GraphSchemasRepo,
    mutations: OntologyMutationsRepo,
    triage,  # TriageRepo — write-through the new version onto the items
    project_id: str,
    params: TriageSchemaWriteParams,
    *,
    owner=None,  # UUID | None — the project owner, for the scoped version stamp
) -> dict:
    """Re-validate (drift), apply the matching ontology mutation (bumps the
    schema_version), then stamp that version onto the signature's resolved items.

    Raises TriageSchemaWriteDrift (422), TriageSchemaWriteUnsupported (422), or the
    repo's Duplicate/ChildNotFound/SchemaNotWritable (router maps 409/422)."""
    schema_id = await _revalidate(schemas, project_id, params)

    if params.action == "add_to_vocab":
        if not params.set_code or not params.code:
            raise TriageSchemaWriteUnsupported("add_to_vocab needs set_code + code")
        await mutations.add_vocab_value(
            schema_id, set_code=params.set_code, code=params.code,
            label=params.label or params.code,
        )
    elif params.action == "add_to_schema":
        if not params.code:
            raise TriageSchemaWriteUnsupported("add_to_schema needs code")
        await mutations.add_edge_type(
            schema_id, code=params.code, label=params.label or params.code
        )
    elif params.action == "widen_target_kinds":
        if not params.code or not params.add_kinds:
            raise TriageSchemaWriteUnsupported("widen_target_kinds needs code + add_kinds")
        await mutations.widen_edge_target_kinds(
            schema_id, code=params.code, add_kinds=params.add_kinds
        )
    elif params.action == "set_multi_active":
        if not params.code:
            raise TriageSchemaWriteUnsupported("set_multi_active needs code")
        await mutations.set_edge_cardinality(
            schema_id, code=params.code, cardinality="multi_active"
        )
    else:  # pragma: no cover — Literal already constrains it
        raise TriageSchemaWriteUnsupported(f"unsupported action {params.action!r}")

    after = await schemas.active_project_schema(project_id)
    new_version = after.schema_version if after else None

    # Stamp the new version onto the (already-resolved) triage items of this
    # signature — the resolve route set it to None; E3 backfills the real version.
    # owner == the project owner the schema is scoped under (scope_id). Best-effort
    # write-through: a stamp failure must not unwind the applied schema change.
    affected = 0
    if new_version is not None and owner is not None:
        try:
            affected = await triage.stamp_schema_version(
                user_id=owner,
                project_id=project_id,
                signature=params.signature,
                schema_version=new_version,
            )
        except Exception:  # noqa: BLE001 — version stamp is advisory metadata
            affected = 0

    return {
        "applied": True,
        "descriptor": "kg_triage_schema_write",
        "action": params.action,
        "schema_version": new_version,
        "stamped": affected,
    }


async def preview_triage_schema_write(
    schemas: GraphSchemasRepo, project_id: str, params: TriageSchemaWriteParams
) -> dict:
    """Non-consuming current-state render: the action, the target, and the version
    bump. Surfaces ``drift`` when the active schema moved/vanished since mint."""
    current = await schemas.active_project_schema(project_id)
    title = f"Schema write: {params.action} '{params.code or params.set_code}'"
    if current is None:
        return {
            "descriptor": "kg_triage_schema_write",
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
        {"label": "action", "value": params.action},
        {"label": "code", "value": params.code or params.set_code},
        {"label": "current schema_version", "value": str(current.schema_version)},
        {"label": "will bump to", "value": str(current.schema_version + 1)},
    ]
    if params.action == "widen_target_kinds" and params.add_kinds:
        rows.append({"label": "add target kinds", "value": ", ".join(params.add_kinds)})
    if drift:
        rows.append({"label": "⚠ drift", "value": "yes",
                     "note": "the schema changed since you proposed — confirming will be rejected"})
    return {
        "descriptor": "kg_triage_schema_write",
        "title": title,
        "destructive": False,
        "drift": drift,
        "preview_rows": rows,
    }
