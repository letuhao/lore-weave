# DF05 Session/Group Chat Foundation — Concept Notes

> **Status:** CONCEPT 2026-04-27 — captures user framing rejection of single-session-per-cell + revised multi-session-per-cell architecture + lifecycle + invariants + Q1-Q12 PENDING. NOT a design doc; the seed material for the eventual `DF05_001_session_foundation.md` design.
>
> **Purpose:** Capture brainstorm + architectural decisions + LLM-engine separation discipline + Q1-Q12 PENDING for DF05 Session/Group Chat Foundation. NOT a design doc; the seed material for the eventual `DF05_001_session_foundation.md` design with all critical Qs locked.
>
> **Promotion gate (to DRAFT):** When (a) Q1-Q12 LOCKED via deep-dive (mirror PROG/AIT/TDIL/COMB pattern), (b) `_boundaries/_LOCK.md` is free, (c) AIT_001 + PCS_001 + ACT_001 closure-pass-extension scope agreed (cross-feature impact §12) → main session drafts `DF05_001_session_foundation.md` in single combined boundary commit.
>
> **Origin:** User direction 2026-04-27 — concerns about scaling to billion NPC + real-life conversation parallel; rejection of "all-actors-at-cell auto-join" model (initial main-session proposal); architectural insight from real social dynamics.

---

## §1 — User's core framing

### §1.1 Initial main-session proposal (REJECTED)

Main session proposed (2026-04-27) a model where:
- "Session" = container per cell holding ALL actors at that cell auto-joined
- Single Active session per (PC, cell) at a time
- Lifecycle: Active / Idle / Frozen / Closed (4 states)

User response (verbatim, Vietnamese):

> "không ổn, chúng ta không thể thiết kế kiểu này
> có cả tỷ NPC, dồng hết vào 1 session là điều bất khả thi
>
> hay vào đó nên thiết kế session là đơn vị cục bộ đi theo 1 cell cố định
> 1 cell có nhiều sessions
>
> ví dụ PC vào cell tavern, mở group chat tương tác với 2 PC khác thì session này nằm trong cell đó thôi
> xong PC mở sang group chat mới tương tác với 2 NPC
>
> ở đây có 2 session và chúng chỉ có giá trị cho tới khi người tham gia rời khỏi session, lúc này dữ liệu được cho là quan trọng trong session chỉ còn lưu trong memory của người tham gia. Họ không thể quay lại session cũ nếu session đã đóng (không còn ai trong group chat), dữ liệu session đã đóng đã chuyển thành memory của mỗi actor tham gia, họ chỉ có thể xem nó trong memory của họ
>
> bạn thấy cách thiết kế này ra sao? vừa giống với thực tế cuộc sống với tránh việc session phình to khổng lồ"

### §1.2 The architectural insight

3 critical observations from user:

1. **Scaling reality check**: AIT_001 supports billion NPCs per reality. Coalescing all cell actors into one session is mathematically infeasible at scale — even tavern with 1000 ambient NPCs would burn LLM context budget for 950 actors who never engage with PC.

2. **Real-life conversation parallel**: enter a tavern → 50 people present → you talk to 2-3 at your table → 47 others are background. Each table = independent conversation. NO "tavern-wide group chat" exists.

3. **Subjective memory model**: closed conversations don't persist as objective records. They live as **subjective per-participant memory**. Two participants of the same conversation may remember different facts/emphasis. **This is feature, not bug** — matches real human cognition.

This reframing solves three problems simultaneously:
- LLM context cost scales with **engagement**, not population
- Privacy is automatic (closed sessions can't be eavesdropped)
- Memory model aligns with cognitive reality (subjective, lossy, distilled)

---

## §2 — The big shift: ambient cell + sparse sessions

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
    ├── Session C: PC₁ + PC₃ (whisper privately) — V2+ same-cell-different-session
    │
    └── ... up to soft cap (DF5-A8) per cell
```

**Old model (REJECTED):**
- 1 cell → 1 session per (PC, cell) → all cell actors auto-join → context bloat
- Multi-PC visibility default → privacy violation
- Lifecycle complex (Active/Idle/Frozen/Closed)

**New model (LOCKED via §1.2):**
- 1 cell → M concurrent sessions (sparse) → only explicitly-engaged actors join
- Per-session privacy default → conversation isolation
- Lifecycle simple (Active/Closed)
- Closed → data flushes to per-actor subjective memory
- No reopen; no objective record

---

## §3 — Lifecycle (radically simplified V1)

```
                    PC opens chat with target(s)
                    /chat @alice @bob OR click NPC
                              │
                              ▼
                       ┌──────────────┐
                       │ SessionBorn   │
                       │ EVT-T3 Derived│ (runtime PC-trigger)
                       │ (canonical    │  OR EVT-T4 (canonical seed)
                       │  seed V1+)    │
                       └──────┬────────┘
                              ▼
                     ┌─────────────────┐
                     │     Active      │  turn-take loop
                     │  (PCs + NPCs    │  (PL_005 Interaction grain;
                     │   interact)     │   each turn = 1 EVT-T1 Submitted)
                     └────────┬────────┘
                              │
                              │ DF5-A4 trigger:
                              │ last PC leaves session
                              ▼
                  ┌─────────────────────┐
                  │ ClosingTransition    │  EVT-T3 Derived
                  │ + per-actor POV      │  EVT-T6 Proposal × N (one per participant)
                  │   LLM distill        │  EVT-T3 Derived × N (memory writes)
                  └────────┬─────────────┘
                           ▼
                     ┌─────────────────┐
                     │     Closed      │  TERMINAL V1 — session aggregate
                     │  (immutable)    │  becomes archival metadata only;
                     └────────┬────────┘  no participant_writes after this
                              │
                              │ Future read paths:
                              ▼
                actor_session_memory[actor, session_id]
                ↑ each participant has subjective record
                ↑ cannot reopen session for "objective truth"
                ↑ POV may differ between participants (intentional)
                ↑ ACT_001 R8 bounded LRU + cold-decay
```

**V1 = 2 states only** (Active, Closed). Removed Idle/Frozen from initial proposal.

**V1+30d additions:**
- Idle state (auto-detect after N turns no PC activity → memory flush + close earlier)
- Wall-clock timeout (24h disconnect → forced close)

**V2+ additions:**
- Frozen state (Forge or DF4 explicit pause)
- NPC-only continuation (V2+ NPC-NPC autonomous chat per DF1 daily life)

---

## §4 — Data flow on close (the critical mechanism)

```
Close trigger detected (DF5-A4: last PC leaves session_participation)
   ↓
1. session.state = Closed; closed_fiction_time = now; close_reason = LastPcLeft
   ↓
2. EVT-T3 Derived emitted: session ClosingTransition
   { session_id, participants: [...], turn_count, channel_id }
   ↓
3. For each participant_actor in session_participation (where left_fiction_time IS NOT NULL OR equals now):

      a. LLM POV-distill prompt:
         """
         Bạn là <actor.display_name>.
         Bạn vừa kết thúc cuộc trò chuyện với <other_participants>.
         Trong N turns vừa rồi (turn_summary briefly), có những fact gì
         đáng nhớ với BẠN từ POV của bạn?

         Output: JSON list of MemoryFact { kind, target?, verb, object?, salience }.
         3-5 facts max. Highest salience first.
         """

      b. LLM returns ~500 tokens JSON:
         [
           { kind: "social", target: "alice", verb: "showed_interest_in", object: "my_quest_offer", salience: 0.8 },
           { kind: "promise", target: "bob", verb: "agreed_to_meet", object: "tomorrow_market", salience: 0.9 },
           { kind: "tone", verb: "felt_warmly_received", salience: 0.5 }
         ]

      c. Append to actor_session_memory[actor_id, session_id] per ACT_001 §3.4:
         · R8 bounded LRU (max ~30 facts per (actor, session))
         · If exceed: rolling summary + drop lowest salience facts
   ↓
4. EVT-T3 Derived emitted: session ClosedTransition
   ↓
5. Aggregate post-state:
   · session row: archival metadata; no further participant writes
   · session_participation rows: all left_fiction_time populated; immutable
   · actor_session_memory rows: PRIMARY post-close access path
   · LLM context cache flushed (memory budget freed)
   ↓
6. ACT_001 R8 cold-memory decay applies over fiction-time (30d/90d/365d):
   · Eventually compacts to summary only
   · Eventually archives or purges per author rule
```

### §4.1 Why per-actor POV (not single objective summary)

| Property | Single objective summary | Per-actor POV (CHOSEN) |
|---|---|---|
| Token cost | 1 LLM call | N LLM calls (N participants) |
| Storage cost | 1 row | N rows |
| Replay determinism | 1 cache | N caches |
| Cognitive realism | Low (omniscient narrator) | High (each remembers differently) |
| Privacy | Same record visible to all | Each actor sees their own |
| Future references | "What did the session say?" | "What does Alice remember?" |
| Drift potential | Low | Moderate (LLM POV variance) |

**Trade-off accepted:** N× cost for cognitive realism + privacy + per-actor LLM persona prompt-assembly continuity. Cost cap: typical session 4 participants × ~500 tokens = 2K tokens on close. Cheap relative to session lifetime.

### §4.2 Replay-determinism preservation (Q12 PENDING)

LLM POV-distill is non-deterministic by default (temperature variance, model updates). Need to preserve EVT-A9.

**Proposed solution:** cache POV-summaries IN the EVT-T3 Derived commit data:

```rust
EVT-T3 Derived {
    aggregate_type: actor_session_memory,
    update_kind: SessionPovDistill,
    payload: {
        actor_id,
        session_id,
        facts: Vec<MemoryFact>,        // ← THE LLM OUTPUT, CACHED HERE
        llm_model_id: String,           // for audit
        prompt_template_version: u32,   // cache invalidator
        generated_at_fiction_time: FictionTime,
    }
}
```

On replay: read from event payload, do NOT re-call LLM. Same as CSC_001 §6 entity_zone_assignments cache pattern.

---

## §5 — Aggregate model

### 5.1 `session` (T2 / Reality, sparse — only Active sessions hot; Closed archival)

```rust
#[derive(Aggregate)]
#[dp(type_name = "session", tier = "T2", scope = "reality")]
pub struct Session {
    pub session_id: SessionId,                    // UUID v5(reality_id, channel_id, anchor_pc_id, started_fiction_time)
    pub reality_id: RealityId,
    pub channel_id: ChannelId,                    // anchor cell (DF5-A1 same-channel)
    pub state: SessionState,                      // Active | Closed
    pub started_fiction_time: FictionTime,
    pub closed_fiction_time: Option<FictionTime>,
    pub turn_count: u32,
    pub close_reason: Option<CloseReason>,        // populated on close
    pub anchor_pc_id: ActorId,                    // creator PC (DF5-A4 anchor invariant)
}

pub enum SessionState {
    Active,     // V1
    Closed,     // V1 — terminal
    // Idle / Frozen / Resumed — V1+30d / V2+
}

pub enum CloseReason {
    LastPcLeft,                  // V1 default — anchor invariant
    AllParticipantsLeft,         // edge case (PC + NPC both move out)
    ForgeClose,                  // V1 admin
    SessionTimeoutWallClock,     // V1+30d
    RealityClosed,               // EM-7 cascade
}
```

**Storage discipline:**
- Active sessions: hot row, indexed by (channel_id, state=Active) for cell-wide queries
- Closed sessions: cold row, archival; future TTL or migrate to `closed_session_archive` aggregate V2+
- No `summary` field — moved to per-actor `actor_session_memory`

### 5.2 `session_participation` (T2 / Reality, sparse per (session, actor))

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
}

pub enum ParticipantRole {
    Anchor,     // PC who created session
    Joined,     // joined later (PC walks in V2+; NPC accepted /chat invite)
}

pub enum LeftReason {
    Explicit,           // /leave or close-chat UI
    MovedCell,          // cascade from PL_001 §13 travel
    Inactive,           // V1+30d auto-detect
    SessionClosed,      // cascade
    AnchorPcLeft,       // when last anchor PC leaves → all NPCs forced out
    Kicked,             // V1+ Forge or DF4 rule
}
```

### 5.3 `actor_session_memory` (already in ACT_001 §3.4 — RE-ROLE)

Old role: "during-session memory accumulation"
**New role: PRIMARY post-close persistence — subjective per-actor record**

ACT_001 R8 bounded LRU + cold-decay already designed for exactly this pattern. **No reopen of ACT_001 needed**.

R8 invariants directly applicable:
- Max ~30 facts per (actor, session)
- Rolling summary + drop oldest specific facts on overflow
- Cold-memory decay: 30d/90d/365d fiction-time compaction
- Retention: 1y default, 5y for "important" sessions (V1+30d)

---

## §6 — Invariants DF5-A1..A11

| ID | Invariant | Why |
|---|---|---|
| **DF5-A1 (Same-channel)** | All session participants ∈ exactly same channel_id at any moment | TDIL-A5 atomic-per-turn travel |
| **DF5-A2 (Container, not single event)** | Session = aggregate; turn-events fire WITHIN session at PL_005 grain | Replay-determinism + scalability |
| **DF5-A3 (Time-flow inheritance)** | Session inherits channel time_flow_rate; per-turn fiction_clock advance follows TDIL | TDIL-A6 per-realm turn streams |
| **DF5-A4 (PC anchor invariant)** | Active session MUST have ≥1 PC. Last PC leaves → auto-close cascade | Avoid NPC-only ghost sessions; AIT scaling discipline |
| **DF5-A5 (One Active per actor)** | Any actor (PC or NPC) ∈ ≤1 Active session at a time | UI sanity + LLM context lifecycle clarity |
| **DF5-A6 (Tier eligibility)** | Session participants ∈ {PC, Major NPC, Minor NPC}. Untracked NPC = NOT eligible | AIT-A8 capability matrix |
| **DF5-A7 (Closed = immutable)** | After Closed transition, no session_participation writes; session aggregate frozen except archival queries | Memory ownership integrity |
| **DF5-A8 (Per-cell soft cap)** | ≤50 Active sessions per cell V1 | Prevent runaway; matches AIT density discipline |
| **DF5-A9 (Memory distill on close)** | Each participant gets POV-summary written to actor_session_memory; cached in EVT-T3 commit data | Lossless from participant POV; no reopen for "objective truth" |
| **DF5-A10 (No cross-session leak)** | Session A's content NOT readable by session B participants | Privacy + real-world parallel; LLM context isolation |
| **DF5-A11 (Replay deterministic)** | Session state derivable from EVT-T1 + EVT-T3 stream filtered by session_id; POV-distill cached | EVT-A9 |

---

## §7 — Edge cases (resolved in §1.2 framing)

### 7.1 PC switches conversation

```
1. PC enters tavern cell (ambient: 30 NPCs, 0 sessions).
2. PC /chat @alice @bob → SessionA created. Participants {PC, alice, bob}. State=Active.
3. PC chats 5 turns. actor_session_memory[*, A] grows during session via in-session reads.
4. PC issues /chat @carol @dan (different group):
   a. PC marked left in SessionA (DF5-A5 enforce: 1 active per actor).
   b. SessionA participant check: PC was only PC → DF5-A4 triggers close cascade.
   c. SessionA close cascade: LLM POV-distill × 3 (PC, alice, bob).
   d. alice + bob → ambient (NPC at cell, no session).
   e. SessionB created. Participants {PC, carol, dan}.
5. SessionB independent of SessionA.
6. Future: PC reads actor_session_memory; sees SessionA + SessionB facts separately tagged by session_id.
```

### 7.2 Two PCs in same cell, separate conversations

```
PC1 in SessionA with alice. PC2 in SessionB with bob. Same cell.
→ DF5-A10 enforces no cross-session visibility.
→ AIT context: 4 LLM-context slots used (alice + bob + persona for both PCs).
→ 28 ambient NPCs cost ~0 (just density check).
→ Real-world parallel: 2 conversations at the tavern. Both happen.
```

### 7.3 NPC busy with one session, PC tries to engage

```
NPC alice ∈ SessionA. PC2 issues /chat @alice (PC2 ∈ different session B or no session).
→ DF5-A5 violation predicted at engage-time.
→ Reject `session.actor_busy_in_other_session`.
→ Hint: "Alice đang nói chuyện với người khác."
→ PC2 may wait (poll), or choose another target.
V2+: alice's Major NPC desire system may auto-leave SessionA if PC2 reputation/desire-match better. Out of V1.
```

### 7.4 PC tries to chat Untracked NPC

```
PC /chat @untracked_villager_3 (or click an Untracked-tier NPC).
→ DF5-A6 violation. Reject `session.actor_not_eligible_untracked`.
→ Hint to user: "Bạn có thể Examine họ, nhưng để chat sâu cần promotion (admin only)."
V1+30d: AIT-D7 LLM-propose-promotion → if PC engagement signal strong, propose Untracked → Tracked Minor.
```

### 7.5 PC moves cell during active session

```
PC ∈ SessionA at cellX. PC issues /travel destinationY.
→ PL_001 §13 travel commits.
→ Cascade: SessionParticipation(PC, SessionA) marked left, reason=MovedCell.
→ DF5-A4 check: PC was only/last PC → SessionA closes.
→ Close cascade fires (LLM POV-distill × all participants).
→ PC arrives cellY (ambient — 0 sessions yet).
```

### 7.6 NPC-only continuation (V1: NO; V2+: optional)

```
PC + alice + bob in SessionA. PC leaves.
V1: SessionA closes immediately per DF5-A4.
V2+: per-reality DF4 rule "ambient_npc_drama_enabled":
     SessionA continues with alice + bob NPCs autonomously.
     Used for DF1 daily life NPC-NPC drama.
     No PC = no LLM-context cost; uses Minor scripted templates.
     Closes when NPCs drift apart (different cells / reaction triggers).
```

### 7.7 Reality close cascade

```
Reality enters EM-7 close lifecycle.
→ All Active sessions in reality cascade-close.
→ For each: close_reason = RealityClosed; LLM POV-distill skipped (cost-saving for closing reality).
→ actor_session_memory writes: brief "Reality ended" placeholder fact only.
→ Reality archive captures session metadata for replay-only access.
```

### 7.8 Forge close-session

```
Author/admin issues Forge:CloseSession{session_id} via WA_003.
→ EVT-T8 AdminAction.
→ close_reason = ForgeClose.
→ Standard close cascade fires (LLM POV-distill × participants).
→ session_participation marked left, reason=Kicked (audit trail).
```

---

## §8 — Event mapping (per 07_event_model)

| Event | EVT-T* | Sub-type | Producer |
|---|---|---|---|
| Session born — runtime PC-trigger | **EVT-T3 Derived** | `aggregate_type=session` Born | session-service (PL_002 /chat command) |
| Session born — canonical seed (V1+ author scripted) | **EVT-T4 System** | `SessionBorn { session_id, channel_id, anchor_pc_id }` | RealityBootstrapper |
| Actor joins session | **EVT-T3 Derived** | `aggregate_type=session_participation` Born | session-service |
| Actor leaves session | **EVT-T3 Derived** | `aggregate_type=session_participation` Update (LeftTransition) | session-service |
| PC takes turn | **EVT-T1 Submitted** | `PCTurn` (existing PL_005) | client → world-service |
| NPC turn (Chorus selects responder) | **EVT-T1 Submitted** | `NPCTurn` (existing PL_005) | NPC_002 Chorus → world-service |
| Turn cascades (mood / opinion / status / location) | **EVT-T3 Derived** | various existing | aggregate owners |
| Session closing transition | **EVT-T3 Derived** | `aggregate_type=session` ClosingTransition | session-service (anchor leave detected) |
| Per-actor POV memory distill | **EVT-T6 Proposal** + **EVT-T3 Derived** | `actor_session_memory` Update with cached POV facts | session-service via LLM |
| Session closed | **EVT-T3 Derived** | `aggregate_type=session` ClosedTransition | session-service |
| Forge admin actions | **EVT-T8 AdminAction** | `Forge:CloseSession` / `Forge:KickFromSession` / `Forge:CreateSession` | WA_003 |
| Reality close cascade | **EVT-T3 Derived** | session ClosedTransition (CloseReason=RealityClosed) | EM-7 cascade |
| Wall-clock timeout sweep (V1+30d) | **EVT-T5 Generated** | `Scheduled:SessionTimeoutSweep` | meta-worker per channel |

**No new EVT-T* category required.** Maps onto existing 07_event_model taxonomy.

---

## §9 — V1 scope cut

| Feature | V1 | V1+30d | V2 | V3 |
|---|---|---|---|---|
| **PC creates session via /chat @actor** | ✅ | | | |
| **PC click NPC → 1-on-1 session** | ✅ | | | |
| **PC creates multi-actor session** (`/chat @a @b @c`) | ✅ | | | |
| **Auto-close on last PC leave** (DF5-A4) | ✅ | | | |
| **Per-actor POV memory distill on close** | ✅ | | | |
| **Per-cell session capacity cap** (DF5-A8) | ✅ | | | |
| **Multiple concurrent sessions per cell** | ✅ | | | |
| **Active/Closed lifecycle** | ✅ | | | |
| **Untracked NPC eligibility reject** | ✅ | | | |
| **Cell-leave cascade** | ✅ | | | |
| **NPC-busy-elsewhere reject** | ✅ | | | |
| **Solo monologue session** (PC + 0 NPCs, V1 Q2) | ✅ | | | |
| **NPC consent gate** (Major NPC reject if hostile rep, V1 Q4) | ✅ | | | |
| **Idle state** (auto-detect inactive session) | | ✅ | | |
| **Wall-clock timeout** (24h disconnect → forced close) | | ✅ | | |
| **Per-tier customized POV-distill prompt** | | ✅ | | |
| **Multi-PC join existing session** (PC2 joins PC1's session) | | | ✅ | |
| **Whisper** (1-to-1 within larger session) | | | ✅ | |
| **PvP** (consent flow per DF4) | | | ✅ | |
| **NPC initiates session** (NPC walks to PC because of desire) | | | ✅ | |
| **Frozen state** (Forge or DF4 explicit pause) | | | ✅ | |
| **Resume closed session** | | | | ✅ |
| **NPC-NPC autonomous session** (DF1 daily life) | | | | ✅ |
| **Cross-cell session cluster** (PC moves to neighbor cell, session follows) | | | | ❓ |
| **Public broadcast** (PC stands up, shouts to cell) | | | | ❓ (may not need; one-off event suffices) |

---

## §10 — Q1-Q12 LOCKED matrix (4-batch deep-dive 2026-04-27)

**Status: ALL LOCKED 2026-04-27** via 4-batch deep-dive (mirror PROG/AIT/TDIL/COMB pattern):
- **Batch 1** (Q1+Q2+Q3): Session entry mechanics — user "approve"
- **Batch 2** (Q4+Q7+Q9): NPC behavior + memory dynamics — user "approve"
- **Batch 3** (Q5+Q8+Q12): Memory mechanics — user "approve"
- **Batch 4** (Q6+Q10+Q11): Operational concerns — user "approve"

### §10.1 — Batch 1: Session entry mechanics

**Q1 LOCKED [B1]:** Session creation grammar — Both CLI + GUI V1.
- `/chat @actor [@actor...]` PL_002 Grammar command (power-user; multi-actor)
- Click-to-talk UI gesture (CC-1 Chat GUI extension; discovery-friendly)
- Q1-D1: GUI NOT deferred — both ship V1

**Q2 LOCKED [B1]:** Solo monologue (0 NPC participants) — YES V1 allow.
- Use cases: journal mode, PCS_001 body_memory recall (xuyên không SoulPrimary), pre-action planning, training rehearsal
- Q2-D1: NO cost discount for monologue (normal token budget Q8)
- Q2-D2: Skip POV-distill if `turn_count < 3` (no meaningful content threshold)

**Q3 LOCKED [B1]:** Max participants per session V1 cap = **8** (inclusive of PC anchor).
- Rationale: tavern table seats 4-6 realistic; council 8 max; LLM context budget fit
- Q3-D1: Reject rule_id `session.participant_cap_exceeded` for 9+ attempts
- Q3-D2: Cap inclusive of PC anchor (1 PC + 7 NPCs = 8)
- Q3-V2+: Larger groups (20+) = SEPARATE "ASSEMBLY" feature V2+ (links to ORG_001); NOT bumped DF5 cap

### §10.2 — Batch 2: NPC behavior + memory dynamics

**Q4 LOCKED [B2]:** NPC consent — YES V1 reputation-gated refusal.
- Q4-D1 LOCKED: **Hated + Hostile** tiers REJECT /chat invite. Unfriendly accepts reluctantly with `mood=Sour` despite acceptance.
- Q4-D2 LOCKED: **Personal opinion (ACT_001 actor_actor_opinion) overrides faction reputation** — alice with Hostile faction rep but +80 personal opinion accepts (with conflict surfaced in persona prompt).
- Q4-D3 LOCKED: **LLM-flavored refusal message + engine template fallback** if LLM budget exhausted (sub-tier Sour/Hostile/Hated → 1-of-N hardcoded phrases per (mood, reputation_tier)).
- Q4-D4 LOCKED: **No per-NPC cooldown V1; rely on PL_002 grammar-layer rate-limit** for spam prevention.

**Q7 LOCKED [B2]:** Cross-session memory bleed — YES V1.
- Persona prompt assembly reads ALL past sessions for actor (R8 bounded LRU); not session-isolated
- Q7-D1 LOCKED: **NO cross-reality memory bleed V1** — reality is hard isolation (TDIL atomic-channel + DP T2 Reality scope). Defer to V2+ knowledge-service bridge.
- Q7-D2 LOCKED: **Top-K=10-20 facts by salience score across all sessions** (sorted by salience desc; not chronological)
- Q7-D3 LOCKED: **NO faction filter V1** — alice's memories flat (privacy via DF5-A10 cross-session-leak prevention; not memory partitioning)
- Q7-D4 LOCKED: **ACT_001 R8 cold-decay 30/90/365 fiction-day cadence confirmed** (already locked via ACT_001)

**Q9 LOCKED [B2]:** TDIL clock interaction — NO direct effect; session orthogonal.
- Q9-D1 LOCKED: **Per-turn fiction_duration source = PC-proposed via PL_005 + engine default fallback** (matches existing PL_005 pattern)
- Q9-D2 LOCKED: **Actor body/soul clocks during session unchanged** — same as outside session; clocks orthogonal to session presence
- Q9-D3 LOCKED: **NO time_flow_rate override** — channel rate authoritative per TDIL-A6; session inherits, cannot override

### §10.3 — Batch 3: Memory mechanics

**Q5 LOCKED [B3]:** POV-distill prompt template — Single template V1.
- Q5-D1 LOCKED: **Full turn history as prompt input** (8-cap participants × ~20 turns max = ~800-1500 input tokens; acceptable)
- Q5-D2 LOCKED: **JSON Schema validated output + 3-retry feedback loop** (mirror PoC tilemap pattern; same approach proven)
- Q5-D3 LOCKED: **3-5 facts cap per distill** (LLM picks within range; highest salience first)
- Q5-D4 LOCKED: **LLM self-scores salience 0.0-1.0** (engine post-scoring V1+30d if drift observed)
- Q5-D5 LOCKED: **I18nBundle vi+en** (matches RES_001 cross-cutting i18n contract; supports CC-2 multilingual)
- Q5-D6 LOCKED: **Placeholder fallback on LLM fail (3-retry exhausted)** — `{ kind: tone, verb: I18nBundle("had a conversation"), salience: 0.3 }` ensures actor has minimal record (better than empty)
- Per-tier customization (Major elaborate / Minor terse) **deferred V1+30d**

**Q8 LOCKED [B3]:** Session token budget — ~3K context per active turn.
- Q8-D1 LOCKED: **Soft cap with priority dropping** (exceeds → drop low-priority blocks; do NOT reject turn submission)
- Q8-D2 LOCKED: **Per-tier customization** per `103_PLATFORM_MODE_PLAN.md`:
  - Free: 2K total / condensed persona ~400 / top-5 memories / last 8 turns
  - Paid: 3K total / full persona ~700 / top-15 memories / last 12 turns
  - Premium: 5K total / rich persona ~1000 / top-30 memories / last 20 turns
- Q8-D3 LOCKED: **Drop priority order**: (1) older recent turns first [keep last 5 always] → (2) low-salience memories <0.5 → (3) session summary [regenerable]; **NEVER drop**: (4) persona block / (5) world rules / (6) system prompt
- Q8-D4 LOCKED: **Per-actor budget** — each actor's turn uses their own context budget (per DF5-A10 isolation; no shared pool)

**Q12 LOCKED [B3]:** Replay-determinism via POV-distill cache.
- Q12-D1 LOCKED: **Full JSON V1 (no compression)** — ~500-1000 bytes per distill; storage acceptable
- Q12-D2 LOCKED: **Cache invalidation on:**
  - `prompt_template_version` mismatch (engine schema upgrade) — flag for regen
  - `llm_model_id` deprecated (model retired) — optional regen
  - `Forge:RegenSessionDistill` admin-triggered (V1 manual)
- Q12-D3 LOCKED: **Replay reads from EVT-T3 cache in event_log (canonical source)** per EVT-A9; aggregate is materialization, not authoritative
- Q12-D4 LOCKED: **Provenance fields**: `llm_model_id` + `prompt_template_version` + `generated_at_fiction_time` + `generated_at_wall_time` + `attempt_count` + **`provider_id`** (NEW V1: lmstudio/openai/anthropic/etc. for audit completeness)
- Q12-D5 LOCKED: **Storage projection acceptable** — typical wuxia kingdom ~500MB-2GB per reality; V1+30d compression reconsider if pain point

### §10.4 — Batch 4: Operational concerns

**Q6 LOCKED [B4]:** Closed session aggregate retention — Unlimited V1.
- Q6-D1 LOCKED: **Unlimited retention V1** + manual purge via Forge (matches small storage profile; ~200B per session row)
- Q6-D2 LOCKED: **Single hot tier V1** (Postgres); cold archive V2+
- Q6-D3 LOCKED: **`closed_session_archive` aggregate V2+** (T3/Reality cold tier; Postgres metadata + MinIO blob for full event subset)
- Q6-D4 LOCKED: **GDPR per-actor erasure** — PC delete → all `actor_session_memory[pc_id, *]` rows purged + `session_participation[*, pc_id]` marked deleted_for_user; OTHER actors' POV facts retain (no cascade reality state damage); plus `Forge:AnonymizePcInSessions` replaces PC name in OTHER actors' memories with "kẻ lạ"
- Q6-D5 LOCKED: **Death = freeze not delete** — actor_session_memory frozen at death fiction_time; sessions accessible by Forge audit only; retention same as alive
- V1+30d: auto-TTL after 1 fiction-year if storage profile shows pain
- V2+: archive aggregate for cold storage

**Q10 LOCKED [B4]:** Cell-leave grace period — 30 wall-seconds for disconnect ONLY.
- Q10-D1 LOCKED: **Differentiated trigger handling**:
  - PC `/travel` to different cell → instant session-leave (DF5-A6 cell-leave cascade)
  - PC `/leave` command → instant session-leave (explicit)
  - WebSocket disconnect (network/crash) → **30 wall-second grace before leave**
  - Browser tab close → same as disconnect (30s grace)
- Q10-D2 LOCKED: **NEW field on `session_participation`**:
  ```rust
  pub presence: PresenceState,                    // V1: connected | disconnected | left
  pub disconnect_at_wall_time: Option<WallTime>,  // populated on Disconnected
  pub enum PresenceState { Connected, Disconnected, Left }
  ```
- Q10-D3 LOCKED: **Multi-PC presence design clean for V2** — V1 solo-PC works; PresenceState extends naturally
- Q10-D4 LOCKED: **Forge can override grace** — `Forge:KickFromSession { actor_id, force=true }` skips 30s timer (abuse mitigation)
- Q10-D5 LOCKED: **Wall-clock 30s, NOT fiction-time** — disconnect = real-world infra event; wall-clock semantic

**Q11 LOCKED [B4]:** Forge admin memory edit — Pre-close YES; post-close NO direct edit.
- Q11-D1 LOCKED: **Pre-close (in-session Active) edits ALL OK V1**:
  - `Forge:EditActorSessionMemory { actor_id, session_id, edit_kind, before, after }` — add/remove/modify/salience-adjust facts; modify i18n strings
  - Reason: pre-distill memory mutable; author has full control during active session
- Q11-D2 LOCKED: **Post-close edit policy**:
  - **NO direct fact edit** — preserves "subjective truth" invariant
  - **YES allowed**: `Forge:RegenSessionDistill { session_id }` (re-run LLM POV-distill, e.g., after prompt template upgrade) + `Forge:PurgeActorSessionMemory { actor_id, session_id }` (GDPR or correction)
- Q11-D3 LOCKED: **GDPR erasure path** — `Forge:PurgeActorSessionMemory` bulk + `Forge:AnonymizePcInSessions` (replace PC name with "kẻ lạ" in others' memories); audit trail in `forge_audit_log` (cannot delete audit layer)
- Q11-D4 LOCKED: **Bulk operations scoped to reality_id**:
  - `Forge:BulkRegenSessionDistill { reality_id, session_filter, prompt_template_version }`
  - `Forge:BulkPurgeStaleSessions { reality_id, before_fiction_time }`
- Q11-D5 LOCKED: **Full audit per WA_003 standard** — every Forge memory operation emits EVT-T8 Administrative; logged with who_edited (UserId) + when (wall + fiction time) + before/after snapshot + reason text; retained per WA_003 audit policy
- Q11-D6 LOCKED: **Player invisible V1** — Forge edits do NOT surface to player; transparency feature deferred V1+30d

### §10.5 — Catalog ID assignment (deferred to DRAFT promotion)

When DF5 promotes to DRAFT, mint stable IDs per §11 closure-pass impact:
- `DF5-1` through `DF5-N` for catalog entries (V1 + V1+30d + V2+)
- `DF5-A1..A11` invariants (already proposed §6)
- `DF5-D1..DN` per-feature deferrals
- `DF5-Q*` if any closure-pass reopens (none expected per concept-notes)
- `DF5-V1..V*` validator slots
- `session.*` RejectReason namespace (~12 V1 rule_ids: `session.participant_cap_exceeded` / `session.actor_not_eligible_untracked` / `session.actor_busy_in_other_session` / `session.npc_refused` / `session.cell_session_overload` / `session.invalid_state_transition` / etc.)

---

## §11 — Closure-pass impact (cross-feature)

DF05 design will trigger closure-pass-extensions on the following features. Magnitude estimated:

| Feature | Closure-pass scope | Magnitude |
|---|---|---|
| **PL_002 Grammar** | Add `/chat`, `/leave`, `/whisper` (V2) command surface | LOW |
| **PL_005 Interaction** | Reference session_id in PCTurn / NPCTurn; verify session-aware validators | LOW-MEDIUM |
| **NPC_001 Cast** | NPC eligibility check (tier + busy-elsewhere) at /chat invite; reject reasons; persona-assembly switches to MemoryProvider trait | MEDIUM |
| **NPC_002 Chorus** | Chorus already turn-orders within session; verify multi-PC interaction V2+; uses MemoryProvider for tier-aware persona | LOW |
| **NPC_003 Desires** | Desire-driven NPC join/leave V2+; V1 read-only | LOW |
| **ACT_001** | actor_session_memory R8 — verify post-close write path; POV-distill cache shape; backend implementation choice (LruDistillProvider) | MEDIUM |
| **REP_001** | NPC consent reputation threshold (Q4) — wuxia tier display name reuse | LOW |
| **WA_003 Forge** | Add Forge:CloseSession, Forge:CreateSession, Forge:KickFromSession AdminAction sub-shapes | LOW |
| **WA_006 Mortality** | PC dies in session → SessionParticipation.left_reason=Killed (V1+30d if combat in session) | LOW |
| **AIT_001** | Verify Untracked rejection path; tier capacity coordination with session capacity (DF5-A8 vs AIT-A5); MemoryProvider capability gate for tier-aware retrieval | LOW-MEDIUM |
| **PCS_001** | PC body_memory feeds prompt-assembly for session turns; per-PC active-session lookup pattern; consumes MemoryProvider trait | MEDIUM |
| **PL_001 Continuum** | session lifecycle hooks at cell-enter / cell-leave; cell-leave cascade in §13 travel sequence | MEDIUM |
| **PF_001 Place** | Cell-tier session capacity tracking; cell display "5 active conversations" | LOW |
| **EM-7 Reality Close** | Cascade sessions to ClosedTransition with reason=RealityClosed; skip POV-distill for cost-saving | LOW |
| **07_event_model** | Register `aggregate_type=session` + `session_participation` EVT-T3 sub-types; SessionBorn EVT-T4 | LOW (additive) |
| **RealityManifest** | OPTIONAL `canonical_sessions` (V1+ author-scripted set-piece sessions); `session_capacity_overrides` per channel | LOW |

**NEW V1 contract directory** (per §15 SDK architecture):
- `contracts/api/session/v1/` — `session_service.rs` + `memory_provider.rs` + `dto.rs` + `query.rs` + `errors.rs` + `capabilities.rs` + `contract_tests.rs` + OpenAPI specs
- `contracts/api/session/_CHANGELOG.md` — version history

**NEW V1 service** (per §15):
- `services/session-service/` — implementation with `adapters/lru_distill.rs` (V1 primary) + `adapters/shadow_read.rs` + `adapters/dual_write.rs` migration helpers + feature_flags.rs

**Total closure-pass-extension scope: 16 features touched + 2 new directories.** Most LOW magnitude. No CANDIDATE-LOCK reopens expected (additive only). Single combined boundary commit feasible.

---

## §12 — Reference games / prior art

To inform design choices during deep-dive:

### Group chat / conversation UX
- **Discord** — channels (≈ cells), per-channel multiple "threads" (≈ sessions); thread participants + visibility model
- **Foundry VTT (TTRPG)** — scene/encounter granularity; whispers; roll20 conversation log; session = encounter
- **AI Dungeon** — single-thread persistence; no multi-session per "world"
- **NovelAI** — per-conversation memory; lorebooks span conversations; relevant for V1 memory distill design
- **SillyTavern** — group chat with N character cards; turn order + auto-respond; relevant for Chorus integration

### Memory/POV models
- **Disco Elysium** — internal monologue (Thought Cabinet) ≈ solo session V1 Q2
- **Mass Effect codex** — entries unlocked per encounter; per-actor knowledge
- **Persona 5 Confidants** — per-NPC relationship narrative state; ≈ actor_session_memory cumulative
- **CK3 character memory** — per-character event memory; decays + colors interactions; ≈ DF5-A9 close-time distill

### Multi-actor turn-taking
- **BG3 dialogue** — single PC chooses; party members chime in via reactions; ≈ V2+ multi-PC join
- **Pillars of Eternity** — companion banter; ≈ V2+ NPC-NPC autonomous (DF1 daily)
- **Wartales / Battle Brothers** — squad voiced lines on action; ambient companion chatter
- **EVE Online corp chat** — channel + windowed conversations ≈ multi-session-per-cell pattern

---

## §13 — Concept-notes file hygiene

- **Author:** main session 2026-04-27 (post-PoC tilemap LLM v3 session)
- **Origin commit:** TBD (concept-notes phase, no boundary lock yet)
- **Creates new files:**
  - `features/DF/DF05_session_group_chat/00_CONCEPT_NOTES.md` (this file)
- **Modifies:**
  - `features/DF/DF05_session_group_chat/_index.md` — status Placeholder → CONCEPT
- **Does NOT touch:**
  - `_boundaries/` files (no lock claimed)
  - Other catalog files (no IDs minted yet — DF05-* deferred to DRAFT)
  - SESSION_PATCH.md (concept-notes doesn't gate phase)
- **Blocks:**
  - Nothing — exploratory; main session can continue PoC tilemap or other work
- **Unblocked by:** none — promotion gate only requires Q1-Q12 LOCKED + boundary lock free
- **Estimated time to DRAFT (post-Q-deep-dive):** ~6-8 hours combined (single feature spec ~700-900 lines + 16 closure-pass-extensions mechanical)

---

## §15 — SDK Architecture (locked 2026-04-27)

**Decision context:** During concept-notes phase, user raised architectural concern (2026-04-27):

> "có cách nào để thiết kế dạng SDK
> nếu chúng ta sai thì sau này rework phần memory bên dưới không phá vỡ cấu trúc tích hợp bên trên không?"

**Decision LOCKED:** YES — DF05 ships as **versioned SDK contract + swappable backend implementations** (mirror Tokio runtime traits / Hibernate JPA / Spring Data pattern). Consumers depend ONLY on the contract; backends implement the contract; rework backend without touching consumers.

### §15.1 Three-layer architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│ CONSUMERS (NEVER import implementation)                                │
│ · NPC_001/002 persona prompt assembly                                  │
│ · PCS_001 body_memory continuation                                     │
│ · WA_003 Forge admin moderation                                        │
│ · Future: Memory UI, analytics, cross-reality bridge                   │
└──────────────────────────────┬────────────────────────────────────────┘
                               │ STABLE SDK CONTRACT (versioned)
                               │ contracts/api/session/v1/
                               ▼
┌───────────────────────────────────────────────────────────────────────┐
│ MEMORY SDK CONTRACT                                                    │
│ · SessionService trait (lifecycle ops)                                 │
│ · MemoryProvider trait (read ops)                                      │
│ · Versioned DTOs (PersonaContextBlock, MemoryFactView, ...)           │
│ · MemoryQuery DSL (no raw SQL/Cypher leak)                            │
│ · ContractTestSuite (~30 scenarios; every backend MUST pass)          │
│ · MemoryProviderCapabilities probe (graceful degradation)             │
└──────────────────────────────┬────────────────────────────────────────┘
                               │ implementation choice (swappable)
                               │ services/session-service/src/adapters/
                               ▼
┌───────────────────────────────────────────────────────────────────────┐
│ BACKENDS (interchangeable; rolled out via feature flags)               │
│                                                                       │
│ V1: LruDistillProvider                                                │
│     · Option A — close-distill, ACT_001 R8 LRU bounded                │
│                                                                       │
│ V1+30d: + SalienceTranscriptProvider (composite layer)                │
│         · Option C — opt-in raw blob for high-salience sessions       │
│                                                                       │
│ V2+: + KnowledgeServiceBridge (cross-reality user-level insight)      │
│      · Option B — knowledge-service integration                       │
│                                                                       │
│ Future: + custom backends (perfect-memory NPCs, archival, etc.)       │
└───────────────────────────────────────────────────────────────────────┘

ENFORCEMENT:
- Consumers in services/world-service/, services/api-gateway-bff/, etc.
  MUST import only from contracts/api/session/v1/
- CI lint rule: blocks PRs that import services/session-service/src/adapters/
  from outside services/session-service/
```

### §15.2 V1 SDK contract surface (locked scope)

#### SessionService trait (7 lifecycle ops)

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

#### MemoryProvider trait (4 read ops + capabilities probe)

```rust
#[async_trait]
pub trait MemoryProvider: Send + Sync {
    /// PRIMARY consumer entry — assemble persona context block for LLM prompt.
    /// Backend decides: distilled summary vs verbatim retrieval vs hybrid. Consumer doesn't know.
    async fn get_persona_context(&self, req: PersonaContextRequest) -> Result<PersonaContextBlock, MemoryError>;

    /// Structured query DSL — no raw SQL/Cypher leak.
    async fn query(&self, q: MemoryQuery) -> Result<MemoryQueryResult, MemoryError>;

    /// Audit/replay — uses canonical event log (any backend supports).
    async fn replay_session(&self, session_id: SessionId) -> Result<TurnStream, MemoryError>;

    /// Capability probe — caller asks "does this backend support feature X?".
    /// Lets consumers gracefully degrade when feature unavailable.
    fn capabilities(&self) -> &MemoryProviderCapabilities;
}

pub struct MemoryProviderCapabilities {
    pub supports_verbatim_replay: bool,         // Option C provides; A doesn't
    pub supports_semantic_similarity: bool,      // V2+ Option B provides
    pub supports_cross_reality_query: bool,      // V2+ knowledge-service bridge
    pub max_query_horizon: Duration,             // R8 cold-decay limit
    pub provider_version: String,                // for telemetry + audit
}
```

#### Versioned DTO (forward-compatible)

```rust
#[derive(Serialize, Deserialize, Clone)]
pub struct PersonaContextBlock {
    pub schema_version: u8,                       // = 1 V1
    pub actor_id: ActorId,
    pub target_actor_id: Option<ActorId>,
    pub recent_memories: Vec<MemoryFactView>,
    pub opinion: Option<OpinionView>,             // ACT_001 bilateral
    pub mood: Option<ActorMood>,                  // ACT_001 actor_core
    pub relevant_facts: Vec<FactView>,
    pub generated_at_fiction_time: FictionTime,
    pub provider_attribution: ProviderAttribution, // which backend(s) contributed
}

// Tolerant readers — V1 ignores unknown fields, allowing V2 backend additive expansion
#[derive(Deserialize)]
#[serde(deny_unknown_fields = false)]
struct PersonaContextBlockReader { /* V1 fields only */ }
```

#### MemoryQuery DSL (extensible without breaking V1 callers)

```rust
pub enum MemoryQuery {
    // V1 query types
    ByActorAboutTarget { actor_id, target, kinds, max_results },
    BySession { session_id, limit },
    ByActorRecentSessions { actor_id, since, limit },

    // V2+ additive (capability-gated; V1 backends reject with NotSupported)
    BySemanticSimilarity { actor_id, query_text, max_results },
    CrossRealityByUser { user_id, kind },
}
```

### §15.3 Migration playbook (5 patterns chống vỡ structure)

#### Pattern 1: Shadow-read (validate before switch)

```rust
pub struct ShadowReadProvider { primary, shadow, differ_log }

// Read serves from primary; shadow runs in parallel; differences logged
// Validate ≥99.5% match → switch primary → drop shadow
```

#### Pattern 2: Dual-write (migration window)

```rust
pub struct DualWriteProvider { old, new }

// Both backends receive writes; old result canonical until verification complete
// Drift logged; switch reads to new; drop old after stability period
```

#### Pattern 3: Versioned DTOs + tolerant readers

V1 consumers ignore unknown fields. V2 backend can return V2 fields. V1 still works.

#### Pattern 4: Capability-gated graceful degradation

```rust
let context = if provider.capabilities().supports_semantic_similarity {
    provider.query(MemoryQuery::BySemanticSimilarity { ... }).await?
} else {
    provider.query(MemoryQuery::ByActorAboutTarget { ... }).await?
};
```

V1 consumers KHÔNG biết V2 features tồn tại; chỉ dùng nếu probed available.

#### Pattern 5: Contract test suite (the firewall)

Every backend MUST pass the same suite:

```rust
// contracts/api/session/v1/contract_tests.rs

pub async fn run_session_service_contract<S: SessionService>(svc: S) {
    test_create_session_basic(&svc).await;
    test_pc_anchor_invariant_DF5_A4(&svc).await;
    test_one_active_per_actor_DF5_A5(&svc).await;
    test_untracked_rejected_DF5_A6(&svc).await;
    test_close_triggers_pov_distill(&svc).await;
    test_replay_determinism_after_close(&svc).await;
    test_per_cell_capacity_DF5_A8(&svc).await;
    test_no_cross_session_leak_DF5_A10(&svc).await;
    // ... ~30 scenarios covering DF5-A1..A11 + edge cases §7
}

#[test]
fn lru_distill_passes_v1_contract() {
    let svc = LruDistillProvider::test_fixture();
    run_session_service_contract(svc).await;
}

#[test]
fn salience_transcript_passes_v1_contract() {
    let svc = SalienceTranscriptProvider::test_fixture();
    run_session_service_contract(svc).await;
}
```

CI gate: PR không merge nếu contract test fail với bất kỳ backend nào registered.

### §15.4 What's locked V1 vs what's swappable

| LOCKED V1 (NOT abstracted) | ABSTRACTED V1 (swappable backend) |
|---|---|
| Session lifecycle states (Active/Closed) | Internal storage layout |
| DF5-A1..A11 invariants | Distillation timing (close vs lazy) |
| ACT_001 actor identity | Salience scoring algorithm |
| Reality scoping discipline | Embedding model choice |
| EVT-T1/T3/T4 event taxonomy | LRU eviction policy |
| Causality / replay determinism | POV-summary prompt template |
| Capability JWT model | Backend tech (Postgres aggregate vs Neo4j vs blob) |
| MemoryFactKind enum (closed) | Memory representation internals |
| DTO schema_version field | Index strategies / cache layer |

**Rule:** invariants + identity + scoping + events + DTO shape = **kernel-level discipline** (locked). Storage shape + algorithms = **implementation choice** (swappable per feature flag).

### §15.5 Mapping into LoreWeave structure

```
contracts/api/session/                          ← THE SDK (frozen V1)
├── v1/
│   ├── session_service.rs        # SessionService trait
│   ├── memory_provider.rs        # MemoryProvider trait
│   ├── dto.rs                    # PersonaContextBlock, MemoryFactView, ...
│   ├── query.rs                  # MemoryQuery DSL
│   ├── errors.rs                 # SessionError, MemoryError
│   ├── capabilities.rs           # MemoryProviderCapabilities
│   └── contract_tests.rs         # ~30 scenarios; both backends must pass
├── openapi/
│   ├── session_v1.yaml           # OpenAPI for HTTP/JSON consumers
│   └── memory_v1.yaml
└── _CHANGELOG.md                  # version history; breaking = major bump

services/session-service/                       ← THE IMPLEMENTATION
├── src/
│   ├── main.rs                   # boot; wires backends to traits
│   ├── adapters/
│   │   ├── lru_distill.rs        # V1 backend (Option A)
│   │   ├── salience_transcript.rs # V1+30d backend (Option C)
│   │   ├── knowledge_bridge.rs   # V2+ backend (Option B)
│   │   ├── shadow_read.rs        # migration helper
│   │   └── dual_write.rs         # migration helper
│   ├── routing.rs                # which backend serves which request
│   └── feature_flags.rs          # platform-mode rollout gate
└── tests/
    └── contract.rs               # imports contract_tests; runs all backends

services/world-service/src/persona_assembly/    ← CONSUMER (NPC_001/002)
└── prompt_builder.rs              # uses MemoryProvider trait, NOT impl
                                   # imports contracts::api::session::v1
                                   # CI lint: NEVER imports services::session_service::adapters
```

**CI lint rule (mandatory):** `services/world-service/`, `services/api-gateway-bff/`, `frontend/` must NOT import from `services/session-service/src/adapters/`. Only `contracts/api/session/v1/` allowed. CI fails build if violated.

### §15.6 Effort estimate

| Phase | Effort | Output |
|---|---|---|
| **V1 SDK definition** | 2-3 days | `contracts/api/session/v1/` ~600 LoC traits + DTOs + ~30 contract tests |
| **V1 Backend A (LruDistill)** | 1 week | `adapters/lru_distill.rs` ~800 LoC; passes contract suite |
| **V1 Consumer migration** | 2-3 days | NPC_001/002 prompt-assembly + PCS_001 body_memory + WA_003 admin all use trait |
| **V1+30d Backend C (Salience)** | 4-5 days | Composite provider + salience scoring + transcript blob storage |
| **V1+30d Migration validate** | 2 days | Shadow-read deploy + diff log analysis |
| **V2+ Bridge to knowledge-service** | 1-2 weeks | KnowledgeServiceBridge backend + cross-reality DTO V2 fields |
| **V1 Total** | ~2 weeks | working SDK + 1 backend + consumers migrated |

So với "no SDK" approach: V1 chỉ tốn thêm ~3-4 days cho contract definition. V1+30d / V2+ migrations rẻ hơn 10× (no rewrite of consumer code).

### §15.7 Risks + mitigations

| Risk | Mitigation |
|---|---|
| **Premature abstraction** (lock wrong concepts) | Start small: only 7 lifecycle ops + 4 read ops V1; consumer-driven additions; major version bump cho breaking changes (6-month overlap support); capability flags cho experimental features |
| **Implementation detail leak** (consumer references fields only 1 backend has) | CI lint rule blocks adapter imports outside service; DTO `provider_attribution` flags backend-specific fields; contract test suite must pass with ALL backends — leak phát hiện sớm |
| **Versioning maintenance overhead** | Tolerant readers (Pattern 3) → V1 consumer auto-works với V2 backend; 6-month overlap sunset; codemod tools cho migrations; single OpenAPI spec với `deprecated` annotations |
| **Backend wrong choice V1** | Easy revert: feature flag flip + drop adapter module; consumer code untouched; no migration needed for rollback |

### §15.8 Decision points (LOCKED 2026-04-27)

User confirmed via "approve" 2026-04-27. Defaults applied:

1. **SDK approach:** ✅ APPROVED — accept ~3-4 days extra V1 effort
2. **Contract location:** `contracts/api/session/` (LoreWeave convention; matches existing `contracts/api/knowledge/` pattern)
3. **Backend boundary:** `services/session-service/` (separate microservice; matches monorepo pattern)
4. **Capability probe granularity:** FINE-grained (`max_query_horizon: Duration`, individual feature booleans) — enables V2+ graceful degradation for arbitrary backend mixes
5. **Migration pattern V1 → V1+30d:** SHADOW-READ MANDATORY for `LruDistillProvider` → `SalienceTranscriptProvider` transitions; manual switchover not allowed; 1-week minimum shadow validation period before primary swap

**Open V2+ refinement:** add `MemoryProviderCapabilities.audit_retention` field (Duration) when V2 KnowledgeServiceBridge ships — different storage tiers have different retention contracts.

### §15.9 Cross-reference impact (added to §11)

This SDK architecture adds 2 NEW directories to closure-pass impact §11:

- `contracts/api/session/v1/` — 7 files (~600 LoC)
- `services/session-service/` — initial scaffold (V1 = lru_distill adapter + boot + tests)

Existing 16 features integration points unchanged — they switch from "direct import" to "trait import" but logic unchanged.

---

## §14 — Status footer

**Last updated:** 2026-04-27 (CONCEPT COMPLETE — all Q1-Q12 LOCKED + §15 SDK LOCKED + ready for DRAFT)

**Phase:** Concept-notes phase **CLOSED**. Concept brainstorm captured + 11 invariants proposed + **Q1-Q12 ALL LOCKED via 4-batch deep-dive 2026-04-27** + §15 SDK architecture LOCKED via user "approve" 2026-04-27.

**Promotion gate (to DRAFT):**
- ✅ Q1-Q12 ALL LOCKED via 4-batch deep-dive 2026-04-27 (Batch 1 / 2 / 3 / 4 each LOCKED via user "approve")
- ✅ `_boundaries/_LOCK.md` free (verified; main session can claim for DRAFT cycle)
- ✅ §15 SDK architecture LOCKED (5 decisions confirmed; defaults applied)
- ✅ §10 Q-LOCKED matrix authoritative for DRAFT spec
- ✅ §6 Invariants DF5-A1..A11 ready for catalog ID minting
- ✅ §11 Closure-pass impact mapped (16 features + 2 NEW directories `contracts/api/session/v1/` + `services/session-service/`)
- 🔓 **PROMOTION GATE FULLY MET** — main session can schedule DRAFT cycle

**Cross-feature DRAFT-time coordination (4-commit cycle expected; mirror TDIL/AIT pattern):**

1. **Phase 0** — Final concept review + commit `00_CONCEPT_NOTES.md` (this file) [COMPLETED 2026-04-27]
2. **Commit 1/4 — Q-LOCKED + boundary plan** — `[boundaries-lock-claim]` + author Phase 0 → Q-LOCKED matrix file
3. **Commit 2/4 — DRAFT promotion + boundary register** — `DF05_001_session_foundation.md` ~700-900 lines + boundary updates (`_boundaries/01_feature_ownership_matrix.md` adds session + session_participation aggregates + RealityManifest extensions + EVT-T sub-types + `session.*` RejectReason namespace + DF5-* stable-ID prefix; `_boundaries/02_extension_contracts.md` §1.4 adds session.* namespace V1 rule_ids + §2 adds RealityManifest extensions)
4. **Commit 3/4 — Phase 3 cleanup** — fix typos, expand thin sections, walkthrough AC scenarios
5. **Commit 4/4 — CANDIDATE-LOCK closure** — `[boundaries-lock-release]` + AC walkthrough complete + closure-pass-extensions plan locked
6. **Subsequent cascading commits** — 16 closure-pass-extensions on PL_002 / PL_005 / NPC_001..003 / ACT_001 / REP_001 / WA_003 / WA_006 / AIT_001 / PCS_001 / PL_001 / PF_001 / EM-7 / 07_event_model / RealityManifest
7. **Implementation phase** (post-DRAFT acceptance):
   - Create `contracts/api/session/v1/` directory + 7 files (per §15.5)
   - Scaffold `services/session-service/` initial structure (per §15.5)
   - CI lint rule: block consumer imports of `services/session-service/src/adapters/`
   - V1 backend `LruDistillProvider` implementation following §4 close-distill pattern
   - Contract test suite (~30 scenarios per §15.3 Pattern 5) MUST pass

**Next action:** Main session schedules DRAFT cycle execution. Estimated combined effort post-promotion gate: **~6-8 hours** (smaller than COMB/PROG due to most architecture already converged via concept-notes + SDK design).

**Risk callouts (final, post-LOCKED):**
- ✅ Q3 max participants cap (8) — V2+ assembly = separate feature confirmed; DF5 stays compact
- ✅ Q7 cross-session memory bleed semantics — confirmed feature, not bug; matches real-world cognition
- ✅ Q12 replay-determinism — POV-distill cache pattern locked + provider_id added; storage acceptable per Q12-D5 projection
- ⚠️ DF5-A6 Untracked exclusion — may surprise users when /chat @some_villager rejects; UX needs clear messaging in DRAFT spec §UX
- ⚠️ Memory distill on close fires N LLM calls atomically — may stutter UX on close; **explicitly deferred to V1+30d async background distill** per Q5-D6 placeholder fallback (immediate degraded path V1)
- ⚠️ §15 SDK premature abstraction — mitigated by start-small principle (7 + 4 ops V1) + consumer-driven additions
- ⚠️ §15 contract test suite scope — ~30 scenarios covering DF5-A1..A11 + edge cases §7; mandatory CI gate prevents backend regression
- 🆕 **Q11-D5 audit retention** — every Forge memory operation logged in `forge_audit_log`; cannot be deleted (audit-grade per WA_003) — note in DRAFT spec for compliance
- 🆕 **Q10-D5 wall-clock vs fiction-time** — 30s grace is wall-clock not fiction-time; document clearly in DRAFT spec to prevent confusion

**Architectural decisions LOCKED 2026-04-27 (final list):**
- §1.2 Multi-session-per-cell sparse model (vs initial single-session-per-cell rejected)
- §4 Close-time POV-distill primary mechanism (Option A core; Option C V1+30d salience opt-in)
- §6 11 invariants DF5-A1..A11
- §10 Q1-Q12 ALL LOCKED via 4-batch deep-dive
- §15 SDK contract + swappable backend pattern (consumers depend on trait, not implementation)
- §15.8 5 SDK decision points (location / boundary / capability granularity / migration pattern)

---

**Concept-notes phase COMPLETE 2026-04-27. All decisions converged. Promotion gate fully met. Ready for boundary lock claim + DRAFT promotion cycle. SDK architecture allows backend rework V1+30d / V2+ without consumer-side breakage.**
