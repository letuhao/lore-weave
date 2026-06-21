"""KM6-M2 — `kg_adopt` descriptor effect + preview (the second class-C action).

Adopt copies a system/user template down into the project (replace-on-adopt: one active
project schema). Unlike `kg_schema_edit` there is NO version-drift to re-validate —
re-adopt is idempotent in effect. Confirm-time re-validation = the source template is
still visible/adoptable (`SchemaNotWritableError`) + the M1 glossary node-kind gate
(`NeedsGlossaryError`). Preview renders the template summary + whether it replaces an
existing schema + any glossary gap that would block confirm — all from current state.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.clients.glossary_ontology_client import GlossaryOntologyClient
from app.db.repositories.graph_schemas import GraphSchemasRepo
from app.db.repositories.ontology_mutations import (
    NeedsGlossaryError,
    OntologyMutationsRepo,
    SchemaNotWritableError,
)
from app.db.repositories.projects import ProjectsRepo
from app.ontology.glossary_gate import resolve_adopt_glossary_codes

__all__ = [
    "AdoptParams",
    "AdoptNeedsGlossary",
    "AdoptSourceMissing",
    "apply_adopt",
    "preview_adopt",
]


class AdoptNeedsGlossary(Exception):
    """The adopt-gate blocked: glossary is missing required node-kinds (router → 422
    with the missing kinds; re-proposable once the gap is filled)."""

    def __init__(self, kinds: list[str], book_id: str | None) -> None:
        self.kinds = kinds
        self.book_id = book_id
        super().__init__(f"glossary missing required node-kinds: {kinds}")


class AdoptSourceMissing(Exception):
    """The source template no longer exists / isn't visible (router → 404)."""


class AdoptParams(BaseModel):
    """Opaque mint params: which template to copy down."""

    source_schema_id: str
    acknowledge_optional_gaps: bool = False


async def apply_adopt(
    mutations: OntologyMutationsRepo,
    projects: ProjectsRepo,
    glossary: GlossaryOntologyClient,
    *,
    owner: UUID,
    project_id: str,
    params: AdoptParams,
) -> dict:
    """Resolve the glossary gate then adopt. Raises AdoptNeedsGlossary (re-proposable),
    AdoptSourceMissing (404), or ValueError on a malformed source id."""
    source_id = UUID(params.source_schema_id)
    book_id, codes = await resolve_adopt_glossary_codes(
        projects, glossary, mutations,
        owner=owner, project_id=project_id, source_schema_id=source_id,
    )
    try:
        result = await mutations.adopt(
            owner_user_id=owner,
            project_id=project_id,
            source_schema_id=source_id,
            glossary_kinds=codes,
            book_id=book_id,
        )
    except NeedsGlossaryError as exc:
        raise AdoptNeedsGlossary(exc.kinds, exc.book_id)
    except SchemaNotWritableError:
        raise AdoptSourceMissing("source template not found")

    return {
        "adopted": True,
        "schema_id": str(result.schema.schema_id),
        "code": result.schema.code,
        "name": result.schema.name,
        "schema_version": result.schema.schema_version,
        "missing_optional": result.missing_optional,
    }


async def preview_adopt(
    schemas: GraphSchemasRepo,
    mutations: OntologyMutationsRepo,
    projects: ProjectsRepo,
    glossary: GlossaryOntologyClient,
    *,
    owner: UUID,
    project_id: str,
    params: AdoptParams,
) -> dict:
    """Non-consuming current-state render: template summary + replace-warning + glossary
    gap (the would-block-confirm reasons), so the human confirms against what is true now."""
    try:
        source_id = UUID(params.source_schema_id)
    except (ValueError, TypeError):
        return _missing_preview()

    summary = await schemas.template_summary(source_id, owner)
    if summary is None:
        return _missing_preview()

    existing = await schemas.active_project_schema(project_id)
    rows = [
        {"label": "template", "value": f'{summary["name"]} ({summary["code"]})'},
        {"label": "edge types", "value": str(summary["edge_type_count"])},
        {"label": "node kinds", "value": str(summary["node_kind_count"])},
        {"label": "fact types", "value": str(summary["fact_type_count"])},
        {"label": "replaces current schema",
         "value": "yes" if existing is not None else "no",
         **({"note": "the project's current ontology will be deprecated and replaced"}
            if existing is not None else {})},
    ]

    # Glossary gap that WOULD block confirm (the §5.1 #5 blast-radius warning).
    _book, codes = await resolve_adopt_glossary_codes(
        projects, glossary, mutations, owner=owner, project_id=project_id, source_schema_id=source_id,
    )
    required = set(await mutations.required_node_kinds(source_id))
    missing = sorted(required - codes)
    blocked = bool(missing)
    if blocked:
        rows.append({"label": "⚠ glossary gap", "value": ", ".join(missing),
                     "note": "confirm will be rejected until these node-kinds exist in glossary"})

    return {
        "descriptor": "kg_adopt",
        "title": f'Adopt template "{summary["name"]}"',
        "destructive": existing is not None,  # replaces the current schema
        "blocked": blocked,
        "preview_rows": rows,
    }


def _missing_preview() -> dict:
    return {
        "descriptor": "kg_adopt",
        "title": "Adopt template",
        "destructive": False,
        "blocked": True,
        "preview_rows": [
            {"label": "status", "value": "template not found",
             "note": "the source template no longer exists or isn't visible — propose again"},
        ],
    }
