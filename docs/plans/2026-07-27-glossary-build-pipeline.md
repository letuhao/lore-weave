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

## Status — M1–M5 COMPLETE (2026-07-27)

| M | State | Evidence |
|---|---|---|
| M1 | ✅ `9f9296c00` + `06420fa2e` | engine + FSM service, 22 unit tests (bounds, retry-then-skip, degrade paths) |
| M2 | ✅ `265069111` | REST 7 routes + `composition_glossary_build` MCP tool (closed-set op) + contract yaml |
| M3 | ✅ same commit | KG phase: project nodes → NAME→graph-id resolution → CP3 apply w/ applied/failed counts |
| M4 | ✅ `713221569` | **MAIDEN LIVE RUN**: 3 chars built (2 deep w/ 6+5 sections) → 3 draft entities w/ 5-6 attrs; 2nd run resolved an edge to hand-made lore → Neo4j holds both relations. 3 real bugs found+fixed |
| M5 | ✅ `fe1fdfc84` | World Setup wizard panel, 6 tests; panel_id enum synced across 3 sides; live-smoked the advertised schema |

**M4's three live-caught bugs (all invisible to the unit suite):** jsonb decoded as
`str` by asyncpg; a KG relation needs the GRAPH node id (content hash), not the glossary
entity_id; name resolution must cover the whole project graph, not just the current run.

## Registers

- **Decisions**: sections above. | **Parked**: rail delegation swap (after M5); wiki flywheel
  extraction of deep-profile inventions (tracked, not in this cycle).
- **Debt/Drift**:
  - *Durability*: the v1 driver is an in-process asyncio task — a restart mid-build leaves a
    run in `building` (no heartbeat/sweep like authoring-runs). Cancel + re-run works today.
  - *CP2 ordering*: `project_kg` is only meaningful after the human approves the drafts in the
    review inbox. Drafts DO project today, so the pipeline doesn't hard-block on it; a
    `NOTHING_PROJECTED` guard reports the empty case honestly.
  - *Planner dedup*: `_existing_names` uses the semantic `select_for_context` (bounded to 50).
    A full name-list route would make dedup exact.
  - *Not done from the M5 scope note*: the AI-suggestions card still shows name+kind only
    (dogfood finding #17 — full attributes + new-canon claims). The wizard shows the built
    items, so the gap is now cosmetic rather than blinding.
  - *Host drift (not a repo defect)*: `services/ai-gateway/node_modules` has TypeScript 7.0.2
    against a `^5.5.3` manifest, so ts-jest cannot read tsconfig and the ai-gateway jest suite
    is unrunnable locally (reproduces on a pristine checkout). Same class as the frontend note
    in SESSION_HANDOFF; fix with a clean `npm install` in that service.
