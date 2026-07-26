// S7-1 — the ONE home on the FE for the closed-set entity-authoring
// vocabularies. Every picker (CreateEntityDialog kind grid, EntityEditDialog
// kind select, CreateRelationDialog predicate select), the enum-badge map, and
// the contract tests import from HERE — never a free `<input>`, never a
// re-declared literal tuple (the "one name for one concept" / Frontend-Tool
// Contract rule).
//
// `AUTHORABLE_ENTITY_KINDS` MUST equal the server gate
// `AUTHORABLE_KINDS` (services/knowledge-service app/db/neo4j_repos/
// entities.py) — the create REST route + the agent `kg_create_node` both gate
// to it. A drift here ships a picker option that 422s (the silent-no-op bug
// class this file exists to kill). The membership contract test asserts the
// equality.
//
// `organization` is the canonical group kind (glossary kind_code + extraction
// emit). The legacy `faction` misnomer is GONE — it lived only in the old
// create gate and zero rows can exist.
export const AUTHORABLE_ENTITY_KINDS = [
  'character',
  'location',
  'organization',
  'concept',
  'item',
] as const;

export type AuthorableEntityKind = (typeof AUTHORABLE_ENTITY_KINDS)[number];

export function isAuthorableEntityKind(v: string): v is AuthorableEntityKind {
  return (AUTHORABLE_ENTITY_KINDS as readonly string[]).includes(v);
}

// S7-1 / s7-4 — the curated relation-predicate vocabulary the GUI offers.
//
// ⚠ This is a GUI CONVENTION, NOT a backend constraint. The wire accepts a
// FREE string (`predicate: str = Field(min_length=1, max_length=100)`,
// relations.py) precisely so the agent's free-form `kg_propose_edge` and
// existing extraction edges are not rejected. DO NOT "tighten" relations.py to
// match this list — that would break the agent path (OQ-3 / D-KG-PREDICATE-
// VOCAB). Seeded from the shipped place-links (`contains/borders/route_to`,
// useWorldMap.ts) + the common character/faction predicates.
export const RELATION_PREDICATES = [
  'ally_of',
  'enemy_of',
  'member_of',
  'mentor_of',
  'parent_of',
  'located_in',
  'owns',
  'part_of',
  'contains',
  'borders',
  'route_to',
] as const;

export type RelationPredicate = (typeof RELATION_PREDICATES)[number];
