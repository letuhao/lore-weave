# Narrative Forge — Methodology (NDLC draft v0.2)

> **Date:** 2026-07-05 · **Status:** DRAFT v0.2 — macro-stage naming + gate-reconciliation direction LOCKED by PO 2026-07-05 (§5 answers below). Quality-rebuild and Visualization are SPUN OFF as separate future tracks — each needs its own CLARIFY→DESIGN→draft-HTML→spec, out of scope here. · **Owner:** user + this session

## 0. Why this exists

Software engineering has a shared vocabulary — SDLC (Requirements→Design→Implement→Test→Deploy) — that every tool, doc, and diagram aligns to. Novel writing has never had an equivalent: human writers each have their own "bí kíp" and work idiosyncratically, which is fine for a human but not for an AI, which needs an explicit system of phases/artifacts/gates to reason over.

LoreWeave has built **8 substantial subsystems** (PlanForge, Agent Mode, Composition drafting, Knowledge extraction/grounding, Glossary/Wiki, Enrichment, Translation, Quality) — each internally well-engineered — but **never unified them into one named lifecycle**. This doc is the audit that grounds that unification in what the code actually does today, not an invented-from-scratch framework.

**Name:** *Narrative Forge* (chosen over a plain "writing methodology" label — continues the `PlanForge` naming lineage already in the repo, evokes the Snowflake Method's successive-refinement spirit). Internally the phase model is called **NDLC** (Narrative Development Life Cycle) — the direct SDLC echo, used when precision matters more than branding.

---

## 1. Audit — what each subsystem already implicitly encodes

Every row below was independently verified against the CURRENT code (7 parallel Explore-agent audits + direct reading), not assumed from docs (which are frequently stale — see the PlanForge finding below).

| Area | Implicit phases (real, as coded) | Canonize-time gate | Existing internal vocabulary |
|---|---|---|---|
| **PlanForge** | `0 Ingest → 1 Propose → 2 Decompose → 3 Link → 4 PlanParts → 5 Integrate → 6 Validate → 7 Commit` | Blocking checkpoint per phase (1,2,3,4,7); phase 5 advisory; phase 6 fail→loop | **Most mature** — phases explicitly named in `09_PLANFORGE_BLUEPRINT.md`'s own mermaid diagram |
| **Agent Mode** (autonomous authoring run) | `draft → gated → running → (paused⇄running) → report_ready → closed`; per-unit `pending → drafted → (accepted\|rejected)` | Batch human review AFTER drafting (`accept_unit`/`reject_unit`/`revert_all`, restricted to `report_ready\|failed\|paused`) | D2-D5 "waves"; `07S_studio_agent_standard.md` §10 names a **"Shared pipeline — ONE build, three gate positions"** (Start/During/End/Exec × Supervised/Autonomous) — closest existing seed for a universal gate taxonomy |
| **Composition drafting** | pack → reasoning-resolve → generate → canon-reflect (advisory, self-repair loop) → persist job → critique (on-demand) → correction (learning flywheel) → persist-to-draft → publish | `composition_generate`/`composition_publish` = propose→confirm token gate (spend-gated, not canon-gated); canon check is the **only hard-blocking gate found across all 8 areas** (blocks Publish) | Informal "retrieve→budget→stream→meter→persist"; separately, a **distinct micro-planning system**, "Planning pipeline · Stage 0-5" (`cast_plan→...→grounded_plan→plan_heal`) — verified this is NOT a duplicate of PlanForge, it operates one granularity level DOWN (scene-decompose detail, after PlanForge's PlanningPackage already exists) — a legitimate two-tier planning split that was just never named as such |
| **Knowledge extraction/grounding** | Extraction (one-time, `chapter.published`-triggered): passage-ingest → anchor-preload → entity→relation/event/fact extraction → write. Grounding (per-turn): Mode 1/2/3 → salience rerank → intent-classify → blend → render | **NONE** — writes directly to Neo4j, fully automatic. Only a downstream, SEPARATE service (glossary's "AI Suggestions"/"Merge Candidates" panels) reviews anything, and that's glossary's own flow, not knowledge-service's gate | "Pass 1/Pass 2", "L0-L3" context layers, "Mode 1/2/3" — heavy internal ticket vocabulary, zero external unification |
| **Glossary & Wiki** | entity: extracted/proposed (draft, `ai-suggested`) → reviewed → active/inactive; separately merge-candidates and wiki staleness→regenerate | Human status-flip required (draft→active); System/User/Book 3-tier (CLAUDE.md's own tenancy standard) | "review bucket", "SS-2/4/7" epic tags, "Phase-2 staleness sweep" |
| **Enrichment** | Trigger (gap-detected OR user-initiated, same pipeline) → retrieval/grounding → generation (H0: never confidence=1.0) → canon-verify → quarantined proposal → human review → promote → (retract, reversible) | **Mandatory quarantine + human promote** — the most rigorous non-PlanForge gate found | C7-C17 RAID cycle IDs, well-documented internally, cites its own spec doc |
| **Translation** | job-create → fan-out → chapter-translate → finalize → **auto-promote if clean** → job-complete → (optional post-publish human review) | **Automatic by default** (self-publishes unless `unresolved_high_count>0`); human review is a soft/opt-in gate, not mandatory | "Pipeline"/"Phase 4c-β" milestone tags, no unified lifecycle name |
| **Quality** (Critic/Promises/Canon) | On-demand chapter critic + promise-audit; on-demand book-level promise-coverage; automatic per-scene canon-reflect | Canon-reflect blocks Publish (same gate as Composition's); critic/promise-audit are **advisory-only, no persistence, no apply affordance** | **The Studio "Quality" activity tab is a COMPLETE STUB** ("Built next.") — the real implementation lives only in the legacy `CompositionPanel.tsx` workspace, never ported to the Studio dockview architecture (same fragmentation shape as the earlier "Cursor-for-novels" findings) |

---

## 2. Cross-cutting findings (the actual evidence for "never unified")

**Finding A — 6+ different gate philosophies for the same underlying question. LOCKED DECISION: this is a real defect, not an accepted variance — reconcile toward gating.** "When does AI-generated content become trustworthy enough to treat as canon?" is answered completely differently by every subsystem: never-gated (Knowledge), mandatory-quarantine (Enrichment), manual-status-flip (Glossary), auto-unless-flagged (Translation), spend-gated-not-canon-gated (Composition generate), and hard-blocking (Composition publish, canon check). None of these reference each other or a shared standard. **PO decision (2026-07-05): the direction is to bring every subsystem's canonize-time gate toward an explicit, justified position in the §4.3 taxonomy — the worst offender today is Knowledge extraction (`none` — writes straight to Neo4j with zero review), which should gain a real gate.** This is a direction, not a single big-bang migration: each subsystem's actual gate change is its own future PLAN/BUILD, scoped and sequenced separately, starting with whichever is cheapest/highest-signal (§6).

**Finding B — a two-tier planning split exists and is *correct*, just unnamed.** PlanForge (system-design grain) and Composition's own "Planning pipeline Stage 0-5" (scene-decompose grain) are NOT competing/duplicate systems — verified via source: Stage 0-5 explicitly operates on PlanForge's already-produced `PlanningPackage`, one granularity level down. This is a legitimate SDLC-like split (high-level design vs detailed design) that nobody has documented as such.

**Finding C — the Studio "Quality" tab is vaporware; the real feature is stranded on the legacy surface.** Same shape as the four gaps closed in the "Cursor-for-novels" effort (coherence/apply-diff/live-sync/agent-mode) — a capability that fully exists but is split across two workspaces.

**Finding D — a real cross-cutting gate model already exists in embryo.** `07S_studio_agent_standard.md`'s "Start/During/End/Exec × Supervised/Autonomous" table is the ONE place in the codebase that already tries to name gate positions generically instead of per-feature. This is the natural seed to generalize into NDLC's gate taxonomy (§4.3) rather than inventing a new one.

---

## 3. Human literary methodology — reference layer, not process layer

Researched to answer "what should the RULE content be," not "what should the PHASES be" — these two are a different axis (see distinction below).

| Methodology | Shape | Role for Narrative Forge |
|---|---|---|
| **Snowflake Method** (Randy Ingermanson) | *Process* — successive refinement: 1 sentence → paragraph → characters → outline → ~100 scenes → draft | Structural template for the MACRO-stage progression (§4.1) — validates "increasingly detailed artifact per stage" as the right backbone shape |
| **Save the Cat!** (Blake Snyder, 15 beats) | *Structure* — required beats a story must hit, with position | Candidate pluggable rule-set for the Verify/Gate micro-stage (§4.2), genre-appropriate for plot-driven Western structure |
| **Story Grid** (Shawn Coyne, 5 Commandments) | *Structure* — every story unit (scene→global) must satisfy: inciting incident, progressive complications, crisis, climax, resolution | Candidate rule-set — most directly comparable to PlanForge's own ad-hoc 7-rule "golden linter" (`arc2_discovery`, `thr_no_early_explain`...). **PlanForge's validator is unknowingly reinventing a small slice of Story Grid's Five Commandments.** **PO decision (2026-07-05): NOT a swap-in.** The existing 7 rules are already POC'd + tested (`02_POC_RESULTS.md` PASS, `04_PO_REVIEW.md` GO) — real, working, trusted. Story Grid (or any other structure framework) is a candidate ADDITION, evaluated via its own POC (side-by-side scoring against the same fixtures the current 7 rules already pass) before any replacement is even considered. The bar: prove it catches something real the current rules miss, not just "it's a named framework." Track as a future POC item, not a locked plan. |
| **John Truby's 22 Steps** | *Structure* — character/plot/world/moral-argument checklist | Candidate rule-set, strongest for character-arc consistency checks |
| **Dan Harmon's Story Circle** (8-step simplification of Campbell's Hero's Journey) | *Structure* — character transformation arc | Candidate rule-set for arc-level (not scene-level) consistency, close to what Agent Mode's per-unit critic or Quality's promise-audit could check against |

**Key distinction to keep locked:** *Process* methodologies (Snowflake) inform NDLC's phase backbone. *Structure* frameworks (the other four) are pluggable rule-sets that slot into the Verify/Gate micro-stage — genre-selectable, not hardcoded, the same way PlanForge's validator already accepts a rule-set but currently only has one home-grown option.

---

## 4. NDLC skeleton v0.2 (names + gate direction locked, §5)

### 4.1 Macro stages (book-level, Snowflake-style successive refinement)

**PO decision (2026-07-05): renamed away from SDLC-literal labels.** "System Design"/"Commit"/"Verify" read as transplanted git/software jargon; "Concept"/"Draft"/"Ground"/"Enrich"/"Localize"/"Publish" were already natural to novel-writing and are kept. The renamed stages lean into the platform's OWN existing naming (Forge, from `PlanForge`; Cast, from `cast_plan.py`'s character-casting step which sits right at this handoff point) rather than inventing new jargon — names are a starting proposal, adjust freely:

```
Concept → Forge → Cast → Draft ⇄ Ground ⇄ Enrich → Hone → Localize → Publish
```

| Stage | Renamed from | What it is today | Owning subsystem(s) |
|---|---|---|---|
| **Concept** | (unchanged) | Raw braindump/idea | (pre-tooling, human) |
| **Forge** | System Design | PlanForge phases 0-6 — shaping the raw idea into a validated `NovelSystemSpec`/`PlanGraph` | PlanForge |
| **Cast** | Commit | PlanForge phase 7 — seeding glossary + outline; literally where `cast_plan.py`'s character-casting already runs | PlanForge → Composition handoff |
| **Draft** | (unchanged) | Two entry points into the same artifact concept: turn-by-turn (Composition generate) and autonomous batch (Agent Mode) — plus the Stage 0-5 scene-decompose detail layer (Finding B) | Composition + Agent Mode |
| **Ground** | (unchanged) | Extraction → KG, feeds back into future Draft calls | Knowledge |
| **Enrich** | (unchanged) | Gap-fill / lore-deepen, interleaved with Draft, not strictly after it | Enrichment |
| **Hone** | Verify | Critic, promise-audit, canon-check — sharpening/refining, not a one-time gate | Quality (currently stub on Studio — spun off, §5) |
| **Localize** | (unchanged) | Parallel track, can run per-published-chapter, not sequential | Translation |
| **Publish** | (unchanged — already literary-native, not SDLC jargon) | The one universal hard gate (canon_blocked check) | Composition |

Draft/Ground/Enrich are drawn as a cycle (⇄), not a line — verified from code that they interleave per-chapter, not book-then-book.

### 4.2 Micro-cycle (the repeatable pattern inside almost every macro stage)

Every one of the 8 audited areas instantiates some subset of this same 6-step shape, just under a different local name:

```
Trigger → Generate → Verify → Gate → Canonize → (Revise)
```

*(Note: this "Verify" is the generic micro-step that happens inside EVERY macro stage — Forge validates its spec, Enrich runs canon-verify, Draft runs canon-reflect, etc. It is distinct from "Hone," the one macro stage in §4.1 whose entire JOB is verification/critique. Same relationship as "testing" being both a universal engineering discipline and also a dedicated SDLC phase.)*

### 4.3 Universal Gate Taxonomy (generalizing 07S's existing Start/During/End/Exec model, Finding D)

Instead of each subsystem inventing its own gate vocabulary, every Gate step in §4.2 should be classified along 2 shared axes:

- **Position:** Start (before generation) · During (mid-stream) · End (after generation, before canonize) · Exec (execution-time, e.g. spend)
- **Strictness:** `none` (Knowledge today) · `advisory` (Composition critic, Quality) · `soft` (Translation, refuses only on flagged issues) · `quarantine+promote` (Enrichment's H0) · `hard-block` (Composition publish canon check) · `propose-confirm` (spend-gated, orthogonal to canon-strictness)

This gives every existing gate a name from ONE shared taxonomy — a prerequisite for visualizing them uniformly (the tech-tree/graph map idea), and a lever for deciding case-by-case whether a subsystem's current strictness is actually the RIGHT one (e.g., should Knowledge extraction really stay `none`?).

---

## 5. Decisions (LOCKED by PO 2026-07-05)

1. **Macro-stage names** — renamed away from SDLC-literal labels (§4.1): `Concept → Forge → Cast → Draft ⇄ Ground ⇄ Enrich → Hone → Localize → Publish`.
2. **Gate-strictness reconciliation** — **treat as a real defect, fix direction locked** (§2 Finding A updated). Knowledge extraction (`none`) is the clearest case needing a real gate. Each subsystem's actual change is its own future scoped PLAN/BUILD — not a single big migration.
3. **PlanForge validator vs. Story Grid/etc.** — **NOT a swap-in.** The current 7 rules are already POC'd + tested and stay as the trusted baseline. Any structure-framework addition (Story Grid, Truby, etc.) requires its OWN POC — scored side-by-side against the same fixtures the 7 rules already pass — before being considered for adoption. Tracked as a future evaluated option, not a commitment.
4. **Quality's Studio stub** — **will be planned, but as its OWN separate track** (needs detailed design + a draft HTML mockup first, same process the Agent Mode / Cursor-for-novels work followed). Out of scope for this methodology doc.
5. **Visualization (tech-tree/graph map)** — **also its own separate track**, needs its own draft HTML + detailed spec. Explicitly sequenced LAST, after the methodology vocabulary is actually in use by ≥1 subsystem (per the "phương pháp luận đi xuống" principle that opened this effort) — not started yet.

## 6. Next steps

This methodology doc (v0.2) is the locked reference for §1-§4 (audit + phase/gate vocabulary). Items 4 and 5 above spin off into their own future CLARIFY sessions when picked up — each starts fresh with its own draft HTML per this repo's established convention, referencing back to this doc for the shared vocabulary rather than re-deriving it. Item 2's gate reconciliation and item 3's rule-framework POC are candidate first PLAN-phase targets whenever the user wants to pick one up next — no specific one is committed yet.
