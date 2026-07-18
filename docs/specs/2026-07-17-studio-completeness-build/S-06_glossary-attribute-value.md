# S-06 · Glossary attribute-value — add-later via REST + delete the row

> **Tier B — route wire-up (no draft).** Entity attribute-values are seeded from the kind's attrs at entity
> create (`entity_handler.go:472`); the only add-later path is MCP `glossary_entity_set_attributes`
> (`entity_attribute_edit_tools.go:256`). **If the book ontology gains an attribute after an entity exists,
> only an LLM can fill it — the REST/GUI editor can't.** And a value can be cleared (empty string) but its
> row + child items/history never deleted. **Service:** glossary-service (Go).

## 1. Current state (verified)
- REST attr-value surface: `PATCH /attributes/{attr_value_id}` (`patchAttributeValue:85`) edits an EXISTING
  value in place. No **add** route (add is MCP-only); no **delete** route (`server.go:534` has PATCH, no
  DELETE).
- The kind→entity attr seeding is at `entity_handler.go:472`; a later-added attr-def leaves existing entities
  without that value row until something writes it.

## 2. Routes (new)
```
POST   /v1/glossary/entities/{entity_id}/attributes         (add a value for an attr-def added after create)
  body: { attribute_def_id, value }                          → 201; 409 if the value row already exists
DELETE /v1/glossary/attributes/{attr_value_id}               (remove the row, not just blank it; 204)
```
The add route mirrors the MCP `glossary_entity_set_attributes` write path — reuse its store method so there
is one write, not two. Tenancy: `book_id`-scoped via the entity, grant-gated (EDIT), exactly like
`patchAttributeValue`. The delete cascades to the value's child items/history (a value row's history is
scoped to the value; removing the value removes its own trail — not other entities').

## 3. MCP
`glossary_entity_set_attributes` already covers agent add/edit. Add nothing unless a dedicated
`glossary_attribute_value_delete` is wanted for agent parity on the new delete verb — **defer** (agents
rarely delete a single attr row; the human GUI is the driver). Record as a conscious asymmetry.

## 4. FE (affordance on the entity editor — no new panel)
On the entity attribute list: if an attr-def exists on the kind but the entity has no value row for it, show
an "＋ add value" affordance (→ POST). On each value row, a "remove" action (→ DELETE, distinct from
clearing to empty). This closes the "an LLM can fill it but you can't" blind spot the audit named.

## 5. Tests
- add: a value for a post-create attr-def lands; a second add for the same (entity, attr-def) → 409.
- delete: removes the row (not blank); grant-gated; another book's entity is untouchable.
- tenancy: EDIT grant required; book-scope isolation.
- regression: entity-create seeding + `patchAttributeValue` in-place edit unchanged.
