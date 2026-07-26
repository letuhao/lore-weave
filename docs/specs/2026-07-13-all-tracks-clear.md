# Tracks A/B/C/D — CLEAR spec (empty every track's parked list)

**Status:** DESIGN — **all decisions RESOLVED (PO, 2026-07-13). Zero open questions. Ready to BUILD.**
**Date:** 2026-07-13 · **Branch:** `feat/context-budget-law`
**Scope (PO):** clear **all four tracks** — because Track C's scenarios only pass if their backing capabilities in A/B/D are real. **Maximal scope: build everything, defer nothing.** All 18 scenarios green; the W11 reader; the W10 maps canvas; every gap in A/B/D closed; every stale doc reconciled.
**Umbrella:** [`docs/specs/2026-07-09-agent-discoverability-and-workflow/`](2026-07-09-agent-discoverability-and-workflow/) · **Board:** [`tracks/BOARD.md`](2026-07-09-agent-discoverability-and-workflow/tracks/BOARD.md) ·
**Track-C run that got us here:** [`docs/plans/2026-07-12-track-c-completion-RUN-STATE.md`](../plans/2026-07-12-track-c-completion-RUN-STATE.md) ·
**W10/W11 backend design (BUILT — status field never flipped):** [`2026-07-11-w10-w11-world-container-and-reader-backends.md`](2026-07-11-w10-w11-world-container-and-reader-backends.md)

---

## 0. The headline finding (28-agent adversarial audit, 2026-07-13)

**The code is essentially built across all four tracks. The drift is in the docs — in BOTH directions.** The tracking docs (board, briefs, completion docs, design-spec status fields) are systematically stale because concurrent sessions shipped code without reconciling them.

**The reassurance on your core worry:** *no scenario is blocked on an unbuilt A/B/D backend.* The scenarios are blocked on **scenario JSON + content fixtures + a few Track-C FE surfaces** — all Track-C-side.

| Track | Doc claims | Verified reality |
|---|---|---|
| **A** Mechanism spine | "✅ COMPLETE, remaining: none" | ~complete. **One confirmed gap:** the tier-tag CI gate was never built (per-service tests only — and the Python ones don't even run in CI). "Missing `skill_list`/`skill_load`" was **inverse-drift**: the capability shipped as `registry_list_skills`/`registry_get_skill` (Tier-R, federated). 2 sub-items unverified (#6 gated-reason, F3 floor). |
| **B** Domain backend | "CLOSED **except W8/W10/W11**"; spec: "awaiting sign-off before BUILD" | **W10/W11 fully BUILT, tested, wired** — reader facade (server-enforced cutoff, resolve-to-owner, fail-closed, 9 tests), reading-position resolver, **public canon-only lore route with a `status='active'` leak-guard test**, world write tools, `kg_create_node`, maps (8 tools + 3 tables + MinIO). Only `story_search`'s cutoff absent. **The rest is doc drift.** |
| **C** User-facing/catalog | board "~35%" | Far past it: consent DONE, rail-driver DONE, catalog 10/10, S06 passes §4. Real remainder = **scenarios + 3 FE surfaces + maps canvas + bugs + fixture seeder + docs**. |
| **D** Tool liveness | claims done; completion doc header says "PLAN (not started)" | **Code done, ZERO gaps.** Three pure doc-staleness drifts (paid "~25"→10; `web_search_client.py` "deleted"→keyless relay, invariant intact; completion-doc header + numbers stale). |

---

## 1. What "all four tracks cleared" means (the DoD)

Cleared when **every track's parked list is empty AND its docs match its code**:

1. **All 18 scenarios green.** S00a, S00b, S00c, S00d, S00e + S01, S02, S03, S04, S05, S06, S06b, S07, S08, S09, S10, S11, S12 — each **authored as runnable JSON** and **passing ≥2/3 consecutive runs** on the gemma rail, scored by **DB ground truth**. **No parked tail.** A scenario below ≥2/3 is **fix-or-escalate** (root-cause the real rail bug; a true model-capability ceiling STOPs for a PO call with measured numbers) — **never** a silent park.
2. **Every FE surface exists and is proven BY EFFECT** in a real browser: workflow rack, binding UI, W11 lore-seeker reader, **W10 maps canvas**.
3. **Every code gap in A/B closed:** Track A's tier-tag CI gate (+ #6 gated-reason, F3 floor if genuinely missing); Track B's `story_search` cutoff.
4. **Every bug fixed:** `D-2-ONTOLOGY-BLOAT`, `D-2-CHAPTER-PAGINATION`, `D-2-PROSE-BLOCKS-BACKFILL`, `D-P1-EVAL-SPEND-FIXTURE`. **Nothing won't-fixed.**
5. **Every stale tracking doc reconciled to code.** A track is not "clear" while its own docs lie about it.
6. **S06 stays green** — its §4 DoD is a regression gate.

**Non-negotiable invariants:** ground-truth beats self-report; live-smoke any slice touching ≥2 services; verify code is IN the container before believing a live run; no silent no-op/success; consumed-by-effect; tenancy scope-key + fail-closed anti-oracle on every reader path; **grep before trusting any list — including this one.**

---

## 2. Verified true state per track

### Track A — 1 confirmed gap + 2 unverified + 1 doc reconcile
- **BUILT:** `tool_list`/`tool_load` (TS+Py lockstep + drift-lock), `ALWAYS_HOT_WRITES`, workflows table + propose/approve + HITL, step-runner + async guard, C4 envelope, WS-6 demotion, WS-0 enum.
- **CONFIRMED GAP:** **tier-tag CI gate** — no central cross-service script asserting write tools carry non-R `_meta.tier`. SDK validators only check *presence* (R passes); the Python tier tests aren't in CI (`foundation-ci.yml` Python job is byte-compile only). **M9a.**
- **UNVERIFIED (verify → build if missing, D-5):** #6 gated-reason at the public edge; F3 reserved-output floor. **M9c.**
- **REFUTED (inverse-drift):** `skill_list`/`skill_load` → shipped as `registry_list_skills`/`registry_get_skill`. **Doc/alias reconcile only (M9b).**

### Track B — fully built; 1 XS gap + doc drift
- **BUILT (no stubs/TODOs):** W11-M1 reading-position resolver; W11-M2 reader facade (`lore_ask`/`lore_browse_entities`/`lore_entity`/`lore_timeline` — cutoff **server-enforced from the reader's own position, never an LLM arg**, resolve-to-owner, fail-closed, 9 tests, registered in all 3 lockstep sources); **W11-M3 public canon-only lore route** (`GET /unlisted/{token}/lore`, explicit `status='active'` leak-guard + test); W10-M1 world tools + `kg_create_node`; W10-M2 maps backend; WS-4A/4B/4C; rename/delete; `/v1/chat/capabilities`; `glossary_confirm_action` (FE-rendered by design).
- **GAP (D-1 → BUILD):** `story_search` lacks the optional `before_chapter_id` cutoff `raw_search` has. **M7c.**
- **Doc drift:** spec status field + board both say "not built." **M10.**

### Track C — the bulk
- **BUILT:** Phase-1 consent (D3/D4/D7 signed off), Phase-2 mechanism, P-1 step-runner, WS-5 10/10 rails, S06 §4 DoD, W8 onboarding FE, W10 world-container FE, the W11 reader **backend**.
- **GAP:** 13 scenarios unauthored/unrun; S04/S05 fixture-blocked; **no content-fixture seeder**; 3 FE surfaces + the maps canvas; 4 bugs; **S06 beat-F unsettled** (RUN-STATE §10 says 5/5; §11 + the v2-gate run say 4/5, `chapters=0` — **the docs contradict each other; M0a settles it**).

### Track D — done; doc reconciliation only
- **BUILT:** spend gate (+ `test_spend_gate.py`), `_meta.paid` kit, glossary `_meta` + wire gate, `web_search` on provider-registry + legacy alias + `research` category, propose-lints ×3 services, TLE harness, manifest + drift-locks, `validateWorkflow` ship gate, tool withdrawal, matrix (211/224, 0 broken), FE-tools e2e.
- **DOC-ONLY:** paid "~25"→10; `web_search_client.py` "deleted"→keyless relay; completion-doc header/numbers. **M10.**

---

## 3. Bugs — ALL FIXED, nothing won't-fixed (PO 2026-07-13)

| ID | Verdict | Fix |
|---|---|---|
| **D-2-ONTOLOGY-BLOAT** | REAL | Project attrs to counts/summaries **preserving `base_version`** (patch's OCC token) + kind/genre codes; mirror `standardKind`. Red-first wire test under the WARN ceiling. **M4.** |
| **D-2-CHAPTER-PAGINATION** | REAL | Optional `offset`/`limit` + `truncated`/`next_offset`; full-body default when omitted. **M0c** (the reader FE needs it). |
| **D-2-PROSE-BLOCKS-BACKFILL** | REAL — **now FIX (D-6, reversed from won't-fix)** | One-shot backfill of `chapter_blocks` for legacy drafts (or lean on the `chapter_raw_objects.body_text` OR-branch the query already has). Makes `prose-state` exact for ALL books — it feeds the rail driver's book-state probe. **M4.** |
| **D-P1-EVAL-SPEND-FIXTURE** | REAL | Declare the extract spend-grant in the warm-setup fixture. **M0b.** |
| **P-2** (4 stale tool-count tests) | Another session's — **now FIX OURSELVES (D-4)** | One-line assertion bump ×4. ⚠️ Violates shared-checkout invariant #9 — **flag loudly in RUN-STATE + the commit** so the owning session doesn't double-fix. **M4.** |
| ~~D-P1-EXTRACT-CHAIN~~ | STALE | Retire the row (DR17 was the real cause). **M10.** |

---

## 4. Milestones (one continuous run; checkpoint at each risk boundary)

Each milestone: red-first tests → build → VERIFY (**pasted** ground truth / live-smoke) → `/review-impl` → fix-in-phase → checkpoint + `git log --oneline`.

| M | What | Size |
|---|---|---|
| **M0a** | **S06 beat-F — settle the contradiction FIRST.** Fresh S06 run on a SQL-provably-empty book; **paste the SQL**. Trust neither §10 nor §11. Then make `composition_generate` land the drafted chapter reliably + **drive-past-async** at the `STOP_ASYNC` arc-plan boundary (own WHERE, not WHEN — DR8/DR9). Unblocks the 5th artifact + S06b/S12. | M |
| **M0b** | **Content-fixture seeder** (`scripts/eval/`): S04 (lore + 0 prose) · S05 (partial translation coverage) · approved-plan (S06b/S12) · canon-contradiction (S09). Fold the eval **spend-grant**. | M |
| **M0c** | **D-2-CHAPTER-PAGINATION** (the reader FE needs paged reads). | S–M |
| **M1** | **S00e** — consent journey (deny ⇒ blocked; revoke ⇒ re-suspend). Cheapest real win; closes drift DR3. | S–M |
| **M2** | **Scenarios S00a, S00b, S00c, S00d, S06b, S07, S08, S09, S12** — author + run ≥2/3 each. All backings built; **this is where real rail bugs surface — fix in-phase.** | L |
| **M3** | **S04 + S05** (needs M0b). | S |
| **M4** | **Bugs:** ontology-bloat · prose-blocks backfill · P-2 test fixes (flag the collision). | M |
| **M5** | **Workflow rack FE.** Build-time: confirm/add a **gateway/BFF route** — `/internal/workflows` is service-to-service (gateway invariant). Proven by effect. | M |
| **M6** | **Binding UI FE.** SET-1..8: effective value + source tier; consumed-by-effect; per-user tenancy (System defaults admin-only). | M |
| **M7** | **W11 reader** — (a) lore-seeker FE facade on the existing prose reader, consuming the live `lore_*` tools; **fail-closed proven in-browser** (fresh reader sees NO spoilers). (b) **S11** scenario. (c) **`story_search` cutoff** (D-1). *Backend already built — a major shrink.* **Mandatory adversarial review** (public/spoiler surface). | L |
| **M8** | **W10 maps (D-2 → IN):** `/v1/worlds/{id}/maps` CRUD REST + **FE canvas** (base image, pins bound to `location` entities, polygon regions). Then **S10** scenario. *Backend already built.* | L |
| **M9** | **Track A:** (a) **tier-tag CI gate** — central cross-service script + wire into CI on all branches + **fix that the Python `_meta` tier tests don't run in CI**. (b) skills naming reconcile (`registry_*` ↔ `skill_*`). (c) verify #6 gated-reason + F3 floor; **build if missing** (D-5). | M |
| **M10** | **Doc reconciliation, all four tracks:** BOARD.md · W10/W11 spec status → BUILT · TRACK-D-COMPLETION.md (header + 211/224 + paid=10 + `web_search_client`=relay) · RUN-STATE §11 + WS-5 count drift · retire `D-P1-EXTRACT-CHAIN` · TRACK-C-AUDIT.md · SESSION_HANDOFF.md. | S–M |

**Order:** `M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9 → M10`.
Dependencies: S11 runs after M7's FE · S10 after M8's canvas · S06b/S12 after M0a+M0b · S04/S05 after M0b · M7 after M0c.

---

## 5. Scenario → dependency map

| Scenario | Blocked on | Lands in |
|---|---|---|
| S01, S02, S03 | — (**passing**) | regression only |
| S06 | beat-F drafted chapter for a clean 5/5 | M0a |
| S00a–S00d | runnable JSON only (mechanisms built) | M2 |
| **S00e** | JSON + one gemma journey (**cheapest**) | M1 |
| S06b, S12 | JSON + approved-plan fixture | M0b → M2 |
| S07 | JSON (W7 rail seeded) | M2 |
| S08 | JSON (onboarding FE **built**) | M2 |
| S09 | JSON + contradiction fixture | M0b → M2 |
| S04, S05 | content fixture (JSON **exists**) | M0b → M3 |
| S10 | JSON + maps canvas (**world backend + FE built**) | M8 |
| S11 | reader FE facade + JSON (**backend built**) | M7 |

**No scenario is blocked on an unbuilt A/B/D backend.**

---

## 6. Decisions — ALL RESOLVED (PO, 2026-07-13). No open questions.

| # | Decision | Resolution |
|---|---|---|
| **D-1** | `story_search` cutoff | **BUILD it (XS)** — 3 sites: MCP signature, `StorySearchArgs`, `_handle_story_search` → `run_hybrid_search(before_sort_order=)`. Track B becomes literally spec-complete. |
| **D-2** | W10 maps FE canvas | **IN SCOPE** — `/v1/worlds/{id}/maps` CRUD REST + the canvas (M8). Backend already built. |
| **D-3** | Scenario set under all-green | **ALL 18** — S00a–e + S01–S12 incl. S06b. No parked tail. |
| **D-4** | P-2 (concurrent session's 4 stale tests) | **FIX OURSELVES** — ⚠️ knowingly overrides shared-checkout invariant #9; **flag loudly** in RUN-STATE + the commit so the owning session doesn't double-fix. |
| **D-5** | Track A #6 gated-reason + F3 floor | **VERIFY, BUILD if missing** — clearing A means closing its whole DoD. |
| **D-6** | `D-2-PROSE-BLOCKS-BACKFILL` | **FIX** (reversed from won't-fix) — one-shot legacy backfill; `prose-state` feeds the rail driver's probe, so exactness matters. |
| **D-7** | Spec filename | **RENAMED** to `2026-07-13-all-tracks-clear.md` (this file). |
| *carried* | Run shape · scenario bar | **One continuous run** · **all-green ≥2/3** (PO, earlier). |

**Nothing is won't-fixed. Nothing is deferred. Nothing is parked.**

---

## 7. Risks & the honest tail

- **The dominant "gap" was doc drift, and doc drift hides real state.** This audit only happened because the docs lied in both directions. **M10 exists so the next reader doesn't have to re-audit.** A run that ends with the board/briefs still stale has not cleared the tracks — it has only moved the lie.
- **The all-green bar has teeth.** A scenario stuck below ≥2/3 blocks "clear" — deliberately, to force out the real rail bug instead of parking a flake. The failure mode to watch: burning the run "fixing" model variance that is actually a driver/directive gap. Root-cause it. A true capability ceiling STOPs with numbers.
- **S06 beat-F is genuinely unsettled** (§10 vs §11 disagree). M0a settles it with a fresh pasted-SQL run *before* anything downstream trusts the drafting path.
- **The W11 public lore route + the reader FE are the highest-risk surfaces** — a spoiler leak or a cross-tenant lore leak is worse than no reader. Built with a `status='active'` leak-guard test, but M7's review must **re-prove fail-closed + anti-oracle + canon-only against a live run**, not trust the test alone.
- **Shared checkout, and we're now knowingly touching another session's files (D-4).** Enumerate files on every commit; never `git add -A`; flag the P-2 fix loudly so we don't collide.
- **Scope is maximal by choice.** Every option was taken at its build-everything setting. That is the right call for a *clear* — but it is XL+, and the honest expectation is a long run with several real bugs surfaced by M2 and M7.
