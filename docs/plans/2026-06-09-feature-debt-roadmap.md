# Feature-Debt Roadmap — composition/LOOM branch (`feat/composition-service`)

> **Created:** 2026-06-09 (LOOM-62 audit) · **HEAD:** `1edb777f` · **PR #19** open → `main`.
> **Status:** PLAN ONLY (PO 2026-06-09 — write the roadmap, build nothing yet; PO greenlights each cycle).
> **Scope:** FEATURE incompleteness **inside this branch's domain** (composition / knowledge / learning / worker-ai / FE / sdks). Other-track debt (tilemap, geo, game-server, enrichment P2/P3, provider-registry, glossary, tooling) is explicitly OUT — those have their own tracks.
> **Method:** grounded by a 3-agent audit (spec-vs-code, deferred+markers, FE). Every row cites file:line evidence.

---

## How to read this

"Incomplete" splits into three *kinds*, and they are NOT equally urgent:

- **🔴 Phase 1 — Half-built (feature LIES).** Code exists + looks wired, but is a no-op / inert / dormant-prompt. These masquerade as complete; they are the genuinely bad debt. Fix regardless of strategy.
- **🟡 Phase 2 — Long-form reasoning engine (Phase B).** Designed in the spec but **deliberately gated** behind "only build if A wins" (reasoning-engine spec §8 validate-first). A's coherence validation **saturated the metric** (lesson: eval-metric-saturation), so building this blind is the exact trap. EVAL-GATED, lower confidence. Prioritized internally per the lesson *"the real lever is F2/narrative_thread state-reinjection, NOT Phase-B recipes"*.
- **🟢 Phase 3 — Polish / UX / hardening.** Real but LOW/MED; usability + latent-bug cleanup.

> **Production-ready principle (PO 2026-06-09):** this is a production product, not a toy build. There is **no "intentional seam we just skip"** — every designed-but-unbuilt escape valve, every dormant flag, every "deferred to a later session" marker gets an explicit **decision before go-live: prove-it-is-needed (measure), build-it, or consciously remove-it**. "Benign-by-design" is only acceptable once it's a *recorded decision*, not a silent gap. The audit's borderline/intentional items are therefore tracked as real rows (FD-21…FD-26), not excluded.

**Spec SSOT:** `docs/specs/2026-06-05-composition-v1-reasoning-engine.md`. **Sub-plans:** `docs/plans/2026-06-05-composition-v1-phase-a.md`, `docs/plans/2026-06-06-comp-longform-state-reinjection.md`.

**Merge relationship:** PR #19's close-out roadmap is COMPLETE; the branch has zero *tracked-as-blocking* debt. This roadmap is the *next* body of work. Per-phase merge guidance is noted below — the PO decides whether any Phase-1 item is a merge-blocker or a fast-follow.

---

## 🔴 Phase 1 — Half-built honesty fixes (feature appears done but is a no-op)

| ID | Feature gap | Evidence | Size | Eval-gated? | Notes / dependency |
|---|---|---|---|---|---|
| **FD-1** | **narrative_thread is INERT** — schema+repo shipped (cy14, full ledger per PO), but **zero callers**: nothing opens/pays threads, nothing re-injects, `generation_job.state` JSONB has 0 readers/writers (dead column). | `db/repositories/narrative_thread.py` (def only, no caller); `db/migrate.py:156-185`; grep `open_thread\|list_open\|NarrativeThreadRepo` → repo-only | L (minimal-runnable) / XL (full S2-S4) | YES for the consumer arm | **PO already chose "build full ledger" — leaving it inert is self-contradictory.** Minimal-runnable = a producer that opens threads (rule or LLM) + `list_open` re-injected into the pack. This is the seam to Phase-2 FD-6/7/8 (same work, just scoped). Recommend doing the *minimal-runnable* slice here so the branch isn't lying, and the deeper detection/eval as Phase 2. |
| **FD-2** | **Chat→KG extraction is a no-op** — worker-ai chat-turn path passes `text=""` (chat-service exposes no message-text endpoint) → `extract_pass2` short-circuits to empty; no chat knowledge is ever extracted. | worker-ai `app/runner.py:1561-1579` | M (cross-service: chat-service + worker-ai) | NO (correctness) | Needs a chat-service message-text fetch endpoint OR an honest decision to disable+document the dead path until that exists. Cross-service → live-smoke token required. |
| **FD-3** | **Scene-leaf summary uses placeholder text** — `_load_scene_leaf_texts` returns Neo4j `path` strings instead of real scene prose from book-service; summarization quality silently degraded. | knowledge `app/jobs/summary_processor.py:381,391,406-407` | M (cross-service: knowledge + book) | partial (quality) | Needs book_client wiring to fetch real scene prose. Cross-service → live-smoke. |
| **FD-4** | **status_effect prompt is DORMANT** — the `:EntityStatus` parser + model exist, but no extraction prompt asks the model to emit status_effects → deaths may never reach KG status. This is the producer half of DEFERRED 066/067. | sdk `loreweave_extraction/extractors/event.py:83,110,518` ("Dormant until A2-S1b-2"); DEFERRED 066/067 | M | YES (prompt-compliance eval; local LLM first) | **First do DEFERRED 067 live diagnostic** (one real death-chapter extraction + read `status_effect_total` metric) to confirm it's prompt-dormancy vs a code path. Then activate the prompt + measure. Local-LLM-first (lesson). |
| ~~**FD-5**~~ ✅ DONE | ~~full context mode may be unbuilt~~ — **VERIFIED STALE DOCSTRING (LOOM-63):** `builder.py:63-64` dispatches `build_full_mode` on `extraction_enabled`, no `NotImplementedError` remains, full-mode is built + reached in prod. Fixed the stale "Commit 1 scaffold" docstring. No gap. | knowledge `app/context/modes/full.py` | XS | NO | Done — docstring corrected. |
| **FD-21** | **MCP tool-call path unproven live** — `USE_MCP_TOOLS` default must NOT flip to true until a real chat-service → knowledge-service `/mcp` tool call (e.g. `memory_recall_entity`) succeeds on a docker stack-up (real Streamable HTTP + JSON-RPC init + header scope). Unit suites are mock/loopback only. | DEFERRED 056 | M (cross-service: chat + knowledge) | NO (live-smoke gate) | Production-ready gate: a wired-but-never-live-proven feature path. Live-smoke token required. Decision: prove → flip default; or keep default-false + document. |
| ~~**FD-22**~~ ✅ DONE | ~~Worker-notification "deferred to K16.6"~~ — verified: worker already **polls** (K16.6 landed as polling, works). **PO chose to BUILD the push-notify** (not just close the seam): knowledge XADDs a best-effort Redis wake (`extraction.wake`) on job-start; worker-ai blocks on it (`XREAD BLOCK`) instead of a blind sleep → ~immediate pickup. Wake-over-poll (poll stays source-of-truth → no double-process); degrades to polling on any Redis fault. Plan: [2026-06-09-fd22-extraction-wake.md](2026-06-09-fd22-extraction-wake.md). /review-impl: 2 MED fixed (block=0 hang floor, cross-service stream-name pin), 2 LOW documented. Live-smoke PASS (real Redis :6399). | knowledge + worker-ai | L (reclassified from XS) | live-smoke | Done LOOM-63. |

**Phase-1 order:** FD-5 + FD-22 (cheap verifies, may be non-issues) → FD-4 (067 diagnostic then activate) → FD-1 minimal-runnable → FD-3 → FD-2 → FD-21 (MCP live-smoke gate). FD-2/FD-3/FD-21 are cross-service and depend on upstream endpoints/stack-up — may slip if chat/book endpoints or a bootable stack aren't ready.

**Merge guidance:** FD-1 (narrative_thread not-lying) and FD-4 (status producer) are the strongest "should this be in PR #19" candidates since the PO chose to build the ledger and the canon-death arc. FD-2/3/5 are platform gaps not specific to the composition V1 arc → fast-follow is fine.

---

## 🟡 Phase 2 — Long-form reasoning engine (Phase B) — EVAL-GATED, validate-first

> ⚠️ **Strategy gate (spec §8):** the spec says build Phase B *only if Phase A wins coherence*. A's validation **saturated** (coherence 5/5 both arms on short scenes — lesson `eval-metric-saturation`). So this whole phase is a **bet**, not a known-good. Each item MUST ship behind a discriminating eval (correction-rate / dropped-promise-rate / contradiction-rate — NOT a ceiling-prone coherence median). Prioritized per lesson: **F2/narrative_thread state-reinjection is the real lever; craft_recipe + recipe-checks are speculative and ranked last.**

| ID | Feature (spec §) | Status | Size | Priority | Eval signal |
|---|---|---|---|---|---|
| **FD-6** | narrative_thread **S2 — OPEN detection producer** (§5.2/§7): detect setups/promises/MICE-opens on a generated scene/chapter → `open_thread`; pay on later beats → `update_status(paid)`. | NOT-BUILT | L | **1 (highest)** | dropped-promise-rate |
| **FD-7** | **S3 — re-injection + `ReasoningState`** (§3/§10.3): formal per-scene `ReasoningState{plan, compressed state, open threads}` threaded through the auto loop; `list_open` → pack (F2); persist to `generation_job.state` (resumable). | PARTIAL (S1/S2 ad-hoc; object + persist NOT built) | L | **2** | long-form coherence (longer scenes, variance) |
| **FD-8** | **S4 — arc-end DEBT check + eval** (§7): advisory "unpaid promise at arc end" flag + the eval arm that proves the ledger reduces dropped-promise defects. | NOT-BUILT | M | **3** | the gate for FD-6/7 |
| **FD-9** | `search`/backtrack combinator (§3b/§6/§10.1): on reflect-exhaust, re-enter `diverge` at this/prior scene with the violation as a new constraint (instead of stop-and-keep-last). | NOT-BUILT (`reflect_revise` caps at max_iters then stops — `canon_check.py:280,302`) | L | 4 | contradiction-resolution-rate |
| **FD-10** | Autonomous arc/book loop (§6): drive the decompose plan scene-by-scene unattended, ReasoningState carried between scenes, capped by `generation_run`, per-chapter human checkpoints. | PARTIAL (single scene/chapter only; no multi-scene driver) | L-XL | 5 | end-to-end long-form defect count |
| **FD-11** | Canon-check breadth (§5.1): broaden beyond "gone entity present" → ConStory-taxonomy judge rubric (timeline/world/factual/memory classes), multi-status `{active,lost,destroyed}`. | PARTIAL (only `gone` literal — `canon_check.py:96,108,133`) | M-L | 6 | contradiction-recall |
| **FD-12** | `craft_recipe` library + compiler (§4/§10.3): table + recipe→primitive compiler so a Work composes 1 template + N recipes. | NOT-BUILT (0 code) | L | 7 (speculative) | only if FD-6/7 show lift first |
| **FD-13** | Craft-method checks (§4b-e): But/Therefore, Scene-Sequel, try-fail escalation, MICE LIFO, monotone tension. | NOT-BUILT | L | 8 (speculative) | per-check ablation |
| **FD-14** | Extra structure templates Freytag / 7-point / Fichtean (§4a). | NOT-BUILT (only 6 builtins — `db/migrate.py:248-324`) | S | 9 (cheap, low-risk) | none (additive seed) |
| **FD-23** | **`llm_judge` reasoning-effort engine** (§3 auto-reasoning) — a small pre-call LLM rating difficulty, as an alternative to the rule-based scorer. The `resolve` seam exists; only `rule_based` is implemented. | NOT-BUILT (intentional seam — `reasoning/policy.py:9-12`) | M | 10 (conditional) | rule-based scorer underperformance |
| | **Production decision (not "skip"):** measure whether the rule-based scorer is good enough on production traffic. If yes → **consciously close** the seam (document "rule-based is sufficient", remove the unbuilt-path framing). If no → build `llm_judge`. Do NOT leave it as an unmeasured "maybe later". | | | | |

**Dependency:** FD-6 → FD-7 → FD-8 is the spine (and is the FD-1 continuation). FD-9/10 build on the ReasoningState from FD-7. FD-12/13 are the *recipe* surface — **do not start until FD-6/7/8 demonstrate a measured lift** (else it's the recipe-trap the lesson warns about). FD-14 is a cheap standalone.

**Merge guidance:** entirely post-merge (validate-first; not blocking PR #19).

---

## 🟢 Phase 3 — Polish / UX / hardening (in-branch, LOW-MED)

| ID | Item | Evidence | Size |
|---|---|---|---|
| **FD-15** | Planner FE affordances: `beat_role` editable, cast add/remove from glossary roster, resolve `present_entity_names_unresolved`, planner-local model picker. | `PlannerTree.tsx:28`, `PlannerSceneRow.tsx:1-4,58-63`, `PlannerView.tsx:10,50` | M (FE) |
| **FD-16** | Canon-rule FE: edit-in-place (hook `patch` exists, unused) + set `entity_id`/`from_order`/`until_order`/`active` (create only sends text+scope → entity/reveal-gate rules can't get bounds). | `useCanonRules.ts:22-26`, `CanonRulesPanel.tsx:10,16` | M (FE) |
| **FD-17** | **069** — A3 replace re-plan leaves orphan arc/chapter nodes (soft-archives only scenes). BE fix in `commit_decomposed_tree`. | DEFERRED 069; `db/repositories/outline.py` | S (BE) |
| **FD-18** | **051** — knowledge `consumer.py` has the dead-retry-in-PEL bug fixed in learning (port the XAUTOCLAIM reclaim). | DEFERRED 051 | M |
| **FD-19** | Correction-feedback loop (learning Phase-B/C/E): **048** Tier-1 anchor consume, **050** raw-content opt-in (Tier-3 gold), **049** ReplayCorrections admin task, **052** desc-diff granularity, **053** emit permanent-failure surface, **046** KS↔PG reconcile sweep. | DEFERRED 048/050/049/052/053/046 | each S-M; batch by area |
| **FD-20** | Dead-code / minor: `getJob` (api.ts:87) unused; pass2 per-scene fanout placeholder (`scene_id=chapter_id`); events.py timeline filter axes (`entity_id`, date-range) unbuilt; packer L5 lens deferred. | `api.ts:87`, `pass2_orchestrator.py:615,639`, `neo4j_repos/events.py:713-723`, `packer/lenses.py:12` | XS-S each |
| **FD-24** | **M7d-3 learning worker-feed dormant** — an off-by-default opt-in flag; corrections don't feed the worker until explicitly enabled. **Production decision (not "skip"):** enable + eval the feed, OR consciously remove the dead flag. Don't ship a dormant half-feature. | learning `app/events/handlers.py:549` | S (decide) → M (if enable+eval) |
| **FD-25** | **Extraction throughput / parallelism** — production orchestrator parallelizes R+E+F within a chapter, but the **events consumer processes 1 message/worker** → ingestion doesn't scale under burst. Production-scale concern (not feature-thin, but a go-live throughput gap). | `app/benchmark/runner.py:26`; consumer single-message path; memory `project_extraction_parallelism_gap` | M (throughput) |
| **FD-26** | Minor cleanups: `mining.py:176` node→run provenance link deferred; richer truncation surfacing (cy16 shipped `finish_reason`; the char-estimate richer signal stays deferred — confirm it's wanted or drop). | learning `app/db/mining.py:176`; composition `app/routers/engine.py:640` | XS each |

**Merge guidance:** all post-merge (none blocking). FD-15/16 improve the just-shipped planner/canon FE. FD-25 (throughput) matters for go-live scale, not for the composition arc — schedule before a real-load deploy.

---

## Recommended sequencing (when the PO greenlights building)

1. **Cheap verifies first** — FD-5 (full-mode reachable?) + FD-22 (K16.6 stale?). Both may collapse to "delete a stale marker"; do them before committing build effort.
2. **Phase 1 honesty** — FD-4 (067 diagnostic → activate status prompt) + FD-1 minimal-runnable (ledger stops lying) + FD-3 + FD-2 + FD-21 (MCP live-smoke gate). Removes every "feature that looks done but is a no-op".
3. **Decide merge timing** — merge PR #19 either after Phase 1's in-arc items (FD-1, FD-4) or now-with-fast-follow; FD-2/3/21 (cross-service) and all of Phase 2/3 are post-merge.
4. **Phase 2 only behind eval** — run FD-6→7→8 (the F2/ledger spine), gate on dropped-promise-rate; **only** proceed to FD-9/10/11 then FD-12/13 if a lift is measured. FD-14 is a free cheap add anytime. **FD-23 (`llm_judge`) = a production decision** (measure rule-based → close the seam or build), not a "maybe later".
5. **Phase 3** — batch FD-19 by area; FD-15/16 when the planner/canon FE is next touched; **FD-24 (M7d-3) = decide enable-or-remove**, don't ship dormant; **FD-25 (throughput) before any real-load deploy**.

**Production-ready close-out condition:** the branch's feature ledger is "done" only when every FD-1…FD-26 is either BUILT, or a **recorded conscious decision** (removed / proven-not-needed / scheduled to a named track) — no silent dormant code, no unproven-live cross-service path, no unmeasured seam.

**Won't-do here (separate tracks, not silent — recorded):** all other-track items (tilemap/geo/game/enrichment P2/P3/provider-registry/glossary/tooling) own their tracks; 063 grounding-compose (own post-merge track); 064 (deferred-on-trigger, re-confirmed cy15).
