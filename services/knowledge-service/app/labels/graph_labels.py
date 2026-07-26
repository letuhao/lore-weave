"""KG-ML M5 (C7 / DD4+DD7) — localized label decoration for KG read surfaces.

The graph-view (`GraphSlice`) and edge-timeline (`EdgeTimeline`) carry the
canonical, source-language graph: a node's `kind` is a code (``character``),
its `name` is the source-language entity name, an edge's `edge_type` is a
predicate code (``ALLY_OF``). For a reader whose language differs from the
source, those must localize:

  * **kind**     → glossary ontology `name_i18n[language]` (C4); fall back to
                   the canonical kind name / code when no label exists.
  * **predicate**→ ``resolve_predicate_label`` (C5): curated map else humanize
                   (open-vocab predicates degrade to "ally of", never a raw
                   code).
  * **entity name** → glossary entity-name translation (C9); ``None`` when the
                   name is untranslated → the FE keeps the canonical `name`
                   (an explicit source-fallback per AC1).

These functions are PURE: they take already-resolved maps and mutate the
response models in place, so the resolution logic is unit-testable without a
live Neo4j or glossary. The router gathers the maps (ontology read + glossary
batch) and calls these. A blank `language` is a no-op — the canonical graph is
returned unchanged, preserving back-compat for callers that don't localize.
"""

from __future__ import annotations

from app.labels.predicate_labels import resolve_predicate_label

__all__ = ["localize_graph_slice", "localize_edge_timeline"]


def localize_graph_slice(
    graph_slice,
    *,
    kind_labels: dict[str, str],
    entity_names: dict[str, str],
    language: str | None,
):
    """Decorate a `GraphSlice` with localized labels (in place; returns it).

    ``kind_labels``: ``{kind_code: label}`` for ``language`` (from the glossary
    ontology read). ``entity_names``: ``{glossary_entity_id: translated_name}``
    (translated entries only — see GlossaryClient.fetch_entity_display_names).
    """
    if not language:
        return graph_slice
    for node in graph_slice.nodes:
        kl = kind_labels.get(node.kind)
        if kl:
            node.kind_label = kl
        if node.glossary_entity_id:
            nm = entity_names.get(node.glossary_entity_id)
            if nm:
                node.name_label = nm
    for edge in graph_slice.edges:
        # Predicate always resolves (curated → humanized fallback), so an
        # edge_type_label is always present for a localizing caller.
        edge.edge_type_label = resolve_predicate_label(edge.edge_type, language)
    return graph_slice


def localize_edge_timeline(
    timeline,
    *,
    entity_names: dict[str, str],
    language: str | None,
):
    """Decorate an `EdgeTimeline` with the localized predicate + per-instance
    localized target name (in place; returns it).

    ``entity_names``: ``{node_id: translated_name}`` keyed by the timeline
    instance ``target_id`` (the obj node id) — translated entries only."""
    if not language:
        return timeline
    timeline.edge_type_label = resolve_predicate_label(timeline.edge_type, language)
    for inst in timeline.instances:
        nm = entity_names.get(inst.target_id)
        if nm:
            inst.target_label_localized = nm
    return timeline
