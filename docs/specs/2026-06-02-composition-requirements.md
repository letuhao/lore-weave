# Composition Service — Requirements (FR + NFR)

> **Date:** 2026-06-02 · Anchor for the DESIGN phase — extracted from the UX/UI drafts so design doesn't drift.
> **Sources:** [vision](2026-06-02-composition-service-vision.md) · [UX](2026-06-02-composition-studio-ux.md) · mocks: [studio v3](composition-studio-mockup-v3.html) · [components](composition-studio-components.html) · [what-if](composition-scene-graph-whatif.html) · [同人](composition-doujin-mockup.html) · research: [prior-art](../research/2026-06-02-ai-novel-composition-prior-art.md) · [competitor audit](../research/2026-06-02-competitor-ui-ux-audit.md).
> **Priority tags:** `[V0]` thinnest-useful co-writer · `[V1]` planning + non-linear + 同人 · `[V2]` polish/advanced. `⚑DECIDE` = needs author sign-off.

---

## §0 Open decisions before DESIGN (the only gating ones)

- **✅ D1 — V0 boundary (LOCKED).** V0 = Editor (Casual/Power) + **Co-writer + Grounding + Critic + Canon Rules + Outline + Scene Graph** + structure templates + **RAG packer + flywheel** + project-resolve/provision. *(Lore-grounded co-writer **with visual planning**.)*
- **✅ D2 — Autonomy (LOCKED).** Co-writing-first (stream) in V0; autonomous chapter-gen (job) in V1.
- **✅ D3 — 同人 priority (LOCKED).** Derivatives → **V2** (after the core engine is proven).
- Resolved: COMP-A1..A6, COMP-Q1 (co-writing-first), COMP-Q3 (genre-agnostic templates). UX U1–U5 = decide during design.

---

## §1 Functional Requirements

### A · Work & project
- **FR-A1** `[V0]` Composition is a tab in `BookDetailPage` (`/books/:bookId/composition`), book-scoped.
- **FR-A2** `[V0]` A Work = a book-typed knowledge project (`project_type='book' ∧ book_id NOT NULL`). Resolve the book's project deterministically; **none → user confirm-create** (reuse knowledge `ProjectCreate`); **>1 → select**; never silent auto-create.
- **FR-A3** `[V0]` Composition owns its tables keyed by `project_id`; **never writes `knowledge_projects`**. "Is a Work?" = presence of composition rows.

### B · Editor & writing (Casual)
- **FR-B1** `[V0]` Reuse the existing TipTap editor (`ChapterEditorPage`) + `useEditorMode`/`useEditorPanels` + the stubbed AI panel. Composition fills them, not a new app.
- **FR-B2** `[V0]` **Classic = Casual** (today's minimal editor) · **AI = Power** (unlock AI panel + components). Progressive disclosure.
- **FR-B3** `[V0]` Inline AI continuation (streaming) + accept / edit / regenerate.
- **FR-B4** `[V1]` Selection tools — rewrite / expand / describe / tone.
- **FR-B5** `[V1]` Slash menu `✦ Continue / Ask`.
- **FR-B6** `[V1]` **Provenance highlighting** — AI-written-unreviewed text marked until edited.
- **FR-B7** `[V1]` **Focus / typewriter mode** — hide panels, dim non-current paragraphs, floating continuity pill.
- **FR-B8** `[V1]` **In-prose mention-linking + heatmap** (entities highlighted; "what AI will get" preview).
- **FR-B9** `[V0]` **SceneAnchor TipTap extension** — scene boundaries as anchor nodes (carry `scene_id`) inside chapter content; **source of truth for intra-chapter scene order**; Outline/Scene-Graph CRUD syncs with them. *(Required by sub-chapter granularity, D1=b.)*

### C · AI panel (Power-default trio)
- **FR-C1** `[V0]` **Co-writer** — guide input → generate → insert; continue/ask.
- **FR-C2** `[V0]` **Grounding** — live RAG context for the scene (present cast / lore / active canon rules), spoiler cutoff label, pin/exclude, mention heatmap; **inherited/overridden badges** for derivatives.
- **FR-C3** `[V0]` **Critic** — calibrated judge scores (coherence / voice / pacing / canon-consistency) + issues surfaced **inline** (continuity linter), not a buried report.

### D · Structure & planning (Power)
- **FR-D1** `[V0]` Outline tree (Arc→Chapter→Scene→Beat).
- **FR-D2** `[V0]` **Scene Graph** canvas — `scene_node` + typed `scene_link` (sequence / character-thread / setup→payoff); "open in editor". *(V0 = view/organize; what-if branching on it = V1.)*
- **FR-D3** `[V1]` Beat Sheet — structure template, beat→scene mapping (filled/empty).
- **FR-D4** `[V1]` Plot Threads — open/paid tracker; flag dangling setups.
- **FR-D5** `[V1]` Beats-as-objects with inline `[directives]`.
- **FR-D6** `[V0]` Pluggable **structure templates** (Save the Cat / Hero's Journey / Story Circle / Kishōtenketsu / web-novel). Seed first-run (no blank slate).
- **FR-D7** `[V2]` Corkboard (index-card view).

### E · World & canon
- **FR-E1** `[V1]` Cast & Codex — entities from glossary + knowledge graph; Linked-Mentions per entity.
- **FR-E2** `[V1]` Relationship Map — curated colored edges; edits write back via `relations/correct`.
- **FR-E3** `[V1]` Timeline — chronology + spoiler cutoff; **filter by entity**.
- **FR-E4** `[V0]` **Canon Rules** — declarative invariants (author-owned); feed packer head + critic.
- **FR-E5** `[V2]` Character Arc · `[V2/opt]` World Map.

### F · Style / voice / references
- **FR-F1** `[V1]` Style profile (prose sliders: density / pace / interiority).
- **FR-F2** `[V1]` Voice profiles per character.
- **FR-F3** `[V2]` Reference sources (comps / sample passages; retrieved semantically, never copied).

### G · Non-linear exploration
- **FR-G1** `[V1]` **What-if branch** — from a scene, spawn an alternate **sandbox** branch (scene + downstream); does not touch the manuscript until promoted.
- **FR-G2** `[V1]` Judge **scores each branch** vs canon (canon-consistency + dimensions).
- **FR-G3** `[V1]` Branch lifecycle — **Promote** (collapse to canonical) / Discard / New what-if / **spin off as 同人**.
- **FR-G4** `[V1]` **Alternate takes** — N variations of one scene; compare side-by-side; pick/merge. (Lifecycle, not infinite scroll.)
- **FR-G5** `[V1]` **Gap-fill / bridge** — write the scene between two existing scenes.
- **FR-G6** `[V1]` Write **out of order** (non-linear drafting; status per scene).

### H · Derivative works (同人 / AU) — **all `[V2]`**
- **FR-H1** `[V2]` Create a derivative Work via the **Divergence Wizard** (source → branch point → divergence type → overrides → name).
- **FR-H2** `[V2]` Divergence taxonomy — POV shift · character transform (性转/黑化/role-reversal/fix-it/CP) · AU.
- **FR-H3** `[V2]` **2-layer COW graph** — inherited base (≤ branch_point, read-only) + delta; **override applied at retrieve**.
- **FR-H4** `[V2]` Derivative opens in studio with **divergence banner** + inherited/overridden grounding + **reference spine** (adapt original Ch.N or write fresh).
- **FR-H5** `[V2]` Critic enforces overrides across all chapters; flywheel runs on the delta layer.

### I · Generation engine
- **FR-I1** `[V0]` **RAG packer** — constraint-shaped context assembly; priority ladder: `canon_rule > present-entity state > recent prose > semantic refs > summaries`; **spoiler cutoff** by scene position; token-budget trim. **(For derivatives: 2-layer merge + override.)**
- **FR-I2** `[V0]` Co-write mode (stream) · **FR-I2b** `[V1]` autonomous mode (job + RabbitMQ callback).
- **FR-I3** `[V0]` Agent loop: plan → retrieve → draft → critique → revise → commit → write-back.
- **FR-I4** `[V1]` Generate N takes/branches = N parallel `completion` jobs.
- **FR-I5** `[V0]` **Flywheel** — approved chapter → book-service → existing extraction → graph → next-scene grounding.

### J · Composability (layout)
- **FR-J1** `[V1]` Panels **dock / float / pop-out**; `+` picker (dock-as-panel vs open-as-view).
- **FR-J2** `[V1]` Layout persisted **per-device** (localStorage; UI-state only).
- **FR-J3** `[V1]` Big surfaces = opt-in **view overlay** (Scene Graph / Timeline / Beat Sheet) with a multi-view switcher; Story Map entry from toolbar.
- **FR-J4** `[V2]` Command palette + shortcuts (Power).

### K · Integration (reuse, no-conflict)
- **FR-K1** `[V0]` Read canon via knowledge HTTP — `drawers/search` (semantic), `timeline?before_order=` (spoiler), entity/relations reads — + glossary `select-for-context` / entities.
- **FR-K2** `[V0]` LLM via `loreweave_llm` (`completion`/`chat`/`stream`/`summarize_level`) — provider-gateway only.
- **FR-K3** `[V0]` Judge via `loreweave_eval` (new prose dims) — reuse harness.
- **FR-K4** `[V0]` Async jobs via outbox → worker-infra relay → Redis Streams; FE progress via the WS `EventsGateway`.
- **FR-K5** `[V0]` Project ensure-create via knowledge `ProjectCreate` (API call, user-confirmed).

---

## §2 Non-Functional Requirements

- **NFR-1 — Isolation / no-conflict.** New service + own DB; only additive touch-points (1 gateway route, 1 contract file, 1 compose block); **no schema change to other services**; own `COMP-*` ID prefix + Redis-stream namespace.
- **NFR-2 — Provider gateway.** All LLM via `loreweave_llm`; no direct SDK; BYOK-cloud and local LM Studio same code path.
- **NFR-3 — Language.** Python / FastAPI (AI-service rule).
- **NFR-4 — Persistence / SSOT.** All user data in Postgres / S3; **no localStorage for user data** (only per-device layout); multi-device consistent.
- **NFR-5 — Theme.** App tokens — amber `primary`, teal `accent`, warm; respect user theme (dark default / light / sepia / oled).
- **NFR-6 — Progressive disclosure.** Casual genuinely minimal; complexity opt-in; never overwhelm (the field's #1 failure).
- **NFR-7 — FE MVC.** hooks=controllers / context=services / components=views; **no conditional unmount** of stateful panels (CSS hidden); split context by update frequency (stable vs streaming); reuse TipTap + editor hooks; ≤100 lines/component, ≤200/hook.
- **NFR-8 — Quality gate.** Prose-critic calibrated + anti-self-reinforcement (reuse eval harness); surfaced **inline**, not buried.
- **NFR-9 — Cost governance.** Per-job `max_chunks` / `max_candidates`; track via `usage-billing-service`; user budget caps; N-take fan-out bounded.
- **NFR-10 — Spoiler-safety.** Retrieval respects `timeline?before_order=` by the scene's position (no future leakage); derivatives respect branch_point.
- **NFR-11 — Performance.** Streaming latency for co-write; long gen = async jobs; per-lens retrieval timeout + graceful degrade; warm-cache friendly.
- **NFR-12 — Multi-tenant security.** User-scoped (JWT `user_id`); cross-user = 404 (anti-leak); derivative inheritance respects source ownership/sharing.
- **NFR-13 — i18n / multi-locale.** Generation per book locale; multi-language capable.
- **NFR-14 — Trust / provenance.** AI output marked; grounding **inspectable** (not a black box).
- **NFR-15 — Idempotency / concurrency.** Generation jobs idempotent; optimistic concurrency (If-Match) on edits; append-only `revision`; branches/takes have a lifecycle (no orphan accumulation).
- **NFR-16 — Observability.** Metrics: gen latency, judge scores, cost; online eval flywheel.
- **NFR-17 — Accessibility.** Keyboard-first (shortcuts, command palette); a11y per existing patterns.

---

## §3 Scope ladder (proposed — ⚑D1/D2/D3)

- **V0 — lore-grounded co-writer + visual planning (LOCKED):** A1-A3 · B1-B3 · C1-C3 · **D1·D2**·D6 · E4 · I1·I2·I3·I5 · K1-K5. *(Write with AI, grounded on the auto-graph, continuity-checked, with Outline + Scene Graph, flywheel closing; co-writing/stream only.)*
- **V1 — full studio + non-linear:** B4-B8 · D3-D5 · E1-E3 · F1-F2 · G* (what-if/takes/gap-fill) · I2b·I4 (autonomous) · J1-J3 (dock/float/pop-out).
- **V2 — 同人 + polish/advanced:** **H*** (derivatives) · D7 · E5 · F3 · J4 · export-with-wizard · adaptive goals/stats · whole-draft snapshots.
