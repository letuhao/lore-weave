<!-- CHUNK-META
source: 03_MULTIVERSE_MODEL.ARCHIVED.md
chunk: 06_M_C_resolutions.md
byte_range: 26959-45156
sha256: ede0ed95f99cd4f1606de9d7292e394249051f34e6ee07bbad92b1f3559f185b
generated_by: scripts/chunk_doc.py
-->

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

### 9.8 Canon update propagation — M4 resolution

This section resolves **M4 (Inconsistent L1/L2 updates across reality lifetimes)** — see [01 §M4](01_OPEN_PROBLEMS.md#m4-inconsistent-l1l2-updates-across-reality-lifetimes--partial). Infrastructure (xreality.* event channels + meta-worker service) is **already locked via R5-L2**; this section adds the **author-safety UX layer**. Decisions M4-D1..D6 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

#### 9.8.1 Preview before L1/L2 edit (M4-D1)

Before author commits any L1/L2 edit in glossary / book editor, a modal shows:

- `N realities will see this change` (read-through per cascade §6)
- `M realities have overridden this attribute locally` (won't see — their L3 wins per cascade §3)
- Breakdown by reality status: active / frozen / archived
- Per-reality drill-down on demand: reality name, override event_id, override timestamp, current L3 value

#### 9.8.2 Default = passive read-through (M4-D2)

By default, L1/L2 edits don't force anything. Cascade rule (§3 + §6) handles it automatically:

- Realities that haven't overridden: see new L1/L2 on next read
- Realities that overrode: their L3 wins (correct by multiverse design — divergence is a feature, not a bug)

Safe, non-destructive default. Author cannot accidentally corrupt active realities.

#### 9.8.3 Optional force-propagate (M4-D3)

For cases where author needs the change to apply EVERYWHERE (canon corrections, typos, continuity errors):

- Writes compensating L3 event in each overriding reality
- Requires **3 gates**: (a) explicit force-propagate opt-in at edit time, (b) reality-owner consent (for realities with active creators), (c) R13 admin action audit — logged as `admin_override` event per R13-L2
- Scope-limited — author must classify: `canon_correction` / `typo_fix` / `continuity_error`
- Affected-reality players notified: *"The author updated {attribute} globally; your reality's local version has been overridden."*
- Reality-owner veto — if any owner rejects, propagation skips that reality (stays with L3 override)

#### 9.8.4 L1 axiomatic — louder warnings (M4-D4)

L1 changes apply globally via cascade §3 (no override possible). Before committing an L1 edit:

- WARNING: `N realities have L3 events that conflict with this new L1 axiom`
- List conflicting events per reality with event IDs
- Author must acknowledge before proceeding
- After commit: runtime canon-guardrail flags / rejects conflicting future L3 writes; existing conflicting L3 events remain historical but canonically void

#### 9.8.5 xreality event channel reuse (M4-D5)

Reuse R5-L2 infrastructure — no new plumbing:

- `xreality.canon.updated` event published on author L1/L2 edit
- Payload: `{book_id, attribute_path, old_value, new_value, canon_layer, propagation_mode}` where `propagation_mode ∈ {read_through, force_propagated}`
- meta-worker consumes, updates per-reality `last_canon_sync_at` in `reality_registry`
- For `force_propagated`: meta-worker orchestrates per-reality consent request + compensating-event writes (reuses R7 event-handler patterns)

#### 9.8.6 Glossary entity change timeline (M4-D6)

Author-facing history on any glossary entity attribute:

- Timeline entries: *"Author changed {attr} from X to Y at {timestamp}"*
- Propagation status: *"Applied to N realities (read-through); M realities overridden"*
- Per-reality drill-down: override event_id, current L3 value, `last_canon_sync_at`
- Reuses M3-D6 attribution surfacing pattern for consistency

#### 9.8.7 Residual OPEN (requires DF3 / governance detail)

- Compensating L3 event schema specifics (DF3-adjacent)
- Notification copy for affected-reality players (M7 `UI_COPY_STYLEGUIDE.md` applies)
- Consent mechanism for ownerless / abandoned realities (governance policy — fallback to admin auth?)
- Runtime canon-guardrail prompt discipline for L1 enforcement (A6-adjacent)

### 9.9 Reality ancestry severance — Orphan Worlds (C1 resolution)

**Origin:** SA+DE adversarial review 2026-04-24 surfaced C1 (cascade read broken when ancestor closes). User reframed as gameplay feature rather than bug: realities whose ancestry has **faded from memory** are a multiverse fiction trope.

**Philosophical alignment:** §1 already states "Alice being alive in one reality and dead in another is normal." Orphan worlds extend this: "History can fade. Knowledge of events before the forgetting is lost, but the present endures."

Full engineering design is in [02 §12M](02_STORAGE_ARCHITECTURE.md#12m-reality-ancestry-severance--orphan-worlds-c1-resolution). Conceptual summary here:

#### 9.9.1 What severance means in the multiverse

When an ancestor reality closes per R9 lifecycle, its descendants **auto-snapshot** their current state and mark ancestry as `severed`. Cascade read stops at the severance point; events from before are no longer reachable except as **lore fragments** in `ancestry_fragment_trail`.

#### 9.9.2 The severance event

Narrative event `reality.ancestry_severed` fires in-world with scope='reality' — broadcast to all active sessions in the severing reality. Narrator copy (localized, configurable):

- **Short**: "The Old Age has passed beyond memory."
- **Poetic** (default): "A profound quiet settles over the world. Ancient memories, once whispered among the oldest, fade into myth. What came before... is no longer known."

Players experience severance as an **in-world event**, not a system notification.

#### 9.9.3 Gameplay implications

- **NPCs react**: "something feels different... like a dream I can't recall"
- **Historian NPCs lose references**: they can no longer speak of specific pre-severance events
- **Artifacts become mysterious**: items/regions that trace to ancestor events now have unknown origin
- **New scholarly themes**: "why did the Old Age fade? What truly happened?"
- **Reality identity persists**: same `reality_id`, same players, same current state — only event history is gone
- **Ancestry fragment trail**: reality's lore page lists severed ancestors by `narrative_name` with dates

#### 9.9.4 Reversibility

- Pre-freeze (during ancestor R9 30-day cooling): ancestor cancel prevents severance
- Post-severance: **one-way**. Narrative event already broadcast; reversing creates continuity mess.

#### 9.9.5 Relationship to MV9 auto-rebase

MV9 auto-rebase (triggered at fork depth > 5) and §9.9 severance (triggered at ancestor close) produce technically similar states. Key differences:
- MV9: silent ops mechanism, new `reality_id` for rebased reality
- §9.9: narrative product mechanism, preserves `reality_id`, adds in-world event

Both coexist. MV9 writes `severance_reason='auto_rebase'` into fragment trail when it fires.

#### 9.9.6 Future mystery layer — DF14

Before severance fires, author/system can optionally **seed breadcrumbs** — mysterious artifacts, prophecies, lore fragments, ruins — in descendant realities. After severance, these become player-discoverable mysteries pointing at the lost past. Players can reconstruct (in-game lore) what might have been.

This is a **separate deferred big feature: DF14 — Vanish Reality Mystery System**. §9.9 (severance) is the substrate; DF14 (mysteries) is the narrative superstructure. §9.9 ships without DF14; DF14 builds on §9.9 later.

