# Composition — FE/BE coverage review vs design drafts (pre-merge, 2026-06-10)

**Branch:** `feat/composition-service` · **HEAD:** LOOM-88 · **Purpose:** before closing the branch, audit whether the implemented FE/BE covers the composition design drafts, and decide implement-plan (gaps) vs e2e/QC plan (no gaps).

**Drafts reviewed (V1 in-scope):** `docs/specs/composition-studio-mockup-v3.html`, `composition-studio-components.html`. **V2 (out of scope):** `composition-doujin-mockup.html` (同人/derivative), `composition-scene-graph-whatif.html` (branch/take sandbox).

---

## TL;DR verdict

The **shipped product is a focused "controlled-auto co-writer"** (V0 complete + V1 reasoning engine), and it **covers its own validated scope end-to-end and is production-ready** (23-spec Playwright sweep already green per the V0 close-out). The **v3 studio mockup is an aspirational full writing-IDE** (dockable/floatable panels, scene-graph canvas, timeline, beat-sheet, style sliders, power-view overlays, focus mode, provenance heatmaps). Most "gaps" vs that mockup are **future roadmap (V1.5/V2), not pre-merge regressions.**

**There are exactly 2 genuine, ship-worthy gaps** where the **BE data path is complete but the FE is unwired** — these are the only items that represent "built-but-not-surfaced" debt:
1. **Plot-thread / promise-debt panel** — `GET /works/{id}/narrative-threads` + the `narrative_thread_enabled` settings toggle exist; **no FE component fetches the endpoint**.
2. **`suggest-cast` unwired** — `POST /works/{id}/scenes/{node}/suggest-cast` (engine.py:878) has **zero FE callers**.

Everything else is either COVERED, or an unbuilt aspirational v3-IDE feature (future roadmap), or explicitly V2.

**Conclusion: the branch is closeable.** The shipped co-writer is feature-complete for its scope; the 2 unwired-BE gaps + the v3 aspirational surface are best tracked as a **post-merge V1.5 roadmap** (see the companion plan). No pre-merge blocker.

---

## Coverage matrix (V1 — studio-mockup-v3 + components catalog)

> Note: the studio is split — `ChapterEditorPage.tsx` is the manuscript-editor shell (Tiptap, chapter list, Original/glossary left-tabs, version history, mention decoration, publish-gate banner); `features/composition/CompositionPanel.tsx` is the AI co-writer side-panel (7 sub-tabs: compose/assemble/planner/grounding/canon/quality/settings). Both count as "implemented".

### A · Structure
| Draft feature | FE | BE | Status |
|---|---|---|---|
| Scene Graph (typed-link canvas) | — (flat PlannerTree only) | `scene-links` CRUD, outline nodes | PARTIAL (BE links exist; no canvas) |
| Outline Tree (Act→Chapter→Scene→Beat) | PlannerView/Tree/SceneRow | `/outline`, node CRUD | PARTIAL (decompose draft, not a persistent Act→Beat browser) |
| Beat Sheet (template beats ↔ scenes) | — (only `unmapped_beats` text) | `/templates`, decompose | MISSING (FE view) |
| Corkboard (index cards) | — | — | V2-DEFERRED (tagged LATER) |
| Plot Threads (open/paid debt) | — (no panel) | `GET /narrative-threads` + settings toggle | **PARTIAL — quick win (BE complete, FE unwired)** |

### B · World & Canon
| Draft feature | FE | BE | Status |
|---|---|---|---|
| Cast & Codex (entities + current state) | glossary list in editor only | `suggest-cast`; `useGlossaryRoster` | PARTIAL (no per-entity story-state; suggest-cast unwired) |
| Relationship Map | — | knowledge `/entities`,`/relations` | MISSING |
| Timeline (spoiler-safe chronology) | — | `before_order` cutoff (internal) | MISSING (UI) |
| Character Arc | — | — | V2-DEFERRED (LATER) |
| **Canon Rules** | **CanonRulesPanel + CanonRuleForm** | canon CRUD + PATCH | **COVERED** |
| World Map | — | — | V2-DEFERRED (LATER) |

### C · Write & AI
| Draft feature | FE | BE | Status |
|---|---|---|---|
| **Manuscript editor + streaming continuation** | **ComposeView (ghost+Accept) + Tiptap shell** | SSE `/generate` | **COVERED** (side-panel ghost, not inline; selection rewrite/expand/describe absent → PARTIAL on that sub-tool) |
| Grounding (live RAG context) | GroundingPanel (read-only blocks) | `/scenes/{node}/grounding` | PARTIAL (no pin/exclude) |
| **Continuity Critic** | **CriticFlags + CanonGatePanel** | `/critique`,`/dismiss-violation`, canon gate | **COVERED** |
| Style & Voice (sliders/voice chips) | — | profile in settings (read-only) | MISSING |
| AI Co-writer (chat brainstorm) | guide textarea only | `/generate` guide | PARTIAL (no conversational chat) |
| References (comps/influences) | — | — | V2-DEFERRED (LATER) |

### D · Track
| Draft feature | FE | BE | Status |
|---|---|---|---|
| **Versions & History (diff/restore)** | **RevisionHistory in editor shell** | book-service revisions | **COVERED** |
| Progress & Stats (streak/goals) | word count only | — | V2-DEFERRED (LATER) |
| Flywheel (+N new facts learned) | — | publish→extraction (server-side) | MISSING (FE surface) |

### v3 shell chrome
| Draft feature | Status |
|---|---|
| **Chapter list / Original tab / Glossary tab + in-prose mentions + autocomplete** | **COVERED** (ChapterEditorPage) |
| **Model picker + reasoning effort** | **COVERED** (exceeds mockup — mockup had none) |
| **Scene done/commit + Publish gate** | **COVERED** (usePublishGate banner) |
| Classic ⇄ AI document-mode switch | PARTIAL (right-tab toggle, not inline ghost/accept-bar mode) |
| Focus/typewriter mode · Grammar/Translate toolbar · Story-Map power-view overlay · Mention heatmap · AI-provenance highlight · dock/float/pop-out windowing | MISSING (aspirational v3 IDE chrome) |

### Built BEYOND the mockups (not gaps — extra validated scope)
Diverge/K-candidate gate (CandidatesView/CandidateCard, `/generate?mode=auto`) · Chapter Assemble (B2 single-pass + B3 stitch) · Quality/eval-gate dashboard (QualityPanel, `/correction-stats`) · Planner decompose (`/outline/decompose`+`/commit`) · Settings tab (model/assembly/narrative-thread).

## V2 drafts (doujin + scene-graph-whatif) — unimplemented is EXPECTED
同人/derivative (divergence banner, inherited/overridden canon layers, POV/gender override) — not built (correctly V2). Scene-graph what-if (branch sandbox, judge-scores-branch, promote-to-canonical, alternate takes) — not built (correctly V2).

---

## Counts (≈30 V1 features assessed)
- **COVERED: 10** — Canon Rules · Continuity Critic · Manuscript+streaming · Versions/History · Chapter list · Original tab · Glossary+mentions · Model picker · Scene-commit/Publish-gate · core co-writer generation.
- **PARTIAL: 8** — Scene Graph · Outline Tree · **Plot Threads (quick win)** · **Cast & Codex (suggest-cast unwired — quick win)** · Grounding pin/exclude · AI Co-writer chat · Classic/AI mode switch · selection rewrite/expand/describe.
- **MISSING: 9** — Beat Sheet · Relationship Map · Timeline UI · Style & Voice · Flywheel panel · Focus mode · Story-Map power-view overlay · Mention heatmap · Provenance highlight (+ dock/float windowing).
- **V2-DEFERRED (catalog LATER): 5** — Corkboard · Character Arc · World Map · References · Progress/Stats.
- **V2 drafts:** not started (expected).

## Gap classification for planning
- **Tier 0 — quick wins (BE done, FE unwired):** Plot-thread debt panel; `suggest-cast` wiring. *Real built-but-not-surfaced debt; smallest effort, highest "honesty" value.*
- **Tier 1 — V1.5 studio features (new FE + some BE):** Cast & Codex with story-state; Grounding pin/exclude; Beat Sheet view; Timeline UI; Style & Voice panel; Flywheel panel; selection rewrite/expand/describe; Classic⇄AI inline mode; Focus mode.
- **Tier 2 — V2 (large, aspirational):** Scene-Graph canvas + Story-Map power-view overlay; Relationship Map; dock/float/pop-out windowing; mention heatmap; provenance highlight; doujin/derivative; what-if branch sandbox.

See `docs/plans/2026-06-11-composition-gap-closure-and-e2e.md` for the prioritized implement plan + the detailed e2e/QC plan for the shipped (COVERED) scope.
