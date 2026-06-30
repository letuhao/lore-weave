# Editor & Compose UX/UI Overhaul — Track Index

> **Started:** 2026-06-30 · **Status:** CLARIFY/DESIGN (discussing user stories one by one) ·
> **Branch (when BUILD starts):** TBD · **Owner:** letuhao1994 (PO) + Claude
> **Supersedes:** [`../2026-06-02-composition-studio-ux.md`](../2026-06-02-composition-studio-ux.md)

This is a **huge, multi-story** effort (re-arrange + wire the chapter editor, compose studio, and
translation into one coherent workspace). It is tracked as a folder so the investigation is written
down **once** and never re-explored — read these before doing any new code-spelunking.

## Visual artifacts
- **[`compose-ideal-journey.html`](compose-ideal-journey.html)** — the IDEAL compose user-story graph
  (design target, not current code). Open in a browser. Next: POC current source vs this to find gaps.

## Read order (new session: start here)

1. **[`00_INVESTIGATION.md`](00_INVESTIGATION.md)** — canonical current-state inventory (file:line
   evidence for the editor shell, the 24 compose panels, scenes, translation, backend/MCP surface,
   and the dock infra). **Don't re-grep what's already here.**
2. **[`01_USER_STORIES.md`](01_USER_STORIES.md)** — the epics/stories + per-story status.
3. **[`02_DESIGN.md`](02_DESIGN.md)** — recommended IA, the Workmode model, milestones M0–M5,
   verification, out-of-scope.
4. **[`stories/`](stories/)** — one file per story, holding the discussion + locked decisions.

## Status tracker

### User stories (discussion → decision)
| Story | Title | Status | Decision file |
|---|---|---|---|
| A1 | Single Write/Translate/Compose switch | ⬜ not discussed | — |
| A2 | Context preserved across mode switch | ⬜ not discussed | — |
| **(manual)** | **Manual "Classic" mode — definition & quality** | ✅ **decided (QoL-only)** | [`stories/01-manual-write.md`](stories/01-manual-write.md) |
| B1–B4 | Translate as a real mode (+ manual/human-first) | ✅ **decided** | [`stories/02-translation.md`](stories/02-translation.md) |
| C (re-frame) | Talk / Build / (Produce→toolbox) frame | 🟡 discussing | [`stories/03-compose-reframe.md`](stories/03-compose-reframe.md) |
| C6 | **AI chat as core** ("Claude Code in VS Code") — tool curation, skills, model settings | 🟡 discussing | [`stories/04-ai-chat-core.md`](stories/04-ai-chat-core.md) |
| C2/C5 | Compose panels = toolbox; Media tool | 🟡 toolbox open / **Media deferred** | [`stories/05-compose-toolbox.md`](stories/05-compose-toolbox.md) |
| **C1 ★** | **The compose journey (process, not tools)** — CORE PROBLEM | 🟡 **investigating** | [`stories/06-compose-journey.md`](stories/06-compose-journey.md) |
| **C7** | **Self-heal / Polish pass** — manual+auto, double-edged ⇒ accept/reject review-gate, never silent | 🟡 discussing | [`stories/07-self-heal-polish.md`](stories/07-self-heal-polish.md) |
| D1–D3 | Scenes I can organize | ⬜ not discussed | — |

### Milestones (build) — sequenced after stories are locked
| M | Goal | Status |
|---|---|---|
| M0 | Workmode switch | ⬜ planned |
| M1 | Translate mode **(FS)** — incl. manual/human-first + seed-from-source BE endpoint | ⬜ planned |
| M2 | Re-group 24 panels into 5 sections | ⬜ planned |
| M3 | Scenes panel (add/reorder/archive/restore) | ⬜ planned |
| M4 | Compose command-center | ⬜ planned |
| M5 | BookAssistantDock → compose bridge (stretch) | ⬜ planned |
| M6 | Polish/self-heal review-gate panel (FS) — engine built; needs MCP propose→confirm + UI | ⬜ planned |

## Operating approach (UPDATED 2026-06-30) — incremental, validate-first
**We do NOT build M0–M5 big-bang.** Per PO: improve **one small slice** at a time → PO **tests the
user story** → decide if the GUI is actually better → only then continue. Each slice is small,
self-contained, and reversible. The milestone table below is the *backlog/menu*, not a build order.
Rationale: the original draft drifted by building everything up front; we de-risk by validating each
improvement against a real user-story test before scaling.

## Decision log (append-only — newest last)
- _2026-06-30_ — PO confirmed: **re-arrange + wire, no re-architecture**; mental model = "recommend
  optimal"; first milestone = "recommend after mapping". → recommended **M0+M1** first.
- _2026-06-30_ — **Checkpoint committed** `3945e4764` (works.py language fix + design/POC/findings).
- _2026-06-30_ — **Approach switched to incremental + validate-first** (small slice → PO tests user
  story → continue). Milestone table is now a backlog menu, not a build order.
- _2026-06-30_ — Effort moved into this tracked folder; investigation persisted to avoid re-explore.
- _2026-06-30_ — **Manual mode decided:** keep **Classic** as designed (ticks original design),
  QoL-only — idle autosave (L2) + ungate media/callouts (L3). Folds into M0. See
  [`stories/01-manual-write.md`](stories/01-manual-write.md).
- _2026-06-30_ — **Translation decided:** persistent Translate mode (extract `ChapterTranslationsPanel`)
  + **manual/human-first translation (B4)** seeded from source, AI kept as a peer option, center
  side-by-side. **M1 becomes full-stack** (one small translation-service seed-from-source endpoint).
  See [`stories/02-translation.md`](stories/02-translation.md).
- _2026-06-30_ — **Compose re-frame:** AI chat = the CORE (story 04, "Claude Code in VS Code" — tool
  curation + skills + model settings, the one place we add NEW build). Panels = a Photoshop/AE
  **toolbox that already exists** behind flag `loom.workspace.enabled` (story 05). **Media tool
  DEFERRED** (classic books have no media). **Core problem identified:** the compose GUI encodes no
  creative PROCESS — need a **guided journey** ordering the 24 tools (story 06, investigating).
- _2026-06-30_ — **PO-pivot: output QUALITY before GUI.** POC chapters read as concatenated scenes →
  fix the **planning/synthesis** layer first. New design track:
  [`../2026-06-30-chapter-synthesis-self-healing.md`](../2026-06-30-chapter-synthesis-self-healing.md)
  (Phase 0 planning connectivity → Phase 2 multi-pass self-heal).
- _2026-06-30_ — **Phase 0 slice 1 (intra-chapter connectivity)** validated — enriched decompose
  prompt (goal·conflict·outcome + causality + ending-guided); fixed the 3 worst reviewer defects at
  the synopsis level (prompt-only).
- _2026-06-30_ — **Phase 0 slice 2 (cross-chapter threading)** ✅ committed — typed `ChapterExitState`
  delta threaded chapter→chapter (`thread_state`, default off); live worker smoke (Gemma, 12ch) shows
  chapters now continue from the prior exit-state, **no arc repetition**. review-impl: 0 HIGH, 4
  findings fixed/accepted; composition unit suite 1180 + slice tests green. **Next: POC self-heal —
  measure the `stitch` baseline first.**
- _2026-07-01_ — **Self-heal cheap-stack judge upgrade shipped + driven over CH1–12** (engine
  `self_heal.py`: grounded judge + vote + verify + sentence-snap + pronoun prefilter; commits
  `ac93981fb` + follow-up). Pronouns fixed book-wide, no inflation; verify found to be a **double-edged
  sword** (stochastic, drops some real findings). **PO decision:** expose the heal as a **user-controlled
  feature** (manual + opt-in auto) behind an **accept/reject review-gate**, never silent — new story
  **C7 / M6** ([`stories/07-self-heal-polish.md`](stories/07-self-heal-polish.md)), lands in the UX/UI track.
