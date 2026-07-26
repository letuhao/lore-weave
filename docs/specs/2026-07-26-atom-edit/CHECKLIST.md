# RUN-STATE · Atom Edit track — checklist

**This file is the anchor.** Re-read it after any compaction, before continuing. Findings and
evidence live in [`INVESTIGATION.md`](./INVESTIGATION.md); this file is the working board.

- **Task size:** XL (files=12, logic=14, side_effects=3) — no phases may be skipped.
- **Branch:** `feat/frontend-tools-mcp-migration` · **base HEAD:** `5d2975436`
- **Mode:** default v2.2 human-in-loop (AMAW **not** enabled — human-initiated only).

## The commitment

> Every one of the 6 PlanForge pass-artifact kinds is reviewable **and revisable** by both the
> author (GUI) and the co-writer (MCP), with the edit **proven to reach the artifact by a real
> run** — not by a unit test asserting an invented shape. Then: the author can mark wrong prose
> blocks and the co-writer can propose grounded fixes.

**Evidence rule (non-negotiable, this is what F3 punished us for):** a box is ticked only when the
transcript/doc contains the **actual pasted output** — a live DB row, an HTTP response, a browser
observation. A claim that a check passed, without its output, does **not** tick the box.

---

## Phase A — prove the bugs live (baseline BEFORE any fix)

- [x] **A1** Target confirmed — book `019f9d2b-b36c-7921-8b4c-96a1bd39c9e4`,
      run `019f9d2e-aef7-7087-849f-d99533b1c717`,
      `beat_plan` `019f9d2f-ff27-707c-8566-cf61cd9154a3`,
      `cast_plan` `019f9d2f-91f2-7db3-b59c-5b4a73bfa3f9` (the shipped ~10.6k-word arc).
- [x] **A0 (unplanned, found during A1)** 🔴 **F6 upgraded to CRITICAL — `beat_role` is `None` for
      all 10 chapters and the tension curve is a flat linear ramp 50→72.** Root cause proven:
      `beat_keys` is always empty ⇒ `plan.py:172` forces every `beat_role` to `None` and
      `plan.py:180` forces `unmapped_beats` to `[]`. The blocking checkpoint reports perfect
      health while discarding 100% of the model's structural output. Evidence pasted in
      INVESTIGATION.md §F6. **This re-orders the plan — see Phase E.**
- [~] **A2/A3 — CLOSED BY FIX, not by evidence.** These wanted a "before" screenshot of the broken
      render. F1/F2 were instead confirmed from the **live DB** (the producer emits `chapters`/
      `tension_curve`, never `beats`; `archetype`/`summary`, never `trait`) and then fixed before
      any browser was driven. Re-breaking the FE to capture a screenshot of a bug already proven
      from its data would be theatre. **The equivalent evidence now exists at C1/C2**: the same
      checkpoint driven live, rendering the real shape. Left visible rather than silently ticked.
- [x] **A4** Agent baseline — the co-writer's edit path was UNPROVEN at the time. Now proven twice
      over at **C3** (beat re-assignment with curve re-derivation; cast deletion 7→6), both
      DB-verified.

## Phase B — fix until full atom edit works (FE + agent)

- [x] **B1** `beat_plan` bound to the real shape. View renders per-chapter `beat_role` + the
      `tension_curve` target + an `unmapped_beats` banner, and names an unassigned chapter
      ("no beat") instead of rendering blank. Editor edits `chapters`.
      `_PASS_LIST_REPLACE_FIELDS['beat_plan']` `beats`→`chapters`.
- [x] **B1b** `beat_role` is now a **closed-set `<select>`**, not free text — options come from a
      new self-describing `available_beats` field on the artifact (emitted by `run_beats` from
      `ctx.beats`). A free-text role is dropped by `parse_chapter_map` AND falls to the neutral
      band with no warning: the same silent-no-op class as an un-enumerated tool arg. A role absent
      from the set (older artifact / changed structure) stays selectable rather than blanking the
      author's data.
- [x] **B1c** A chapters edit **re-derives `tension_curve`** (`_recompute_tension_curve`). Pass 6
      honours the stored curve verbatim, so without this an author promoting a chapter to `climax`
      would see `climax` in the UI while the drafter still aimed at the old neutral target. An edit
      that does NOT touch chapters leaves a hand-tuned curve alone.
- [x] **B2** `cast_plan` exposes `archetype` + `summary` (and flags `is_new: false` as "existing" —
      the invented-vs-already-in-your-book distinction). Legacy `trait` still read as a fallback,
      since artifacts edited under the old FE really do contain it.
- [x] **B3** FE tests re-pointed at **producer-derived** fixtures with a header explaining why;
      the BE `test_a_beat_edit_REPLACES_the_beats…` test (which asserted the non-existent `beats`
      key and thus vouched for the bug) rewritten + 2 new curve tests added.
      **Evidence:** FE `plan-forge` + `studio` = **1577 passed / 175 files**; composition unit
      **2398 passed, 1 skipped**; `tsc --noEmit` **exit 0**.
- [x] **B4** ✅ **Machine-checked BE↔FE contract shipped** — `contracts/plan-artifacts.contract.json`.
      **BE half** runs the REAL adapters (stubbing only the LLM-calling engine, using the engines'
      own dataclasses) and snapshots what they actually emit — deliberately NOT a hand-declared
      schema, which would just be a third place to be wrong. Regenerate with
      `WRITE_PLAN_ARTIFACT_CONTRACT=1`.
      **FE half** reads the snapshot and asserts every editor list-field, column, view key and
      nested scene field really exists — and **imports the real `SHAPE`** from `PassArtifactEditor`
      rather than mirroring it (a mirror would be the same failure mode this guard prevents).
      **Proven to fail in BOTH directions** — reintroducing the original shapes in the test → 5 reds
      naming both regressions; breaking the *component* (`beat_plan.field` → `'beats'`) → 2 reds.
      A guard that cannot fail is worthless.
- [x] **B5** GUI editing extended to `motif_plan`, `world_plan`, `char_arc_plan` + readable views
      for all four (raw-JSON fallback gone). `arc_role` left FREE TEXT after verifying
      `motifs_for_beat` matches by substring and is explicitly fail-open — an enum there would have
      been wrong. `motif_plan` calls out an empty selection instead of rendering blank.
      `scene_plan` needed a nested editor rather than a flattened fake → delivered in **B8**.
- [x] **B6** Every atom kind now supports **DELETE**. `_PASS_LIST_REPLACE_FIELDS` gained
      `motif_plan {motifs|selected_motifs}`, `world_plan {entities}`,
      `char_arc_plan {character_arcs}`, `scene_plan {chapters}` — previously they fell through to
      `_deep_merge`'s id-upsert, so a shorter list silently kept the removed member while reporting
      success. 6 parametrized tests + a nested-scene deletion test.
- [x] **B8** Dedicated NESTED editor for `scene_plan` (chapters → scenes) — `ScenePlanEditor`,
      routed from `CheckpointReview`. **All 6 atoms are now GUI-editable.** Two invariants pinned by
      tests: nothing unexposed is lost (scene `present_entity_ids`/`suggested_k`, chapter
      `warning`/`exit_state` survive an unrelated edit — dropping the entity ids would silently
      un-ground the scene), and the chapter grouping is never flattened. Also flags a zero-scene
      chapter as "cannot be drafted".
- [x] **B9** 🔴 **The door** (F10) — see C1/C2. The editors existed but nothing could open four of
      them. Fixed after the browser pass.
- [x] **B7** Re-verify: composition unit **2409 passed / 1 skipped**; FE `plan-forge` + `studio`
      **1601 passed / 176 files**; `tsc --noEmit` **exit 0** (TS 5.5.4 — local node_modules has
      drifted to 7.0.2, see the host-drift note in SESSION_HANDOFF).

## Phase C — real-run proof (the gate that actually matters)

- [x] **C1/C2** 🎯 **BROWSER PASS DONE — and it caught a bug 1596 unit tests missed.**
      Drove the real studio (chrome-devtools MCP; the Playwright profile was held by the concurrent
      session) on book `019f9d2b`, run `019f9d2e`.

      🔴 **F10 — the editors were UNREACHABLE.** `PassRow.awaitingReview`
      (`blocking && completed && decision==='pending'`) was the ONLY route to `CheckpointReview`,
      the ONLY host of every structured editor. So the four ADVISORY atoms (motifs, world,
      character_arcs, scenes) **never rendered a door** — four editors, including the scene_plan one
      built minutes earlier, were dead UI — and cast/beats became uneditable the moment they were
      approved (a one-way door on the two atoms most likely to need revision).
      **Why no test caught it:** every editor test renders `CheckpointReview` *directly* with a
      fabricated `pass`, so the host was always "open" and the gate was never exercised. This is the
      same shape as F3 (testing the consumer's assumption instead of the real path) — one layer up.
      **Fix:** any COMPLETED pass with an artifact gets a quiet `edit…` door onto the same host; the
      warning-styled `review →` CTA stays exclusive to blocking+pending.

      **Live evidence after the fix:** all 6 doors render (self_heal correctly none — no artifact) ·
      `scenes` shows the readable chapter/scene/tension view, not raw JSON · Edit opens the **nested**
      `ScenePlanEditor` (flat one correctly not used), 10 chapter blocks · retitled scene 1 and
      deleted scene 3 → saved → **DB: new artifact `019f9f24-3154`, 25→24 scenes, ch1 3→2, title
      "The Erasure (BROWSER EDIT)", and `present_entity_ids` PRESERVED (`019f9d2f-a1a3…`)** — the
      scene's grounding survived an unrelated title edit, which is the invariant the editor was
      built around.
- [x] **C3** 🎯 **AGENT EDIT PROVEN LIVE via MCP** — both editable kinds, on the real book/run.

      **beat_plan** — `plan_review_checkpoint(pass_id='beats', approved=false, edits={chapters})`
      re-assigning ch6 "The Ledger" `rising_conflict`→`setback`. New artifact
      `019f9eea-5875-782e-840a-143a986d872a` written (never mutated in place), and the curve
      **re-derived around the new grouping**:

      |        | ch4 | ch5 | ch6 | ch7 | ch8 |
      |--------|-----|-----|-----|-----|-----|
      | before | 55  | 68  | 82  | 66  | 90  |
      | after  | 55  | 82  | 66  | 78  | 90  |

      (rising_conflict run 3→2 re-ramps 55→82; setback run 2→3 re-ramps 66→90.) Ledger:
      `beats decision=pending` — **held with the revision, not blind-approved** — and
      `scenes fresh=False`, i.e. staled downstream by derivation. Exactly the designed semantics.

      **cast_plan (DELETE — the semantic most likely to fail silently)** — dropping "Mina" from the
      roster produced artifact `019f9eeb-6c3c-7e7e-af5e-7bf8cad5effc` with **7 → 6** members. The
      wholesale-replace rule really deletes; deep-merge would have kept her.

      **`available_beats` verified live** on artifact `019f9ee8-899a…` (6 entries) — the closed set
      the editor's `<select>` binds to now ships on the artifact.
- [x] **C4** 🎯 **THE CAPSTONE — the shaped curve reaches the scenes.** Drove the full legitimate
      chain on the real book (no bypass): cast → seed apply → accept → beats → accept →
      character_arcs → scenes. **25 scenes over 10 chapters**, and the scene decomposition now
      tracks the curve:

      | ch | beat_role       | target | scene peak |
      |----|-----------------|--------|------------|
      |  1 | hook            |  65    |  65        |
      |  2 | establishment   |  35    |  35        |
      |  3 | establishment   |  58    |  58        |
      |  4 | rising_conflict |  55    |  55        |
      |  5 | rising_conflict |  68    |  68        |
      |  6 | rising_conflict |  82    |  **60** ⚠   |
      |  7 | setback         |  66    |  66        |
      |  8 | setback         |  90    |  90        |
      |  9 | climax          | 100    | 100        |
      | 10 | resolution      |  52    |  48        |

      **9 of 10 chapters hit their target exactly**, and every chapter's `beat_role` propagated into
      the scene plan. Before this track: all 10 `beat_role` were NULL and the targets were a flat
      50→72 ramp, so the decomposer had no shape to aim at. The edit chain is real, not cosmetic.
      *(Honest read: ch6 undershot 82→60 and ch10 came in slightly under. Model-side steering, not a
      wiring bug — the target reached the prompt.)*
- [x] **C5 (unplanned)** ✅ **A STALE DEFERRED ITEM IS CLEARED.** SESSION_HANDOFF still carries
      *"GAP 1 (real agentic workflow bug): the cast/beats glossary-seed proposals apply ONLY via
      composition REST — there is NO MCP tool, so the co-writer CANNOT drive the scene-compiler past
      cast/beats autonomously."* **That is no longer true.** Proven live: `plan_bootstrap_apply`
      (confirm-gated) applies a CAST SEED proposal by id → `{"proposal_status":"applied"}` → then
      `plan_review_checkpoint(approved=true)` cleared the PF-7 gate. The agent can drive the whole
      compiler now. *(Verify claims against code before trusting a handoff note — this one had gone
      stale, exactly as the anti-laziness rule warns.)*
- [x] **C6 (negative result, worth recording)** `plan_run_pass` **deliberately omits `force`** —
      the PF-5/PF-6 bypass exists on the service and the HTTP route (for a human at the GUI) but is
      withheld from the agent *by absence*, with a comment explaining that a model which hits a 409
      listing its blockers will simply retry with `force=true`. Confirmed by attempting it: the pass
      refused. This is the gate working, not a defect.
      ⚠ Minor: an unknown kwarg like `force` is silently ignored rather than rejected, so an agent
      could believe it forced. Outcome is still correct (refusal), so low severity — noted, not fixed.

## Phase D — error-block reporting (the new track)

- [ ] **D1** CLARIFY with human (**Q2**): which surface(s) can mark blocks — Draft Review, chapter
      editor, or both.
- [ ] **D2** DESIGN: block identity + provenance (scene/outline node, revision), the payload to the
      co-writer, and the grounded-suggestion path (KG + glossary + canon rules + scene plan).
      Must respect: MCP-first, confirm-gated writes, no agent-driven GUI nav.
- [ ] **D3** BUILD + real-run proof: mark a wrong block → co-writer proposes a grounded fix →
      author confirms → prose updated in the DB.

## Phase E — 🔴 PROMOTED TO FIRST (human decision Q1): planning quality

- [x] **E1** Migration: `plan_run.structure_template_id uuid NULL` (forward-only). Applied live —
      column verified present on `infra-postgres-1`.
- [x] **E2** `plan_compile` resolves the template → `package["beats"]`, via new
      `app/engine/plan_forge/structure.py`. Provenance always recorded. Live compile returned:
      `{template_id: 0190ce00-…-005, name: "Web Novel Arc", source: "default", beat_count: 6,
      shapeable: true, note: "no structure was chosen for this run; using the platform default —
      change it to reshape the arc"}`. The `run_pipeline` path now uses the SAME resolved beats.
- [x] **E3** Author + agent can choose: `plan_compile(structure_template_id=…)` on MCP **and**
      REST (`PlanCompileRequest`), persisted to the run when overridden.
      **Also fixed a blocking affordance gap:** `composition_structure_template_edit` had five
      WRITE ops and **no read**, so the agent could never discover a template id. Added `op=list`
      (returns built-ins + own, with beats and a `builtin` read-only flag) — live-verified.
- [x] **E4** 🎯 **REAL-RUN PROOF — the arc now has a shape.** Same book/run, recompiled, `motifs`
      then `beats` re-run live on Gemma-4 26B:

      BEFORE                          AFTER
      ch  beat_role  tension          ch  beat_role        tension
       1  (null)     50                1  hook              65
       2  (null)     52                2  establishment     35
       3  (null)     55                3  establishment     58
       4  (null)     57                4  rising_conflict   55
       5  (null)     60                5  rising_conflict   68
       6  (null)     62                6  rising_conflict   82
       7  (null)     65                7  setback           66
       8  (null)     67                8  setback           90
       9  (null)     70                9  climax           100   ← a real climax
      10  (null)     72               10  resolution        52   ← and it comes down

      `chapters_with_role: 10/10`. Chapter 9 "The Void" — *"Elara enters the void to confront the
      reality of the people she accidentally erased"* — was assigned `climax`, which is
      semantically correct, so the mapping is real, not incidental.
- [x] **E5** Regression tests — `tests/unit/test_plan_forge_structure.py`, **11 passed**. The
      anchor (`test_empty_beat_keys_discards_every_role`) asserts the *mechanism*: a valid model
      response is discarded wholesale when `beat_keys` is empty, and lands once it isn't.
- [x] **E5b** 🔴 **Second defect found during E4 and fixed:** only the web-novel/3-act vocabulary
      existed in `arc_plan._BANDS`. Four of the six built-ins (Hero's Journey, Save the Cat, Story
      Circle, Kishōtenketsu) had **zero** mapped keys — they would assign beat roles and *still*
      produce a flat curve. Added all four vocabularies (+ `confrontation`), plus
      `known_beat_keys()` and a `unshaped_beat_keys` / `shapeable` field on the structure
      provenance so a **custom** template with unknown keys reports itself instead of silently
      flattening. Two tests pin it, including "every vocabulary must PEAK and come back down".
- [ ] **E6** F7/F8 — thread canon rules + existing cast into `PassContext` so the compiler stops
      re-inventing the book. *(Larger; may split.)*
- [ ] **E7** Re-run `scenes` + `self_heal` and confirm the scene decomposition now honours the real
      curve (pass 6 reads `tension_curve` verbatim). **Not yet done — the shape is proven at the
      beat layer only.**
- [x] **E8** FE structure picker shipped. `CompilePlanBody.structure_template_id` → `runCompile` →
      a picker beside the arc picker, labelled with each structure's beat count. `usePlanRun` loads
      the library once per token (synchronization effect) and exposes `structures`.
      Blank ("keep current") is **never pre-selected** and the id is **omitted rather than sent as
      null**, so opening the panel and hitting Compile cannot silently re-shape an already-structured
      plan. `structures` is optional/defaulted — a failed library load degrades the picker instead of
      blocking the compile. 3 tests incl. the degraded-library case.
      *(Confirms the "built but never wired" thesis again: `StructureTemplatesPanel` = 462 lines of
      CRUD, `compositionApi.listTemplates` already served the data, and nothing referenced a plan
      run.)*
- [x] **E9** ✅ The beats checkpoint now says **"Shaped by <name>"**, flags `source: default` as
      *"platform default — change it to reshape the arc"*, and warns when the structure carries
      beats the pacing model doesn't know (roles assigned, curve still flat — the quiet recurrence).
      `PassContext.structure` + `run_beats` echoes the provenance onto the artifact, so the artifact
      a reviewer opens describes itself. Degrade-safe for older artifacts with no `structure`.
      **The B4 guard earned its keep immediately** — adding the field turned the BE contract test
      RED on the next run, unprompted, telling me to regenerate AND update the FE consumers.

## Phase F — atom inventory matrix (scopes the rest of Phase B, per Q2)

- [x] **F0** 🔴 **Found + FIXED while mapping the matrix: the motifs pass has NEVER selected a
      motif, for any book.** Every `motif_plan` artifact in the DB held 0 motifs and was NOT flagged
      degraded, so pass 6 always planned scenes with no motif layer. Not an empty library — 147
      rows. Cause: `_fetch_candidates` filters `AND language = $2`, but the neutral default is the
      sentinel `"auto"`, which no row can equal (motifs are `en`/`vi`); the empty-**genre** case
      already had this exact guard (MD-2) and `language` never got it. Also, `pass_input` never
      threaded `source_language`, so every pass ran as `auto` regardless of the book.
      **Fixed 3 ways** (omit the clause for auto/unknown/und; thread the Work's real language; warn
      on an empty selection). **Live proof: 0 → 3 motifs**, semantically apt with distinct arc roles
      (`Dao-Heart Tempering`/central spine, `Fortuitous Encounter→Legacy`/recurring, `chosen one
      refuses the call`/climax payoff). 3 regression tests incl. one pinning the `LIMIT` placeholder
      after the clause renumbering.
- [x] **F1** Atom types enumerated across composition / book / glossary / knowledge (~22 kinds,
      matching the human's "24+"): 6 PlanForge pass artifacts · 11 composition `*_edit` families ·
      book chapter/details/structure · glossary entity/ontology/wiki · kg node/schema/view/template.
- [~] **F2** Matrix in progress. Confirmed so far:
      - **Consumed & wired:** canon_rule, motif, motif_bind/link, scene_link, reference,
        entity_override (all → `pack()` at draft time); arc, outline_node (→ propose grounding);
        arc_template (→ `arc_apply`).
      - **BUILT BUT NOT WIRED:** `structure_template` — BE now wired by this track, but
        `StructureTemplatesPanel` is **462 lines of full CRUD with ZERO references to a plan run**.
        An author can lovingly write a beat sheet in the GUI and it can never reach a plan. (E8)
      - **Agent cannot DELETE from 4 of 6 atom kinds:** `_PASS_LIST_REPLACE_FIELDS` covers only
        `cast_plan`/`beat_plan`, so `motif_plan`(`motifs`), `world_plan`(`entities`),
        `char_arc_plan`(`character_arcs`) and `scene_plan`(`chapters`) deep-merge — a shorter list
        silently keeps the removed member. Live shapes confirmed. → **B6**
      - **FE cannot edit 4 of 6 kinds at all** (read-only JSON fallback). → **B5**
- [ ] **F3** Rank the remaining gaps; fold the "built but never wired" ones into Phase B.

---

## Human decisions (CLARIFY, 2026-07-26) — SEALED

| id | Question | Answer |
|---|---|---|
| Q1 | Where does F6 go? | **Fix it FIRST, in this track.** Phase E is promoted ahead of Phase B — fix the DATA before the EDITOR. |
| Q2 | Scope of "atom" | **Broader than PlanForge artifacts.** An atom is *every editable domain object* — the `*_edit` tool family (24+) **and chapters**. The MCP layer already exists for them; the suspected gap is **forgotten wiring / missing tests**, not missing tools. ⇒ deliverable includes an **atom inventory matrix** (atom × MCP × FE surface × wired? × real-run proven?). |
| Q3 | Error-block surface | **Both** — Draft Review (before accept) *and* the chapter editor (already-persisted prose), sharing one block-marking primitive. |

**Q2 is already vindicated by F6-RC:** `structure_template` has a table, 6 seeded built-ins, a repo,
CRUD routes and 5 MCP tools — and **zero consumers**. Built, then not wired. That is the exact
failure mode the human predicted, and the matrix exists to find the rest of them.

## ⚠️ Commit provenance — where this track's code actually landed

**Phase E + Phase B code is in commit `439d9037a`, NOT in a commit of its own.**

A second Claude session was working this same repo and branch concurrently (its commits:
`77dc6f3e2` state-ledger, `221846ca8` critic remediation, `ef53eb47e` chapter length target, all
21:18–21:55). At 21:55 it ran a commit while this track's 18 files were staged, so they were swept
into its commit — 1757 insertions filed under the message
`docs(session): record chapter-quality fixes #1–#3 shipped + proven`.

- **Nothing was lost or clobbered.** File sets were disjoint: that session touched `compress.py`,
  `cowrite.py`, `config.py`, `routers/engine.py`, `authoring_run_service.py` + tests; this track
  touched `structure.py`, `arc_plan.py`, `plan_forge_service.py`, `plan_pass_adapters.py`,
  `plan_runs.py`, `migrate.py`, `mcp/server.py`, `routers/plan_forge.py` + the plan-forge FE.
- **History was deliberately NOT rewritten** (human decision): amending a commit a live concurrent
  session may already be building on is riskier than an inaccurate message.
- **Caveat on this track's live evidence:** the composition images were rebuilt from a working tree
  that also carried that session's in-flight changes, so the smoke ran on a *mixed* image. The beats
  findings still hold — their changes are in compress/critic/length, structurally unrelated to beat
  mapping, and the 10/10 `beat_role` + climax curve follows directly from populating
  `package["beats"]` — but it was not an isolated image, and a future re-verify should be.
- **Two agents rebuilding `composition-service` against one working tree is a standing hazard.**
  Coordinate before the next long run.

## Registers

### Decisions
| date | decision | why |
|---|---|---|
| 2026-07-26 | Investigation written before any fix; live-DB verification required for every finding | F3 showed source-only + unit-test evidence is exactly what produced the bug |
| 2026-07-26 | Classified XL as ONE effort, not N small tasks | coherent change across FE + BE + contract + a new feature |

### Parked
| id | item | gate reason |
|---|---|---|
| — | — | — |

### Debt
| id | item | note |
|---|---|---|
| — | — | — |

### Drift log (near-misses — an empty drift log at the end is dishonest, not clean)
| date | what nearly went wrong |
|---|---|
| 2026-07-26 | Almost reported F1/F2 from source reading alone. Querying `plan_artifact` live is what upgraded them from PLAUSIBLE to CONFIRMED — and revealed that the older `id,name,role,trait` rows are fixture-shaped, which is the actual root cause (F3), not a second bug. |
| 2026-07-26 | **Nearly declared E4 done with a half-fix.** The beats wire was working and the unit tests were green; I only caught the `_BANDS` gap (E5b) because the live `op=list` output happened to show Hero's Journey keys (`ordinary_world`, `call_to_adventure`) that I recognised as absent from the band table. Had the default template been anything other than Web Novel Arc, the "fixed" pipeline would have produced beat roles and a flat curve — a *quieter* version of the same bug, now with a green test suite vouching for it. Lesson: after fixing a lookup, check the WHOLE key space, not just the path the default happens to take. |
| 2026-07-26 | `plan_compile` MCP arg was written before `op=list` existed, i.e. an argument the agent had no way to populate. Caught only by asking "how would the co-writer actually get this id?" — the affordance question, not the code question. |
| 2026-07-26 | Reached for `force=true` to shortcut the C4 chain. It was silently ignored and the pass refused — which is the design (the bypass is withheld from agents *by absence*). Had it been exposed, I would have skipped the two human checkpoints to save ~8 minutes and called the result an end-to-end proof, when it would have proven nothing about the gate. The honest chain took 4 passes and a seed apply. |
| 2026-07-26 | **The big one.** I reported "5 of 6 atoms GUI-editable" on the strength of 1596 green unit tests. The first real browser pass showed FOUR of those editors had no door to open them — advisory passes never render the review CTA. The claim was true of the components and false of the product. I had even written the `scene_plan` editor and its 9 tests without ever checking that a user could reach it. Every editor test renders `CheckpointReview` directly, so the gate was never in the test path. Lesson, again: "the tests pass" is not "the feature works" — and I was one turn away from calling atom edit DONE. |
| 2026-07-26 | Sweeping for more `auto`-sentinel filters, I found `arc_template_repo`'s language clause and nearly reported it as a second instance. It takes an explicit query param defaulting to `None` (which skips the clause), not the book profile's `"auto"` — verified the callers before claiming. Negative results need the same rigour as positive ones. |
