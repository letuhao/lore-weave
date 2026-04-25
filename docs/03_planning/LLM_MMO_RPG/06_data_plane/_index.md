# 06_data_plane — Index

> **Purpose:** Kernel contract for how all game-layer services read from and write to LoreWeave's event-sourced storage. Defines the Control Plane / Data Plane split, the persistence tier taxonomy, the SDK enforcement model, and the scale/SLO anchors that every gameplay feature must conform to. Option C scope: this folder owns the kernel access contract; `02_storage/` becomes implementation detail behind this layer.

**Active:** (empty — no agent currently editing)

---

## Why this folder exists

Event-sourcing reads are expensive, and MMO-grade gameplay interactions have extreme read/write frequency that cannot round-trip through a durable event log on every tick. This folder defines the layer that sits between game-layer services and the event-sourced kernel in `02_storage/`, so that:

1. Hot-path reads are served from cache/memory — not from event replay
2. Hot-path writes are classified by tier — only durability-critical writes enter the event log synchronously
3. No service can bypass the contract — enforced via Rust SDK + control plane authority
4. Every future gameplay feature picks a tier from a fixed taxonomy — no ad-hoc persistence policy per feature

If this layer is wrong, every feature built on top of it has to be reworked. That is why it is locked before any feature design starts.

---

## Reading order

1. [00_preamble.md](00_preamble.md) — context, relation to 02_storage and 03_multiverse
2. [01_scope_and_boundary.md](01_scope_and_boundary.md) — Option C scope decision + feature-repo boundary
3. [02_invariants.md](02_invariants.md) — **DP-A1..A12** axioms (read this before proposing any change)
4. [03_tier_taxonomy.md](03_tier_taxonomy.md) — **DP-T0..T3** four-tier persistence model
5. [11_access_pattern_rules.md](11_access_pattern_rules.md) — **DP-R1..R8** Rulebook every feature repo must follow
6. [08_scale_and_slos.md](08_scale_and_slos.md) — **DP-S1..S8** V1/V2/V3 scale anchors and latency budgets
7. [99_open_questions.md](99_open_questions.md) — deferred items (Q1..Q14) including Python handshake, Redis topology, concrete Rust types

Phase 2 (landed 2026-04-25):

8. [04_kernel_api_contract.md](04_kernel_api_contract.md) — **DP-K1..K12** Rust SDK primitive API surface + types + macros (resolves Q1, Q14)
9. [05_control_plane_spec.md](05_control_plane_spec.md) — **DP-C1..C10** control plane service responsibilities (partial Q5, Q6, Q9)
10. [06_cache_coherency.md](06_cache_coherency.md) — **DP-X1..X10** invalidation and consistency protocol (resolves Q4; partial Q10)

Phase 3 (landed 2026-04-25):

11. [07_failure_and_recovery.md](07_failure_and_recovery.md) — **DP-F1..F10** failure modes, CP outage degraded mode, node handoff, split-brain, invalidation reconciliation, backpressure token buckets, schema migration rollback, chaos drill cadence (resolves Q6, Q12; closes Q5 residual)

**Phase 4 — Channel-model follow-ups (in progress, 2026-04-25):**

User clarified on 2026-04-25 that the game uses a **hierarchical channel** model (cell session → tavern → town → district → country → continent) with event bubble-up. Phase 1-3 contracts remain LOCKED as baseline; channel concept extends them. Backlog recorded in [99_open_questions.md](99_open_questions.md) as Q15..Q34. Resolved so far:

12. [12_channel_primitives.md](12_channel_primitives.md) — **DP-Ch1..Ch10** channel identity, tree registry, CP cache + delta stream, scope marker traits, cache-key format, SessionContext extension, CRUD primitives (resolves Q26)
13. [13_channel_ordering_and_writer.md](13_channel_ordering_and_writer.md) — **DP-Ch11..Ch15** per-channel `channel_event_id` allocation, writer assignment rules (cell vs non-cell), epoch fencing, cross-node write routing via gRPC, causal-ref schema for bubble-up (resolves Q17 + Q30 + Q34)
14. [14_durable_subscribe.md](14_durable_subscribe.md) — **DP-Ch16..Ch20** durable per-channel subscribe with resume token, hybrid Redis Streams + Postgres catchup, monotonic gap-free delivery, multi-channel multiplex convenience, backpressure + reconnect (resolves Q16)
15. [15_turn_boundary.md](15_turn_boundary.md) — **DP-Ch21..Ch24** turn boundary primitive: TurnBoundary event + advance_turn SDK API + per-event turn_number tagging + capability gating + composition with pause/bubble-up/move (resolves Q15)
16. [16_bubble_up_aggregator.md](16_bubble_up_aggregator.md) — **DP-Ch25..Ch30** `BubbleUpAggregator` trait + register/unregister + event-sourced state + deterministic RNG + CP registry + cascading + privacy redaction patterns (resolves Q27 — last design blocker)
17. [17_channel_lifecycle.md](17_channel_lifecycle.md) — **DP-Ch31..Ch37** lifecycle state machine (Active/Dormant/Dissolved) + auto-dormant scheduler + dissolution + canonical MemberJoined/MemberLeft + channel_pause/resume + composition rules + idempotency (resolves Q19 + Q28 + Q31)
18. [18_causality_and_routing.md](18_causality_and_routing.md) — **DP-Ch38..Ch42** `CausalityToken` opaque newtype attached to acks + `wait_for` parameter on read primitives + projection-apply checkpoint table + session-writer transparent routing extending DP-Ch14 pattern + error taxonomy + gateway contract (resolves Q21 + Q22)

**🎉 Phase 4 design phase complete + 6 follow-up gaps resolved.** Remaining Phase 4 work is 3 🟡 gaps + 4 🟢 nits/ops items, all non-blocking. **Feature design (DF4 / DF5 / DF7) can now consume the locked DP contract.**

---

## Status table

| # | File | Status | Owned IDs | Last touched |
|---:|---|---|---|---|
| 00 | [00_preamble.md](00_preamble.md) | LOCKED | — | 2026-04-24 |
| 01 | [01_scope_and_boundary.md](01_scope_and_boundary.md) | LOCKED | — | 2026-04-24 |
| 02 | [02_invariants.md](02_invariants.md) | LOCKED | DP-A1..A19 | 2026-04-25 |
| 03 | [03_tier_taxonomy.md](03_tier_taxonomy.md) | LOCKED | DP-T0, DP-T1, DP-T2, DP-T3 | 2026-04-25 (DP-T1 reframed for Phase 4 channel model) |
| 04 | [04_kernel_api_contract.md](04_kernel_api_contract.md) | LOCKED | DP-K1..K12 | 2026-04-25 |
| 05 | [05_control_plane_spec.md](05_control_plane_spec.md) | LOCKED | DP-C1..C10 | 2026-04-25 |
| 06 | [06_cache_coherency.md](06_cache_coherency.md) | LOCKED | DP-X1..X10 | 2026-04-25 |
| 07 | [07_failure_and_recovery.md](07_failure_and_recovery.md) | LOCKED | DP-F1..F10 | 2026-04-25 |
| 08 | [08_scale_and_slos.md](08_scale_and_slos.md) | LOCKED | DP-S1..S8 | 2026-04-24 |
| 11 | [11_access_pattern_rules.md](11_access_pattern_rules.md) | LOCKED | DP-R1..R8 | 2026-04-24 |
| 12 | [12_channel_primitives.md](12_channel_primitives.md) | LOCKED | DP-Ch1..Ch10 | 2026-04-25 |
| 13 | [13_channel_ordering_and_writer.md](13_channel_ordering_and_writer.md) | LOCKED | DP-Ch11..Ch15 | 2026-04-25 |
| 14 | [14_durable_subscribe.md](14_durable_subscribe.md) | LOCKED | DP-Ch16..Ch20 | 2026-04-25 |
| 15 | [15_turn_boundary.md](15_turn_boundary.md) | LOCKED | DP-Ch21..Ch24 | 2026-04-25 |
| 16 | [16_bubble_up_aggregator.md](16_bubble_up_aggregator.md) | LOCKED | DP-Ch25..Ch30 | 2026-04-25 |
| 17 | [17_channel_lifecycle.md](17_channel_lifecycle.md) | LOCKED | DP-Ch31..Ch37 | 2026-04-25 |
| 18 | [18_causality_and_routing.md](18_causality_and_routing.md) | LOCKED | DP-Ch38..Ch42 | 2026-04-25 |
| 99 | [99_open_questions.md](99_open_questions.md) | OPEN + **Phase 4 design ✅ + 6 follow-ups resolved** | Phase 1-3 residuals (Q2/Q3/Q7/Q10/Q11/Q13) + **Phase 4 Q15..Q34** (13 resolved: Q15/Q16/Q17/Q18/Q19/Q21/Q22/Q26/Q27/Q28/Q30/Q31/Q34; 3 🟡 + 4 🟢 remaining, none blocking) | 2026-04-25 |

---

## Exported stable IDs

Outside docs may cross-link unambiguously to:

| Prefix | Scope | Owned by |
|---|---|---|
| `DP-A*` | Axioms / invariants (DP-A1..A19) | [02_invariants.md](02_invariants.md) |
| `DP-T0..T3` | Tier taxonomy | [03_tier_taxonomy.md](03_tier_taxonomy.md) |
| `DP-R*` | Access Pattern Rulebook rules (DP-R1..R8) | [11_access_pattern_rules.md](11_access_pattern_rules.md) |
| `DP-S*` | Scale and SLO items (DP-S1..S8) | [08_scale_and_slos.md](08_scale_and_slos.md) |
| `DP-K*` | Kernel API primitive surface (DP-K1..K12) | [04_kernel_api_contract.md](04_kernel_api_contract.md) |
| `DP-C*` | Control plane spec items (DP-C1..C10) | [05_control_plane_spec.md](05_control_plane_spec.md) |
| `DP-X*` | Cache coherency / consistency items (DP-X1..X10) | [06_cache_coherency.md](06_cache_coherency.md) |
| `DP-F*` | Failure and recovery items (DP-F1..F10) | [07_failure_and_recovery.md](07_failure_and_recovery.md) |
| `DP-Ch*` | Channel primitives (DP-Ch1..Ch10) | [12_channel_primitives.md](12_channel_primitives.md) |
| `DP-Ch*` | Channel ordering + writer binding (DP-Ch11..Ch15) | [13_channel_ordering_and_writer.md](13_channel_ordering_and_writer.md) |
| `DP-Ch*` | Durable per-channel subscribe (DP-Ch16..Ch20) | [14_durable_subscribe.md](14_durable_subscribe.md) |
| `DP-Ch*` | Turn boundary primitive (DP-Ch21..Ch24) | [15_turn_boundary.md](15_turn_boundary.md) |
| `DP-Ch*` | Bubble-up aggregator (DP-Ch25..Ch30) | [16_bubble_up_aggregator.md](16_bubble_up_aggregator.md) |
| `DP-Ch*` | Channel lifecycle + membership + pause (DP-Ch31..Ch37) | [17_channel_lifecycle.md](17_channel_lifecycle.md) |
| `DP-Ch*` | Causality token + routing UX (DP-Ch38..Ch42) | [18_causality_and_routing.md](18_causality_and_routing.md) |

Retired IDs: (none yet). Retired IDs use `_withdrawn` suffix, never reused.

---

## Cross-folder references

This folder reads from and constrains:

| Folder | Relation |
|---|---|
| [02_storage/](../02_storage/) | Becomes implementation detail behind DP SDK. Existing R*/S*/C*/SR* design still authoritative for the durable tier; DP owns the access contract above it. |
| [03_multiverse/](../03_multiverse/) | Canon layering (L1–L4) is orthogonal to tier taxonomy; DP respects reality boundaries in cache keying. |
| [04_player_character/](../04_player_character/) | PC aggregates live in DP-T2/T3; PC DF items register through DP contract when implemented. |
| [05_llm_safety/](../05_llm_safety/) | World Oracle / command dispatch produces events that flow through DP write path. |
| [catalog/](../catalog/) | Every feature in the catalog picks one tier (DP-T0..T3) when it graduates to detailed design. |

---

## Pending splits

None. All Phase 1 files are under the 500-line soft cap.
