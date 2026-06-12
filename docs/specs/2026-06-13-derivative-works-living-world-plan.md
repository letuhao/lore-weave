# Derivative works (dị bản) → Living World — writer-feature focus & build plan

**Date:** 2026-06-13
**Persona:** P1 author (advanced) · feeds P2 worldbuilder · substrate for the "living world"
**Status:** PLAN. The feature is **already designed** (vision §9 / requirements FR-H1..H5 / UX §7) but
**unbuilt** and locked to **V2** ("after core engine proven", Decision D3). This doc bridges that design to a
buildable plan, connects it to the **living world**, and states the prerequisites that gate real value.

Source design (do not duplicate — cite):
`docs/specs/2026-06-02-composition-service-vision.md` §9 (derivatives, COW graph),
`docs/specs/2026-06-02-composition-requirements.md` §3 FR-H1..H5 (scope, V2),
`docs/specs/2026-06-02-composition-studio-ux.md` §7 (divergence taxonomy + wizard + studio).

---

## 1. What the writer wants (the job)

> "I have a finished/ongoing work. I want to spin an **alternate version** — a genderbent lead, a side
> character's POV, a fix-it where the tragic ending doesn't happen, or a full AU from chapter 30 — **without
> copy-pasting and re-explaining the whole world to the AI**. The variant should *inherit* the canon up to the
> branch point, then *diverge*, and stay internally consistent on its own terms."

Vietnamese: **dị bản** = a divergent variant that forks from an original canon. It is the writer-facing name
for what the design calls **derivative works (同人 / AU / 番外)**.

These variants are not throwaway — they are the **raw material for a living world** (§5): a base world plus a
tree of coexisting alternate timelines that share lore below their divergence points.

---

## 2. The architectural choice (already made — and it's the right one for a living world)

Two ways to "fork from canon" exist; they serve **different intents**. Pick per intent, don't conflate.

### (A) Copy-on-write reference + override + delta — **the dị bản / living-world model** ✅ (vision §9.2)
- The derivative is a **new composition Work** carrying `source_work_id` + a `divergence_spec`.
- **Base lore is inherited by reference**, read-only, **filtered to ≤ `branch_point`** — *not copied*.
- **Overrides** (`entity_override[]`, e.g. "Kael → female") are applied **at every retrieve** inside COMP's
  context packer → cross-chapter consistency for free, no find/replace, **no knowledge-service change**
  (COMP-A6). The derivative's own approved chapters extract into a **delta layer** (its own graph) via the
  existing flywheel.
- **Why it fits the living world:** branches stay cheap, share a base, and can multiply. The base world has one
  source of truth; each timeline is a thin spec + a delta. This is a **branching-canon multiverse**, not N
  full copies.

### (B) Full clone across services — a *different* feature ("make an independent copy")
- The data-model survey mapped what a full clone touches: book/chapter/parts/scenes (book-service), entities/
  EAV/evidence/wiki (glossary), project/summaries/Neo4j subgraph (knowledge), work/canon/outline
  (composition) — a 4-database saga with ID-rewrite and re-anchoring.
- This is heavy, needs a distributed-transaction/outbox saga, duplicates lore, and **breaks the "one base
  world" premise** the living world needs. Reserve it for a future "hard-fork / export-as-new-book" action,
  **not** for dị bản.

**Decision for this plan: build (A).** It's what vision §9 committed to, it's cheaper, and it's the only one
that yields a living world rather than a pile of disconnected copies. *(No book/glossary/knowledge schema
changes; all new tables live in composition-service.)*

---

## 3. Divergence taxonomy (what kinds of dị bản) — UX §7.1

| Family | Variants | Override shape |
|--------|----------|----------------|
| **POV shift** (视角) | side-character narrator · same character, new lens · new inserted character | `pov_anchor` (entity) + narration overrides |
| **Character transform** (人物改写) | 性转 genderbend · 黑化 dark-turn · role-reversal · fix-it · CP/relationship rewrite | `entity_override[]` (field, new_value, kind) |
| **Universe / AU** (架空) | canon-divergence from Ch.N · total AU · crossover/fusion | `au_template` + new `canon_rule[]` |

All three reduce to the same primitives: a **branch_point**, an optional **pov_anchor**, a set of
**entity_overrides**, and additional **canon_rules** — captured in one `divergence_spec`.

---

## 4. What to build (delta against today's code)

Composition core V0 is built and functional (Works, outline, canon rules, generation, critic, flywheel,
packer). The derivative machinery is **entirely missing**. Concretely:

### 4.1 New composition-service tables (vision §9.1) — *new migration only, no other service*
- `derivative_work(project_id PK, source_work_id, branch_point, divergence_type, status, created_at …)`
  — or fold onto `composition_work` with nullable `source_work_id` + `branch_point` (lighter; recommended).
- `divergence_spec(id, project_id, branch_point, pov_anchor_entity_id, au_template, divergence_type, …)`
- `entity_override(id, project_id, entity_id, field, new_value, kind)` — kind ∈
  {genderbend, dark_turn, role_reversal, attribute, pov, …}

### 4.2 New API (composition-service)
- `POST /works/{source_project_id}/derive` — create a derivative Work from a source + a `divergence_spec`
  (idempotent; **no data clone** — just the spec + a new Work row).
- `GET/PATCH /works/{project_id}/divergence` — read/edit the spec + overrides.
- (Reuse existing outline/prose/generate/critic routes; the derivative is "just a Work" to them.)

### 4.3 Packer change (the heart — vision §9.2)
Extend the existing context packer: when a Work has a `divergence_spec`, the retrieve becomes
`source-graph(≤ branch_point)` → **apply entity_overrides** → **merge with derivative delta-graph** →
budget → inject. Overrides re-applied every pull = consistency without rewriting history.

### 4.4 Critic change
Add a derivative dimension: enforce overrides across all chapters ("called Kaela 'he'" is a violation) and
catch derivative-internal contradictions — reuse the existing critic harness, new rule source.

### 4.5 Flywheel
Approved derivative chapters → existing extraction → **delta** graph (not the base). Base stays read-only.

### 4.6 Frontend
- **Divergence Wizard** (UX §7.2, 4 steps): source & branch point → divergence type → overrides preview
  (inherited grey · overridden highlighted, editable) → name & create. Mockup exists:
  `composition-doujin-mockup.html`.
- **Derivative studio** (UX §7.3): divergence banner ("同人 of «…» · diverges from Ch.N"), 2-layer grounding
  panel (INHERITED vs OVERRIDDEN badges), original chapters as an optional **reference spine**.
- **What-if → derivative promotion** (§9.5): the existing/planned what-if "promote" action gains a third
  option, "spin off as a persistent derivative."

---

## 5. From dị bản to **Living World** (the user's north star)

A living world is not one book — it's a **base world + a tree of timelines** that share lore below their
divergence points and evolve independently above them.

```
            ┌─ canon timeline (the source Work) ───────────────▶ (grows)
 BASE WORLD │
 (shared    ├─ dị bản A: genderbend lead, branch @ Ch.1 ───────▶ (its own delta)
  lore ≤    │
  branch)   ├─ dị bản B: side-POV, branch @ Ch.12 ─────────────▶
            │
            └─ dị bản C: fix-it AU, branch @ Ch.30 ────────────▶
```

- Each branch is a thin `divergence_spec` + `entity_override[]` + its own delta graph. Cheap to spawn, cheap
  to keep. The base world has **one** source of truth.
- **This is why the COW model matters:** the living world *is* the COW tree. Full-clone forks would shatter it
  into disconnected copies with no shared base — no "world," just files.
- **Convergence with the newcomer review:** the Day-0 finding **BL-6 / §6 #3 — "world" as a first-class
  container** is the *same object* the living world needs. Build the **world container** once and it serves
  both: (a) the worldbuilder's prose-less entry, and (b) the root that holds a canon Work plus its dị bản
  branches as a navigable timeline tree. **Design them together, not twice.**
- Future living-world surfaces (post-MVP): a branch/timeline graph view; "what's true in branch X at Ch.N";
  cross-branch character diff ("Kael across all timelines"); promoting a branch to its own canon.

---

## 6. Prerequisites & honest sequencing (what must be true first)

Derivatives are the **advanced payoff**, not a quick win. They sit on top of:

1. **A working creation substrate.** The knowledge/rerank/QoL hard-blocks (BL-1..BL-4 in the use-cases doc)
   must clear — the COW packer merges a **base graph**; if knowledge build is blocked, the base layer is empty
   and the derivative's headline benefit ("inherit the world, then diverge") degrades to canon-rules-only.
2. **Composition core proven (V0/V1).** It is built; confirm grounding + critic + flywheel are solid on a
   *normal* Work before layering override-at-retrieve on top.
3. **The "world" container (BL-6)** — strongly recommended *before* derivatives, so branches have a home and
   you don't build the wizard against a book-only model and rework it.
4. **Roadmap reality:** this is **locked to V2** (Decision D3, "after core engine proven"). Pulling it forward
   is a deliberate re-prioritization — fine, but do it eyes-open: ship the substrate + world container first,
   or the dị bản demo will look impressive and *ground on nothing*.

---

## 7. Phased build plan (each phase shippable)

| M | Scope | Depends on | Demo |
|---|-------|-----------|------|
| **M0** | Schema: `source_work_id`+`branch_point` on `composition_work`, `divergence_spec`, `entity_override`. `POST /derive` (spec only, no clone). | core V0 | create a derivative Work via API, see it linked to source |
| **M1** | Divergence Wizard FE (4 steps) + derivative studio banner + 2-layer grounding badges | M0 | author spawns a genderbend dị bản from the UI |
| **M2** | Packer override-merge: `base(≤branch) + overrides + delta` | M0, knowledge substrate (BL-1..4) | generate a scene; overridden entity stays overridden across chapters |
| **M3** | Critic enforces overrides + derivative-internal consistency | M2 | critic flags "Kaela called 'he'" |
| **M4** | Flywheel on delta + what-if→derivative promotion | M2 | approve a dị bản chapter → its delta graph enriches next-scene grounding |
| **M5** | Living-world container + branch/timeline tree view (shared with BL-6 world container) | M0–M4, BL-6 | one world shows canon + 3 dị bản branches as a tree |

**Verification note (CLAUDE.md):** M2–M4 touch composition + knowledge at the seam → cross-service live-smoke
required (real base-graph retrieve with an override applied, on a stack-up), not mock-only. Rebuild touched
images first.

---

## 8. Open design questions to lock before M0

1. **Branch-point granularity:** chapter-only, or chapter×scene (the canon `from_order`/`until_order` stride
   supports finer)? Finer = more precise inheritance, more UI.
2. **Override scope:** only glossary-entity fields, or also relationships/events/canon-rules as overridable?
   (Start with entity fields + added canon rules; defer relationship overrides.)
3. **Delta extraction model:** new `knowledge_project` per derivative (clean isolation, more rows) vs a
   project-scoped delta partition keyed by `(user_id, project_id)` in the existing Neo4j (vision leans
   partition). Confirm with knowledge-service owner — **but no knowledge *schema* change either way.**
4. **Reference spine policy:** is the original's Ch.N shown verbatim as adaptable source, or only summarized,
   to avoid the derivative becoming copy-paste?
5. **Ownership/sharing of a dị bản** (ties to the translator/derivative ownership gap, §4A N-T #6): who owns a
   variant of a shared/collaborative work; what's publishable.
6. **World container first?** Decide now whether M0 targets a book-rooted Work (rework later) or the world
   container (BL-6) up front. Recommendation: **world container first** — it's shared substrate.
