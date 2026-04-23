# 03 — Multiverse Model

> **Status:** Exploratory — conceptual foundation for the world-persistence layer. Companion to [02_STORAGE_ARCHITECTURE.md](02_STORAGE_ARCHITECTURE.md) (engineering) and [01_OPEN_PROBLEMS.md](01_OPEN_PROBLEMS.md) (risks).
> **Created:** 2026-04-23
> **Supersedes:** The "root reality" framing in early drafts of 02. Each reality is a peer; none is privileged.

---

## 1. Philosophy

In parallel-universe / multiverse theory (and in SCP-style fiction), there is no privileged "true" reality. Universes share only an **origin point** (khởi nguyên); from there each evolves independently, with its own logic, its own history, its own outcomes.

LoreWeave adopts this literally:

- **The Book is not a reality.** The book is a body of canonical source material — characters, locations, lore, axiomatic facts. It is the origin, not a universe.
- **Every reality is a universe.** Each one is a complete, independent timeline. No reality is "more canonical" than another just because it was created first or hews closer to the book.
- **Logic can diverge.** Alice being alive in one reality and dead in another is normal. Magic working in one and not in another is normal. The book defines what is *possible*; reality defines what *happened*.

```
                     📖 BOOK
              (canon source material;
               characters, world concepts, axioms)
                        │
                        │ seeds each reality's initial state
                        │
    ┌─────────┬─────────┼─────────┬──────────┬──────────┐
    │         │         │         │          │          │
   R_α       R_β       R_γ       R_δ        R_ε        R_ζ
  alive     dead-at-  queen-at  assassin-   pirate-    librarian-
  @T=200    T=50      T=500     T=120       T=300      @T=∞
  (peer)    (peer)    (peer)    (peer)      (peer)     (peer)
```

None of R_α…R_ζ is "main." They are sibling universes that happen to share an origin.

## 2. What a reality is

A **reality** is a complete, self-contained simulation with:

- Its own timeline of events (event log scoped to `reality_id`)
- Its own NPCs (instances of glossary entities — same canonical persona, divergent history)
- Its own player characters (PCs do not cross realities by default; see §9)
- Its own regions, items, world state
- Its own local canon (facts established within it, immutable within it)
- Its own divergence record (when/why it forked, if applicable)

A reality is always born from somewhere:
- **From the book**: seeded directly from book's initial state. A fresh universe on the same origin.
- **From another reality** (snapshot fork): inherits the ancestor's event chain up to the fork point, then diverges.

Both are valid ways to start a reality. Neither produces a "root."

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

Author marks each attribute / fact at ingestion:

```sql
-- In glossary-service or wherever canonical facts are authored
ALTER TABLE entity_attributes ADD COLUMN canon_lock_level INT NOT NULL DEFAULT 2;
-- 1 = L1 axiomatic (never drifts)
-- 2 = L2 seeded canon (default, drifts allowed)
```

Levels 3 and 4 are never authored; they emerge from play.

### Canonization — promoting emergent narrative

An exciting reality can have events worth preserving. **Canonization** is the explicit flow to promote L3 events → L2 seeded canon (and rarely, L2 → L1 axiomatic). This is an author-gated action with review. It is **not** automatic and it is **not** bidirectional:

- L3 → L2: "This reality's version of Alice's death should become a canonical possibility in the book." Author reviews, confirms, writes to book + glossary.
- Never L2 → L3: a canonical change to the book does not retroactively rewrite existing realities. Existing realities live in their own time; they see book updates read-through at points they have not already diverged on.

## 4. Reality lifecycle

```
              ┌─────────────┐
              │  CREATED    │  metadata only, no events yet
              └──────┬──────┘
                     │ seed initial state
                     ▼
              ┌─────────────┐
              │  ACTIVE     │  players join, events happen
              └──────┬──────┘
                     │
           ┌─────────┼─────────┐
           ▼         ▼         ▼
      ┌──────┐  ┌──────┐  ┌──────────┐
      │FROZEN│  │FORKED│  │  CLOSED  │
      │(maint│  │(child│  │ (archived│
      │ ro)  │  │exists│  │   , DB   │
      │      │  │paren)│  │  dropped)│
      └──┬───┘  └──────┘  └──────────┘
         │        │
         └───►back to ACTIVE (thaw)
```

- **Created** — metadata row exists, seed process pending
- **Active** — live, accepting writes
- **Frozen** — no new writes, reads OK (maintenance, projection rebuild, admin review)
- **Forked** — normal state; existence of a child fork doesn't change parent's status (parent keeps running)
- **Closed** — events + snapshots archived to MinIO, DB dropped, registry row retained for audit

## 5. Seeding modes

When creating a reality, the creator specifies **where it starts**:

### 5.1 From book — fresh universe

```sql
INSERT INTO reality_registry (
  reality_id, book_id, seeded_from, parent_reality_id, fork_point_event_id, ...
) VALUES (
  'uuid', 'book-uuid', 'book', NULL, NULL, ...
);
```

- Starts from book's initial state (L1 + L2 canon)
- No L3 history yet — a blank page
- Entry point for players who want "start from the beginning"

### 5.2 From another reality — snapshot fork

```sql
INSERT INTO reality_registry (
  reality_id, book_id, seeded_from, parent_reality_id, fork_point_event_id, ...
) VALUES (
  'uuid-child', 'book-uuid', 'reality', 'uuid-parent', 12345, ...
);
```

- Inherits parent's event chain up to `fork_point_event_id` (event_id 12345)
- Cascades through ancestors recursively
- After fork point, parent and child are independent
- Entry point for "what-if" branches, capacity overflow splits, private sessions

### 5.3 Seeding is permanent

Once created, a reality's seeding mode + fork point are immutable. They define "what history do I inherit." Changing them later would invalidate every projection. If a different seed is wanted, create a different reality.

## 6. Snapshot fork semantics (locked decision)

Fork is always snapshot. Repeated from [02 §4](02_STORAGE_ARCHITECTURE.md) for self-containment:

- Child reality inherits events from parent's chain **up to and including `fork_point_event_id`**
- Events in parent after fork point are **not visible** to child
- Events in child are **not visible** to parent
- No merging between peer realities
- Replay of child is deterministic: same events chain → same state, always

For the full tradeoff analysis vs live fork, see the conversation log; live fork was rejected.

### One exception: read-through to book

The book layer (L1 + L2 canon) is not a reality and not subject to snapshot fork. Book updates are read-through to all realities. This is NOT live fork between realities — it is cascading read to the immutable canon layer.

- If the author edits an L1 axiom after a reality was created, that reality sees the new axiom on next read.
- If the author edits an L2 seeded fact, realities that have not written a conflicting L3 event see the new L2 value; realities that have overridden see their own L3.

This follows from the cascade read rule in §3: L3 > L2 > L1. Updates to L1 or L2 propagate only where L3 has not already overridden.

## 7. Cascading read

Reading the state of an aggregate (PC, NPC, region, KV) in reality R:

```python
def load_aggregate_state(aggregate_id, reality_id):
    # 1. Walk ancestry backward, collecting (reality_id, effective_cutoff)
    chain = []
    r = reality_id
    cutoff = None  # no cutoff for self — see all own events
    while r is not None:
        chain.append((r, cutoff))
        parent = lookup_parent(r)
        if parent is None:
            break
        cutoff = lookup_fork_point(r)  # see parent events only up to here
        r = parent

    # 2. Load events from each link with its cutoff
    events = []
    for (r_id, cut) in chain:
        if cut is None:
            events += select_events(reality_id=r_id, aggregate_id=aggregate_id)
        else:
            events += select_events(reality_id=r_id, aggregate_id=aggregate_id,
                                     event_id__lte=cut)

    # 3. Order by (chain_depth_descending, aggregate_version) and fold
    events.sort(key=lambda e: (e.chain_depth, e.aggregate_version))

    # 4. If L1/L2 values exist, use them as base; else default empty
    base = load_canon_defaults(aggregate_id)
    return fold(base, events)
```

Optimization: projections collapse this cascade into per-reality flat rows (see [02 §5](02_STORAGE_ARCHITECTURE.md)). The cascade above is the semantic model; the physical read hits a projection row.

## 8. Schema additions vs 02

[02_STORAGE_ARCHITECTURE.md](02_STORAGE_ARCHITECTURE.md) described the engineering baseline. Multiverse model requires these schema adjustments:

### 8.1 Events: add `reality_id` + reserve travel origin fields

```sql
ALTER TABLE events
  ADD COLUMN reality_id UUID NOT NULL;

-- PK changes from (aggregate_type, aggregate_id, aggregate_version)
--                to (reality_id, aggregate_type, aggregate_id, aggregate_version)
-- Monotonic version is per (reality, aggregate), not global.

CREATE INDEX events_reality_idx ON events (reality_id, created_at);
CREATE INDEX events_reality_aggregate_idx
  ON events (reality_id, aggregate_type, aggregate_id, aggregate_version);
```

**Event metadata reserves P4 travel-origin fields** (MV5 primitive). The `metadata` JSONB in [02 §4.3](02_STORAGE_ARCHITECTURE.md) is extended with optional keys, ignored in V1 but reserved for future world-travel:

```json
{
  "actor": { "type": "user", "id": "..." },
  "causation_id": "...",
  "correlation_id": "...",
  "source": "world-service",
  "occurred_at": "...",
  "instance_clock_tick": 12345,

  // Reserved for future world-travel feature — nullable, unused in V1
  "travel_origin_reality_id": null,
  "travel_origin_event_id": null
}
```

Consumers must tolerate absent keys. Reserving the key names now prevents every consumer from needing a schema-version check when travel lands.

### 8.2 Projections: add `reality_id`

Every projection table gains `reality_id` as part of its primary key:

```sql
ALTER TABLE pc_projection DROP CONSTRAINT pc_projection_pkey;
ALTER TABLE pc_projection ADD COLUMN reality_id UUID NOT NULL;
ALTER TABLE pc_projection ADD PRIMARY KEY (pc_id, reality_id);

-- Same for npc_projection, region_projection, world_kv_projection, etc.
```

### 8.3 Reality registry

```sql
CREATE TABLE reality_registry (
  reality_id              UUID PRIMARY KEY,
  book_id                 UUID NOT NULL,
  name                    TEXT NOT NULL,
  locale                  TEXT NOT NULL,           -- P1: e.g. 'en', 'vi', 'zh' — must exist from V1 for future world-travel
  seeded_from             TEXT NOT NULL,           -- 'book' | 'reality' | 'rebase_snapshot'
  parent_reality_id       UUID REFERENCES reality_registry,
  fork_point_event_id     BIGINT,                  -- NULL if seeded_from='book' or 'rebase_snapshot'
  rebase_source_reality_id UUID,                   -- audit trail when seeded_from='rebase_snapshot'
  fork_type               TEXT,                    -- 'auto_capacity' | 'user_initiated' | 'author_genesis' | 'auto_rebase'
  status                  TEXT NOT NULL,           -- 'created' | 'active' | 'frozen' | 'archived' | 'closed'
  divergence_type         TEXT,                    -- 'capacity_split' | 'narrative_branch' | 'private_session' | 'fresh_seed'
  player_cap              INT NOT NULL DEFAULT 100,
  current_player_count    INT NOT NULL DEFAULT 0,
  canonicality_hint       TEXT,                    -- 'canon_attempt' | 'divergent' | 'pure_what_if' — UI hint only
  db_host                 TEXT NOT NULL,
  db_name                 TEXT NOT NULL,
  schema_version          TEXT NOT NULL,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_heartbeat_at       TIMESTAMPTZ,
  last_activity_at        TIMESTAMPTZ,              -- drives freeze/archive lifecycle
  frozen_at               TIMESTAMPTZ,              -- when status transitioned to 'frozen'

  CHECK (
    (seeded_from = 'book' AND parent_reality_id IS NULL AND fork_point_event_id IS NULL) OR
    (seeded_from = 'reality' AND parent_reality_id IS NOT NULL AND fork_point_event_id IS NOT NULL) OR
    (seeded_from = 'rebase_snapshot' AND parent_reality_id IS NULL AND rebase_source_reality_id IS NOT NULL)
  )
);

CREATE INDEX ON reality_registry (book_id, status);
CREATE INDEX ON reality_registry (parent_reality_id);
CREATE INDEX ON reality_registry (status, last_activity_at);  -- freeze/archive scanner
```

Notes:
- No `depth` column — depth is meaningless in peer model.
- `locale` is required at creation; cannot be NULL. Set to book's default locale or user's choice.
- `rebase_snapshot` seeding is a third mode, used by auto-rebase at depth limit (§12.3).

### 8.4 Canon lock level on glossary/knowledge

```sql
-- In glossary-service (or wherever canonical facts are stored)
ALTER TABLE entity_attributes ADD COLUMN canon_lock_level SMALLINT NOT NULL DEFAULT 2;
-- 1 = L1 axiomatic (never drifts in any reality; enforced globally)
-- 2 = L2 seeded canon (default, reality can override via L3 events)
```

## 9. Product / UX implications

### 9.1 Reality discovery

Users pick which reality to play in. This section resolves **M1 (Reality discovery problem)** — see [01 §M1](01_OPEN_PROBLEMS.md#m1-reality-discovery-problem--partial). Decisions M1-D1..D7 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

#### Structure overview

Flat list. No "main server." No nested tree. User-facing term is **"timeline"** or **"server"**, not "reality" (see [§9.6 Progressive disclosure](#96-progressive-disclosure--m7-resolution), M7-D1).

Card content per reality:
- Name + description
- Origin ("from book" vs "forked from R_α at event 12345")
- Canonicality hint (`canon_attempt`, `divergent`, `pure_what_if`) — MV3: UI hint only, no gameplay effect
- Population (current / cap)
- Language flag
- Friend avatars (if any friends present and their PC's `presence_visibility` permits)
- Recent activity ("last active Xh ago")
- 1-line notable-event preview (top L3 headline)

#### 9.1.1 Entry flow — smart funnel (M1-D1)

Never dump the raw list on first click.

```
User clicks Play on Book X
  ├─ Has PC in this book?
  │    ├─ YES → "Continue as Kael in R_α" + "Browse other timelines"
  │    └─ NO  → Smart match:
  │              1. Any friend in a reality of Book X → surface top
  │              2. Else: highest-ranked canon_attempt reality
  │              3. Else (zero realities exist): "Be the first" → author-genesis fresh seed
  │
  └─ Default landing = 1 pre-selected reality, 1-click join; "Browse all" CTA always visible.
```

#### 9.1.2 Composite ranking (M1-D2)

Default sort = composite score. Weights configurable under `multiverse.discovery.weight.*`; V1 defaults:

| Signal | Weight | Source |
|---|---|---|
| Friend presence (≥1 friend in reality) | 100 | auth-service friend graph |
| Population density `current / cap` | 40 | `reality_registry.current_player_count / player_cap` |
| Language match `reality.locale == user.locale` | 30 | `reality_registry.locale` |
| `canon_attempt` hint | 20 | `reality_registry.canonicality_hint` |
| `divergent` hint | 10 | " |
| `pure_what_if` hint | 5 | " |
| Recent activity within 7 days | 15 | `reality_registry.last_activity_at` |
| Near-cap penalty (density > 0.85) | -20 | density threshold |

Weights are V1 starting values only — tune from Layer 9.1.7 metrics once real data lands.

#### 9.1.3 Friend-follow layer (M1-D3)

- Reuse **auth-service** friend graph (existing follow system)
- PC carries new field: `presence_visibility TEXT NOT NULL DEFAULT 'friends'` — values `friends | mutuals | nobody`
- Browse card renders friend avatars when visibility permits
- CTA: "Join R_β with Alice & Bob"

#### 9.1.4 Canonicality hint governance (M1-D4)

- Creator self-declares `canonicality_hint` at reality creation (dropdown)
- V1: self-declared, no audit, no enforcement
- V2+: source-book author can override hint on derived realities (platform-mode feature)
- Reaffirms MV3: UI hint only, zero gameplay effect

#### 9.1.5 Browse UI (M1-D5)

- Flat paginated list, default 20/page
- Filters: `language` · `canonicality` · `has_friends` · `population_range` · `recent_activity`
- Sort override: newest / oldest / population / recency
- Hibernated / frozen realities hidden by default; "Show archived" toggle reveals them

#### 9.1.6 Create-new gating (M1-D6)

V1 anti-fork-spam discipline to prevent lonely realities:

- "Create new timeline" CTA exists but hidden behind "Advanced" tab (not peer to "Browse")
- Confirmation modal before user-fork: "3 timelines in Book X have <50% capacity — want to join one instead?"
- No hard block — user remains world creator per MV4-b (no quota, no gate)
- Auto-fork (capacity overflow) remains transparent; does not surface in this UX

#### 9.1.7 Metrics feedback loop (M1-D7)

Log for weight tuning:

| Metric | Purpose |
|---|---|
| `default_landing_accept_rate` | Did user accept default or click Browse? |
| `friend_match_rate` | % of landings in reality with ≥1 friend |
| `lonely_reality_ratio` | % realities with <3 players for >7 days |
| `reality_creation_rate_per_user` | Detect fork-spam pattern |
| `browse_filter_usage` | Which filters used → cleanup UX |

V1 threshold: if `lonely_reality_ratio > 30%` over 1 month → tighten density weight or Layer 9.1.6 gating.

#### 9.1.8 Residual OPEN (requires V1 data)

Framework locked; these sub-items need prototype measurement before claiming SOLVED:

- Actual weight values (all weights in 9.1.2 are starting guesses)
- Notable-event preview format — raw L3 headline vs AI 1-line summary (measure engagement)
- First-week cold-start interaction with [01 C3](01_OPEN_PROBLEMS.md#c3-cold-start-empty-world-problem--open)
- Preview-content caching freshness policy

### 9.2 Fork as gameplay mechanic

Players can fork a reality when:
- Capacity overflow (automatic, transparent)
- Narrative what-if (explicit, user-initiated, may cost credits in platform mode)
- Private session (DM + party forks for their own campaign)

Forking is a first-class product feature, not just plumbing.

### 9.3 No default canonicality enforcement

A reality marked `canon_attempt` is not automatically "better." It is a hint for players who prefer canon-faithful play. No gameplay enforcement. No reward for staying canonical. Authors can create opinionated realities with strict L1 lock sets if desired (platform-mode feature).

### 9.4 Cross-reality travel — deferred

Default: players cannot travel between realities. A PC belongs to one reality. To play in another reality, create a new PC there.

Post-V3: "dimensional rift" mechanic may allow rare cross-reality travel under narrative scaffolding. Out of scope for this doc.

### 9.5 Multi-lingual canon realities

A reality is a natural unit for multilingual variants. Same book, different realities, each in a different language. Seeded from book → translation pipeline produces reality's initial state in target language. Players choose reality partially by language preference.

### 9.6 Progressive disclosure — M7 resolution

This section resolves **M7 (Concept complexity for users)** — see [01 §M7](01_OPEN_PROBLEMS.md#m7-concept-complexity-for-users--partial). The multiverse model is sophisticated; casual users don't need to learn it. Decisions M7-D1..D5 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

#### 9.6.1 User-facing terminology map (M7-D1)

Internal terms (design docs, admin tools, code) vs user-facing terms (default UI):

| Internal | User-facing (default UI) | Power-user label (optional) |
|---|---|---|
| reality | **timeline** (default) / **server** (gaming context) | reality |
| book | **world** (immersive) / **book** (literary) | book |
| fork | "explore another version" / "branch" | snapshot fork |
| canonicality_hint | "follows the book" / "alternate take" / "what-if" | canon_attempt / divergent / pure_what_if |
| L1 axiomatic | "world law" (unchangeable) | L1 axiomatic canon |
| L2 seeded | "starting facts" | L2 seeded canon |
| L3 reality-local | "story event" / "what happened" | L3 reality-local canon |
| L4 flexible | *(not user-visible)* | L4 runtime state |
| NPC | **character** | NPC |
| PC | **your character** | PC |
| event sourcing | "the world remembers" | event sourcing |
| aggregate / projection | *(never surfaced)* | aggregate / projection |

Default UI uses user-facing terms everywhere. Power-user labels appear only in author tooling, admin ops, and developer docs. Enforced via copy style guide (M7-D4).

#### 9.6.2 Three-tier complexity model (M7-D2)

| Tier | Default UI | Advanced features visible |
|---|---|---|
| 🧍 **Reader / Casual** | Auto-routed to top-ranked timeline (M1-D1). No fork UI. No canonicality badges inline (tooltip only). Just "Step inside" CTA. | None surfaced by default. |
| 🧙 **Player** | Browse UI (PO-2) fully visible. Canonicality badges shown. Filters available. Friend avatars. Can join any timeline. | "Create new timeline" behind Advanced tab (M1-D6). Power-user labels on hover. |
| ✍️ **Author / Creator** | Full multiverse controls. canonicality_hint setter. World Rules (DF4). Canonization flow (DF3). Ancestry tree viewer. | All power-user labels visible by default (toggleable). |

**Soft upgrade triggers** (not gated — user can click "Advanced" anywhere to reveal full UI):

- Reader → Player: user clicks "Explore other timelines" **OR** after N sessions (config `tier.reader.sessions_to_prompt`, default `3`)
- Player → Author: user creates their first book **OR** explicit "I'm an author" toggle in settings

Tier is a default-complexity signal, not a permission gate.

#### 9.6.3 Onboarding tutorial (M7-D3)

Four-step first-time entry for new users:

1. **Book detail page** — shows book as "world" with **"Step inside"** CTA (never "Join reality")
2. **First "Step inside" click** — full-screen overlay:
   > *"You're about to step into Alice's world. There may be several timelines of it — like parallel versions of the same story. We'll pick the most welcoming one for you. You can explore others anytime."*
3. **After first session** — postcard summary modal:
   > *"You played in **The Traitor's Redemption** (this timeline follows the book closely). 47 other readers are here. Come back anytime, or peek at other versions of this world."*
4. **Tier-upgrade prompt** — at N sessions (M7-D2 threshold):
   > *"You've played a lot. Want to see other timelines of this world?"* → unlocks Player tier UI.

Tutorial is skippable (X top-right) and re-runnable (help menu → "Show me around again"). Locale-aware via `i18next` from novel platform; V1 ships English + Vietnamese minimum.

#### 9.6.4 Copy style guide (M7-D4)

See [`docs/02_governance/UI_COPY_STYLEGUIDE.md`](../../02_governance/UI_COPY_STYLEGUIDE.md) — new governance doc codifying the M7-D1 terminology map + phrasing patterns + PR review gate ("copy reviewed against styleguide" checkbox on user-facing UI PRs).

#### 9.6.5 Contextual helpers (M7-D5)

Inline tooltips on concepts that must surface but may confuse:

| Element | Tooltip |
|---|---|
| `canon_attempt` badge | "This timeline follows the book closely" |
| `divergent` badge | "This timeline diverges from the book" |
| `pure_what_if` badge | "What-if scenario — a hypothetical version" |
| "Create new timeline" CTA | "Start a fresh version of this world. You can begin from the book or from a specific moment in an existing timeline." |
| Friend avatar on card | "Your friend Alice is currently playing in this timeline" |
| "Hibernated" badge | "No players for 30 days. Read-only; start a new session to wake it up." |
| "Forked from R_α at event 48" | "Branched off from another timeline at a specific story moment. They share history up to that point." |

All tooltips i18n (reuse `i18next`), short (<100 chars default).

#### 9.6.6 Residual OPEN (requires V1 data)

- Tutorial copy A/B testing (which phrasing reduces bounce rate?)
- Tier-upgrade trigger thresholds (3 sessions? 5? different by intent signal?)
- Word choice: "world" vs "book" vs "story" for source material at Reader tier
- Tooltip wording refinement per locale

### 9.7 Canonization safeguards — M3 resolution

This section resolves **M3 (Canonization contamination)** — see [01 §M3](01_OPEN_PROBLEMS.md#m3-canonization-contamination--partial). Framework-level **TECHNICAL + UX safeguards** that DF3 (Canonization / Author Review Flow implementation) MUST honor. Does NOT close **E3 (IP ownership — legal review)**, which remains an independent launch gate for platform mode. Decisions M3-D1..D8 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

#### 9.7.1 Author-only trigger (M3-D1)

- Only the book author can initiate canonization — no player request queue, no voting, no "suggest for canon" button
- No public metrics on canonization rate (prevents gaming-the-meter dynamics)
- No auto-surfacing of candidates — author must actively enter the Canonization workbench (DF3)
- Opt-in sidebar per book: "show L3 events marked canonization-eligible"

#### 9.7.2 Diff view mandatory (M3-D2)

Before confirmation, DF3 MUST render 5 sections:

| Section | Content |
|---|---|
| **Current state** | Glossary / book entity attribute pre-change |
| **Proposed change** | Proposed L2 value after canonization |
| **Prose preview** | How the change reads in book context (not the raw dialogue line) |
| **Cascade impact** | Realities that will see the change vs realities already overriding (cross-links to M4 L1/L2 propagation mechanics) |
| **Source attribution** | Reality origin, contributing PCs, event chain |

No single-button canonize. **5-second delay** + typed confirmation `CANONIZE {attribute_name}` + explicit confirm modal.

#### 9.7.3 Eligibility + consent gates (M3-D3)

**Event eligibility:**

- L3 events default `canonization_eligible = false`
- World Rules (DF4) per-reality can enable defaults for event categories: `death`, `major_decision`, `world_state_change`, `relationship_milestone`
- Flavor / mood / combat / small-talk events are never eligible regardless of setting

**Player consent:**

- PC creation checkbox: "My character's actions may be considered for canonization by the book author" — default ON, can be turned off per PC
- If **any** contributing PC is opt-out → event is INELIGIBLE regardless of quality or category
- Consent is sticky per PC — cannot retroactively flip for already-played events

#### 9.7.4 L2 → L1 promotion — harder gate (M3-D4)

L2 → L1 is rarer and higher-risk than L3 → L2. Reuse R9 destructive-op pattern:

- 7-day cooling period after confirmation (cancel window)
- Typed book-name confirmation (same pattern as R9 reality closure)
- Double approval required in platform mode (author + admin reviewer)
- **No direct L3 → L1 path ever** — must pass through L2 first, then wait ≥30 days before L1 consideration
- L1 promotions carry permanent audit-log entry

#### 9.7.5 Reversibility — 90-day undo window (M3-D5)

Canonized entry metadata: `canonized_from = (reality_id, event_id, source_author_id, canonized_at)`.

- **Within 90 days:** single-click revert restores the pre-canonization value silently
- **After 90 days:** revert requires a compensating write (new L2 event with new value; original canonization preserved in history)
- All reversions audit-logged
- L1 reversions use the harder R9-style double-approval flow, independent of this window

#### 9.7.6 Attribution + IP metadata (M3-D6)

Canonized L3 event carries:

- Contributing PC IDs + user IDs
- Narrator turn count
- Source reality + source event chain
- Canonization timestamp + book author ID

Surfaces:

- Glossary entity history view: *"canonized from reality R_β, chapter 12, contributors: Kael (user_id), Lyra (user_id)"*
- Export formats (PDF / EPUB) — author-controlled: strip attribution / inline footnote / appendix credits

**Does NOT close E3.** Legal ToS language (who owns the prose of a canonized event) remains the IP resolution. E3 is an independent launch gate for platform mode.

#### 9.7.7 Distinguishability in book content (M3-D7)

Canonized content is visually distinguishable from author-original:

- Subtle label in glossary / book UI: *"Canonized from R_β, 2026-05-12"* (toggleable in reading view)
- Icon delta — e.g., quill icon for original, compass icon for canonized
- Export options (M3-D6)
- Author edit of canonized content → becomes derivative (both contributors + author attribution tracked)

#### 9.7.8 Scope fence with E3 + DF3 (M3-D8)

| Concern | Scope | Status |
|---|---|---|
| TECHNICAL + UX safeguards | **M3 (this section)** | MITIGATED via M3-D1..D7 |
| Full implementation (workbench UI, pipelines, audit schemas) | **DF3 — Canonization / Author Review Flow** | Deferred big feature |
| IP ownership / ToS / licensing | **E3** | `OPEN` — independent legal review |

**Design can lock now** (M3 framework + DF3 spec). **Canonization cannot LAUNCH in platform mode** until E3 resolved. **Self-hosted mode is exempt** — user owns their instance and data; IP transfer is not a platform concern.

#### 9.7.9 Residual OPEN (requires DF3 detail or external input)

- Exact "significant event" categorization per World Rule — DF4 + V1 prototype data
- >90-day compensating-write mechanism — DF3 implementation detail
- Export attribution UI (footnote vs appendix vs strip) — DF3 detail
- Edge cases: canonized event from deleted PC / banned user / retroactive opt-out — DF3 policy
- **E3 (IP ownership)** — independent legal review, platform-mode launch gate

## 10. What this resolves from 01_OPEN_PROBLEMS

| Problem | Status after multiverse model | Reason |
|---|---|---|
| **A2 Temporal consistency cross-player** | `PARTIAL` | Players in different realities having different NPC state is *correct* by construction. Players in the *same* reality still need per-PC memory discipline (A1), but cross-reality consistency is no longer a contradiction. |
| **C4 Author canon vs player-emergent narrative** | `PARTIAL` | Four-layer canon resolves the tension: L1/L2 is author canon; L3 is emergent; canonization is the explicit bridge. Narratives don't compete. |
| **F1 Locked beliefs vs flexible behaviors** | `PARTIAL` | L1 = locked (globally enforced). L2 = seeded default (drifts). L3/L4 = emergent. Author decides per-attribute at authoring time. |
| **R1 Event volume explosion** (from 02 risks) | `MITIGATED` | Per-reality event streams are bounded by reality's player cap + lifespan. Shared ancestor events are not duplicated — inherited by reference (fork_point cutoff). |
| **R8 Snapshot size drift** (from 02) | `PARTIAL` | Per-reality snapshots smaller than unbounded-world snapshots. NPC memory bounded by reality's player population. |

`PARTIAL` rather than `SOLVED` because the model gives a clean frame; implementation still must get memory, performance, and UX right.

## 11. Risks specific to the multiverse model

### M1. Reality discovery problem (C3 variant) — **MITIGATED**

Resolved by 7-layer design in [§9.1](#91-reality-discovery): smart-funnel entry flow, composite ranking (friend presence / density / locale / canonicality / recency / near-cap penalty), friend-follow via auth-service, creator-declared canonicality hint, flat browse UI with filters, create-new gated behind "Advanced" tab, metrics feedback loop for weight tuning. Decisions M1-D1..D7 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md). Residual sub-items (weight values, preview format, cold-start interaction with C3, preview caching) need V1 prototype data before SOLVED.

### M2. Storage cost of many inactive realities

Users fork to try a what-if, abandon after 30 minutes. DB rows accumulate. Mitigations:
- Auto-freeze realities with no player activity for N days
- Compress frozen realities (detach event partitions, compress)
- Auto-archive frozen + unflagged realities after M days
- Fork quota per user (platform-mode tier)

### M3. Canonization contamination — **MITIGATED**

Resolved by 8-layer safeguard framework in [§9.7](#97-canonization-safeguards--m3-resolution): author-only trigger (no player request queue, no voting, no public metrics), mandatory diff view with cascade impact analysis, event eligibility + per-PC consent gates, harder L2 → L1 promotion gate (R9-style with 7-day cooldown + typed confirm + double approval), 90-day undo window with compensating-write for later reverts, attribution + IP metadata schema, distinguishability in book content (label + icon + export options), explicit scope fence with DF3 (implementation) and E3 (legal launch-gate). Decisions M3-D1..D8 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md). Residual sub-items are DF3 implementation details + E3 legal review (independent launch gate for platform mode; self-hosted exempt).

### M4. Inconsistent L1/L2 updates across reality lifetimes

Author updates L2 attribute after many realities already exist. Some realities' L3 events conflict with new L2. By cascade rule, their L3 wins — but this could confuse authors who expect "my change applies everywhere." Mitigations:
- UI shows "realities where this L2 change will not apply (overridden locally): N"
- Option to force-propagate: would write compensating L3 events in overriding realities (destructive, rare, requires reality owner consent)

### M5. Fork explosion (depth)

Snapshot fork allows forks of forks of forks. 10-level-deep chain has cascading read across 10 reality_ids. Mitigations:
- Fork depth limit (e.g., 5 levels)
- Projection tables collapse cascade — depth invisible at read time (only at rebuild)
- Monitor deep chains and offer "rebase": rewrite a deep reality as a single top-level reality seeded from a snapshot (breaks ancestor chain for that reality)

### M6. Cross-reality queries (analytics)

"How many realities is Alice alive in?" requires scanning all realities of a book. Mitigations:
- Analytics ETL pipeline (ClickHouse) denormalizes across realities for aggregate queries
- Runtime answer via aggregation over reality_registry + projection rows (bounded by book, manageable)

### M7. Concept complexity for users — **MITIGATED**

Resolved by 5-layer progressive disclosure in [§9.6](#96-progressive-disclosure--m7-resolution): user-facing terminology map (reality → timeline, NPC → character, L1 → "world law", etc.), 3-tier user model (Reader / Player / Author) with soft upgrade triggers, 4-step onboarding tutorial, copy style guide governance doc, and contextual tooltips on must-appear concepts. Decisions M7-D1..D5 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md). Residual sub-items (tutorial A/B copy, tier-upgrade thresholds, tooltip wording per locale) need V1 prototype data before SOLVED.

## 12. Configuration & decisions status

### 12.1 Tunable configuration values

All thresholds are **configuration-driven, not hardcoded**. Platform-wide defaults ship in service config; per-book overrides may be supported later (platform-mode feature). Suggested config namespace: `multiverse.*`

| Config key | Locked value | Scope |
|---|---|---|
| `multiverse.reality.player_cap` | 100 | Per-reality max concurrent PCs |
| `multiverse.subtree_split.max_events` | 50,000,000 | Trigger DB subtree split |
| `multiverse.subtree_split.max_concurrent_players` | 500 | Trigger DB subtree split |
| `multiverse.fork.depth_limit` | 5 | Before auto-rebase triggers |
| `multiverse.fork.auto_rebase` | true | At depth limit, flatten chain into fresh-seeded reality with snapshot |
| `multiverse.freeze.inactive_days` | 30 | Days of no activity → freeze |
| `multiverse.archive.frozen_days` | 90 | Days frozen → archive to MinIO |

Env vars or config file. Changes require service restart in V1; dynamic reload in V3+.

### 12.2 Fork policy (locked)

| Fork type | Seed mode | Who triggers | Storage amplification |
|---|---|---|---|
| **Auto-fork** (capacity sharding) | **Fresh from book** | System, at `player_cap` overflow | None — fresh reality = empty projection |
| **User-fork** (narrative) | User chooses: fresh OR snapshot from any reality at any event | Any user | Snapshot = projection populated lazily as child diverges |
| **Author-first-reality** | Fresh from book | Author, first time book opens for play | None |

**Why auto-fork = fresh (not snapshot from parent):** snapshot-fork does not copy events physically, but it does force child-reality projection tables to populate from ancestor chain on first read. For capacity-driven sharding where narrative continuity between parent and child is not needed, fresh seed avoids this amplification entirely. Each auto-forked sibling is a "new WoW server" — clean start, independent evolution.

**Why user-fork allows snapshot:** the whole point of a user-initiated fork is "branch from THIS reality at THIS moment to explore an alternative." Inheritance is the feature, not a cost.

**Load balancing:** players are NOT moved between auto-forked siblings. Once joined, a player stays in their reality until they explicitly leave (via future world-travel feature). Parent reality does not drain.

**User fork policy (V1):** no quota, no gate, user is world creator. Quota / cost / review are a future feature. Default: anyone can fork anything.

### 12.3 Fork depth — auto-rebase

When a new fork would exceed depth limit N (default 5):

1. System computes a **flattened snapshot** of the ancestor chain at the requested fork point
2. New reality is created as **fresh-seeded with that snapshot as its initial state**
3. New reality's `parent_reality_id = NULL`, `seeded_from = 'rebase_snapshot'`, `rebase_source_reality_id = X` (audit trail)
4. New reality's ancestry is collapsed — no further cascading read needed

User does not lose state; they only lose "lineage visibility." The new reality looks like a fresh one that happens to have a non-empty initial state.

This makes depth limit non-blocking: user can always fork, but at depth N+1 the system transparently rebases.

### 12.4 Decisions status

| Decision | Answer | Status |
|---|---|---|
| Fork semantics | Snapshot fork | **LOCKED** |
| Model name | Multiverse | **LOCKED** |
| L1 axiomatic definition | Manual + category-based | **LOCKED** |
| Canonization allowed | Yes, author-gated explicit action | **LOCKED** |
| Canonicality badge in UI | Yes, discovery hint only | **LOCKED** |
| Player cap per reality | 100 (configurable) | **LOCKED** |
| DB subtree split threshold | 50M events OR 500 players (configurable) | **LOCKED** |
| Fork policy (auto + user) | Both; auto=fresh, user=choice; no drain, no quota | **LOCKED** |
| Seed mode | Resolved by MV4 (auto=fresh, user=choice, first-of-book=fresh) | **LOCKED** |
| Auto-freeze inactive reality | 30 days (configurable) | **LOCKED** |
| Auto-archive frozen reality | 90 days (configurable) | **LOCKED** |
| Fork depth strategy | Auto-rebase at N=5 (configurable) | **LOCKED** |
| Cross-reality travel | Deferred to future world-travel feature | **LOCKED (as deferred)** |

**MV5 primitives locked now** — see [OPEN_DECISIONS.md §"MV5 primitives"](OPEN_DECISIONS.md). Schema must accommodate future travel:
- P1: Reality has `locale` field
- P4: Event metadata reserves `travel_origin_reality_id` + `travel_origin_event_id` (nullable, unused in V1)
- P5: Inventory items have `origin_reality_id` (nullable)

Incorporated into §8 schema below.

See [OPEN_DECISIONS.md](OPEN_DECISIONS.md) for complete decision history.

## 13. References

- [00_VISION.md](00_VISION.md)
- [01_OPEN_PROBLEMS.md](01_OPEN_PROBLEMS.md) — A2, C4, F1 moved to PARTIAL; M1–M7 added
- [02_STORAGE_ARCHITECTURE.md](02_STORAGE_ARCHITECTURE.md) — engineering baseline, receives schema adjustments in §8
- [OPEN_DECISIONS.md](OPEN_DECISIONS.md) — all pending decisions including defaults above
- SCP Foundation canon structure (hubs, alternate canons, reality-bender SCPs) — conceptual inspiration
- Copy-on-write branching patterns: Git, Dolt (OLTP branchable DB), Prolly trees, Datomic as-of queries
