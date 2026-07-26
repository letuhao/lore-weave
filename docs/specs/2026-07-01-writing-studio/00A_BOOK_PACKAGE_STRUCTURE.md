# 00A · Book Package Structure

> **Status:** 🗺️ reference · **all open questions cleared 2026-07-10** · branch `feat/context-budget-law`
> **Scope:** every table in `composition-service` (30) and `book-service` (27), placed in one model, plus the **Decisions Register** (§9) that closes every open question in [`22`](22_scene_model_and_crud.md), [`23`](23_book_architecture.md), and this file.
> **Companions:** [`00_OVERVIEW.md`](00_OVERVIEW.md) · [`23_book_architecture.md`](23_book_architecture.md) (the spec layer) · [`22_scene_model_and_crud.md`](22_scene_model_and_crud.md) (the scene seam) · [`docs/DATA_ARCHITECTURE.md`](../../DATA_ARCHITECTURE.md)
>
> This file **maps, names, and decides. It does not duplicate DDL.** Column truth lives in
> [`composition/app/db/migrate.py`](../../../services/composition-service/app/db/migrate.py) and
> [`book-service/internal/migrate/migrate.go`](../../../services/book-service/internal/migrate/migrate.go).

---

## 1. The name, and why it is the right one

**A book is a package.** It has a manifest, declared dependencies on a registry, a lockfile that
pins what was resolved, a spec, a test suite, an implementation, a derived index, and a build
history. Every table in both services lands in exactly one of those, and once you see it, *where a
new table goes* stops being an argument.

The analogy earns its keep everywhere **except one place**, and that exception is load-bearing
enough to state before the layout:

> **Nobody edits `dist/bundle.js`. Everybody edits chapter 12.**

In a compiler, the source holds *all* the information and the binary is a total function of it —
which is why `target/` is disposable. Here the plan holds perhaps one percent and the prose holds
the rest. Generation is a **lossy expansion**, not a compilation: run it twice, get two different
books. `rm -rf manuscript/ && rebuild` does not restore the book. It destroys it and writes a
different one.

Book-service is not shaped like a build directory either: `chapter_drafts`, `chapter_revisions`
(`body`, `message`, `author_user_id` — that is a *commit*), a Tiptap editor, a raw editor.
`target/` does not get an editor and a revision history with commit messages.

So `manuscript/` is **not** `target/`. The relation between `spec/` and `manuscript/` is
**desired-state ↔ actual-state**, reconciled — the `terraform plan` relation — and the proof is
already in the codebase: **`arc_conformance` exists.** You never diff a binary against its source;
you just rebuild it. A conformance engine is only meaningful between two independently-durable
things.

---

## 2. The package layout

```
<book>/
│
├── book.manifest            composition_work                    ← L1 MANIFEST
│                              settings · active_template_id · knowledge project ref
│
├── deps/                    arc_template · motif · motif_link   ← L0 REGISTRY
│                            structure_template                     2-tier (system|user) · visibility
│                                                                   version · imported_derived (licence)
│                                                                   embedding (search)
│         │ apply()                                    ▲ extract()
│         ▼                                            │
├── book.lock                motif_application                   ← L2 LOCKFILE
│                              motif_id + pinned motif_version + role_bindings
│                              "what was bound, not what's live"
│
├── spec/                    ★ DESIRED STATE · per-book · shared  ← L3 SPEC
│   ├── structure/           structure_node    saga → arc → sub-arc
│   │                          tracks · roster · roster_bindings · provenance
│   ├── outline/             outline_node      chapter → scene
│   │                          pov · present_entity_ids · tension · goal · conflict …
│   ├── links/               scene_link        setup → payoff
│   ├── grounding/           scene_grounding_pins
│   ├── style/               style_profile · voice_profile
│   └── divergence/          divergence_spec · entity_override · reference_source
│
├── tests/                   ★ ASSERTIONS over the manuscript     ← L4 TESTS
│   ├── canon_rule           world invariants · reveal gates
│   ├── narrative_thread     promises / foreshadows that must be PAID
│   └── (runner)             arc_conformance   →  diff(spec/, manuscript/)
│
├── manuscript/              ★ THE IMPLEMENTATION                 ← L5 IMPLEMENTATION
│   ├── parts/ chapters/       chapters · chapter_drafts · chapter_revisions
│   │                          ★ SSOT OF CONTENT · hand-edited · NEVER regenerated from spec/
│   └── media/                 chapter_raw_objects · page_images · audio_segments · block_media
│
├── .index/                  ★ SOURCE MAP · derived · never hand-edited   ← L6 INDEX
│   ├── scenes                 leaf_text · content_hash · parse_version
│   │                          source_scene_id ──────────────┐
│   └── chapter_blocks         search + P2-extraction projection │
│                                                                ▼
│                                              spec/outline/<scene>.id
│
└── .runs/                   BUILD DIRECTORY                       ← L7 RUNS
    plan_run                  ← the COMPILER (PlanForge) · source_markdown = source file
    plan_artifact               kind='spec'    = the typed IR (NovelSystemSpec)
                                kind='package' = the OBJECT FILE  ──link──▶ spec/, deps/, glossary
                                                 ⚠ outline_skeleton has NO linker (BPS-14/18)
    plan_bootstrap_proposal · authoring_runs · authoring_run_units
    decompose_commit · generation_job · generation_correction · import_jobs

─── OUTSIDE the package (per-USER, not per-book) ──────────────────────────────
    book_collaborators (E0 grants) · reading_progress · book_views
    user_book_prefs · user_favorites · composition_daily_progress
    composition_progress_baseline · user_storage_quota · book_consumed_tokens
    tenant_access_audit
```

**The layout *is* the tenancy law.** Everything inside `<book>/` is scoped `book_id`. Everything a
single reader or author owns privately lives outside it. That single sentence resolves the entire
per-user/per-book question — see **BPS-1**.

---

## 3. PlanForge is the compiler

`spec/` is an **intermediate representation**, and it has three producers. This was briefly mistaken
for a design flaw ("three planners converging on one lossy sink"). It is not — a compiler is allowed
several frontends. The defect was that the IR was *lossy*, which [`23`](23_book_architecture.md) fixes.

| Frontend | Registry input | Emits |
|---|---|---|
| **A3 decompose** | `structure_template.beats` (a beat sheet) | `outline_node` tree, via `commit_decomposed_tree` |
| **Arc apply** | `arc_template` (`tracks` × motif `layout`) | `structure_node` + `outline_node` + `book.lock` rows |
| **PlanForge** | a natural-language **plan document** | object files → *(link step)* → `spec/` |

But PlanForge is not merely a frontend. Read against
[`09_PLANFORGE_BLUEPRINT.md`](../2026-07-01-plan-forge/09_PLANFORGE_BLUEPRINT.md) it is a **complete
compiler**, and every stage already has a name in the codebase:

| Compiler stage | PlanForge | Artifact |
|---|---|---|
| source file | the author's NL plan document | `plan_run.source_markdown` |
| lex + parse | ingest | `PlanDocument` |
| **AST / typed IR** | `plan_propose_spec` | `NovelSystemSpec` (`plan_artifact.kind='spec'`) |
| **semantic analysis / type-check** | `plan_validate` (S1–S8 invariants) · `plan_self_check` (fidelity, ranked gaps) | `validation_report` |
| optimizer / fixup passes | `plan_interpret_feedback` → `plan_apply_revision` → `plan_handoff_autofix` | revised `spec` |
| **code generation** | `plan_compile` | `plan_artifact.kind='package'` — **the object file** |
| **link** | ⚠️ *partially missing — see below* | `spec/`, `deps/`, glossary |

### The linker links two payloads out of five

`compile.py` emits five payloads. Traced across every service and the frontend:

| Payload | Linked into | Linker |
|---|---|---|
| `glossary_seeds` | glossary-service entities | `bootstrap_service.py:90` ✅ |
| `planning_package` | the planner / `plan_pipeline` worker | `plan_forge_service.py:375,440,701` ✅ |
| **`outline_skeleton`** | **`spec/` — the arc & chapter tree** | ❌ **nothing** |
| `planner_state_init` | — | ❌ nothing |
| `working_memory_charter` | — | ❌ nothing |

`outline_skeleton` is emitted in exactly the IR's shape — `{"kind":"arc", …}`, `{"kind":"chapter",
"parent_arc": …}` ([`compile.py:44-70`](../../../services/composition-service/app/engine/plan_forge/compile.py#L44-L70))
— and **no code reads it.** The compiler generates the book's architecture and drops it on the floor.

This is not a mystery, and it is not a phantom blocker. The blueprint's **M5** names it outright:

> *"Wire Manuscript — plan events → outline nodes (**Writing Studio debt #1**)"*

**M5's link step was never built** — because there was nothing coherent to link *into*.
`outline_node kind='arc'` cannot hold `tracks`, `roster`, or provenance. [`23`](23_book_architecture.md)'s
`structure_node` **is the missing link target.** See **BPS-14**, **BPS-18**.

> This closes the loop on the complaint that started this whole architecture: *"after we complete
> plan and make real book we only keep chapter and lost the architecture of the book."* The
> architecture was never lost. **It was never linked.**

### PlanForge v2 is a multi-pass compiler

[`2026-06-30-planning-pipeline-architecture.md`](../2026-06-30-planning-pipeline-architecture.md)
(Status: **DESIGN DIRECTION**, three PO questions never answered) diagnoses `decompose` as
**one-shot**. In compiler terms it is **single-pass**, and every symptom in its own table is a
textbook single-pass failure — an unresolved forward reference:

| Symptom (from the plan review) | Compiler name |
|---|---|
| `motif_coverage = {}` — no thematic structure | a pass that never ran |
| every scene's present cast is empty | **symbol table empty at codegen time** |
| new characters appear anonymous ("a group", "someone") | **use of an undeclared identifier** |
| CH1 telescopes the origin, hits tension 100 in ch1 | no scheduling / budget pass |
| the arc reads generic | no theme pass before codegen |

So v2's seven steps are seven **passes**, and the pass order is forced, not chosen:

| # | v2 step | Compiler pass | Status |
|---|---|---|---|
| 1 | Theme & motif selection | dependency resolution (`deps/` → `book.lock`) | pieces exist (`motif_select`, `MotifRetriever`) |
| 2 | **Cast design + glossary seed** | **symbol-table population** | ⚠️ partial — `engine/cast_plan.py` (Stage 0 `propose_cast`) exists; the seed/orchestration does not |
| 3 | World / power-system | more symbols | partial |
| 4 | Arc & beat shaping + tension curve | **scheduling** | pieces exist (templates, L1) |
| 5 | **Character arcs + introduction schedule** | **definite-assignment analysis** — no symbol used before defined | ❌ **MISSING** |
| 6 | Scene decomposition | **code generation**, conditioned on 1–5 | exists (`decompose` L2), starved of inputs |
| 7 | Plan self-heal | **lint / peephole pass** | ❌ MISSING (but `engine/self_heal.py` has the judge→locate→splice pattern to reuse) |

A single-pass compiler cannot resolve a forward reference. That is *why* the one-shot planner invents
anonymous characters — not a prompt-quality problem, a **pass-structure** problem. See **BPS-19**.

---

## 4. Table inventory — composition-service (30)

`✱` = introduced or changed by [`23`](23_book_architecture.md) / [`22`](22_scene_model_and_crud.md) / this register.

| Table | Package path | Purpose | Scope key (target) |
|---|---|---|---|
| `arc_template` | `deps/` | published arc blueprint: `tracks`✱ · `layout` · `pacing` · `roster`✱ | `owner_user_id` (NULL = system) + `visibility` |
| `motif` | `deps/` | library unit (`sequence`/`trope`/`emotion_arc`/…) with `beats`, roles | `owner_user_id` (NULL = system) + `book_id` label |
| `motif_link` | `deps/` | motif graph edges | inherits `motif` |
| `structure_template` | `deps/` | beat-sheet template (A3 frontend) | `owner_user_id` (NULL = system) |
| `composition_work` | `book.manifest` | settings · `active_template_id` · knowledge project ref | **`book_id` UNIQUE** ✱ |
| `motif_application` | `book.lock` | pinned `motif_version` + `role_bindings` + `structure_node_id`✱ | `book_id` |
| **`structure_node`** ✱ | `spec/structure/` | **saga → arc → sub-arc · `tracks` · `roster` · `roster_bindings` · provenance** | **`book_id`** |
| `outline_node` ✱ | `spec/outline/` | `chapter → scene` + scene intent. `kind='arc'` and `kind='beat'` **both removed** ✱ | **`book_id`** ✱ |
| `scene_link` | `spec/links/` | non-derivable setup→payoff edges | **`book_id`** ✱ |
| `scene_grounding_pins` | `spec/grounding/` | pin/exclude lore for a scene's generation | **`book_id`** ✱ |
| `style_profile` | `spec/style/` | density/pace at work · chapter · scene scope | **`book_id`** ✱ |
| `voice_profile` | `spec/style/` | per-entity voice tags injected by the packer | **`book_id`** ✱ |
| `divergence_spec` | `spec/divergence/` | AU / POV-shift / character-transform | **`book_id`** ✱ |
| `entity_override` | `spec/divergence/` | per-book override of a glossary entity | **`book_id`** ✱ |
| `reference_source` | `spec/divergence/` | lore pins / cited sources | **`book_id`** ✱ |
| **`canon_rule`** | `tests/` | world/entity invariants + reveal gates — **assertions** | **`book_id`** ✱ |
| **`narrative_thread`** | `tests/` | promise / foreshadow / question / MICE debt — **assertions** | **`book_id`** ✱ |
| `plan_run` | `.runs/` | PlanForge pipeline run | `book_id NOT NULL` *(already)* |
| `plan_artifact` | `.runs/` | run output (`spec`/`graph`/`package`/`llm_io`/…) | FK `plan_run` |
| `plan_bootstrap_proposal` | `.runs/` | bootstrap diff awaiting approval | `book_id` *(already)* |
| `authoring_runs` | `.runs/` | Agent-Mode autonomous drafting run | `book_id NOT NULL` *(already)* |
| `authoring_run_units` | `.runs/` | per-unit accept/reject ledger | FK `authoring_runs` |
| `generation_job` | `.runs/` | one LLM generation | **`book_id`** ✱ + `user_id` = **actor** |
| `generation_correction` | `.runs/` | edit / regenerate / reject telemetry | FK `generation_job` |
| `decompose_commit` | `.runs/` | A3 commit idempotency. `arc_id` → `structure_node.id` ✱ | **`book_id`** ✱ + `idempotency_key` |
| `import_source` | ***outside*** ✏️ | raw text staged for import/deconstruct — pre-book, un-shareable, `owner_user_id`-scoped. ✏️ *Moved outside the package 2026-07-10:* placing it at `.runs/` violated DA-11 (per-user scope key inside `<book>/`) — caught by [`25`](25_package_migration_master.md) PM-16/OQ-10. | `owner_user_id` |
| `composition_daily_progress` | *outside* | word-count goal snapshots | `(user_id, book_id)` |
| `composition_progress_baseline` | *outside* | goal baselines | ″ |
| `outbox_events` | — | transactional outbox | — |
| `consumed_tokens` | — | confirm-token `jti` replay guard | `jti` |

## 5. Table inventory — book-service (27)

| Table | Package path | Purpose | Scope key |
|---|---|---|---|
| `books` | `manuscript/` | the manuscript root | `owner_user_id` |
| `parts` | `manuscript/parts/` | **physical/parse** division (`path`, `parse_version`) — *not narrative* | `book_id` |
| `chapters` | `manuscript/chapters/` | **the unit of prose.** `UNIQUE(book_id, sort_order, original_language)` | `book_id` |
| `chapter_drafts` | `manuscript/` | live Tiptap body | `chapter_id` (PK) |
| `chapter_revisions` | `manuscript/` | version history — `body`, `message`, `author_user_id` (**a commit**) | `chapter_id` |
| `chapter_raw_objects` | `manuscript/media/` | original uploaded bytes | `chapter_id` |
| `chapter_page_images` · `chapter_audio_segments` · `block_media_versions` · `book_cover_assets` | `manuscript/media/` | media | `chapter_id` / `book_id` |
| **`scenes`** ✱ | `.index/` | **parse leaves. `content_hash` · `parse_version` · `source_scene_id`✱ · `book_id`✱ · `title`✱** | `book_id` |
| `chapter_blocks` | `.index/` | block projection for search + P2 extraction | `chapter_id` |
| `book_steering` | `spec/style/` | always/scene-match steering text injected into prompts | `book_id` |
| `worlds` | `manuscript/` | world container | `owner_user_id` |
| `import_jobs` | `.runs/` | import pipeline run | `book_id` |
| `book_collaborators` | *outside* | **E0 grants** — the tenancy boundary both services gate on | `book_id` |
| `reading_progress` · `book_views` · `user_book_prefs` · `user_favorites` | *outside* | per-user reader state | `(user_id, book_id)` |
| `user_storage_quota` · `book_consumed_tokens` | *outside* | metering | `user_id` / `book_id` |
| `tenant_access_audit` | *outside* | access audit trail | `book_id` |
| `outbox_events` | — | transactional outbox | — |
| `canon_model_migration` · `word_count_backfill_migration` · `chapter_blocks_extraction_backfill_migration` | — | one-shot backfill bookkeeping | — |

---

## 6. The seams — every cross-database reference

No foreign keys cross a database. Each is a **soft id** with **exactly one writer** (DA-8).

| From | → To | Direction | Notes |
|---|---|---|---|
| `composition_work.book_id` | `books.id` | manifest → package | **`UNIQUE`** ✱ (BPS-2). One manifest per book. |
| `composition_work.project_id` | knowledge-service project | manifest → KG | 1:1 with the Work; becomes per-book (BPS-2 risk) |
| `structure_node.book_id` ✱ | `books.id` | spec → package | Per-book scope key |
| `outline_node.chapter_id` | `chapters.id` | spec → implementation | **the join point where intent meets prose** |
| **`scenes.source_scene_id`** ✱ | **`outline_node.id`** | **index → spec** | **the source map.** Nullable (undecompiled), non-unique. **Sole writing role: the index owner** — book-service's parser + worker-infra's book-DB import tail (DA-8 ✏️; never composition). |
| `plan_run.book_id`, `authoring_runs.book_id`, `plan_bootstrap_proposal.book_id` | `books.id` | runs → package | already `NOT NULL` — the precedent BPS-1 follows |
| `outline_node.pov_entity_id` · `.present_entity_ids[]` · `structure_node.roster_bindings` · `voice_profile.entity_id` · `canon_rule.entity_id` · `entity_override.target_entity_id` · `motif_application.role_bindings` | `glossary_entities.id` | spec/tests → **authored lore SSOT** | glossary is authored SSOT; knowledge-service is its derived layer |
| knowledge-service P2 extraction | `scenes`, `chapter_blocks` | KG ← index | reads the **index**, never the spec |

**Every soft id points from the derived thing toward the authored thing.** `scenes.source_scene_id`
was the sole exception before [`22`](22_scene_model_and_crud.md)'s amendment; it now conforms.

---

## 7. Invariants

Violating one of these is a defect, not a shortcut.

| # | Invariant | Why | Enforced by |
|---|---|---|---|
| **DA-1** | **`manuscript/` is never regenerated from `spec/`.** Generation *proposes*; a human accepts. | Generation is lossy expansion, not compilation. | `authoring_run_units` accept/reject; `generation_correction` |
| **DA-2** | **`.index/` is derived and never hand-edited.** `scenes.leaf_text` and `chapter_blocks.text_content` are projections of `chapter.body`. | A writable index is a second prose store. | [`22`](22_scene_model_and_crud.md) SC13 (D17); `scenes` `/v1` is **read-only** |
| **DA-3** | **The index points at the spec.** `scenes.source_scene_id → outline_node.id`, never the reverse. | A symbol table points at source. Also `scope-separation`: derived carries the anchor. | [`22`](22_scene_model_and_crud.md) SC2 (amended); D5 test |
| **DA-4** | **The spec must be READ, not merely stored.** `pack.py` injects the resolved arc chain, merged `tracks`, pacing, `roster_bindings`, open promises. | `outline_node kind='arc'` shipped write-only. A stored-but-unread blob is a bug. | [`23`](23_book_architecture.md) BA12 + D2 effect test |
| **DA-5** | **The lockfile pins.** `motif_application.motif_version` records what was bound, not what is live. | A trace that follows the live library is not a trace. | existing column |
| **DA-6** | **Conformance diffs `spec/` ↔ `manuscript/`**, not `deps/` ↔ `manuscript/`. Template drift is a *separate* question. | The template is where the plan came from, not what it is measured against. | [`23`](23_book_architecture.md) BA4 |
| **DA-7** | **Derive, don't store.** An arc's chapter span = `min/max(story_order)` over members. Its pacing curve = member scenes' `tension`. | A stored range goes stale on the next chapter insert. | [`23`](23_book_architecture.md) BA6 + **BPS-3** |
| **DA-8** ✏️ | **One anchor-writing ROLE per identity.** Exactly one *role* — one identity arbiter, one evidence-rule set — writes each soft id. For `scenes.source_scene_id` that role is the **index owner**: book-service's parser plus worker-infra's book-DB import tail (which already inserts the `scenes` rows themselves, via [`26`](26_structure_prose_indexing.md) IX-12's decompile write-back) — **never composition**. | `kg-glossary-fk-is-globally-unique`: two writers *disagreeing on identity*, silently arbitrated by a global constraint. The invariant guards against disagreeing arbiters, not against two processes applying one rule set to one DB. | §6 · 26 OQ-6 |
| **DA-9** | **Cascade resolution shadows by key.** `tracks`/`roster`/`roster_bindings` merge root-ancestor → leaf. | Mirrors the System → Per-user → Per-book tenancy cascade — no new mental model. | [`23`](23_book_architecture.md) BA7 |
| **DA-10** | **One name, one concept.** `tracks` = plotlines · `narrative_thread` = promise ledger · `arc_template` = library · `structure_node` = spec · character-arc = entity lens. | `arc` named four things; `thread` named two, one letter apart. | [`23`](23_book_architecture.md) BA10 |
| **DA-11** ✱ | **The package is per-book; the private is per-user.** Nothing inside `<book>/` carries a per-user scope key. `user_id` inside the package means **actor**, never **scope**. | The layout *is* the law (§2). Removes the regime split that produced [`22`](22_scene_model_and_crud.md)'s SC1/SC2 workaround. | **BPS-1** |
| **DA-12** ✱✏️ | **Nothing may *silently* infer narrative structure from `parts`.** `chapters.part_id` (physical) and `outline_node.structure_node_id` (narrative) are independent axes. The one sanctioned crossing: the decompiler may **propose** volume-aligned arc boundaries **for explicit human approval** (BPS-9 ✅) — a write without that approval is the violation. | `parts` is importer output (`path`, `parse_version`). A folder layout must never dictate a story's arcs; it may *suggest* them to a human who decides. | **BPS-9** (decided: explicit proposal) |
| **DA-13** ✱ | **A compiler stage that emits an artifact no stage consumes is a bug.** Every `compile.py` payload must have a named linker, or be deleted. | `outline_skeleton` was generated and dropped for months while the book "lost its architecture". `plan_compile` returning 200 having materialized nothing is `silent-success-is-a-bug-not-environment` at compile scale. | **BPS-18** |
| **DA-14** ✱ | **No fixture constants in codegen.** A compiler backend emits what the IR says, never what the POC fixture said. | `compile.py` hardcodes xianxia genre tags and "preserve dry humor" into *every* book's planning package, and they reach `propose_cast`. | **BPS-20** |

---

## 8. Tenancy — three regimes, one target

| Regime | Tables | Key | Verdict |
|---|---|---|---|
| Library (2-tier) | `deps/` — `arc_template`, `motif`, `structure_template` | `owner_user_id` (NULL = system) + `visibility` | ✅ correct — a registry is System-seeded, user-extended |
| Legacy (per-user Work) | `outline_node`, `scene_link`, `narrative_thread`, `generation_job`, `canon_rule`, `style_profile`, `voice_profile`, `scene_grounding_pins`, `divergence_spec`, `entity_override`, `reference_source` | `(user_id, project_id)` | ⚠️ **migrates to `book_id`** — BPS-1 |
| **Package (per-book)** | `plan_run`, `authoring_runs`, `plan_bootstrap_proposal` | **`book_id NOT NULL`** | ✅ the target shape — *already shipped*, and the precedent BPS-1 follows |

**Cardinality, checked.** "One source, many books" is **not** a requirement.
`chapter_translations(chapter_id, book_id, target_language)` (*translation-service*) attaches a
translation to the same chapter in the same book; `chapter_revisions(chapter_id, body, message,
author_user_id)` (*book-service*) attaches a version to the same chapter; and chapters are
themselves language-keyed via `UNIQUE(book_id, sort_order, original_language)`. **A book already
holds its own languages and its own history.** No compile-target table is needed.

---

## 9. Decisions Register — every open question, cleared

Each row supersedes the OQ it names. `22` and `23` link here rather than restating.

### Structural

| # | Question | **Decision** | Rationale |
|---|---|---|---|
| **BPS-1** ✏️ *refined by [`25`](25_package_migration_master.md) PM-3* | Which `(user_id, project_id)` tables follow the spec to Per-book? *(latent — opened by [`23`](23_book_architecture.md) BA8, named by no doc)* — **✏️ refinement, forced by shipped code (C23 dị bản):** `book_id` becomes the TENANCY scope key, but **`project_id` survives as the Work *partition* key** — a literal `project_id→book_id` predicate swap would merge a derivative Work's spec/jobs/canon into the source's. `user_id` predicates are *deleted*, exactly as intended. | **All of them inside `<book>/`.** `book_id` becomes the scope key for `outline_node`, `scene_link`, `narrative_thread`, `canon_rule`, `style_profile`, `voice_profile`, `scene_grounding_pins`, `divergence_spec`, `entity_override`, `reference_source`, `generation_job`, `decompose_commit`. **`user_id` demotes from scope key to `created_by`/actor.** Only the *outside-the-package* set stays per-user. | **Scope follows layer** (DA-11). A team shares one `main.tf`; collaborators share one spec, one test suite, one manifest. `plan_run`/`authoring_runs`/`plan_bootstrap_proposal` already did this and nothing broke. Piecemeal migration would mean migrating twice. |
| **BPS-2** ✏️ *refined by [`25`](25_package_migration_master.md) PM-4* | `composition_work` cardinality — N Works per book is currently possible (**verified: no unique index on `book_id`, only `uq_composition_work_project` on `project_id`**). — **✏️ refinement, forced by shipped code:** the unique is **PARTIAL** — `UNIQUE(book_id) WHERE source_work_id IS NULL AND status='active'`. One **canonical** manifest per book; C23 derivative Works (`source_work_id`, the dị bản copy-on-write feature) stay N-per-book *by design*. A bare unique fails the backfill and forecloses a shipped feature. 25's F4 verdict: **safe now, no knowledge-side prerequisite.** | ~~**`UNIQUE(book_id)` on `composition_work`.**~~ One **canonical** manifest per book. `user_id` → `created_by`. | A package has one manifest. Two Works per book was the *only* reason [`22`](22_scene_model_and_crud.md) SC2 needed `UNIQUE(project_id, scene_id)`. ⚠️ **Named risk:** `uq_composition_work_project` makes the knowledge project 1:1 with the Work, so this makes the KG project **per-book**. **Verify before migrating** that knowledge-service does not assume a per-user project. This is a check to run, not an assumption to ship. |
| **BPS-3** | [`23`](23_book_architecture.md) OQ-1 — is `pacing` intent and `tension` realized, or is one derived? | **Neither. Both are intent — so `structure_node.pacing` is DELETED and DERIVED.** An arc's pacing curve *is* the sequence of its member scenes' `outline_node.tension`. `arc_template.pacing` **stays** (a template has no scenes). `apply(template)` writes the template's curve *into* scene `tension` values. | Two authored representations of one fact is the drift bug in miniature. This removes a column, satisfies DA-7, and gives conformance a well-defined comparison: **authored `tension` vs prose-extracted tension.** Corrects [`23`](23_book_architecture.md)'s DDL. |
| **BPS-4** | `outline_node.kind='beat'` — keep, or drop? *(latent)* | **Dropped. `kind IN ('chapter','scene')`.** | **Verified dead:** no code writes `kind='beat'` anywhere; every read excludes it — `outline.py:521` says *"'beat' is excluded (structural, not navigable)"*, and `:526`/`:559` filter `kind <> 'beat'`. Beats live in `beat_role` (on scene/chapter) and in `motif.beats` / `structure_template.beats`. **Migration guard:** count `kind='beat'` rows first — the free-string `kind` (F6) means an agent *could* have created one. Non-zero ⇒ fail loudly. Corrects [`23`](23_book_architecture.md) BA2. |
| **BPS-5** | [`23`](23_book_architecture.md) OQ-3 — `structure_node.roster` vs `arc_template.arc_roster`: accept the asymmetry? | **No. Rename `arc_template.arc_roster` → `roster`**, in the same migration as `threads` → `tracks`. | The "published/embedded rows" concern is empty — a column rename does not touch embeddings or `layout`. Carrying an asymmetry forever to avoid a second `ALTER` *in a migration we are already writing* is false economy. DA-10. |
| **BPS-6** ✏️ *refined by [`25`](25_package_migration_master.md) PM-10* | `decompose_commit.arc_id` after [`23`](23_book_architecture.md) | **Becomes `structure_node.id`.** Renamed `structure_node_id`. **✏️ refinement:** the exactly-once index stays **`UNIQUE(project_id, idempotency_key)`** — NOT `(book_id, …)` as this row originally said: a derivative Work replaying a client key must not be handed the *source* Work's stored result (same C23 logic as PM-3/PM-4). | It already meant "the arc this commit produced". |
| **BPS-7** | `style_profile.scope_type='scene'` → `scope_id` is a soft ref to `outline_node.id` | **Stays soft, no FK.** `scope_id` targets `outline_node.id`; the table re-scopes to `book_id`. | Already soft ([`22`](22_scene_model_and_crud.md) F3: *"`style_profile.scope_id` is already a soft ref — no cost there"*). Adding an FK now buys nothing. |
| **BPS-8** | Grant gating once the spec is per-book | **Gate directly on `book_id` E0 grants.** `_work_or_deny` → `_book_or_deny`; the Work lookup disappears from the hot path. | The Work was only ever a proxy for the book. Removes a query per tool call. |

### Scene seam

| # | Question | **Decision** | Rationale |
|---|---|---|---|
| **BPS-9** ✅ *PO-decided* | [`23`](23_book_architecture.md) OQ-4 / BA14 — `parts` (physical) vs `saga` (narrative) | **DECIDED by the PO (2026-07-10): EXPLICIT PROPOSAL.** The two axes stay orthogonal in data forever — no schema relation, no merge (`parts` is importer plumbing: written only by parse.go/import_processor, read only by the internal hierarchy endpoint, zero frontend references). The ONE sanctioned crossing: **the arc-level decompiler may PROPOSE arc boundaries aligned to `parts` boundaries as hints, and a human approves or redraws them before anything is written** ([`26`](26_structure_prose_indexing.md) §decompiler). Silent inference remains forbidden (DA-12). | Physical ≠ narrative in general (an arc can span volumes; a volume can hold three arcs) — so unification is wrong; but volume boundaries are genuinely useful *hints* at extract time. A confirmed proposal is authored structure with a good default, not inferred structure. No schema change, no migration. |
| **BPS-10** | [`23`](23_book_architecture.md) OQ-5 — does `extract_template` auto-mint a draft template on direct authoring? | **Explicit user action only.** Provenance (`arc_template_id`) stays nullable. | Auto-minting pollutes the registry with every ad-hoc arc. S06's Mai authors an arc and never sees the word "template" — precisely because no template is minted. |
| **BPS-11** | [`22`](22_scene_model_and_crud.md) OQ-1 — server-side `status`/`pov` filters on the scene browser? | **Client-side in v1**, documented in the panel footer. | Requires a cross-service join. Revisit on **profiling evidence** from a 10k-scene book (defer gate #4), not on speculation. |
| **BPS-12** | [`22`](22_scene_model_and_crud.md) OQ-4 — is `exit_state` author-written or generator-written? | **Both, with provenance.** Generator writes it; the author may override. The `{v:1,…}` envelope carries `source: 'generator' \| 'author'`; an author override is never silently reclaimed by the next generation. | Read-mostly in the inspector. Without `source`, a regeneration silently discards an author's correction — the write-only bug class inverted. |
| **BPS-13** | [`22`](22_scene_model_and_crud.md) OQ-5 — a spec scene the parser cannot match leaves `source_scene_id` NULL | **Surfaced, never silent.** The inspector distinguishes *"not yet written"* (no index row) from *"anchor lost"* (index row, NULL back-link) and offers the existing ⚓ re-anchor action. | A silent NULL is `silent-success-is-a-bug-not-environment`. |

### Findings that became decisions

| # | Question | **Decision** | Rationale |
|---|---|---|---|
| **BPS-14** ✅ | Does PlanForge's `outline_skeleton` ever become `outline_node`? *(latent)* | **CONFIRMED: it does not. PlanForge is a compiler with no link step for its `spec/` payload.** Of five payloads `compile.py` emits, `glossary_seeds` links (`bootstrap_service.py:90`) and `planning_package` links (`plan_forge_service.py:375,440,701`). **`outline_skeleton`, `planner_state_init`, and `working_memory_charter` are read by nothing** — verified across all services and the frontend. | It is **not a mystery and not a blocker.** The blueprint's **M5** names it: *"Wire Manuscript — plan events → outline nodes (Writing Studio debt #1)"*. It was never built because there was nothing coherent to link into — `outline_node kind='arc'` cannot hold `tracks`, `roster`, or provenance. **This is the same defect that started this architecture, seen from the compiler end: the book's structure was never lost — it was never linked.** |
| **BPS-15** ✏️ *substrate exists* | [`23`](23_book_architecture.md) OQ-2 — spec branching for collaborator divergence | **Not built in v1. One canonical spec per book, shared.** **✏️ correction (2026-07-10):** the branching *substrate* already shipped as **C23 derivative Works** — `composition_work.source_work_id`, a copy-on-write fork of the spec at a chapter-level `branch_point`, N per book. So "fork the book" was wrong; the real mechanism is **fork the Work**, and it exists. What stays deferred is the branch *UX* (diff/merge/promote between Works). | Conscious deferral (gate #5). Branching is a real feature with a real design, and BA8 makes it *possible* without committing to it. **Revisit trigger:** the first real user request for two plans on one book — not before. |
| **BPS-16** | Three planners write the spec — is that a defect? *(latent, §3)* | **No. Three frontends, one IR.** `structure_template` (beat sheet) and `arc_template` (motif layout) are both `deps/` registry kinds; PlanForge is a full compiler (BPS-17). The defect was a *lossy* IR, which [`23`](23_book_architecture.md) fixes. | A compiler may have many frontends. Merging `structure_template` into `arc_template` (a degenerate single-track arc) is a plausible later simplification — **not** required, and not blocking. |

### PlanForge — the compiler

| # | Question | **Decision** | Rationale |
|---|---|---|---|
| **BPS-17** | Where does PlanForge sit in the package model? *(latent)* | **PlanForge is the compiler** (§3). `plan_run.source_markdown` = source · `NovelSystemSpec` = typed IR · `plan_validate` (S1–S8) = the type-checker · `plan_interpret_feedback`/`_apply_revision`/`_handoff_autofix` = optimizer passes · `plan_compile` = codegen · `plan_artifact.kind='package'` = **the object file**. `.runs/` is therefore the **build directory**, and `plan_artifact` rows are object files awaiting link — not merely history. | Every stage already had a name in the codebase; nobody had written down which stage it was. Naming it makes the missing stage (link) visible instead of inferable. |
| **BPS-18** ✏️ *refined by [`27`](27_planforge_v2_compiler.md) PF-10* | The link step for `outline_skeleton` (blueprint **M5**, *"Writing Studio debt #1"*) — **✏️ refinement:** idempotency is NOT bare `event_id` (event ids are 0%-stable across re-proposes — POC 03 measured title overlap 100%, id overlap 0%); the key is a partial unique on **`(book_id, plan_run_id, plan_event_id)`**, cross-run near-duplicates surfaced in the `link_report`, never auto-merged. Detail owned by 27 V2-E. | **BUILD IT — now owned by [`27`](27_planforge_v2_compiler.md) (PF-8/V2-E), superseding [`23`](23_book_architecture.md) Phase E.** The link target is `structure_node` (arc) + `outline_node` (chapter). `plan_compile` gains `structure_node_id` provenance; `outline_skeleton` entries carry `event_id`, which becomes the idempotency key so a re-link updates rather than duplicates. **Also delete `planner_state_init` and `working_memory_charter` from `compile.py`'s output** — dead payloads with no reader. | `23` is the prerequisite that unblocks M5, not a competing effort. Emitting an object file no linker consumes is `silent-success-is-a-bug-not-environment` at compile scale: `plan_compile` returns 200 having materialized nothing. Deleting dead payloads now stops a future agent "wiring them up" out of politeness. |
| **BPS-19** | [`2026-06-30-planning-pipeline-architecture.md`](../2026-06-30-planning-pipeline-architecture.md) — its three PO questions, open since 2026-06-30 | **(a) Stage it, in pass order — and the doc's own instinct (steps 2 + 5 + orchestration first) is right for a stronger reason than "biggest hole": a pass may not run before its inputs are resolved.** Symbol table (2, 3) → scheduling (4, 5) → codegen (6) → lint (7). **(b) Checkpoints block where the human is the only oracle:** blocking at **2** (cast identity) and **4** (arc shape); advisory at 1, 3, 5, 6, 7 — motif selection is a `deps/` resolution and cheap to redo via the existing `motif_bind`/`_unbind` tools, so it need not block. **(c) One arc is the scope unit — confirmed, and now it finally *has* a referent** (`structure_node.id`). | `decompose` is **single-pass**; every symptom in the doc's table is an unresolved forward reference (anonymous characters = **use of an undeclared identifier**). That is a pass-structure defect, not a prompt-quality one — which is why prompt tuning never fixed it. **(c) is the sharpest evidence:** `compile_artifacts(spec, arc_id: str = "arc_2")` defaults its scope unit to a *fixture string*, because before `23` an arc was not an entity. ⚠️ **(b) is decided on a stated principle; the PO may override.** |
| **BPS-20** ✅ 🐞 | **LIVE BUG — the codegen backend emitted the POC fixture's constants.** *(found + **FIXED** 2026-07-10)* | **FIXED.** `genre_tags` is now a caller-supplied kwarg defaulting to `[]` — never fabricated. `constraints` now come from `charter.style_constraints` + `charter.forbids` (both real, both populated by `propose.py:307`; `style_constraints` was **dead schema** while three fixture strings stood in its place). `arc_id` is now **required**. `planner_state` derives from `spec.layers.variables`. The dead payloads `planner_state_init` + `working_memory_charter` (which hardcoded `language: "vi"`) are deleted per DA-13. | `compile.py` hardcoded `genre_tags: ["xianxia","cultivation","psychological"]` and `constraints: ["HA must stay high…", "Preserve dry humor in early events", "THR: show phenomena only…"]`, and defaulted `arc_id="arc_2"`. **Not dead:** `plan_forge_service.py:750` fed `package["genre_tags"]` into `pipe_input` → `plan_pipeline` worker → `cast_plan.propose_cast(...)`. **Every book was planned as xianxia cultivation fiction with dry humor.** Guarded by `tests/unit/test_plan_forge_no_fixture_constants.py` — it compiles a romance spec and fails on any surviving fixture string. **✏️ Correction:** an earlier draft of this row called `plan_forge_service.py:20`'s `mock_pipeline_result` import a leaked test helper. It is not — `:784` uses it deliberately for `pipeline_preview` on the worker-disabled sync path, and it self-labels `"mock": True`. Left in place. **Open sub-question, still open:** where *should* `genre_tags` come from — `spec.meta` (needs a schema change; `Meta` is `additionalProperties: false`), a per-book setting, or an explicit user field? Until answered, `[]` — honest beats wrong. |
| **BPS-21** | `planner_state`'s **contract schema is fixture-shaped.** *(latent, found while fixing BPS-20)* | **DEFERRED — gate #2 (large/structural: a cross-service contract change).** Not fixed now. | [`contracts/plan-forge/planner_state.schema.json`](../../../contracts/plan-forge/planner_state.schema.json) hardcodes **one novel's variables** as `required: ["PA","HA","CD","THR"]` with `additionalProperties: false` — `Perfection_Addiction`, `Humanity_Anchor`, `Corruption_Debt`, `Than_Hon_Resonance`. The generic source (`spec.layers.variables`, a `VariableDef` list) already exists, and `compile.py` now derives from it. But `VariableDef` has **no `initial` field**, so every variable starts at 0 and the fixture's `HA=100` baseline is inexpressible. **Safe to defer:** `planner_state` is read by **nothing** in composition, and `planner_state.schema.json` is **not validated at runtime** (only the frozen POC writes it). **Target:** add `VariableDef.initial`, drop the four hardcoded keys, before anything consumes `planner_state`. |

---

## 10. Remaining gaps (open work, not open questions)

**Nothing below is undecided.** Every open question in this track is now cleared (§9). Each row is
**buildable, scoped, and unbuilt** — no row is "blocked".

| # | Gap | Package path | Owner |
|---|---|---|---|
| ~~🐞~~ | ~~`compile.py` emits POC fixture constants into every book's planning package~~ | `.runs/` | ✅ **BPS-20 — FIXED 2026-07-10** |
| 0 | `planner_state.schema.json` hardcodes one novel's variables (`PA`/`HA`/`CD`/`THR`) | contract | **BPS-21** — deferred (gate #2); no consumer, not runtime-validated |
| 1 | `structure_node` does not exist — the arc is write-only structure | `spec/structure/` | [`23`](23_book_architecture.md), unbuilt |
| 2 | `pack.py` never reads an arc — the spec cannot steer generation | `spec/` → prompt | [`23`](23_book_architecture.md) BA12 + D2 (**the top risk**) |
| 3 | **PlanForge's link step (M5, "Writing Studio debt #1")** — `outline_skeleton` → `spec/` | `.runs/` → `spec/` | **BPS-18** · unblocked by gap 1 |
| 4 | Agent can suggest an arc but cannot create, apply, move, or safely type one | MCP | [`23`](23_book_architecture.md) F6 / BA11 · blocks [S06](../2026-07-09-agent-discoverability-and-workflow/scenarios/S06-flagship-idea-to-arc.md) |
| 5 | `scenes` has no public route; the SceneRail renders empty for imported books | `.index/` | [`22`](22_scene_model_and_crud.md), unbuilt |
| 6 | The per-book re-key across 12 tables | `spec/`, `tests/`, `.runs/` | [`23`](23_book_architecture.md) Phase 0, widened by **BPS-1** |
| 7 | `useChapterBrowserGroups` pays an O(arcs) cross-service N+1 for group headers | FE | [`23`](23_book_architecture.md) C5 |
| 8 | **PlanForge v2 — the multi-pass planner.** Passes 2 (symbol table) + 5 (definite-assignment) + the orchestration | `.runs/` | **BPS-19** · [`2026-06-30-planning-pipeline-architecture.md`](../2026-06-30-planning-pipeline-architecture.md) |
| 9 | Pass 7 (plan self-heal / lint) — reuse `engine/self_heal.py`'s judge→locate→splice at plan granularity | `.runs/` | **BPS-19** |
| — | ~~Spec-number collisions (`22_`, then `24_`)~~ | docs | ✅ resolved 2026-07-10 — translation-repair renumbered to `29_translation_repair.md`, links swept |

**Dependency order.** 🐞 is independent and immediate. Gap 1 (`structure_node`) unblocks gaps 2, 3,
4, 7. Gap 3 (the linker) is what turns PlanForge from a compiler that discards its output into one
that produces a book's architecture. Gap 8 (multi-pass) is what makes that output *good* — it is
worth building only once gap 3 exists to receive it.
