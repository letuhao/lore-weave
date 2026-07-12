# RUN-STATE — Book-Package cluster (specs 22–28) autonomous build

> ## 📌 READ THIS FILE FIRST after any compaction, and at every checkpoint.
> This file — not my memory of the conversation — is the source of truth for the run.
> Context is lossy. Disk is not.

**Started:** 2026-07-12 · **Branch:** `feat/context-budget-law` · **Mode:** long unattended run, self-checkpointing.
**Law:** [`00A_BOOK_PACKAGE_STRUCTURE.md`](../specs/2026-07-01-writing-studio/00A_BOOK_PACKAGE_STRUCTURE.md) (DA-1..14, BPS-1..21) — binding, never re-litigated from memory.
**Sequence:** [`00B_EXECUTION_ROADMAP.md`](../specs/2026-07-01-writing-studio/00B_EXECUTION_ROADMAP.md) — 9 stages. **This file sequences nothing; 00B does.**
**Pillars:** `22` scene seam · `23` book architecture · `24` plan hub · `25` migration · `26` indexing · `27` compiler · `28` agent-native.

---

## 1. The goal (one sentence)

**Finish the book-package cluster — every REMAINING milestone of 00B (Stage 7's unbuilt half, Stage 6, Stage 8)
built, `/review-impl`-clean, live-proven, and committed — or explicitly parked in §7 with a reason.**

## 2. Autonomy contract (agreed with PO 2026-07-12)

| | Rule |
|---|---|
| **Don't stop** | Work continuously. Do not pause for approval between slices or phases. |
| **Self-checkpoint** | I checkpoint myself: `/review-impl` → fix → VERIFY → commit → update this file. **No human gate.** |
| **`/review-impl` per phase** | **Mandatory, run by me.** Findings fixed **in the same phase**, not deferred. A phase is not done until its review is clean. |
| **I decide** | All ordinary technical decisions are mine. Record every one in §6 with its reasoning — the PO audits them at the end. |
| **Undecidable → §6 as OPEN** | If I genuinely cannot decide (a product/UX call, a trade-off with no technical winner), I pick the **reversible** option, ship it, and record it in §6 flagged **`⚠ PO-DECIDE`** with the alternatives. I do NOT block on it. |
| **Blocked ≠ stop** | Cannot solve it? **Park it in §7, move to other work, keep going.** Never block the run on one problem. |
| **STOP only if** | (a) **destructive/irreversible** — data loss, a migration that deletes user data, a security-critical exposure; or (b) a **LAW in 00A** (DA/BPS) or a sealed 00B adjudication turns out to be wrong and needs redesign. Then: stop, write it up, ask. **Nothing else is a stop.** |
| **Final audit** | Built incrementally (§6–§10) so the audit is a *byproduct*, not archaeology. **An empty drift log (§9) is dishonest, not clean.** |

## 2b. The `/goal` condition (the human↔agent commitment — durable copy)

The human sets this with `/goal` (**the agent cannot set it**). Recorded here so it survives compaction.
⚠️ The `/goal` evaluator **reads the transcript only — it cannot run commands or read files**, so the
condition is deliberately written to force proof *into* the transcript.

```
/goal Every remaining milestone of docs/specs/2026-07-01-writing-studio/00B_EXECUTION_ROADMAP.md is COMPLETE, or parked in RUN-STATE §7 with a reason. This is a long unattended run: the human will review only at the end. Work continuously through the phases in the order set in docs/plans/2026-07-12-book-package-RUN-STATE.md §5; do NOT stop between slices or between phases. Done means ALL of: (1) every slice in RUN-STATE §5 is ✅ with a real evidence string, or 🅿️ parked in §7; (2) for each phase, the transcript contains the ACTUAL PASTED OUTPUT of that phase's test runs (unit + integration) — claiming a check passed without pasting its output does NOT satisfy this condition; (3) every phase that touches ≥2 services has a LIVE smoke whose actual output/DB rows are pasted into the transcript — a green unit suite is NOT proof of a behaviour it never exercised; (4) /review-impl has been run BY YOU on EVERY phase and every finding is FIXED and committed in that same phase (not deferred); (5) the transcript shows `git log --oneline` after each phase; (6) RUN-STATE §6-§9 registers (decisions / parked / debt / drift) are kept current AS YOU GO, and §10 completeness ledger is filled at the end; (7) a final audit covering decisions · drift · debt · parked · completeness. RULES: after any compaction, re-read docs/plans/2026-07-12-book-package-RUN-STATE.md FIRST, then `git log --oneline -15`, then continue — never re-derive a sealed decision from memory. NEVER `git add -A` (this checkout is shared with concurrent agent sessions; enumerate files, and stage only your own hunks in shared files). Clean up every seeded DB row and throwaway DB. Make ALL ordinary technical decisions yourself and record them in §6; if a decision is genuinely the PO's, pick the REVERSIBLE option, ship it, flag it ⚠ PO-DECIDE in §6, and KEEP GOING. If you cannot solve something, park it in §7 and MOVE ON — blocked is not stopped. Stop and ask ONLY if (a) an action is destructive/irreversible or risks real user data, or (b) a LAW in 00A or a sealed 00B adjudication turns out to be wrong. Otherwise keep going until every milestone is done or parked.
```

## 3. Invariants — the bar that must not be silently lowered

Drift in a long run is not "forgot the task"; it is **lowering the bar**. These are the specific ways this
run could cheat, taken from bugs this repo has actually shipped:

1. **A green unit suite is not proof.** Every cross-service slice needs a LIVE smoke with pasted output. Two HIGH bugs in the Plan Hub passed a full green suite (`24eae5934`).
2. **Rebuild + `--force-recreate` before believing a live result.** A stale image read as a false green this week.
3. **A fixture can seed a column production never writes.** Verify the WRITER, not just the reader (`7c8a8a487`).
4. **Never decide from a partial view.** A no-op guard on loaded-only data silently swallowed a real move; a truncated 100-row page sent an undo to chapter 1 (`749805ca6`).
5. **Absent ≠ zero. A silent success is a bug.** Surface it.
6. **`/review-impl` is not optional and not a rubber stamp.** "0 issues found" without evidence is the tell.
7. **Never `git add -A`** — shared checkout, concurrent sessions. Stage your own hunks even inside a shared file.
   **AND: `git add … && git commit …` must be ONE command.** `git commit` takes the WHOLE INDEX, and the
   index is *shared*. Splitting the add from the commit opens a window in which the other session's
   `git commit` sweeps up your staged files. This is not hypothetical — it happened (DR-04).
8. **Clean up every seed + throwaway DB.** Never run a destructive fixture against the shared dev DB.
9. **The workflow gate is mechanical** — `scripts/workflow-gate.py` + the pre-commit hook. Do not bypass.

## 4. Ground truth at run start (verified 2026-07-12 against the live DB + code, not docs)

| Stage | Pillar | Status | Evidence |
|---|---|---|---|
| 0–1 | adjudications · `25` re-key trunk | ✅ DONE | `package_migration` marker present |
| 2 | `23` structure layer | ✅ DONE | `structure_node` present |
| 3 | `25` the lift (point of no return) | ✅ DONE | legacy `arc` table **gone** |
| 4 | `22` scene seam | ✅ DONE | `scenes.source_scene_id` + `book_id` present |
| 5 | `26` indexing + staleness | ✅ DONE | `arc_conformance_state` present |
| **6** | **`27` PlanForge v2 compiler** | ❌ **NOT BUILT** | `pass_state` table absent |
| **7** | **`24` Plan Hub** | ⚠️ **~60%** | read/display/drag real; the ACTION half absent (see §5-A) |
| **8** | **`28` agent-native** | ⚠️ **HALF** | `book_steering_set`/`book_search` ship; `composition_package_tree` / `find_references` / `diagnostics` absent |

**Order deviation on the record:** Stage 7 was built before Stage 6. Dependency-legal (24's prereqs are
Stage 3 + 26-C, not 27), but the trunk order was jumped — the compiler that *produces* the plans the Hub
displays is still v1.

**Cross-spec blocker found in the audit:** 00B §7.1 requires 24-H1.3's coverage-diff to land as **the shared
helper 28-AN-4/OQ-4 names — ONE implementation**. It is a hardcoded `"unplanned_chapters": []`
(`plan_overlay.py:199`). So **28-AN-A has an unbuilt prerequisite sitting inside the Hub.** Phase A closes it.

---

## 5. Slice board — `done` = an evidence string, never a claim

Legend: `[ ]` todo · `[~]` in progress · `[x]` done + evidence · `🅿️` parked (→ §7)

### PHASE A — finish Stage 7 (`24` Plan Hub): the action half + the audit's fix-now tier
*Rationale for going first: it is half-built (finish what's started), and it unblocks Stage 8.*

| # | Slice | Status | Evidence |
|---|---|---|---|
| A1 | **24-H1.3 coverage-diff helper** — the real `unplanned_chapters` (book chapters ∌ spec nodes). ONE implementation, exported for 28-AN-4. **Unblocks Stage C.** | [x] | `03f02533d` · `app/services/coverage.py`; 1856 pass / 248 skip; degraded ⇒ key ABSENT + warning (absent≠zero), proven at helper AND route |
| A2 | **PH21 empty state + unplanned tray + UNASSIGNED strip** | [x] | `774f51692` · found a DA-10 naming collision: `layout.unplanned` (spec chapters w/ no ARC) vs `overlay.unplanned_chapters` (manuscript w/ no spec) were two sets under one name. Renamed → `unassigned`, RENDERED (they were computed + dropped ⇒ invisible ⇒ unfixable), and made REACHABLE (new `unassigned=true` children axis — neither existing axis could fetch an arc-less chapter, so a decompiled book rendered blank). |
| A3 | **Window pagination unreachable** | [x] | `cd92bdd05` · lane header shows `loaded/total` ALWAYS (100/100 vs 100/340 were indistinguishable — the ambiguity the bug hid behind) + `+ more`. |
| A4 | **Fix-now debt tier** | [x] | `b23ff9862` · one root cause: things COMPUTED then never surfaced. One `notices` channel (dead manuscript join / refs_capped / coverage warning) + cold-open loading state + live Canon+Threads drawer facets. `useActualState.note` was documented "non-null when unavailable" and hardcoded `null`. |
| A5 | **PH18 deep-links** | [x] | `b23ff9862` · the seam was DEAD: every node card read `data.onOpenRef` and NodeBadges honoured it, but PlanCanvas never put it in `data` ⇒ `undefined` forever ⇒ every canon badge a plain chip. Each piece unit-green in isolation; nobody tested the JOIN. |
| A6 | **PH13 stub connectors** | [x] | `428edee0f` · UNFIXABLE client-side: a collapsed arc never loads its scenes, so the endpoint's lane is unknowable. Read surface #4 now ships endpoint ANCESTRY; pure `edgeResolve.ts` walks it to the nearest rendered ancestor; ⇄N badge for folded edges. ArcRollupNode had no `<Handle>` — RF drops an edge onto a handleless node, so the stub resolved right and died one layer lower. |
| A7 | **PH20 row 5 — draw/delete a scene-link edge** (`nodesConnectable={false}` today; no `onConnect`; `createSceneLink` absent from the FE api) | [ ] | |
| A8 | **Cast chips (H4.4/PH26)** + missing-vs-truncated split — `NodeContent` drops `present_entity_ids`, which is already on the wire | [ ] | |
| A9 | **Node/arc action rail + Hub toolbar** (PH15's 9 Action seats, OQ-7 "Ask AI about this plan") | [ ] | |
| A10 | **Drawer writes** (PH20) — rename/status, add chapter/scene/arc, archive/restore, tension edit, ⚓ re-anchor, motif bind/unbind, **"Open in Editor"** (PH16 calls this contract *fixed*) | [ ] | |
| A11 | **H8.1 cold-open ≤5-request budget** — currently VIOLATED: `useActualState` eagerly pages the whole book scene index. Assert the budget in a test. | [ ] | |
| A12 | **Coverage** — `usePlanHub`, `usePlanWindows`, `useActualState`, `PlanHubPanel` have **no tests**; they own the generation/`complete`/identity guards that exist because these bug classes bit before. Backend: `POST /chapters/reorder` + `conformance/status` have no route tests. | [ ] | |
| A13 | **PH25** — the navigator is a column inside the panel, not an **Activity Bar tab**; rail rows lack every specced decoration | [ ] | |
| A7 | **PH20 row 5 — draw/delete a scene-link edge** | [x] | `a10a0b4bf` · book-keyed create mirror (the Work-keyed one is uncallable: PH9 gives the Hub no `project_id`). Delete is UNDOable (A-R fixed my false "the 204 carries no kind/label" — the client holds the edge). |
| A8 | **Cast chips (PH26)** + missing-vs-truncated split | [x] | `96f8980e1` · `present_entity_ids` was on the wire since H1.1; NodeContent dropped it. COMPLETE map + absent ⇒ MISSING; TRUNCATED map + absent ⇒ unknown. A failed read is NOT a complete map. |
| A9 | **Node/arc action rail + Hub toolbar** | [x] | `1f7185c02` · find(highlight, never filter — PH14) · fit · problems · Ask AI (P-13: Compose w/ selection) · view modes VISIBLE+DISABLED (P-10). |
| A10 | **Drawer writes** (PH20) | [x] | `021401099` + A-R · rename/status/tension/goal/synopsis/⚓re-anchor/archive+restore/Open-in-Editor. Status is a closed set; unknown status renders as ITSELF (never snaps to option 1 and writes it). |
| A11 | **H8.1 cold-open ≤5-request budget** | [x] | `6ef1eea5b` + A-R · was ~100 requests (whole-book scene index at mount). Now lazy per loaded chapter; per-chapter completeness gate. **Test asserts what must NOT fire, not only what may** — that omission is what let A10 re-break it. |
| A12 | **Coverage** — BE route tests | [x] | `6da59fcc3` · 10 cases on `POST /chapters/reorder` (the route that PERMUTES THE MANUSCRIPT and had none). No bugs found; now guarded. |
| A13 | **PH25** — Activity-Bar rail | [x] | `6da59fcc3` · `plan` is now the 2nd Activity Bar tab; removed from the panel (OQ-6 rejects a duplicate in-panel list). Rail→Hub focus rides the bus (`planFocusNode`), which **clears DBT-03**. |
| A-R | **`/review-impl` Phase A + fix all findings + commit** | [x] | **3 HIGH · 7 MED · 4 LOW — ALL FIXED** in `09f2d29b1` (see DR-04: index collision put them in a concurrent session's commit). FE 4946 pass (672 files) · composition 1873 pass/248 skip · tsc clean. |
| A-S | **LIVE SMOKE (cross-service: composition ↔ book-service ↔ gateway)** | [x] | Stack up, image **rebuilt --no-cache + verified in-container** (the first rebuild silently didn't take — invariant §3.2 caught it). Seeded book + 3 chapters, **zero plan**: `plan-overlay` returned all 3 as `unplanned_chapters` with `unplanned_count: 3` (that key was a hardcoded `[]` before A1). Axis guard: 0-axis→400, `unassigned=false`→400, `unassigned=true`→200. Scene-link on a plan-less book → **409 NO_CANONICAL_WORK** (honest, not a 500). Decompiler over unparsed prose → `scenes_total: 0, detail: "no parsed scenes to decompile"` (honest zero, not a fake success). **Book deleted; 0 rows left.** |

### PHASE B — Stage 6 (`27` PlanForge v2 multi-pass compiler)
*The biggest slice. Restores the trunk order. `00B` §6.0 is a hard pre-build gate.*

| # | Slice | Status | Evidence |
|---|---|---|---|
| B0 | **25 M-step registration (NC-4 pre-build gate)** | [x] | **ALREADY SATISFIED — verified, not assumed.** `25` §M6 exists (added at the 2026-07-10 integration): *"M6.1 · 27 A3: drop `outline_chapter_required`, re-add inverted as `outline_chapter_written_kinds` … ships with 27 V2-A · MUST land before 27 V2-E's first link insert."* The gate requires the *registration* to exist before building; it does. My board wrongly said it "mints M6". |

**Phase B ground truth (verified against the LIVE DB + migrate.py, 2026-07-12 — not from docs):**
| Fact | State |
|---|---|
| `outline_chapter_required` CHECK | ⛔ **still the OLD one** (`migrate.py:212`) — M6.1 is REGISTERED but NOT IMPLEMENTED. This is B1's first job, and it **blocks B4** (every skeleton-link insert violates the old CHECK). |
| `plan_run.pass_state` / `.genre_tags` | ⛔ **absent.** ⚠️ Evidence correction: `pass_state` is a **JSONB COLUMN on `plan_run`**, not a table — my run-start check probed `to_regclass('pass_state')`, which can only ever return NULL. Right conclusion, wrong evidence. Re-verified against `information_schema.columns`: `plan_run` = id/created_by/book_id/work_id/status/mode/model_ref/source_checksum/source_markdown/active_job_id/error_detail/checkpoint_state/created_at/updated_at. No pass_state, no genre_tags. |
| provenance columns (PF-9/PF-10) | ⛔ **absent** — `structure_node.plan_run_id`/`plan_arc_id` and `outline_node.plan_run_id`/`plan_event_id` all missing. V2-A2 unbuilt. |
| `genre_tags` | ✅ present on `motif` + `arc_template` (pre-existing; 27's own plumbing is still B2). |
| B1 | **27-V2-A** — `pass_state`/`genre_tags`, CHECK swaps, provenance columns + partial uniques, the A3 swap | [x] | `a4558ed44` · **LIVE-PROVEN in the DB**: pass_state/genre_tags on plan_run · provenance cols + both partial UNIQUEs (tombstone-exempt) · **`outline_chapter_required` GONE → `outline_chapter_written_kinds`** (M6.1). Proved the effect both ways: chapter w/ `chapter_id NULL` INSERTs; arc w/ a chapter_id is rejected by name. **This unblocks B4.** 1890 pass / 251 skip (+12 schema-contract tests: the model Literals are compared to the CHECK sets, which nothing in CI did). |

> **▶ RESUME HERE (next context): B2.** B0 ✅ (gate already registered in 25 §M6, verified) · B1 ✅ (schema live).
> **B2 = 27-V2-B ∥ V2-C** — contracts unfixturing (PF-14) + `genre_tags` plumbing ∥ the pass runner
> (`app/services/plan_pass_service.py`, NEW: pass registry + fingerprinting + derived freshness),
> `app/engine/world_plan.py` (NEW — mirror `cast_plan.py`), the pass-4 hoist, and the artifact-I/O
> adapters for passes 1/2/5/6/7. Spec: `27_planforge_v2_compiler.md` §V2-B (L510-516) + §V2-C (L517-525).
| B2 | **27-V2-B ∥ V2-C** — pass registry + fingerprint + derived freshness · `world_plan.py` · `genre_tags` | [x] | `b0eafe205` · `plan_pass_service.py` (registry; PF-3 fingerprint with model_ref EXCLUDED; derived fresh/cursor/blocked_at — never stored) · `world_plan.py` (pass 3, mirrors cast_plan; tolerant parse; degrade-safe) · genre_tags route→service→repo→row→response. **Fixed my own B1 closed-set drift** (see DR-06). 1946 pass. *NOT done: C2 worker op · C4 pass-4 hoist · C5 adapters → §7 P-01.* |
| B2b | **27-V2-C2/C4/C5 — MAKE THE PASSES RUN** (was P-01, un-parked per DR-10) | [x] | `51707e29f` · **LIVE: a pass RUNS.** One op runs all seven (`input.pass_id`). Compute in the op; persistence in the finalize hook, **artifact FIRST then the pointer** (the other order records a pointer to an artifact that does not exist — every downstream pass resolves its input to nothing while the ledger says complete). C4 hoist makes `beats` a checkpoint a human can BLOCK on, and `grounded_decompose` now HONOURS a supplied curve (recomputing it would discard the human's edit — PF-11 one layer down). Smoke: PF-5 `world`→**409 UPSTREAM_STALE blockers:['cast']** · `cast`→real LLM→**6 members, `Ha / protagonist`** · pointer RESOLVES · PF-6 completed≠accepted so `world` STILL 409s · bad pass_id→422 · rows reaped. **2 bugs only the smoke could find** (DR-11, DR-12). 1999 pass. |
| B3 | **27-V2-D** — `propose_seed` quarantine + checkpoint extension + `roster_bindings` (PF-13) | [x] | `6ef793f3f` · **LIVE: the full author loop.** PF-7: passes 2/3 PROPOSE, never seed — one approval mechanism, and accepting `cast` REQUIRES its proposal `applied`, so the blocking gate and the mutation gate are the SAME gate. PF-13: `roster_bindings` written onto the arc, proven by **EFFECT** (change the binding ⇒ the PACKED PROMPT changes — the discipline the spec demands, not a source assertion). D2: `edits` ⇒ a NEW artifact ⇒ downstream stales by derivation, zero writes. Smoke: accept-while-pending→**409 'apply it first (PF-7)'** · apply→**6 glossary entities MINTED** · accept→200 `decision=accepted by=user` · **arc.roster_bindings = 6 real glossary ids** · `world` 409→**200** · edit→new artifact · both DBs reaped. **3 bugs only the smoke could find** (DR-13, DR-14, DR-15). 2021 pass. |
| B4 | **27-V2-E** — the LINK step (skeleton inline at compile · provenance · E2b stamp) | [x] | `e813f7200` · **LIVE-PROVEN on real rows**: compile → 1 arc + 3 chapters, `source='planforge'`, `chapter_id NULL` ("planned, not yet written" — insertable only because of B1's M6.1 swap), strided story_order 1000/2000/3000. **PF-10**: a 2nd compile reports `updated 1/3`; counts stay 1 arc/3 chapters — the partial-index ON CONFLICT really arbitrates. **PF-11**: a human retitles ch.2 → re-link reports `updated: 2, preserved_user_edit: 1` and the human's title SURVIVES. **E4** zero-node = error, report persisted. Rows cleaned to zero. **The linker immediately found a 100%-reproducible upstream bug** (Arc-1 events silently dropped). *NOT done: E3 bootstrap stamp → §7 P-03.* |
| B5 | **27-V2-F ∥ V2-G** — 3 MCP tools + HTTP mirrors ∥ fixture severing (PF-19) **+ P-06** | [x] | `2c0a44a30` · **THE COMPILER STOPPED PLANNING SOMEONE ELSE'S BOOK.** Three leaks, each making it answer questions about a novel the user never read: (1) the PROPOSER FABRICATED — `_variable_defs` took a `var_body` and *ignored it entirely*, returning one novel's PA/HA/CD/THR; anchors, forbids, the protagonist and the arc titles were all hardcoded. Rules mode did not FAIL on an unseen book, it **silently planned a DIFFERENT one**. (2) the VALIDATOR BLOCKED — `anchors_min ≥ 4` (the POC's own count) was a HARD gate, so any shorter charter got a 422; and `arc2_discovery` asserted a value the proposer hardcoded — the validator checking the fixture against itself, a rule that could not fail. (3) the SERVICE GRADED every book against `story-plan-v1.md` — "what's missing from your plan" meant "what does your plan lack that this other novel has". All parsed/severed now; the POC's own values still come out **because they were in its text all along**. V2-F: 3 MCP tools + HTTP mirrors + `link_scene_plan` finally given a caller. **LIVE (a detective story, rules mode):** its own arc/vars/cast/anchors · **POC LEAKS: NONE** · compile→premise is THIS book→1 arc + 2 chapters · re-link idempotent (`unchanged 1/2`, no dupes) · scene-link with no scenes→409 · rows reaped. 2022 pass. |
| B6 | **27-V2-H** — unit + effect tests + **H3 cross-service live smoke** + **E3** | [x] | `47bddd8d9` · **THE WHOLE COMPILER RUNS.** H3: compile -> skeleton link -> all 7 passes (both human checkpoints) -> glossary through the quarantine -> roster join -> scene link -> bootstrap creates the manuscript and **E3 stamps the plan**. `pass_cursor 7/7` · 7 glossary entities · 6 roster roles · **6 scenes with tension 20/40/50/45 AND `present_entity_ids` 1/2/2/2** · story_order 1000/1001/1002/2000 (the strided 0-based axis) · **2/2 planned nodes stamped** · 0 rows left in both DBs. H2 effect tests: change the cast => pass-6's PROMPT changes; change the binding => the PACKED prompt changes. **3 bugs only the 7-pass smoke could find** (DR-18/19/20). 2038 pass. |
| H4 | **S06 flagship replay gate** | P | **PARKED -> §7 P-07.** A concurrent agent session is actively and repeatedly redeploying `chat-service` (it restarted TWICE mid-run; container uptime confirms), and every redeploy kills the 17-turn eval's in-flight session with a 401. Reached turn 8/17 with 4 tool calls and 0 empty-intent -- the harness and the new tools work; the RUN cannot complete while the service under test is rebuilt beneath it. **The property S06's gate ADDS ("the plan movement ends with linked structure: structure_node + chapter/scene outline_node > 0") is already LIVE-PROVEN by H3.** What stays unproven is the agent-DISCOVERABILITY path. |
| B-R2 | **`/review-impl` Phase B (B2b/B3/B5/B6) + fix all findings + commit** | [x] | `b99b38b6b` · **3 HIGH · 2 MED -- ALL FIXED.** **HIGH-1: the AGENT could FORCE past the human's checkpoint** -- my own tool description promised the model that `cast`/`beats` need a human, and then handed it `force`. An agent that hits a 409 retries with force=true; that is what being helpful MEANS. PF-6 was a speed bump. Enforced by ABSENCE now (the human's HTTP route keeps it). **HIGH-2: re-running a pass broke the compiler** -- an empty seed proposal overwrote the pointer, acceptance refused behind it, and the roster join lost every id => the scenes silently lost their cast. **HIGH-3: a re-run silently ATE the author's acceptance** -- nothing marked a pass `running`, so the ledger reported the PREVIOUS run's `completed`+`accepted` for 30s while its artifact was replaced; the accept returned 200 and the finalize hook then wrote `pending` over it. MED: `paid` undeclared on a money-spender; the parser uncapped. **LIVE-proven on the re-run path** (where all three lived): 409-then-200, roster 6 roles (no shrink), the whole chain completes. 2045 pass. |
| B-R | **`/review-impl` Phase B (B1-B4) + fix all findings + commit** | [x] | `f5ca7ecf8` · **3 HIGH · 8 MED · 4 LOW — ALL FIXED**, none deferred. 1975 pass / 251 skip. **The unit suite could not have caught 3 of them** — a **5-compile** live smoke did (a 2-compile smoke shows a GREEN `preserved_user_edit: 1` while the human is overwritten on the 3rd). HIGH-1 (PF-11 reclaimed the human's edit one compile later — and **my first fix was itself wrong**, see DR-08) · HIGH-4 (**a no-op compile bumped every chapter's + scene's version** → staled every held ETag → next user edit 412s; and `unchanged` was structurally unreachable — a counter that can never be non-zero is a lying metric, DR-09) · HIGH-2 (arc titled with the premise blob). Live: human's chapter + arc survive 5 compiles; `Event 1 \| v1` (was climbing to v4); rows reaped `sn=0 on=0 pr=0`. |

### PHASE C — Stage 8 (`28` agent-native studio)
*Needs A1 (the shared coverage helper). AN-B already shipped.*

| # | Slice | Status | Evidence |
|---|---|---|---|
| C1 | **28-AN-2/3/4** — the agent's three read surfaces | [x] | `a3abc05a6` · **LIVE through the REAL MCP transport** (handshake + tools/list + call -- the path the agent takes, not the python fn). All three **ADVERTISED** (AN-10). `package_tree`: spec + manuscript + index + coverage + runs in **553 chars / ~138 tokens** (AN-2's whole point -- the 146K-token `list_outline` incident is what happens when orientation and content share a tool). `find_references`: found the protagonist **cast as "protagonist"** on the arc roster -- PF-13's symbol table read backwards. `diagnostics`: ranked, composes IX-14 + canon_issues + BA15 + the SAME coverage diff 24 H1.3 renders. **NAMING deviation (D-06):** 28's shorthand says `ReferencesRepo.find_by_entity`, but `ReferencesRepo` ALREADY EXISTS and means the author's REFERENCE SHELF -- following the shorthand would have put two concepts behind one name. **5 bugs the live MCP smoke found** (DR-23). 2060 pass. |
| C2/C3 | **28-AN-C/AN-D** — discovery registration · effect tests · cross-service live smoke | [x] | Folded into C1 + C-R and proven there: **tools/list advertises all three** (AN-10's deterministic-completeness contract, asserted live); the token-budget effect test pins AN-2's cap on a synthetic 10k-chapter book; the cross-service live smoke runs through the real MCP transport against composition + book-service + glossary. |
| C3-S06 | **28-AN-D3** — the S06 flagship replay (pillar-28 ship signal) | P | **PARKED -> §7 P-07**, same external blocker as 27's H4: a concurrent session is redeploying `chat-service` mid-run. |
| C-R | **`/review-impl` Phase C + fix all findings + commit** | [x] | `54ae6c72a` · **1 HIGH · 2 MED · 1 LOW -- ALL FIXED.** **HIGH: the problems panel silently skipped its ERROR-severity source.** AN-4 names FIVE sources; I queried four. `SEVERITY` declared `prose_deleted_spec_node: error` and NOTHING emitted it -- so an agent asking "what is wrong with this book" got a confident answer that had never checked the highest-severity class the panel has. **A panel with a silent gap is worse than no panel: the reader believes the count.** MED: the `.runs/` block ignored AN-2's own owner-gate (a VIEW grantee was being handed the owner's planning history); a dead `project_id` had the tool passing a BOOK id in a project slot. **LIVE-proven by DOING it:** delete a chapter out from under a linked plan -> the spec node SURVIVES (IX-13) -> the panel now reports `prose_deleted_spec_node` ERROR (before the fix: nothing). Verified clean: provider gate, all 8 SQL sources book-scoped with no interpolated user value, the closed-set enum SURVIVES to tools/list. 2067 pass. |

### PHASE D — close-out
| # | Slice | Status | Evidence |
|---|---|---|---|
| D1 | Per-pillar **definition of done** re-checked against `00B` §6 | [ ] | |
| D2 | `SESSION_HANDOFF` + `00B` status stamps updated; every cleared defer moved to "Recently cleared" | [ ] | |
| D3 | **Final audit** written (§6–§10 consolidated) | [ ] | |

---

## 6. Decisions register — every ordinary call I made (PO audits these)

> Format: `date · decision · why · reversible?` — flag `⚠ PO-DECIDE` where the call is genuinely the PO's
> and I picked the reversible option to keep moving.

| # | Decision | Why | Reversible | Flag |
|---|---|---|---|---|
| D-01 | **Phase order A → B → C** (finish 24, then 27, then 28) rather than 00B's literal 6 → 7 → 8 | Stage 7 is half-built (finish what's started, don't leave a half-feature), and A1 unblocks C. No dependency is violated: 24's prereqs are Stage 3 + 26-C, and 28-AN-A needs A1, not 27. | Yes | |
| D-02 | **The coverage diff is computed SERVER-side** in composition-service (`app/services/coverage.py`), reading book-service's spine via the existing internal book client — *not* client-side as H1.3's first cut assumed. | 28 OQ-4/NC-1 seals it as "one composition-side helper shared by 24 H1.3's overlay and AN-4", and an MCP tool (`composition_diagnostics`) **cannot** compose an FE computation — a client-only tray makes Phase C unbuildable. SC11 only bars the **per-node** two-truths server JOIN (thousands of nodes); this is one bounded set-difference, exactly the `pack.py` cross-service read AN-2 blesses. | Yes (the FE could still re-derive it) | |
| D-03 | **Degraded coverage OMITS `unplanned_chapters` rather than sending `[]`**, and the FE type is optional so consumers must branch. | `[]` renders as "nothing unplanned" — a green-looking zero over an unknown. This is the `fe-status-default-fallback` bug class and the same absent≠zero law 24 OQ-8 already applies to drift. Cost: every consumer must handle `undefined`. | Yes | |
| D-06 | **`EntityReferencesRepo`, not `ReferencesRepo.find_by_entity`** (28 AN-3's shorthand). | `ReferencesRepo` ALREADY EXISTS and means the author's REFERENCE SHELF -- a research library with embeddings and a cosine search. Hanging an entity-backlink query off it would put two unrelated concepts behind one name: the exact drift the MCP Tool I/O one-name-one-concept rule exists to stop. The TOOL keeps the spec's name (`composition_find_references`), which is unambiguous at the tool layer. | Yes (a rename) | |
| D-07 | **AN-3's 8 sources map onto `outline_node.kind`, not a `scenes` table.** There is no `scenes` table in composition (the prose scenes live in book-service), and `narrative_thread` has no entity column at all. | `outline_node` holds BOTH chapters and scenes -- which is what AN-1's "the outline pov/present pair splits" means -- so all four node sources stay composition-scoped, exactly as AN-3 requires (no federation in v1). A thread is opened AT A NODE, so an entity's threads are the promises opened where that entity appears: a genuine join, and the question an author actually asks. | Yes | |
| D-08 | **A new locale string is added to `en` + tool-scaffolded; an EXISTING `en` string is NEVER edited.** | `scripts/i18n_translate.py` **gap-fills only** -- it re-translates keys that are missing/broken and KEEPS a valid existing translation (see its `carry` branch). So editing an `en` string that already has 17 translations leaves those 17 **permanently stale against English, silently** -- the tool will never revisit them. I nearly shipped exactly that (an improved `canonIntro`). The new lane announces itself through a NEW key (`canonFromRules`), which the tool does translate. | Yes | |
| D-09 | **`rule_violations` is capped at 200 with an EXACT count + a `capped` flag**, not unbounded. | Rows are FLAT per (scene x violation) and each carries the rule's full text, so a long book multiplies out fast. `pagination-cap-lint` does NOT catch it (there is no client `limit` to clamp -- the lint's blind spot is a route that takes no limit at all). Mirrors `coverage.UNPLANNED_CAP`/`unplanned_capped` and `plan_overlay._REFS_CAP`/`refs_capped`, two files away. | Yes | |
| D-10 | **`composition_diagnostics` gains source (2b), the RULE lane.** | Source (2) reads only the ENTITY lane. Without (2b) an agent asking "what is wrong with this book" could not see a broken author-declared rule AT ALL, while the human's canon panel now could -- two truths for one question. The `SEVERITY`-binds-emitters test written at C-R covers the new kind. | Yes | |
| D-05 | **`compile()` sources genre from `plan_run.genre_tags`** (PF-15), closing the "BPS-20 open sub-question" the code comment itself named. | PF-15's run field IS the explicit field that comment was waiting for. Still no fabricated default — an unset genre stays `[]`, the honest value the old comment insisted on. | Yes | |
| D-04 | **PH18's canon deep-link targets the node's CHAPTER, not the canon RULE** (threads still target the thread id). | The spec says "canon badge → quality-canon filtered to the rule". **That is impossible against the real data model**: the overlay's canon ref is a `canon_rule.id`, and `QualityCanonPanel` lists `CanonIssue` rows carrying `scene_id`/`chapter_id`/`violations[]` and **no rule id at all**. Passing the rule would open the panel and match nothing — a link that looks like it worked, i.e. the exact bug the deep-link exists to fix. The chapter is what that lens *can* resolve, and it is what the user means ("show me the canon problems around here"). Threads are unaffected: `narrative_thread.id` IS what the promises panel lists. | Yes | ✅ **RESOLVED 2026-07-12 — and my premise was WRONG.** "Impossible against the data 
model" was true of the OBJECT I looked at and false of the SYSTEM. A generation job carries TWO 
verdicts: `result.canon.violations[]` (the ENTITY lane -- `canon_check` never loads `canon_rule`, so 
no rule id) and **`critic.violations[]` (the RULE lane -- `judge_prose` is handed the active rules and 
its contract REQUIRES a `rule_id`; `_filter_violations` drops any item lacking one)**. The rule->violation 
link already existed; the panel just surfaced the wrong lane. PO approved **option B**: surface the critic 
lane, forward `focusRuleId`. NOT option C (a `rule_id` on `CanonIssue`) -- that would mean INVENTING a 
rule<->entity attribution that does not exist, plus a backfill. **PH18 was never a spec amendment. It was 
a small build I mis-scoped by reading one object and generalising to the system.** |

## 7. Parked / blocked register — blocked ≠ stopped

> Anything I could not solve. I move on and keep going; the PO reviews these.

| # | Item | Why parked | What would unblock it |
|---|---|---|---|
| ~~P-01~~ | ~~**27 V2-C2 — the `plan_pass` WORKER op**~~ | **UN-PARKED (DR-10).** Parking this was *"missing infrastructure"* mislabelled *"blocked"*. Nothing external gates it: composition-service already runs worker ops I can mirror. **Built in B2b.** | — |
| ~~P-02~~ | ~~**27 V2-D (B3)**~~ | Parked *only* "after P-01" ⇒ unchains with it. **Built in B3.** | — |
| ~~P-03~~ | ~~**27 V2-E3** — bootstrap stamps `outline_node.chapter_id`~~ | Unchains with P-01. | — |
| ~~P-04~~ | ~~**27 V2-F/G (B5)**~~ | Unchains with P-01. **V2-G was independently real all along** (see below). | — |
| ~~P-05~~ | ~~**27 V2-H (B6)**~~ | Unchains with P-01. | — |
| **P-07** | **27 V2-H4 -- the S06 flagship replay gate** (the 17-turn agent-discoverability eval on `gemma-4-26b`). | **BLOCKED (gate #4 -- genuinely external).** A concurrent agent session is actively redeploying `chat-service`: it restarted TWICE during my two attempts (container uptime confirms), and each redeploy 401s the in-flight eval session. Reached turn 8/17 with 4 tool calls, 0 empty-intent -- the harness and the new tools work; the RUN cannot complete while the service under test is rebuilt beneath it. Re-running would also contend for LM Studio with that session. **Not a code defect, and not a coverage hole in the compiler:** the property S06's gate ADDS is "the plan movement ends with linked structure (structure_node + chapter/scene outline_node > 0)", and H3 live-proves exactly that. What stays unproven is whether the AGENT discovers and drives the new tools. | Re-run when no concurrent session is redeploying chat-service: set `JWT_SECRET` + `QG_BASE=http://localhost:8212` + `QG_MODEL_REF=019ebb72-...` + `QG_SCENARIOS=scripts/eval/discoverability_scenarios/S06-flagship.json`, then run `scripts/eval/run_discoverability_scenario.py`. |
| ~~P-06~~ | ~~**The rules-mode parser is hard-bound to the POC fixture.**~~ **FIXED in B5** (`2c0a44a30`) — and it was worse than parked: not "cannot plan a generic book" but "silently plans a DIFFERENT book". See DR-16. | — | — |
| ~~P-06-orig~~ | **(original text)** **The rules-mode parser is hard-bound to the POC fixture.** Numbered `# N.` sections, the literal headers `## Arc 1`/`## Arc 2`, `### Event N`, and **hardcoded Vietnamese themes/summaries per arc**. **A generic book cannot be planned in rules mode at all** — this is a correctness bug, not tech debt. (It is also how B4's linker found a 100%-reproducible upstream bug: Arc-1's events were silently dropped.) | **NOT parked as "blocked" — this is 27 V2-G, and it is in scope.** Kept as a register row because it is a *distinct* correctness defect from the pass runner, and it must not get lost inside "B5 done". | Sever the fixture (V2-G): the parser must key on structure, not on the POC's literal strings. |

## 8. Debt register — knowingly incurred, tracked

| # | Debt | Where | Gate reason (1–5) |
|---|---|---|---|
| DBT-01 | **Row-3 is a non-atomic cross-service saga** — book-service commits, then composition's mirror+canon resync. On a 502 the manuscript is permuted and the mirror stale; the ONLY repair is the user re-issuing the drag. No sweeper, no outbox. | `arc.py:582-640` | #2 structural — needs a resync sweeper |
| DBT-02 | **`chapter_reorder.go` bumps `updated_at` on every chapter in the language track**, perturbing any `sort=updated_at` consumer (the chapter browser's "recently updated" collapses to the reorder timestamp) | `chapter_reorder.go:141-152` | #2 — needs a scoped-run renumber |
| DBT-03 | **`planHub.selection` bus publish** — WON'T-BUILD until a consumer exists (a write-only value is the bug class this repo bans) | `PlanHubPanel.tsx:16` | #5 conscious won't-fix |
| DBT-04 | **React Flow mount-frame size warning** — cosmetic; dockview sizes the panel a frame late. A ResizeObserver mount-gate is real risk for a benign warning. | `PlanCanvas.tsx` | #5 conscious won't-fix |
| DBT-05 | **H7 view modes** (timeline/worldmap) — deferred by PO decision P-10 (v1 narrative-only). *But the "visible but disabled" buttons were a v1 deliverable and are missing — folded into A9.* | `24` PH22 | #3 naturally-next-phase |
| DBT-06 | **`23`-C3 arc inspector does not exist** — the Hub drawer's arc variant is an honest minimal summary rather than a fork | `PlanDrawer.tsx:191` | #4 genuinely-upstream |
| DBT-07 | **FE test files are EXCLUDED from typecheck** (`tsconfig.json` excludes `__tests__`/`*.test.*`). So a contract change cannot red a test that mocks the old shape — the `fixtures-can-seed-a-field-the-writer-never-sets` class, repo-wide. Measured: enabling it yields **1869 errors**, nearly all missing `@testing-library/jest-dom` matcher types in that config. | `frontend/tsconfig.json` | #2 structural — needs a jest-dom types wire-up + a sweep across EVERY feature, in a checkout shared with concurrent sessions. Out of scope for the book-package cluster. |
| DBT-09 | **Deleting a BOOK does not cascade to composition's spec rows.** Observed live: `DELETE /v1/books/{id}` → 204, and this book's `structure_node` / `outline_node` / `plan_run` / `composition_work` rows all SURVIVE (cross-DB, no FK — by design, §1.4). My smoke's orphans had to be reaped by hand. Nothing consumes a `book.deleted` event. | cross-service | #2 structural — needs a `book.deleted` consumer + reaper in composition. Real, but outside this cluster. |
| ~~DBT-08~~ | ~~**`composition_find_references` (28 AN-3) is the drawer's References facet.**~~ **CLEARED** -- the tool shipped in Phase C (`a3abc05a6`) and is live-proven. The FE facet can now call it. | `PlanDrawer.tsx` | -- |
| DBT-12 | **The `studio` i18n namespace is missing ~106 keys in all 17 non-`en` locales** (they ride the component's `defaultValue`, so those users see ENGLISH). Pre-existing. `scripts/i18n_translate.py --ns studio` fills them for free (local model, $0, ~7 min, verified 0 FAILED keys) -- I ran it, then REVERTED all but my own 12 keys: a +3,400-line diff across 18 files is disproportionate to a deep-link fix and collision-prone in a checkout shared with concurrent agent sessions. | `frontend/src/i18n/locales/*/studio.json` | #1 out of scope -- belongs in its OWN commit, not bundled into D-04 |
| DBT-10 | **`_var_deltas` is O(lines x declared-codes) and `source_markdown` has no `max_length`.** The parser is capped at 24 variables (B-R2 MED-5), which bounds it -- but the FIELD is still unbounded on the way in, so a multi-megabyte braindump is accepted and parsed. | `routers/plan_forge.py:34` | #2 structural -- a body cap belongs at the gateway/router layer for EVERY large-text field, not one-off here |
| DBT-11 | **No composition tool declares `paid` except `plan_run_pass`.** `plan_propose_spec`, `plan_apply_revision` and `plan_compile(run_pipeline=true)` all spend real LLM money and are undeclared (pre-existing; the `_meta` Completeness Law is status PROPOSED). I declared it on the tool I ADDED rather than silently matching the omission. | `mcp/server.py` | #1 out of scope -- a service-wide `paid` audit belongs with Track D's WS-D0/D1, not this cluster |

## 9. Drift log — the near-misses, recorded honestly

> **A run that ends with an empty drift log is not clean — it is dishonest.**

| # | Drift | Caught by | Correction |
|---|---|---|---|
| DR-01 | I reported **"all defers cleared"** — true of the tracked list, but the tracked list only ever described Stage 7's *polish*. It said nothing about the ~20 unbuilt spec-24 requirements. **Clearing a defer list ≠ completing a spec.** | The PO asking for a completeness audit | This RUN-STATE now boards the spec, not the defer list |
| DR-02 | I claimed **"Rows 1/2/4/5 ship"**. Row-5 (draw a scene-link edge) is **not built in the FE at all** — what shipped was the backend enum hardening. | The same audit | Slice A7; claim corrected to 4 of 18 rows |
| DR-03 | I shipped a **manuscript-corrupting bug** (Row-3 undo → chapter 1 on any >100-chapter book) one hour after live-proving Row-3 — because I asked for `{limit: 500}` and trusted a server that clamps to 100. | The audit, not my own review | Fixed `749805ca6`; invariant §3.4 added |
| DR-04 | **The A-R commit collided with a concurrent session.** I ran `git add` (31 files) and `git commit` as **two separate** shell calls, to check nothing leaked. In that window the other agent committed — and `git commit` takes the whole *shared* index, so my 31 A-R files were swallowed into **`09f2d29b1` "feat(chat): T-4 ratified"** (43 files: my 31 + their 12). **Nothing is lost and the tree is correct**, but the commit message misdescribes half its contents. Not rewriting history: another session is live on this branch. | Noticed immediately (`git commit` said "no changes added") | Invariant §3.7 amended: add+commit must be ONE command. Recorded here so the audit trail is truthful about where the A-R work lives. |
| DR-06 | **I introduced a closed-set drift in B1** — `PlanPassId` used `motif/beat/char_arc/scene/heal`; the spec's sealed enum is `motifs · cast · world · beats · character_arcs · scenes · self_heal`. A closed-set value that drifts from the spec is the Frontend-Tool-Contract bug: the agent passes the documented value and the server 422s. | Reading 27 §170 while building B2 | Fixed before anything consumed it (`b0eafe205`); the live smoke then showed the 7 correct ids on the wire. |
| DR-07 | **The green unit suite did NOT exercise the linker.** After wiring the skeleton link into `compile()`, 1965 tests passed — and exactly ONE test invokes `compile()`, in the INTEGRATION suite, which is among the **251 SKIPPED**. I nearly took that green as proof. | Checking WHICH test covers the new path instead of trusting the count | Live-smoked instead; it found two real bugs in minutes (Arc-1 event drop; `status='active'` violating the CHECK). `env-gated-integration-tests-skip-and-the-green-suite-lies`, verbatim. |
| DR-08 | **My HIGH-1 fix was WRONG, and only the live smoke could tell me.** The preserve branch dropped the row from the version ledger, so the next link saw "no prior record" and clobbered the human. I fixed it by recording the row's **current** version — which is the same bug wearing a mask: the next compile's guard then *equalled the human's version*, `version <= guard` was TRUE, and the update fired. The human survived exactly **one more compile**. My unit test asserted the ledger got *a* value; it could not know *which* value was right. The 2-compile smoke I ran first showed a green `preserved_user_edit: 1` and I nearly shipped on it. | A **5-compile** smoke — because the bug is invisible at 2 and 3 is the first compile that shows it | The ledger means *"the version this row had immediately after **OUR** last write"*. A preserve is **not** a write, so it carries the **PRIOR guard** forward unchanged. `_settled()` now derives preserve-vs-no-op from the **version alone** (exact), where the arc had been comparing **content** (a proxy that mislabelled an edit-and-revert). |
| DR-09 | **I fixed the arc's no-op guard in A-R and did not carry it to the chapters and scenes.** `_UPSERT_ARC` gained `IS DISTINCT FROM` so an unchanged arc doesn't bump its version; `_UPSERT_CHAPTER`/`_UPSERT_SCENE` never got it. So every no-op compile bumped every chapter and every scene: it staled every ETag the user held (their next edit 412s), and made the `unchanged` counter **structurally unreachable** — it could never be non-zero, and I had been reading `updated: N` as normal. **Fixing a bug class in one place is not fixing the bug class** — the *same lesson as DR-05*, and I repeated it inside the same run. | Reading the smoke's counters instead of just its PASS/FAIL — `unchanged: 0` on a compile where nothing changed is a contradiction I had to actually *look* at | Guard added to all three; a test now asserts the DISTINCT column set **equals** the DO-UPDATE SET column set for every upsert, so a new column can't silently escape the guard. |
| DR-10 | **I parked P-01..P-05 as a chain rooted in "the pass worker op isn't built."** That is *"missing infrastructure"* dressed as *"blocked"* — the exact tell CLAUDE.md's anti-laziness rule exists to kill. The worker op is **buildable in this repo today** (composition-service already runs worker ops I can mirror); nothing external gates it. Parking it would have parked **the entire point of Stage 6** — a compiler whose passes cannot run — behind a word. | Re-reading §7 against the anti-laziness rule after the compaction, as the run rules require | **P-01 UN-PARKED and built** (B2b). P-02/P-03/P-04/P-05 were parked *only* "after P-01", so they unchain with it. |
| DR-11 | **`UpstreamStale` was not a BUSINESS error.** It subclasses `Exception`, not `ValueError`, so it was outside the worker's `_BUSINESS_ERRORS`. A blocked pass would have propagated as an INFRA error, the AMQP message un-ACKed, and the broker would have redelivered a pass that was *correctly refusing to run* — forever. "Your upstream is stale" is the PF-5 gate doing its job, the most ordinary condition in the compiler. | Reading the worker's error taxonomy while wiring the dispatch, not a test | Added to `_BUSINESS_ERRORS` + a test that asserts it is there AND is not incidentally caught by one of the others. |
| DR-12 | **I looked the planning package up under kind `"planning_package"` — which is not a member of `PlanArtifactKind` at all.** So the lookup could never match, and every package-reading pass was unrunnable behind a message that blamed the USER ("compile first") for something they had already done. The kind is `"package"` — and the package is NESTED inside that artifact, so even the right kind would have handed the adapters the WRAPPER, and a degrade-safe adapter would have planned a book with no premise, no arc, no chapters, and reported it as a success. **The type is a `Literal`, but at runtime it is just a string**, and no unit test ran the worker against a real row. **Second closed-set drift of this run** (DR-06 was the first). | The live smoke, on the first run | `PACKAGE_KIND` + `package_body()` — one constant, one reader, pinned to the Literal by a test that makes a third drift impossible. |
| DR-13 | **`record_pass()` REQUIRED `status`, while its own docstring promised "fields left `None` are UNTOUCHED".** The signature contradicted the contract, so a DECISION-ONLY write was impossible — accepting a pass changes the decision, not the status, and there was no honest value to pass. The accept 500'd. | The live smoke | `status` is now optional like every other field; a test pins that a decision write leaves status, the artifact pointer and the fingerprint untouched (that pointer is what every downstream pass resolves through). |
| DR-14 | **The PF-7 gate ran AFTER the edit was written.** With `approved=true` + `edits`, the edit persisted and *then* the seed gate refused — a 409 for a call that had already mutated the user's plan. **A partial success reported as a failure is the worst of both**: the user retries, and the retry re-applies the edit on top of itself. | The live smoke (the 409 was "correct", so only looking at what it had already DONE showed the bug) | The gate runs before any write ⇒ a refused checkpoint is ATOMIC. Test pins the ordering. |
| DR-15 | **`plan_forge_service` had no module logger at all**, so `_bind_roster`'s log line 500'd the request — *after* every write had committed. Same class as DR-14: the caller saw a failure for work that had entirely succeeded. | The live smoke | Added the logger. Two instances of "500 after commit" in one slice is the tell that I was not thinking about what the caller SEES when a late line throws. |
| DR-16 | **I parked P-06 as "the rules parser can't plan a generic book" — the truth was far worse.** It did not fail on an unseen book; it **silently returned a plan for a DIFFERENT book**: another novel's state variables, its protagonist's personality, its plot-secret forbids, its arc titles. Every downstream pass then planned faithfully against that charter. I had even *seen* the symptom and not recognised it — my own B4 smoke's arc came back titled "Arc 1", and I read that as the parser echoing my markdown when it was the HARDCODE. A confident wrong answer is the worst failure mode there is: it does not crash, it does not return empty. | Actually READING `propose.py` when I sat down to sever it, rather than trusting my own park note | Fixed in B5. And the parked note itself was the drift: a park is a claim about *what is wrong*, and mine was wrong. **Re-read the code before trusting a park you wrote yourself.** |
| DR-17 | **The validator was checking the fixture against itself.** `arc2_discovery` asserted `arc_kind == "discovery"` — a value the PROPOSER hardcoded. The rule could not fail, for any document, ever. A tautology dressed as a golden criterion, sitting in the suite looking like coverage. | Severing the proposer made it go red — which is the only reason anyone would ever have noticed | It is advisory now, and what gates compile is structural (`spec_has_arc`, `spec_has_events`). A rule whose subject is a constant is not a test. |
| DR-25 | **My C-R "fix" was itself a regression, and I caught it during the DoD recheck.** AN-2's text says the `.runs/` block is owner-keyed and a non-owner must get it "absent + a warning… **until** 25 OQ-3's VIEW resolution lands" — so at C-R I owner-filtered it and called it a MED. But **OQ-3 HAS landed**: 00B §1.4 records it shipped, in the same breath as "also unblocks 28-AN-2's `runs` block", and its decision is *default VIEW*. `list_for_book` has carried no owner predicate ever since. So I "fixed" against a sentence written BEFORE the thing it was waiting for, re-narrowing a scope the spec had deliberately widened and hiding a collaborator's legitimate view of their own book's planning history. | The Phase-D per-pillar DoD recheck, reading 00B's status stamps against my own diff | Reverted. **A doc sentence is a claim about the world AT THE TIME IT WAS WRITTEN — check the world.** This is DR-16's lesson exactly, and I walked into it a second time, in the review that was supposed to be the catch-net. |
| DR-23 | **Five bugs in Phase C, every one found by the LIVE MCP smoke and none reachable from a unit test.** The tools 404'd a book whose Work was still PENDING backfill (`resolve_by_book` excludes it BY DESIGN, and its own docstring says len==0 must fall through, not deny -- a book with a pending Work still HAS a spec tree, because `structure_node`/`outline_node` are book-keyed). The MCP envelope carries NO user JWT, so every book-service read needed the service-bearer seam. `CompositionWork` has no `title`. `canon_rule`'s column is `text`, not `rule_text`. `list_for_book` returns a (rows, cursor) TUPLE. **Four of the five surfaced as honest WARNINGS rather than silent zeros** -- the absent-not-zero posture catching my own bugs while I had the field names wrong, which is exactly what it is for. | The live smoke, through the real MCP transport | Fixed. And the reason to drive the REAL transport rather than the python function: `tools/list` advertising is itself a contract (AN-10), and a tool that works in-process but 404s over MCP is not a tool. |
| DR-24 | **I declared an ERROR-severity diagnostic kind and never emitted it.** `SEVERITY` carried `prose_deleted_spec_node` while no source produced it, so the problems panel silently never checked the highest-severity class it has -- and an agent asking "what is wrong with this book" got a confident answer with a hole in it. **A problems panel with a silent gap is worse than no panel: the reader believes the count.** The dead map entry was the only visible tell. | `/review-impl` (C-R), counting AN-4's five sources against the four I had written | The test now binds the severity map to the emitters: a kind cannot be declared and forgotten, nor emitted without a severity. |
| DR-18 | **The SERVICE and the WORKER disagreed about whether a pass could run.** `character_arcs` has `reads_package=False`, so the worker skipped loading the package -- but it DEPENDS on `cast` and `beats`, which both read it, so their fingerprints were recomputed with `package_artifact_id=None`, could not match, and read as STALE. The service returned 200 and enqueued the job; the worker then refused it, naming two upstreams the ledger showed as fresh and accepted. Two components answering one question with different inputs. | The full 7-pass live smoke -- nothing smaller reaches a pass that does not read the package but depends on ones that do | The package is a property of the RUN, not of the pass being run. Always loaded. |
| DR-19 | **The "LOSSLESS round-trip" test passed while never exercising the field that broke.** `ChapterExitState` is a DATACLASS, not pydantic; `.model_dump()` raised inside the scene_plan serializer, and because that is an INFRA error the message was un-ACKed and REDELIVERED three times before the pass died. My test's fixture set `exit_state=None`. **A fixture that omits the hard case is a test that passes for the wrong reason** -- and it had "LOSSLESS" in its name. | The live run, on pass 6 | The fixture now carries a real exit_state, asserted explicitly so nobody can quietly weaken it back. |
| DR-20 | **The scenes had NOBODY IN THEM, and everything else looked perfect.** The `cast` artifact holds NAMES; the glossary ids do not exist until the human applies the seed. Nothing joined them, so `grounded_decompose`'s `cast_index` (which keys on `entity_id`) was empty, every scene returned `present_entity_ids: []`, and the linker wrote scene nodes with no cast. The characters WERE in the glossary; the roster WAS bound to the arc; the plan was complete in every other respect. | Reading `present=0` in the smoke's own output instead of just its PASS/FAIL | The roster join runs before any pass reads the cast. An unresolvable member keeps its name and gets NO invented id. |
| DR-21 | **I exposed `force` on the agent's tool while that same tool's description promised the model it could not skip a checkpoint.** I wrote both lines in the same commit. An agent that hits a 409 listing its blockers does not stop -- being helpful is what it is FOR -- so PF-6, the one structural guarantee in the design, was a speed bump the model could step over whenever it felt stuck. | `/review-impl` (B-R2), reading my own tool description against my own signature | Enforced by ABSENCE now. **A guarantee stated in a prompt is not a guarantee.** |
| DR-22 | **My own smoke's failure was a bug in the SMOKE, and I nearly "fixed" the code for it.** `character_arcs`/`scenes` came back blank, so I assumed a missing `motifs` run. Wrong twice: the real cause was that a re-run never marks a pass `running`, so my poll saw the PREVIOUS run's `completed` instantly and accepted mid-flight. Had I trusted my first theory I would have shipped a script change and left a real HIGH in the product. | Refusing to accept my own hand-wave, and writing a diagnostic that printed EVERY http code | Diagnose, do not theorise. The blank status was the evidence; my explanation for it was not. |
| DR-05 | **`/review-impl` found 3 HIGH — and two were bugs I created *while fixing* other bugs.** `useBookChapters` re-introduced the exact cold-open budget violation A11 had removed, **one commit later**, with the budget test green (it summed the allowed calls and never asserted the forbidden ones). And A4/A5's "the deep-link seam was dead" fixed the canvas half while the *consumer* half — the panels reading `props.params` — was equally dead. **Fixing a bug class in one place is not fixing the bug class.** | The review, not me | All 14 findings fixed in-phase (see `09f2d29b1`). The budget test now asserts what must NOT fire, not only what may. |
| DR-26 | **I told the PO a spec requirement was IMPOSSIBLE, and it was not.** D-04: "PH18's rule-filtered canon deep-link cannot be built -- `CanonIssue` carries no rule id." True of that object. But I never asked whether a DIFFERENT producer already carried the rule -- and one did, fully rule-keyed end to end, with a `dismiss-violation` endpoint already addressing violations BY RULE. I generalised from one object to the whole system and escalated a small build to the PO as a spec amendment. **"Impossible" is a claim about the system; check the system, not the first object you opened.** | The PO asking "so let's overview data model" -- the question I should have asked myself | Option B shipped. The rule lane was 200 lines away the whole time. |
| DR-27 | **My own panel told users their book was clean when it had never checked it.** `QualityCanonPanel`'s two composition queries are `enabled: !!projectId`; with no project they never run, resolve to `[]` with NO error, and `empty` computed TRUE -> **"No canon issues found."** -- over a book whose canon was never examined. It does this when the Work is pending, absent, **or when composition-service is DOWN**. Its 3 sibling quality panels already guard this via `QualityNoWorkState`; canon was the only one that never adopted it. **NOT hypothetical: all 8 Works in the dev DB are `pending_project_backfill`, so the panel was lying about every book on it.** And one test in the file had PINNED the false-clean as correct (it asserted the empty state with the work left unresolved). The bitterest part: `composition_diagnostics` -- which I wrote in Phase C -- guards this exact case with the comment *"'no problems found' over sources we never queried is the single most dangerous thing this tool can say."* **The agent got the honesty. The human did not.** | `/review-impl` (D-04), then the LIVE smoke 404ing and my chasing WHY instead of swapping in a book that worked | Unconsulted != clean: `compositionUnknown` gates `empty`; `unavailable` and `no-work` get distinct banners; a rule deep-link into an unchecked book no longer says "nothing has broken it". |
| DR-28 | **I re-derived a solution that already existed, and my version was WORSE.** Fixing the sibling quality panels I wrote a shared `useQualityWork` gate -- and only during `/review-impl` found `useSceneBrowser.ts:43` had solved the identical problem first, with the identical reasoning already in a comment (*"that is NOT 'no plan yet', so it must not show the create-plan CTA (a user could make a duplicate Work)"*). Worse: **the pre-existing one handled `candidates` and mine did not.** `WorkResolution.status` has SIX values; every other consumer (`CompositionPanel`, `OutlineTree`, `usePublishGate`, `useSceneBrowser`) resolves `candidates` by taking the first Work. Mine dropped it into `no-work`, so a book that HAS Works was told *"no co-writer session yet -- start composing a chapter first"* -- inviting exactly the duplicate Work that comment warns about. **AMBIGUOUS IS NOT ABSENT**, the twin of *unconsulted is not empty*. | `/review-impl`, running the SDK-First check (">=2 users ⇒ one implementation") instead of assuming I was first | `useQualityWork` is now THE gate; `useQualityCanon`, the 3 panels, `QualityHubPanel` and `useSceneBrowser` all consume it. **Before grepping for the bug, grep for whether someone already fixed it.** |
| DR-29 | **The quality HUB carried the same collapse** -- and it fronts all four panels. `hasWork = status === 'found'` meant a composition-service outage rendered *"start composing a chapter first"* at the entry point to the very panels I was fixing. Found only because `/review-impl` asked "is there any REMAINING consumer that still collapses unavailable into no-work" -- the question I had not asked myself when I declared the fix done. | `/review-impl` (phase 2) | Hub adopts the gate; `quality-hub-unavailable` is a distinct state with its own test. |

## 10. Completeness ledger

**Verified 2026-07-12 against the LIVE DB + the live MCP surface — not against this file's own notes.**
(DR-16 is why: a park note is a *claim*, and mine was wrong. Every row below was re-checked by query.)

| Pillar | DoD (00B §6) | Met? | Evidence (live) |
|---|---|---|---|
| `22` scene seam | scene index reads; `source_scene_id` filter | ✅ pre-existing | `loreweave_book.scenes` carries `book_id` + `source_scene_id` |
| `23` book architecture | `structure_node` spec tree; BA12 packer reach; roster_bindings | ✅ | `structure_node.roster_bindings` present; **PF-13 proven BY EFFECT** — change the binding ⇒ the PACKED PROMPT changes |
| `24` plan hub | the ACTION half + the audit's fix-now tier | ✅ **Phase A** | 13 slices, `/review-impl` (3H/7M/4L), live smoke. `b904b3a74` + `09f2d29b1` |
| `25` migration | the lift; the M-steps | ✅ | legacy `arc` table **GONE**; **M6.1 swap live** (`outline_chapter_written_kinds`) — which is what makes a "planned, not yet written" node insertable at all |
| `26` indexing | `arc_conformance_state`; IX-14's ONE staleness computation | ✅ | table present; **IX-14's helper is COMPOSED by 3 consumers** (its route, AN-2's `.index/`, AN-4's source 1) — never re-derived |
| `27` compiler | the 7-pass compiler, checkpoints, the link step | ✅ **Phase B** | `pass_state`+`genre_tags` live; 4/4 provenance cols; **LIVE: `pass_cursor 7/7`**, both human checkpoints, glossary through the quarantine, 6 scenes linked with tension + resolved cast, E3 stamps 2/2 |
| `28` agent-native | the 3 composition R tools | ✅ **Phase C** | all 3 **ADVERTISED in `tools/list`** and live-called over the real MCP transport; `package_tree` 553 chars/~138 tok |

**The one thing NOT met:** the **S06 flagship replay** (27 H4 / 28 AN-D3) — 🅿️ **P-07**, blocked
externally (a concurrent session redeploying `chat-service` under the run). What it would ADD over
what is proven is the *agent-discoverability* leg: does the model FIND and DRIVE these tools. The
structural property its gate names — "the plan movement ends with linked structure" — is live-proven
by H3.

---

## 11. Final audit

### What shipped

The book-package cluster is **built and live-proven end to end**. A book can now be taken from a
braindump to a linked, cast-populated, scene-level plan with a manuscript under it — and an agent can
orient in it, search it, and be told what is wrong with it.

Ten commits: `b904b3a74` `09f2d29b1` (A) · `a4558ed44` `b0eafe205` `e813f7200` `f5ca7ecf8`
`51707e29f` `6ef793f3f` `2c0a44a30` `47bddd8d9` `b99b38b6b` (B) · `a3abc05a6` `54ae6c72a` (C).
**2067 tests pass**, 251 skipped.

### The four `/review-impl` passes found 9 HIGH — and every one was mine

| | The finding | Why it matters |
|---|---|---|
| A-R | 3 HIGH (incl. a budget violation I re-introduced ONE COMMIT after fixing it) | fixing a bug class in one place is not fixing the bug class |
| B-R | 3 HIGH — PF-11 reclaimed the author's edit one compile later; **my first fix was itself wrong**; a no-op compile bumped every version | a 2-compile smoke shows a GREEN `preserved_user_edit: 1` while the human is overwritten on the 3rd |
| B-R2 | 3 HIGH — **the agent could FORCE past the human's checkpoint**; re-running a pass broke the compiler; a re-run silently ATE the author's acceptance | I wrote a tool description promising the model it could not skip a checkpoint, and handed it `force` in the same commit |
| C-R | 1 HIGH — the problems panel silently skipped its **ERROR-severity** source | a panel with a silent gap is worse than no panel: the reader believes the count |

### What the LIVE smokes caught that a green suite could not

**Fourteen bugs.** Every one of them passed unit tests.

The pattern is not subtle, and it is the single most useful thing this run produced:

- **DR-07** — 1965 tests green, and exactly ONE test invoked `compile()`. It was in the *integration*
  suite, which is among the **251 SKIPPED**. I nearly took that green as proof.
- **DR-19** — a test named "LOSSLESS round-trip" whose fixture set the one field that broke to `None`.
- **DR-18** — the service said a pass was runnable and the worker refused it. Two components
  answering one question with different inputs; nothing smaller than the full 7-pass chain reaches it.
- **DR-20** — the scenes had **nobody in them**, and everything else looked perfect.

### Decisions (§6) — 7, of which 1 is ⚠ PO-DECIDE

`D-04` is the one the PO should look at: 24 PH18 asks for a canon deep-link "filtered to the rule",
and that is **impossible against the data model** (`CanonIssue` rows carry no rule id). I deep-linked
by the node's CHAPTER — the lens that *can* resolve — and flagged it. If you want rule-level
filtering, `CanonIssue` needs a `rule_id`, and PH18 becomes a spec amendment.

`D-06`/`D-07` are places the SPEC's shorthand was wrong and following it would have been the bug
(`ReferencesRepo` already means something else; there is no `scenes` table in composition).

### Drift (§9) — 24 entries. **This is the honest part.**

Six of them are cases where I was the bug: a closed-set value I drifted **twice** (DR-06, DR-12); a
fix that was itself wrong (DR-08); a bug class I fixed in one place and not the sibling (DR-09); a
guarantee I stated in a prompt and then handed the model the key to (DR-21); a park note that was a
*claim*, and wrong — the parser did not "fail on a generic book", it **silently planned a different
one** (DR-16).

And DR-22: my own smoke's ❌ was a bug in the SMOKE, and I nearly "fixed" the code for it. Refusing
my own hand-wave and writing a diagnostic that printed every HTTP code is what found the real HIGH.

### Debt (§8) — 3 new, all gate-eligible

`DBT-10` (unbounded request body — belongs at the router layer for every large-text field, not
one-off), `DBT-11` (a service-wide `paid` audit — Track D's), and `DBT-09` (book delete does not
cascade to composition — cross-service, real, outside this cluster).

### Parked (§7) — 1

`P-07`, the S06 replay. External, precisely scoped, with the exact command to re-run it.

### The one thing I would tell the next agent

**Read `propose.py` before trusting anything it produced.** The compiler was, for its entire life,
returning one specific Vietnamese novel's characters, variables, forbids and arc titles for *every*
book anyone planned in rules mode — and it never failed, never returned empty, and never looked
wrong. A confident wrong answer is the worst failure mode there is, and the only reason it surfaced
is that the linker (BPS-18: *an emitted artifact with no linker is a bug*) finally tried to write the
compiler's output somewhere real.
