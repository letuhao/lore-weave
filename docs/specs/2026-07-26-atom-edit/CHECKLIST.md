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
- [ ] **A2** Open the Pass Rail in the real UI at the `beats` checkpoint.
      Evidence: screenshot/snapshot showing *"No beats in this plan yet."* against a run that
      demonstrably HAS `chapters` + `tension_curve` in the DB. ← **F1 live proof**
- [ ] **A3** Same for `cast` — confirm `archetype`/`summary` are not rendered. ← **F2 live proof**
- [ ] **A4** Agent baseline: ask the co-writer to edit the `cast` atom via
      `plan_review_checkpoint(edits=…)`. Record whether it can, and what the resulting artifact
      looks like in the DB. ← **F5, the untested path**

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
- [ ] **B4** **Machine-checked contract** for pass-artifact shapes across the BE↔FE seam, so this
      class of drift reds in CI. (Mirrors `contracts/frontend-tools.contract.json`; that file does
      not cover artifacts today.)
- [ ] **B5** Extend GUI editing to the remaining kinds — `motif_plan`, `world_plan`,
      `char_arc_plan`, `scene_plan` (**pending Q1**).
- [ ] **B6** Give every list-bearing kind wholesale-replace semantics so the agent can **delete**
      a scene/motif/world entity, not only add (F5 caveat).
- [ ] **B7** Re-verify: full composition unit suite + `plan-forge`/`studio-panels` FE suites, tsc.

## Phase C — real-run proof (the gate that actually matters)

- [ ] **C1** GUI: edit a `beats` atom in a **real browser**. *(Not yet — FE is unit-proven only;
      the browser pass is still owed.)*
- [ ] **C2** GUI: edit a `cast` atom incl. a deletion in a real browser. *(Same.)*
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
- [ ] **C4** Re-run `scenes` after an edit and confirm the edit **changed the output** (an edit that
      stales but does not influence would be F1 all over again). **Still owed.**

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
- [ ] **E8** FE: surface the structure picker + show `structure.name`/`source` at the beats
      checkpoint. Currently the author cannot see or change the structure in the GUI.

## Phase F — atom inventory matrix (scopes the rest of Phase B, per Q2)

- [ ] **F1** Enumerate every atom type across composition / book / glossary / knowledge.
- [ ] **F2** For each: MCP tool? FE edit surface? actually wired? real-run proven?
- [ ] **F3** Rank the gaps; fold the "built but never wired" ones into Phase B.
      *(`structure_template` is already a confirmed member of this class.)*

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
