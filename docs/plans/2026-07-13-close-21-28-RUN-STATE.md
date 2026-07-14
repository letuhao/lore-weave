# RUN-STATE — Close specs 21–28 to Definition-of-Done

> ## 📌 READ THIS FILE FIRST after any compaction, then `git log --oneline -15`, then continue.
> The plan is [`2026-07-13-close-21-28-plan.md`](2026-07-13-close-21-28-plan.md) — its **§6.6 SEALED
> LEDGER** is binding; **never re-derive a sealed decision from memory.** This file is the live
> board; the plan is the contract.

**Started:** 2026-07-13 · **Branch:** `feat/context-budget-law` · **Mode:** long unattended, self-checkpointing.
**Goal (durable copy):** every pillar 21–28 satisfies its `00B` §7 named effect test + its own spec's
ship gate, proven by PASTED output; `/review-impl` per phase, findings fixed in-phase; live smoke for
≥2-service phases; `git log` after each phase; seeds reaped; §6–§9 registers current.

## The autonomy contract (from the goal)
- **Don't stop** between slices/phases. Self-checkpoint: `/review-impl` → fix → VERIFY → commit → update this file.
- **NEVER `git add -A`** (shared checkout). `git add … && git commit …` = **ONE** command.
- **Do NOT touch** specs 29+ or the 30–38 wave build — the other session's, after we clear.
- **Clean up** every seeded row + throwaway DB, proven by a count query.
- **I decide** ordinary calls → §6 (decisions). Genuinely-PO → reversible option, ship, flag ⚠ PO-DECIDE in §7, keep going.
- **Blocked ≠ stop** → park in §7, move on.
- **STOP only if** destructive/irreversible, or a sealed 00A law / §6.6 decision turns out wrong.

## Invariants (the bar; §7 of the plan)
1. Green unit suite ≠ proof — ≥2-service slices need a live smoke with pasted output.
2. A fix needs a test that REDS on the old code.
3. A checked slice ≠ a done pillar — the evidence string is the named effect test.
4. `/review-impl` per phase; findings fixed in that same phase.
5. Never `git add -A`; add+commit is ONE command.
6. Absent ≠ zero; a silent success is a bug.
7. Re-read a park note before trusting it.
8. An empty drift log is dishonest.
9. Rebuild + `--force-recreate` before believing a live result (stale image = false green).

---

## 5. Slice board — `done` = an evidence string, never a claim
Legend: `[ ]` todo · `[~]` in progress · `[x]` done+evidence · `🅿️` parked (→ §7)

### PHASE 0 — the inherited tree (BLOCKS everything) — ✅ DONE
| # | Slice | Status | Evidence |
|---|---|---|---|
| S0.0 | Baseline: full suite green with the 96 dirty files | [x] | composition **2106 passed/289 skip**; FE **5130 passed**, 2 fail files = 3 chatParity (theirs, allowed) + PlannerPanel (fixed below); no Go service dirty (D-CL-02) |
| S0.1 | Triage the 96 files → adopt / leave-theirs | [x] | Adopted: composition BE (`89629ced1`) · studio FE (`5d4ae91a3`) · token-lint tooling (`f7948d442`). LEFT dirty (theirs, off-limits): their planning/status docs + 3 `chat-service/tests/*.py`. D-CL-01/03. |
| S0.2 | `/review-impl` the adopted diff; fix findings this phase | [x] | **2 findings, both fixed in-phase:** (1) PlannerPanel.test mock missing `useOptionalStudioHost` → 12/12 (`5d4ae91a3`); (2) **HIGH — BE-7c half-fix**: `mineConfirm` still polled the Work-gated `/jobs/{id}` (404 forever on the unbound mine); repointed to `/motif-jobs/{id}` + guard test (`be4d72abf`). tsc clean. |
| S0.3 | Commit in attributed chunks | [x] | 4 adopt/fix commits + my plan/RUN-STATE (`745753f88`). Tree clean of my concerns. |

> ⚠ **Phase-2b O-2 prerequisite (from S0.2):** `arc_import` (analyze_reference) is the SAME Work-less
> lane as mine, but has **NO FE poll leg yet** (agent-only today). When O-2 builds the decompiler FE,
> its poll MUST use `compositionApi.getMotifJob` (`/motif-jobs/{id}`), never `getJob` — or it 404s
> exactly the way mine did.

### PHASE 1 — the three real bugs
| # | Slice | Status | Evidence |
|---|---|---|---|
| B1 | AN-C2 discovery scent (`stream_service.py`) — unblocks P-08→S06→DoD of 23/27/28 | 🅿️ | **PARKED → §7 P-B1** — chat-service is LIVE-owned by the other session (it committed `90c3ba8cc` mid-run). Cannot edit `stream_service.py` without a DR-04 collision. |
| B2 | Canonical-Work predicate (`agent_native.resolve_scope`) — write 25-T4 RED first | [x] | `9a9ec24e8` · 25-T4 RED on `marked[0]`, GREEN after using `resolve_canonical_work`; composition 2112/289. |
| B3 | `arc_lift` startup fail-loud assertion (Q2 sealed) | [x] | `9a9ec24e8` · auto-lift clean DBs + `_assert_lift_applied` fails loud on rekey-without-lift. **LIVE**: fresh throwaway DB → born LIFTED (`kind IN ('chapter','scene')`, both markers, no trip); throwaway dropped (0 left). Unit tests pin both marker states. |
| B4 | C5 — is `POST /works/{pid}/generate` ungated-spend reachable? | [x] | **Investigated → DEFER + ⚠ PO-DECIDE (§6 D-B4).** Reachable ONLY from the legacy editor (`App.tsx:134` route), NOT the studio (`ComposePanel` is chat-only — imports `@/features/chat/Chat`, no `/generate`). Streaming cowrite/ghost can't take a per-call confirm (UX); the surface is Wave-6-retiring; the correct gate (per-work spend budget / opt-in + discrete-generate confirm) is the compose-path wave, tracked as W3-3c / D-COMPOSE-GENERATE-UNGATED (PO decision sheet). ⚠ **NOT proven fail-closed at a guardrail** — stated honestly, not claimed. |

### PHASE 2 — the missing test batteries (`25` T3/T4/T5/T6)
| # | Slice | Status | Evidence |
|---|---|---|---|
| T4 | Derivative-separation — book-scoped read returns CANONICAL Work (RED on today's resolve_scope, GREEN after B2) | [ ] | |
| T3 | Grantee-widening — incl. F5 zero-pending-forks regression (PM-9's untested claim) | [ ] | |
| T5 | Spend attribution by effect on the usage row | [ ] | |
| T6 | The re-key cross-service live smoke (O-4) | [ ] | |

### PHASE 2b — the 5 REAL orphans (§6.4)
| # | Slice | Status | Evidence |
|---|---|---|---|
| O-1 | Ground the PlanForge proposer (LLM: digest · rules: pre-flight) — by EFFECT | [ ] | |
| O-3 | BA11's 5 arc-template CRUD MCP tools (+ fix the misquote at server.py:4546) | [ ] | |
| O-11 | The what-if branch preview producer (+ fix wave-6's false parity row) | [ ] | |
| O-2 | The arc decompiler (26-D3/IX-17) — depends on Work-less lane from Phase 0 | [ ] | |

### PHASE 3 — live BROWSER smoke (`24`-H8.2) — also closes `26`-F2
| # | Slice | Status | Evidence |
|---|---|---|---|
| H8.2 | Playwright: open plan-hub → drag chapter → DB structure_node_id changed → badge updates | [ ] | |
| H8.1 | 10k-chapter fixture + cold-open budget + EXPLAIN keyset proof | [ ] | |
| F2 | 26's Hub leg: edit→publish→dirty:prose_drift→conformance clears it, in the browser | [ ] | |

### PHASE 4 — S06 flagship replay (ship gate of 23/27/28)
| # | Slice | Status | Evidence |
|---|---|---|---|
| S06 | IN-CONTAINER replay (depends on B1) → 23-D7 · 27-H4 · 28-D3 | [ ] | |
| EV | 27's eval report → `docs/eval/plan-forge/` (regression floor + 5 v2 grounding metrics) | [ ] | |

### PHASE 5 — `22`'s remaining DoD
| # | Slice | Status | Evidence |
|---|---|---|---|
| D5 | Anchor-direction: no `outline_node.scene_id`; deleting a scene leaves spec intact | [ ] | |
| D4 | Tenancy: collaborator B sees shared spec, no per-user fork (fold into T3) | [ ] | |
| D3 | Committed E2E: import→scenes→decompile→backlink→tension=80→adaptive_k high-tension | [ ] | |
| F3 | 26-F3: one-word edit preserves every back-link; re-import never clobbers authored | [ ] | |

### PHASE 6 — close-out
| # | Slice | Status | Evidence |
|---|---|---|---|
| C0 | Land `legacyParityContract.test.ts` as a REAL file — 25/25 → panel id or retirement reason | [ ] | |
| C1 | Re-homing amendment (incl. §6.4 orphans, by name) | [ ] | |
| C2 | Disposition all 12 orphans (owner + next action) | [ ] | |
| C3 | Resolve the `resource_ref` name collision in 28 AN-12.1a | [ ] | |
| C4 | Doc fixes: PH9 C5 stale claim · IX-3 sweeper-predicate · PH2 reactflow · RUN-STATE false rows | [ ] | |
| C5 | 00B §7 status stamps + SESSION_HANDOFF; cleared defers → "Recently cleared" | [ ] | |
| C6 | Final audit (decisions · drift · debt · parked · completeness) | [ ] | |

---

## 6. Decisions register (I audit these at the end)
| # | Decision | Why | Reversible |
|---|---|---|---|
| D-CL-01 | **Phase 0 adopt = commit the green tree in attributed chunks, do NOT surgically split it.** The 96 files are green *together*; splitting a green tree risks breaking green at high token cost. Commit by concern-group, attributed to the Wave-0 session, so the tree is clean (kills the DR-04 collision hazard) and nothing is lost. `/review-impl` focuses on the parts we BUILD ON (BE-7c, G1, OpenAPI parity). | Clean tree unblocks all phases; adopting ≠ building 30+ (it is already-built green code). | Yes — `git revert` a chunk |
| D-CL-02 | **No Go service is dirty** (verified `git status`), so Phase 0 is Python + FE only; the Go suites are unaffected and not re-run at adoption. | Scope the baseline to what changed. | n/a |
| D-CL-03 | **Leave the OTHER session's planning/status docs + `chat-service/tests` DIRTY, don't adopt them.** They own their status ("họ tự update sau"); chat-service is explicitly off-limits. Dirty docs pose no collision risk to code work (I won't edit them). | Respect their ownership; don't misattribute their in-flight status. | Yes |
| D-CL-04 | **BE-7c FE poll fix = repoint FE (option B), NOT owner-scope the generic `/jobs/{id}` (option A).** The Wave-0 session made `/jobs/{id}` deliberately 404 unbound jobs (`engine.py:1444`, "Its route is /motif-jobs/{id}") — a sealed design choice. Honor it; repoint the one live unbound leg (`mineConfirm`), leave getJob's Work-gate intact for collaborator VIEW grants. | Don't fight their sealed design; keep one route = one gate mode. | Yes |
| D-B3 | **The arc-lift assertion HARD-FAILS boot** (not a warning), but run_migrations **auto-lifts a CLEAN DB** first so fresh/test DBs are born consistent. The risky data-lift (legacy DBs with real arc rows) stays operator-invoked; the assertion catches only "post-lift code deployed onto a legacy pre-Deploy-2 DB." | Q2 sealed "fail loud"; the auto-lift resolves the fresh-DB/test-DB breakage without touching legacy data. | Yes |
| D-B4 | ⚠ **PO-DECIDE — C5 ungated /generate spend: DEFER, don't bolt a confirm onto a retiring surface.** Reachable only from the legacy editor (not the studio's chat-based compose); streaming cowrite can't take a per-call confirm; the surface is Wave-6-retiring; the real fix (spend budget/opt-in + discrete-generate confirm) is the compose-path wave (W3-3c, tracked). Chose the reversible option (defer) over negative work. | A confirm on streaming cowrite is wrong UX; a confirm on a dying surface is O-12-class negative work. | Yes — the compose-path wave lands the real gate |

## 7. Parked / blocked
| # | Item | Why | Unblocks when |
|---|---|---|---|
| **P-B1** | **B1 — AN-C2 discovery scent** (`services/chat-service/app/services/stream_service.py`) + its downstream **S06 replay leg** (Phase 4, DoD of 23/27/28) | The plan assumed chat-service was UNOWNED (the other session had stopped). **FALSE — the other session is LIVE in chat-service**: it committed `90c3ba8cc fix(chat-tests)` mid-run, between my own commits. Editing a large shared file under a live concurrent session is the exact DR-04 collision hazard the run's rules forbid. **Blocked, not stopped** — every other phase is composition-service/FE (mine) and proceeds. | The other session confirms stopped in chat-service (PO re-confirms), OR the PO explicitly authorizes editing stream_service.py despite the concurrency. Then B1 is a ~20-token one-line prompt edit + a guard test; S06 runs after. |
| **P-CONC** | **The book-service / glossary-service slices — T6 (Phase 2), O-2 (Phase 2b), 26-F2 (Phase 3), D3 (Phase 5)** | The other session is **LIVE-editing book-service + glossary-service** right now (verified `git status`: `services/book-service/internal/api/server.go`, `glossary-service/internal/api/mcp_server.go` + new files, all dirty). These slices write/smoke across those services → a cross-session DR-04 collision on a shared file. **Composition-service is still clean, so composition-only slices proceed** (T3, T5, O-1, O-3, C0). | The other session leaves book-service + glossary-service (PO confirms, or `git status` shows them clean). Then T6/O-2/F2/D3 run — they are built-ready, just collision-gated. |
| **P-P34** | **Phase 3 (24-H8.2 live browser smoke) + Phase 4 (S06)** | Phase 3's Playwright smoke drives the live studio which talks to book-service (contended, P-CONC); Phase 4 (S06) is gated on B1 (P-B1, chat-service). Both are cross-service live smokes into services the other session is actively editing. | P-B1 + P-CONC clear. |

## 8. Debt (carried from prior RUN-STATE)
DBT-01 (row-3 saga no sweeper) · DBT-02 (chapter_reorder updated_at) · DBT-04 (RF mount warn) ·
DBT-05 (H7 view modes = O-10 v2 cut) · DBT-07 (FE tests excluded from tsc) · DBT-09 (book.deleted no
cascade). DBT-06 (arc-inspector) → re-homed to spec 32 by C1.

## 9. Drift log — the near-misses, recorded honestly
| # | Drift | Caught by | Correction |
|---|---|---|---|
| DR-A | Marked `C2/C3 [x]` using C3's evidence for both; C2 never built; parked P-08 blaming chat-service for my own hole | this audit | B1 |
| DR-B | Shipped a tenancy bug the spec forbade (28:502-510); the test that catches it (25-T4) I never wrote | this audit | B2 + T4 |
| DR-C | Dropped spec 21 from the pillar board; PH7/PH8/G1/G2 tracked by nobody | PO asking "wasn't it 21–28?" | plan §2 |
| DR-D | My orphan register went stale within hours — read 30–38 but not the concurrent wave-*.md; 5 of 12 already homed | the triage agent | §6.4-CORRECTION |
| DR-E | **The other session is STILL LIVE despite being asked to stop.** It committed `90c3ba8cc` (chat-tests) between my `f7948d442` and `be4d72abf`. Nothing of mine was lost (linear history; add+commit-as-one-command held), but the plan's premise "chat-service is now unowned" is false. | The unexpected commit in `git log --oneline` after Phase 0 | **P-B1 park**; verify index-clean before EVERY commit (already the rule); surfaced to PO. |

## 10. Completeness ledger (filled at the end)
*(per-pillar: 21 · 22 · 23 · 24 · 25 · 26 · 27 · 28 → DoD test → evidence string)*
