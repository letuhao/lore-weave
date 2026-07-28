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

- [x] **D1** CLARIFY — sealed at **Q3**: **both** surfaces (Draft Review pre-accept + the chapter
      editor), sharing one block-marking primitive.
- [x] **D2** ✅ **DESIGN WRITTEN — [`DESIGN-error-blocks.md`](./DESIGN-error-blocks.md).**
      **The reframe that shrinks it: an error block is a human-authored self-heal `Finding`.**
      `engine/self_heal.py` already runs judge → locate → satellite-edit → splice → review; the
      author replaces the *judge*, and steps 2–5 are reused verbatim. So Phase D is ~70% wiring,
      not a new feature.
      Verified reusable: `EditProposal`/`SelfHealProposal` shape · `applySelfHealEdits`
      drift-guarded splice · `locate_span` fuzzy re-anchor · `build_selection_messages(guide=,
      grounding=)` — **the author-instruction and grounding slots already exist** and the satellite
      edit is already grounded (`self_heal.py:485`) · `propose_edit`→ProposeEditCard→
      `applyProposedEdit` (the whole human-gated apply path) · TipTap + `SelectionToolbar` +
      decoration layers.
      **Four real gaps:** (1) nothing persists a human finding — `GenerationCorrection` is the
      near-miss but is job-scoped, span-less, and H2-guarded, so it must NOT be overloaded;
      (2) `editorBridge` is write-only, so the co-writer cannot read the author's marks;
      (3) 🔴 **there is no MCP tool for prose self-heal at all** (`proposeSelfHeal` is REST-only;
      the `self_heal` in `mcp/server.py` is the unrelated PlanForge pass name) — another instance
      of this track's recurring "built, never wired for the agent" class; (4) no marking affordance.
      **Decisions:** one table `chapter_error_block` (per-book tenancy tier, discriminated
      `chapter_draft`|`draft_job` target because the compose preview is ephemeral and has no chapter
      identity) · `quote` is the anchor, offsets are a hint, `locate_span` re-anchors, a lost block
      **orphans visibly rather than vanishing** · accept migration re-anchors draft blocks onto the
      chapter · ground via **`pack()`** (real KG/glossary/canon), NOT self-heal's cast-only
      `render_canon` · **one** unified `composition_error_block_edit(op=…)` with `op="list"`
      shipped alongside the writes (the E3 affordance-gate lesson) · the fix path adds no new tool.
      Recorded limitations: `locate_span` degrades on CJK (whitespace tokenizer), and the
      code-point↔UTF-16 offset mismatch is pre-existing — inherit the guard, don't "fix" it here.
- [x] **D2b** ✅ **All four open questions CLEARED against code — and one was a design error.**
      **R1:** 🔴 the design's `owner_user_id` scope key was **WRONG**. Composition scopes by
      **`book_id`** (`-- tenancy scope key (25 M1/M2)`); `created_by` is an actor stamp
      **explicitly never filtered on** (PM-5). Identical on `canon_rule`/`narrative_thread`/
      `generation_correction`. Migration DDL rewritten to the house pattern (uuidv7, CHECK-enum
      closed sets, `version` OCC, `is_archived`, partial index).
      **R2:** `draft_version` is the OI-2 **OCC token** — monotonic, and `patchDraft` 409s on
      mismatch, so it doubles as the stale guard.
      **R3:** orphan on regenerate; `job_id REFERENCES generation_job ON DELETE CASCADE` is the
      house pattern (`generation_correction` precedent).
      **R4:** overlap/ordering already solved in `self_heal.py:474-513` — inherited, not re-derived.
      **R5 (new):** the editor's prose is a **ProseMirror JSONB doc** but self-heal offsets are
      **flat-text code points** over `tiptap_doc_to_text()` — two coordinate systems with no
      round-trip. Blocks store flat offsets + `quote`; the *apply* goes through the editor's own
      transaction.
- [x] **D2c** 🔴 **F11 — FOUND WHILE CLEARING R5: the shipped Polish apply silently corrupts the
      chapter.** `QualityHealPanel.healedTextToDoc` (:30) rebuilds the whole chapter as flat
      paragraphs; book-service stores a `json` body **verbatim** (`normalizeBodyToTiptap` passes it
      through, server.go:2613/2639). So an applied Polish drops **`_text` block snapshots** — read
      by full-text search (`search.go:117`), block extraction (`server.go:2968/3030/3560`,
      `migrate.go:1283`) via `x.elem->>'_text'` ⇒ **the chapter goes invisible to search and
      extraction** — plus heading nodes + `attrs.sceneId` (Scene Rail anchors) and every mark.
      The correct primitive **already exists and is used everywhere else**: `addTextSnapshots`
      (`lib/tiptap-utils.ts:18`), which `ManuscriptUnitProvider:277` calls with the comment
      *"REQUIRED before persist (chapter_blocks trigger)"*, and which the normal editor save uses
      (`TiptapEditor:173`). **Polish is the one path that skips it.** This track's signature bug
      class again — correct converter on one path, naive twin on another.
      **Design consequence (load-bearing):** an error-block fix MUST be a **surgical span
      replacement in the live document**, never a whole-doc text round-trip — which is exactly what
      the reused `propose_edit(replace_selection)` path does. Reusing it isn't just economical, it's
      **the only non-lossy option.**
      ⚠️ **NOT FIXED HERE** — `QualityHealPanel.tsx` is the concurrent session's quality surface.
      Logged with evidence; coordinate before touching. Error blocks don't depend on the fix, only
      on not repeating it.
- [x] **D2d** ✅ **DESIGN REVIEW (phase 3) — 12 edge cases swept and resolved, one section reversed.**
      🔴 **Reversal: §9's `propose_from_findings` refactor is WITHDRAWN.** Two independent reasons:
      (a) `self_heal.py` is the concurrent session's **most active file** (6 recent commits, one
      literally `fix(compose-quality)`) — refactoring it is the highest-conflict edit available, and
      **this corrects the "D3a–D3c are safe backend work" claim** made when the design was presented;
      (b) reading `self_heal.py:440-513`, the human path must SKIP nearly all of it — judge,
      `locate_span` (pre-located), **`_snap_to_sentence` (would silently widen the author's
      deliberate span!)**, verify-vote, re-ranker, dup-word merge, re-judge. What remains is ~25
      lines. ⇒ new `engine/error_block_heal.py` **composing** public primitives; **no existing engine
      file is touched.** Cheaper, lower-risk, and honest that the two paths differ.
      **Edge cases resolved (E1-E12):** 🔴 **E1 ambiguous re-anchor** — `locate_span` returns the
      FIRST match, so a drifted mark on the 3rd "Nàng gật đầu." lands the fix on the 1st (silently
      wrong prose) ⇒ nearest-to-stored-offset wrapper, tie ⇒ orphan, never guess · **E2** overlapping
      marks MERGE (self-heal's silent drop is unacceptable for human input) · 🔴 **E3** a missing
      `_text` changes the whole flattened string ⇒ **every offset shifts at once** (F11 creates
      exactly this) ⇒ new `source_fingerprint` column; mismatch ⇒ distrust offsets, re-anchor by
      quote · **E4** cap at the existing `SELECTION_MAX_CHARS` · **E5** partial-unique dedup index ·
      **E6** hand-fixed prose ⇒ orphan + ask, never auto-resolve · **E7** unanchorable quote ⇒
      reject, no silent no-op · **E8** capped list + true `open_count` · **E9** cross-DB orphan rows
      = tracked debt, not a blocker · **E10** marking needs **EDIT** grant · **E11** degraded
      grounding must be SAID ("fixed without canon grounding") · **E12** every skip reported.
      **Scope cuts:** `op="create"` (agent self-marking) cut as speculative; `op="list"` ships first.
      **Slices re-ordered so D3a/D3b/D3c touch ZERO contested files**, and **D3f (the live gate) now
      precedes D3e** — the feature is provable end-to-end on the editor surface alone, so the
      draft-arm accept-migration (the hardest piece, serving the less-used surface) is explicitly
      **optional and last**.
- [x] **D2e** 🔒 **DESIGN SEALED 2026-07-27.** Last pre-BUILD sweep closed three real gaps:
      (1) 🔴 **the FE↔BE REST surface had never been specified** — §8 detailed the *agent's* path
      thoroughly and left the browser's implicit, but the FE cannot call MCP. Routes now named
      (§8b). **Gateway work: none** — verified `gateway-setup.ts:354` proxies `/v1/composition` by
      prefix. `PATCH` carries `If-Match: version` (canon_rule precedent); the propose route reuses
      the existing `202+poll`/inline `_resolveJob` shape.
      (2) 🔴 **no slice taught the co-writer the tool exists** → new **D3g**. This track proved both
      failure directions: a skill naming a RETIRED tool causes discovery loops (19 refs fixed), and
      a tool **no skill names** is never reached for. Its proof is behavioural — the model calls it
      unprompted in a live chat — not textual.
      (3) **corrected a second over-confident claim**: D3a is *not* zero-conflict. Its DDL lands in
      `migrate.py`, which the concurrent session appended to hours ago (`9f9296c00`) and which was
      in the `439d9037a` sweep. Low severity, textual — but not "none".
      **Sealed:** 9 decisions, each verified against code (see the SEAL block in the design).
      **Left open deliberately:** F11 (the other session's bug — logged, coordination required),
      D3d/D3e file ownership, and the two recorded fail-safe limitations (CJK, offset units).
      **BUILD may begin at D3a.** D3a–D3c + D3g need no coordination; D3d/D3e do.
- [x] **F11 FIXED** (`b7f160397`) — human authorised clearing it during BUILD. `healedTextToDoc`
      now routes through `addTextSnapshots`. **Upgraded from inference to PROVEN port regression:**
      the legacy `ChapterEditorPage.handleApplyPolish` emits `_text` per block *deliberately*
      (its comment: *"Builds the same Tiptap paragraph shape book-service writes (a `_text`
      snapshot per block)"*) — the Studio port said it mirrored that conversion and dropped the
      field. Regression guard added to the existing apply-seam test and **proven to red against
      the pre-fix code** (`expected undefined to be defined`), green after. The `legacyParityContract`
      test could not have caught it: it proves a capability is PRESENT in the port, not that the
      port is behaviourally faithful. Residual documented in code — a flat-text rebuild can never
      restore headings/`sceneId`/marks, which is precisely why error blocks apply surgically.
      Verify: studio panels + PolishPanel **796 passed / 100 files**.
- [x] **D3a** ✅ **Migration + repo — LIVE-PROVEN on `infra-postgres-1`.**
      `chapter_error_block` (`_ERROR_BLOCK_SQL` in migrate.py) + `ErrorBlock` model +
      `ErrorBlocksRepo`. Scoping follows the canon_rule/narrative_thread house pattern, **not** the
      newer glossary_build_* one: `book_id` is the tenancy scope key, `created_by` is a
      never-filtered actor stamp, and `book_id` is **derived from `composition_work` inside the
      INSERT** so a row cannot land with a NULL book scope.
      **Live evidence — every constraint exercised against real Postgres, not asserted:**
      | # | probe | result |
      |---|---|---|
      | 1 | `chapter_draft` with no `chapter_id` | ❌ `chapter_error_block_target` |
      | 2 | `end_offset == start_offset` | ❌ `chapter_error_block_span` |
      | 3 | `kind='totally-made-up'` | ❌ `chapter_error_block_kind_check` |
      | 4 | well-formed row | ✅ `INSERT 0 1` |
      | 5 | **same span + same note again** | ❌ `uq_chapter_error_block_open` |
      | 6 | **same span, different note** | ✅ `INSERT 0 1` |
      | A | real project | ✅ derived `book_id=019f63d6-51f0-7acb-b03d-33cffd8f342e` |
      | B | unknown project | ✅ `INSERT 0 0` ⇒ repo raises; **NULL book scope is impossible** |
      (5)+(6) are exactly E5: the accidental twin dies, two *distinct* reasons on one passage live.
      **Repo shape:** `update` is a FINDING editor only — span, fingerprint, scope and status are
      **not** patchable (a PATCH that moved `start_offset` without `quote` would split the anchor
      triple and leave the block silently describing different prose); status moves only through
      the lifecycle helpers; `reanchor` rewrites offsets but **never** `quote`; delete is a
      soft-archive so the correction history survives. `migrate_job_blocks_to_chapter` carries an
      explicit ORDER-MATTERS comment — the re-targeted rows clear `job_id`, so the orphan sweep
      keys on it and by construction touches only the ones that did not locate.
      Tests: **17 new** (closed sets reject; span/status not patchable; `orphaned` counts as still
      wanting attention). Full composition suite **2547 passed / 336 skipped**.
- [x] **D3b** ✅ **`engine/error_block_heal.py` — and 🔴 the E1 bug fixed before it could ship.**
      Composes self-heal's public primitives; **modifies no existing engine file.** Skips judge/
      vote/verify/rerank (the author already decided — re-adjudicating would be the tool
      second-guessing its user) and critically skips **`_snap_to_sentence`**, which would have
      silently WIDENED a deliberate human selection.
      🔴 **E1:** `locate_span` returns the FIRST match. A mark on the 3rd *"She nodded."* would
      re-anchor to the 1st and the fix would edit a paragraph the author never complained about —
      **reporting success, undetectable downstream.** `locate_nearest` picks the occurrence nearest
      the stored offset; ambiguity tolerance is tied to `hint_trusted` (the fingerprint check), so a
      moved coordinate space + an ambiguous quote **orphans instead of guessing**, while a single
      candidate still anchors (one candidate is not a guess) and fuzz never outvotes an exact match.
      A test **pins `locate_span`'s first-match behaviour** — reusing a primitive means owning it.
      **Second find (latent, not live):** the Python `apply_self_heal_edits` has **no `before`
      guard**, though its JS "mirror" does and explains why. Checked the caller — `self_heal.py:796`
      splices against the same in-memory chapter, so **it is not exploitable there**. It *is*
      exploitable for any caller whose text can drift, which is exactly the error-block path (a
      human reviews between propose and apply), so `apply_block_edits` carries its own guard.
      Own `_chat` (not self-heal's private one): author-driven spend must not be stamped
      `extractor="self_heal"`. Every skip REPORTED with a reason; `grounded` reports a degraded pack.
      **33 tests**, incl. a stub model that captures the built prompt (a `guide=` that failed to
      thread would still produce a plausible edit — invisible in the output).
- [x] **D3c** ✅ **REST routes + the MCP tool — the feature is now reachable from both sides.**
      **7 REST routes** (`error_blocks.py`), gate mirrored from `canon.py`: E0 grant resolved
      BEFORE any repo call, **VIEW to read / EDIT to mark** (a mark is authoring input that drives
      a prose change), by-id routes resolve the block's own project and gate on ITS book, anti-oracle
      id-only bootstrap, `If-Match` → 412, duplicate → **409 not a silent success**, soft-archive +
      restore. Verified registered: all 7 paths listed off the live app.
      **`composition_error_block_edit(op=list|resolve|dismiss)`** — `op="list"` ships first as the
      affordance gate (the `composition_structure_template_edit` lesson: five writes, no read, so
      the agent could never discover an id). Its description tells the model the blocks ARE the
      author's instructions and to read them before rewriting; `orphaned` is called out as
      ask-don't-guess. `op="create"` stays cut.
      🔴 **Found + fixed a bug in my own D3a code:** `VersionMismatchError.__init__` takes the
      **current row**, not a message — I passed a string. It constructs fine (one positional arg
      either way) and only fails later at `exc.current.model_dump()`, turning a legitimate **412
      into a 500**. Same shape as E1: reusing a shared primitive without reading its contract.
      Pinned by a test.
      The frozen MCP tool-catalog contract caught the new tool and required explicit registration —
      the guard working as designed.
      ⚠️ **Amendment recorded (not silent drift):** the batch `/error-blocks/propose` route is NOT
      built. `pack()` needs a **scene** node and a block is chapter-scoped — picking the wrong scene
      would silently ground the fix on the wrong context. The agent path doesn't need it (it
      composes the fix itself and uses `propose_edit`). So `propose_for_blocks` is **built + tested
      but not yet wired**, stated in the design rather than left to be discovered.
      Suite: **2556 passed / 336 skipped**.
- [x] **D3g** ✅ **The co-writer is taught — and building the guard found 2 bugs in my own tooling.**
      `co_write_skill` (the WRITE-mode surface, where error blocks live) gains a section teaching:
      the marks ARE the author's instructions · **list them before rewriting anything** · fix via
      `propose_edit(replace_selection)` on the exact quoted span, changing only what the note
      complains about · close with resolve/dismiss · `orphaned` = **ask, never guess** · you cannot
      create a block. Surfacing verified mechanically: `_skill_prompt_named_tokens` extracts
      backticked tokens, so both `composition_error_block_edit` and `propose_edit` ride the surface
      **budget-exempt** (D-SKILL-NAMED-TOOLS-RIDE).
      🔴 **New guard — `test_every_tool_a_skill_names_ACTUALLY_EXISTS`.** The existing lint is
      **denylist-only** (`_NONEXISTENT_TOOL_NAMES` is hand-maintained), so a typo would pass green
      and send the model hunting an undiscoverable tool — the exact class the July sweep cleared.
      The new check derives the real catalog from the **services themselves** via
      `scripts/deprecated-tool-scan.py` and asserts every named token exists. Skips loudly (never
      silently passes) if the scanner is unreachable or returns an implausibly small catalog.
      🔴 **Bug 1 — in `scripts/deprecated-tool-scan.py` (mine).** provider-registry registers as
      `registerTool(srv, &mcp.Tool{Name: …})`; neither existing regex matched a struct literal, so
      **the scanner was silently blind to that entire service** — reporting its live tools as
      nonexistent and never catalog-matching its names during the migration sweep. **184 → 198
      advertised.** Under-reporting is the dangerous failure here: a missed finding looks exactly
      like a clean scan. Re-ran after the fix — still **0 findings reach the model**, so the sweep's
      result holds.
      🔴 **Bug 2 — in the new guard itself.** It inherited `_EXEMPT_SKILL_CODES`, which exempts
      `admin`/`co_write` from the **hot-domain** check because they reach tools lazily. Hot-vs-lazy
      says nothing about whether a tool EXISTS — and a wrong lazily-reached name is *worse* (the
      model burns discovery turns). So `co_write`, the skill carrying the newest tool, was the one
      skill the check skipped. **Caught only by injecting a typo to prove the guard could fail** —
      it passed. Fixed, then re-proven: the injected `composition_error_blocks_edit` now reds.
      Two false-positive classes handled honestly rather than by loosening: skills that name a tool
      *in order to say it does not exist* ("**There is no `jobs_retry` tool**") get a documented
      `_DELIBERATELY_ABSENT_TOOL_NAMES` entry — legitimate only when the prompt actually negates.
      chat-service: **1928 passed**.
- [x] **D3d** ✅ **The editor surface — and the FE half of the E1 bug avoided by construction.**
      `errorBlocks.ts` carries the **offset bridge**: the editor works in ProseMirror positions,
      the server in flattened-text offsets, and a mark computed in the wrong space points at the
      wrong prose while every layer reports success. `flattenDoc` routes through
      `addTextSnapshots` — the same helper that writes the `_text` the server reads back — so it
      **is** `tiptap_doc_to_text` byte-for-byte. `selectionToSpan` derives `start` from the **block
      index**, deliberately NOT by searching the flat text: a search would collapse all three
      *"She nodded."*s onto the first. Proven — marking the 2nd yields `lastIndexOf`, not
      `indexOf`. Empty/whitespace selections are refused (an anchorless mark can never re-locate).
      Residual drift (inline atoms) degrades to a **re-anchor, never a corrupted splice**.
      `MarkErrorBlockAction` in the selection bubble: re-reads the selection at **submit** time
      (the author can adjust it while typing the note), refuses an empty note (a mark with no note
      is just a highlight), and reports a 409 **as a duplicate** rather than a generic failure.
      `SelectionToolbar.chapterId` is optional so a surface that omits it hides the action instead
      of breaking the AI ops. **19 FE tests**; composition + studio **2447 passed / 308 files**.
      ✅ **TS drift RESOLVED (2026-07-27).** `tsc --noEmit` now runs: **exit 0, zero errors**, and
      `npm run build` (`tsc --noEmit && vite build`) completes — which matters because the FE Docker
      build runs tsc and can otherwise serve a **stale bundle** on a tsc failure.
      **Root cause, and it exonerates the repo:** `frontend/package-lock.json` is deliberately
      **gitignored** (`.gitignore:218`, with a note that api-gateway-bff's IS kept for its Docker
      build). The 7.0.2 pin lived only in this machine's lockfile; `package.json`'s `^5.5.4` already
      excludes 7.x, and Docker installs from the manifest — which is exactly why the image was
      never affected. So the fix was **local only**: reinstall TypeScript 5.x (now 5.9.3).
      `package.json` was briefly bumped to `^5.9.3` as an npm side effect and **reverted** — the
      repo was never wrong, and changing a shared manifest for a local problem is scope creep.
      **Net repo change: none.**
- [x] **D3h** 🎯 **BROWSER-PROVEN — the marks actually render.** `vite dev :5199` with the new
      code, real studio, real chapter (*The Wet Ink*), offsets computed from the **real** flattened
      prose (`position('Her vision blurred')` → 64) so a miss could not be faked by convenient data.
      | check | result |
      |---|---|
      | decorated text | **`"Her vision blurred"`** — the exact quote, not shifted |
      | class | `lw-error-block lw-error-block--open` |
      | hover title | `"too clinical for her panic here"` — the author's own note |
      | `data-error-block-kind` / `-id` | `voice` / the real row id |
      | computed style | `dotted 2px rgba(225,29,72,.75)` + `rgba(225,29,72,.06)`, `cursor: help` |
      | 🔒 **view-layer only** | the mark appears in the rendered HTML and **NOT** in the document JSON — a Decoration, never a stored mark |
      | resolved ⇒ stops drawing | re-opened the chapter after `status='resolved'` → **0 marks** |
      Visual confirmed by screenshot of the span itself.
      ⚠️ **A near-miss worth recording:** the first post-resolve check returned `errorBlockCount: 0`
      with `editorMounted: false` — the studio does not re-open the editor on reload, so that zero
      meant *"no editor"*, not *"no marks"*. Re-opened the chapter before concluding. Accepting the
      first 0 would have "proven" the status filter with a test that never ran.
- [x] **D3f** 🎯 **THE GATE — LIVE ROUND TRIP PROVEN.** New code deployed into
      `infra-composition-service-1` (files copied + restart; composition-service's tree was fully
      committed, and the other session's in-flight work is in glossary/knowledge, so nothing of
      theirs was built or disturbed). Real book `019f9d2b`, real chapter `019f9d72-7045`:

      | step | result |
      |---|---|
      | author marks a passage | block `019fa3e0-d7ad` created |
      | **MCP `op=list`** | returns `quote`, `note` (*"Mina is dead as of chapter 3…"*), `desired`, offsets, `open_count: 1` |
      | **MCP `op=resolve`** | `status=resolved`, `proposal_id=eb0`, `resolution` stored, `resolved_at` stamped, `version` 1→2 |
      | **MCP `op=list` again** | `open_count: 0` — resolved still visible, no longer counted |
      | 🔒 **cross-project guard** | same block id under a DIFFERENT project → **refused**: *"not found in this project"* |
      | REST route | `GET …/error-blocks` → **401** (route wired, auth gate live) |

      The co-writer can read what the author marked and close it, on the real stack. Smoke row
      cleaned up with a **scoped** delete (by id + `created_by`).
- [x] **D3e** ✅ **Draft Review arm + accept migration — LIVE-PROVEN. Phase D is COMPLETE.**
      This is what makes *"one block-marking primitive across both surfaces"* true rather than
      aspirational: a mark made on a compose preview keeps meaning the same passage after accept.
      `plan_accept_migration` re-anchors by **quote only**, with `hint_trusted=False` — an honest
      statement, since the stored offsets were computed against the *preview*, and accepting
      inserts the draft into an existing manuscript so every offset shifts. Ambiguous ⇒ **orphan,
      never guess** (E1's rule applied at the exact moment the coordinate space provably changed).
      Both halves are returned, so a caller can tell the author *which* marks were lost — returning
      only survivors would make a lost mark indistinguishable from an addressed one.
      2 new routes (`GET …/draft-jobs/{job_id}/error-blocks`, `POST …/error-blocks/migrate-accept`);
      **9 routes total**, all verified registered.
      **Live evidence** (real project/job, chapter with prose *above* the accepted draft):

      | mark | outcome |
      |---|---|
      | quote survives the accept | migrated: `draft_job`→`chapter_draft`, `job_id` **NULL**, offsets `0`→`65`, and `chapter[65:85]` is **still its own words** |
      | quote gone from the chapter | `status=orphaned`, **not** moved — its stale offsets slice `' prose.\n\nElara opened '`, i.e. garbage, which is exactly why they were refused |

      That second row is the point: the stale offsets really do slice nonsense, and the migration
      declined to trust them instead of pointing the author's complaint at the wrong prose.
      6 new tests (survives-the-shift · ambiguous-orphans · lost-is-reported · partial reports BOTH
      halves · empty is a no-op). Composition suite **2563 passed / 336 skipped**. Smoke rows
      removed with a **scoped** delete.

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
- [x] **E6** F7/F8 — canon rules + existing cast threaded into `PassContext`; the CAST pass
      (`run_cast`) stops re-inventing the book. `is_new` is anchored to the book's roster instead
      of one arc's premise, and `package["canon"]` — compiled on every run, read by nobody — now
      reaches a prompt. Four layers, each mutation-proven separately.
- [x] **E6b** The same for the WORLD pass (`run_world`), which had it worse: pass 3 both extracts
      and INVENTS. Live-fired at a real model, the blind run **re-invented the established faction
      `Thanh Vân Môn` as `Thanh Vân Tông`, `is_new=true`, kind `location`**; with the roster all
      three established entities came back `is_new=false` under their correct kinds. The roster is
      passed BY KIND (a flat one is how a mountain becomes a character), and the worker's
      already-existing read now feeds both passes instead of discarding the non-characters.
- [x] **E7 — DONE.** Curve conformance. **Pass 6 DOES honour the curve — measured, not asserted:** on the
      real 10-chapter arc (beat_plan `019f9f0f` → scene_plan `019f9f12`) 8 chapters landed EXACTLY
      on target, two undershot (−22, −4), none ever exceeded. `app/engine/tension_conformance.py`
      makes that a permanent, deterministic output instead of a one-off query, stamped on the
      artifact and rendered per-chapter in `PassArtifactView`. It also flags the **degenerate
      curve** — a real stored artifact (`019f9d2f`) is the all-`beat_role`-NULL flat ramp, which
      scores 10/10 conformance to a curve nobody planned.
      **`self_heal` FIRST LIGHT — it had never run, 0 of 278 plan runs.** It completed, applied
      6 edits, and moved **no chapter's tension peak at all** (heal_moved = 0 across all 10). So
      the curve-blindness of `run_plan_self_heal` is a real structural risk that is NOT realised
      in practice: it edits scene CONTENT (5× repetition, 1× dangling setup), not tension values.
      Recorded as a risk the re-measure now guards, not as a bug found.
      **The pass-6 → pass-7 bridge is proven LIVE, twice.** (a) dogfood run `019f9d2e`: pass 6
      re-run wrote `measured=true, 10/10, MAD 1.1`; pass 7 read those targets off its own input
      (it depends on scenes+cast, NOT beats — the stamp is the only channel) and re-measured
      identically after 6 edits. (b) clean room: a throwaway book + run `019fa874` compiled from
      scratch → pass 6 `10/10, MAD 0.5` → pass 7 `10/10, MAD 0.5`, 6 edits. Throwaway trashed.
      **Also found:** self_heal's first-ever run reports the same defect five times — every
      chapter's FIRST scene re-enacts the previous chapter's LAST scene (CH03←CH02, CH04←CH03,
      CH05←CH04, CH08←CH07, CH09←CH08). That is pass 6 cross-chapter threading quality, i.e. the
      other session's surface — recorded, not chased.
      **Still open:** a NEW book's cold-start needs a glossary ontology `POST /v1/glossary/books/
      {id}/adopt` before the cast seed can apply; nothing in the plan UI says so (the error only
      appears at bootstrap-apply time, as `422 … adopt one in the Graph Schema tab`).
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
- [~] **F2** Matrix in progress. **Surface presence swept 2026-07-27** — all 11 composition
      `*_edit` families have BOTH a live unified MCP tool and an FE write path:
      `motif`/`motif_link`/`motif_bind` (`motifApi.create|patch|archive|restore|createLink|
      deleteLink|bind|unbind`, 71 tsx under `motif/`), `arc` (`motif/arcApi.ts`),
      `arc_template` (`arcTemplates/api.ts` + `create|update|archive|restore|clone`),
      `structure_template` (panel + now wired, E8), `outline_node` (`create|patch|archive|
      restore|reorderNode`), `canon_rule` (`create|patch|delete|restore`), `entity_override`
      (`add|update|delete`), `scene_link` (`create|delete`), `derivative`
      (`deriveWork`/`patchDivergenceSpec`/`getDerivativeContext`), plus `authoring_run`
      manage/review (`authoringRuns/api.ts`).
      ⚠️ **Presence is NOT proof.** All 6 PlanForge atoms also "had both sides" and 8 of them were
      broken (F10: four editors with no door; B6: four kinds where DELETE silently no-op'd). The
      matrix's real column — *real-run proven?* — is still **empty for all 11**. → F3.
      **The gates below are NOT that column.** They prove shape, reachability and preservation;
      the commitment demands a live edit reaching the artifact. Closing F2 on gates alone was a
      bar-lowering caught by the human, not by me — recorded because it is the exact drift this
      checklist's evidence rule exists to stop.
      **REAL-RUN PROVEN (2026-07-28), all 6 kinds — every one a DELETE, the semantic that failed
      silently on four of six (B6), each verified by re-reading the artifact AFTER the write:**
      `beat_plan` MCP (C3, `019f9eea`, curve re-derived) · `cast_plan` MCP (C3, `019f9eeb`, 7→6) ·
      `scene_plan` GUI (C1/C2, `019f9f24`, 25→24, `present_entity_ids` preserved) ·
      **`motif_plan` MCP 2→1** (dropped "Fortuitous Encounter → Legacy") ·
      **`world_plan` MCP 10→9** (dropped "The Ember-Mark") ·
      **`char_arc_plan` MCP 6→5** (dropped "Bram Low").
      **Honest remainder:** that is ONE channel per kind, not both. MCP covers 5, the browser
      covers `scene_plan`. A GUI pass over the other five is the only thing still owed on the
      commitment's literal wording.
      **Two defects found while proving it:** `cold-path-smoke.py` reported 10/10 while never
      running the `world` pass at all (found by trying to edit a `world_plan` that did not exist —
      now 11/11), and my MCP harness silently swallowed tool errors because `isError` rides inside
      `result.content`, not the JSON-RPC `error` field, so two failed edits first read as "no error,
      just not applied".
      Supporting gates, which prove other things and are worth keeping: delete/archive by the per-family contract + live registry gate, the FE door by
      `scripts/fe-door-scan.py` (0 dead components; one real hit fixed), and round-trip
      preservation by a check DERIVED from the producer's own contract, so a field added tomorrow
      is covered without anyone remembering. Plus `scripts/cold-path-smoke.py`, which walks a book
      from nothing to a healed scene plan in 60.7s — the one thing none of the static gates could
      have caught.
      Earlier confirmations:
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
- [x] **F3 — DONE (2026-07-28).** Swept by GATE rather than by 44 round-trips, in the priority
      order below.
      **Stage 1 (DELETE/archive):** the per-family atom-delete contract + live registry gate.
      **Stage 2 (the FE door):** `scripts/fe-door-scan.py`. Reachability-by-import proves nothing —
      F10's editors WERE imported — so it asks the three questions that do: mounted nowhere at all
      (JSX *or* panel-catalog); single-parent (one point of failure); and does any test mount the
      PARENT. Result: **0 dead components**, F10's own site covered by 13 `PassRow` tests, and one
      real hit — `MotifDetailDrawer`'s edit door, a four-term predicate whose `motif-detail-edit`
      had ZERO references outside the component, gating a change made the same day
      (`isReadOnly` → `book_shared` editable). 6 tests, 3 mutation cuts caught.
      **Stage 3 (round-trip preservation):** derived, not sampled. The unexposed set is
      `contract.row_fields − the editor's real cols`, read from the generated snapshot, so a
      producer that adds a field is covered the moment it lands. Every editable kind, one
      object-valued field to catch a shallow copy. Both cuts caught (readRows dropping unexposed
      keys; save rebuilding rows from the exposed columns).
      **Two scanner blind spots found by checking hits instead of reporting them:** a panel is
      mounted by REGISTRY not JSX, and a component's HOST and its DOOR can be different components
      (`CheckpointReview` is hosted by `PassRailPanel`, gated by `PassRow`).
      **Proof sweep design (2026-07-27):** proving 11 families × 4 ops live is ~44 round-trips and
      most would pass. Prioritise by *failure mode observed in this track*, not by count:
      1. **DELETE / archive first** — the op that failed silently on 4 of 6 PlanForge kinds (B6).
      2. **Then the FE door** — does a completed/advisory state actually render a way in? (F10).
      3. **Then round-trip preservation** — does an unrelated edit drop an unexposed field? (B8).
      Ops that merely add a row are the least likely to be silently wrong; sample them.

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
| 2026-07-27 | **Designed the agent's path in detail and forgot the human's.** The spec specified the MCP tool, its ops, its affordance gate and its confirm-gating — and never named a single REST route, even though the whole point of the feature is that *the author* marks the block and the FE cannot call MCP. Caught only by asking "what else before build?" one more time instead of accepting my own "BUILD-ready". The MCP-first invariant makes the agent path the one you think hardest about; it does not make it the only one. |
| 2026-07-27 | **Claimed "zero contested files" a second time, and was wrong again.** After being corrected once on `self_heal.py`, I wrote "D3a — none (new table)" — but the DDL lands in `migrate.py`, which the other session appended to hours earlier and which was already swept once. The table is new; the *file* is not. Same error shape as the first: reasoning about the artifact I'm adding instead of the file I'm editing. |
| 2026-07-27 | **Told the human that D3a–D3c were safe backend work, then found `self_heal.py` is the concurrent session's single most active file** — six recent commits, one named `fix(compose-quality)`. I had checked file ownership for the *FE* surfaces (D3d/D3e) and simply assumed the backend was uncontested, because "backend" felt like my territory. The coordination hazard is documented at the bottom of the design and I still reasoned past it. The fix turned out to be strictly better anyway (a composing module beats the refactor), which is the uncomfortable part: the right answer was reachable without the near-miss, and I only looked because REVIEW forced a second pass. |
| 2026-07-27 | **Nearly shipped a design whose re-anchor silently corrupts prose (E1).** `locate_span` returns the FIRST match. I had already read that function, quoted it in the design as the re-anchoring solution, and never asked what happens when the quoted sentence appears twice — which, in fiction, short lines constantly do. A drifted mark on the third "She nodded." would have sent the co-writer's fix to the first one, and *nothing* would have reported an error: the block resolves, the prose changes, the wrong paragraph is edited. Reusing a primitive means inheriting its preconditions, not just its behaviour. |
| 2026-07-27 | **Wrote a whole data model on an assumed scope key.** The Phase D design specified `owner_user_id` as the tenancy column — reasonable-sounding, and wrong: composition scopes by `book_id`, and `created_by` is an actor stamp *explicitly never filtered on*. Three sibling tables say so identically. Had I gone to BUILD on the design as written, the migration would have shipped a column that no query could correctly use, and the tenancy filter would have been silently wrong — the exact defect class the User Boundaries rule exists to prevent. Caught only because "clear the gaps" meant *reading the sibling tables* instead of trusting the design I had just written. **A design is a hypothesis; the schema is the fact.** |
| 2026-07-27 | Nearly reported F11 (Polish drops `_text`) after reading only the FE converter. Two more checks were needed before it was a claim rather than a guess: that book-service stores a `json` body verbatim (it does — `normalizeBodyToTiptap` passes through), and that the *normal* editor save doesn't have the same hole (it doesn't — `addTextSnapshots`). Had either gone the other way the finding would have been noise. Negative-result rigour, again. |
| 2026-07-26 | Sweeping for more `auto`-sentinel filters, I found `arc_template_repo`'s language clause and nearly reported it as a second instance. It takes an explicit query param defaulting to `None` (which skips the clause), not the book profile's `"auto"` — verified the callers before claiming. Negative results need the same rigour as positive ones. |
