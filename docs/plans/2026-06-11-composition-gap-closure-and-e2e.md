# Composition — gap-closure + e2e/QC plan (post-coverage-review)

**Source:** `docs/reports/2026-06-10-composition-fe-be-coverage-review.md`. **Branch:** `feat/composition-service`.
**Framing (PO-corrected 2026-06-10):** the v3 studio drafts are the PRODUCT SPEC. We ship a usable product, not a mockup — a PARTIAL feature (exists but unusable) or a MISSING one is unfinished work, not "future roadmap." So Part A below is a **mandatory, sequenced build program** that must complete before the branch closes (the earlier "merge now, roadmap later" framing is retracted). Part B is the e2e/QC gate run **after** the product is complete. Excluded only: the V2 drafts (doujin, scene-graph-whatif) + the catalog-LATER items (corkboard/arc/world-map/references/progress) — re-confirm with PO.

---

## Part A — Gap closure (implement next session, prioritized)

### Tier 0 — quick wins: BE complete, FE unwired (do these next session; ~S each, /loom)
1. **Plot-thread / promise-debt panel** (FD-1 surface). BE `GET /works/{id}/narrative-threads` (`status=open`=debt, `all`=ledger; `open_count`) is live + `narrative_thread_enabled` settings toggle exists; **no FE consumer**.
   - Build: `useNarrativeThreads(projectId, token)` hook + a `ThreadsPanel` (or a section in an existing tab) listing open promises (priority-ordered) with paid/abandoned status; gate render on `narrative_thread_enabled`. Reuse the `CanonRulesPanel` list idiom. 4-locale i18n + vitest (open vs all; empty state; gated-off hides it).
   - Acceptance: an author can see the unpaid-promise debt for the project; advisory only (D4). Size **S-M (FE)**.
2. **`suggest-cast` wiring** (FD — cast assist). BE `POST /works/{id}/scenes/{node}/suggest-cast` (engine.py:878) has zero callers.
   - Build: a "Suggest cast" action in `PlannerSceneRow` (or ComposeView grounding) → calls suggest-cast → merges suggested entity_ids into `present_entity_ids` (reuse the FD-15 cast-edit path + `useGlossaryRoster` labels). vitest + i18n.
   - Acceptance: one click proposes scene cast from the model; author accepts/edits. Size **S (FE)**.

### Tier 1 — V1.5 studio features (post-merge roadmap; M each, new FE ± small BE)
Cast & Codex with per-entity story-state (needs a knowledge read for current state) · Grounding **pin/exclude** (needs BE pin-state on the grounding pack) · **Beat Sheet** view (template beats ↔ filled scenes) · **Timeline** UI (surface the spoiler-safe `before_order` chronology) · **Style & Voice** panel (editable voice/structure profile, currently read-only text) · **Flywheel** panel ("+N new facts" from publish→extraction) · selection **rewrite/expand/describe** tools · explicit **Classic⇄AI** inline document-mode (in-prose ghost + accept-bar) · **Focus/typewriter** mode.

### Tier 2 — V2 (large, aspirational; separate track)
Scene-Graph canvas + **Story-Map power-view overlay** (Scene Graph / Timeline / Beat Sheet as a full-width opt-in view) · Relationship Map · dock/float/pop-out **windowing model** (replace the fixed sub-tab strip) · mention **heatmap** · AI-**provenance** highlight (mark-reviewed) · **同人/derivative** (doujin draft) · **what-if branch** sandbox + promote-to-canonical (scene-graph-whatif draft).

> **Execution order (all MANDATORY before close):** Phase 0 (the 2 unwired-BE quick wins) → Phase 1 (finish every PARTIAL into a usable state) → Phase 2 (build the MISSING views). Do NOT merge/close until Phase 0–2 are complete + usable + the Part-B QC gate passes. The catalog-LATER + V2 drafts are the only items deferred (pending PO re-confirm). This is a multi-session program — drive it via `/loom <feature>` one feature at a time, updating SESSION_HANDOFF after each.

---

## Part B — e2e / QC plan for the SHIPPED (COVERED) scope (the production delivery gate)

**Existing baseline (V0 sweep, green):** 23 Playwright specs covering U1–U9 · B1.* publish-lifecycle · B3.1/B3.3 telemetry · B4.* engine · B6.* grounding/canon · B7.* · B8.* revision-compare · B9.1 isolation · U8 flywheel-decision. These cover the editor shell, streaming generate, canon gate, candidates gate, assemble, publish-gate, grounding-empty hint, cross-user isolation. **Treat these as the regression net — they must stay green.**

**NEW e2e specs needed** — features built THIS branch *after* the V0 sweep (LOOM-68→88) that the sweep predates. These are the QC-gate additions:

1. **`composition-canon-rules.spec.ts`** (FD-16, LOOM-84) — model-gated NOT required (CRUD only):
   - Add a `world` rule (text+scope) → appears in list.
   - Add a `reveal_gate` rule with entity (from roster) + from/until window → appears with the `[from–until]` badge; an inverted window (from>until) disables submit + shows the error.
   - Edit-in-place: open a rule → change text + toggle `active` off → save → list reflects it (inactive styling); reopen → cancel returns to read view.
   - Archive a rule → removed from list.
   - DB-assert (optional): the canon_rule row carries entity_id/from_order/until_order/active.
2. **`composition-planner-affordances.spec.ts`** (FD-15, LOOM-85) — model-gated (decompose needs an LLM) OR seed a draft:
   - From a decompose preview: edit a chapter `beat_role` inline → persists into the commit payload.
   - Cast: add an entity from the roster select → chip appears; remove a chip → gone.
   - Resolve: an unresolved planner name that matches a roster entity → one-click "+name" adds it to cast; a non-matching name stays a `name?` hint.
   - Planner-local model picker: choose a non-inherited model → the decompose preview request uses it (network-assert the model_ref).
3. **`composition-narrative-threads.spec.ts`** (after Tier-0 #1 ships) — open-promise debt panel renders open vs paid; gated-off hides it.
4. **`composition-suggest-cast.spec.ts`** (after Tier-0 #2 ships) — suggest-cast proposes + author accepts into cast.

**Cross-service / live-smoke evidence to (re)capture for the QC gate** (≥2-service paths built this branch):
- chat→KG extraction full chain (FD-2): publish a chat turn → auto `scope='chat'` drain → entity extracted → recallable via `/mcp` (FD-21). *Done live this session — record in the QC evidence doc.*
- worker-ai zero-output + reasoning-model advisory (FD-27): seeded smoke confirmed.
- knowledge consumer PEL reclaim (FD-18): unit-proven (XAUTOCLAIM) — a live stuck-message reclaim is optional.
- learning correction-capture (FD-19 053/052): unit + real-DB migration proven.

**QC gate exit criteria (production-ready definition):**
- [ ] All 23 V0 Playwright specs green (regression net).
- [ ] New specs #1 + #2 green (FD-15/16 — the FE built this branch).
- [ ] Full unit/integration suites green per service (knowledge / worker-ai / chat / composition / learning / provider-registry) — already verified per-cycle this session.
- [ ] Cross-service live-smoke evidence recorded for FD-2/FD-21 (chat→KG→recall) + FD-27.
- [ ] No open `MED+` deferral that is a `feat/composition-service` pre-merge blocker (confirmed clear — see DEFERRED.md; remaining opens are other tracks / phase-gated).
- [ ] PO sign-off at POST-REVIEW.

> This QC gate runs **after** the Part-A build program completes. Every newly-built feature (Phase 0/1/2) adds its own e2e spec to this gate (not just #1–#4 — each feature ships with vitest + a Playwright path + i18n parity). The branch closes only when: Phase 0–2 done + usable · all unit/integration green · the full Playwright suite (V0 net + every new feature spec) green · cross-service live-smokes recorded · PO sign-off. Until then the feature is **not** production-ready and the branch stays open.
