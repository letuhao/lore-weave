"""Project a knowledge-service ``ResolvedSchema`` into the SDK's
``ExtractionSchema`` (KG customizable-ontology, lane LB / L7 activation).

The SDK (``loreweave_extraction``) deliberately does NOT import
``app.db.ontology_models`` — it consumes a plain dict via
:meth:`ExtractionSchema.from_resolved`. This module is the knowledge-service
side of that contract: it reads the resolved (system→user→project merged)
schema and emits exactly the dict shape the SDK expects.

**Two consumers, two postures (the L7 pre-drop reconciliation):**

  * the **write boundary** (``write_pass2_extraction``) wants the *authoritative*
    schema — real ``allow_free_edges`` — so it is the sole closed-set
    enforce-and-triage-park point (Milestone A);
  * the **SDK prompt path** (``extract_pass2`` in worker-ai) wants an *advisory*
    projection — ``allow_free_edges`` forced True — so the vocab is injected as a
    *hint* into the prompt but the SDK never pre-drops an off-vocab predicate
    (which would rob the writer's triage park of the edge). Pass
    ``advisory=True`` for that path (Milestone B).

``event_kinds`` is intentionally empty: event kinds are not part of the
customizable ontology yet (the schema models entity-kinds, edge-types,
fact-types, and closed vocab sets like ``drive`` — never an event-kind vocab).
An empty list makes the SDK inject no event hint + accept any event kind, i.e.
today's static behavior — never stricter.

Spec: docs/specs/2026-06-20-knowledge-graph-customizable-ontology.md §1.1, §10-B1.
"""

from __future__ import annotations

from app.db.ontology_models import ResolvedSchema
from loreweave_extraction.schema_projection import ExtractionSchema

__all__ = ["resolved_to_extraction_dict", "build_extraction_schema"]


def resolved_to_extraction_dict(
    resolved: ResolvedSchema, *, advisory: bool = False,
) -> dict:
    """Project a ``ResolvedSchema`` into the plain dict the SDK consumes.

    ``advisory=True`` forces ``allow_free_edges=True`` so the SDK treats the
    edge vocab as a non-binding prompt hint (never pre-drops off-vocab) — used
    by the extraction-prompt path so the write boundary stays the single
    enforce+park point. ``advisory=False`` (default) carries the schema's real
    ``allow_free_edges`` — used by the write boundary itself.

    Vocab lists are *codes*. ``resolve_for_project`` already excludes deprecated
    edge-types / fact-types, so the lists here are the active set.
    """
    return {
        "entity_kinds": [nk.kind_code for nk in resolved.node_kinds],
        "edge_predicates": [et.code for et in resolved.edge_types],
        # Not modeled in the schema (no event-kind vocab) → empty ⇒ SDK keeps
        # today's static event behavior.
        "event_kinds": [],
        "fact_types": [ft.code for ft in resolved.fact_types],
        "allow_free_edges": True if advisory else resolved.allow_free_edges,
        # KG customizable-ontology (L7) — per-predicate cardinality (write-path
        # only; never a prompt/validation concern, so it is carried in BOTH the
        # authoritative and advisory projections). The write boundary
        # (``write_pass2_extraction``) looks a predicate's cardinality up here to
        # auto-close the prior open ``single_active`` edge. ``multi_active`` (the
        # default) is the no-op case; only ``single_active`` entries matter, but
        # we project the full map so the writer can distinguish "unknown" (no
        # entry → no-op) from an explicit ``multi_active``.
        "edge_cardinalities": {et.code: et.cardinality for et in resolved.edge_types},
        "label": f"{resolved.project_id}@v{resolved.schema_version}",
        "schema_version": resolved.schema_version,
    }


def build_extraction_schema(
    resolved: ResolvedSchema, *, advisory: bool = False,
) -> ExtractionSchema:
    """Convenience: project + construct the SDK ``ExtractionSchema``."""
    return ExtractionSchema.from_resolved(
        resolved_to_extraction_dict(resolved, advisory=advisory),
    )
