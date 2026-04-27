# DF05_001 — Session / Group Chat Foundation

> **Conversational name:** "Session" (DF5 / SES). The local conversation aggregate — when a PC explicitly engages with N actors at a cell, those actors form a sparse multi-session-per-cell group. Memory is distilled per-actor POV on close. Closed sessions are immutable; subjective truth lives in `actor_session_memory` per participant.
>
> **Category:** DF — Big Deferred Features (DF05; V1-blocking biggest unknown — resolved 2026-04-27)
> **Status:** **DRAFT 2026-04-27** — Q1-Q12 ALL LOCKED via 4-batch deep-dive 2026-04-27 (zero revisions). Section 16 SDK Architecture LOCKED. 11 invariants DF5-A1..A11 codified. Companion: [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md).
> **i18n compliance:** Conforms to RES_001 §2 cross-cutting pattern — all stable IDs English `snake_case` / `PascalCase`; user-facing strings `I18nBundle`.
> **Catalog refs:** [`catalog/cat_18_DF5_session_group_chat.md`](../../../catalog/cat_18_DF5_session_group_chat.md) — owns `DF5-*` stable-ID namespace.
> **Builds on:** [PL_001 Continuum](../../04_play_loop/PL_001_continuum.md) §3.6 entity_binding.location.InCell · [PL_005 Interaction](../../04_play_loop/PL_005_interaction.md) §9 InteractionKind taxonomy · [ACT_001 Actor Foundation](../../00_actor/ACT_001_actor_foundation.md) §3.4 actor_session_memory R8 bounded LRU · [NPC_001 Cast](../../05_npc_systems/NPC_001_cast.md) tier-aware persona assembly · [NPC_002 Chorus](../../05_npc_systems/NPC_002_chorus.md) multi-NPC turn ordering · [AIT_001 AI Tier](../../16_ai_tier/AIT_001_ai_tier_foundation.md) §7 capability matrix tier eligibility · [TDIL_001 Time Dilation](../../17_time_dilation/TDIL_001_time_dilation_foundation.md) §7.1 per-channel turn streams · [REP_001 Reputation](../../00_reputation/REP_001_reputation_foundation.md) 8-tier consent gating · [PCS_001 PC Substrate](../../06_pc_systems/PCS_001_pc_substrate.md) body_memory persona prompt input
> **Defers to:** future V2 multi-PC join · V2 whisper · V2 PvP consent flow (depends on DF4 World Rules) · V2+ NPC-NPC autonomous (DF1 daily life) · V3 closed-session resume · V3 cross-cell session cluster · V3 public broadcast.

---

## §1 — Purpose & V1 minimum scope

### Why this feature exists

User direction 2026-04-27 (verbatim Vietnamese):

> "không ổn, chúng ta không thể thiết kế kiểu này / có cả tỷ NPC, dồng hết vào 1 session là điều bất khả thi / hay vào đó nên thiết kế session là đơn vị cục bộ đi theo 1 cell cố định / 1 cell có nhiều sessions / [...] dữ liệu được cho là quan trọng trong session chỉ còn lưu trong memory của người tham gia"

Initial main-session proposal (single-session-per-cell, all actors auto-joined) was rejected with two arguments:
1. **AIT_001 billion-NPC scaling** — coalescing all cell actors into one session burns LLM context budget for actors who never engage with PC
2. **Real-life conversation parallel** — entering a tavern of 50 people, you talk to 2-3 at your table; the other 47 are background

DF5 owns the **multi-session-per-cell sparse architecture** that solves both concerns: sessions are explicit social acts (PC engages targets); 95%+ cell actors stay ambient (zero LLM cost); on close, memory distills to subjective per-actor records.

### V1 minimum scope (per Q1-Q12 LOCKED)

- **Aggregates V1:** `session` (T2/Reality) + `session_participation` (T2/Reality, sparse per-(session, actor)). Reuses ACT_001 `actor_session_memory` (no reopen).
- **Lifecycle V1:** 2-state (Active / Closed). Idle V1+30d; Frozen V2+.
- **Session creation V1:** Both CLI `/chat @actor [@actor...]` (PL_002 Grammar) AND click-to-talk UI gesture (CC-1). Solo monologue (0 NPC participants) allowed.
- **Participant cap V1:** 8 participants max (inclusive of PC anchor); reject `session.participant_cap_exceeded` for 9+. V2+ assembly = separate feature for 20+ groups.
- **Per-cell capacity V1:** ≤50 Active sessions per cell (soft cap); reject `session.cell_session_overload`.
- **NPC consent V1:** Reputation-gated (Hated + Hostile reject; Unfriendly reluctant accept with mood=Sour). Personal opinion overrides faction reputation.
- **Cross-session memory bleed V1:** YES — actor's persona prompt assembly reads top-K=10-20 facts by salience across all past sessions for that actor. NO cross-reality bleed. NO faction filter.
- **TDIL clock interaction V1:** Session orthogonal — clocks advance per-turn regardless of session presence; channel time_flow_rate authoritative.
- **POV-distill on close V1:** LLM × N participants on Closed transition; cached in EVT-T3 payload for replay-determinism. Skip if turn_count < 3 (no meaningful content).
- **Disconnect grace V1:** 30 wall-seconds (NOT fiction-time) for WebSocket disconnect ONLY; explicit `/leave` is instant.
- **Forge admin V1:** Pre-close edits OK (full memory mutation); post-close only `Forge:RegenSessionDistill` + `Forge:PurgeActorSessionMemory`; full audit per WA_003; player invisible V1.
- **SDK V1:** `contracts/api/session/v1/` versioned contract + `services/session-service/` swappable backends (LruDistillProvider V1; SalienceTranscript V1+30d; KnowledgeServiceBridge V2+).
- **Replay-determinism V1:** EVT-T3 payload caches POV-summaries; replay reads cache, never re-LLM-calls.

### V1 NOT shipping (deferred)

| Feature | Defer to | Why |
|---|---|---|
| Multi-PC join existing session | V2 (DF5-D1) | Solo RP V1; multi-PC = additional turn arbitration via SR11 |
| Whisper (1-to-1 within session) | V2 (DF5-D2) | Multi-PC dependency |
| PvP within session | V2 (DF5-D3) | Depends on DF4 World Rules consent flow |
| Idle state (auto-detect) | V1+30d (DF5-D4) | Active+Closed enough V1 |
| Wall-clock 24h timeout | V1+30d (DF5-D5) | Anchor-leave close enough V1 |
| Per-tier customized POV-distill prompt | V1+30d (DF5-D6) | Single template enough V1 |
| NPC initiates session (desire-driven) | V2 (DF5-D7) | NPC_003 Desires V1 read-only |
| Frozen state (Forge/DF4 explicit pause) | V2 (DF5-D8) | Not blocking V1 |
| NPC-NPC autonomous continuation (PC absent) | V3 (DF5-D9) | DF1 daily life dependency |
| Closed session resume | V3 (DF5-D10) | V1 invariant immutable on close |
| Cross-cell session cluster | V3 (DF5-D11) | TDIL-A5 atomic-channel V1 |
| Public broadcast (PC shouts to cell) | V3+ (DF5-D12) | One-off event suffices V1 |

---

## §2 — Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **Session** | Aggregate `session` (T2/Reality) | Long-lived container; 2-state lifecycle; sparse — only exists when actors actively engage. NOT an event; IS an aggregate. |
| **SessionId** | `pub struct SessionId(pub Uuid)` — UUID v5 from `(reality_id, channel_id, anchor_pc_id, started_fiction_time)` | Deterministic; replay-safe per EVT-A9 |
| **SessionState** | Closed enum 2 V1 — `Active \| Closed` | V1+30d adds `Idle`; V2+ adds `Frozen`. |
| **SessionParticipation** | Aggregate `session_participation` (T2/Reality, sparse per-(session, actor)) | Tracks who joined when + left when + role + presence. |
| **ParticipantRole** | Closed enum 2 V1 — `Anchor \| Joined` | Anchor = PC who created session. Joined = NPC accepted invite OR V2 PC2 joins existing. |
| **PresenceState** | Closed enum 3 V1 — `Connected \| Disconnected \| Left` | Disconnected = WebSocket lost but inside 30s grace; Left = formally departed. |
| **LeftReason** | Closed enum 7 V1 — `Explicit \| MovedCell \| DisconnectTimeout \| Inactive \| SessionClosed \| AnchorPcLeft \| Kicked` | Audit trail. DisconnectTimeout V1 (30s wall-clock grace expired); Inactive V1+30d (in-session activity auto-detect); Kicked V1 Forge. |
| **CloseReason** | Closed enum 5 V1 — `LastPcLeft \| AllParticipantsLeft \| ForgeClose \| RealityClosed \| SessionTimeoutWallClock` | Default V1: `LastPcLeft`. SessionTimeoutWallClock V1+30d. |
| **MemoryFact** | Distilled subjective fact per actor POV | `{ kind, target?, verb: I18nBundle, object?: I18nBundle, salience: f32 }`; written to actor_session_memory on close. |
| **MemoryFactKind** | Closed enum 5 V1 — `Social \| Promise \| Tone \| Threat \| Knowledge` | V2+ additive: Quest, Combat, Faction, Discovery |
| **PovDistillRequest** | LLM-prompt input on close | Full turn history × actor POV → JSON output 3-5 facts |
| **PersonaContextBlock** | SDK DTO returned by MemoryProvider | `{ actor_id, target?, recent_memories, opinion?, mood?, generated_at, provider_attribution }` |
| **MemoryQuery** | SDK DSL — structured queries | V1 4 variants; V2+ adds BySemanticSimilarity + CrossRealityByUser |
| **SessionService** | SDK trait — 7 lifecycle ops | `create_session / join_session / leave_session / close_session / record_turn / get_session / list_active_in_channel` |
| **MemoryProvider** | SDK trait — 4 read ops + capabilities | `get_persona_context / query / replay_session / capabilities()` |
| **MemoryProviderCapabilities** | Capability probe struct | Fine-grained boolean + Duration; supports graceful degradation |

---

## §2.5 — Event-model mapping (per 07_event_model)

DF05 introduces no new EVT-T* category. Maps onto existing taxonomy:

| DF5 event | EVT-T* | Sub-type | Producer |
|---|---|---|---|
| Session born — runtime PC-trigger | **EVT-T3 Derived** | `aggregate_type=session` Born | session-service (PL_002 `/chat` command handler) |
| Session born — canonical seed (V1+ author scripted) | **EVT-T4 System** | `SessionBorn { session_id, channel_id, anchor_pc_id }` | RealityBootstrapper |
| Actor joins session | **EVT-T3 Derived** | `aggregate_type=session_participation` Born | session-service |
| Actor leaves session | **EVT-T3 Derived** | `aggregate_type=session_participation` Update (LeftTransition) | session-service |
| PC takes turn (existing PL_005) | **EVT-T1 Submitted** | `PCTurn { session_id, ... }` | client → world-service |
| NPC turn (existing; Chorus selects responder) | **EVT-T1 Submitted** | `NPCTurn { session_id, ... }` | NPC_002 → world-service |
| Turn cascades (mood/opinion/status/location/etc.) | **EVT-T3 Derived** | various existing | aggregate owners |
| Session closing transition | **EVT-T3 Derived** | `aggregate_type=session` ClosingTransition | session-service (anchor leave detected) |
| Per-actor POV memory distill | **EVT-T6 Proposal** + **EVT-T3 Derived** | `actor_session_memory` Update with cached `MemoryFact[]` payload | session-service via LLM |
| Session closed | **EVT-T3 Derived** | `aggregate_type=session` ClosedTransition | session-service |
| Forge admin actions | **EVT-T8 Administrative** | `Forge:CreateSession / Forge:CloseSession / Forge:KickFromSession / Forge:EditActorSessionMemory / Forge:RegenSessionDistill / Forge:PurgeActorSessionMemory / Forge:AnonymizePcInSessions / Forge:BulkRegenSessionDistill / Forge:BulkPurgeStaleSessions` | WA_003 Forge |
| Reality close cascade | **EVT-T3 Derived** | `aggregate_type=session` ClosedTransition (CloseReason=RealityClosed) | EM-7 cascade |
| Wall-clock timeout sweep (V1+30d) | **EVT-T5 Generated** | `Scheduled:SessionTimeoutSweep` | meta-worker per channel |

**No new EVT-T* row in `_boundaries/01_feature_ownership_matrix.md`.** EVT-T4 System sub-types row gains `SessionBorn`. EVT-T3 Derived sub-types row gains `aggregate_type=session` + `aggregate_type=session_participation`. EVT-T8 Administrative sub-shapes registry gains 9 new Forge AdminAction variants.

---

## §3 — Aggregate inventory

DF05 owns 2 new aggregates V1; reuses 1 from ACT_001.

### §3.1 `session` (T2 / Reality, sparse — Active hot; Closed archival) — PRIMARY

```rust
#[derive(Aggregate)]
#[dp(type_name = "session", tier = "T2", scope = "reality")]
pub struct Session {
    pub session_id: SessionId,                    // UUID v5(reality_id, channel_id, anchor_pc_id, started_fiction_time)
    pub reality_id: RealityId,
    pub channel_id: ChannelId,                    // anchor cell — DF5-A1 same-channel constraint
    pub state: SessionState,                      // Active | Closed
    pub started_fiction_time: FictionTime,
    pub closed_fiction_time: Option<FictionTime>, // populated on close
    pub turn_count: u32,                          // bumped per EVT-T1 commit
    pub close_reason: Option<CloseReason>,        // populated on close
    pub anchor_pc_id: ActorId,                    // creator PC — DF5-A4 anchor invariant
}

pub enum SessionState {
    Active,                                       // V1
    Closed,                                       // V1 — terminal
    // Idle V1+30d / Frozen V2+
}

pub enum CloseReason {
    LastPcLeft,                  // V1 default — DF5-A4 anchor invariant trigger
    AllParticipantsLeft,         // edge case (PC + NPC both move out simultaneously)
    ForgeClose,                  // V1 admin
    RealityClosed,               // EM-7 cascade
    SessionTimeoutWallClock,     // V1+30d auto-close after 24h wall-time idle
}

pub struct SessionId(pub Uuid);
```

**Rules:**
- One row per `session_id`. Primary key conflict = reject `session.duplicate_session_id`.
- `state = Active` allowed transitions: → `Closed` (terminal).
- `state = Closed` is **IMMUTABLE** (DF5-A7); no further `session_participation` writes; only archival reads.
- `anchor_pc_id` MUST be PC kind (DF5-A4); rejected `session.anchor_must_be_pc` if non-PC.
- `channel_id` MUST be cell-tier (consistent with PF_001 §5 cell-only invariant).
- Active session count per cell MUST be ≤50 V1 (DF5-A8); reject `session.cell_session_overload`.
- Active session count per actor MUST be ≤1 (DF5-A5); reject `session.actor_busy_in_other_session`.

**Storage discipline:**
- Active sessions: hot row, indexed by `(channel_id, state=Active)` for cell-wide queries.
- Closed sessions: cold row, archival; future TTL or migrate to `closed_session_archive` aggregate V2+.
- No `summary` field on `session` — moved to per-actor `actor_session_memory` (R8 bounded LRU).

### §3.2 `session_participation` (T2 / Reality, sparse per-(session, actor)) — PER-PARTICIPANT

```rust
#[derive(Aggregate)]
#[dp(type_name = "session_participation", tier = "T2", scope = "reality")]
pub struct SessionParticipation {
    pub session_id: SessionId,
    pub actor_id: ActorId,
    pub joined_fiction_time: FictionTime,
    pub left_fiction_time: Option<FictionTime>,   // None = currently in session
    pub role: ParticipantRole,                    // Anchor | Joined
    pub turn_count_contributed: u32,
    pub last_turn_fiction_time: Option<FictionTime>,
    pub left_reason: Option<LeftReason>,
    pub presence: PresenceState,                  // V1 add per Q10-D2
    pub disconnect_at_wall_time: Option<WallTime>,// populated on Disconnected presence
}

pub enum ParticipantRole {
    Anchor,                                       // PC who created session (DF5-A4)
    Joined,                                       // accepted invite (NPC) OR V2+ PC2 joins existing
}

pub enum PresenceState {
    Connected,                                    // active turn-taking
    Disconnected,                                 // WebSocket lost; in 30s grace window (Q10)
    Left,                                         // formally departed (left_fiction_time populated)
}

pub enum LeftReason {
    Explicit,                                     // /leave or close-chat UI
    MovedCell,                                    // cascade from PL_001 §13 travel
    DisconnectTimeout,                            // V1 — WebSocket disconnect 30s grace expired (Q10-D1)
    Inactive,                                     // V1+30d auto-detect of in-session activity stall (DF5-D4)
    SessionClosed,                                // cascade
    AnchorPcLeft,                                 // forced exit when last PC leaves
    Kicked,                                       // V1 Forge OR V1+ DF4 rule
}
```

**Rules:**
- Composite key `(session_id, actor_id)`. Duplicate write = reject `session.participant_already_joined`.
- `role = Anchor` exactly once per session (the creator PC). Subsequent participants = `Joined`.
- `role = Anchor` actor MUST be PC kind (DF5-A4); enforced via cross-validator with ACT_001.
- After `state = Closed` on parent session: NO new participation writes; existing rows immutable except `left_reason` finalization.
- `left_fiction_time = None` iff `presence ∈ {Connected, Disconnected}`; `Some` iff `presence = Left`.
- `disconnect_at_wall_time` ONLY populated on Disconnected; cleared on reconnect.

### §3.3 Reuse `actor_session_memory` (ACT_001 §3.4)

ACT_001 already owns `actor_session_memory` per (actor, session). **DF5 does NOT reopen ACT_001.** Roles:

- **Pre-close (Active session):** facts accumulate during turn-taking; bounded LRU per ACT_001 R8 (max ~30 facts per (actor, session)); rolling summary on overflow.
- **Post-close (Closed session) — PRIMARY V1 access path:** POV-distill writes 3-5 facts per actor on close cascade (see §6); subsequent persona prompt assembly reads here.
- **Cold-decay:** ACT_001 R8 30/90/365 fiction-day cadence; eventual compaction to summary only.

**No DF5-owned aggregate for memory.** All memory state lives in ACT_001 `actor_session_memory` rows + EVT-T3 Derived payload cache.

---

## §4 — Lifecycle state machine V1

```
                         PC opens chat with target(s)
                         /chat @alice @bob OR click NPC
                                  │
                                  ▼
                          ┌──────────────┐
                          │  SessionBorn  │ → EVT-T3 Derived (runtime) OR
                          │               │   EVT-T4 System (canonical seed V1+)
                          └──────┬────────┘
                                 ▼
                        ┌─────────────────┐
                        │     Active      │  turn-take loop
                        │  (PCs + NPCs    │  · PL_005 Interaction grain
                        │   interact)     │  · turn → EVT-T1 Submitted
                        └────────┬────────┘  · cascades → EVT-T3 Derived
                                 │
                                 │ DF5-A4 trigger:
                                 │ last PC leaves session
                                 │ (PC /travel | /leave | disconnect>30s)
                                 ▼
                      ┌──────────────────────┐
                      │ ClosingTransition    │  EVT-T3 Derived
                      │ + per-actor POV      │  EVT-T6 Proposal × N
                      │   LLM distill        │  EVT-T3 Derived × N (memory writes)
                      │ (skip if turn_count  │  cached payload per Q12 LOCKED
                      │  < 3 per Q2-D2)      │
                      └────────┬─────────────┘
                               ▼
                       ┌──────────────────┐
                       │     Closed       │  TERMINAL V1 — immutable
                       │  (archival only) │  no participant writes
                       └────────┬─────────┘
                                │
                                │ Future read paths:
                                ▼
                  actor_session_memory[actor, session_id]
                  ↑ each participant has subjective record
                  ↑ cannot reopen session for "objective truth"
                  ↑ POV may differ between participants (intentional)
                  ↑ ACT_001 R8 bounded LRU + cold-decay 30/90/365d
```

**V1 = 2 states only** (Active, Closed). V1+30d adds Idle (auto-detected after N turns no PC activity → memory flush + close earlier). V2+ adds Frozen (Forge or DF4 explicit pause).

**Allowed transitions V1:**

| From → To | Trigger | Producer |
|---|---|---|
| (none) → Active | PC `/chat` OR canonical seed | session-service / RealityBootstrapper |
| Active → Closed | DF5-A4 anchor invariant fires (last PC leaves) | session-service detect |
| Active → Closed | Forge:CloseSession admin action | WA_003 Forge |
| Active → Closed | EM-7 reality close cascade | reality-service cascade |

**Forbidden transitions** (validated at write-time; reject `session.invalid_state_transition`):
- Closed → Active (terminal V1; resume V3+ deferred)
- Closed → Closed (idempotent reject; can only close once)

---

## §5 — PC anchor invariant + close trigger (DF5-A4)

**DF5-A4 (PC anchor invariant):** Every Active session MUST have ≥1 PC with `presence ∈ {Connected, Disconnected}` and `left_fiction_time = None`. When the last such PC transitions to `Left` state, session-service detects and triggers ClosingTransition cascade.

### Close detection algorithm

```rust
async fn check_anchor_invariant_after_leave(
    session_id: SessionId,
    actor_who_left: ActorId,
) -> Result<(), SessionError> {
    let participants = query_session_participation(session_id, presence ∈ {Connected, Disconnected}).await?;
    let pc_count = participants.iter().filter(|p| is_pc(p.actor_id)).count();
    if pc_count == 0 {
        // Last PC left — trigger close cascade
        emit_closing_transition(session_id, CloseReason::LastPcLeft).await?;
    }
    // else: NPCs may continue holding session if PC2 still in (V2+ multi-PC)
    //       V1 solo PC: this branch only fires when leaving PC was anchor PC
    Ok(())
}
```

### Close cascade ordering

```
1. detect last PC left → mark session.state = ClosingTransition (intermediate marker; not in SessionState enum but used by session-service)
2. for each remaining NPC participant:
     mark left_fiction_time = now
     left_reason = AnchorPcLeft
     emit EVT-T3 Derived (session_participation Update)
3. for each (actor_id) ∈ all_participants_who_were_in_session_at_close:
     run POV-distill cascade (§6)
     write actor_session_memory facts
     emit EVT-T6 Proposal + EVT-T3 Derived per actor
4. mark session.state = Closed
   set session.closed_fiction_time = now
   set session.close_reason = CloseReason::LastPcLeft
   emit EVT-T3 Derived (session ClosedTransition)
5. session-service flushes LLM context cache for this session_id
```

All 5 steps run in **single Postgres transaction** (atomic per DP-K1 ACID guarantee). Mid-cascade failure → all rollback; session stays Active until next attempt.

### Special case: PC explicit `/leave`

```rust
PC issues /leave command in PL_002 Grammar
  → handler: leave_session(session_id, actor_id, LeftReason::Explicit)
  → mark left_fiction_time = now; presence = Left; left_reason = Explicit
  → check_anchor_invariant_after_leave() fires
  → if last PC: trigger close cascade
```

### Special case: PC `/travel` to different cell

```rust
PC issues /travel destination=other_cell
  → PL_001 §13 travel cascade
  → for each session containing PC at current cell:
      mark left_fiction_time = now; left_reason = MovedCell
      check_anchor_invariant_after_leave()
  → PC arrives at destination cell (no auto-join other sessions; stays ambient)
```

### Special case: PC WebSocket disconnect (Q10 LOCKED)

See §13 disconnect grace.

---

## §6 — Per-actor POV memory distill on close (CRITICAL MECHANISM)

The defining mechanism of DF5: when session closes, **each participant gets their own subjective summary** of what happened. Two participants of the same conversation may remember different facts/emphasis. **This is feature, not bug** — matches real human cognition.

### §6.1 Why per-actor POV (not single objective summary)

| Property | Single objective summary | Per-actor POV (V1 CHOSEN) |
|---|---|---|
| Token cost | 1 LLM call | N LLM calls (N participants) |
| Storage cost | 1 row | N rows |
| Replay determinism | 1 cache | N caches (all in EVT-T3 payload) |
| Cognitive realism | Low (omniscient narrator) | High (each remembers differently) |
| Privacy | Same record visible to all | Each actor sees their own |
| Future references | "What did the session say?" | "What does Alice remember?" |

**Trade-off accepted:** N× cost for cognitive realism + privacy + per-actor LLM persona prompt-assembly continuity. Cost cap: typical session 4 participants × ~500 tokens = 2K tokens on close. Cheap relative to session lifetime cost.

### §6.2 POV-distill prompt template (Q5-D1..D6 LOCKED)

**Single template V1; per-tier customization V1+30d (DF5-D6).**

```
SYSTEM:
You are <actor.display_name>, a <actor.kind> in the world of <reality.name>.
Your faction: <actor.faction>. Your current mood: <actor.mood>.

You just finished a conversation. Distill the conversation into 3-5 memory facts
from YOUR subjective POV. Output JSON only.

CONVERSATION CONTEXT:
- Session anchor: <anchor_pc.display_name>
- Other participants: <participants.display_name list>
- Total turns: <turn_count>
- Started at: <fiction_time> in <cell.display_name>

CONVERSATION TURNS:
[full turn list per Q5-D1 LOCKED — actor + interaction kind + content]

SCHEMA:
{
  "facts": [
    {
      "kind": "social|promise|tone|threat|knowledge",
      "target": "<actor_id of who fact is about>" | null,
      "verb": { "vi": "...", "en": "..." },
      "object": { "vi": "...", "en": "..." } | null,
      "salience": 0.0-1.0
    }
  ]
}

INSTRUCTIONS:
- Top 3-5 facts max. Highest salience first (per Q5-D3 LOCKED).
- Salience: how memorable/impactful from YOUR perspective (Q5-D4 LOCKED).
- "kind" must be exactly one of: social, promise, tone, threat, knowledge (Q5-D2 schema).
- I18nBundle vi+en per Q5-D5 LOCKED.
- Output ONLY JSON; no markdown, no commentary.
```

**Output schema: JSON Schema validated + 3-retry feedback loop** (Q5-D2 LOCKED) mirror PoC tilemap pattern proven in SPIKE_03 §13.

**Failure handling Q5-D6 LOCKED:** if 3-retry exhausted, write placeholder fact `{ kind: tone, verb: I18nBundle("had a conversation"), salience: 0.3 }` ensures actor has minimal record (better than empty).

### §6.3 Distill cascade implementation

```rust
async fn run_session_close_cascade(session_id: SessionId, close_reason: CloseReason) {
    // Step 1: ClosingTransition event
    emit_evt_t3_derived(session_id, "session", "ClosingTransition", { close_reason }).await;

    // Step 2: gather participants who were in session at close
    let participants = query_session_participation_at_close(session_id).await?;

    // Step 3: skip distill if turn_count < 3 (Q2-D2 LOCKED — no meaningful content)
    let turn_count = read_session(session_id).await?.turn_count;
    if turn_count < 3 {
        emit_evt_t3_closed(session_id, close_reason);
        return;
    }

    // Step 4: per-actor POV distill (parallel)
    for actor in participants {
        let prompt = build_pov_distill_prompt(actor, session_id, full_turn_history);
        let facts = llm_call_with_retry(prompt, max_attempts=3).await
            .unwrap_or_else(|_| vec![PLACEHOLDER_FACT]);  // Q5-D6 fallback

        // Cache facts in EVT-T3 payload (Q12-D1 LOCKED — full JSON V1)
        emit_evt_t3_pov_distill(actor.id, session_id, facts.clone(), {
            llm_model_id, prompt_template_version: 1, provider_id,
            generated_at_fiction_time, generated_at_wall_time, attempt_count
        });

        // Append to actor_session_memory per ACT_001 R8
        write_actor_session_memory(actor.id, session_id, facts).await?;
    }

    // Step 5: ClosedTransition event
    emit_evt_t3_closed(session_id, close_reason);
}
```

### §6.4 Token cost on close

```
Typical session: 4 participants × ~500 tokens distill output = 2K tokens
+ LLM input ~800-1500 tokens × 4 = 3.2-6K tokens input
+ JSON Schema validation overhead (3-retry max) = up to 3× per actor
Worst case: 4 × 3 retries × ~1500 tokens = 18K tokens
Realistic case (1-attempt success): 4 × 2K = 8K tokens total
```

Cheap relative to session lifetime cost (typical session ~20 turns × 3K context = 60K tokens cumulative).

### §6.5 Async background distill V1+30d (DF5-D13)

V1 ships **synchronous distill** on close cascade — N LLM calls atomically. May stutter UX on close for large sessions.

V1+30d (DF5-D13) deferral: async background distill via worker-ai (per knowledge-service pattern). Close cascade marks session as Closed + queues distill jobs; persona prompt assembly degrades gracefully if distill not yet done (uses placeholder fact + retries on next read).

---

## §7 — Multi-session-per-cell architecture (THE BIG SHIFT)

```
CELL (channel) — N actors (potentially billion via AIT)
│
├── 95%+ actors AMBIENT (NOT in any session)
│   · vendors hawking, untracked crowd, idle NPCs
│   · ZERO LLM cost; ZERO context budget; ZERO storage write per turn
│   · only AIT density caps + procedural Untracked spawn matter
│
└── M concurrent SESSIONS (sparse — exist only when actors actively engage)
    │
    ├── Session A: PC₁ + NPC_alice + NPC_bob (chat at table 3)
    │              ↑ explicitly engaged via /chat or click
    │
    ├── Session B: PC₂ + NPC_carol (corner conversation)
    │              ↑ different PC, different group
    │
    └── ... up to soft cap 50 sessions per cell V1 (DF5-A8)
```

**Real-life parallel:** vào tavern 50 người ngồi, bạn chỉ "trong conversation" với 2-3 người bạn ngồi cùng bàn. 47 người còn lại là background. Mỗi nhóm ngồi bàn riêng = mỗi session riêng. Không có "tavern group chat" toàn cell.

**Key insight:** Session là **explicit social act**, không phải spatial co-location.

### Session creation grammar (Q1-D1 LOCKED — Both V1)

| Trigger | Mechanism | UX surface |
|---|---|---|
| **CLI `/chat @actor [@actor...]`** | PL_002 Grammar handler | Power-user; multi-actor select; scriptable |
| **Click NPC avatar** | CC-1 Chat GUI extension | Discovery-friendly; single-target start; can drag more |
| **Drag actor onto session window** (V2+) | UI gesture | Multi-PC join V2+ |
| **NPC initiates `/chat @PC`** (V2+ DF5-D7) | NPC_003 desire-driven | NPC walks up to PC because of desire |

### Solo monologue allowed (Q2 LOCKED)

Zero-NPC session permitted V1. Use cases:
- **Journal mode** — PC reflects, writes diary; LLM-aided introspection
- **PCS_001 body_memory recall** — PC accesses soul/body knowledge_tags (xuyên không SoulPrimary scenario)
- **Pre-action planning** — PC "thinks" before issuing complex action sequence
- **Practice/training** — PC mentally rehearses cultivation technique

Q2-D2 LOCKED: skip POV-distill if `turn_count < 3` (no meaningful content threshold). Distill always fires for real conversations.

### Cell session capacity (Q3 LOCKED + DF5-A8)

- **Per-session cap:** 8 participants V1 (inclusive of PC anchor); reject `session.participant_cap_exceeded` for 9+
- **Per-cell cap:** ≤50 Active sessions V1 (soft cap); reject `session.cell_session_overload`
- **V2+ assembly feature:** for groups of 20+ (guild meeting, sect council, banquet) — separate feature linking to ORG_001 V3+

---

## §8 — NPC consent + reputation gating (Q4 LOCKED)

NPC may refuse `/chat` invite based on REP_001 reputation tier (Q4-D1) modulated by personal opinion (Q4-D2).

### §8.1 Consent decision algorithm

```rust
async fn npc_consent_check(npc: ActorId, pc: ActorId, npc_faction: FactionId) -> ConsentOutcome {
    // Read REP_001 8-tier reputation (PC ↔ NPC's faction)
    let faction_rep = read_actor_faction_reputation(pc, npc_faction).await
        .unwrap_or(0i16);  // missing row = Neutral default

    // Read ACT_001 bilateral opinion (NPC's personal feelings about PC)
    let personal_opinion = read_actor_actor_opinion(npc, pc).await
        .unwrap_or(0i16);

    // Q4-D2 LOCKED: personal opinion overrides faction rep (gradient ±2 tiers)
    let effective_rep = faction_rep + (personal_opinion * 2);  // clamp to i16 bounds

    let tier = compute_reputation_tier(effective_rep);

    match tier {
        ReputationTier::Hated | ReputationTier::Hostile => {
            // Q4-D1 LOCKED: hard reject
            ConsentOutcome::Reject {
                rule_id: "session.npc_refused",
                refusal_message: build_refusal_message(npc, tier).await,
                reason_kind: RefusalReason::Hostile,
            }
        }
        ReputationTier::Unfriendly => {
            // Q4-D1 LOCKED: reluctant accept with mood=Sour
            ConsentOutcome::AcceptReluctant {
                mood_override: ActorMood::Sour,
            }
        }
        ReputationTier::Neutral
        | ReputationTier::Friendly
        | ReputationTier::Honored
        | ReputationTier::Revered
        | ReputationTier::Exalted => {
            ConsentOutcome::Accept
        }
    }
}
```

### §8.2 Refusal message form (Q4-D3 LOCKED)

**Hybrid: LLM-flavored refusal + engine template fallback.**

Primary path: LLM-generated refusal (~100 tokens, persona-flavored):
```
prompt: "You are <npc.display_name>. PC <pc.display_name> wants to chat with you.
        You refuse because <reason: faction_rep=Hostile + opinion=neutral>. 
        Output 1 short sentence in Vietnamese with your character's voice."
```

Fallback path (LLM budget exhausted OR cost-tier Free): hardcoded template per (mood, reputation_tier):
```rust
const REFUSAL_TEMPLATES: HashMap<(Mood, ReputationTier), Vec<I18nBundle>> = {
    (Mood::Hostile, ReputationTier::Hostile) => vec![
        I18nBundle::new("Đi đi! Ta không nói chuyện với kẻ thù!", "Begone! I don't speak with enemies!"),
        // ... 3-5 variants per cell
    ],
    // ...
};
```

### §8.3 No cooldown V1 (Q4-D4 LOCKED)

PC repeated `/chat @npc` after refusal: no per-NPC cooldown. Anti-spam relies on **PL_002 grammar layer rate-limit** (existing). PC sees same refusal each attempt; reputation increment penalty deferred V2+.

V1+ if grief becomes issue: per-NPC 5-turn cooldown (DF5-D14) OR reputation -1 per refusal (DF5-D15).

### §8.4 Tier eligibility (DF5-A6)

Per AIT_001 §7 capability matrix:
- ✅ **PC** — full session participation (always anchor or joined)
- ✅ **Major NPC** — full session participation; reputation gating (§8.1)
- ✅ **Minor NPC** — session participation; scripted-only behavior (NPC_002 dialogue templates)
- ❌ **Untracked NPC** — REJECTED `session.actor_not_eligible_untracked` per AIT-A8 target-only

Promotion path: AIT-D7 V1+30d allows LLM-propose-promotion of Untracked → Tracked Minor based on PC engagement signal.

---

## §9 — Cross-session memory bleed (Q7 LOCKED)

NPC alice in SessionB references what alice remembered from past SessionA, SessionZ, etc. **YES V1.**

### §9.1 Persona prompt assembly read pattern

```rust
async fn build_persona_context(actor: ActorId, target: Option<ActorId>) -> PersonaContextBlock {
    // Q7-D2 LOCKED: top-K=10-20 facts by salience across ALL past sessions
    let memories = query_actor_session_memory(actor, MemoryQuery::ByActorRecentBySalience {
        actor_id: actor,
        max_results: 15,
        target_filter: target,  // optional: only facts about specific target
    }).await?;

    // Q7-D1 LOCKED: NO cross-reality bleed — DP T2 Reality scope enforced naturally
    // Q7-D3 LOCKED: NO faction filter — alice's memories are flat (privacy via DF5-A10)
    // Q7-D4 LOCKED: ACT_001 R8 cold-decay 30/90/365d already applied at storage layer

    PersonaContextBlock {
        actor_id: actor,
        target_actor_id: target,
        recent_memories: memories,
        opinion: read_actor_actor_opinion(actor, target).await,
        mood: read_actor_core(actor).mood,
        relevant_facts: vec![],  // V2+ domain facts integration
        generated_at_fiction_time: now(),
        provider_attribution: ProviderAttribution::LruDistill,
    }
}
```

### §9.2 Why YES is correct

- **Real-world:** alice doesn't forget past conversations when entering new ones
- **ACT_001 R8 design** assumes this bleed (already bounded LRU + cold-decay)
- **Persona consistency:** NPC = "everything alice knows so far"
- **Drives narrative:** PC who promised alice last week → alice reminds in this week's session

### §9.3 Reality isolation (Q7-D1 LOCKED)

```
PC has 2 realities (Reality_A wuxia, Reality_B sci-fi)
alice exists in both (different incarnations per WA_002 Heresy)
→ alice in Reality_B does NOT remember Reality_A events V1

V2+ knowledge-service bridge MAY enable cross-reality user-level insights
(per concept-notes Option B); user-scoped not in-character
```

### §9.4 No faction filter (Q7-D3 LOCKED)

- alice's memories are flat (no compartmentalization)
- Privacy via DF5-A10 (no cross-session leak — alice doesn't share PC1's secret with PC2 in different session)
- alice herself remembers; alice's choice what to volunteer

---

## §10 — Token budget per active turn (Q8 LOCKED)

**Soft cap with priority dropping** (Q8-D1 LOCKED). Per-tier customization (Q8-D2 LOCKED) per `103_PLATFORM_MODE_PLAN.md`.

### §10.1 Default budget breakdown V1 (Paid tier reference)

| Block | Budget V1 | Source | Drop priority |
|---|---|---|---|
| System prompt (DF5 invariants + role) | ~300 | DF5 fixed | 6 (NEVER drop) |
| World rules (DF4 active rules) | ~200 | DF4 — V1 minimal | 5 (NEVER drop) |
| Persona block (per-actor identity + top-K memories) | ~600-800 | ACT_001 + R8 LRU | 4 (NEVER drop) |
| Recent turns (last N=10-15) | ~1000 | event log filtered | 1 (drop FIRST; keep last 5) |
| Session summary (if turn_count > 20) | ~300-500 | LLM-generated mid-session | 3 (regenerable) |
| Available actions + grammar hints | ~200 | PL_002 | 4 (NEVER drop) |
| **Total** | **~2700-3000** | | |

Output reservation: ~500-800 tokens.

**Total wallet per turn: ~3500-3800 tokens.**

### §10.2 Per-tier customization (Q8-D2 LOCKED)

| Tier | Total budget | Persona detail | Memory depth | Recent turns |
|---|---|---|---|---|
| **Free** | 2K total | condensed (~400) | top-5 | last 8 |
| **Paid** ✅ default | 3K total | full (~700) | top-15 | last 12 |
| **Premium** | 5K total | rich (~1000) | top-30 | last 20 |

### §10.3 Drop priority order (Q8-D3 LOCKED)

When budget exceeded:
1. ✅ Older recent turns (drop first; keep last 5 always)
2. ✅ Lower-salience memories (drop facts with salience < 0.5)
3. ✅ Session summary (regenerable from event log)
4. 🔒 Available actions / grammar hints (NEVER drop — gameplay correctness)
5. 🔒 World rules (NEVER drop)
6. 🔒 Persona block (NEVER drop — actor identity fundamental)
7. 🔒 System prompt (NEVER drop — invariants)

### §10.4 Per-actor budget (Q8-D4 LOCKED)

Multi-actor session: each turn = 1 LLM call but for which actor's POV?

**LOCKED: per-actor budget — each actor's turn uses their own context budget.** Matches DF5-A10 cross-session leak prevention; each actor has own context.

```
Multi-actor session, turn 15:
  PC turn (LLM call 1):
    Persona block reads PC's actor_session_memory (top-15 facts of PC's POV)
    
  NPC alice turn (LLM call 2 — different actor's POV):
    Persona block reads alice's actor_session_memory (top-15 facts of alice's POV;
    INCLUDES facts from past sessions per Q7 cross-session bleed)
```

---

## §11 — Replay-determinism via POV-distill cache (Q12 LOCKED)

LLM POV-distill is non-deterministic (temperature variance, model updates). Cache POV-summaries in EVT-T3 commit data. Replay reads cache; never re-LLM-calls.

### §11.1 Cache shape V1 (Q12-D1 LOCKED — full JSON; no compression)

```rust
pub struct EvtT3DerivedSessionPovDistill {
    pub aggregate_type: "actor_session_memory",
    pub update_kind: "SessionPovDistill",
    pub payload: {
        actor_id: ActorId,
        session_id: SessionId,
        facts: Vec<MemoryFact>,                // THE LLM OUTPUT, CACHED HERE
        llm_model_id: String,                  // e.g., "qwen/qwen3.6-35b-a3b"
        prompt_template_version: u32,           // = 1 V1; bumped on schema upgrade
        provider_id: String,                    // Q12-D4 LOCKED — lmstudio/openai/etc.
        generated_at_fiction_time: FictionTime,
        generated_at_wall_time: WallTime,       // for audit
        input_token_count: u32,                // for telemetry
        output_token_count: u32,
        attempt_count: u8,                     // 1-3 retries
    }
}
```

### §11.2 Cache invalidation (Q12-D2 LOCKED)

Re-distill triggers:
- **`prompt_template_version` mismatch** — engine prompt schema upgrade flags for regen
- **`llm_model_id` deprecated** — model retired triggers optional regen
- **`Forge:RegenSessionDistill`** admin-triggered manual regen (V1)

### §11.3 Replay path (Q12-D3 LOCKED)

```
Replay reality from event_log:
  → encounter EVT-T3 SessionPovDistill payload
  → read cached `facts` directly
  → apply to actor_session_memory aggregate
  → DO NOT re-LLM-call (deterministic per EVT-A9)

Cache invalidation mid-replay (e.g., prompt_template v1 → v2 across timeline):
  → engine logs "stale cache detected"
  → aggregate uses cached v1 facts (correct for that fiction-moment)
  → background regen with v2 prompt for future queries
```

### §11.4 Storage cost projection (Q12-D5 LOCKED)

```
Worst case: 1B NPC × 5 lifetime sessions × 1KB per distill = 5TB raw
Realistic (Major+Minor only per AIT): ~120 NPCs/cell × 1000 cells × 5 sessions × 1KB = 600MB
Per-reality bound: ~500MB-2GB total session distill cache
Acceptable V1; V1+30d reconsider compression if storage profile shows pain
```

---

## §12 — TDIL clock interaction (Q9 LOCKED)

**Session does NOT directly affect TDIL clocks. Per-turn fiction_clock advancement happens regardless of session presence.** Sessions inherit channel time_flow_rate (DF5-A3). Clocks orthogonal.

### §12.1 Per-turn fiction_duration (Q9-D1 LOCKED)

PC-proposed via PL_005 + engine default fallback. Existing PL_005 pattern unchanged by DF5.

### §12.2 Actor body/soul clocks (Q9-D2 LOCKED)

Per-turn advancement same as outside session. Channel time_flow_rate authoritative; PCS_001 body_memory BodyOrSoul determines which clock advances.

### §12.3 No time_flow_rate override (Q9-D3 LOCKED)

Channel rate authoritative per TDIL-A6. Session inherits; cannot override. Bullet-time (story-pause) deferred V2+.

### §12.4 Cross-realm session impossibility

Per TDIL-A5 (atomic-per-turn travel) + DF5-A1 (same-channel constraint), participants of one session must all be in same channel. Heaven cell + mortal cell sessions cannot share. Cross-realm observation = O(1) materialization read-only per TDIL-A7 (sees other realm's actor without participating).

---

## §13 — Disconnect grace + presence (Q10 LOCKED)

**30 wall-seconds grace for WebSocket disconnect ONLY** (Q10-D1 LOCKED). Explicit `/leave` is instant.

### §13.1 Trigger handling matrix

| Trigger | Behavior V1 |
|---|---|
| PC `/travel` to different cell | Instant session-leave (DF5-A6 cell-leave cascade); LeftReason=MovedCell |
| PC `/leave` command | Instant session-leave; LeftReason=Explicit |
| WebSocket disconnect (network/crash) | **30 wall-second grace**; presence=Disconnected |
| Browser tab close | Same as disconnect (30s grace) |
| Server crash | Same as disconnect |

### §13.2 Disconnect cascade

```rust
async fn handle_disconnect(actor_id: ActorId, session_id: SessionId) {
    mark_session_participation(session_id, actor_id, |sp| {
        sp.presence = Disconnected;
        sp.disconnect_at_wall_time = Some(now());
        // left_fiction_time stays None — not yet left
    }).await?;

    // Schedule grace timeout (Q10-D5 wall-clock NOT fiction-time)
    schedule_grace_timeout(session_id, actor_id, Duration::from_secs(30));
}

async fn handle_reconnect(actor_id: ActorId, session_id: SessionId) -> Result<()> {
    let sp = read_session_participation(session_id, actor_id).await?;
    if sp.presence != Disconnected {
        return Err(SessionError::ActorNotInDisconnectedState);
    }
    let elapsed = now().saturating_duration_since(sp.disconnect_at_wall_time.unwrap());
    if elapsed > Duration::from_secs(30) {
        return Err(SessionError::ReconnectGraceExpired);  // already left
    }
    // Within grace — restore
    mark_session_participation(session_id, actor_id, |sp| {
        sp.presence = Connected;
        sp.disconnect_at_wall_time = None;
    }).await?;
    Ok(())
}

async fn grace_timeout_fired(session_id: SessionId, actor_id: ActorId) {
    let sp = read_session_participation(session_id, actor_id).await?;
    if sp.presence != Disconnected {
        return;  // already reconnected or left
    }
    // Timeout — formal leave (Q10-D1 LOCKED)
    mark_session_participation(session_id, actor_id, |sp| {
        sp.presence = Left;
        sp.left_fiction_time = Some(current_fiction_time());
        sp.left_reason = Some(LeftReason::DisconnectTimeout);  // V1 distinct from Inactive (V1+30d auto-detect)
    }).await?;
    check_anchor_invariant_after_leave(session_id, actor_id).await;
}
```

### §13.3 Forge override (Q10-D4 LOCKED)

`Forge:KickFromSession { actor_id, force=true }` skips 30s timer for abuse mitigation (PC server-crashing intentionally to hold session).

### §13.4 Wall-clock vs fiction-time (Q10-D5 LOCKED)

Grace period = 30 wall-seconds (NOT fiction-time). Disconnect = real-world infra event, NOT in-fiction.

---

## §14 — Forge admin operations (Q11 LOCKED)

**Pre-close edits OK; post-close NO direct edit; Regen + Purge allowed.**

### §14.1 V1 Forge AdminAction sub-shapes (9 total)

| AdminAction | Phase | Q-LOCKED | Description |
|---|---|---|---|
| `Forge:CreateSession { channel_id, anchor_pc_id, initial_participants }` | pre-close | V1 | Author canonical seed session at bootstrap OR runtime |
| `Forge:CloseSession { session_id, reason }` | pre-close | V1 | Force-close active session (admin abuse mitigation, narrative reset) |
| `Forge:KickFromSession { session_id, actor_id, force }` | pre-close | V1 | Eject participant; `force=true` skips 30s grace |
| `Forge:EditActorSessionMemory { actor_id, session_id, edit_kind, before, after }` | pre-close | V1 | Add/remove/modify/salience-adjust facts; modify i18n strings (Q11-D1) |
| `Forge:RegenSessionDistill { session_id }` | post-close | V1 | Re-run LLM POV-distill (e.g., after prompt_template_version upgrade) |
| `Forge:PurgeActorSessionMemory { actor_id, session_id }` | post-close | V1 | Delete all distilled facts for one actor (GDPR or correction) |
| `Forge:AnonymizePcInSessions { actor_id }` | post-close | V1 | Replace PC name in OTHER actors' memories with "kẻ lạ" (GDPR Q11-D3) |
| `Forge:BulkRegenSessionDistill { reality_id, session_filter, prompt_template_version }` | post-close | V1 | Bulk regen with new prompt schema (Q11-D4) |
| `Forge:BulkPurgeStaleSessions { reality_id, before_fiction_time }` | post-close | V1 | Bulk cleanup; admin abuse mitigation (Q11-D4) |

### §14.2 Audit per WA_003 (Q11-D5 LOCKED)

Every Forge memory operation:
- Emits EVT-T8 Administrative
- Logged in `forge_audit_log` (per WA_003 pattern)
- Includes: who_edited (UserId), when (wall_time + fiction_time), before snapshot, after snapshot, reason (free text)
- Retained per WA_003 audit policy — **CANNOT be deleted** (audit-grade integrity for GDPR compliance)

### §14.3 Player visibility (Q11-D6 LOCKED)

V1: **invisible to player.** Forge edits do NOT surface to PC owner. Audit trail server-side only. Privacy laws may require disclosure later (V1+30d transparency feature DF5-D16).

---

## §15 — Retention policy + GDPR (Q6 LOCKED)

### §15.1 Aggregate retention (Q6-D1 LOCKED — Unlimited V1)

- **V1:** Unlimited retention; no auto-purge. Manual purge via Forge.
- **V1+30d:** auto-TTL after 1 fiction-year if storage profile shows pain (DF5-D17)
- **V2+:** archive aggregate `closed_session_archive` (T3/Reality cold tier; Postgres metadata + MinIO blob)

Storage cost: ~200B per session row × 1B sessions = 200GB worst-case per reality (acceptable).

### §15.2 GDPR per-actor erasure (Q6-D4 LOCKED)

PC delete:
- All `actor_session_memory[pc_id, *]` rows purged
- `session_participation[*, pc_id]` marked `deleted_for_user`
- OTHER actors' POV facts retain (no cascade reality state damage)
- `Forge:AnonymizePcInSessions { actor_id: pc_id }` replaces PC name in OTHER actors' memories with "kẻ lạ" (anonymous)
- Audit trail in `forge_audit_log` retains operation evidence (cannot delete audit layer per WA_003)

### §15.3 Death = freeze (Q6-D5 LOCKED)

Actor dies (mortality_state=Dead per WA_006):
- `actor_session_memory` frozen at death fiction_time
- Sessions accessible by Forge audit only; player cannot access
- Retention same as alive; no separate timeline

### §15.4 Reality close cascade (EM-7)

```
Reality enters EM-7 close lifecycle
→ All Active sessions in reality cascade-close
→ For each: close_reason = RealityClosed; LLM POV-distill SKIPPED (cost-saving)
→ actor_session_memory writes brief "Reality ended" placeholder fact only
→ Reality archive captures session metadata for replay-only access
```

---

## §16 — SDK Architecture (LOCKED 2026-04-27)

DF05 ships as **versioned SDK contract + swappable backend implementations**. Consumers depend on contract; backends implement; rework backend without consumer changes.

### §16.1 Three-layer architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ CONSUMERS (NEVER import implementation)                           │
│ · NPC_001/002 persona prompt assembly                             │
│ · PCS_001 body_memory continuation                                │
│ · WA_003 Forge admin moderation                                   │
│ · Future: Memory UI for player, analytics, cross-reality bridge   │
└──────────────────────────┬───────────────────────────────────────┘
                           │ STABLE SDK CONTRACT (versioned)
                           │ contracts/api/session/v1/
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ MEMORY SDK CONTRACT                                                │
│ · SessionService trait (lifecycle)                                 │
│ · MemoryProvider trait (read)                                      │
│ · Versioned DTOs (PersonaContextBlock, MemoryFactView)            │
│ · MemoryQuery DSL (no raw SQL/Cypher leak)                        │
│ · ContractTestSuite (~30 scenarios)                                │
│ · MemoryProviderCapabilities (graceful degradation probe)         │
└──────────────────────────┬───────────────────────────────────────┘
                           │ implementation choice (swappable)
                           │ services/session-service/src/adapters/
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ BACKENDS (interchangeable; rolled out via feature flags)          │
│                                                                   │
│ V1: LruDistillProvider                                            │
│     · Option A — close-distill, ACT_001 R8 LRU bounded            │
│                                                                   │
│ V1+30d: + SalienceTranscriptProvider (composite layer)            │
│         · Option C — opt-in raw blob for high-salience sessions   │
│                                                                   │
│ V2+: + KnowledgeServiceBridge (cross-reality user-level insight)  │
│      · Option B — knowledge-service integration                   │
│                                                                   │
│ Future: + custom backends (perfect-memory NPCs, archival, etc.)   │
└──────────────────────────────────────────────────────────────────┘

CI ENFORCEMENT (mandatory):
- services/world-service/, services/api-gateway-bff/, frontend/ MUST NOT import
  from services/session-service/src/adapters/
- Only contracts/api/session/v1/ allowed
- CI fails build if violated
```

### §16.2 SessionService trait (7 lifecycle ops)

```rust
#[async_trait]
pub trait SessionService: Send + Sync {
    async fn create_session(&self, req: CreateSessionRequest) -> Result<SessionView, SessionError>;
    async fn join_session(&self, req: JoinRequest) -> Result<JoinOutcome, SessionError>;
    async fn leave_session(&self, req: LeaveRequest) -> Result<LeaveOutcome, SessionError>;
    async fn close_session(&self, req: ForgeCloseRequest) -> Result<CloseOutcome, SessionError>;
    async fn record_turn(&self, req: RecordTurnRequest) -> Result<RecordTurnOutcome, SessionError>;
    async fn get_session(&self, session_id: SessionId) -> Result<SessionView, SessionError>;
    async fn list_active_in_channel(&self, channel_id: ChannelId) -> Result<Vec<SessionView>, SessionError>;
}
```

### §16.3 MemoryProvider trait (4 read ops + capabilities probe)

```rust
#[async_trait]
pub trait MemoryProvider: Send + Sync {
    async fn get_persona_context(&self, req: PersonaContextRequest) -> Result<PersonaContextBlock, MemoryError>;
    async fn query(&self, q: MemoryQuery) -> Result<MemoryQueryResult, MemoryError>;
    async fn replay_session(&self, session_id: SessionId) -> Result<TurnStream, MemoryError>;
    fn capabilities(&self) -> &MemoryProviderCapabilities;
}

pub struct MemoryProviderCapabilities {
    pub supports_verbatim_replay: bool,         // Option C provides
    pub supports_semantic_similarity: bool,      // V2+ Option B provides
    pub supports_cross_reality_query: bool,      // V2+ knowledge-service bridge
    pub max_query_horizon: Duration,             // R8 cold-decay limit
    pub provider_version: String,                // for telemetry + audit
}
```

### §16.4 Versioned DTO (forward-compatible)

```rust
#[derive(Serialize, Deserialize, Clone)]
pub struct PersonaContextBlock {
    pub schema_version: u8,                       // = 1 V1
    pub actor_id: ActorId,
    pub target_actor_id: Option<ActorId>,
    pub recent_memories: Vec<MemoryFactView>,
    pub opinion: Option<OpinionView>,
    pub mood: Option<ActorMood>,
    pub relevant_facts: Vec<FactView>,
    pub generated_at_fiction_time: FictionTime,
    pub provider_attribution: ProviderAttribution,
}

// Tolerant readers — V1 ignores unknown fields, allowing V2 backend additive expansion
#[derive(Deserialize)]
#[serde(deny_unknown_fields = false)]
struct PersonaContextBlockReader { /* V1 fields only */ }
```

### §16.5 MemoryQuery DSL

```rust
pub enum MemoryQuery {
    // V1 query types
    ByActorAboutTarget { actor_id, target, kinds, max_results },
    BySession { session_id, limit },
    ByActorRecentSessions { actor_id, since, limit },
    ByActorRecentBySalience { actor_id, max_results, target_filter },

    // V2+ additive (capability-gated; V1 backends reject with NotSupported)
    BySemanticSimilarity { actor_id, query_text, max_results },
    CrossRealityByUser { user_id, kind },
}
```

### §16.6 Migration patterns (5 patterns)

**Pattern 1: Shadow-read** — new backend reads alongside old; results compared; logged. Validate ≥99.5% match before switch.

**Pattern 2: Dual-write** — both backends receive writes during migration window. Old result canonical until verification; switch reads after stability.

**Pattern 3: Versioned DTOs + tolerant readers** — V1 consumers ignore unknown fields. V2 backend adds fields; V1 still works.

**Pattern 4: Capability-gated graceful degradation** — V1 consumers probe `capabilities()` before using V2 features; gracefully fall back if unavailable.

**Pattern 5: Contract test suite (the firewall)** — ~30 scenarios covering DF5-A1..A11 + edge cases. Mandatory CI gate; PR blocked if any backend fails.

### §16.7 Mapping into LoreWeave structure

```
contracts/api/session/                          ← THE SDK (frozen V1)
├── v1/
│   ├── session_service.rs        # SessionService trait
│   ├── memory_provider.rs        # MemoryProvider trait
│   ├── dto.rs                    # PersonaContextBlock, MemoryFactView, ...
│   ├── query.rs                  # MemoryQuery DSL
│   ├── errors.rs                 # SessionError, MemoryError
│   ├── capabilities.rs           # MemoryProviderCapabilities
│   └── contract_tests.rs         # ~30 scenarios
├── openapi/
│   ├── session_v1.yaml
│   └── memory_v1.yaml
└── _CHANGELOG.md                  # version history

services/session-service/                       ← THE IMPLEMENTATION
├── src/
│   ├── main.rs                   # boot
│   ├── adapters/
│   │   ├── lru_distill.rs        # V1 backend
│   │   ├── salience_transcript.rs # V1+30d backend
│   │   ├── knowledge_bridge.rs   # V2+ backend
│   │   ├── shadow_read.rs        # migration helper
│   │   └── dual_write.rs         # migration helper
│   ├── routing.rs
│   └── feature_flags.rs
└── tests/
    └── contract.rs               # imports contract_tests; runs all backends
```

---

## §17 — RealityManifest extensions

```rust
pub struct RealityManifest {
    // ... existing fields ...

    // ─── DF5 extension (OPTIONAL V1) ───
    pub canonical_sessions: Vec<CanonicalSessionDecl>,    // V1+ author-scripted set-piece sessions
}

pub struct CanonicalSessionDecl {
    pub session_id: SessionId,                            // pre-deterministic for replay
    pub channel_id: ChannelId,                             // anchor cell
    pub anchor_pc_template: ActorTemplateRef,              // PC role at session start
    pub initial_npc_participants: Vec<ActorRef>,           // pre-joined NPCs
    pub bootstrap_facts: Vec<MemoryFactSeed>,              // pre-seeded actor_session_memory
}
```

V1 default: empty `canonical_sessions: []`. Authors opt-in for set-piece dramatic moments.

---

## §18 — Validator chain (DF5-V1..V4)

| Slot | Validator | When | Reject rule_id |
|---|---|---|---|
| **DF5-V1** | ParticipantCapValidator | session.create / session_participation.born | `session.participant_cap_exceeded` |
| **DF5-V2** | OneActiveSessionValidator | session_participation.born | `session.actor_busy_in_other_session` |
| **DF5-V3** | SameChannelValidator | session_participation.born | `session.cross_channel_participation_forbidden` |
| **DF5-V4** | TierEligibilityValidator | session_participation.born | `session.actor_not_eligible_untracked` |

Slot ordering: **Stage 0 (canonical seed pre-validation)** for DF5-V1..V3 (write-time); **Stage 1 (per-turn runtime)** for DF5-V4 (consumer-aware tier check).

Cross-aggregate consistency rules (registered in `_boundaries/03_validator_pipeline_slots.md`):
- **DF5-C1**: `session.anchor_pc_id` MUST be PC kind (verify via ACT_001)
- **DF5-C2**: `session.channel_id` MUST be cell-tier (verify via PF_001)
- **DF5-C3**: Active session count per cell MUST be ≤50 (DF5-A8)
- **DF5-C4**: Active session count per actor MUST be ≤1 (DF5-A5)

---

## §19 — Acceptance criteria (AC-DF5-1..25)

**25 V1-testable scenarios:**

1. **AC-DF5-1 — Session born via /chat:** PC issues `/chat @alice` at cell — `session_participation` table has 2 rows (PC + alice) + `session.state = Active` + EVT-T3 Derived `aggregate_type=session` Born event committed. Verifies §3.1 + §3.2 + §2.5.

2. **AC-DF5-2 — Solo monologue (0 NPC):** PC issues `/chat` with no targets — session created with 1 participant (PC anchor only); state=Active; turn_count=0. Verifies Q2 LOCKED.

3. **AC-DF5-3 — Participant cap rejection:** PC issues `/chat @a @b @c @d @e @f @g @h @i` (9 actors) — engine rejects with `session.participant_cap_exceeded`; no session created. Verifies §3.1 + DF5-A8 + Q3-D1.

4. **AC-DF5-4 — Anchor PC invariant:** Forge:CreateSession with `anchor_pc_id: <NPC_actor_id>` rejects `session.anchor_must_be_pc`. Verifies §3.1 + DF5-A4.

5. **AC-DF5-5 — Cell session capacity:** 50 active sessions exist at `cell:lin_an`; PC tries to create 51st — rejects `session.cell_session_overload`. Verifies DF5-A8.

6. **AC-DF5-6 — One active session per actor:** alice currently in SessionA; PC2 tries `/chat @alice` from different session B — engine rejects with `session.actor_busy_in_other_session`. Verifies DF5-A5.

7. **AC-DF5-7 — Untracked NPC reject:** PC issues `/chat @some_villager` (Untracked-tier per AIT) — rejects `session.actor_not_eligible_untracked`. Verifies §8.4 + DF5-A6 + AIT-A8.

8. **AC-DF5-8 — Reputation Hated reject:** PC has Hated rep with alice's faction — `/chat @alice` rejects `session.npc_refused`; LLM-flavored refusal message returned. Verifies §8.1 + Q4-D1.

9. **AC-DF5-9 — Reputation Unfriendly reluctant:** PC has Unfriendly rep with alice's faction — `/chat @alice` accepts; alice joins with mood=Sour. Verifies §8.1 + Q4-D1.

10. **AC-DF5-10 — Personal opinion override faction rep:** alice has +80 opinion of PC; faction rep is Hostile — alice accepts (gradient ±2 tiers shifts to Unfriendly reluctant). Verifies Q4-D2.

11. **AC-DF5-11 — Anchor PC leave triggers close:** SessionA has {PC, alice, bob}; PC issues `/leave` — session_participation marks PC.left; check_anchor_invariant fires; cascade closes session; alice + bob marked left with reason=AnchorPcLeft. Verifies §5 close cascade.

12. **AC-DF5-12 — POV distill on close (turn_count >= 3):** SessionA closes after 5 turns — for each participant, EVT-T6 Proposal + EVT-T3 Derived emitted with cached MemoryFact[] payload; actor_session_memory rows updated. Verifies §6.

13. **AC-DF5-13 — POV distill skipped (turn_count < 3):** SessionA closes after 1 turn — no LLM call; no actor_session_memory writes from distill. Verifies Q2-D2.

14. **AC-DF5-14 — Disconnect grace 30s reconnect:** PC's WebSocket disconnects; presence=Disconnected; PC reconnects within 25s — presence=Connected; session unchanged. Verifies §13.

15. **AC-DF5-15 — Disconnect grace 30s timeout:** PC disconnects; 35s pass without reconnect — grace_timeout_fired marks PC.left with reason=Inactive; check_anchor_invariant fires; session closes if last PC. Verifies §13 + Q10.

16. **AC-DF5-16 — Forge override grace:** Admin issues `Forge:KickFromSession { actor_id: PC, force: true }` while PC in 30s grace window — session_participation marks PC.left immediately; close cascade fires. Verifies §14.1 + Q10-D4.

17. **AC-DF5-17 — Forge edit pre-close:** Active session A; admin issues `Forge:EditActorSessionMemory { actor_id: alice, session_id: A, edit_kind: Add, fact: ... }` — actor_session_memory[alice, A] gains fact; EVT-T8 Administrative emitted; forge_audit_log entry created. Verifies §14.1 Q11-D1.

18. **AC-DF5-18 — Forge edit post-close rejected:** Closed session A; admin issues `Forge:EditActorSessionMemory` directly — rejects `session.closed_session_immutable`. Verifies §14.1 + Q11-D2 + DF5-A7.

19. **AC-DF5-19 — Forge regen post-close:** Closed session A with prompt_template_version=1; admin issues `Forge:RegenSessionDistill { session_id: A }` — re-runs LLM POV-distill for all participants; new EVT-T3 SessionPovDistill cached with prompt_template_version=2. Verifies §14.1 + Q11-D2.

20. **AC-DF5-20 — GDPR PC erasure:** PC requests deletion; admin issues `Forge:PurgeActorSessionMemory + Forge:AnonymizePcInSessions` — PC's memory rows purged; OTHER actors' memory references replaced with "kẻ lạ"; forge_audit_log retains operation evidence (cannot delete audit). Verifies §15.2 + Q11-D3 + Q6-D4.

21. **AC-DF5-21 — Cross-session memory bleed:** alice in past SessionA learned "PC saved my life" (salience 0.95). PC `/chat @alice` now creates SessionB. Persona prompt assembly for alice in SessionB includes this fact among top-15. Verifies §9 + Q7.

22. **AC-DF5-22 — No cross-reality memory bleed:** PC has 2 realities A + B with alice in both. alice in Reality_B does NOT see Reality_A facts in persona context. Verifies Q7-D1.

23. **AC-DF5-23 — Token budget per-tier:** Free tier session — PC turn LLM call uses 2K total tokens (condensed persona + top-5 memories + last 8 turns). Verifies §10.2 + Q8-D2.

24. **AC-DF5-24 — Replay-determinism cache:** Replay reality from event_log; encounter EVT-T3 SessionPovDistill payload — apply cached facts directly to actor_session_memory aggregate; NO LLM call invoked during replay. Verifies §11 + Q12-D3 + EVT-A9.

25. **AC-DF5-25 — Contract test suite — backend swap:** Run ContractTestSuite against `LruDistillProvider` and `SalienceTranscriptProvider` — both pass identical 25 scenarios (modulo Option C verbatim-replay capability). Verifies §16.6 SDK contract integrity.

---

## §20 — Sequences (5 worked examples)

### §20.1 PC switches conversation (the canonical example)

```
1. PC enters tavern cell. Cell has 30 NPCs ambient (no session).
2. PC clicks alice + bob avatars → `/chat @alice @bob`
   → DF5-V1..V3 validators pass
   → DF5-V4 tier check: alice + bob both Major NPC → eligible
   → §8.1 NPC consent: alice friendly + bob neutral → both accept
   → SessionA created: state=Active, channel_id=tavern, anchor_pc_id=PC
   → 3 SessionParticipation rows created (PC=Anchor, alice + bob=Joined)
   → 3 EVT-T3 Derived events committed
3. PC chats 5 turns with alice/bob.
   → Each turn: EVT-T1 Submitted PCTurn / NPCTurn
   → actor_session_memory[*, A] grows during session via in-session reads
   → turn_count=5, last_turn_fiction_time updated
4. PC issues `/chat @carol @dan` (different group):
   a. PC marked left in SessionA (left_fiction_time=now, left_reason=Explicit)
   b. SessionA participant check: PC was only PC → DF5-A4 triggers close cascade
   c. SessionA close cascade:
      - emit ClosingTransition
      - LLM POV-distill × 3 (PC, alice, bob)
      - cache facts in EVT-T3 payload
      - write actor_session_memory[*, A] final state
      - mark SessionA.state=Closed
      - alice + bob marked left with reason=AnchorPcLeft (forced)
   d. alice + bob → ambient (NPC at cell, no session)
5. SessionB created with {PC, carol, dan}.
6. SessionB independent of SessionA.
7. Future: PC reads actor_session_memory; sees SessionA + SessionB facts separately tagged by session_id.
```

### §20.2 Two PCs in same cell, separate conversations

```
PC1 in SessionA with alice. PC2 in SessionB with bob. Same cell.
→ DF5-A10 enforces no cross-session visibility.
→ AIT context: 4 LLM-context slots used (alice + bob + persona for both PCs).
→ 28 ambient NPCs cost ~0 (just density check).
→ Real-world parallel: 2 conversations at the tavern.
```

### §20.3 NPC busy with one session, PC tries to engage

```
NPC alice ∈ SessionA. PC2 issues `/chat @alice` (PC2 in different SessionB).
→ DF5-V2 OneActiveSessionValidator fires.
→ Reject `session.actor_busy_in_other_session`.
→ Hint to PC2: "Alice đang nói chuyện với người khác."
→ PC2 may wait (poll), or choose another target.
V2+: alice's NPC desire system may auto-leave SessionA if PC2 reputation/desire-match better.
```

### §20.4 Disconnect with reconnect within grace

```
PC chats với alice tại tavern.
PC's WiFi blips for 12 seconds.
  → server detects disconnect → SessionParticipation.presence=Disconnected
  → 30s grace timer scheduled
Wall-clock 12s later: PC reconnects → presence=Connected
  → grace timer canceled
  → session unchanged; turn count unchanged; alice none the wiser

vs:

PC's WiFi dies entirely (>30s).
  → server detects disconnect → presence=Disconnected
  → 30s timer expires → grace_timeout_fired
  → mark PC.left with reason=Inactive
  → check_anchor_invariant fires: PC was last PC → close cascade
  → SessionA closes; POV-distill runs
  → alice → ambient at tavern
```

### §20.5 Forge close + GDPR cascade

```
Author/admin issues Forge:CloseSession { session_id, reason: ForgeClose }
  → EVT-T8 AdminAction
  → forge_audit_log entry: { admin_uid, action: CloseSession, session_id, reason: "narrative reset" }
  → Standard close cascade fires (all participants distill via Q5 LOCKED template)
  → session_participation[*, session_id] marked left, reason=Kicked

Subsequent: PC owner deleted account (GDPR right to erasure)
  → Forge:PurgeActorSessionMemory { actor_id: PC, session_id: ALL }
  → Forge:AnonymizePcInSessions { actor_id: PC }
  → All actor_session_memory[PC, *] rows purged
  → All references to PC in OTHER actors' memories replaced with "kẻ lạ"
  → forge_audit_log retains operation evidence (audit-grade requirement; cannot delete)
```

---

## §21 — RejectReason rule_id catalog (`session.*` namespace)

### §21.1 V1 reject rule_ids (14 rules)

Registered in `_boundaries/02_extension_contracts.md` §1.4.

| rule_id | Trigger | Vietnamese reject copy V1 | Soft-override eligible |
|---|---|---|---|
| `session.duplicate_session_id` | second write attempt for `session_id` already exists | "ID phiên hội thoại đã tồn tại." | No (write-time) |
| `session.participant_cap_exceeded` | 9+ participants requested (V1 cap=8) | "Phiên hội thoại không thể chứa quá 8 người." | No (DF5-A8) |
| `session.cell_session_overload` | 51st active session at cell (V1 cap=50) | "Khu vực này đã có quá nhiều phiên hội thoại đang diễn ra." | No (DF5-A8) |
| `session.actor_not_eligible_untracked` | Untracked NPC in participant list | "Người này không thể tham gia hội thoại." | No (DF5-A6 + AIT-A8) |
| `session.actor_busy_in_other_session` | actor already in another active session | "Họ đang nói chuyện với người khác." | No (DF5-A5) |
| `session.participant_already_joined` | composite key (session_id, actor_id) duplicate write — actor attempts to join same session twice | "Bạn đã tham gia phiên hội thoại này rồi." | No (defensive write-time validator on session_participation Born) |
| `session.npc_refused` | reputation Hated/Hostile (per Q4-D1) | LLM-generated persona-flavored refusal | No (Q4-D1) |
| `session.invalid_state_transition` | Closed → Active OR Closed → Closed write attempt | "Phiên hội thoại đã đóng và không thể mở lại." | No (DF5-A7) |
| `session.empty_participant_list_invalid` | session created with 0 participants AND 0 NPC count for non-monologue mode (impossible after Q2; defensive) | "Phiên hội thoại không thể trống." | No (defensive) |
| `session.anchor_must_be_pc` | session.anchor_pc_id not PC kind | "Chỉ người chơi mới có thể khởi tạo phiên hội thoại." | No (DF5-A4) |
| `session.cross_channel_participation_forbidden` | session_participation.actor at different channel from session.channel_id | "Tham gia hội thoại phải ở cùng vị trí." | No (DF5-A1 + TDIL-A5) |
| `session.closed_session_immutable` | participant write attempt after Closed transition | "Phiên hội thoại đã đóng — không thể chỉnh sửa." | No (DF5-A7) |
| `session.distill_cache_version_mismatch` | EVT-T3 cache prompt_template_version doesn't match current engine | "Bản tóm tắt cần được tái tạo." | Yes (V1+30d auto-regen background) |
| `session.cell_session_creation_rate_limited` | PC creates >5 sessions in <1 minute wall-clock | "Bạn đang khởi tạo phiên hội thoại quá nhanh." | No (anti-spam) |

### §21.2 V1+ reservations

```
session.cross_reality_session              (V2+ if multi-reality session — currently impossible per TDIL-A5)
session.npc_only_session_disallowed        (V1 hard-reject; V2+ DF1 ambient may allow)
session.session_resume_disallowed          (V1 hard; V3+ resume feature)
session.summary_corruption_detected        (V1+30d transcript verify SalienceTranscript backend)
session.distill_quota_exceeded             (V1+30d cost cap per usage-billing-service)
```

---

## §22 — Open questions (post-DRAFT)

| ID | Question | Resolution path |
|---|---|---|
| **DF5-Q1** | Async background distill V1+30d (DF5-D13) — when to ship? | Profile V1 production for stutter pain; ship V1+30d if observed |
| **DF5-Q2** | Per-tier customized POV-distill prompt V1+30d (DF5-D6) — Major elaborate vs Minor terse — when to ship? | Profile V1 distill quality per tier; ship V1+30d if drift observed |
| **DF5-Q3** | Cross-session memory salience tuning — top-K=10-20 default; need empirical validation | V1 prototype measurement (NPC-4 retrieval quality coordination) |
| **DF5-Q4** | Session capacity cap soft-50 — empirical adequacy at scale | Production V1 monitoring; bump V1+30d if hit frequency >1% |

---

## §23 — Deferrals (DF5-D1..DF5-D17)

| ID | Feature | Why deferred | Target phase |
|---|---|---|---|
| **DF5-D1** | Multi-PC join existing session | V1 solo RP scope | V2 |
| **DF5-D2** | Whisper (1-to-1 within session) | depends DF5-D1 multi-PC | V2 |
| **DF5-D3** | PvP within session (consent flow) | depends DF4 World Rules | V2 |
| **DF5-D4** | Idle state (auto-detect inactive session) | not blocking V1 | V1+30d |
| **DF5-D5** | Wall-clock 24h timeout | anchor-leave close enough V1 | V1+30d |
| **DF5-D6** | Per-tier customized POV-distill prompt | single template enough V1 | V1+30d |
| **DF5-D7** | NPC initiates session (desire-driven) | NPC_003 V1 read-only | V2 |
| **DF5-D8** | Frozen state (Forge/DF4 explicit pause) | not blocking V1 | V2 |
| **DF5-D9** | NPC-NPC autonomous continuation | DF1 daily life dependency | V3 |
| **DF5-D10** | Closed session resume | V1 invariant immutable on close | V3 |
| **DF5-D11** | Cross-cell session cluster | TDIL-A5 atomic-channel V1 | V3 |
| **DF5-D12** | Public broadcast (PC shouts to cell) | one-off event suffices V1 | V3+ |
| **DF5-D13** | Async background distill | V1 sync acceptable | V1+30d |
| **DF5-D14** | Per-NPC refusal cooldown | grammar layer rate-limit V1 | V1+30d |
| **DF5-D15** | Reputation -1 per refusal | grief mitigation if needed | V1+30d |
| **DF5-D16** | Player-visible Forge edit transparency | invisible V1; transparency law may require | V1+30d |
| **DF5-D17** | Auto-TTL closed sessions after 1 fiction-year | unlimited V1; storage profile dependent | V1+30d |

---

## §24 — Cross-references

- **PL_001 Continuum** §3.6 entity_binding.location.InCell — session_participation.actor cell membership consumer
- **PL_001 Continuum** §13 travel sequence — cell-leave cascade triggers session-leave with LeftReason::MovedCell
- **PL_002 Grammar** — `/chat @actor [@actor...]` + `/leave` + `/whisper` (V2) command surface
- **PL_005 Interaction** — turn submission within session; `session_id` reference field on PCTurn / NPCTurn
- **ACT_001 Actor Foundation** §3.4 actor_session_memory R8 bounded LRU — primary post-close memory store
- **NPC_001 Cast** — NPC eligibility check (tier + busy-elsewhere) at /chat invite; persona prompt assembly switches to MemoryProvider trait
- **NPC_002 Chorus** — turn ordering within multi-NPC session; tier-aware persona via MemoryProvider
- **NPC_003 Desires** — desire-driven NPC join/leave V2+; V1 read-only context input
- **REP_001 Reputation Foundation** — 8-tier reputation gating for §8 NPC consent
- **WA_003 Forge** — admin actions §14.1 (9 V1 sub-shapes) + audit per §14.2
- **WA_006 Mortality** — death cascade V1+30d (combat in session) for SessionParticipation.left_reason=Killed
- **AIT_001 AI Tier** — tier eligibility (DF5-A6 Untracked exclusion); tier-aware persona retrieval via MemoryProvider capability gate
- **PCS_001 PC Substrate** — PC body_memory feeds prompt-assembly for session turns; per-PC active-session lookup
- **PF_001 Place Foundation** — cell-tier session capacity tracking; cell display "5 active conversations"
- **EM-7 Reality Close** — cascade sessions to ClosedTransition with reason=RealityClosed; skip POV-distill cost-saving
- **TDIL_001 Time Dilation** — DF5-A1 same-channel constraint per TDIL-A5; DF5-A3 time_flow_rate inheritance per TDIL-A6
- **DF4 World Rules** — V1+30d override consumer for session_caps_override + disconnect_grace_override
- **07_event_model** — register `aggregate_type=session` + `session_participation` EVT-T3 sub-types; `SessionBorn` EVT-T4
- **RealityManifest** — OPTIONAL `canonical_sessions` extension §17
- **SDK contracts** — `contracts/api/session/v1/` (NEW); `services/session-service/` (NEW)

---

## §25 — Status footer

**Last updated:** 2026-04-27 (DRAFT NEW — commit 2/4 of 4-commit cycle)

**Phase:** DRAFT 2026-04-27 — Q1-Q12 ALL LOCKED via 4-batch deep-dive 2026-04-27 (zero revisions). §16 SDK Architecture LOCKED. 11 invariants DF5-A1..A11 codified. Ready for Phase 3 cleanup commit 3/4.

**Promotion gate (to CANDIDATE-LOCK):**
- ✅ Q1-Q12 ALL LOCKED via 4-batch deep-dive 2026-04-27
- ✅ §16 SDK architecture LOCKED (5 decisions confirmed)
- ✅ 25 V1-testable acceptance scenarios AC-DF5-1..25 documented
- ✅ 13 V1 reject rule_ids in `session.*` namespace + 5 V1+ reservations
- ✅ 4 validator slots DF5-V1..V4 + 4 cross-aggregate consistency rules DF5-C1..C4
- ✅ 9 Forge AdminAction sub-shapes registered §14.1
- ✅ RealityManifest extension §17 OPTIONAL `canonical_sessions`
- 🟡 Phase 3 cleanup walkthrough pending (commit 3/4)

**Cycle plan:**
1. ✅ Phase 0 (commit 0080b533): concept-notes Q-LOCKED + SDK LOCKED
2. ✅ Commit 1/4 (745e9f6e): `[boundaries-lock-claim]` lock + cycle plan
3. 🟡 Commit 2/4 (THIS): DRAFT promotion + boundary register + catalog seed
4. ⏳ Commit 3/4: Phase 3 cleanup — AC walkthrough + typo fixes + thin-section expansion
5. ⏳ Commit 4/4: `[boundaries-lock-release]` CANDIDATE-LOCK closure

**16 cross-feature closure-pass-extensions** queued (PL_002 + PL_005 + NPC_001..003 + ACT_001 + REP_001 + WA_003 + WA_006 + AIT_001 + PCS_001 + PL_001 + PF_001 + EM-7 + 07_event_model + RealityManifest) — to fire in subsequent commits post-CANDIDATE-LOCK.

**Implementation phase** (post-CANDIDATE-LOCK):
- Create `contracts/api/session/v1/` directory + 7 files
- Scaffold `services/session-service/` initial structure (V1 LruDistillProvider)
- CI lint rule: block consumer imports of `services/session-service/src/adapters/`
- Contract test suite ~30 scenarios CI gate

**Architectural decisions LOCKED 2026-04-27:**
- §1 Multi-session-per-cell sparse model (vs initial single-session-per-cell rejected)
- §6 Close-time POV-distill primary mechanism (Option A core; Option C V1+30d salience opt-in)
- §16 SDK contract + swappable backend pattern (consumers depend on trait, not implementation)
- 11 invariants DF5-A1..A11
- Q1-Q12 all locked

---

**DRAFT promotion COMPLETE 2026-04-27 commit 2/4. Ready for Phase 3 cleanup walkthrough.**
