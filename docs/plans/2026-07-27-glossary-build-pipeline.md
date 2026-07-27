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
## ✅ M6 — SCHEMA-AWARE EXECUTOR (built + live-proven 2026-07-27)

**Outcome — attribute fill, measured on the live Mị Đế book (same source text, same model):**

| Run | Fields asked | Fields filled | Miss |
|---|---|---|---|
| `019fa28f` (before) | 38 | 19 | **50%** |
| `019fa2e5` (after) | 26 | 26 | **0%** |
| `019fa2f7` (after) | 26 | 26 | **0%** |

Empty shells: **5 → 0**. Suite 2529 passed.

**What was built** — the ontology read (`read_book_ontology`, minted service bearer, fetched
ONCE per run), the no-empty-shell intersect at the write boundary, and per-kind field selection
sized by a POC (`eval/schema_recall_poc.py`, 6 arms): narrowing a schema pays only when it is
WIDE (power_system 7→3 = +66% depth; terminology 4→2 = no change), so `NARROW_THRESHOLD=4`
gates it; same-kind items batch 3-at-a-time (3× cheaper, mild decay) but **never** mixed kinds.
The POC also **overturned an assumption**: injecting each field's authored `auto_fill_prompt`
made quality *worse* (123 → 96 chars/field) and cost 20% more tokens — those hints are written
for humans and dilute attention. So the prompt carries field codes + SHAPE only.

**Two steering defects found after the first live re-run — both were the SAME mistake, one
level down: reading the schema but throwing its metadata away.**

1. *Type stripped in, typed value destroyed out.* `aliases` is `field_type=tags`. The prompt
   sent bare field names plus "1-3 câu" — wrong instruction for a list — and the postprocess ran
   `str(v)` on everything, turning the model's correct JSON array into a Python repr
   `"['a','b']"` that the glossary then wrapped again → `["['a','b']"]`. The model was right;
   the platform mis-instructed it and then corrupted the right answer. Fixed by rendering each
   field's shape (`"aliases": ["...", "..."]` vs `"description": "... (2-4 câu)"`) and keeping
   lists intact. Live: `["Lõi năng lượng nguyên thủy","Điểm kỳ dị của thần hồn","Mỏ neo bản thể"]`.
2. *`sort_order` used as a value signal.* It is FORM LAYOUT (short scalars first, prose last).
   Slicing `item` by it kept `name/aliases/type/owner` and dropped BOTH `description` and
   `symbolic_meaning` — every field carrying meaning. Fixed to rank by information density
   (required → textarea → text → tags). Live: `Pháp khí` now keeps its two prose fields.

**Declared absence (added same cycle).** Fiction is not a form to be filled: a kind can define
an attribute the story has not established yet. The executor now offers an explicit `null` (with
a deliberately HIGH bar — "not a way to avoid work"), and the postprocess splits the result into
`absent` (the model said there is no basis — an authoring prompt for the human at CP2) vs
`missing` (never answered — an attention drop, the *only* signal that would justify a repair
call). Both ride on the item in the run API. Word forms count too (`"chưa xác định"` etc.),
or the placeholder itself lands in the SSOT as canon.

*Why no auto-repair loop:* with fill at 0% miss there is nothing to recover, and a retry that can
only succeed by producing text is a hallucination pump — it re-asks for what the story has no
answer to and the model obliges. **Fill-rate is a diagnostic, not a target.** The glossary is the
SSOT, so an invented `owner` propagates to KG → plan → draft and becomes canon the author never
chose. The asymmetry says: bias to under-fill, and let the human close the gap.
Live-proven on `019fa32b` (`Pháp khí`, deep, full 6-field schema):
`absent=["aliases","owner"]`, `missing=[]` — exactly the two fields the source text is silent on,
with the other four fully written. Note the deep path DOES invent (it named materials the source
never gives) — which is precisely why CP2 is a human, not a loop.

<details><summary>Original M6 diagnosis (2026-07-27, before the build)</summary>

**The finding (quality audit of the wizard's own output).** The executor emits a FIXED,
character-shaped attribute set (`name/description/role/personality/…`) for EVERY kind. It
never reads the kind's real schema. Measured on the live Mị Đế build:

| Kind | Schema offers | Executor filled | Result |
|---|---|---|---|
| `terminology` | `term, definition, category, usage_note` | none of them | **5 EMPTY SHELLS** — `entity_snapshot IS NULL`, no name, reported "proposed" |
| `power_system` | `name, description, type, effects, rank, user, aliases` | `name, description` | 2/7 — silent loss |
| `item` | `name, description, type, owner, symbolic_meaning, aliases` | `name, description` | 2/6 |
| `organization` | `name, description, type, leader, headquarters, members, aliases` | `name, description` | 2/7 (the hand-authored Lâm gia has 6) |

Worst casualty: **Chân Linh** — the story's ten-thousand-year callback anchor — is an empty row.
Root cause is one line of design: the prompt hardcodes attributes instead of consuming the
ontology the platform already authored (`book_attributes` even carries `auto_fill_prompt`, a
per-attribute hint written FOR an AI to use — stored but unread, the SET-standard bug shape).

**The fix (designed, ready to build):**
1. `glossary_client.read_book_ontology(bearer, book_id)` → `GET /v1/books/{id}/ontology`
   (the public route DOES carry attribute defs; the internal `/internal/…/ontology` is
   contract-bound to knowledge-service's `OntologyKinds` and returns kinds only — do NOT
   widen it). The background driver has no user bearer, so mint one with the existing
   `mint_service_bearer(owner, settings.jwt_secret)` — the same pattern the MCP path uses
   for book-service draft routes.
2. Fetch the ontology ONCE per run; pass the target kind's real attribute codes + their
   `auto_fill_prompt`/description into the executor and distill prompts, and require output
   keyed by those codes.
3. **No-empty-shell invariant at the write boundary**: intersect the built attribute codes
   with the kind's defs — zero intersection ⇒ `skipped` with a reason, never a hollow row.
4. Re-run for the 5 shells (delete them first) and re-verify attribute fill per kind.

Expected gain: entity richness roughly triples for non-character kinds, and the empty-shell
class becomes impossible.

</details>

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
