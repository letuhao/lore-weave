<!-- CHUNK-META
source: 03_MULTIVERSE_MODEL.ARCHIVED.md
chunk: 01_four_layer_canon.md
byte_range: 2979-10619
sha256: 2b9b2a14f08b5f9f052984b3e26dc0f89532725c64ebef790da4c793b3f9fef1
generated_by: scripts/chunk_doc.py
-->

## 3. Four-layer canon model

The multiverse framing exposes a subtlety collapsed in earlier designs: canon has *levels*, not a single "canon vs drift" binary.

| Layer | Defined by | Can drift? | Scope | Example |
|---|---|---|---|---|
| **L1 — Axiomatic canon** | Author (explicit `locked=true` in book/glossary) | **Never** | Every reality | "Magic exists"; "Elves are a species"; "Gods are real" |
| **L2 — Seeded canon** | Book's initial state (default) | Yes, per reality | Each reality independently | "Alice is a princess" — can drift to "Alice is a blacksmith" in some reality |
| **L3 — Reality-local canon** | Events that happened in a specific reality | **Immutable within that reality** | Only that reality | "In R_β, Alice died at T=50" — fact of R_β, doesn't exist in R_α |
| **L4 — Flexible state** | Runtime / LLM drift | Drifts freely within a reality | Only that reality, often transient | Elena's mood today; NPC's recent thoughts |

### How the layers interact

- **Writes always land in L3 (events) or L4 (projection).** The act of playing does not change L1 or L2.
- **Reads cascade upward.** Query "what is Alice's job?" in reality R:
  1. Look in R's events (L3) — if set, return.
  2. Look in ancestor realities' events up to fork point (L3) — if set, return.
  3. Look in L2 seeded canon — if set, return.
  4. Look in L1 axiomatic canon — if set, return.
  5. Otherwise: unknown.

- **L1 is enforced globally.** Attempts to drift an L1 fact are rejected by a canon-guardrail layer (validation + possible LLM-output filtering).
- **L2 can drift.** Default position but not locked. Provides starting coherence; individual realities are free to diverge.

### Author controls the lock level

Author marks each attribute / fact at ingestion. MV1 locked: "Manual author flag + category heuristics." WA-4 below specifies the category heuristics.

```sql
-- In glossary-service or wherever canonical facts are authored
ALTER TABLE entity_attributes
  ADD COLUMN canon_lock_level INT NOT NULL DEFAULT 2,
  -- 1 = L1 axiomatic (never drifts)
  -- 2 = L2 seeded canon (default, drifts allowed)
  ADD COLUMN canon_lock_source TEXT NOT NULL DEFAULT 'author_default',
  -- 'category_default_l1' | 'category_default_l2'
  -- 'author_override_l1' | 'author_override_l2'
  -- 'author_default'
  ADD COLUMN canon_lock_changed_at TIMESTAMPTZ,
  ADD COLUMN canon_lock_change_reason TEXT;
```

Levels 3 and 4 are never authored; they emerge from play.

### Category heuristics for L1 / L2 default (WA-4)

When a fact is ingested, the author-assigned (or auto-detected) **category** determines the default `canon_lock_level` before any manual override. Three tiers:

#### Strong L1 defaults — world axioms (existence-of-category)

These categories describe the **existence and rules of foundational world elements**. Drifting them per reality would break cross-reality reference and narrative coherence.

| Category | Default | Rationale |
|---|---|---|
| `magic_system` | **L1** | Does magic exist? Axiom-level rules of how it works. |
| `species` | **L1** | "Elves exist in this world." Core roster of sentient kinds. |
| `deities` / `pantheon` | **L1** | Gods existing. Individual god attributes may override to L2. |
| `cosmology` | **L1** | Planets, dimensions, planes. Universe structure. |
| `physics_laws` | **L1** | Teleport/flight/resurrection permitted? Core world rules. |
| `tech_level` | **L1** | Medieval / modern / sci-fi — genre-defining. |
| `language_families` | **L1** | "Languages exist; common tongue exists." Individual languages → L2. |

#### Strong L2 defaults — specific instances (drift expected)

These categories describe **specific instances** that may legitimately differ across realities. Drift is a feature.

| Category | Default | Rationale |
|---|---|---|
| `characters` | **L2** | Alice is a princess in R_α, a blacksmith in R_β. Natural drift. |
| `locations` | **L2** | Specific places (tavern names, cities, castles). |
| `items` | **L2** | Magic swords, artifacts — per-reality presence. |
| `historical_events` | **L2** | "War of 1234" — different realities, different timelines. |
| `organizations` / `factions` / `guilds` | **L2** | Kingdoms, orders, syndicates — rise and fall per reality. |
| `currency` | **L2** | Specific currency names/values. |

#### Ambiguous — L2 default, surface L1 recommendation UI

For these categories, default is **L2** but the ingestion UI surfaces a **recommendation**: "If this is axiomatic for your world, mark L1." One-click promote.

| Category | Default | Recommendation trigger |
|---|---|---|
| `language` (individual) | L2 | If marked "divine language" or "world-foundational" → suggest L1 |
| `religion` (organized) | L2 | If central to world axioms ("the Church is God's only voice") → suggest L1 |
| `races` (sub-species) | L2 | Core races handled via `species`; sub-races usually drift |
| `magic_schools` | L2 | Specific schools drift; `magic_system` laws stay L1 |
| `social_structure` | L2 | "Feudal" vs "democratic" — may be axiomatic if genre-defining |

#### New/custom categories

When an author creates a custom category not in the above lists, **default is L2** (conservative — drift-safe). Author can override to L1 per-attribute via standard override flow.

#### Override UX — asymmetric policy

Changing default lock level has different risk profiles:

| Change | Risk | UX policy |
|---|---|---|
| L1 → L2 (loosen) | Low — relaxes constraint | One-click change + brief confirm dialog |
| L2 → L1 (tighten) | Medium — affects existing realities (may create L3 conflicts via M4) | **Requires justification text** (min 20 chars), recorded in `canon_lock_change_reason` |

L2 → L1 transitions trigger [§9.8 M4 canon-update propagation](#98-canon-update-propagation--m4-resolution) — existing realities with L3 overrides on that attribute are surfaced to author before commit.

#### Configuration

All category lists are **configuration-driven**, not hardcoded:

```
canon.category_defaults.strong_l1 = "magic_system,species,deities,cosmology,physics_laws,tech_level,language_families"
canon.category_defaults.strong_l2 = "characters,locations,items,historical_events,organizations,factions,guilds,currency"
canon.category_defaults.ambiguous = "language,religion,races,magic_schools,social_structure"
canon.category_defaults.ambiguous_behavior = "recommend"   # 'recommend' | 'force_choice' | 'silent'
canon.category_defaults.new_category_default = "L2"
canon.override.l1_to_l2_requires_justification = false
canon.override.l2_to_l1_requires_justification = true
```

Admin/author teams can extend categories without code changes. Changes take effect on future ingests; existing fact lock levels are unaffected unless explicitly re-evaluated.

### Canonization — promoting emergent narrative

An exciting reality can have events worth preserving. **Canonization** is the explicit flow to promote L3 events → L2 seeded canon (and rarely, L2 → L1 axiomatic). This is an author-gated action with review. It is **not** automatic and it is **not** bidirectional:

- L3 → L2: "This reality's version of Alice's death should become a canonical possibility in the book." Author reviews, confirms, writes to book + glossary.
- Never L2 → L3: a canonical change to the book does not retroactively rewrite existing realities. Existing realities live in their own time; they see book updates read-through at points they have not already diverged on.

