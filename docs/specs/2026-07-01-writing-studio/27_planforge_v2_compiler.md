# 27 · PlanForge v2 — the multi-pass compiler

> **Status:** 📐 SEALED (multi-agent authored + adversarially reviewed 2026-07-10; PO ratified all product decisions same day — see 00B §6) — buildable
> **Scope:** `composition-service` (Python) + `contracts/plan-forge/` + a thin GUI data surface (wiring owned by the Plan Hub spec, see Ownership).
> **Supersedes:** [`2026-06-30-planning-pipeline-architecture.md`](../2026-06-30-planning-pipeline-architecture.md) (DESIGN DIRECTION, its three PO questions now closed by BPS-19 + this file). That file gains nothing; this file is its successor. **Extends:** [`09_PLANFORGE_BLUEPRINT.md`](../2026-07-01-plan-forge/09_PLANFORGE_BLUEPRINT.md) (M1–M4 shipped; its §9 checklist is stale — M4/M5 shown unchecked but the MCP tools and FE panels exist).
> **Foundation:** [`00A`](00A_BOOK_PACKAGE_STRUCTURE.md) BPS-14/17/18/19/20/21 + DA-13/DA-14 · [`23_book_architecture.md`](23_book_architecture.md) Phase E (owned here in detail) · [`22_scene_model_and_crud.md`](22_scene_model_and_crud.md) (amended seam).
> Follows [`docs/standards/mcp-tool-io.md`](../../standards/mcp-tool-io.md) (IN-1..8 / OUT-1..6 / CAT-1..4), [`docs/standards/settings-and-config.md`](../../standards/settings-and-config.md), [`docs/standards/scope-separation.md`](../../standards/scope-separation.md).

---

## Why

PlanForge v1 is a complete compiler with two defects the register already named. First, its
codegen output is only partially linked: `outline_skeleton` — the book's architecture — is
emitted and read by nothing (BPS-14/18, *"Writing Studio debt #1"*). Second, its downstream
expansion (`plan_pipeline`) is a **single opaque worker job**: all planning stages run
end-to-end in one AMQP message with no per-stage artifact, no human checkpoint, no resume
point, and no way to re-run one stage without paying for all of them. The 2026-06-30 review
holes (empty present-cast, anonymous new characters, `motif_coverage = {}`, ch1 telescoping)
were diagnosed as single-pass compilation failures — unresolved forward references — and
BPS-19 locked the cure: **stage it, in pass order, with the human blocking where the human is
the only oracle.**

v2 therefore does three things, and only three: (1) formalizes the seven planning steps as
**pass contracts** with named inputs, outputs, and resume keys, over the run/artifact
persistence that already exists; (2) gives the run a **multi-pass state machine** — pass
ledger, blocking/advisory checkpoints, make-style downstream invalidation, crash resume; and
(3) builds the **link step** (23 Phase E) so the compiler stops discarding its own output:
skeleton → `structure_node` + `outline_node`, grounded scenes → spec scenes with
`present_entity_ids` and `tension` a human can finally see and edit (a **generator-side**
writer for 22 F2's under-exposed fields, alongside the MCP/human writer 22 SC8 already
assigns them; PF-11 is the rule that lets the two coexist).

---

## Investigation findings

All read from source 2026-07-10, at HEAD of `feat/context-budget-law`. A sibling recon report
was spot-checked; every load-bearing claim below was re-verified directly.

### F1 — the run/artifact substrate is ready for passes; the pipeline is not

`plan_run` / `plan_artifact` ([`migrate.py:935-972`](../../../services/composition-service/app/db/migrate.py#L935-L972)) already
give v2 everything but the ledger: append-only artifacts with latest-wins reads
([`plan_runs.py:196-241`](../../../services/composition-service/app/db/repositories/plan_runs.py#L196-L241) —
`save_artifact`, `latest_artifact`, `DISTINCT ON (kind)`), a scratch `checkpoint_state` JSONB
(sole key written today: `pipeline_job_id`,
[`plan_forge_service.py:785-788`](../../../services/composition-service/app/services/plan_forge_service.py#L785-L788)),
and the async-job pattern with a lazy `sync_from_job` backstop
([`plan_forge_service.py:78-95`](../../../services/composition-service/app/services/plan_forge_service.py#L78-L95)).
But the artifact `kind` CHECK is closed over seven v1 kinds
([`migrate.py:967-969`](../../../services/composition-service/app/db/migrate.py#L967-L969)), and the pipeline itself is one worker op:
`run_plan_pipeline` ([`operations.py:112-138`](../../../services/composition-service/app/worker/operations.py#L112-L138))
calls `run_planning_pipeline` end-to-end and returns one blob.

### F2 — six of the seven passes already exist as engine modules; one does not

Verified module-by-module (the 2026-06-30 table is stale — most "MISSING" rows were built):

| v2 pass | Engine today | Ref |
|---|---|---|
| 1 motifs | `select_arc_motifs` | [`motif_plan.py:108`](../../../services/composition-service/app/engine/motif_plan.py#L108) |
| 2 cast | `propose_cast` (+ `canon_from_proposed`) | [`cast_plan.py`](../../../services/composition-service/app/engine/cast_plan.py) (Stage 0 docstring names the disease it fixes) |
| 3 world | **nothing** — `grep -rn world_plan app/` = 0 hits | — |
| 4 beats | L1 beat-map (`build_chapter_map_messages`/`parse_chapter_map`) + `shape_tension_curve` | [`arc_plan.py:56`](../../../services/composition-service/app/engine/arc_plan.py#L56); the curve is computed **inside** pass 6 today ([`grounded_plan.py:125`](../../../services/composition-service/app/engine/grounded_plan.py#L125)) — v2 hoists it |
| 5 character arcs | `plan_character_arcs` (arcs + `introduce_at_chapter`) | [`character_plan.py`](../../../services/composition-service/app/engine/character_plan.py) |
| 6 scenes | `grounded_decompose(cast, motifs, char_arcs, mapped, skip_l1)` | [`grounded_plan.py:82`](../../../services/composition-service/app/engine/grounded_plan.py#L82) |
| 7 self-heal | `run_plan_self_heal` (judge → satellite-edit → splice) | [`plan_heal.py:143`](../../../services/composition-service/app/engine/plan_heal.py#L143) |

The orchestrator [`planning_pipeline.py:54-125`](../../../services/composition-service/app/engine/planning_pipeline.py#L54-L125)
chains them **in memory** — no stage's output is persisted, and its own docstring concedes
*"Human checkpoints are the caller's concern"*. Every stage threads `cancel_check` and is
independently degrade-safe. v2's job is to materialize this chain, not rewrite it.

### F3 — the checkpoint machinery exists, at the wrong granularity, in the right shape

The structural-mutation quarantine is built and battle-hardened:
`plan_bootstrap_proposal` (pending → approved → applying → applied, atomic claim, per-item
idempotent resume, [`bootstrap_service.py:206-321`](../../../services/composition-service/app/services/bootstrap_service.py#L206-L321)),
including glossary seeding through `seed_entities_or_raise` with partial-result detection.
PROPOSE computes a diff exactly once; APPLY replays what was approved, never re-negotiates
([`bootstrap_service.py:8-12`](../../../services/composition-service/app/services/bootstrap_service.py#L8-L12)).
This is precisely the diffable-checkpoint pattern BPS-19b needs — but today it fires only
*after* the whole pipeline, and stage 0 **bypasses it**: `run_planning_pipeline` seeds the
glossary directly (`seed_cast=True`,
[`planning_pipeline.py:77-83`](../../../services/composition-service/app/engine/planning_pipeline.py#L77-L83)).

### F4 — the link step is absent, and its absence is load-bearing

`compile_artifacts` emits `outline_skeleton` in the IR's shape
([`compile.py:71-91`](../../../services/composition-service/app/engine/plan_forge/compile.py#L71-L91));
the deliberate comment at [`compile.py:130-132`](../../../services/composition-service/app/engine/plan_forge/compile.py#L130-L132)
says it *"stays — Phase E links it into `structure_node`"*. Nothing reads it (BPS-14,
re-verified: the only consumers of the compiled dict are the `package` artifact write and
`bootstrap_service`'s reads of `chapters`/`glossary_seeds`). Pass 6's scene output has the
same fate at a finer grain: grounded scenes (with `present_entity_ids`, `tension`) reach the
manuscript only as **plain-text drafting guides** joined by `chapter_id == event_id`
([`bootstrap_service.py:34-50`](../../../services/composition-service/app/services/bootstrap_service.py#L34-L50)) —
they never become spec scenes, which is why 22 F2's `present_entity_ids`/`tension` have no
writer a human or agent can reach today (22 SC8 assigns them an MCP writer, not yet shipped;
the scene link is the generator-side counterpart).

### F5 — fixture taint: contracts and service paths

- [`planner_state.schema.json:7`](../../../contracts/plan-forge/planner_state.schema.json#L7) hardcodes
  `required: ["PA","HA","CD","THR"]` + `additionalProperties:false` — one novel's variables
  (BPS-21, confirmed). `VariableDef` ([`novel_system_spec.schema.json:109-123`](../../../contracts/plan-forge/novel_system_spec.schema.json#L109-L123))
  has no `initial`, so [`compile.py:16`](../../../services/composition-service/app/engine/plan_forge/compile.py#L16)
  forces every variable to start 0. Nothing reads `planner_state` today (latent).
- [`plan_forge_service.py:34-35`](../../../services/composition-service/app/services/plan_forge_service.py#L34-L35)
  pins `_FIXTURES`/`_FIDELITY` to the POC fixture; live `self_check()` and `interpret()`
  compute coverage against **`story-plan-v1.md` for every user's run** when the fixture file
  exists ([`:593-604`](../../../services/composition-service/app/services/plan_forge_service.py#L593-L604), [`:658-669`](../../../services/composition-service/app/services/plan_forge_service.py#L658-L669)), degrading to `consistency_audit` + `run_rules` when absent.
- Four fixture-specific `validate.py` rules were demoted to `tier:"advisory"`
  (D-PLANFORGE-GENERAL-VALIDATE); `_hard_rules_pass` gates on hard tier only
  ([`plan_forge_service.py:48-53`](../../../services/composition-service/app/services/plan_forge_service.py#L48-L53)).

### F6 — MCP + HTTP surface today

All 8 blueprint tools are wired ([`mcp/server.py:3117-3350`](../../../services/composition-service/app/mcp/server.py#L3117-L3350))
with `require_meta` tiers, `async_job` flags, and the shared `_resolve_model_ref` default-model
fallback. HTTP: runs/patch/validate/refine/interpret/self-check/compile
([`routers/plan_forge.py:60-229`](../../../services/composition-service/app/routers/plan_forge.py#L60-L229)).
`plan_compile(run_pipeline=true)` enqueues the monolithic `plan_pipeline` job and persists
`checkpoint_state.pipeline_job_id`. There is no per-pass surface of any kind.

### F7 — beat source gap

`compile()` passes `beats: []` because a PlanForge `arc_kind` (a theme tag, enum
`setup/discovery/power/transition/other`) is **not** a `structure_template.kind` — the code
comment at [`plan_forge_service.py:726-741`](../../../services/composition-service/app/services/plan_forge_service.py#L726-L741)
states there is no mapping and refuses to invent one. Consequence: L1 degrades to a no-op,
`beat_role` stays None, and the tension curve shapes over nothing. The `deps/` registry
(`structure_template`) exists and is retrievable; the bridge is simply unbuilt.

---

## The pass architecture (PF-1)

The seven steps are seven passes over one compiled arc package (BPS-19c: one arc is the scope
unit). Order is forced by data dependencies, not preference:

```
                 package (plan_compile output — the object file)
                    │
   ┌────────────────┼───────────────┐
   ▼                ▼               │
 1 motifs        2 cast ── bootstrap(cast) ──▶ glossary     SYMBOL TABLE
   │                │  └──▶ structure_node.roster_bindings
   │                ▼
   │             3 world ── bootstrap(world) ──▶ glossary
   ▼                │
 4 beats ◀──────────┘   (+ optional structure_template)      SCHEDULING
   │
   ▼
 5 character_arcs  (cast × beats → introduction schedule)    DEFINITE ASSIGNMENT
   │
   ▼
 6 scenes          (conditioned on 1–5 + planner_state)      CODEGEN
   │
   ▼
 7 self_heal       (judge → satellite → splice)              LINT
   │
   ▼
 scene link ──▶ outline_node kind='scene'  (the pass-6/7 linker, DA-13)
```

### Pass contracts

`pass_id` is a closed set (IN-3): `motifs · cast · world · beats · character_arcs · scenes ·
self_heal`. For every pass: inputs are resolved **by `pass_state` pointer** (the artifact id
recorded at the producing pass's completion), never by latest-kind lookup — see PF-3.

| # | `pass_id` | Compiler analogue | Engine | LLM/rules | Input artifacts | Output artifact kind | Checkpoint | Resume key |
|---|---|---|---|---|---|---|---|---|
| 1 | `motifs` | dependency resolution (`deps/` → selection) | `motif_plan.select_arc_motifs` (exists) | LLM + retrieval | `package` | **`motif_plan`** | advisory | `(run_id,'motifs',fp)` |
| 2 | `cast` | **symbol-table population** | `cast_plan.propose_cast` + `heal_canon.canon_from_proposed` (exist) | LLM | `package` | **`cast_plan`** | **BLOCKING** — cast bootstrap proposal | `(run_id,'cast',fp)` |
| 3 | `world` | symbol table (settings/factions/locations) | **NEW `engine/world_plan.py`** (mirror `cast_plan.py`'s shape: propose → tolerant parse → degrade-safe `[]`) | LLM | `package` + `cast_plan` | **`world_plan`** | advisory — world bootstrap proposal (apply may lag) | `(run_id,'world',fp)` |
| 4 | `beats` | **scheduling** (beat budget + tension curve) | L1 (`plan.build_chapter_map_messages`/`parse_chapter_map`) + `arc_plan.shape_tension_curve`, **hoisted out of pass 6** | LLM (L1) + rules (curve) | `package` + `motif_plan` + optional `structure_template_id` | **`beat_plan`** | **BLOCKING** — arc-shape review | `(run_id,'beats',fp)` |
| 5 | `character_arcs` | definite-assignment analysis (no symbol used before introduced) | `character_plan.plan_character_arcs` (exists) | LLM | `cast_plan` + `beat_plan` | **`char_arc_plan`** | advisory | `(run_id,'character_arcs',fp)` |
| 6 | `scenes` | **code generation**, conditioned on 1–5 | `grounded_plan.grounded_decompose` (exists; `skip_l1=True`, curve supplied from `beat_plan`) | LLM | `package` (incl. `planner_state` + per-event `var_deltas`) + `cast_plan` + `motif_plan` + `beat_plan` + `char_arc_plan` | **`scene_plan`** | advisory | `(run_id,'scenes',fp)` |
| 7 | `self_heal` | lint / peephole | `plan_heal.run_plan_self_heal` (exists; canon from `cast_plan`) | LLM judge + satellite edits | `scene_plan` (pass-6 pointer) + `cast_plan.canon` | new **`scene_plan`** (healed) + **`heal_report`** | advisory | `(run_id,'self_heal',fp)` |

`fp` = the pass's input fingerprint (PF-3). Every pass runs as one `plan_pass` worker job
(PF-4) and inherits the engine modules' existing `cancel_check` threading and `_NO_THINK`
reasoning suppression.

### What is new vs. lifted

**Lifted (adapters only):** passes 1, 2, 5, 6, 7 — the modules exist; v2 wraps each in an
artifact-in/artifact-out adapter instead of `planning_pipeline.py`'s in-memory chaining.
**New code:** pass 3 (`world_plan.py`); pass 4 as a discrete step (hoist L1 + curve out of
`grounded_decompose`); the pass runner itself; the link step; the checkpoint plumbing.
**Unchanged:** `run_planning_pipeline` stays as the legacy one-shot for
`plan_compile(run_pipeline=true)` (PF-18).

---

## Locked decisions

| # | Decision | Why |
|---|---|---|
| **PF-1** | **Seven passes, contract-first, order forced by data deps** (table above). `pass_id` is a closed-set enum registered in `CLOSED_SET_ARGS`. | BPS-19a. A pass may not run before its inputs are resolved; anonymous characters were uses of undeclared identifiers. |
| **PF-2** | **One `plan_artifact` kind per pass output**: `motif_plan`, `cast_plan`, `world_plan`, `beat_plan`, `char_arc_plan`, `scene_plan`, `heal_report`, plus `link_report`. The `plan_artifact_kind_chk` CHECK extends by exactly these 8. Artifacts stay append-only. | Reuses the existing persistence + `latest_artifact` API instead of inventing a pass table. Deliberate CHECK extension per the assignment; swap follows `migration-check-constraint-must-backfill-all-historical-blocks` (additive values — drop + re-add, no backfill needed). |
| **PF-3** | **Pass ledger = `plan_run.pass_state` JSONB; freshness is DERIVED, never stored.** Each entry records `{status, decision, artifact_id, job_id, input_fingerprint, bootstrap_proposal_id?, decided_by, decided_at}`. `input_fingerprint = sha256(ordered input artifact ids + explicit pass params)` — **model_ref excluded** (changing the default model must not silently stale a plan). A pass is *fresh* iff its recorded fingerprint equals the fingerprint recomputed from current pointers; *stale* otherwise. `pass_cursor` (max contiguous accepted+fresh pass) is **computed in serialization, never stored**. Inputs resolve by `pass_state` pointer, not latest-by-kind — pass 7 writes a new `scene_plan` and would otherwise stale itself against its own output. | DA-7 derive-don't-store; make semantics: re-running pass N needs **zero invalidation writes** — downstream passes go stale by derivation (PF-5). `checkpoint_state` stays scratch; the ledger is load-bearing state and gets its own column. |
| **PF-4** | **Each pass is one `generation_job`** — new worker op `plan_pass`, dispatched in [`job_consumer.py`](../../../services/composition-service/app/worker/job_consumer.py) beside `plan_forge_propose`/`refine`, finalized by a `_finalize_plan_pass_job` hook mirroring [`_finalize_plan_forge_job`](../../../services/composition-service/app/worker/job_consumer.py#L60-L68), with the existing `sync_from_job` lazy backstop extended to pass jobs. Crash resume: a completed job whose hook was missed is absorbed on next GET; a dead job re-enqueues just that pass. Enqueue idempotency: an active job for the same `(run_id, pass_id, input_fingerprint)` is returned, not duplicated — keyed on **fresh completed exists**, not on job activity alone. | The async_job pattern is a locked PO decision (09 §8b) and the propose/refine plumbing already proves it. `idempotency-gate-exists-not-active-version`. |
| **PF-5** | **Re-running a pass invalidates downstream by derivation.** New output artifact id ⇒ every downstream pass's recorded fingerprint mismatches ⇒ derived `stale`. The runner refuses to run pass N while any upstream pass is stale (run upstream first or pass `force`); `plan_pass_status` reports per-pass `fresh|stale`. | Exactly `make`: edit a header, dependents rebuild. No stored dirty flags to drift. |
| **PF-6** | **Checkpoints: blocking at pass 2 (cast identity) and pass 4 (arc shape); advisory at 1, 3, 5, 6, 7.** Per BPS-19b — ✅ **RATIFIED by the PO 2026-07-10** (P-8; OQ-1). A blocking pass completes with `decision:"pending"`; the runner stops. Approval/rejection + optional surgical `edits` (deep-merge onto the pass artifact, same `_deep_merge` as `patch_spec`) go through the extended `plan_review_checkpoint`. Advisory passes auto-accept (`decision:"auto"`) and remain reviewable/re-runnable after the fact. `auto_approve=true` (an explicit per-call arg, never an env flag — Settings & Configuration Boundary) converts blocking to advisory for autonomous runs (`authoring_runs` level 3/4). | The human blocks where the human is the only oracle. Editable-after beats blocked-always for cheap-to-redo passes (motif selection is a `deps/` resolution). |
| **PF-7** | **Pass 2/3 glossary mutations go through the bootstrap quarantine, never direct seeding.** The v2 runner calls a new glossary-only `BootstrapService.propose_seed(run_id, entities, kind)` building `{new_glossary_entities}` from the pass artifact (cast: `character`; world: `location`/`faction`/`concept`), deduped by the existing claimed-keys mechanism; **pass 2's `decision:"accepted"` requires its proposal `applied`** (the blocking gate falls out of the mutation gate); pass 3's may lag (advisory, degrade-safe grounding). The legacy pipeline's `seed_cast=True` direct write stays legacy-only. | F3: the quarantine exists, is idempotent-resumable, and is the *"diffable proposal per the plan_bootstrap_proposal pattern"* the assignment names. One approval mechanism, not two. |
| **PF-8** | **The link step (23 Phase E) has two halves.** (a) **Skeleton link** — `link_outline_skeleton(run_id)` runs **inline at `compile()`** (deterministic, no LLM, composition-local): `outline_skeleton` arcs → `structure_node (kind='arc')`, chapters → `outline_node (kind='chapter', structure_node_id, book_id)`. (b) **Scene link** — `link_scene_plan(run_id)` runs at pass-6/7 acceptance: healed scenes → `outline_node (kind='scene')` under the linked chapter, carrying `title`, `synopsis`, `tension`, `present_entity_ids` (names resolved to glossary ids via the KAL roster join pass 6 already uses). Both are re-runnable via the `plan_link` tool. Linked nodes carry `chapter_id NULL` until bootstrap [A] stamps it — the "planned, not yet written" state, which **requires the `outline_chapter_required` swap in §Target data model** (the pre-v2 CHECK rejects every link insert). **Zero nodes linked ⇒ `success:false`, never a silent 200** (E4; per-target created/updated/unchanged/skipped counts always returned and persisted as a `link_report` artifact). | BPS-18/DA-13: an emitted artifact with no linker is a bug. Inline-at-compile because a compile that materializes nothing *is* the silent-success bug at compile scale. Spec writes need no human gate — the spec layer is the agent's normal CRUD surface (23 BA11); the heavy gate guards manuscript + glossary (PF-7). |
| **PF-9** | **Provenance is additive and never overloads `arc_template_id`.** `structure_node` gains `plan_run_id UUID NULL` + `plan_arc_id TEXT NULL`; `outline_node` gains `plan_run_id UUID NULL` + `plan_event_id TEXT NULL` (chapter: the event id; scene: `"{event_id}:{ordinal}"`). `arc_template_id` stays NULL for PlanForge-authored arcs — it references the `deps/` registry and a plan run is not a template (DA-10: one name, one concept). | BA13 keeps template provenance nullable; a second, orthogonal provenance axis must not squat on it. Additive per the assignment. |
| **PF-10** | **Link idempotency = partial UNIQUE on `(book_id, plan_run_id, plan_arc_id/plan_event_id)`**; upsert via `ON CONFLICT` **repeating the partial index's WHERE clause**. Cross-run near-duplicates (a second run re-planning the same arc) are **surfaced in the `link_report` (title-match heuristic), never auto-merged**. | **Refines BPS-18**, which named bare `event_id` as the idempotency key: event ids are stable within a run (surgical refine) but 0%-stable across re-proposes (POC 03: title overlap 100%, ID overlap 0%) — so the key must be run-scoped. Within-run re-link-updates-never-duplicates semantics are exactly BPS-18's; only cross-run behavior changes (a fresh run's near-duplicates are surfaced per OQ-3, never merged into a prior run's nodes). Recorded here per the register's never-silently-deviate rule. `postgres-partial-index-on-conflict-predicate-must-match`. Never-guess, per 23's migration guards. |
| **PF-11** | **A re-link never silently reclaims an author's edit.** Each `link_report` records the `version` of every node it wrote. On re-link, a node whose current `version` exceeds the last-linked version gets **structural linkage only** (parentage/provenance), keeps its authored fields, and is reported `preserved_user_edit`. | BPS-12's `source: generator|author` principle applied to the linker; the write-only bug class inverted. |
| **PF-12** | **The introduction schedule has no new column.** Intent lives in `char_arc_plan` (`introduce_at_chapter`); pass 6 stages it into the introduction scene's `present_entity_ids`; the *realized* introduction is **derived**: first scene by `story_order` whose `present_entity_ids` contains the entity. Planned-vs-realized drift surfacing belongs to the conformance/staleness spec (26). | DA-7. The signal (`present_entity_ids`) exists on `outline_node` and finally gets a writer via PF-8(b). "Keep minimal" per the assignment. |
| **PF-13** | **The symbol table lands in the spec, not only in the run.** After the cast proposal applies, pass 2 writes `structure_node.roster_bindings` (`{role_key: glossary_entity_id}` for protagonist/antagonist/mentor/… roles) on the linked arc via `StructureRepo`. A test asserts the packer's prompt changes when the binding changes (BA12's effect-test discipline). | Otherwise `cast_plan` is a stored-but-unread blob on the spec side — the exact F1 bug `structure_node` was built to kill. |
| **PF-14** | **BPS-21 executed here.** `VariableDef` gains optional `initial: number` (default 0); `planner_state.schema.json` drops the four fixture keys for `patternProperties: {"^[A-Z]{2,4}$": {"type":"number"}}` + free-string nullable `tier`; `compile.py` seeds each variable at `initial`. **And `planner_state` gains its first reader:** pass 6's prompt includes the variable ledger (entry state + per-event `var_deltas`) so scenes respect declared trajectories. Schema cleanup rides along: `CompileTargets.planner_state_init` removed (compile stopped emitting it — DA-13), `VarDelta.coupled_to_realm` relaxed `const:false` → `boolean`. | The generic source (`spec.layers.variables`) already exists and compile already derives from it; only the baseline was inexpressible. A contract nothing validates at runtime is safe to fix now, and giving the payload a reader closes its write-only smell instead of institutionalizing it. |
| **PF-15** | **`genre_tags` = explicit, persisted input on run create** (✅ **RATIFIED by the PO 2026-07-10**, closes BPS-20's open sub-question): optional `genre_tags: string[]` (maxItems 8) on `plan_propose_spec` / `POST /plan/runs`, stored as `plan_run.genre_tags`, threaded to `compile_artifacts(genre_tags=…)` and every pass (`propose_cast`, `select_arc_motifs`, `convention_for` all already take it). Omitted ⇒ `[]` — honest beats wrong. | `Meta` is `additionalProperties:false` in a frozen contract, and genre is a fact the author knows about the book, not something to mine from the plan doc. An explicit arg beats a hidden setting (the silent-hidden-default bug class); a per-book settings fallback can layer on later without breaking this. |
| **PF-16** | **Pass 4's beat source is an optional, explicit `structure_template_id`.** Present: the template's `beats` feed L1 (a `deps/` resolution — same move as pass 1's motif selection). Absent: pass 4 runs template-less (L1 skipped; the curve shapes from event order + a default arc envelope). **No silent `arc_kind` → template auto-map, ever** — `arc_kind` is a theme tag ([F7](#f7--beat-source-gap)). | The bridge the recon flagged, built as explicit dependency resolution instead of an invented mapping. Mirrors BPS-10's no-auto-mint instinct. |
| **PF-17** | **MCP surface: three new tools + one extension; all eight v1 tools survive.** New: `plan_run_pass` (A, async_job; `mode: "single"\|"through"` — CAT-1: the branches share every field, so one tool), `plan_pass_status` (R, `@small_return` — 7 ledger rows), `plan_link` (A — re-link/repair, per-node counts). Extended: `plan_review_checkpoint` gains optional `pass_id` + `edits` (absent ⇒ v1 spec-checkpoint behavior — an implicit discriminator, CAT-1). The HIL loop (`plan_interpret_feedback` / `plan_apply_revision` / `plan_self_check` / `plan_handoff_autofix`) is retained unchanged as the **optimizer** over the spec; passes consume its output downstream. | MCP-first; catalog hygiene (CAT) argues against 7 per-pass verbs. Schemas below. |
| **PF-18** | **v1 runs stay readable; v2 is additive.** `pass_state` defaults `{}` ⇒ derived `pass_cursor: null` ⇒ the API/GUI renders a v1 run pass-less; every v1 endpoint/tool behaves identically. `plan_compile(run_pipeline=true)` + the monolithic `plan_pipeline` op remain as the legacy autonomous path (CAT-4 spirit: supersede, don't delete), with a Deferred row targeting retirement once the S06 gate passes on pass-mode. Bootstrap's drafting-guide read prefers the accepted `scene_plan` pointer and falls back to `checkpoint_state.pipeline_job_id`. | Zero-migration compat; two code paths is a carrying cost, so retirement is tracked, not silent. |
| **PF-19** | **Fixture severing:** `self_check()` and `interpret()` compute coverage/section maps against **the run's own `document` artifact** (`source_markdown` is persisted on every run), never `story-plan-v1.md`; `validate()`'s `fidelity_score` is `None` unless a per-run fidelity config exists (the fixture YAML becomes regression-harness-only, per 09 §8b). The four advisory fixture rules in `validate.py` stay advisory pending the genuinely-general validator (tracked, out of v2 scope). | DA-14 at the service layer: computing every user's gaps against the POC's story is a fixture constant with extra steps. `run_self_check` already takes paths — the change is plumbing, not engine work. |
| **PF-20** | **One new run status: `planned`** — set when all seven passes are accepted and fresh; the signal "bootstrap-ready". No other status semantics change; passes execute while `status='compiled'`. | One honest terminal beats seven per-pass statuses duplicated into the run row (the ledger owns per-pass state). |

---

## Target data model

All DDL is **additive, with ONE exception the linker cannot ship without.** The live
`outline_chapter_required` CHECK
([`migrate.py:177`](../../../services/composition-service/app/db/migrate.py#L177)) requires
`chapter_id IS NOT NULL` for **both** `chapter` and `scene` kinds — written when every outline
row was born from an existing manuscript chapter. PlanForge links planned nodes **before** any
manuscript chapter exists (bootstrap [A] stamps `chapter_id` only later — §The link step), so
under the current CHECK every skeleton and scene link insert fails with a check violation. The
swap below relaxes it: a linked node with `chapter_id IS NULL` means **"planned, not yet
written"** — surfaced in the ledger, Pass Rail, and inspector, never silent (BPS-13's posture;
the same affordance 22 SC5 gives a spec scene with no index row). **This is an amendment 23
Phase E inherits:** 23's own F1 names the constraint, but Phase E never relaxes it — 23 should
reference this swap rather than re-spec it. Execution order, batching, and any interleaving
with the Phase-0 re-key belong to the migrations pillar (**25** — integrator: assign these to
a 25 Phase; see Open questions). Shapes:

```sql
-- plan_run: the pass ledger + genre input (PF-3, PF-15, PF-20)
ALTER TABLE plan_run ADD COLUMN IF NOT EXISTS pass_state JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE plan_run ADD COLUMN IF NOT EXISTS genre_tags JSONB NOT NULL DEFAULT '[]'::jsonb;
-- plan_run_status_chk: drop + re-add with + 'planned'
-- plan_artifact_kind_chk: drop + re-add with + ('motif_plan','cast_plan','world_plan',
--   'beat_plan','char_arc_plan','scene_plan','heal_report','link_report')

-- provenance (PF-9/PF-10) — requires 23 Phase A (structure_node) + Phase 0 (outline_node.book_id)
ALTER TABLE structure_node ADD COLUMN IF NOT EXISTS plan_run_id UUID;
ALTER TABLE structure_node ADD COLUMN IF NOT EXISTS plan_arc_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_structure_node_plan_prov
  ON structure_node(book_id, plan_run_id, plan_arc_id)
  WHERE plan_run_id IS NOT NULL AND plan_arc_id IS NOT NULL AND NOT is_archived;

ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS plan_run_id UUID;
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS plan_event_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_outline_node_plan_prov
  ON outline_node(book_id, plan_run_id, plan_event_id)
  WHERE plan_run_id IS NOT NULL AND plan_event_id IS NOT NULL AND NOT is_archived;

-- The ONE non-additive change (PF-8): chapter/scene nodes may now exist BEFORE their
-- manuscript chapter. Re-added INVERTED — chapter_id becomes "written" provenance that only
-- chapter/scene kinds may carry; NULL = planned, not yet written. New name for the new
-- semantics (DA-10). Pre-flight, per migration-check-constraint-must-backfill-all-historical-
-- blocks: assert no arc/beat row carries a chapter_id (no writer sets one today; NULL any
-- stray row in the same transaction before the re-add).
ALTER TABLE outline_node DROP CONSTRAINT IF EXISTS outline_chapter_required;
ALTER TABLE outline_node ADD CONSTRAINT outline_chapter_written_kinds
  CHECK (chapter_id IS NULL OR kind IN ('chapter','scene'));
```

`pass_state` entry shape (one key per `pass_id`):

```jsonc
{
  "cast": {
    "status": "completed",              // pending | running | completed | failed
    "decision": "accepted",             // pending | accepted | rejected | auto
    "artifact_id": "0197…",             // the pass's output pointer (PF-3)
    "job_id": "0197…",
    "input_fingerprint": "sha256:…",
    "bootstrap_proposal_id": "0197…",   // pass 2/3 only (PF-7)
    "decided_by": "user",               // user | auto
    "decided_at": "2026-07-10T…"
  }
}
```

Derived (computed at serialization, never stored): per-pass `fresh|stale`, `pass_cursor`,
`blocked_at`.

### DA-13 closure — every payload has a named consumer after v2

| Payload / artifact | Consumer (linker) |
|---|---|
| `glossary_seeds` | bootstrap [B] (exists) |
| `planning_package` | the pass runner (passes 1–7) |
| `outline_skeleton` | **skeleton link** (PF-8a) — inline at compile |
| `motif_plan` | pass 4 + pass 6 prompts |
| `cast_plan` | cast bootstrap proposal · passes 5/6/7 · `roster_bindings` write (PF-13) |
| `world_plan` | world bootstrap proposal · pass 6 prompt |
| `beat_plan` | passes 5/6 (beat roles + tension targets) |
| `char_arc_plan` | pass 6 (introduction staging) |
| `scene_plan` | **scene link** (PF-8b) · bootstrap [C] drafting guides |
| `heal_report` | Plan Hub surfacing ([`24_plan_hub_v2.md`](24_plan_hub_v2.md)) + audit |
| `link_report` | E4 counts · PF-11 user-edit preservation base · Plan Hub |

---

## Orchestration — the run lifecycle, extended

v1 statuses and transitions are untouched: `pending → proposed → (checkpoint ↔ refine) →
validated → compiled | failed`. v2 appends:

```
compiled ──plan_run_pass──▶ [pass ledger executes: 1→2⛔→3→4⛔→5→6→7]──▶ planned
   ▲                              │           │
   │        re-compile after      │ blocking  │ pass N re-run ⇒ N+1.. derived stale
   └── refine (optimizer loop) ◀──┘ decision  ▼
                                     plan_review_checkpoint(pass_id, approved, edits?)
```

- **Run semantics** (`mode:"through"`): execute, in order, every pass ≤ target that is not
  (accepted ∧ fresh); stop after a blocking pass completes (its `decision:"pending"`), or at
  target, or on failure (`pass_state[p].status:"failed"` + `error_detail`; the run row itself
  does not fail — other passes' artifacts stay valid).
- **Re-compile invalidates everything:** a new `package` artifact changes every pass-1..7
  fingerprint ⇒ whole ledger derived stale. The optimizer loop (refine → re-validate →
  re-compile) therefore naturally sits *upstream* of the passes, exactly like editing source
  invalidates the build.
- **Crash resume:** per PF-4 — the job either finalizes via the hook, is absorbed by
  `sync_from_job` on the next read, or is re-enqueued idempotently. No pass ever re-runs
  because a *hook* was missed (fingerprint check happens before enqueue).
- **`sync_from_job` extension:** `apply_job_outcome` learns `op == "plan_pass"`: save the
  output artifact(s), update `pass_state[pass_id]`, auto-accept advisory passes, create the
  bootstrap proposal for pass 2/3, trigger the scene link for pass 6/7 acceptance.

---

## Checkpoints (PF-6, PF-7)

| Pass | Class | Checkpoint payload (always a persisted, diffable proposal — computed once, approved as-recorded) |
|---|---|---|
| 2 `cast` | **blocking** | A **cast bootstrap proposal**: `{new_glossary_entities}` from the proposed cast (deduped against roster + prior proposals), rendered as extracted-vs-invented (`is_new`) with roles/relationships. Approve → apply seeds glossary → roster join → `roster_bindings` → `decision:"accepted"`. Reject → `decision:"rejected"`; the user edits via `plan_review_checkpoint(edits)` or free text through the interpret loop, then re-runs the pass. |
| 4 `beats` | **blocking** | The `beat_plan` artifact presented as a diff vs `package.chapters`: per-chapter `beat_role` + tension target + the curve (peak position surfaced — the ch1-telescoping tell), template id if used. Approve/edit/reject as above. No external mutation — approval is artifact acceptance only. |
| 1, 3, 5, 6, 7 | advisory | Auto-accepted (`decision:"auto"`), fully reviewable and re-runnable afterwards. Pass 3's glossary proposal still requires human approval **to apply** (the quarantine is never bypassed) — but pass execution does not block on it. |

`auto_approve=true` on `plan_run_pass` converts blocking → advisory for the autonomous path
(authoring runs). It never auto-approves a **bootstrap apply** for world/cast when the caller
lacks the grants the bootstrap endpoints already enforce.

---

## The link step in detail (owns 23 Phase E: E1/E2/E4)

**Skeleton link** (`link_outline_skeleton(run_id)` — deterministic, inline at `compile()`):

1. Resolve-or-create the arc: upsert `structure_node` on `(book_id, plan_run_id, plan_arc_id)`
   — `kind='arc'`, `title` from the skeleton, `plan_run_id`/`plan_arc_id` provenance,
   `arc_template_id` NULL (PF-9). Re-link updates title only if unedited (PF-11).
2. For each chapter entry: upsert `outline_node` on `(book_id, plan_run_id, plan_event_id)` —
   `kind='chapter'`, `structure_node_id` = the arc from (1), `book_id`, rank by `ordinal`.
3. Emit + persist `link_report`: `{arcs: {created,updated,unchanged,preserved_user_edit},
   chapters: {…}, possible_duplicates: […], node_map: {arc_id → structure_node_id,
   event_id → outline_node_id}}`. **Zero nodes = `success:false`** (E4). The `node_map` is E2's
   provenance record on the run side.

**Scene link** (`link_scene_plan(run_id)` — at pass-6 acceptance, refreshed at pass-7):

1. Read the accepted `scene_plan` pointer. For each chapter's scenes: upsert `outline_node` on
   `(book_id, plan_run_id, plan_event_id="{event_id}:{ordinal}")` — `kind='scene'`,
   `parent_id` = the linked chapter node, `title`, `synopsis`, `tension`,
   `present_entity_ids` (roster-resolved ids; unresolvable names reported, never guessed).
2. Same report/preservation semantics. This is a **generator-side** writer for 22 F2's
   read-only-to-everyone fields, alongside the MCP/human writer 22 SC8 assigns them — the two
   coexist without silent reclaim because PF-11's version-compare always yields to the newer
   human edit. The scene rows it writes are exactly what the SceneRail,
   `adaptive_k` (`tension >= 70`), and the packer's voice-tag injection already consume.

**Manuscript join:** when bootstrap [A] later creates a real chapter for an `event_id`, apply
additionally stamps `outline_node.chapter_id` on the linked chapter node (event-id join,
composition-local write) — completing `spec ↔ implementation` at the seam 00A §6 names. Until
that stamp, the linked node's `chapter_id` is NULL — legal only after the §Target-data-model
constraint swap — and every read surface renders it as *planned, not yet written* (BPS-13:
surfaced, never silent).

**Dependencies:** skeleton link requires 23 Phase A (`structure_node` exists), the
outline `book_id` re-key (25/23 Phase 0), **and the `outline_chapter_required` swap (V2-A3)**.
Until Phase A lands, `compile()` behaves as v1
(no link) — feature-gated by table existence is **not** acceptable; v2 ships after Phase A.

---

## MCP + HTTP surface

All tools: identity from the envelope (IN-1), `book_id` explicit (IN-2), one-line rejections
(IN-6), serialized via `_tool_result_content` (OUT-3), success = bare payload (OUT-4).
`PASS_IDS = ["motifs","cast","world","beats","character_arcs","scenes","self_heal"]`
registered in `CLOSED_SET_ARGS` (IN-3).

| Tool | Kind / meta | Schema (new/changed args) |
|---|---|---|
| `plan_run_pass` *(new)* | A · book · `async_job` · EDIT | `run_id: uuid` · `pass_id: enum PASS_IDS` · `mode: enum["single","through"] = "through"` · `auto_approve: bool = false` · `structure_template_id?: uuid` (pass-4 only) · `model_ref?: uuid` · `force: bool = false`. Returns `{run_id, job_id, passes_started: […], blocked_at: pass_id\|null}`. |
| `plan_pass_status` *(new)* | R · book · `@small_return` · VIEW | `run_id: uuid`. Returns the 7-row ledger: per pass `{pass_id, status, decision, fresh: bool, artifact_id, checkpoint: {…}\|null}` + derived `pass_cursor`, `blocked_at`. |
| `plan_link` *(new)* | A · book · EDIT | `run_id: uuid`. Re-runs skeleton + scene link (whatever is linkable). Returns the `link_report` counts; `success:false` when zero nodes (E4/OUT-5 — partiality is always reported). |
| `plan_review_checkpoint` *(extended)* | A · book · EDIT | + `pass_id?: enum PASS_IDS` (absent ⇒ v1 spec checkpoint — implicit discriminator, CAT-1) · + `edits?: object` (deep-merge onto the pass artifact before decision). |
| `plan_propose_spec` *(extended)* | — | + `genre_tags?: string[]` (`maxItems: 8`, bound in the schema per IN-4). |
| `plan_compile` *(changed)* | — | Response gains the skeleton `link_report` counts. `run_pipeline` kept (legacy, PF-18); description updated to point new callers at `plan_run_pass`. |
| `plan_validate` · `plan_self_check` · `plan_interpret_feedback` · `plan_apply_revision` · `plan_handoff_autofix` | unchanged | The optimizer loop over the spec (PF-17); PF-19 changes their *internals* (own-document coverage), not their contracts. |

HTTP mirrors (GUI path; writes stay MCP-first for agents):
`POST /v1/composition/books/{book_id}/plan/runs/{run_id}/passes/{pass_id}` (run) ·
`GET …/runs/{run_id}/passes` (ledger) · `POST …/runs/{run_id}/passes/{pass_id}/review` ·
`POST …/runs/{run_id}/link`. OpenAPI: extend
[`contracts/api/composition-service/plan-forge.v1.yaml`](../../../contracts/api/composition-service/plan-forge.v1.yaml).

**GUI surface** (data contract only — wiring is the Plan Hub spec's, see Ownership): a **Pass
Rail** (7 rows: status chip · fresh/stale · re-run) fed by `GET …/passes`; **checkpoint
cards** for pass 2 (cast diff — extracted vs invented) and pass 4 (beat/tension curve vs
package order) with approve/edit/reject; the `link_report` toast with per-node counts and a
`preserved_user_edit` drill-down. Panels follow dockable-gui (DOCK-1/2: reuse the existing
`BootstrapPanel` proposal-diff rendering for pass-2 cards, no fork).

---

## Contract changes (`contracts/plan-forge/`)

| File | Change | Compat |
|---|---|---|
| `planner_state.schema.json` | Fixture keys out: `required` dropped; `properties` → `patternProperties: {"^[A-Z]{2,4}$": {"type":"number"}}`; `tier`: nullable free string (the `tier_1..4` enum was the fixture's cultivation ladder). | Not runtime-validated (verified BPS-21); POC harness fixtures updated in the same change. |
| `novel_system_spec.schema.json` | `VariableDef` + `initial?: number` (PF-14) · `CompileTargets.planner_state_init` removed (compile no longer emits — DA-13) · `VarDelta.coupled_to_realm`: `const:false` → `boolean`. `version` stays `const 1` (additive-optional fields don't fork the IR). | Additive-optional except the two dead-field removals, which match shipped code. |
| `planning_package.schema.json` | Inherits the unfixtured `planner_state` by `$ref`. `genre_tags` unchanged (already `string[]`). | A non-PA/HA/CD/THR package finally validates. |
| *(new)* `plan_pass_artifacts.schema.json` | One `definitions` entry per pass-artifact kind (`MotifPlan`, `CastPlan`, `WorldPlan`, `BeatPlan`, `CharArcPlan`, `ScenePlan`, `HealReport`, `LinkReport`) mirroring the engine dataclasses (`ProposedChar`, `CharacterArc`, `ChapterTension`, `DecomposeResult`, `PlanHealReport`). | New file; referenced by tests, not runtime-enforced (same posture as the other plan-forge contracts). |

---

## v1 → v2 migration

1. **Additive DDL** (§Target data model) — folded into 25's migration train; no backfill:
   `pass_state {}` and `genre_tags []` defaults make every existing run a valid v1 run.
2. **CHECK swaps** (status + artifact kind) are value-additive; drop + re-add in one
   transaction (`migration-check-constraint-must-backfill-all-historical-blocks` satisfied
   trivially — no historical row carries a new value). The `outline_chapter_required` →
   `outline_chapter_written_kinds` swap is the one **non**-value-additive change: its
   pre-flight asserts no arc/beat row carries a `chapter_id` before the inverted re-add
   (§Target data model), so the same lesson is satisfied non-trivially.
3. **Readable-forever:** derived `pass_cursor: null` marks a v1 run; list/detail/tools
   unchanged for it. No run is upgraded in place — passes begin only when a user runs one.
4. **Legacy path:** `run_pipeline=true` + `plan_pipeline` op + `checkpoint_state.pipeline_job_id`
   keep working (PF-18). Deferred row `D-PF-V2-RETIRE-MONOLITH` targets removal after the S06
   gate passes on pass-mode.

---

## Eval plan

Reports persist to `docs/eval/plan-forge/` dated (per `store-reports-in-files`).

**Regression floor (carried POC numbers — a v2 run may not regress below):**

| Metric | Floor | Source |
|---|---|---|
| Rules path S1–S8 on fixture | PASS (7/7 sections, 4 vars, 7 arc_2 events) | POC 02 |
| Propose stability (gemma-4-26b) | ≥6/7 events ×3 reruns; title overlap ≥86% | POC 03 |
| Fidelity gate | ≥0.90 post-HIL (POC hit 1.0; baseline 0.86 is *below* gate by design) | POC 06/08 |
| Manual-edit rate | invariants ≥90% · prose ≥70% | 09 §1 |
| Chat HIL intents I1–I4 | 100%; final fidelity ≥0.94 | POC 08 |
| Handoff prompt budget | ≤55k tokens | POC 08 |
| Story Grid `sg_value_shift_per_scene` | stays **advisory** — never promoted to hard without re-audit | [`docs/eval/plan-forge-story-grid-poc-2026-07-06.md`](../../eval/plan-forge-story-grid-poc-2026-07-06.md) |

**New v2 grounding metrics (the disease v2 exists to cure — baselines are the one-shot's):**

| Metric | One-shot baseline | v2 target |
|---|---|---|
| Scenes with non-empty `present_entity_ids` | ~0% (the review hole) | ≥80% |
| New characters introduced **named** (vs "a group"/"someone") | ~0% | ≥90% at their scheduled chapter |
| `motif_coverage` non-empty | `{}` | every selected motif placed ≥1 event |
| Tension peak position | ch1 (telescoping) | peak in the curve's declared band, not ch1 |
| Linked nodes per compile | 0 (BPS-14) | arcs ≥1, chapters = event count, scenes ≥ min_scenes×chapters; **0 ⇒ red** |

**Acceptance gate:** S06 flagship replay on `gemma-4-26b-a4b-qat` via
[`scripts/eval/run_discoverability_scenario.py`](../../../scripts/eval/run_discoverability_scenario.py) +
[`scripts/eval/discoverability_scenarios/S06-flagship.json`](../../../scripts/eval/discoverability_scenarios/S06-flagship.json),
compared against the committed baseline (`docs/eval/discoverability/runs/2026-07-09-S06-baseline`).
Gate adds: the plan movement ends with linked structure (`structure_node` + chapter/scene
`outline_node` counts > 0), the pass-2 checkpoint surfaces in Mai's language (no jargon from
the S06 denylist), zero empty-intent `find_tools({})`, and the judge's canon-fact checklist
holds. Per `prefer-e2e-and-evaluation-over-live-smoke-poc`, this replay — not a hand-fed
smoke — is the ship signal; per `live-smoke-rebuild-stale-images-first`, rebuild images
before the run.

---

## Task breakdown

Dependency spine: **25/23-Phase-0 + 23-Phase-A → V2-A → {V2-B ∥ V2-C} → V2-D → V2-E → V2-F →
V2-G ∥ V2-H**. Per `fanout-independent-slices-parallel-build-serial-integrate`, V2-B/V2-C and
V2-F/V2-G fan out on disjoint files with one serial VERIFY.

### V2-A — schema (with 25)
| # | Task | Files |
|---|---|---|
| A1 | `pass_state` + `genre_tags` columns; status + artifact-kind CHECK swaps; models (`PlanArtifactKind`, `PlanRunStatus`, `PlanRun.pass_state/genre_tags`) | `app/db/migrate.py`, `app/db/models.py` — DDL execution order folded into **25** |
| A2 | Provenance columns + partial unique indexes on `structure_node`/`outline_node` | same, after 23 Phase A |
| A3 | `outline_chapter_required` drop + inverted re-add as `outline_chapter_written_kinds`, with the arc/beat `chapter_id` pre-flight (PF-8, §Target data model) | `app/db/migrate.py` — folded into **25**; blocks V2-E |

### V2-B — contracts
| # | Task | Files |
|---|---|---|
| B1 | `planner_state` unfixture + `VariableDef.initial` + dead-field removals (PF-14) | `contracts/plan-forge/*.json`, `app/engine/plan_forge/compile.py`, POC fixtures |
| B2 | `plan_pass_artifacts.schema.json` + mirror tests | `contracts/plan-forge/`, `tests/unit/` |
| B3 | `genre_tags` plumbing: run create → row → compile → pass inputs (PF-15) | `routers/plan_forge.py`, `plan_forge_service.py`, `mcp/server.py` |

### V2-C — pass runner + engine
| # | Task | Files |
|---|---|---|
| C1 | Pass registry (contracts table as code: inputs, output kind, checkpoint class, engine adapter) + fingerprinting + derived freshness/cursor | `app/services/plan_pass_service.py` *(new)* |
| C2 | `plan_pass` worker op + dispatch + finalize hook + `sync_from_job` extension (PF-4) | `app/worker/operations.py`, `app/worker/job_consumer.py`, `plan_forge_service.py` |
| C3 | `engine/world_plan.py` *(new — mirror `cast_plan.py`: messages → tolerant parse → degrade-safe)* | `app/engine/world_plan.py` |
| C4 | Hoist pass 4: L1 + `shape_tension_curve` as a discrete step; `grounded_decompose` accepts a supplied curve; optional `structure_template_id` (PF-16) | `app/engine/arc_plan.py`, `grounded_plan.py` |
| C5 | Artifact-I/O adapters for passes 1/2/5/6/7 (no engine rewrites); pass-6 prompt gains the variable ledger (PF-14 reader) | `app/services/plan_pass_service.py`, `app/engine/grounded_plan.py` |

### V2-D — checkpoints
| # | Task | Files |
|---|---|---|
| D1 | `BootstrapService.propose_seed` (glossary-only diff; kinds per pass) + pass-2 accept-on-applied wiring (PF-7) | `app/services/bootstrap_service.py` |
| D2 | `plan_review_checkpoint` extension (`pass_id`, `edits` deep-merge) | `plan_forge_service.py`, `mcp/server.py`, `routers/plan_forge.py` |
| D3 | `roster_bindings` write after cast apply + BA12-style effect test (PF-13) | `plan_pass_service.py`, `tests/unit/` |

### V2-E — the link step
| # | Task | Files |
|---|---|---|
| E1 | `link_outline_skeleton` inline at `compile()`; upserts with `ON CONFLICT` repeating the partial-index predicate; `link_report` artifact; zero-node = error (PF-8a, E4) | `app/services/plan_link_service.py` *(new)*, `plan_forge_service.py` |
| E2 | `link_scene_plan` at pass-6/7 acceptance; roster-resolved `present_entity_ids`; PF-11 preservation | `plan_link_service.py` |
| E2b | **Both linkers stamp `source='planforge'`** on every node they mint ([`26`](26_structure_prose_indexing.md) IX-11 reserves the value; the stamp must come from the writer — a reserved-but-never-written enum value is the write-only bug class). `link_report.possible_duplicates` (PF-10) widens to **cross-axis** duplicates: a planforge-minted node title-matching a `source='decompiled'` node (an imported-then-replanned book) is surfaced, never auto-merged. The two preservation predicates compose: IX-11(a) protects `source='authored'` rows from the decompiler; PF-11's version-compare protects edited rows from the re-linker — both yield to the newer human edit. | `plan_link_service.py` |
| E3 | Bootstrap [A] stamps `outline_node.chapter_id` on the linked node; drafting-guide read prefers the `scene_plan` pointer (PF-18) | `bootstrap_service.py` |

### V2-F — surface
| # | Task | Files |
|---|---|---|
| F1 | `plan_run_pass`, `plan_pass_status`, `plan_link` MCP tools + `CLOSED_SET_ARGS` registration + `plan_compile` response counts | `app/mcp/server.py`, tool tests |
| F2 | HTTP pass endpoints + OpenAPI | `routers/plan_forge.py`, `contracts/api/composition-service/plan-forge.v1.yaml` |
| F3 | Pass Rail / checkpoint-card data wiring — hands off to the Plan Hub wiring spec, [`24_plan_hub_v2.md`](24_plan_hub_v2.md) | `frontend/src/features/plan-forge/` |

### V2-G — fixture severing (PF-19)
| # | Task | Files |
|---|---|---|
| G1 | `self_check`/`interpret` coverage from the run's own `document` artifact; fidelity `None` without per-run config | `plan_forge_service.py`, `engine/plan_forge/self_check.py`, `coverage.py` |

### V2-H — verification
| # | Task |
|---|---|
| H1 | Unit: fingerprint/staleness derivation · blocking-stops-runner · re-run invalidates downstream · resume after simulated crash · link idempotency (re-link updates, never duplicates) · planned-node insert with `chapter_id NULL` passes the swapped CHECK (A3) · PF-11 preservation · zero-node link errors |
| H2 | **Effect tests** (per `checklist-is-self-report-enforce-by-tests`): pass-6 prompt changes when `cast_plan` changes; packer prompt changes when `roster_bindings` change; linked scene's `tension`/`present_entity_ids` reach the SceneRail read path |
| H3 | **Cross-service live-smoke** (≥2 services, per the VERIFY gate): compile → skeleton link → pass 2 → cast proposal → approve → glossary applied (real glossary-service) → roster join resolves ids → passes 4–7 → scene link → bootstrap creates chapters + stamps `chapter_id` (real book-service). Drive through the consumer path (`new-cross-service-contract-needs-consumer-live-smoke`) |
| H4 | S06 replay gate + regression-floor run (§Eval plan) |

---

## Ownership boundaries (no cross-spec duplication)

- **Migration DDL execution/backfill/re-key order → 25.** This file specifies target shapes only.
- **Plan Hub GUI wiring → [`24_plan_hub_v2.md`](24_plan_hub_v2.md).** This file supplies the data contract (ledger, cards, report).
- **Dirty-tracking / spec↔prose staleness / conformance surfacing → 26.** PF-3/PF-5's pass
  freshness is *build-graph* staleness internal to a run — different concept, owned here.
- **`structure_node` MCP CRUD → 23 BA11** (referenced, never re-specced). New agent-experience
  tools beyond PlanForge's own domain tools → 28.

---

## Open questions

Every row is decided; the two former PO-DECIDE rows (checkpoints, genre source) were ratified by the PO 2026-07-10 (P-8/P-9).

| # | Question | Disposition |
|---|---|---|
| OQ-1 | **Checkpoint classes** — blocking at 2 + 4, advisory elsewhere? | ✅ **RATIFIED (PO 2026-07-10)** — decision = BPS-19b as stated (blocking 2 + 4; `auto_approve` arg for autonomous runs). BPS-19 itself flags "(b) is decided on a stated principle; the PO may override." |
| OQ-2 | **`genre_tags` source** (BPS-20's open sub-question) | ✅ **RATIFIED (PO 2026-07-10)** — decision = PF-15: explicit optional field on run create, persisted on `plan_run`, omitted ⇒ `[]`. Alternatives considered and disliked: `spec.meta` (frozen `additionalProperties:false` contract + unreliable to mine), a per-book setting (a hidden default the run never surfaces — the settings-boundary bug class; can layer on later as a fallback without breaking the explicit arg). |
| OQ-3 | Cross-run duplicate arcs when a book re-plans via a fresh run | **Decided (PF-10): surfaced in `link_report.possible_duplicates`, never auto-merged.** Same never-guess posture as 23's migration guards. Revisit trigger: the first real user hit, with the report data in hand. |
| OQ-4 | Should the linker bind selected motifs as `motif_application` rows (the lockfile)? | **Decided: not in v2** — defer gate #3 (naturally-next: binding needs the scene nodes this spec creates *plus* role-binding UX owned by the motif tools). `motif_plan`'s consumers in v2 are the pass-4/6 prompts (a real reader — DA-4 satisfied). Tracked as a Deferred row at SESSION time. |
| OQ-5 | Genuinely-general validator (replace the 4 advisory fixture rules with story-agnostic hard rules) | **Decided: out of v2 scope, tracked.** PF-19 severs the fixture *paths*; the validator redesign is its own effort (D-PLANFORGE-GENERAL-VALIDATE's comment already names it follow-up work). v2 does not widen the hard-tier gate. |
| OQ-6 | Does `plan_run.status` need per-pass statuses? | **Decided (PF-20): no** — one new `planned` terminal; the ledger owns pass state. |
| OQ-7 | Spec numbering collision with the translation-repair file. | ✅ **Resolved 2026-07-10:** translation-repair was renumbered to `29_translation_repair.md` with a mechanical link sweep (00A §10) — no collision exists. This file's filename-anchored references survived the rename unchanged, as intended. |
| OQ-8 | For the integrator: fold §Target-data-model DDL into 25's phase ordering (V2-A depends on 23 Phase A + Phase 0). | Flagged for 25's task list. |
| OQ-9 | 09 blueprint §2's phase table marks Link as *"Blocking: missing links"* and Decompose as *"Blocking: per-layer"* — superseded? | **Decided: yes.** BPS-19b (newer, register-locked) narrows blocking to passes 2 + 4; the link is deterministic and composition-local (PF-8) so it gates on nothing. Recorded here rather than editing the frozen blueprint. |

---

## Risks

| Risk | Mitigation (tied to the repo lesson where one exists) |
|---|---|
| Pass artifacts become write-only blobs (stored, never conditioning anything) | H2 effect tests: pass-6 prompt must change when `cast_plan` changes; packer must change when `roster_bindings` change (`checklist-is-self-report-enforce-by-tests`, BA12/D2 discipline) |
| Link returns 200 having linked nothing | PF-8/E4: zero nodes ⇒ `success:false` + counts always (`silent-success-is-a-bug-not-environment`) |
| Upsert misses the partial unique index → duplicate nodes on re-link | `ON CONFLICT` repeats the index's WHERE clause verbatim; H1 asserts re-link idempotency (`postgres-partial-index-on-conflict-predicate-must-match`) |
| CHECK swap breaks on historical rows | Status/kind values are additive; the `outline_chapter_required` swap pre-flights that no arc/beat row carries a `chapter_id`; drop + re-add in one transaction (`migration-check-constraint-must-backfill-all-historical-blocks`) |
| A crashed/parallel pass job double-runs or clobbers a newer result | Enqueue keyed on **fresh-completed-exists** (`idempotency-gate-exists-not-active-version`); finalize hook + `sync_from_job` absorb, never re-execute; per-pass jobs inherit `cancel_check` (`worker-loop-under-one-amqp-message-cancel-clobber`) |
| Roster join silently thins the cast (server-side default filters on the glossary read path) | Pass-2 acceptance asserts every applied cast name resolved an id; live-smoke H3 uses the real KAL path (`mocked-client-hides-server-side-default-filters`) |
| Mock-green, live-red across the compile→link→bootstrap→glossary chain | H3 drives the consumer's real path on a rebuilt stack (`new-cross-service-contract-needs-consumer-live-smoke`, `live-smoke-rebuild-stale-images-first`) |
| A local reasoning model burns its budget before emitting pass JSON | Pass modules already send `_NO_THINK`; tolerant parsers salvage truncated arrays (`reasoning-model-burns-max-tokens-before-real-answer`) |
| A sibling track promotes/renames plan-forge pieces mid-build | Verify engine/schema compat at BUILD start (`planforge-promoted-by-another-agent-check-compat`) |
| Re-link silently reclaims an author's manual edits to linked nodes | PF-11 version-compare + `preserved_user_edit` reporting (BPS-12's provenance principle) |
| Eval replay wedges the local model queue | `lm-studio-queue-wedge-lms-reload`: `lms` reload between S06 movements if a turn times out |
