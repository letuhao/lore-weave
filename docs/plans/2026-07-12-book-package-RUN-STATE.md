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
| A1 | **24-H1.3 coverage-diff helper** — the real `unplanned_chapters` (book chapters ∌ spec nodes). ONE implementation, exported for 28-AN-4. **Unblocks Stage C.** | [ ] | |
| A2 | **PH21 unplanned tray + empty state** — render `layout.unplanned` (computed, unit-tested, never drawn); 2 CTAs (`materialize-scenes` route already exists) | [ ] | |
| A3 | **Window pagination is unreachable** — `loadMoreArc`/`hasMore` exported, never consumed ⇒ an arc renders only its first 100 chapters and 101+ are **unmovable** | [ ] | |
| A4 | **Fix-now debt tier** — actual-state read failure silently neutralises the 3-state treatment; drawer's Canon/References/Critic stubs (overlay is already in memory); no cold-open loading state; stale "404 until 26 ships" comments; `refs_capped` computed + never surfaced | [ ] | |
| A5 | **PH18 deep-links** — canon→`quality-canon`, thread→`quality-promises`, drift→arc conformance. `onOpenRef` is a seam nobody wires (and a comment falsely claims `PlanCanvas` wires it) | [ ] | |
| A6 | **PH13 stub connectors** — an edge whose endpoint is in a collapsed arc is handed to RF with a nonexistent node id and **silently dropped** (the exact failure PH13 forbids) + rollup edge-count badge | [ ] | |
| A7 | **PH20 row 5 — draw/delete a scene-link edge** (`nodesConnectable={false}` today; no `onConnect`; `createSceneLink` absent from the FE api) | [ ] | |
| A8 | **Cast chips (H4.4/PH26)** + missing-vs-truncated split — `NodeContent` drops `present_entity_ids`, which is already on the wire | [ ] | |
| A9 | **Node/arc action rail + Hub toolbar** (PH15's 9 Action seats, OQ-7 "Ask AI about this plan") | [ ] | |
| A10 | **Drawer writes** (PH20) — rename/status, add chapter/scene/arc, archive/restore, tension edit, ⚓ re-anchor, motif bind/unbind, **"Open in Editor"** (PH16 calls this contract *fixed*) | [ ] | |
| A11 | **H8.1 cold-open ≤5-request budget** — currently VIOLATED: `useActualState` eagerly pages the whole book scene index. Assert the budget in a test. | [ ] | |
| A12 | **Coverage** — `usePlanHub`, `usePlanWindows`, `useActualState`, `PlanHubPanel` have **no tests**; they own the generation/`complete`/identity guards that exist because these bug classes bit before. Backend: `POST /chapters/reorder` + `conformance/status` have no route tests. | [ ] | |
| A13 | **PH25** — the navigator is a column inside the panel, not an **Activity Bar tab**; rail rows lack every specced decoration | [ ] | |
| A-R | **`/review-impl` Phase A + fix all findings + commit** | [ ] | |

### PHASE B — Stage 6 (`27` PlanForge v2 multi-pass compiler)
*The biggest slice. Restores the trunk order. `00B` §6.0 is a hard pre-build gate.*

| # | Slice | Status | Evidence |
|---|---|---|---|
| B0 | **25 M-step registration (NC-4 pre-build gate)** — 27-V2-A3's `outline_chapter_required` → `outline_chapter_written_kinds` swap is **non-additive** and MUST register as a numbered M-step in `25` before building (mints M6) | [ ] | |
| B1 | **27-V2-A** — `pass_state`/`genre_tags`, CHECK swaps, provenance columns + partial uniques, the A3 swap | [ ] | |
| B2 | **27-V2-B ∥ V2-C** — contracts unfixturing (PF-14/BPS-21) + `genre_tags` plumbing ∥ pass runner + `world_plan.py` + pass-4 hoist + adapters | [ ] | |
| B3 | **27-V2-D** — `propose_seed` quarantine wiring + checkpoint extension + `roster_bindings` write (PF-13) | [ ] | |
| B4 | **27-V2-E (incl. E2b)** — the link step: skeleton link at compile + scene link at pass-6/7 + bootstrap `chapter_id` stamp; linkers stamp `source='planforge'` | [ ] | |
| B5 | **27-V2-F ∥ V2-G** — 3 MCP tools + HTTP mirrors + OpenAPI ∥ fixture severing (PF-19) | [ ] | |
| B6 | **27-V2-H** — unit + effect tests + **H3 cross-service live smoke** + **H4 S06 replay gate** (pillar-27 DoD) | [ ] | |
| B-R | **`/review-impl` Phase B + fix all findings + commit** | [ ] | |

### PHASE C — Stage 8 (`28` agent-native studio)
*Needs A1 (the shared coverage helper). AN-B already shipped.*

| # | Slice | Status | Evidence |
|---|---|---|---|
| C1 | **28-AN-A** — `composition_package_tree` (+4K-token budget test) · `ReferencesRepo.find_by_entity` + `composition_find_references` · `composition_diagnostics`. **Composes** 26-C3's status helper + **A1's coverage helper — never a second computation.** Canonical-Work scoped. | [ ] | A1 |
| C2 | **28-AN-C** — the spec→prose recipe contract test over 22-A4's `source_scene_id` filter · orientation sentence in the studio `book_context_note` · discovery-registration checks | [ ] | |
| C3 | **28-AN-D** — D1 cross-service live smoke · D2 effect tests · **D3 the S06 flagship replay gate** (pillar-28 ship signal) · D4 xdist marks | [ ] | |
| C-R | **`/review-impl` Phase C + fix all findings + commit** | [ ] | |

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

## 7. Parked / blocked register — blocked ≠ stopped

> Anything I could not solve. I move on and keep going; the PO reviews these.

| # | Item | Why parked | What would unblock it |
|---|---|---|---|
| — | *(none yet)* | | |

## 8. Debt register — knowingly incurred, tracked

| # | Debt | Where | Gate reason (1–5) |
|---|---|---|---|
| DBT-01 | **Row-3 is a non-atomic cross-service saga** — book-service commits, then composition's mirror+canon resync. On a 502 the manuscript is permuted and the mirror stale; the ONLY repair is the user re-issuing the drag. No sweeper, no outbox. | `arc.py:582-640` | #2 structural — needs a resync sweeper |
| DBT-02 | **`chapter_reorder.go` bumps `updated_at` on every chapter in the language track**, perturbing any `sort=updated_at` consumer (the chapter browser's "recently updated" collapses to the reorder timestamp) | `chapter_reorder.go:141-152` | #2 — needs a scoped-run renumber |
| DBT-03 | **`planHub.selection` bus publish** — WON'T-BUILD until a consumer exists (a write-only value is the bug class this repo bans) | `PlanHubPanel.tsx:16` | #5 conscious won't-fix |
| DBT-04 | **React Flow mount-frame size warning** — cosmetic; dockview sizes the panel a frame late. A ResizeObserver mount-gate is real risk for a benign warning. | `PlanCanvas.tsx` | #5 conscious won't-fix |
| DBT-05 | **H7 view modes** (timeline/worldmap) — deferred by PO decision P-10 (v1 narrative-only). *But the "visible but disabled" buttons were a v1 deliverable and are missing — folded into A9.* | `24` PH22 | #3 naturally-next-phase |
| DBT-06 | **`23`-C3 arc inspector does not exist** — the Hub drawer's arc variant is an honest minimal summary rather than a fork | `PlanDrawer.tsx:191` | #4 genuinely-upstream |

## 9. Drift log — the near-misses, recorded honestly

> **A run that ends with an empty drift log is not clean — it is dishonest.**

| # | Drift | Caught by | Correction |
|---|---|---|---|
| DR-01 | I reported **"all defers cleared"** — true of the tracked list, but the tracked list only ever described Stage 7's *polish*. It said nothing about the ~20 unbuilt spec-24 requirements. **Clearing a defer list ≠ completing a spec.** | The PO asking for a completeness audit | This RUN-STATE now boards the spec, not the defer list |
| DR-02 | I claimed **"Rows 1/2/4/5 ship"**. Row-5 (draw a scene-link edge) is **not built in the FE at all** — what shipped was the backend enum hardening. | The same audit | Slice A7; claim corrected to 4 of 18 rows |
| DR-03 | I shipped a **manuscript-corrupting bug** (Row-3 undo → chapter 1 on any >100-chapter book) one hour after live-proving Row-3 — because I asked for `{limit: 500}` and trusted a server that clamps to 100. | The audit, not my own review | Fixed `749805ca6`; invariant §3.4 added |

## 10. Completeness ledger — filled at the end

| Pillar | DoD (00B §6) | Met? | Evidence |
|---|---|---|---|
| `22` scene seam | | | |
| `23` book architecture | | | |
| `24` plan hub | | | |
| `25` migration | | | |
| `26` indexing | | | |
| `27` compiler | | | |
| `28` agent-native | | | |
