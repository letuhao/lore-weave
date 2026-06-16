# `dp-kernel-macros` — usage guide

> RAID cycle 17 / L4.B. Q-L4B-1 attribute syntax: `#[handles_event("npc.said")]`.

Two surfaces ship in V1:

1. `#[derive(Aggregate)]` — derives `dp_kernel::Aggregate` +
   `dp_kernel::AggregateMeta` for a struct.
2. `#[handles_event("type")]` — informational attribute on event-handler
   methods inside an aggregate's `impl` block.

## `#[derive(Aggregate)]`

### Required field shape

The struct MUST have:

| Field | Type | Used for |
|---|---|---|
| `id` | `String` (or any `AsRef<str>`) | `AggregateMeta::id()` |
| `version` | `u64` | `Aggregate::aggregate_version()` + bumped by derived `apply()` |

### Default `aggregate_type`

Lowercased struct ident:

```rust
#[derive(Aggregate)] struct World { id: String, version: u64 }
// World::aggregate_type() == "world"
```

### Override `aggregate_type`

Two equivalent syntaxes (name-value preferred):

```rust
#[derive(Aggregate)]
#[aggregate_type = "geo_region"]
struct Region { id: String, version: u64 }

#[derive(Aggregate)]
#[aggregate_type("npc_session")]
struct NpcSession { id: String, version: u64 }
```

### What the derive emits

A minimal version-bump `Aggregate::apply()` and a paired `AggregateMeta`
impl:

```rust
impl dp_kernel::Aggregate for Counter {
    fn apply(&mut self, env: &dp_kernel::EventEnvelope) -> Result<(), String> {
        self.version = env.aggregate_version;
        Ok(())
    }
    fn aggregate_version(&self) -> u64 { self.version }
}
impl dp_kernel::AggregateMeta for Counter {
    fn aggregate_type() -> &'static str { "counter" }
    fn id(&self) -> &str { AsRef::<str>::as_ref(&self.id) }
}
```

### Composing with user logic

V1 derive does NOT auto-dispatch on `event.event_type`. Write a thin
wrapper method that owns the dispatch, then call back into the derived
`apply()` to bump the version:

```rust
impl Counter {
    #[handles_event("counter.incremented")]
    fn apply_incremented(&mut self, env: &EventEnvelope) -> Result<(), String> {
        let delta = env.payload.get("delta").and_then(|v| v.as_i64())
            .ok_or_else(|| "missing 'delta'".to_string())?;
        self.value += delta;
        <Self as Aggregate>::apply(self, env) // version-bump
    }
}
```

Cycle 21 (L4.D) will extend the derive to scan `#[handles_event]` attrs and
emit the dispatch automatically. V1 keeps the surface minimal so the trait
contract is locked in without coupling to a code-gen design that's still
evolving.

## `#[handles_event("type")]`

Attached to methods inside an `impl` block. **V1 is inert** — the macro
validates the literal-string payload (so misspellings like
`#[handles_event = "x"]` or `#[handles_event(42)]` surface as friendly
errors) but does NOT alter the method body.

Multiple attrs per method are supported via stacking:

```rust
#[handles_event("counter.reset")]
#[handles_event("counter.zeroed")]
fn apply_reset(&mut self, env: &EventEnvelope) -> Result<(), String> { … }
```

## Error messages

The derive's diagnostics are span-tracked. Common errors:

| Error | Cause | Fix |
|---|---|---|
| `requires named fields` | Tuple struct or unit struct | Switch to named-field struct |
| `requires a field named id` | Missing `id` field | Add `id: String` |
| `requires a field named version: u64` | Missing version field | Add `version: u64` |
| `#[aggregate_type] expects a string literal` | Passed a non-string | Use `#[aggregate_type = "world"]` |

## What is NOT in cycle 17

- `#[derive(Projection)]` — cycle 21.
- Auto-dispatch from `#[handles_event]` — cycle 21.
- UI snapshot tests via `trybuild` — skeleton present, snapshots land
  alongside the auto-dispatch work in cycle 21.
