# Glossary-Build + KG-Build pipeline — build plan (RUN-STATE)

**Spec:** `docs/specs/2026-07-27-glossary-kg-build-workflows.md` (POC CLOSED — 4 experiments).
**Effort:** XL. **Re-read this file first after any compaction.**

## Locked decisions (from spec + PO)

1. State machine OUTSIDE the agent; LLM calls only fill content. One LLM call NEVER both
   reasons deeply and fans out (planner enumerates; executor builds ONE item).
2. Home: **composition-service** (Python=AI rule; owns authoring-run FSM precedent; models via
   provider-registry — model_ref from the run params, NO hardcoded model).
3. Depth dial per worklist item: `standard` (single-shot) | `deep` (plan→steer loop, E4 shape,
   varied craft instruction per section, long-form sections + 1 distill call → attributes).
4. Relations by NAME (closed-set types); platform resolves names→ids after entities exist.
5. Human checkpoints: (1) worklist approve/trim, (2) review inbox (existing glossary drafts),
   (3) edges review. New-canon claims surfaced distinctly at (2).
6. Bounds: 1 retry per invalid-JSON call then skip-with-record. No unbounded loops possible.

## FSM (table `glossary_build_runs` in loreweave_composition, + `glossary_build_items`)

```
run:   draft → planning → plan_ready → [CP1 approve] → building → proposing →
       proposed → [CP2 via glossary inbox] → kg_projecting → edges_ready →
       [CP3 approve] → done   (any state → failed/cancelled; resumable by row)
item:  pending → building(section i/N for deep) → built → proposed(entity_id) →
       skipped(reason)
```

Scope: `owner_user_id` + `book_id` on every row (tenancy). Params carry `model_ref`
(explicit; user_default_models is empty for the test account), `source_text`, `max_items`,
`deep_threshold` (planner assigns depth; params can cap deep count).

## Milestones (each = commit + tests; live-smoke on Mị Đế at M4)

- **M1 — engine**: `app/services/glossary_build/` (service + prompts + FSM repo), migrations.
  Planner prompt (enumerate-only, dedup vs existing glossary via glossary internal API);
  executor standard prompt (E1/E3 shape); deep loop (E4: plan sections → steer each, varied
  craft instruction; distill call → attributes). Pure-unit tests with fake SDK (schema-valid,
  bounds, retry-then-skip).
- **M2 — REST + MCP**: `/v1/glossary-build/runs` CRUD + step-advance endpoints (create,
  approve-plan, start, status, approve-edges, cancel) + contracts/api entry; MCP tool
  `composition_glossary_build` (unified enum-dispatch op, closed-set — Frontend-Tool-Contract
  discipline) so chat can DELEGATE to the pipeline (rail later replaces its 9 steps with one
  delegation).
- **M3 — writes**: proposals via glossary-service internal propose API (draft entities, 1
  item/call); KG phase via knowledge-service internal APIs (ensure-project idempotent,
  entities-to-nodes, edges from name-resolved relations). Cross-store best-effort try/except
  (memory lesson); outbox events if any new event type (register in OUTBOX_SOURCES).
- **M4 — maiden run (live smoke)**: Mị Đế — Tô Thanh Dao (deep), Lâm Trạch (deep),
  Huyết Vô Thường (standard) + relations. DB-verified: 3 active entities w/ attrs, KG nodes +
  edges in Neo4j. This is the VERIFY evidence gate.
- **M5 — FE wizard**: `frontend/src/features/glossary-build/` (hooks/context/components per
  MVC), World Setup panel (Pass Rail UX): paste text → worklist review (CP1) → progress
  (item i/N, section j/M) → inbox link (CP2) → edges review (CP3). Update FEATURE_INDEX.md.
  AI-suggestions card upgraded to show full attributes + new-canon claims (dogfood #17).

## Registers

- **Decisions**: sections above. | **Parked**: rail delegation swap (after M5); wiki flywheel
  extraction of deep-profile inventions (tracked, not in this cycle).
- **Debt/Drift**: (append as found)
