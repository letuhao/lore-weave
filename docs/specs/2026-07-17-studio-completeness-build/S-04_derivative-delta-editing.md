# S-04 · Derivative (dị bản) delta editing

> **Tier A — DATA-layer build (port surface).** `derivatives.py` = create_spec / create_override / get /
> list only; the sole writer is `perform_derive` at derive-time, so **the deltas are frozen at creation**.
> After making a dị bản the author cannot change its taxonomy/pov/added-rules, nor add/edit/remove a
> per-entity field override — the only "edit" is archive-the-whole-branch and re-derive. `DivergenceManagerView`
> shows deltas it cannot mutate. **No HTML draft** — that view is the design reference. **Service:** composition.

## 1. Current state (verified)

```
divergence_spec (migrate.py:146)  — ONE per derivative Work (work_id FK, CASCADE)
  taxonomy CHECK('pov_shift'|'character_transform'|'au')  · pov_anchor UUID?  · canon_rule TEXT[]
entity_override (migrate.py:164)  — MANY per Work (idx on work_id)
  target_entity_id UUID  · overridden_fields JSONB
scope on both: book_id (tenancy, via work_id) · created_by (actor stamp)
```
`derivatives.py` writes both only inside `perform_derive` (`works.py:389`). No update/delete of either.

## 2. Scope decision — field-overrides + spec, NOT relationship/event overrides

The audit noted relationship/event overrides are an **explicit M0 deferral**. This spec covers exactly what
exists today: the `divergence_spec` row and `entity_override.overridden_fields` (field-level). Relationship
and event overrides remain deferred to their own track — do not build them here.

## 3. Repository methods (new)

**divergence_spec (one per work — UPDATE only, no create/delete here):**
- `update_spec(work_id, book_id, *, taxonomy?, pov_anchor?, canon_rule?) -> DivergenceSpec | None` —
  `UPDATE divergence_spec SET <provided> WHERE work_id = $ AND book_id = $`. `taxonomy` is CHECK-constrained
  — validate against the same closed set before the write (return a domain error → 422 on a bad value, never
  let the CHECK 500). No create (a spec exists from derive-time); no delete (deleting the spec = archiving
  the derivative Work, which already has a path — `composition_archive_derivative`).

**entity_override (many — full CRUD):**
- `add_override(work_id, book_id, created_by, target_entity_id, overridden_fields) -> EntityOverride` —
  standalone create AFTER derive (the missing "add an override later"). One override per
  (work_id, target_entity_id) — add `UNIQUE(work_id, target_entity_id)` so a second add is an upsert-or-409,
  not a silent duplicate.
- `update_override(work_id, book_id, override_id, overridden_fields) -> EntityOverride | None` — replace the
  JSONB (a field-set edit; whole-object replace is correct here — the override IS the delta).
- `delete_override(work_id, book_id, override_id) -> bool` — hard delete (an override is a pure delta, no
  history to preserve; removing it reverts that entity to canon).

**Migration:** `CREATE UNIQUE INDEX IF NOT EXISTS uq_entity_override_work_target ON entity_override(work_id,
target_entity_id);` (backs the add-upsert semantics; safe — the derive-time writer already writes at most one
per target).

## 4. Tenancy

Both tables carry `book_id`; every route resolves the derivative Work → its book → the E0 grant (EDIT), then
scopes by `work_id` + `book_id`. A `target_entity_id` in an override must belong to the book's graph — verify
at the route (a cross-book entity override is a tenancy breach). `created_by` stays a stored actor stamp,
never a filter (PM-5).

## 5. REST routes

```
PATCH  /v1/composition/works/{work_id}/divergence-spec            (update taxonomy/pov/canon_rule)
GET    /v1/composition/works/{work_id}/entity-overrides           (list — repo.list already exists)
POST   /v1/composition/works/{work_id}/entity-overrides           (add-after; 201; 409 on dup target)
PATCH  /v1/composition/works/{work_id}/entity-overrides/{id}      (replace overridden_fields)
DELETE /v1/composition/works/{work_id}/entity-overrides/{id}      (204 — reverts entity to canon)
```

## 6. MCP tools (agent parity)

`composition_divergence_spec_update` + `composition_entity_override_{add,update,delete}`. `taxonomy` is a
**closed-set enum** (`pov_shift|character_transform|au`) registered in `CLOSED_SET_ARGS`. `overridden_fields`
is a structured JSON arg.

## 7. Frontend (in `DivergenceManagerView` — no new panel)

The view already lists the spec + overrides read-only; make them editable: an inline taxonomy/pov/canon
editor on the spec header, and add/edit/remove affordances on the override list, plus an "override another
entity" action (entity picker → field-set editor). Persist via the routes above; refresh via a Lane-B
`divergenceEffects` handler (agent parity). No draft — the layout exists.

## 8. Tests

- **spec update:** taxonomy change persists; an off-enum taxonomy → 422 (not a 500 from the CHECK); pov/canon
  edits round-trip.
- **override CRUD:** add-after creates; a second add for the same target → 409 (the new unique); update
  replaces the field-set; delete reverts to canon (the row is gone, the generation reads canon).
- **tenancy:** EDIT grant required; an override targeting an entity outside the book is rejected; work-scope
  isolation (work A's routes can't touch work B's overrides).
- **MCP parity:** each tool round-trips; taxonomy enum enforced at the contract layer.
- **regression:** `perform_derive` still writes spec + initial overrides unchanged; the generation path still
  reads the (now mutable) deltas.

## 9. Out of scope / by-design

- Relationship + event overrides — explicit M0 deferral, separate track.
- No DELETE of `divergence_spec` — deleting it = archiving the derivative Work (existing path).
- No LIST-of-a-book's-derivatives here — that is a separate small route (the audit's derivative-LIST gap);
  fold into S-09 wire-ups.
