# 00B · Execution Roadmap — one build sequence for the package model (22–28)

> **Status:** 📐 INTEGRATED v2 · **§6 RATIFIED IN FULL (PO 2026-07-10)** — buildable from Stage 1 (rewritten 2026-07-10 after the adjudication pass; supersedes the
> 2026-07-10 draft that predated `28` and the CF-1..15 adjudications)
> **Scope:** the single dependency-ordered build sequence across every phase of
> [`22`](22_scene_model_and_crud.md) · [`23`](23_book_architecture.md) · [`24_plan_hub_v2.md`](24_plan_hub_v2.md) ·
> [`25`](25_package_migration_master.md) · [`26`](26_structure_prose_indexing.md) ·
> [`27`](27_planforge_v2_compiler.md) · [`28`](28_agent_native_studio.md), plus the wave plan,
> the **adjudication ledger** (§5 — every CF-1..15 verified against the stamps on disk), the
> consolidated PO-DECIDE list, and the per-pillar definition of done.
> **Law upstream:** [`00A_BOOK_PACKAGE_STRUCTURE.md`](00A_BOOK_PACKAGE_STRUCTURE.md) (DA-1..14, BPS-1..21).
> **This file sequences; it decides nothing.** The 15 conflicts of the first integration pass are
> adjudicated and stamped into the pillar specs; §5 records where each stamp landed. The four
> residual items (NC-1..4) were **all closed 2026-07-10** — §5's second table records each
> resolution. No open conflicts remain.
> **Milestone naming:** `<spec>-<phase>` (e.g. `25-M3`, `23-A6`, `28-AN-B`). A bare phase letter is
> never used — 22, 23, 26, and 28 all have lettered phases, so an unqualified "Phase A" is
> ambiguous by construction (CF-15's rule, now adopted by cross-spec citations).

---

## 1. Why

Eight specs now describe one architecture: the book as a package (`00A`), the scene seam (`22`),
the durable spec layer (`23`), the Hub as package explorer (`24`), the one ordered re-key (`25`),
the honest source map (`26`), the multi-pass compiler with its link step (`27`), and the
agent-native capability layer over all of it (`28`). Each was written with explicit ownership
boundaries, and each names prerequisites in the others. What none of them contains — by design —
is the *global* order: which milestone unblocks which, where the commit + PO checkpoints land
under the budget-driven cadence, what can fan out in parallel, and which open questions are
genuinely the PO's. That is this file.

---

## 2. Ground truth at sequencing time (verified 2026-07-10, against code and the files on disk)

| Fact | Evidence |
|---|---|
| **23-E5 (BPS-20 fixture-constant bug) is FIXED and shipped.** | [`compile.py`](../../../services/composition-service/app/engine/plan_forge/compile.py) takes `genre_tags` as a caller kwarg defaulting to `[]`; zero `xianxia` literals remain; guard test [`test_plan_forge_no_fixture_constants.py`](../../../services/composition-service/tests/unit/test_plan_forge_no_fixture_constants.py) exists. |
| **23-E3 (dead payloads `planner_state_init` / `working_memory_charter` deleted) is DONE**, folded into E5 per 23's own Phase-E table. | Same commit family; `compile.py` no longer emits them. |
| **The S06 acceptance anchor exists.** | [`scripts/eval/discoverability_scenarios/S06-flagship.json`](../../../scripts/eval/discoverability_scenarios/S06-flagship.json) + committed baseline [`docs/eval/discoverability/runs/2026-07-09-S06-baseline`](../../eval/discoverability/runs/2026-07-09-S06-baseline) — 27-H4, 28-AN-D3, and 23-D7 have a real comparison target. |
| **`28_agent_native_studio.md` now EXISTS** (CF-13 closed): authored + adversarially verified 2026-07-10 (2 HIGH / 3 MED / 4 LOW findings, all 9 fixed). Zero new tables; 7 tools + 1 arg extension; the ownership boundary "new agent-experience tools → 28" is now enforceable. | File on disk; AN-1's closed capability matrix. |
| **The adjudication stamps are on disk** — 23 carries two ⚠ supersession blocks (migration → 25, Phase E → 27) and the "MCP-first *for agents*" reword; 22 carries the SC5 publish-only and D5 read-time-null amendments; 00A carries the PM-3/PM-4/PM-10 ✏️ refinements, the DA-8 role reword, the BPS-15/BPS-18 corrections, and the `import_source` move; 25 carries OQ-8 (MOOT) + OQ-11 (M-train rule); 27 carries V2-E2b. | §5 ledger, per-row anchors. The four residual items (NC-1..4) were closed the same day. |
| **`29_translation_repair.md` exists; no `24_` collision remains** (CF-14 closed). | Rename on disk (`24_translation_repair.md → 29_translation_repair.md`), links swept; 00A §10 row ✅. |
| **The bootstrap contract after 23-E5 is proven BY EXECUTION** (was held by inspection only). | 2026-07-10: `test_bootstrap_service.py` — **16/16 passed** against a throwaway Postgres (`TEST_COMPOSITION_DB_URL`, created + dropped for the run). `glossary_seeds`/`planning_package` consumption of the slimmed compile output verified live. |
| **25's M0 pre-flights were previewed READ-ONLY on the live dev DB** — Deploy 1 starts with facts. | 2026-07-10: M0.2=0, M0.4=0, 81 arc rows (M4 workload), 201 Works/195 books. Two hits, both scoped + pre-decided in 25's M0 section: ONE duplicate-canonical-Work book (test account, empty duplicate → archive) and 4 junk `kind='beat'` rows (test account → archive). Operator pass = two known actions. |
| **Everything else in 22–28 is unbuilt.** `structure_node`, `scenes.source_scene_id`, `pass_state`, `arc_conformance_state`, `book_steering` MCP tools, the re-key — all absent from code (each spec's own Investigation sections verified this; spot-checked). | Grep evidence cited inside each spec. |

---

## 3. The build sequence

One trunk, nine stages. **RB** = risk boundary: commit + (where marked) PO checkpoint, per the
budget-driven cadence — checkpoints land at genuine contract/migration/seam boundaries, not at
sub-task counts. Within a stage, waves (§4) fan out on disjoint files with one serial VERIFY.

### Stage 0 — already DONE (2026-07-10)

| Milestone | Content | Status |
|---|---|---|
| 23-E5 | BPS-20 fix: `genre_tags` → caller kwarg `[]`, constraints from charter, `arc_id` required, `planner_state` derived | ✅ shipped, guard test green |
| 23-E3 | dead compile payloads deleted (DA-13) | ✅ shipped (folded into E5) |
| — | Adjudication stamps for CF-1..15 landed in 22/23/00A/25/26/27/28; `28` authored + reviewed (9 findings fixed); NC-1..4 all closed | ✅ on disk (§5); zero open conflicts |

### Stage 1 — the re-key trunk (`25` Deploy 1) — **everything else sits on this**

| Order | Milestone | Content | Prerequisite |
|---|---|---|---|
| 1.1 | **25-M0** | pre-flight assertions + `package_migration` marker + quarantine protocol. **Includes the 25-task-1b residue**: the 22 A1/B0 sequencing pointers → 25 (the 23/00A stamps already landed — §5 CF-1/CF-2/CF-6) **plus the NC-2 one-liners** (22 B4 `/v1` mirror note, 22 A4 `source_scene_id` arg note, 22's "one writer" sentence → DA-8 role wording) and the NC-3 stale-narration sweeps | — |
| 1.2 | **25-M1** | additive DDL: 13× `book_id` + indexes; **carries 23-A1** (`structure_node` + trigger + `outline_node.structure_node_id` + `motif_application.structure_node_id`) and **22-B1** (8 SC4 columns + `exit_state` model) | 1.1 |
| 1.3 | **25-M2** | backfills (keyset-batched for `outline_node`/`generation_job`) + NOT NULL flips + assertions | 1.2 |
| 1.4 | **25-M3** | cutover DDL (partial manifest unique PM-4, `decompose_commit` re-scope PM-10, actor renames PM-5, style/voice PK swap M3.4) **atomically with** the code sweep (25 tasks 5–7: repos, `_book_or_deny`, PlanForge `_ensure_work`, sweeper, `pack.py`, PM-14 docstring). Carries **25-OQ-3's `.runs/` VIEW widening per P-3 ✅** (predicate-only — also unblocks 28-AN-2's `runs` block) | 1.3 |
| 1.5 | **25-T1..T5** | snapshot migration test, M0 refusal tests, grantee-widening, derivative-separation, spend attribution | 1.4 |
| 1.∥ | **22-A1** *(parallel lane, book-service)* | `scenes.book_id`/`title`/`source_scene_id` + batched backfill (`migrate.go`, CB3 shape) — owned by 22, sequenced here per 25's own note | — |

**RB-1 — commit + PO checkpoint.** Tenancy cutover across the whole composition surface; evidence
must include 25-T6 (`live smoke: grantee B drives outline read/write + $0 local generation through
the gateway`) or its explicit deferral row. This is the single highest-risk boundary in the plan.

### Stage 2 — the structure layer (`23` on Deploy-1 schema)

| Order | Milestone | Content | Prerequisite |
|---|---|---|---|
| 2.1 | **23-A3** | `StructureRepo` (tree CRUD, move w/ depth recompute, cascade resolvers) | RB-1 |
| 2.2 | **23-A4 · 23-A5** | conformance retarget to `arc_id` (BA4); `arc_apply`/`arc_extract_template` | 2.1 |
| 2.3 | **23-A6** | **`pack.py` injects resolved arc context (BA12)** — the single most load-bearing task in 23; also the prerequisite 28-AN-C's context table cites | 2.1 |
| 2.4 | **23-B1..B4** | the full arc/template/outline-move MCP surface + `Literal` closed sets — **plus the REST write mirrors for arc CRUD** (CF-9 resolution, now stamped at [`23:356`](23_book_architecture.md); the Hub's drag-drop transport) | 2.1 |
| 2.5 | **23-D2..D4** | BA12 effect test · nesting tests · cascade/derivation tests | 2.2–2.4 |
| 2.∥a | **22-A2..A5** *(parallel wave, book-service + worker-infra)* | 3 read-only `/v1` scene routes, keyset paging, `book_scene_list/get` MCP tools — **`book_scene_list` MUST carry the `source_scene_id` filter (28 AN-5b/OQ-3; 28-AN-C1's recipe test reds without it)** — parse writers set `book_id` + anchor-matched `source_scene_id` | 22-A1 |
| 2.∥b | **26-A** *(parallel wave, SDK + knowledge)* | `source_format='tiptap'` walker + `Scene.anchor_scene_id`; `/internal/parse` passthrough | — |

**RB-2 — commit.** New MCP + REST contract (arc tools). No PO checkpoint needed unless 23-D2 red.

### Stage 3 — the lift (`25` Deploy 2) — **point of no return**

**PO checkpoint FIRST** (P-4: recommended default = only after Deploy 1 has survived a real
authoring session and T1–T6 are green), then:

| Order | Milestone | Content | Prerequisite |
|---|---|---|---|
| 3.1 | **25-M4** | arc lift → `structure_node` (lift map, provenance backfill, `motif_application.structure_node_id`, PM-10 re-point) | RB-2 + PO go |
| 3.2 | **25-M5** | arc-row delete, `kind` CHECK swap, BPS-5 renames (`threads`→`tracks`, `arc_roster`→`roster`), lift-map drop | 3.1, T7 rehearsal green |
| 3.3 | **24-H1.1 route flip** *(same deploy — pinned by 25-OQ-11)* | children route: `book_id` keying + `structure_node_id` axis + `detail=summary`; **"omitted `parent_id`" semantics re-defined**; Manuscript Navigator re-pointed; `idx_outline_node_structure_keyset` (24-H1.2, additive — rides this deploy's image inline per the OQ-11 M-train rule) | 3.1 (chapters become `parent_id NULL` here — the route inverts at this exact moment) |
| 3.4 | **23-A7 reader code** | `layout[].thread`→track-key readers ship with the M5.2 rename DDL | 3.2 |
| 3.5 | **25-T7 · 23-D5 · 23-D6 · 23-D7** | M5 gate rehearsal on snapshot · migration test · cross-service live-smoke (Work-less book → arc list → author → apply → conformance) · S06 idea→arc replay | 3.2–3.4 |

**RB-3 — commit.** M5 deletes data; nothing after this rolls back.

### Stage 4 — the scene seam completed (`22`)

| Order | Milestone | Content | Prerequisite |
|---|---|---|---|
| 4.1 | **22-B2 · 22-B3** | `_UPDATABLE_COLUMNS` widening; `_NodeCreateArgs`/`_NodeUpdateArgs` full-field + enums/ranges | RB-1 (columns exist since 25-M1) |
| 4.2 | **22-B4** | `materialize-scenes` decompiler (idempotent, per-scene counts) — **plus its EDIT-gated `/v1` mirror** (CF-10 resolution, decided at 24-OQ-9; PH21's CTA has no transport without it) | 4.1 |
| 4.3 | **22-C1..C5** | `scene-browser` + `scene-inspector` panels, SceneRail union + inline title edit, i18n | 22-A2, 4.1 |
| 4.4 | **22-D1..D5** | OpenAPI · contract regen · **D3 cross-service live smoke** · **D4 tenancy assertion** (the pillar-25 DoD test) · D5 anchor-direction | 4.2–4.3 |
| 4.∥a | **24-H2.2** *(parallel wave, FE-only)* | the deterministic lane-layout pure function, unit-tested headless — zero backend dependency | — |
| 4.∥b | **28-AN-B** *(parallel wave, book-service Go — earliest legal slot)* | `book_steering_list/set/delete` + `book_search` MCP tools + meta boot tests. No composition prerequisites; immediate S06 value (steering + grep). Serializes on `mcp_server.go` **after 22-A4 merges** (§4 registry) | 22-A4 merged |

**RB-4 — commit.** D3's evidence line is mandatory (≥2 services touched).

### Stage 5 — index honesty + staleness (`26`)

| Order | Milestone | Content | Prerequisite |
|---|---|---|---|
| 5.1 | **26-B1..B5** | `last_parsed_revision_id`; worker importers gain auto-publish (IX-1 corollary); `reparse.go` hash-preserving upsert + IX-5 evidence rules; both publish sites wired + `chapter.scenes_reparsed` in-Tx; sweeper; canon-markers batch route | 26-A, 22-A5 merged (same Go files — §4 collision registry) |
| 5.2 | **26-C1..C3** | `arc_conformance_state` + persist helper + status route + `composition_conformance_status` MCP tool — **C3's helper is the ONE staleness computation** (IX-14's law): its **route** is consumed directly by 24-H4.1 (read surface #7, NC-1 ✅); its **helper** is composed by 28-AN-2/AN-4. 24-H1.3's overlay never carries drift. | 5.1 (B5), 23-A4 |
| 5.3 | **26-D1..D3** | `source`/`decompile_key` columns + never-overwrite-authored predicate; `mappings[]` + import-tail write-back; `arc_import_analyze` stamps provenance | 22-B4 |
| 5.4 | **26-E1** | knowledge K14 handler for `chapter.scenes_reparsed` | 5.1 (B3) |
| 5.5 | **26-F1..F3** | state chips · **F2 cross-service live smoke** (the pillar-26 DoD) · effect tests | 5.1–5.4 |

**RB-5 — commit.** New frozen event contract (`chapter.scenes_reparsed`) + a consumer in a second
service — live-smoke through the consumer path, images rebuilt first.

### Stage 6 — the multi-pass compiler (`27`)

| Order | Milestone | Content | Prerequisite |
|---|---|---|---|
| 6.0 | **25 M-step registration** *(pre-build gate — NC-4)* | 27-V2-A3's `outline_chapter_required` → `outline_chapter_written_kinds` swap is **non-additive** and must register as a numbered M-step in 25 before building (25-OQ-11's rule; 25 currently ends at M5 — this mints M6) | RB-3 |
| 6.1 | **27-V2-A** | `pass_state`/`genre_tags`, CHECK swaps, provenance columns + partial uniques, **the A3 swap** (blocks V2-E). Additive parts ride 27's own build inline per OQ-11; A3 executes as the registered M-step | 6.0 |
| 6.2 | **27-V2-B ∥ V2-C** | contracts unfixturing (PF-14/BPS-21) + `genre_tags` plumbing ∥ pass runner + `world_plan.py` + pass-4 hoist + adapters | 6.1 |
| 6.3 | **27-V2-D** | `propose_seed` quarantine wiring + checkpoint extension + `roster_bindings` write (PF-13) | 6.2 |
| 6.4 | **27-V2-E (incl. E2b)** | the link step: skeleton link inline at compile + scene link at pass-6/7 acceptance + bootstrap `chapter_id` stamp; **E2b: linkers stamp `source='planforge'`, `link_report` widens to cross-axis duplicates, the IX-11(a)/PF-11 preservation predicates compose** (CF-12's stamp) | 6.1 (A3), 6.3 |
| 6.5 | **27-V2-F ∥ V2-G** | 3 new MCP tools + HTTP mirrors + OpenAPI ∥ fixture severing (PF-19) | 6.4 |
| 6.6 | **27-V2-H** | unit + effect tests + **H3 cross-service live smoke** + **H4 S06 replay gate** (the pillar-27 DoD) | 6.5 |

**RB-6 — commit + PO checkpoint.** The S06 replay is the ship signal; present the grounding-metric
deltas (present-cast %, named-introduction %, linked-node counts) against the one-shot baseline.

### Stage 7 — the package explorer (`24`)

| Order | Milestone | Content | Prerequisite |
|---|---|---|---|
| 7.1 | **24-H1.3..H1.6** | `plan-overlay` (canon + threads + tension + motif chips + unplanned tray — **drift never rides the overlay; the Hub reads 26 IX-14's route directly as read surface #7, ≤5 cold-open budget — NC-1 ✅**), book-keyed scene-links, `composition_arc_list` derived-block contract test, glossary entity-names widening. H1.3's coverage-diff computation lands as the **shared helper** 28-AN-4/OQ-4 names — ONE implementation | RB-3 (H1.1 already shipped there), 26-C for drift (else the key is absent per 24-OQ-8 — absent ≠ zero) |
| 7.2 | **24-H2** | panel shell, window loader, React Flow components, two-truths join, bus wiring (H2.2 already done in the Stage-4 wave) | 7.1 |
| 7.3 | **24-H3 ∥ H4 ∥ H5** | drawer ∥ decorations ∥ interactions (per-row OCC/undo tests) — disjoint files | 7.2 |
| 7.4 | **24-H6** | Plan navigator rail | 7.2 |
| 7.5 | **24-H7** | view modes — **deferred per P-10 ✅ (v1 narrative-only)**; timeline then worldmap, each its own cycle | 7.3 |
| 7.6 | **24-H8** | 10k-fixture perf pass (cold-open budget **≤5 requests** per NC-1 ✅, EXPLAIN keyset assertion) + **H8.2 live browser smoke** (the pillar-24 DoD) + amendment check | 7.3–7.4 |

**RB-7 — commit + PO checkpoint.** The Hub is the user-visible face of the whole package model —
present it live.

### Stage 8 — the agent-native studio (`28`) — now REALLY sequenced

| Order | Milestone | Content | Prerequisite |
|---|---|---|---|
| 8.0 | **28-AN-B** *(if not already done in the Stage-4 wave)* | steering + search Go tools — independent of everything composition-side | 22-A4 merged |
| 8.1 | **28-AN-A** | `composition_package_tree` (+ 4K-token budget test) · `ReferencesRepo.find_by_entity` + `composition_find_references` · `composition_diagnostics`. Composes 26-C3's status helper (extended with `draft_indexed`) + 24-H1.3's shared coverage-diff helper — **never a second staleness/coverage computation**. All three scope to the **canonical Work** (PM-3/PM-4, P-2's canonical-only resolution); the `runs` block serves non-owners only under P-3's VIEW widening, else absent + warning | 25 Deploy 1 (canonical-Work partition + OQ-3 sweep) · 23-A (structure_node) · 26-C (IX-14 machinery) · 24-H1.3 (the shared coverage helper) |
| 8.2 | **28-AN-C** | AN-C1: the spec→prose recipe contract test over 22-A4's `source_scene_id` filter · AN-C2: the static orientation-tools sentence in the studio `book_context_note` (chat-service) · AN-C3: discovery-registration checks (`tool_list` completeness + `find_tools` synonym recall). Context stays pull-only; generation-side spec injection is 23-A6's packer work (already shipped in Stage 2) | 22-A4 · 8.1 · 23-A6 |
| 8.3 | **28-AN-D** | D1 cross-service live smoke (tree with live manuscript block → degraded absent+warning path → steering effect in a real turn → `book_search` vs `story_search` → seeded canon error in diagnostics) · D2 effect tests (steering-set → next-turn `<steering>` injection; diagnostics item disappears after the underlying fix) · **D3 the S06 flagship replay gate** — pairs with 27-H4's: same fixture, same baseline, now also asserting the steering row after turn 9, the verification-read before any "it's set up" claim, ≤2 discovery calls per movement, denylist grep = 0 · D4 xdist marks | 8.1–8.2 |

**RB-8 — commit + PO checkpoint.** The AN-D3 replay is the pillar-28 ship signal — present the
per-movement checkpoint table next to 27-H4's grounding deltas: the compiler now produces the
architecture *and* the agent can see, search, steer, and verify it.

---

## 4. Wave plan — what fans out (`fanout-independent-slices-parallel-build-serial-integrate`)

Parallel BUILD on provably-disjoint files, ONE serial VERIFY per stage. The gating resource is not
the dependency graph — it is five shared files.

### Parallelizable waves

| Wave | Slices (disjoint) | When |
|---|---|---|
| W1 | 25 Deploy-1 (composition, Python) ∥ 22-A1 (book-service, Go) | Stage 1 |
| W2 | 23-A3..A6 (composition engine/repos) ∥ 22-A2..A5 (book-service + worker-infra, Go) ∥ 26-A (SDK + knowledge `internal_parse.py`) | Stage 2 |
| W3 | 22-C (FE `features/books` + `features/studio/panels`) ∥ 26-B (book-service Go) ∥ 24-H2.2 (FE `features/plan-hub/layout`, pure function) ∥ 28-AN-B (book-service `steering_tools.go`/`search_tools.go`, new files — registration serialized per the registry) | Stage 4–5 |
| W4 | 27-V2-B (contracts) ∥ 27-V2-C (engine/services) — 27's own declared fanout | Stage 6 |
| W5 | 24-H3 ∥ 24-H4 ∥ 24-H5 (drawer / decorations / interactions) — 24's own declared fanout | Stage 7 |
| W6 | 28-AN-A (composition, Python) ∥ 28-AN-B remainder (book-service, Go) — disjoint services | Stage 8 |

### Shared-file collision registry (serialize these; never fan out across them)

| File | Claimants | Rule |
|---|---|---|
| `composition-service/app/mcp/server.py` | 25 task 6 (24 gate sites) · 23-B1..B4 · 22-B3 · 26-C3 · 27-V2-F1 · **28-AN-A2/A3/A4** | One claimant at a time, in stage order. This is the busiest file in the whole plan. |
| `composition-service/app/db/migrate.py` | 25 (owner of the trains) · 23-A1 · 22-B1 · 26-C1/D1 · 27-V2-A · 24-H1.2 | **The OQ-11 M-train rule** (CF-8's adjudication): *additive* DDL rides each spec's own build inline in `_SCHEMA_SQL` (`IF NOT EXISTS`, no central train); *non-additive* DDL (drops, CHECK swaps, PK changes — 27-A3 is the one instance) MUST register as a numbered 25 M-step before building (Stage 6.0). The file itself is still single-writer per wave. |
| `book-service/internal/api/parse.go` + `worker-infra/…/import_processor{,_pdf}.go` | 22-A5 · 26-B1 · 26-D2 | 22-A5 merges before 26-B1 starts; 26-D2 last. |
| `book-service/internal/api/mcp_server.go` | 22-A4 (scene tool registration) · 28-AN-B1/B2 (steering + search registration) | 22-A4 first; AN-B's new tool files are disjoint but the registration edit serializes here. |
| `chat-service …/frontend_tools.py` + `contracts/frontend-tools.contract.json` | 22-C2 · 24-H2.1 (panel-enum additions + regen) | Each panel addition is its own regen commit; never two concurrent regens. 28 adds **nothing** here (AN-12: no new GUI, no enum change). |

---

## 5. Adjudication ledger — CF-1..15 verified on disk (2026-07-10), plus residuals

Every row was re-checked against the file content, not the handoff notes
(`debt-batches-list-is-stale-verify-first`).

| # | Conflict (one line) | Where the fix landed (file + anchor) | Status |
|---|---|---|---|
| **CF-1** | 23 restated the whole migration; its P0.0 pre-flight fails on any dị bản | 23 §Task breakdown: ⚠ *"Superseded 2026-07-10 — migration ownership moved to 25"* block (above Phase 0), naming M0.1 as P0.0's replacement + PM-3/4/10 | ✅ (the 22 A1/B0 sequencing pointers ride 25 task 1b at Stage 1.1 — NC-2a; 25's header still wins on conflict until then) |
| **CF-2** | 00A BPS-1/2/6 vs shipped C23 derivative code | 00A §9: BPS-1 *"✏️ refined by 25 PM-3"* (project_id survives as partition key), BPS-2 *"✏️ refined by PM-4"* (partial unique), BPS-6 *"✏️ refined by PM-10"* (replay stays `(project_id, key)`) | ✅ |
| **CF-3** | 22 SC5 "on draft/save" vs 26 IX-1 publish-only | 22 SC5: *"✏️ inverted … by the parser, **on publish** (never on draft/save … [26] IX-1)"* | ✅ |
| **CF-4** | 22 D5 "deleting a spec node nulls `source_scene_id`" — no such physical write can exist | 22 D5: *"**renders** the back-link as null **at read time** via the union join; no physical write occurs … [26] OQ-4"* | ✅ |
| **CF-5** | 23 Phase E vs 27's ownership + bare-`event_id` idempotency | 23 Phase E: ⚠ *"Superseded 2026-07-10 — link-step ownership moved to 27"* block (naming PF-10's re-key + the A3 CHECK swap); 00A BPS-18 *"✏️ refined by 27 PF-10"* | ✅ |
| **CF-6** | 00A §4 shelved `import_source` inside `<book>/` against DA-11 | 00A §4 `import_source` row: *"**outside** ✏️ … moved outside the package 2026-07-10 … caught by 25 PM-16/OQ-10"* | ✅ |
| **CF-7** | DA-8 "sole writer: the parser" vs 26 IX-12's two-service writing role | 00A DA-8 ✏️: *"One anchor-writing **ROLE** per identity … book-service's parser plus worker-infra's book-DB import tail … never composition"*; 00A §6 row matches; 26 OQ-6 is the source decision | ✅ (22's design-section line 208 still says "exactly one writer … the parser" — NC-2d, one-line sweep) |
| **CF-8** | The mutual-deferral DDL gap + the children-route flip named by nobody | 25 **OQ-11** (added at integration): the M-train rule (additive rides each spec's build; non-additive registers as a numbered M-step) + **24-H1.1 pinned to Deploy 2**; 25 OQ-8 adjudicated **MOOT** (neither 26 nor 27 needs the lift map) | ✅ (open tail: 27-A3's M-step not yet minted in 25 — NC-4, gated at Stage 6.0) |
| **CF-9** | 23 "writes stay MCP-first" left the Hub's drag-drop without a transport | 23 §API+MCP (line ~356): *"Writes stay MCP-first **for agents** … Phase B therefore also ships REST write mirrors over the same repo methods — one repo method, two front doors ([24] PH20/OQ-3)"*; 24 OQ-3 marked RESOLVED citing it | ✅ |
| **CF-10** | PH21's extract-CTA wired to internal-token + MCP-only surfaces | 24 OQ-9: **Decided** — 22-B4 also ships an EDIT-gated `/v1` mirror; arc analysis reuses propose→confirm; PH21 carries the disabled-with-tooltip fallback until then. Sequenced at Stage 4.2 | ✅ (22 B4's own task row not yet annotated — NC-2b) |
| **CF-11** | Two read surfaces claimed the Hub's drift badges (24 `plan-overlay` vs 26 IX-14's route) | **Direct-consume adopted** (NC-1 ✅ 2026-07-10): the Hub reads IX-14's route as read surface #7 (≤5 budget); drift never rides `plan-overlay`; 26's consumer note + 28's AN-2/AN-4/OQ-4 swept to match. ONE computation, its route for the GUI, its helper for the agent aggregates. | ✅ |
| **CF-12** | 26 IX-11 reserved `source='planforge'` but 27's linker never wrote it; two identity axes could double-mint | 27 **V2-E2b**: both linkers stamp `source='planforge'`; `link_report.possible_duplicates` widens to cross-axis (planforge × decompiled) matches, never auto-merged; the IX-11(a) and PF-11 preservation predicates compose | ✅ |
| **CF-13** | The 28 spec did not exist while three specs delegated ownership to it | `28_agent_native_studio.md` authored + adversarially verified (9/9 findings fixed); AN-1's closed matrix makes the boundary enforceable; 24's narration swept (NC-3a ✅) | ✅ |
| **CF-14** | Two spec files shared the number 24 | Renumbered on disk: `29_translation_repair.md`; links swept; 00A §10 row ✅; 24's header numbering note confirms | ✅ (27 OQ-7 still narrates a live collision — NC-3b) |
| **CF-15** | Bare "Phase A" names three different things across 22/23/26 | This file's `<spec>-<phase>` convention; 24/25/26/27/28 all cite by qualified phase or full filename | ✅ (convention, enforced by review) |

### New/residual conflicts found by this pass (⚠ open)

| # | Finding | Where | Resolution (all four closed 2026-07-10, same session) |
|---|---|---|---|
| **NC-1** ✅ | The CF-11 adjudication had landed as two opposite texts (26/28: *compose into plan-overlay, ≤4* vs 24's revised PH18: *consume the route directly, ≤5*). | 24 ↔ 26 ↔ 28 | **RESOLVED — direct-consume wins.** 24's revised shape is adopted as final: the Hub reads `26` IX-14's route directly as read surface #7 (≤5 cold-open budget); drift never rides `plan-overlay`. Rationale: independent refresh cadence for staleness (re-fetch on focus without re-pulling the overlay), one wire shape for staleness, and an honest pre-26 degrade (route absent → badge absent). Swept: 26 IX-14's consumer note, 28 AN-2/AN-4's consumer lists + OQ-4. ONE computation stands (26-C3's helper): the Hub consumes its **route**, the agent aggregates compose its **helper**. Stage 5.2's gate is lifted. |
| **NC-2** ✅ | The 22-side stamp tail (four one-liners). | 22 | **LANDED in 22:** (a) A1 + B0 sequencing pointers → 25 Deploy 1 / M0–M3; (b) B4's EDIT-gated `/v1` mirror (24 OQ-9); (c) A4's `book_scene_list.source_scene_id` filter arg (28 AN-5b); (d) the DA-8 writing-role reword at the design section. |
| **NC-3** ✅ | Stale narration left behind by the adjudications. | 24 · 27 · 25 | **SWEPT:** 24 header/:127/OQ-7 now say 28 is authored (and that the `resource_ref` convention remains open, gating Phase 4); 27 OQ-7 marked resolved (29 rename); 25's header retires its conflict-precedence clause — task 1b's stamps are on disk. |
| **NC-4** ✅ | 27-A3's non-additive CHECK swap had no numbered 25 M-step. | 25 | **REGISTERED as 25-M6** (M6.1: the `outline_chapter_written_kinds` swap + arc/beat `chapter_id` pre-flight; ordered after M5, ships with 27 V2-A, must precede 27 V2-E's first link insert). Stage 6.0 becomes a check that M6 is honored, not a registration task. |

---

## 6. Product decisions — ✅ RATIFIED IN FULL by the PO, 2026-07-10

The PO approved **all 15 recommended defaults as decisions** ("let's seal layer 1, I approve your
suggestion"). Each owning spec's OQ row carries the ✅ RATIFIED stamp; the table below is the
consolidated record. **P-2 additionally ratifies 25 OQ-2** (canonical-Work reads) **and P-8
ratifies BPS-19b's checkpoint policy** — their register/spec homes are stamped. BPS-9 (parts/saga
→ explicit proposal, 26 IX-17) was ratified separately the same day. **No open product decisions
remain anywhere in the 22–28 cluster.**

| # | Owner | Question | ✅ Decision (= the recommended default, ratified) |
|---|---|---|---|
| P-1 | 25-OQ-1 | May an EDIT-grantee auto-provision the book's knowledge project? | **No — stays OWNER-only.** Owner-identity minting on a grantee's action is privilege escalation with billing surface; the MED-1 message already gives an actionable path. |
| P-2 | 25-OQ-2 | With derivatives (dị bản), do book-scoped reads return the canonical Work's spec only, or all Works'? | **Canonical only** (`source_work_id IS NULL`); derivative surfaces pass `project_id` explicitly. (28's three composition tools are hard-wired to this resolution — §Canonical-Work scoping.) |
| P-3 | 25-OQ-3 | Do `.runs/` reads (`plan_run`/`plan_artifact`/`authoring_runs`/`plan_bootstrap_proposal`) widen to book-grant VIEW in Deploy 1? | **Yes, in the M3 sweep** — predicate-only, no DDL; leaving them owner-keyed recreates the F5 fork class one layer up. Also gates 28-AN-2's `runs` block (which degrades to absent + warning if deferred). |
| P-4 | 25-OQ-4 | Timing of Deploy 2 (M4–M5, the point of no return). | **The next session after Deploy 1 survives a real authoring session + T1–T6 green** — never the same run. Gates Stage 3. |
| P-5 | 26-OQ-1 | Does a parse failure block publish? | **No** — publish proceeds, index marked stale, sweeper heals; the failure is visible, never silent. |
| P-6 | 26-OQ-2 | Index drafts (debounced re-parse on save) or canon only? | **Canon-only in v1**; draft-ahead is already its own visible fact. Revisit on a real user request. |
| P-7 | 26-OQ-3 | How loudly does the Hub surface dirtiness? | **Per-arc badges + one `stale_chapter_count` rollup line; no book-level banner** (banner-blindness). |
| P-8 | 27-OQ-1 | Checkpoint classes — blocking at passes 2 + 4, advisory elsewhere? (BPS-19b explicitly reserves the override to the PO.) | **As stated** (blocking 2 + 4), with `auto_approve` as an explicit per-call arg for autonomous runs. |
| P-9 | 27-OQ-2 | `genre_tags` source (closes BPS-20's open sub-question). | **PF-15**: explicit optional `genre_tags` on run create, persisted on `plan_run`, omitted ⇒ `[]`. A per-book fallback can layer on later. |
| P-10 | 24-OQ-1 | Timeline / worldmap visual treatment (PH22 mandates PO-DECIDE). | **v1 ships narrative mode only**; the two mode buttons render disabled with a "coming" tooltip. Data contracts are locked either way. |
| P-11 | 24-OQ-5 | Initial camera on Hub open. | **From an editing context: focus + expand the active chapter's arc; otherwise fit-whole-book, all arcs collapsed** (the working-scope lesson applied to the canvas). |
| P-12 | 24-OQ-6 | Does OutlineTree's indented-list view survive as a toggle inside the Hub? | **No toggle in v1** — the Plan navigator rail is the list rendering of the same data. |
| P-13 | 24-OQ-7 | What does "Ask AI about this plan" do in v1? | **Opens Compose chat with the current selection's ref pre-filled** — existing surface, zero new contract; the canvas-native plan-agent affordance stays Phase 4 / PH8. |
| P-14 | 28-OQ-1 | Should `composition_find_references` federate glossary chapter-links + KG edges into one cross-service backlink read? | **No in v1.** The three sibling reads exist and the tool's description names them; a federating proxy makes composition a read-router over three services and triples its failure surface. Revisit on transcript evidence of agents failing to compose the three calls. |
| P-15 | 28-OQ-2 | Should the studio turn auto-inject a one-line *live* package digest (counts + dirty flag) instead of the static tool-name sentence — the auto-context recipe default? | **No.** A cross-service fetch on every turn for task-dependent context; the measured lessons (`m3-pullmode-measured-nogo`, the 4000-token trim) say don't add per-turn cost without a measured win. Revisit with AN-D3 replay data if orientation reads aren't happening. |

Adjudication items that look like PO-DECIDEs but are **not** (evidence-forced refinements or
decided-with-override-noted, listed in §5): PM-3/PM-4/PM-10 (CF-2), PF-10 (CF-5), the DA-8
rewording (CF-7), 28-OQ-7 (steering write tier — decided **A**, PO may override to W on transcript
evidence of abuse).

---

## 7. Definition of done — per pillar, each tied to a verifiable EFFECT test

Per `checklist-is-self-report-enforce-by-tests`: a pillar is DONE only when the named test asserts
its effect, not when its tasks are checked off.

| Pillar | DONE means | The effect test |
|---|---|---|
| **Foundation: 23** (structure layer) | The spec steers generation — the exact write-only bug F1 names is dead. | **23-D2**: `pack.py`'s assembled prompt CHANGES when `structure_node.tracks` changes. Plus 23-D7: S06 idea→arc replay green (agent authors an arc, never says "template"). |
| **Pillar 25** (package re-key) | Two collaborators genuinely share one spec — tenancy is real, not aspirational. | **22-D4**: collaborator B on a shared book sees the manuscript's scenes AND the shared spec, and no per-user `outline_node` fork exists. Plus 25-T3 (grantee-widening: B's PlanForge run attaches to THE canonical Work, zero pending forks) and 25-T4 (derivative separation) green on the T1 snapshot. |
| **Foundation: 22** (scene seam) | An imported book's scenes are browsable and an agent-set `tension` changes generation. | **22-D3** live smoke: import → scenes visible with no Work → decompiler upserts one spec node per leaf → parser back-links `source_scene_id` → agent sets `tension=80` → `adaptive_k` picks the high-tension policy. Plus **22-D5** (index disposable, spec durable). |
| **Pillar 26** (indexing/staleness) | The index re-derives on canon change and staleness is visible end-to-end. | **26-F2** live smoke: edit → publish → `scenes` deltas ≠ 0 → `chapter.scenes_reparsed` consumed by knowledge (invalidation observed) → P2 reads the NEW leaf text → Hub flips the arc to `dirty: prose_drift` → conformance re-run clears it by predicate. Plus 26-F3 (a one-word edit preserves every back-link; re-import never clobbers an authored node). |
| **Pillar 27** (PlanForge v2) | The compiler stops discarding its output and grounding holes close. | **27-H4**: S06 flagship replay green vs the committed 2026-07-09 baseline, AND the grounding metrics beat the one-shot floor (scenes with non-empty `present_entity_ids` ≥80%, named introductions ≥90%, `motif_coverage` non-empty, tension peak not in ch1, **linked nodes > 0 — a zero-link compile is red**). Plus 27-H2 (pass-6 prompt changes when `cast_plan` changes; packer changes when `roster_bindings` change). |
| **Pillar 24** (Plan Hub v2) | A human and an agent both drive the package model through one canvas. | **24-H8.2** live browser smoke: agent `ui_open_studio_panel('plan-hub')` → canvas renders a seeded book → drag a chapter across lanes → DB `structure_node_id` changed → overlay badge updates. Plus **24-H8.1**: 10k-chapter fixture, cold-open request budget met (the constant is NC-1's resolution — ≤4 composed or ≤5 direct), EXPLAIN proves the keyset index is used. |
| **Pillar 28** (agent-native studio) | The agent can see, search, steer, and verify the package — and provably uses that power. | **28-D2** steering effect test: `book_steering_set` → the rule lands in the NEXT real turn's `<steering>` block (effect, not row) — and a diagnostics item disappears after its underlying fix. Plus **28-D3** the S06 replay orientation-read gate: the steering row exists after turn 9 in Mai's wording; every "it's set up"-class claim is preceded by a `composition_package_tree`/status read; ≤2 discovery calls per movement; §1-denylist grep = 0. Plus the AN-2 budget gate (10k-chapter tree ≤ 4K tokens). |

---

## 8. Risks of the sequence itself

| Risk | Mitigation (lesson) |
|---|---|
| A concurrent session ships part of a stage while this roadmap is in review | Re-grep before each stage's CLARIFY (`shared-checkout-convergent-tracks-verify-before-clarify`); §2's ground-truth table is dated and must be re-verified at Stage-1 kickoff (`debt-batches-list-is-stale-verify-first`) |
| ~~NC-1 stays unresolved~~ (resolved ✅) — residual risk: a builder re-introduces drift into `plan-overlay` "to save a request" | The NC-1 resolution is recorded in 24 PH18, 26 IX-14, 28 AN-4, and §5 — four places a builder will look; H8.1's budget test pins ≤5 with the conformance call named (`css-var-duplicated-across-two-consumers-drifts`) |
| The five shared files (§4 registry) get concurrent edits during a wave | The collision registry is the fanout gate: a slice touching a registry file is not fanout-eligible (`fanout-independent-slices-parallel-build-serial-integrate`, `shared-file-collision-safe-staging-multi-agent-checkout`) |
| Deploy 2 lands before Deploy 1 has soaked | P-4's default is the gate; 25-T7's rehearsal on a snapshot is mandatory before M5 touches the real DB (`kg-integration-tests-truncate-shared-dev-db`) |
| The route flip (Stage 3.3) ships in a different deploy than the lift and the Navigator breaks | Pinned to the same deploy by 25-OQ-11; 24-H1.1 carries a test that fails if `parent_id`-omitted returns chapter-kind rows (`new-cross-service-contract-needs-consumer-live-smoke`) |
| 27-A3 builds without its 25 M-step and the non-additive swap ships unordered | Stage 6.0 is a hard gate (NC-4); the M-train rule is in the §4 registry where the builder will look |
| Stage 7 builds against 26-less drift data and fakes a zero | 24-OQ-8 already decided: the drift key/route is ABSENT until 26-C ships — absent ≠ zero; the FE renders no badge (`fe-status-default-fallback-signals-backend-field-omission`) — the same posture 28-AN-2 applies to its manuscript/index/runs blocks |
| 28's tools ship but the model never calls them (the S06 baseline failure: no attempt) | AN-10 synonyms + `tool_list` completeness + AN-C2's static note; AN-D3 counts orientation reads — shipped-but-unfound is a FAIL (`checklist-is-self-report-enforce-by-tests`) |
| The residual stamps (NC-2/NC-3) never land and a builder follows the stale text | ✅ landed 2026-07-10 (same-day clearance); residual risk retired — §2's ground truth is the check |

---

## 9. The v2+ ledger — everything deliberately NOT in v1, in one place

Every "v1 ships X, revisit later" across the cluster, consolidated (added at clearance,
2026-07-10). **A row here is a conscious cut with an owner and a trigger — not a forgotten item.**
Nothing below blocks any v1 stage. Rule: shipping a ledger row early is a *spec amendment to its
owner first* (the owning OQ/decision row gets un-deferred), never an inline build decision.

### Product features cut to v2+ (each ratified as a v1 cut by its P-row)

| # | What it is | Owner (spec home) | Ships when / trigger |
|---|---|---|---|
| V2-1 | **Timeline view mode** — same canvas nodes re-laid on the `story_time` axis (data contract already locked: sort stays `story_order`, `story_time` renders as captions; "Undated" tray) | 24 PH22 / Phase H7 (P-10 ✅) | its own cycle after Hub v1 ships; PO schedules |
| V2-2 | **Worldmap view mode** — nodes clustered by `location_entity_id`, edges = scene transitions ("Unlocated" tray) | 24 PH22 / Phase H7 (P-10 ✅) | after V2-1 (each mode its own cycle) |
| V2-3 | **Canvas-native plan agent** — "Ask AI" acts ON the canvas: AI-pending ghost nodes (`ai-pending` dashed-gold state), highlight-my-pending-edit | 21 PH8 / 24 Phase 4 (P-13 ✅) | gated on **AN-12 `resource_ref`** (28 OQ-8) being specced first; after `27` links PlanForge output so the agent has real spec objects to point at |
| V2-4 | **Draft indexing** — debounced re-parse on save so the scene browser sees unpublished prose | 26 OQ-2 (P-6 ✅, canon-only v1) | a real user request — not before |
| V2-5 | **Federated `find_references`** — one call spanning composition + glossary links + KG edges | 28 OQ-1 (P-14 ✅) | transcript evidence that agents fail to compose the three existing reads |
| V2-6 | **Per-turn live package digest** in the studio agent's context | 28 OQ-2 / AN-9 (P-15 ✅) | AN-D3 replay data showing orientation reads don't happen |
| V2-7 | **Per-book `genre_tags` fallback setting** layered under the explicit run-create arg | 27 PF-15 (P-9 ✅) | when a book-settings home exists with a consumption proof (SET rules) |
| V2-8 | **Branching UX** — diff / merge / promote between a book's Works (the dị bản substrate already shipped as C23 `source_work_id`; what's missing is only the UX + merge semantics) | 00A BPS-15 ✏️ (no pillar spec yet — it will need its own) | the first real user request for two plans on one book |
| V2-9 | **Volume-aligned arc proposals** — the decompiler proposes arc boundaries at `parts` boundaries, human approves (`boundary_hint: volume\|content`) | 26 IX-17 (BPS-9 ✅) | ships WITH 26 Phase D's arc-level decompile work — early v2, already fully specced |
| V2-10 | **Per-node track paint** on canvas nodes (v1: tracks render as lane legend + drawer only) | 24 PH23 | users ask; PO-reviewable enhancement |
| V2-11 | **Server-side `status`/`pov` filters** on the scene browser (v1: client-side, documented in the panel footer) | 22 OQ-1/BPS-11 | profiling evidence from a real 10k-scene book — never speculation |
| V2-12 | **Scene-level anchor-orphan detail in `composition_diagnostics`** (v1: chapter-level `index.stale` rollup; scene detail lives on 22's browser union) | 28 AN-4 | when the diagnostics tool gains a book-service read path worth its cost |
| V2-13 | **Event-driven staleness** (v1: poll-on-read via IX-9 canon-markers; the manifest comparison is transport-agnostic) | 26 IX-9 | if profiling shows the poll hurting — "the event alternative stays available without schema change" |
| V2-14 | **`_arc_lift_map`-style provenance beyond M5** — none needed (OQ-8 MOOT); listed only to say so | 25 OQ-8 ✅ | n/a — closed |

### Contract work scheduled INSIDE the v1 stages (not v2 — just later stages; listed to kill ambiguity)

| What | Owner | Ships at |
|---|---|---|
| `planner_state` un-fixture + `VariableDef.initial` + first reader (BPS-21) | 27 PF-14 | **27 V2-B1** (Stage 6) — scheduled, not deferred |
| `resource_ref` convention (AN-12) | 28 OQ-8 | specced when 24 Phase 4 is scheduled — a Phase-4 build without it is a spec violation |
| 10k-chapter perf fixture (assumed by 24-H8.1's EXPLAIN/budget gate, 28-A2's token-budget test, 26's sweep tests) | **built once at Stage 7.6 (24-H8.1), owner of record; 28-AN-D and 26-F reuse it** | Stage 7.6; a generated-content script, not hand-authored |
