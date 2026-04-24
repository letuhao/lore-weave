<!-- CHUNK-META
source: 03_MULTIVERSE_MODEL.ARCHIVED.md
chunk: 05_product_ux_basics.md
byte_range: 20776-26959
sha256: 6484f0b5cd2704935d9908d2018ddf0d5a09d214d7b649ae4568b27b92f44591
generated_by: scripts/chunk_doc.py
-->

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

