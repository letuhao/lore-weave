# 22 — Feature Design Quickstart

> **Status:** LOCKED (bridging doc, post-Phase-4). Not an axiom or primitive — a **mental-model + worked-example** entry point for agents designing features against the locked DP contract. If anything here conflicts with files 02 / 04a-d / 11-21, those files win — re-open this doc to fix.
> **Audience:** Any agent (or human) about to design a feature that reads or writes per-reality kernel state via the DP SDK. Read this first; then read only the DP-A* / DP-K* / DP-Ch* sections this doc points to.
> **Scope:** This is a *how-to-design*, not a *what-the-system-is*. For "what", read [00_preamble.md](00_preamble.md) and [02_invariants.md](02_invariants.md) DP-A1..A19.

---

## 1. The 5-minute mental model

Each **reality** is an instance of a book. Time inside a reality is a sequence of **events**, not wall-clock — turn-based and event-linear. Players inside a reality sit in a **tree of channels** (cell session → tavern → town → district → country → continent), where a player is in exactly one cell at a time but is a "resident" of every ancestor.

You design a feature by:

1. **Listing every aggregate** the feature reads or writes.
2. For each aggregate, picking exactly **one tier** (T0/T1/T2/T3) and **one scope** (RealityScoped / ChannelScoped). Both choices are design-time and locked.
3. **Composing DP primitives** (~42 total — see [04d DP-K12](04d_capability_and_lifecycle.md#dp-k12--api-surface-summary)) into your feature's typed Rust APIs.

You do **NOT** design new database tables, cache keys, locks, event ordering, channel writers, or invalidation. DP owns those. You **DO** design the feature's domain logic and its public Rust API surface.

Cross-service read-your-writes inside a session = pass `T2Ack.causality_token` / `T3Ack.causality_token` to the next service via RPC arg, the next service passes it to a read primitive's `wait_for: Some(token)` parameter.

---

## 2. Worked example: "Tavern Notice Board"

Players in a tavern channel can post a notice (text + author). All tavern members see new notices in event-order. Players see "how many notices I've posted total" (drives a 100-notice achievement).

### 2.1 Aggregates

| Aggregate | What it stores |
|---|---|
| `TavernNotice` | One posted notice (author, body, posted_at) |
| `PlayerNoticeStats` | Per-player total notice count |

### 2.2 Tier + scope per aggregate

| Aggregate | Tier | Scope | Why |
|---|---|---|---|
| `TavernNotice` | **T2** Durable-async | **ChannelScoped** | Durable (notices persist as canon); eventual consistency on cross-session reads OK; lives in the tavern channel, not the player |
| `PlayerNoticeStats` | **T2** Durable-async | **RealityScoped** | Durable (achievement depends on it); follows player across taverns |

**Rejected alternatives:**
- `TavernNotice` as **T3**? Too synchronous; notices are not money-adjacent. T2 is faster and equally correct.
- `TavernNotice` as **T1**? T1 allows ≤30 s loss on crash. Notices must survive crashes.
- `PlayerNoticeStats` as **ChannelScoped**? Counter would reset when player walks to next tavern.

### 2.3 Aggregate declarations

```rust
#[derive(Aggregate)]
#[dp(scope = "channel", tier = "T2")]
pub struct TavernNotice {
    pub notice_id: NoticeId,
    #[dp(indexed)] pub author: PlayerId,
    pub body: String,
    pub posted_at: Timestamp,
}
// derive emits: impl ChannelScoped for TavernNotice {} + impl T2Aggregate for TavernNotice {}

#[derive(Aggregate)]
#[dp(scope = "reality", tier = "T2")]
pub struct PlayerNoticeStats {
    pub player_id: PlayerId,
    pub total_posted: u64,
}
// derive emits: impl RealityScoped for PlayerNoticeStats {} + impl T2Aggregate for PlayerNoticeStats {}
```

### 2.4 Primitives the feature calls

| Operation | Primitive |
|---|---|
| Post notice | `t2_write::<TavernNotice>(ctx, id, delta)` — SDK routes to channel writer (DP-Ch14) |
| Increment player counter | `t2_write::<PlayerNoticeStats>(ctx, id, delta)` |
| Read a specific notice | `read_projection_channel::<TavernNotice>(ctx, &channel, id, None, None)` |
| List notices in tavern | `query_scoped_channel::<TavernNotice>(ctx, &channel, predicate, limit, None, None)` |
| Members get new notices live + on reconnect | `subscribe_channel_events_durable::<NoticePosted>(ctx, channel, from_event_id)` |
| Achievement service reads stats AFTER post (RYW) | `read_projection_reality::<PlayerNoticeStats>(ctx, id, wait_for: Some(&token), None)` |

### 2.5 Capability claims required

| Operation | JWT claim |
|---|---|
| Post notice | (none beyond standard write capability) |
| Increment counter | (none) |
| Subscribe | (none — visibility checked from session's ancestor chain) |

This feature needs **no special claims**. Special claims are only required for: `advance_turn` (DP-Ch23), `channel_pause`/`resume` (DP-Ch35), `register_bubble_up_aggregator` (DP-Ch25), `claim_turn_slot` (DP-Ch53 — gated by same `can_advance_turn`).

### 2.6 Cross-cutting decisions

| Decision | Choice for this feature | Why |
|---|---|---|
| Turn semantics? | None — channel never calls `advance_turn`; events stay at `turn_number = 0` (DP-A17) | Notice-posting is async, not turn-gated |
| Pause behavior? | Default — admin pause blocks notice-posting (DP-Ch36) | No special handling needed |
| Privacy redaction? | `Transparent` for v1 | All tavern members see all notices |
| Causality across services? | Achievement service: `post.ack.causality_token` → RPC arg → `read_projection_reality(.., wait_for: Some(token), ..)` (DP-A19) | Avoids stale read after async projection apply |
| Bubble-up? | None for v1 | If we wanted "this tavern is busy → notify town", register a `BubbleUpAggregator` later |
| Failure modes user-visible? | `RateLimited` → "too many notices, retry"; `WrongChannelWriter` → SDK transparently routes (invisible); `CausalityWaitTimeout` → "stats still updating" | Standard backpressure UX |

---

## 3. Decision flowchart per aggregate

```
1. TIER?
   - Memory-only OK, lose on crash? .................. T0
   - High-churn OR transient, ≤30s loss OK? .......... T1
   - Durable, eventual consistency OK? ............... T2 ← default for most game data
   - Durable, RYW required (money/canon-critical)? ... T3
   When unsure: pick T2. Move down to T1 only if you have a measured high-frequency
   case. Move up to T3 only if a stale read would be a correctness bug.

2. SCOPE?
   - Follows the player across channels (PC, inventory, achievements)? ... RealityScoped
   - Lives in one specific channel (chat, tavern decor, cell quest) ...... ChannelScoped
   When unsure: ask "if the player walks from cell A → tavern → cell B,
   does this aggregate move with them?" Yes = Reality, No = Channel.

3. CAPABILITY?
   - Standard read/write only? ................. (no extra JWT claim needed)
   - advance_turn? ............................. can_advance_turn:[level_name]
   - channel_pause / channel_resume? ........... can_pause_channel:[level_name]
   - register_bubble_up_aggregator? ............ can_register_aggregator:[level_name]
   - claim_turn_slot? .......................... can_advance_turn (same claim, see DP-Ch53)
   - move_session_to_channel? .................. (allowed_channels in JWT scope)

4. SUBSCRIBE PATTERN?
   - Need cache invalidation only? .......................... subscribe_invalidation
   - Need T1 broadcast (presence, ephemeral)? ............... subscribe_broadcast<T1>
   - Need durable per-channel events with replay/resume? .... subscribe_channel_events_durable<S>
   - Need to track all channels in session's ancestor chain? subscribe_session_channels<S>
```

---

## 4. Pattern selection cheatsheets

### 4.1 Turn-slot patterns (when feature uses turn-based interaction — DP-Ch53)

| Pattern | When to pick | Examples |
|---|---|---|
| **Strict** (slot + pause + advance) | One actor per turn; others must wait visibly. Classic turn-based. | Combat round, formal scene, structured negotiation |
| **Concurrent** (slot only, no pause) | Multiple players act in parallel within one turn; turn boundary is just a beat. | Group chat, open-world conversations, social RP |
| **Cancellable** (slot + cancellation token) | Long actions (LLM thinking) the player should interrupt. | NPC dialog generation, narrative scene generation, world-event narration |

When unsure: **start with Concurrent**. It's least restrictive. You can tighten to Strict later without breaking writes (only adds pause); going from Strict → Concurrent is a design change.

### 4.2 Redaction policy (when feature has a `BubbleUpAggregator` — DP-Ch43)

| Policy | When to pick |
|---|---|
| `Transparent` (default) | Public channels; no privacy concern; aggregator sees everything |
| `SkipPrivate` | Private cells exist; **don't** aggregate their events at all (counts will not include private cells) |
| `AnonymizeRefs` | Aggregate counts/stats from private cells, but strip `causal_refs` to source events from emitted output |
| `Custom(filter)` | Feature-specific policy (partial reveal based on relationship, role-based redaction, etc.) — requires writing a `RedactionFilter` impl |

When unsure: **start with Transparent**. Add `SkipPrivate` when private channels are first introduced.

### 4.3 Tier × Scope quick reference

Already exhaustively shown in [12 DP-Ch4](12_channel_primitives.md#dp-ch4--scope-marker-traits) — example aggregates per cell:

| Tier ↓ \ Scope → | RealityScoped | ChannelScoped |
|---|---|---|
| **T0** Ephemeral | (in-memory caches per session) | `TypingIndicator` |
| **T1** Volatile | (rare; mostly session-scoped state lives at T1+Reality via session_id) | `ChannelPresence` (who's currently in cell) |
| **T2** Durable-async | `PlayerInventory`, `PlayerNoticeStats`, achievements | `ChatMessage`, `TavernNotice`, cell quest progress |
| **T3** Durable-sync | `ReputationScore`, currency, canon writes | (rare; only if channel-local data is money-adjacent — e.g., cell-scoped wager pool) |

If your aggregate doesn't fit a cell, re-examine — likely a sign the tier or scope is wrong.

---

## 5. Anti-patterns (what NOT to do)

| ❌ Don't | ✅ Do | Reason / Enforcement |
|---|---|---|
| Read Postgres / Redis directly from feature code | Use `dp::read_projection_*`, `dp::query_scoped_*` | DP-R3 lint rejects raw `sqlx` / `redis` imports |
| Build cache keys with `format!("dp:...")` | Use the `dp::cache_key!` macro | DP-R4 — hand-built keys break reality scoping |
| Emit `MemberJoined` / `MemberLeft` / `ChannelPaused` / `ChannelResumed` / `TurnSlotClaimed` / `TurnBoundary` events from feature code | These are DP-emitted canonical events. Subscribe via `subscribe_channel_events_durable` to consume them | DP-A18 / DP-Ch34 / DP-Ch52 — feature emission rejected by SDK type system |
| Use wall-clock `now()` inside `BubbleUpAggregator::on_event` | Use `dp::deterministic_rng(channel_id, channel_event_id)` for any randomness | DP-Ch27 — wall-clock breaks replay determinism |
| Generate your own RNG for bubble-up trigger probability | Same — `deterministic_rng` is mandatory | DP-Ch27 |
| Pick a tier "T1.5" or "between T2 and T3" | Pick the closer tier; if unsure, pick the safer one (higher tier) | DP-A5 — closed taxonomy, no in-betweens |
| Switch tier at runtime based on load / config / player rank | Tier is design-time only | DP-A9 |
| Hardcode "wait 2s before reading after a write" | Use `T2Ack.causality_token` / `T3Ack.causality_token` + read's `wait_for: Some(token)` | DP-A19 — principled, typed coordination |
| Conditionally swallow `RateLimited` / `CircuitOpen` errors with `.ok()` / `.unwrap_or_default()` | Propagate to caller | DP-R6 — clippy lint rejects |
| Skip the `dp::instrumented!` wrapper around DP calls | Wrap DP calls (or `#[allow(dp::missing_instrumentation)]` on tight loops + emit aggregated metrics) | DP-R8 — clippy warns |
| Invent your own session-to-NPC mapping inside DP | Roleplay-service / orchestrator owns NPC session mapping; use `ActorId::Npc { npc_id }` + your service's existing `SessionContext` | OOS-1 in [99_open_questions.md](99_open_questions.md) |
| Build a runtime aggregate type registry across services | Use a shared workspace crate (`crates/loreweave-aggregates/`) | OOS-2 in [99_open_questions.md](99_open_questions.md) |
| Read state inside an LLM-driven write path on the LLM service | Python emits proposal events; Rust validates and writes | DP-A6 |
| Forge writes on behalf of an NPC from outside the orchestrator service | Orchestrator's `SessionContext` is the only authorized writer for NPC actions | OOS-1 |
| Call CP on every player action | CP is never on the hot path | DP-A2 — only at session bind, schema migration, capability refresh, channel-tree-delta subscribe |
| Pre-resolve `RealityId` from a config string and pass it everywhere | `RealityId` newtype is module-private; obtain it from `SessionContext::reality_id()` | DP-A12 — gates cross-reality leakage at the type level |

---

## 6. What a feature design doc must contain

Before submitting for governance review, your feature doc must answer:

1. **Tier table (DP-R2)** — every aggregate, read tier, write tier, rationale.
2. **Scope declaration** per aggregate (`RealityScoped` vs `ChannelScoped`).
3. **Primitive list** — which DP primitives the feature calls, by name.
4. **Capability requirements** — which `can_*` JWT claims your service needs.
5. **Subscribe pattern** — which subscribe primitive + replay/resume contract.
6. **Failure-mode UX** — what the user sees on `DpError::RateLimited` / `CircuitOpen` / `WrongChannelWriter` / `CausalityWaitTimeout` / `ResumeTokenExpired`.
7. **Cross-service handoffs** — if your feature triggers another service via RPC/bus, document `CausalityToken` flow.
8. **Pattern choices** — turn-slot pattern (if any), redaction policy (if has bubble-up).

If any of these is missing or "TBD", design review will block per DP-R2.

---

## 7. Where to look next

| Question | File |
|---|---|
| Full ~42-primitive surface | [04d DP-K12](04d_capability_and_lifecycle.md#dp-k12--api-surface-summary) |
| Why each axiom exists | [02_invariants.md](02_invariants.md) DP-A1..A19 |
| Tier eligibility rules + examples | [03_tier_taxonomy.md](03_tier_taxonomy.md) |
| Read/write primitive signatures | [04b_read_write.md](04b_read_write.md) DP-K4..K5 |
| Subscribe primitives + macros | [04c_subscribe_and_macros.md](04c_subscribe_and_macros.md) DP-K6..K8 |
| Capability tokens, channel CRUD, turn slot | [04d_capability_and_lifecycle.md](04d_capability_and_lifecycle.md) DP-K9..K12 |
| Rulebook + lint enforcement labels | [11_access_pattern_rules.md](11_access_pattern_rules.md) DP-R1..R8 |
| Channel scope semantics | [12_channel_primitives.md](12_channel_primitives.md) DP-Ch1..Ch10 |
| Per-channel ordering + writer binding | [13_channel_ordering_and_writer.md](13_channel_ordering_and_writer.md) DP-Ch11..Ch15 |
| Durable subscribe with resume | [14_durable_subscribe.md](14_durable_subscribe.md) DP-Ch16..Ch20 |
| Turn boundaries | [15_turn_boundary.md](15_turn_boundary.md) DP-Ch21..Ch24 |
| Bubble-up aggregators | [16_bubble_up_aggregator.md](16_bubble_up_aggregator.md) DP-Ch25..Ch30 |
| Channel lifecycle + membership + pause | [17_channel_lifecycle.md](17_channel_lifecycle.md) DP-Ch31..Ch37 |
| Causality token + WrongWriterNode UX | [18_causality_and_routing.md](18_causality_and_routing.md) DP-Ch38..Ch42 |
| Privacy redaction policies | [19_privacy_redaction_policies.md](19_privacy_redaction_policies.md) DP-Ch43..Ch45 |
| LLM turn slot patterns | [21_llm_turn_slot.md](21_llm_turn_slot.md) DP-Ch51..Ch53 |
| What's NOT decided + OOS pointers | [99_open_questions.md](99_open_questions.md) |

---

## 8. When this doc is wrong

This is a *bridging doc*. The locked spec lives in 02 / 04a-d / 11-21. If a primitive name, signature, or guarantee here disagrees with those files:

- **The locked spec wins.** Do not infer behavior from this doc.
- **Open a fix PR for this doc.** Target this file for correction, not the locked spec.
- **If you find a real DP gap** (something a feature genuinely needs but no primitive exists), record it in [99_open_questions.md](99_open_questions.md) with severity, and stop trying to design around it locally — escalate.
