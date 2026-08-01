# Investigation — Atom Edit (PlanForge checkpoint artifacts): FE + co-writer agent

- **Date:** 2026-07-26
- **Branch:** `feat/frontend-tools-mcp-migration` · **HEAD at investigation:** `5d2975436`
- **Trigger:** human question — *"evaluate atom edit in writing studio, include FE for user atom
  edit on tools and co-writer ability to edit; how many tools affect PlanForge compile and how many
  are designed but never wired; are the tools used correctly and can they be fuel to make chapters
  and improve quality?"*
- **Method:** code read (composition-service + frontend `plan-forge`) **+ live verification against
  the running dev Postgres** (`infra-postgres-1` / `loreweave_composition`). Findings marked
  CONFIRMED were checked against real `plan_artifact` rows, not only source.

---

## 0 · What "atom edit" means here

An **atom** = one **pass artifact** produced by a PlanForge compiler pass — the reviewable unit an
author accepts, holds, or revises at a checkpoint. The seven passes emit six distinct kinds
(`plan_pass_service.PASS_REGISTRY`):

| # | Pass | `output_kind` | Checkpoint |
|---|---|---|---|
| 1 | `motifs` | `motif_plan` | advisory |
| 2 | `cast` | `cast_plan` | **blocking** — who the characters ARE |
| 3 | `world` | `world_plan` | advisory |
| 4 | `beats` | `beat_plan` | **blocking** — what SHAPE the story takes |
| 5 | `character_arcs` | `char_arc_plan` | advisory |
| 6 | `scenes` | `scene_plan` | advisory |
| 7 | `self_heal` | `scene_plan` (new) | advisory |

"**Full atom edit**" (the goal of this track) = every one of those six kinds is reviewable and
revisable **by the author in the GUI** *and* **by the co-writer agent via MCP**, with the edit
provably reaching the artifact and the downstream passes.

---

## 1 · Architecture as built (accurate, for orientation)

Two edit channels, deliberately separated by the sealed 2026-07-26 decision
(*chat = SUPPORTER of atomic edits; compile + long-run drafting = authoring-run SUBAGENT*):

| Channel | Surface | Reaches |
|---|---|---|
| **User (GUI)** | `PassArtifactEditor` inside `CheckpointReview`, in the Pass Rail | `POST …/plan/runs/{id}/checkpoint` with `edits` |
| **Co-writer (agent)** | MCP `plan_review_checkpoint(pass_id, approved, edits)` | the same service method |

Both land on `PlanForgeService.review_checkpoint` → `_merge_pass_edits` → a **NEW** artifact, which
stales everything downstream by derivation. That backend design is **sound**: list fields are
replaced wholesale (option A) so a deletion actually deletes, and a re-run is forced rather than
letting a plan silently become internally inconsistent.

The defects below are all at **seams**, not in that core.

---

## 2 · Findings

### F1 — `beat_plan` editor and viewer are a total no-op — **CONFIRMED (live DB)**
**Severity: high.** `beats` is one of only two blocking checkpoints — the author's primary lever on
story shape — and it is inert.

Real artifact keys, queried live:

```
loreweave_composition=# SELECT kind, jsonb_object_keys(content) FROM plan_artifact
                        WHERE kind IN ('beat_plan','cast_plan') GROUP BY 1,2;
 beat_plan | chapters
 beat_plan | tension_curve
 beat_plan | unmapped_beats
 cast_plan | cast
 cast_plan | roster
```

The producer `plan_pass_adapters.run_beats` emits exactly `{chapters, tension_curve,
unmapped_beats}`. The consumers key on a **`beats`** field that is never produced:

- `PassArtifactView.tsx:41` → `arr(content,'beats')` → renders *"No beats in this plan yet."*
- `PassArtifactEditor.tsx:25` → `{ field:'beats', cols:[beat,tension,synopsis] }` → renders
  *"Nothing here yet — add a row."*
- `plan_forge_service._PASS_LIST_REPLACE_FIELDS['beat_plan'] = ('beats',)` → the wholesale-replace
  rule targets the same non-existent field.

Consequences, in order of harm:
1. The author **cannot see** what they are approving at the blocking checkpoint.
2. `tension_curve` (pass 6 honours it verbatim) and `unmapped_beats` (*"beats the story will never
   hit"* — the checkpoint's whole safety signal) are **never rendered at all**.
3. If the author adds rows anyway, the save writes `{beats:[…]}` — a key **no pass reads** (pass 5
   reads `inputs.beats.chapters`; pass 6 reads `chapters` + `tension_curve`) — **and stales
   `scenes` + `self_heal`**, forcing a paid re-run that changes nothing. Actively worse than inert.

### F2 — `cast_plan` editor drops the model's characterisation — **CONFIRMED (live DB)**
**Severity: medium.** Per-artifact field sets, newest first:

```
019f9d2f-91f2… | archetype,attributes,is_new,name,role,summary   ← engine-produced
019f9d21-3715… | archetype,attributes,is_new,name,role,summary   ← engine-produced
019f6e10-c4cd… | id,name,role,trait                              ← older/fixture-shaped
```

`run_cast` emits `name, role, archetype, summary, is_new, attributes`. The FE viewer and editor
expose `name`, `role`, **`trait`** — a field the engine has never produced. So at the checkpoint
where the human answers *"who are these characters?"*, `archetype` and `summary` are invisible, and
a saved `trait` writes into a field nothing downstream reads. `name`/`role`/**delete** do work, so
this kind is ~2/3 functional.

### F3 — root cause: FE built against a fixture shape; tests lock the fixture — **CONFIRMED**
`PassArtifactEditor.test.tsx:44` feeds `{beats:[{id,beat,tension}]}` and
`PassArtifactView.test.tsx:23` the same. The backend has **never** produced that shape. The suites
are green because they assert the invented shape on both sides.

This is the known **"test input fields from the producer schema, not the code under test"** trap,
and structurally the same class as the Frontend-Tool Contract bug (`panel_id` with no enum): a
2-service / 2-language seam joined by nothing machine-checked. `contracts/frontend-tools.contract.json`
covers agent→GUI tool schemas; it does **not** cover pass-artifact shapes, so nothing red-flagged this.

### F4 — only 2 of 6 atom kinds are editable in the GUI — **CONFIRMED**
`CheckpointReview.tsx:20` — `EDITABLE_KINDS = new Set(['cast_plan','beat_plan'])`, and
`PassArtifactEditor.SHAPE` has entries for those two only (`if (!shape) return null`).
`motif_plan`, `world_plan`, `char_arc_plan`, `scene_plan` fall back to read-only JSON. The author
cannot fix a bad scene breakdown, a wrong motif selection, or a wrong world entity in the GUI at all.

### F5 — the agent's edit path is unrestricted but **unproven end-to-end** — CONFIRMED (code) /
**UNVERIFIED (live)**
`plan_review_checkpoint` accepts `edits: dict` free-form for **any** `pass_id`, so the co-writer is
in principle strictly more capable than the GUI. Two caveats:
- Only `cast_plan`/`beat_plan` get list-replace semantics; every other kind deep-merges, so an
  agent **cannot delete** a scene or a motif — a shorter list silently keeps the removed member.
- **No live evidence exists that any agent has ever successfully edited an atom.** The 2026-07-26
  E2E runs exercised propose → compile → pass → *approve* → bootstrap → draft. An **edit** through
  the agent is untested. ⇒ this is the P1 real-run gap.

### F6 — 🔴 the `beats` pass CANNOT produce a beat role. Ever. — **CONFIRMED (live DB + code)**
**Severity: critical. This is the largest quality defect found, and it explains the human's report
that drafted chapters have wrong content.**

The chain:
1. `PassContext.beats` reads `package["beats"]`. `compile_artifacts` emits `events`, never `beats`.
   **Nothing anywhere writes that key** ⇒ `ctx.beats == []` always.
2. `map_beats_and_shape` derives `beat_keys = {b["key"] for b in beats}` ⇒ **always the empty set**.
3. `plan.py:172` — `beat_role = beat if isinstance(beat,str) and beat in beat_keys else None`
   ⇒ **every chapter's `beat_role` is forced to `None`, whatever the LLM returned.**
4. `plan.py:180` — `unmapped = [b for b in raw_unmapped if b in beat_keys]` ⇒ **always `[]`**, so
   the checkpoint reports perfect health while discarding everything.
5. `shape_tension_curve([None]*n)` groups all chapters into one `None` run and ramps the neutral
   `_DEFAULT_BAND` linearly.

**Live proof — the shipped 10-chapter arc (`019f9d2f-ff27-707c-8566-cf61cd9154a3`, book
`019f9d2b…`, the ~10.6k-word run):**

```
 ch | beat_role | tension_target
  1 |   (null)  | 50
  2 |   (null)  | 52
  3 |   (null)  | 55
  4 |   (null)  | 57
  5 |   (null)  | 60
  6 |   (null)  | 62
  7 |   (null)  | 65
  8 |   (null)  | 67
  9 |   (null)  | 70
 10 |   (null)  | 72
unmapped_beats: []
```

Not a story shape — a **straight line**. No setup, no midpoint, no climax, no resolution. So pass 4
spends an LLM call and throws 100% of its structural output away; pass 6 then decomposes scenes
against a meaningless linear ramp; and every chapter is drafted as narratively identical. (`intent`
IS preserved — `plan.py:173` — which is why chapters had intents and the failure stayed invisible.)

The legacy pipeline documents this degrade honestly (`plan_forge_service.py:1685`, *"beats: []
degrades the pipeline's L1 beat-map stage to a no-op"*); the **new 7-pass path inherited it
silently** and put a blocking human checkpoint in front of it.

**⇒ Compounded with F1, this is the whole failure:** the one gate that could have caught a
shapeless story renders as an empty panel, so nobody could see that the shape was never computed.

#### F6-RC · The wire was BUILT, SEEDED, and then DROPPED by PlanForge V2 — **CONFIRMED**

The human's instinct (*"maybe forgot wire or test"*) is exactly right. Everything needed already
exists:

- **The table:** `structure_template(id, owner_user_id, name, kind, beats jsonb, …)` — a proper
  System/Per-user tiered library (built-ins have `owner_user_id IS NULL`).
- **The data — 6 built-ins seeded and live:**

  ```
  Save the Cat      save_the_cat   builtin  15 beats
  Hero's Journey    hero_journey   builtin  12 beats
  Story Circle      story_circle   builtin   8 beats
  Web Novel Arc     web_novel      builtin   6 beats
  Kishōtenketsu     kishotenketsu  builtin   4 beats
  Three-Act         generic        builtin   3 beats
  ```

- **The shape is already exactly right** — `{key, label, order, purpose}`, which is precisely what
  `build_chapter_map_messages` consumes (`b['key']`, `b['purpose']`), and every key is a member of
  `arc_plan._BANDS` (`hook`, `establishment`, `rising_conflict`, `setback`, `climax`, `resolution`…).
- **The repo, CRUD routes and 5 MCP tools exist** (`composition_structure_template_edit` + legacy
  create/clone/update/archive/restore).
- **The LEGACY plan path WIRES IT** — `routers/plan.py:498-537`: `/outline/decompose` *requires*
  `body.structure_template_id` (404 if absent) and passes **`"beats": tmpl.beats`** into the pipeline.
- **The PlanForge V2 path passes `"beats": []`** — `plan_forge_service.py:1691`.

So this is not missing infrastructure and not a design gap. It is **one dropped connection** in the
V2 rewrite. `structure_template` currently has **zero consumers** outside its own CRUD — verified by
grepping every `StructureTemplatesRepo` reference: `deps.py`, `mcp/server.py` (CRUD), `routers/
canon.py` (CRUD), and the single legacy `routers/plan.py` use above.

**Fix path (F6-FIX):**
1. `plan_run.structure_template_id uuid NULL` (forward-only migration).
2. `plan_compile` resolves the template → `package["beats"] = tmpl.beats`.
3. Resolution must be **explicit-then-defaulted, never silently hidden** (Settings standard SET:
   expose the effective value *and* its source): the run's own id → else a built-in chosen by
   genre/chapter-count → and the package **records which template and why**, so the checkpoint can
   show it.
4. Author + agent must be able to CHOOSE the structure (it is a per-book creative decision, not a
   platform constant) — this is itself an *atom edit* surface, and it is the missing FE wire.

### F9 — 🔴 the motifs pass has NEVER selected a motif, for any book — **CONFIRMED (live DB) · FIXED**
**Severity: critical. Third instance of the identical bug class, found while mapping the atom
matrix.**

Live evidence — **every** `motif_plan` artifact in the database:

```
 id                                   | n_motifs | degraded | warning
 019f9d20-6062-…                      |        0 |          |
 019f9ed9-a5c4-…                      |        0 |          |
 019f9d2f-6be8-…                      |        0 |          |
 019f6b9c-793a-…                      |        0 |          |
 a63e7247-66b0-…                      |        0 |          |
```

Zero motifs, and **not** flagged `degraded` — so it read as "this book legitimately has no motifs".
Consequence: pass 6 has always decomposed scenes with `motifs=[]`, and the prose has never carried
a motif layer.

**Not an empty library** — `motif` holds **147 rows** (88 platform-tier, 118 active).

**Root cause:** `MotifRetriever._fetch_candidates` filters `AND language = $2`. `language` is a
concrete stored code (`en`: 70 active, `vi`: 48 active), but the callers' NEUTRAL default is the
sentinel **`"auto"`** (`packer/profile.from_settings`), which **no row can ever equal**. So the
pre-filter matched 0 of 147, `retrieve` returned `[]`, and the pass emitted a bare `{"motifs": []}`.

The empty-**genre** case already had exactly this guard — MD-2, *"an empty array && is always false
and would zero out retrieval"* — so the defensive pattern was understood and simply not applied to
`language`.

Compounding it, `plan_forge_service`'s `pass_input` never included `source_language` at all, leaving
the worker's `input.get("source_language") or "auto"` fallback permanently in charge — so even a
book that DID declare `vi` ran every pass as `auto`.

**Fix (3 parts):**
1. `_fetch_candidates` omits the language clause for `auto`/`unknown`/`und`/empty — "unspecified"
   means *any* language, the same treatment an empty genre already got.
2. `pass_input` threads the Work's real `source_language` (the field `routers/plan.py` already reads).
3. `run_motifs` emits a `warning` on an empty selection — an empty **result** must be as loud as an
   empty **look** (the existing `degraded` flag only covered "no retriever at all").

**Live proof after the fix** — same book/run, motifs pass re-run:

```
 019f9ef7-3f04-…  15:07:11 | n_motifs = 3
   Dao-Heart Tempering          | central spine  | "…confront the guilt of erasing Oakhaven…"
   Fortuitous Encounter→Legacy  | recurring      | "…the ancient inks and the vanished cartographers…"
   chosen one refuses the call  | climax payoff  | "…refuses Lord Vane's demand to redraw borders…"
```

0 → 3, semantically apt, with distinct arc roles.

### F7 — `package["canon"]` is compiled and read by nobody — **CONFIRMED (code)**
`compile.py` builds `package["canon"]` from the charter's `consistency_anchors`. `PassContext`
exposes only `premise`, `arc_title`, `beats`, `chapters`. No adapter reads `canon`, `constraints`,
`planner_state`, or `events`. The author's declared canon constraints reach compile and stop there.

### F8 — the 7-pass compiler is structurally blind to authored canon — **CONFIRMED (code)**
No pass adapter receives a glossary client, canon repo, KG client, or motif-binding repo. Only
pass 1 gets a live data source (`MotifRetriever`). `run_cast` proposes characters from
`premise + genre_tags` **only** — it does not receive the existing cast, so the compiler
**re-invents** the book's characters; the mismatch is patched afterwards by name-matching in
`merge_existing_into_spec` plus a placeholder-injection heuristic. Grounding lives at *propose*
(`gather_existing_state`, hard-capped at 1500 tokens), not at the passes that make the structural
decisions.

---

## 3 · Tool inventory vs PlanForge compile

composition-service MCP surface: **63 advertised**, **51 `visibility="legacy"`** (hidden, superseded
by the unified `*_edit` enum-dispatch tools). Categorising the 63 by relationship to compile:

| Category | N | Tools |
|---|---|---|
| **Drive the compile** | **13** | `plan_propose_spec`, `plan_validate`, `plan_compile`, `plan_run_pass`, `plan_pass_status`, `plan_review_checkpoint`, `plan_self_check`, `plan_apply_revision`, `plan_interpret_feedback`, `plan_handoff_autofix` (10 at/pre-compile) + `plan_link`, `plan_bootstrap_propose`, `plan_bootstrap_apply` (3 post-compile materialize) |
| **Feed authored data compile actually reads** | **7** | `composition_arc_edit`, `composition_arc_apply`, `composition_decompile_arcs`, `composition_outline_node_edit` (→ propose grounding via `gather_existing_state`); `composition_motif_edit`, `composition_motif_adopt`, `composition_motif_mine` (→ pass 1 `MotifRetriever`) |
| Reads / diagnostics | 25 | `*_get`, `*_list`, `*_search`, `diagnostics`, `package_tree`, `find_references`, `arc_suggest`, `arc_import_analyze`, `arc_template_drift`, … |
| **Write authored craft data compile + all 7 passes structurally cannot read** | **13** | `composition_canon_rule_edit`, `composition_entity_override_edit`, `composition_motif_bind_edit`, `composition_motif_link_edit`, `composition_scene_link_edit`, `composition_reference_update`, `composition_structure_template_edit`, `composition_arc_template_edit`, `composition_arc_extract_template`, `composition_conformance_run`, `composition_create_derivative`, `composition_derivative_edit`, `composition_motif_suggest_for_chapter` |
| Drafting / infra | 5 | `composition_generate`, `composition_authoring_run_manage`, `composition_authoring_run_review`, `composition_create_work`, `composition_switch_active_work` |

**⇒ ~20 of 63 touch the compile. 13 write authored content wired to nothing upstream of it.**

**Important nuance — those 13 are NOT dead code.** `generate_chapter`
(`routers/engine.py:927`) pulls glossary, knowledge/KG, canon rules, motifs + motif applications,
scene links, narrative threads, grounding pins, style/voice profiles, references and derivative
overrides through `pack()`. They are **drafting fuel wired to the wrong stage** — rich at draft
time, absent at plan time.

---

## 4 · Answer to "is it correct, and is it fuel?"

- **Drafting: yes.** The 10-chapter / ~10.6k-word arc came out canon-grounded because `pack()` is
  genuinely well-fed. Tools that write canon/glossary/motif/KG data **are** real fuel for prose.
- **Planning: no.** The compiler decides structure with `premise + genre_tags + chapter titles`.
  Authored canon does not constrain it (F7, F8).
- **Correctness of what IS wired:** high — pointer-resolved pass inputs, fingerprint staling,
  degrade-safe *absent ≠ zero*, blocking checkpoints placed exactly where the human is the only
  oracle. The engineering discipline is not the problem.
- **The binding constraint on quality today** is that the two human review gates are the weakest
  links: `beats` shows and edits nothing (F1); `cast` hides characterisation (F2). The loop runs,
  but the author cannot steer it.

---

## 5 · Follow-on track requested by the human (2026-07-26)

> *"the chapter is wrong content in somewhere — the FE should have ability to send error blocks, so
> the co-writer can read and suggest the fix based on user instruction and KG/glossary and more."*

**Error-block reporting**: from the reading/editing surface the author marks a block (or range) of
drafted prose as wrong, optionally with an instruction ("she should not know this yet"). That block
+ its provenance travels to the co-writer, which reads it **together with KG / glossary / canon
rules / scene plan** and proposes a concrete fix as a confirm-gated edit.

Scoped as **Phase C** below — designed after the atom-edit foundation lands, because it reuses the
same "author marks a wrong artifact → agent revises it" seam.

---

## 6 · Open questions for the human (CLARIFY)

- **Q1** — For "full atom edit", is the target all **6** artifact kinds in the GUI, or the 2 blocking
  ones done properly first and the advisory 4 as read-only-with-agent-edit?
- **Q2** — Error blocks: does the author mark blocks in the **Draft Review** panel (authoring-run
  units), the **chapter editor** (persisted prose), or both?
- **Q3** — Should F6/F7/F8 (feed real beats + canon + existing cast into the passes) be **in this
  track** or a separate planning-quality track? It is the largest quality lever found, and it is
  structural.

---

## 7 · Evidence index

| Claim | Where verified |
|---|---|
| Real `beat_plan` / `cast_plan` keys | live `psql` on `loreweave_composition.plan_artifact` |
| Engine-produced cast field set | live per-artifact `jsonb_object_keys` query |
| `run_beats` / `run_cast` output shape | `app/services/plan_pass_adapters.py:172,138` |
| FE consumer keys | `PassArtifactEditor.tsx:25`, `PassArtifactView.tsx:41` |
| Editable kinds | `CheckpointReview.tsx:20` |
| Merge semantics | `plan_forge_service.py:83-100` |
| `ctx.beats` never populated | `plan_pass_adapters.py:79`, `compile.py` package literal |
| Pass context surface | `plan_pass_adapters.py:42-87` |
| Advertised vs legacy counts | scripted parse of `app/mcp/server.py` tool decorators |
| Drafting grounding set | `app/routers/engine.py:927-1010` |
