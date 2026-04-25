# 07 — Proposal Bus Framework (EVT-L*)

> **Status:** LOCKED Phase 3b (Option C discipline 2026-04-25). Per [EVT-A7 untrusted-origin pre-validation](02_invariants.md#evt-a7--untrusted-origin-events-require-pre-validation-lifecycle-reframed-2026-04-25), untrusted-origin services emit EVT-T6 Proposal events onto a proposal bus; trusted commit-services consume + validate + commit fresh Submitted events. This file specifies the **bus framework** (transport, lifecycle, idempotency, ordering, backpressure, dead-letter) at mechanism level. Specific operational config (topic names, retention seconds, MAXLEN values) is deployment-tuning, not Event Model lock.
> **Stable IDs:** EVT-L1..EVT-L6. Never renumber. Retired IDs use `_withdrawn` suffix.
> **Resolves:** [DP-A6](../06_data_plane/02_invariants.md#dp-a6--python-is-event-producer-only-for-game-state) deferred bits — DP-A6 locked the direction (Python emits, Rust validates and applies); this file locks the protocol framework.
> **Naming note:** file named "llm_proposal_bus" for historical continuity (per brief seed list); EVT-L* and the framework apply to **any untrusted-origin producer** per EVT-A7 — not just LLM.

---

## How to use this file

When implementing an untrusted-origin producer (LLM service today; future agentic/plugin services):

1. Confirm your service-account JWT carries `produce: [Proposal]` ONLY per [EVT-P6](04_producer_rules.md#evt-p6--proposal-evt-t6).
2. Implement against EVT-L1 transport mechanism (Redis Streams via I13 outbox).
3. Honor EVT-L2 lifecycle state machine (proposal → terminal state).
4. Generate `proposal_id` per EVT-L3 idempotency rules.
5. Tolerate EVT-L5 backpressure correctly (propagate, don't swallow).

When implementing a trusted commit-service consuming proposals:

1. Subscribe to the bus per EVT-L1.
2. Apply EVT-L4 ordering guarantee (per-stream FIFO).
3. Run EVT-V* validator pipeline on each proposal.
4. On Validated: commit fresh EVT-T1 Submitted with idempotency dedup.
5. On Rejected/Expired: emit dead-letter per EVT-L6 + EVT-V7.

Specific values (topic strings, retention windows, MAXLEN caps, backoff intervals) are operational tunables documented in deployment ops doc, NOT in this file.

---

## EVT-L1 — Bus transport mechanism

**Rule:** The proposal bus transport is **Redis Streams**, deployed via the existing [I13 outbox pattern](../00_foundation/02_invariants.md#i13-outbox-pattern-for-cross-service-events). Producer writes to outbox in same transaction as proposal-side state (if any); the publisher service drains outbox to Redis Streams. Consumer reads from Redis Streams via consumer group (XREADGROUP) for at-least-once delivery + Pending Entries List (PEL) tracking.

**Topic naming pattern:** topics are **reality-prefixed** per [DP-A7](../06_data_plane/02_invariants.md#dp-a7--reality-boundary-in-cache-keys). Granularity guidance: **per-cell** is the default for live proposal traffic (matches per-cell single-writer DP-A16 + enables parallel cell-consumer scale-out without contention). Specific topic-string format is operational design (ops doc owns the literal pattern).

**Default for design:** assume per-cell topic granularity until V1 measurement shows the topic count exceeds Redis Streams comfort zone (per Q3 Redis topology open question). All EVT-L* designs are topic-granularity-agnostic — the protocol works under any reality-prefixed scheme.

**Why Redis Streams:** forced by I13 outbox (LoreWeave-wide pattern) + DP-A4 (Redis already in stack). Mature client libraries (redis-rs, fred); native consumer groups + PEL + acknowledgment + MAXLEN trim; supports XADD with NOMKSTREAM for backpressure.

**Forbidden alternatives:** NATS / Kafka / custom transport — would add new infrastructure dependency for no proven benefit at V1 scale.

**Cross-ref:** [DP-A4 Redis cache + pubsub + streams](../06_data_plane/02_invariants.md#dp-a4--redis-is-the-cache--pubsub--streams-technology), I13 outbox, [DP-A7 reality scoping](../06_data_plane/02_invariants.md#dp-a7--reality-boundary-in-cache-keys).

---

## EVT-L2 — Lifecycle state machine

**Rule:** Every Proposal event has exactly one **terminal state**, reached via this state machine:

```
                  ┌─ Validated ──► commit fresh EVT-T1 Submitted; original proposal NOT retained as event
                  │
[Proposal] ──────►│─ Rejected { reason } ──► log + dead-letter (EVT-L6); original payload preserved 7d default
                  │
                  └─ Expired ──► bus retention elapsed without consume; dead-letter as ProposalExpired
```

**State transitions:**
- `Proposal → Validated`: trusted commit-service ran EVT-V* pipeline successfully → committed fresh EVT-T1 Submitted via DP `advance_turn`. The original Proposal is **NOT promoted in-place** — a fresh canonical event is committed; the proposal is acked off the bus.
- `Proposal → Rejected`: validator pipeline rejected (any stage with `reject_hard` or exhausted `reject_soft_with_retry` per EVT-V2) → log + dead-letter. Proposal is acked off the bus to prevent retry loops.
- `Proposal → Expired`: bus retention window elapsed without commit-service consume → cleanup process moves entry to dead-letter as `ProposalExpired`.

**Default retention window:** ~60 seconds — long enough to absorb commit-service brief outages, short enough that stale LLM proposals don't pile up. Specific value is operational tunable.

**Why fresh commit (not in-place promotion):** the original Proposal exists on the bus; once Validated, the Submitted event is a SEPARATE canonical record in the channel event log. This split:
- Keeps the bus retention bounded (proposals don't live forever)
- Makes the canonical event log self-contained (no "this commit is actually the validated form of bus message X")
- Allows the proposal_id to track Origin → Canonical mapping for audit (the committed Submitted carries `origin_proposal_id` reference)

**Forbidden:** "in-place promotion" of bus messages to canonical events (would conflate bus retention with event-log retention); silent drop of proposals (per EVT-V2 silent_drop forbidden — Expired is the explicit failure path).

**Cross-ref:** [EVT-T6 Proposal](03_event_taxonomy.md#evt-t6--proposal), [EVT-A7 untrusted-origin lifecycle](02_invariants.md#evt-a7--untrusted-origin-events-require-pre-validation-lifecycle-reframed-2026-04-25), [EVT-V7 dead-letter framework](05_validator_pipeline.md#evt-v7--dead-letter-framework).

---

## EVT-L3 — Idempotency-based dedup

**Rule:** Every proposal carries an `idempotency_key` per the uniform shape `(producer_service, client_request_id=proposal_id, target_channel)` per [EVT-P6](04_producer_rules.md#evt-p6--proposal-evt-t6). The trusted commit-service uses this key to **dedupe consume** — if the bus delivers the same proposal twice (legitimate at-least-once retry), only one Validated commit results.

**Dedup mechanism (commit-service-side):**
1. Read proposal from bus.
2. Check dedup cache for `(producer_service, proposal_id, target_channel)`.
3. If found and previous outcome was Validated → ack the bus entry; return cached result. NO re-validation, NO double-commit.
4. If found and previous outcome was Rejected/Expired → ack the bus entry; do NOT re-process (would re-derive same rejection).
5. If not found → run validator pipeline; on terminal state, write to dedup cache + ack the bus entry.

**Dedup cache lifetime:** matches commit-service's idempotency-cache TTL per PL_001 §14 (default 60 seconds; covers retry storms and brief outages). Specific value operational.

**Producer responsibility:** generate `proposal_id` as a fresh UUIDv4 per logical proposal. Retries of the same logical proposal MUST use the same `proposal_id` — that's how the producer signals "this is a retry, not a new proposal".

**Why:** without idempotency dedup, at-least-once delivery from Redis Streams could double-commit during commit-service restarts or network blips. UUIDv4 collision probability is negligible; per-(producer, target_channel) scoping prevents cross-target false-dedup.

**Cross-ref:** [PL_001 §14 idempotency](../features/04_play_loop/PL_001_continuum.md), [EVT-P6](04_producer_rules.md#evt-p6--proposal-evt-t6), uniform idempotency-key shape.

---

## EVT-L4 — Ordering guarantee

**Rule:** Within a single bus stream (one Redis Streams key), proposals are delivered to consumers in **per-stream FIFO order** (Redis Streams natural ordering). Cross-stream ordering is **independent** — the bus does NOT guarantee any cross-stream ordering. If two proposals on different streams are causally related, the producer MUST encode the dependency via causal-refs, not stream ordering.

**Granularity implication:** per-cell topic granularity (EVT-L1 default) means proposals within the same cell are FIFO-ordered. Proposals across cells are not — that's intentional, since DP-A16 single-writer-per-channel handles cross-cell ordering at the commit layer, not the bus layer.

**Producer-perspective:** if you emit two proposals to the same target_channel, expect them delivered in submission order. If you emit to different target_channels, no ordering guarantee.

**Consumer-perspective:** process per-stream sequentially (one proposal at a time per stream, completing the validator pipeline + commit before moving to next). This honors the FIFO contract and matches DP-A16 single-writer.

**Why per-stream FIFO:** matches Redis Streams native semantics (XADD appends preserve order; XREADGROUP delivers in order within a consumer group). Cross-stream ordering would require a global-ordering layer (Kafka exactly-once partitioning or distributed transaction) — overkill for V1.

**Cross-ref:** [DP-A16 channel writer-node binding](../06_data_plane/02_invariants.md#dp-a16--channel-writer-node-binding-phase-4-2026-04-25), [DP-A15 per-channel total event ordering](../06_data_plane/02_invariants.md#dp-a15--per-channel-total-event-ordering-phase-4-2026-04-25), Redis Streams native ordering.

---

## EVT-L5 — Backpressure framework

**Rule:** When the bus is at capacity (per-stream MAXLEN reached) or commit-service is lagging (PEL grows beyond a threshold), backpressure flows back to producers. Backpressure mechanism is **fail-fast at producer** + retry-with-backoff, NOT silent buffer growth.

**Producer-side backpressure handling:**
- Bus rejection (XADD fails with NOMKSTREAM or MAXLEN ~ trim drops the new entry): producer treats as rate-limit signal; surfaces upstream (e.g., LLM-Originator → gateway → user toast "system busy, retry in N sec").
- DO NOT retry immediately; honor exponential backoff (specific intervals operational).

**Consumer-side backpressure handling:**
- PEL length monitoring: if PEL > threshold (operational), commit-service signals "lagging" → bus producers throttle.
- New consumers added (horizontal scale-out) when PEL persistently high.

**Bus-side limits:**
- Per-stream `MAXLEN ~ N` cap (operational; default guidance ~10K entries per cell). Old entries trimmed to make room for new — but this means dropped proposals → must be dead-lettered as `ProposalExpired` BEFORE the trim happens.
- Cleanup process scans for proposals exceeding retention BEFORE MAXLEN trim deletes them; trim drops are an EXCEPTIONAL audit-event-worthy condition (not normal flow).

**Why fail-fast:** silent buffer growth at the bus would hide capacity problems until catastrophic failure. Surface backpressure to the user via gateway → toast; operator sees alerts; capacity gets adjusted explicitly.

**Forbidden:** silent drop without dead-letter; unbounded buffer growth; producer-side infinite retry loops.

**Cross-ref:** [DP-R6 backpressure propagation](../06_data_plane/11_access_pattern_rules.md#dp-r6--backpressure-propagation-not-swallow-and-retry), [SR9 alert tuning](../decisions/locked_decisions.md) (PEL alerts), Redis Streams MAXLEN.

---

## EVT-L6 — Dead-letter integration

**Rule:** Terminal-state proposals (Rejected, Expired) flow into the dead-letter framework specified in [EVT-V7](05_validator_pipeline.md#evt-v7--dead-letter-framework). Dead-letter is a **shared mechanism** across the validator pipeline (rejected events) and proposal bus (rejected/expired proposals); both share the same destination + retention + replay framework.

**Dead-letter entry shape (proposal-specific fields):**
- All fields from EVT-V7 (`original_event_id` placeholder, `producer_service`, `failure_reason`, `retry_count`, `final_attempt_at`, `original_payload`)
- Plus: `proposal_id` (from EVT-T6), `target_channel`, `time_on_bus` (how long the proposal waited before terminal state)

**Replay mechanism:** operator-initiated via admin command. Replay re-emits the original proposal payload as a fresh proposal (with a NEW `proposal_id` to avoid dedup cache collision); the new proposal flows through the bus + validator pipeline normally. Idempotency dedup ensures double-replay doesn't double-commit.

**Why shared dead-letter:** validator-rejection of a Submitted event and validator-rejection of a Proposal are mechanically the same failure class (validator said no; preserve for review + replay). Sharing the framework avoids two disparate dead-letter systems.

**Cross-ref:** [EVT-V7 dead-letter framework](05_validator_pipeline.md#evt-v7--dead-letter-framework), [EVT-V3 retry policy](05_validator_pipeline.md#evt-v3--retry-policy).

---

## What an untrusted-origin producer needs to know to implement

Minimum implementation contract for a Python LLM-Originator (today) or future agentic service:

| Need | Where to find |
|---|---|
| What category to emit | EVT-T6 Proposal — the only category your service is authorized for |
| What sub-shapes exist | feature design docs (PL_002 PCTurnProposal; NPC_001 NPCTurnProposal; future) + register in `_boundaries/` |
| JWT claim shape | DP-K9 + EVT-A4 producer-role binding — `produce: [Proposal]` ONLY |
| Bus topic | reality-prefixed pattern; specific format in ops doc; per-cell granularity default |
| `proposal_id` generation | UUIDv4; same id on retries of same logical proposal |
| Retry behavior | NO retry on validator-rejection; exponential backoff on bus-side rejection (capacity); honor backpressure |
| Lifecycle observability | poll `(producer_service, proposal_id)` against commit-service status endpoint to see Validated/Rejected/Expired (per PL_001 §14.1 status endpoint pattern) |
| Failure UX | producer surfaces "Rejected/Expired" to upstream as soft-fail; downstream UI per A5-D4 fallback |

**Concrete enough to implement:** Python roleplay-service can be coded against this contract — types, transport, retry policy, idempotency, dead-letter all specified at the framework level. Specific values (topic strings, retention seconds, MAXLEN caps) come from ops doc when V1 deploys.

---

## What an event-model-aware commit-service needs to know

Minimum implementation contract for a Rust commit-service (today: world-service) consuming proposals:

| Need | Where to find |
|---|---|
| Consumer group setup | per-reality consumer group; one consumer per cell-channel writer for ordering preservation (DP-A16 + EVT-L4 per-stream FIFO) |
| Dedup cache | per EVT-L3; default 60s TTL; commit-service-owned; uses uniform idempotency-key shape |
| Validator pipeline | run EVT-V* full pipeline per [`05_validator_pipeline.md`](05_validator_pipeline.md); per-category subset for Proposal = full pipeline as input |
| Promotion | on Validated, commit fresh EVT-T1 Submitted via DP `advance_turn` carrying `origin_proposal_id` reference in metadata |
| Rejection | on Rejected, log + dead-letter per EVT-L6; ack the bus entry to prevent re-delivery |
| Expiry handling | bus cleanup process produces `ProposalExpired` dead-letter entries; commit-service does NOT poll for expired |
| Observability | emit metrics: `evt.proposal.consumed_total{outcome}`, `evt.proposal.validator_latency_ms`, `evt.proposal.pel_length` per consumer group |

---

## Locked-decision summary

| ID | Short name | One-line |
|---|---|---|
| EVT-L1 | Bus transport mechanism | Redis Streams via I13 outbox; reality-prefixed topics; per-cell granularity default |
| EVT-L2 | Lifecycle state machine | Proposal → Validated (commit fresh Submitted) / Rejected (dead-letter) / Expired (dead-letter); 60s retention default |
| EVT-L3 | Idempotency-based dedup | Uniform idempotency-key consumed by commit-service dedup cache; UUIDv4 proposal_id; producer reuses on retry |
| EVT-L4 | Per-stream FIFO ordering | Redis Streams natural ordering; cross-stream independent; encode dependency via causal-refs not stream order |
| EVT-L5 | Backpressure framework | Fail-fast at producer; XADD rejection → retry-with-backoff; PEL monitoring; no silent buffer growth |
| EVT-L6 | Dead-letter integration | Shared with EVT-V7 framework; proposals + rejected events use same destination + retention + replay |

---

## Cross-references

- [EVT-A6 typed causal-refs](02_invariants.md#evt-a6--causal-references-are-typed-single-reality-gap-free) — for cross-stream dependency encoding
- [EVT-A7 untrusted-origin pre-validation](02_invariants.md#evt-a7--untrusted-origin-events-require-pre-validation-lifecycle-reframed-2026-04-25) — invariant this file implements
- [EVT-T6 Proposal](03_event_taxonomy.md#evt-t6--proposal) — taxonomy entry
- [EVT-P6](04_producer_rules.md#evt-p6--proposal-evt-t6) — producer authorization
- [`05_validator_pipeline.md`](05_validator_pipeline.md) — EVT-V* + dead-letter framework EVT-V7
- [DP-A6 Python event-only](../06_data_plane/02_invariants.md#dp-a6--python-is-event-producer-only-for-game-state) — direction this file makes concrete
- [DP-A7 reality scoping](../06_data_plane/02_invariants.md#dp-a7--reality-boundary-in-cache-keys) — topic prefix discipline
- [DP-A4 Redis](../06_data_plane/02_invariants.md#dp-a4--redis-is-the-cache--pubsub--streams-technology) — transport choice
- [DP-A16 channel writer-node binding](../06_data_plane/02_invariants.md#dp-a16--channel-writer-node-binding-phase-4-2026-04-25) — per-cell consumer matching
- I13 outbox pattern (foundation invariant) — transport mechanism
- [PL_001 §14](../features/04_play_loop/PL_001_continuum.md) — idempotency cache pattern
- [DP-R6 backpressure](../06_data_plane/11_access_pattern_rules.md#dp-r6--backpressure-propagation-not-swallow-and-retry) — propagation discipline
- [`../05_llm_safety/`](../05_llm_safety/) — A6 internals run as part of validator pipeline on proposals
