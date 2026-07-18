# Writing Studio — Completeness BUILD specs (roadmap)

> **Source of gaps:** [`../../plans/2026-07-17-studio-completeness-AUDIT.md`](../../plans/2026-07-17-studio-completeness-AUDIT.md)
> §6.5 synthesis. **This is a BUILD track, not a port track** — the audit proved the legacy code is itself
> incomplete, so the detail specs here BUILD the missing verbs (most at the data layer), they do not wire
> legacy forward.
>
> **HTML-draft rule (PO, 2026-07-17):** a spec gets an HTML draft in `design-drafts/screens/studio/` **only
> when the surface never had a GUI** (no legacy component to reference). A PORT reuses its legacy component
> as the design reference — no draft. A wire-up/affordance adds to an existing panel — no draft.

---

## The spec set

**Status: 12 specs WRITTEN + CLARIFY-SEALED 2026-07-17 (S-01..S-11) + 3 HTML drafts. Decisions: [`01_DECISIONS.md`](01_DECISIONS.md). Ready to BUILD (fanout, Tier-A parallel). G-WORKFLOWS sealed to THIS track (S-12).**

**+ S-13 added 2026-07-18** — `studio decompose surface` (G-STORY-STRUCTURE), the buildable home for the S-01
`D-S01-USE-IN-DECOMPOSE` debt. It is an **M FE-only port** (the decompose UX already exists in `usePlanner`/
`PlannerView`; this wraps it in a studio panel + wires the S-01 deep-link), **not** the "large new track" the debt
was mis-carried as. See [`S-13_studio-decompose-surface.md`](S-13_studio-decompose-surface.md).

| # | Spec | Tier | New verb(s) at DATA layer? | HTML draft? | Size |
|---|---|---|---|---|---|
| **S-01** | `structure-template authoring` — create/edit/delete a custom story structure | A | ✅ full write side (repo has only list+get) | ✅ **net-new** (`screen-structure-templates.html`) | M |
| **S-02** | `manuscript parts` — acts/volumes CRUD + move-chapter-to-part | A | ✅ parts CRUD + `part_id` on patchChapter | ✅ **net-new** (`screen-manuscript-parts.html`) | M+S |
| **S-03** | `references edit` — `UPDATE` + the edit affordance on reference-shelf | A | ✅ `ReferencesRepo.update` + `PATCH` route | ❌ port (`ReferencesPanel` is the reference) | S/M |
| **S-04** | `derivative delta editing` — mutate `divergence_spec` + `entity_override` | A | ✅ update/delete repo methods | ❌ port (`DivergenceManagerView` exists) | M |
| **S-05** | `KG fact authoring + triage surfacing` — author/invalidate a fact + the triage queue panel | B | ✅ fact-author route; triage is wire-up | ✅ **net-new** triage (`screen-kg-triage.html`) | S+M |
| **S-06** | `glossary attribute-value` — add-later via REST + delete a value row | B | ✅ REST add + delete method | ❌ affordance on the entity editor | S |
| **S-07** ✅ BUILT 2026-07-18 | `world-maps OCC + agent verbs` — OCC on MCP/image; MCP world_update/delete + chapter-reorder | B | ✅ image_version OCC decouple + world_update/delete + book_chapter_reorder | ✅ backend-only (RUN-STATE_S07) | S→M |
| **S-08** | `soft-archive RESTORE` — motif + arc-template restore (dead-end soft-delete) | B | ✅ `restore` repo method each | ❌ affordance | S |
| **S-09** | `small wire-ups` — corrections `list_for_job` route · glossary→graph seed route · wiki suggestion withdraw/status · view-aware graph reader (F-12) | B | mixed (routes over existing methods) | ❌ affordances | XS–S |
| **S-11** ✅ BUILT 2026-07-18 | `search activity-view` (PO D-a: BUILD) — mount RawSearchPanel + memory_search into the `search` nav | C | ✅ rail + SearchPanel (Text/Semantic) + registry (RUN-STATE_S11) | ✅ category `knowledge`; deep-links into editor | S |
| **S-12** | `workflows + workflow-proposals GUI` (G-WORKFLOWS, PO: build here) — 3 BE verbs (mirror skills) + 2 panels + mode-binding setting | B | ❌ 3 routes over existing repo | ❌ near-clone of ExtensionsPanel/ProposalsPanel | M |
| **S-10** | `Tier-C FE orphans` — style-voice + reference-shelf panels · Issues/diagnostics tab · bible/quality rails · MotifBindingLens mount · 3 arc agent-only surfaces · `[[`-create (PO D-d) | C | ❌ FE-only | ❌ (Issues tab layout = a small inline decision; the rest are ports/mounts) | S each |
| **S-13** | `studio decompose surface` (G-STORY-STRUCTURE) — closes the S-01 `Use in decompose` loop: a studio `decompose` panel hosting the existing decompose flow + a deep-link from `structure-templates` | A follow-on | ❌ FE-only PORT (decompose UX already exists in `usePlanner`/`PlannerView`) | ❌ port (`PlannerView` is the reference) | M |
| **S-01b** | `structure-templates UX hardening` — clears every S-01 dead-end + lifts the GUI score ≈6.3→≈8.4: blank-create on-ramp, feedback/safety layer (unsaved-guard, save-toast, human error copy, archive-confirm), narrow-dock `@container` responsive, i18n/a11y/kind-edit. A1 button wired via S-13 | A follow-on | ❌ FE-only (all verbs already backend-supported) | ❌ hardens existing panel | M |

**HTML drafts required (3):** `screen-structure-templates.html`, `screen-manuscript-parts.html`,
`screen-kg-triage.html`. Everything else references an existing component or adds an affordance.

---

## Ordering rationale

1. **Tier A first (S-01..S-04)** — these are DATA-layer builds. They gate everything downstream (a panel
   over `structure_template` is pointless until the write side exists) and carry the tenancy/OCC/migration
   risk that needs the most careful design. Each is a full spec: schema + migration + tenancy + repo + route
   + MCP + FE + tests.
2. **Tier B (S-05..S-09)** — route/MCP wire-ups over existing repo methods. Lower risk, faster.
3. **Tier C (S-10)** — the FE orphans (largely the A-3..A-13 actions from the audit). No backend.

Each Tier-A/B spec follows the repo's CLAUDE.md invariants explicitly: **User-Boundaries** (every new
table declares its scope tier + a `UNIQUE(scope_key, code)` constraint, never a global one),
**Settings-and-Config** (effective-value + source-tier where applicable), **MCP-first** (agent verb = an
MCP tool on the owning domain, not a bespoke endpoint), **Frontend-Tool-Contract** (closed-set args =
enums), and **OCC** where concurrent writes are possible.

---

## What must NOT be re-specced (audit-confirmed complete)

outline · canon rules · style/voice(BE) · arcs · plan runs · motif bindings · projects · schema/ontology ·
books/chapters · world maps CRUD · glossary entities/kinds/attribute-defs/revisions · wiki. Plus the
by-design absences (bitemporal fact/relation in-place UPDATE, entity hard-delete, import immutability,
append-only corrections). Re-specing these is scope-creep.

## Stale plan-30 rows to retire (do not carry into any new backlog)

G-WORLD-MAPS/BE-15 (UPDATE layer shipped) · arc_apply/drift `_pending_engine` flags (both wired) ·
G-ARC-SPEC-CRUD (closed) · G-KG-WRITE-HOLES createEntity claim (false at HEAD).
