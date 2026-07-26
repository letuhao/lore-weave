# Story 06 — The compose journey (process, not tools) ★ CORE PROBLEM

> **Status:** 🟡 investigating (workflow/dependency map in flight) · **Epic:** C (the real C1) ·
> **Evidence:** pending agent map; will cite `composition-service` + `CompositionPanel` tools.

## PO insight (the actual root cause)
> "I'm an engineer, I don't really know how to write. I need to make an idea first. What's the tool to
> do that — scene generator? motif usage? template? There are a lot of tools but I don't know how to
> pick the first one, how to use them, or how to wire them. **That is the problem of the current
> compose GUI.**"

The 24 tools exist and are individually wired, but **the GUI encodes no creative PROCESS.** A
non-writer has no entry point and no sense of order/dependencies. Grouping (C2) and the toolbox (story
05) are downstream cosmetics — **the primary fix is to give the tools a guided ORDER**: a journey from
*nothing → idea → structure → scenes → draft → refine → assemble*, with each tool mapped to a step and
the "what do I do next" always answered.

## What we need to design (after the map returns)
1. **A guided authoring journey** — the canonical ordered path, with the MINIMUM viable chain (empty
   Work → first drafted scene) highlighted, and the full path available.
2. **The ideation entry** — the first tool for "make an idea" (premise/logline → outline). Likely the
   AI chat / cowriter + template + planner; confirm with the map.
3. **Per-step "next action"** — every step says what tool to use now and what it produces (extends the
   existing `useGuidedFirstRun`).
4. **Tool→step mapping** — the 5-section grouping (story 05 / M2) re-derived from the *process*, not
   arbitrary categories.

## Workflow / dependency map (from the engine — canonical)

**Tier-0 prerequisites (nothing works without these):** a **Work** (`project_id`, via
`POST /books/{id}/work`) + a **chat model** selected.

**Ideation entry:** the **CoWriter chat** (zero deps beyond a model) — brainstorm premise/characters.
There is **no premise→outline wizard**; the **Planner** IS the premise→outline tool but is never
surfaced as "next".

**The idea→draft chain (how tools wire):**
| Phase | Tool(s) | Consumes | Produces |
|---|---|---|---|
| ① **Idea** | CoWriter chat | a vague idea + model | premise/logline, character & plot ideas (as compose guide) |
| ② **Structure** | Planner (+ Beats, Scene Graph) | structure_template + premise + model; **EXISTING chapters** | outline: scenes per chapter (+ beat_role, tension, cast) |
| ③ **Story bible** *(opt., grows)* | Cast, RelMap, Timeline, Arc, WorldMap, Canon rules, References, Grounding, CanonView | knowledge-graph extraction (external), authored rules | grounding context for drafting |
| ④ **Draft** | Compose (Generate→Accept), Assemble | `sceneId` + `modelRef` (+ optional guide, grounding) | scene prose (job, critic) |
| ⑤ **Refine** | Critic, Quality, Style/Voice, Threads, Conformance, Motifs, Flywheel | a generation job / prose | scores, violations, tuned voice, motif bindings |
| ⑥ **Assemble** | Assemble / Stitch | chapter with all scenes `status='done'` | chapter prose → publish (M9 gate) |
| meta | Settings, Progress | project | config, stats |

**Minimum viable path to first prose** (`useGuidedFirstRun`, ≤2 clicks): Work → model →
"Set up co-writer" (auto-creates "Opening scene") → Compose → Generate → Accept. **Skips ideation +
structure** — so it's NOT the non-writer's path; the 6-phase journey above is.

**Compose preconditions** (`ComposeView.tsx:64`): `canGenerate = !!sceneId && !!modelRef`. Guide +
grounding optional. So the shortest chain to prose is just *scene + model*.

**Motifs** = primarily refinement/self-enrichment (mine from existing prose; bind in planner;
conformance audit). Can feed ideation only after a draft exists. **Not a first tool.**

### ⚠ Key gotcha — Planner does NOT create chapters
`plan.py`: decompose "NEVER mints book chapters" — it reuses the book's **existing** `chapter_id`s and
decomposes each into scenes. ⇒ a brand-new book with **no chapters** can't be structured until a
chapter exists. **The journey must create the first chapter as part of structuring.**

### Gaps for a non-writer (why the GUI is process-blind)
No getting-started wizard beyond the first-scene primer; no "recommended next step" in the UI; the
KG-extraction dependency for Cast/Timeline/Arc/World is buried; Planner preview must be manually
committed (no resume); tab order (`compose` first) reflects UI ownership, **not** creative process.

## Ideal visualization → then POC
**Ideal story graph (design target, NOT current code):**
[`../compose-ideal-journey.html`](../compose-ideal-journey.html) — open in a browser. Visualizes the
blank-page problem (the PO's failed-Gemma-brainstorm anchor), the always-present AI assistant + Journey
rail, the 6 phases (each a toolbox group), and the FIX-vs-today per phase.

**Next step (agreed sequence):** POC the **current source** phase-by-phase against the ideal and mark
each step **✅ wired / 🟡 hidden-or-unsequenced / 🔴 missing** — that diff becomes the build backlog
for the compose journey.

## Proposal — the journey IS the grouping
Group the 24 tools **by the 6 phases** (= the toolbox grouping, story 05 / M2) **and** surface the
phases as a **guided path** with an always-present "do this next" cue (extend `useGuidedFirstRun` into
a journey state machine: detect premise? outline? draft? → next action). The **AI chat** sits at phase
① *and* remains the always-present core (story 04). This unifies **C1 (journey) + C2 (grouping) +
C3 (discuss→content)** into one design.

## Phase ② Structure — open issue: structure-template authoring (mapped)
**PO finding:** structure templates have **no design / no manual edit**; PO suggests **extending the
motif system**.

**Findings (evidence):**
- **Read-only today.** 6 seeded built-ins; `GET /templates` only — no POST/PATCH/DELETE, no editor UI
  ("custom-template authoring is a later surface", V0). `structure_template` table already has
  `owner_user_id` + the repo filters `owner_user_id IS NULL OR = caller` → **per-user is schema-ready**,
  just no write path. (`composition-service db/models.py:99-105`, `repositories/structure_templates.py`,
  `routers/plan.py`.)
- **Motif system already has the full machinery** structure-templates lack: CRUD
  (create/patch/archive), proven tenancy (owner-stamped, **clone-to-edit**, System read-only,
  visibility/quota), and a **`beats[]` of the SAME shape** the Planner consumes (`key/label/purpose/
  order`). (`db/models.py:357-408`, `routers/motif.py`.)
- **Arc-templates are richer** (multi-thread *layout of placed motifs* + roster), NOT a flat beat list
  → not a Planner drop-in; the Planner only wants flat beats. Conceptually: **motif → arc-template →
  structure-template = three scales** of reusable structure.
- **Tenancy risk:** built-ins are global rows (`owner_user_id IS NULL`); safe only while read-only.
  Authoring MUST be owner-only writes + **clone-to-customize** (copy motif repo's uniform-404 pattern).

**Options (storage):**
- **A — literally extend motif** (`kind="structure"`, beats-only; decompose accepts `motif_id` OR
  `structure_template_id`). Reuses all motif infra; cost = overloads "motif" + dual id-space + seeds in
  another table.
- **B (rec) — add CRUD to `structure_template`** (POST/PATCH/DELETE), copying the motif tenancy pattern;
  **surface in the same "Structure Library" UI as motifs/arc-templates** so it *feels* unified.
  Keeps decompose single-id-space + structure-template a clean concept (~200 LOC).

**Scope:** net-new **backend** build (CRUD + MCP tools + FE beats editor) — a Structure-template
authoring milestone within the compose-journey build (NOT pure FE).

- [x] **S-D1** — design + manually edit structure templates: **YES** (real gap; V0 deferred it).
- [ ] **S-D2** — storage: **Option B** (CRUD on `structure_template` + unified library UX) _(rec)_ vs
  **Option A** (literal motif reuse). _PO to choose._
- [ ] **S-D3** — tenancy: System read-only + per-user clone-to-edit (copy motif pattern). _(rec: lock yes.)_

## Phase ③ Story Bible — feature: Canonical Cast & Naming Convention (POC-surfaced)
**POC finding (2026-06-30):** generation invents **inconsistent** character names across scenes (MC =
"Linh" one run, "Lâm Uyển" the next) and **out-of-genre** supporting names (mundane "bà Lý" / "ông Lâm"
instead of tiên-hiệp Hán-Việt). No canonical cast or naming convention feeds the drafter.

**Feature:** a Story-Bible/setup step that lets the author establish, early and once:
- a **canonical cast** with **genre-appropriate names** (tiên hiệp Hán-Việt: họ + tên kép),
- a **naming convention / honorific style** (gia chủ / trưởng lão / công tử / tiểu thư; avoid modern
  "ông/bà + họ"),
- persisted as **canon** (canon rules + cast entities) so EVERY scene draft stays consistent + in-genre.

Pairs with the language-inheritance fix (Work now carries `source_language`) — naming is the next "book
identity" attribute the journey should set up front. **POC validates the gap + the fix.** → see
[`../poc/02-findings.md`](../poc/02-findings.md) #4.

- [ ] **SB-D1** — cast + naming-convention as a first-class Story-Bible step (canon-persisted)?
- [ ] **SB-D2** — offer AI-suggested genre-appropriate names (one-click cast) vs author-typed only?

## Open decisions (PO)
- [ ] **J-D1 — Adopt the 6 phases** (Idea → Structure → Bible → Draft → Refine → Assemble) as BOTH the
  guided path AND the toolbox grouping? _(rec: yes.)_
- [ ] **J-D2 — First action = "Brainstorm an idea" in the AI chat** → hands off to Planner? _(rec: yes.)_
- [ ] **J-D3 — Delivery = first-run wizard + persistent "next step" guide** over the toolbox? And
  **auto-create the first chapter** when structuring a fresh book (dodge the Planner gotcha)? _(rec: yes to both.)_

## Decisions locked
_(none yet)_
