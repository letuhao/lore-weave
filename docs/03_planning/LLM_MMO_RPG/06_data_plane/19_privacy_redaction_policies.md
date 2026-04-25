# 19 — Privacy Redaction Policy Templates (DP-Ch43..DP-Ch45)

> **Status:** LOCKED (Phase 4, 2026-04-25). Resolves [99_open_questions.md Q32](99_open_questions.md) — privacy bubble-up formalization. Builds on [DP-Ch30](16_bubble_up_aggregator.md#dp-ch30--privacy--redaction-patterns) (visibility flag exposed) and [DP-A18](02_invariants.md#dp-a18--channel-lifecycle-state-machine--canonical-membership-events-phase-4-2026-04-25) (canonical events). **No new axiom** — this file is a policy library implementing existing invariants.
> **Stable IDs:** DP-Ch43..DP-Ch45.

---

## Reading this file

[DP-Ch30](16_bubble_up_aggregator.md#dp-ch30--privacy--redaction-patterns) established the data shape: channels carry `visibility: Public/Private`; aggregators receive `source_visibility` on every `SourceEvent`; redaction is a feature-level decision. That's the floor.

This file adds the **policy template library** so most features pick a standard policy at registration rather than hand-writing redaction logic in every `on_event`. Three templates cover the common cases (Transparent / SkipPrivate / AnonymizeRefs); a `Custom` escape hatch handles the rare advanced cases.

---

## DP-Ch43 — `RedactionPolicy` enum + templates

### Definition

```rust
/// Declared at register_bubble_up_aggregator time. SDK applies the policy
/// in the runtime loop around each on_event invocation. Aggregator code
/// itself is policy-agnostic — it focuses on game logic, not redaction.
#[derive(Clone)]
pub enum RedactionPolicy {
    /// Default. No redaction. Aggregator sees all events; emits flow as-is.
    /// Acceptable for fully-public channel hierarchies (most public taverns/
    /// towns) and for aggregators that explicitly want full transparency.
    Transparent,

    /// Drop events from Private-visibility source channels BEFORE dispatch.
    /// Aggregator never sees Private events; on_event is not called for them.
    /// Use when the aggregator should be entirely oblivious to private
    /// activity (e.g., a public-noise-tracker that shouldn't know secret
    /// meetings exist).
    SkipPrivate,

    /// Pass all events through to on_event (aggregator state may update from
    /// private sources); SDK strips causal_refs whose source channel is
    /// Private from each EmitDecision before commit. Use when the aggregator
    /// should aggregate private-event signal but should NOT leak the source
    /// channel id in emitted causal references.
    AnonymizeRefs,

    /// Feature-defined filter. SDK calls filter.before_dispatch on each
    /// SourceEvent and filter.after_decision on each EmitDecision; either
    /// can return None to drop. Used for advanced redaction (per-actor
    /// rules, time-windowed visibility, etc.). Audit-logged on every drop.
    Custom(Arc<dyn RedactionFilter>),
}
```

### `RedactionFilter` trait

For `Custom(...)` policy:

```rust
pub trait RedactionFilter: Send + Sync + 'static {
    /// Stable identifier for audit log + telemetry. UPPER_SNAKE recommended.
    fn filter_id(&self) -> &'static str;

    /// Called pre-dispatch. Return Some(event) to dispatch (possibly modified),
    /// or None to skip silently. Default: pass-through.
    fn before_dispatch(&self, event: &SourceEvent) -> Option<SourceEvent> {
        Some(event.clone())
    }

    /// Called post-on_event for each EmitDecision. Return Some(decision) to
    /// commit (possibly modified), or None to drop. Default: pass-through.
    fn after_decision(
        &self,
        decision: &EmitDecision,
        source: &SourceEvent,
    ) -> Option<EmitDecision> {
        Some(decision.clone())
    }
}
```

Both methods have safe defaults — a feature can implement only the side it cares about (only pre-dispatch filtering, only post-decision filtering, or both).

### Default

If `register_bubble_up_aggregator` is called without specifying a policy, default is `Transparent` (preserves prior Phase 4 behavior). Backward-compatible — existing test fixtures and prior Phase 4 documentation remain accurate.

### Multiple aggregators on same parent

[DP-Ch25 H4c](16_bubble_up_aggregator.md#dp-ch25--bubbleupaggregator-trait--registerunregister-primitives) allows multiple aggregators per parent channel. Each carries **its own** `RedactionPolicy` — different aggregators on the same parent can have different policies. SDK applies the matching policy per aggregator.

---

## DP-Ch44 — Application semantics in the runtime loop

### Where policy slots into the runtime loop

Recall the [DP-Ch26](16_bubble_up_aggregator.md#dp-ch26--state-model-event-sourced--periodic-snapshots) loop:

```text
For each incoming SourceEvent:
  1. (Phase 4 + Q32) Apply policy.before_dispatch — possibly skip
  2. rng = deterministic_rng(source_channel_id, source_event_id)
  3. (next_state, decisions) = aggregator.on_event(state, event, rng)
  4. state := next_state
  5. (Phase 4 + Q32) Apply policy.after_decision per emit
  6. Commit surviving emits via writer
  7. snapshot if needed
```

The integration is precisely two filtering points (steps 1 and 5) keyed by the policy.

### `Transparent`

```text
Step 1: pass through (no-op)
Step 5: pass through (no-op)
```

No overhead beyond the trivial enum match.

### `SkipPrivate`

```text
Step 1:
  if raw_event.source_visibility == ChannelVisibility::Private {
      counters.redacted_event.inc(aggregator_type, "private", "SkipPrivate")
      return  // skip dispatch entirely
  }
  pass raw_event through
Step 5: pass through (no decisions need stripping; aggregator never saw private events)
```

Cheap. Aggregator state is fully oblivious to private activity.

### `AnonymizeRefs`

```text
Step 1: pass through (aggregator may aggregate signal from private sources)
Step 5:
  for each decision:
      if decision.causal_refs is None or empty:
          pass through (SDK auto-fills from triggering source per DP-Ch15;
          if source is private, SDK fills with empty refs instead)
      else:
          retain only refs whose source_channel.visibility == Public;
          if remaining refs is empty, replace with empty Vec
  if all causal_refs ended up empty for an emit:
      counters.redacted_decision.inc(aggregator_type, "anonymized")
```

Aggregator's state evolves normally from private signal; emitted events don't reveal which private channel triggered them. Per [DP-Ch30](16_bubble_up_aggregator.md#dp-ch30--privacy--redaction-patterns), default redaction is "empty out causal_refs" — simplest, most-private. Features that want richer "anonymized-but-cardinality-preserving" markers can use `Custom`.

### `Custom(filter)`

```text
Step 1:
  match filter.before_dispatch(&raw_event):
      Some(e) => dispatch e
      None    => audit_stream.log_redaction(filter.filter_id(), "event_skipped", &raw_event)
                 counters.redacted_event.inc(aggregator_type, "custom_filter")
                 skip dispatch
Step 5:
  for each decision:
      match filter.after_decision(&decision, &source):
          Some(d) => commit d
          None    => audit_stream.log_redaction(filter.filter_id(), "decision_dropped", &decision)
                     counters.redacted_decision.inc(aggregator_type, "custom_filter")
                     drop decision
```

Custom is the only policy that emits **full audit-stream entries** per redaction (not just counters). This lets ops review what feature-defined filters are doing — `Custom` filters are riskier than the static templates (they may have bugs).

### Composition with cascading bubble-up (DP-Ch29)

Bubble-up cascades from cell to tavern to town etc. Each level has its own aggregator with its own policy. Visibility-aware redaction applies independently at each level:

- Cell C is Private. C's aggregator (if any) follows its own policy.
- Tavern T's aggregator subscribes to children including C; sees C's events tagged `Private`. Applies T's policy.
- Town N's aggregator subscribes to T's children; sees T's events. T's events themselves are Public (if T is Public), regardless of whether they were derived from a Private cell. **Causal_refs are the only signal that survives across levels** — if T's aggregator stripped them via AnonymizeRefs, town N's aggregator sees no link back to private cell.

This cascade-redaction property is **emergent**, not enforced — it relies on each level's policy being set sensibly. A feature that wants strict private-cell secrecy must use SkipPrivate or AnonymizeRefs at every aggregator subscribing to potentially-Private sources.

---

## DP-Ch45 — Audit + observability + cascading visibility rule

### Telemetry (counters)

Built-in policies emit lightweight counters; full audit-stream entries are reserved for `Custom` filters.

```
dp.bubble_up.redacted_event_count{aggregator_type, source_visibility, policy}
dp.bubble_up.redacted_decision_count{aggregator_type, policy, reason}
```

`reason` enum: `private_source_skipped` · `private_refs_anonymized` · `custom_filter_drop_event` · `custom_filter_drop_decision`.

Dashboards plot redaction rate per aggregator type. Spike in `custom_filter_drop_*` with no corresponding feature change = investigate (filter logic may be over-aggressive).

### Audit stream — Custom only

Stream key: `dp:writer_audit:{reality_id}` (existing per [DP-Ch13](13_channel_ordering_and_writer.md#dp-ch13--writer-handoff--epoch-fencing-protocol)).

New entry shape for `Custom` policy redactions:

```json
{
  "type": "bubble_up_custom_redaction",
  "aggregator_id": "...",
  "aggregator_type": "...",
  "filter_id": "...",
  "redacted_what": "event" | "decision",
  "source_channel_id": "...",
  "source_event_id": 12345,
  "source_visibility": "private" | "public",
  "at": 1714003200123
}
```

Built-in policies (Transparent / SkipPrivate / AnonymizeRefs) do NOT write audit entries (counters are sufficient — behavior is fully specified).

### Visibility cascading rule

Per [L5a decision](99_open_questions.md): **visibility is per-channel, no inheritance.**

When a channel is created via `create_channel(parent, level_name, metadata)`:

- `metadata.visibility: ChannelVisibility` is read; defaults to `Public` if absent.
- The new channel's visibility is **independent of parent's visibility**.
- Inheritance, if desired, is the **feature's** responsibility — feature inspects parent's visibility and explicitly copies it to the child's metadata at creation time.

This trade-off:
- **Pros:** explicit, no surprises; changing parent's visibility doesn't silently change descendants' policies.
- **Cons:** feature must remember to set visibility on every child of a private channel; bug = leak.

**Recommendation for feature code:** centralize private-channel creation in a helper that always sets `metadata.visibility = Private` on children. This is a feature-level pattern, not a DP enforcement.

### Visibility changes are immutable post-creation

Channel visibility is set at `create_channel` time and not mutable thereafter. To "change visibility", feature dissolves the channel and creates a new one. This avoids the complexity of "what happens to in-flight aggregator state when visibility flips" (analogous to dissolution-is-terminal per DP-Ch31).

If a future use case needs visibility flip, it's a separate axiom-level decision (not Q32).

---

## Summary

| ID | What it locks |
|---|---|
| DP-Ch43 | `RedactionPolicy` enum (4 variants: `Transparent`, `SkipPrivate`, `AnonymizeRefs`, `Custom`); `RedactionFilter` trait with safe defaults; default = `Transparent` for backward compat; per-aggregator policy at registration time |
| DP-Ch44 | Application semantics in runtime loop — Transparent/SkipPrivate/AnonymizeRefs are pre/post filters with deterministic behavior; Custom uses feature-defined RedactionFilter; cascade-redaction is emergent (feature must set policy at each level for end-to-end secrecy) |
| DP-Ch45 | Telemetry counters for built-in policies; full audit-stream entries only for `Custom` policy redactions; visibility is per-channel (no inheritance); visibility immutable post-creation |

---

## Cross-references

- [DP-Ch30](16_bubble_up_aggregator.md#dp-ch30--privacy--redaction-patterns) — establishes data shape (visibility flag exposed); this file extends with policy templates
- [DP-Ch15](13_channel_ordering_and_writer.md#dp-ch15--causal-references-for-bubble-up-preview-full-design--q27) — `causal_refs` schema that AnonymizeRefs strips
- [DP-Ch25](16_bubble_up_aggregator.md#dp-ch25--bubbleupaggregator-trait--registerunregister-primitives) — `BubbleUpAggregator` trait + registration that this file extends with policy parameter
- [DP-Ch29](16_bubble_up_aggregator.md#dp-ch29--cascading--recursive-bubble-up) — cascading bubble-up where redaction policies compose
- [DP-A18](02_invariants.md#dp-a18--channel-lifecycle-state-machine--canonical-membership-events-phase-4-2026-04-25) — canonical events that flow through aggregators, including MemberJoined/MemberLeft from private channels
- [04_kernel_api_contract.md DP-K11](04_kernel_api_contract.md) — `register_bubble_up_aggregator` signature extended with policy parameter

---

## What this leaves to other Phase 4 items

| Q | Status |
|---|---|
| **Q32 privacy bubble-up** | ✅ Resolved here. |
| Q20 LLM latency | Deferred until V1 prototype data. |
| Q29 fan-out tuning | Independent — operational tuning, ops doc territory. |
| 🟢 nits Q23/Q24/Q25/Q33 | Independent — operational + security follow-ups. |

After Q32, Phase 4 design-level work has 1 deferred item (Q20) + 1 ops-doc item (Q29) + 4 nits = 6 remaining, all small or external-data-dependent. Feature design unblocked across the board.
