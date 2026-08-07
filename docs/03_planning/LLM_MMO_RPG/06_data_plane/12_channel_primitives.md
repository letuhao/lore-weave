# 12 — Channel Primitives (DP-Ch1..DP-Ch10)

> **Status:** LOCKED (Phase 4, 2026-04-25). Resolves [99_open_questions.md Q26](99_open_questions.md) — channel hierarchy as first-class DP concept. Implements axioms [DP-A13](02_invariants.md#dp-a13--channel-hierarchy-as-first-class-scope-phase-4-2026-04-25) and [DP-A14](02_invariants.md#dp-a14--aggregate-scope-reality-scoped-vs-channel-scoped-design-time-choice-phase-4-2026-04-25).
> **Stable IDs:** DP-Ch1..DP-Ch10.

---

## Reading this file

Channels are the game's nested social contexts — cell session inside tavern inside town inside district inside country inside continent, rooted at the reality. This file locks the DP-level primitives: identity type, tree schema, registry ownership, scope marker traits, cache-key format, SessionContext extension, and the SDK primitives that manipulate channel state.

It does **not** lock: per-channel event ordering (→ Q17/Q30), writer node binding per channel (→ Q34), turn/page boundary primitives (→ Q15), bubble-up aggregator (→ Q27), pause semantics (→ Q19), membership validation rules (→ Q28), lifecycle details (→ Q31), or privacy rules on bubble-up (→ Q32). Those are separate Phase 4 items that build on the primitives here.

---

## DP-Ch1 — ChannelId and tree structure

### ChannelId newtype

```rust
/// Channel identifier. Newtype with module-private constructor — cannot be
/// forged by feature code. Produced only by the SDK during channel-tree
/// resolution (at bind_session or on delta-stream updates).
///
/// ⚠ AMENDED 2026-08-07 (REC-102a, PO-approved): the payload is `i64`, not
/// `Uuid`. Three artifacts disagreed and two of the three said 64-bit — the
/// shipped `crates/dp-kernel/src/channel.rs`, and the client wire contract
/// (`contracts/game-wire/common.schema.json`, `Uint64String`). The build is
/// right on substance: DP-Ch11's allocator is a monotonic per-channel COUNTER
/// seeded from MAX(), which is what a BIGINT is for; a Uuid cannot be
/// incremented. So the spec adopts i64 rather than the code adopting Uuid.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Hash)]
pub struct ChannelId(pub(crate) i64);

impl ChannelId {
    /// Reserved: the root channel of a reality. Stable per-reality derivation
    /// so reality-scoped aggregates can reference an implicit root without
    /// an extra CP lookup.
    pub fn reality_root(reality_id: &RealityId) -> Self { /* deterministic derivation */ }

    /// Read the raw BIGINT — needed to bind it as a query parameter.
    pub fn get(self) -> i64 { self.0 }

    pub(crate) fn new_verified(raw: i64) -> Self { Self(raw) }
}
```

> **⚠ AMENDED 2026-08-07 (REC-102a) — the SHIPPED type had a `pub` field, and the privacy is the
> whole point.** `crates/dp-kernel/src/channel.rs` declared `pub struct ChannelId(pub i64)`, so any
> caller could write `ChannelId(7)`. That deletes exactly the property this section claims — *"cannot
> be forged by feature code"* — and it is the property `DP-A12` rests the whole cross-reality
> argument on for the parallel `RealityId`. **It is the third occurrence of one shape this week**:
> `SEALED-SUBJECT` on the proposal's `actor`, `PID-D5` on `event_category`, and here — *a value whose
> supplier is also its judge.*
>
> **Applied to the code in the same commit.** The field is now `pub(crate)`, with `get()` for the
> query-binding read. Because `new_verified`'s caller — SDK channel-tree resolution against the
> `channels` table — **does not exist yet** (`crates/dp` is unbuilt, and `channels` has no migration),
> the code carries a deliberately-named, greppable `ChannelId::unverified(i64)` instead:
>
> - It does **not** claim safety. It makes the unverified mints **countable**. Measured
>   2026-08-07 — `rg -c 'ChannelId::unverified' --type rust` over `crates/` + `services/`:
>   **22 call sites**, and the shape of the list is the useful part. **18 are tests**; three of the
>   remaining four are operator CLIs (`bin/spine.rs`, `bin/ceilings.rs`). **The load-bearing one is
>   exactly one line** — `services/commit-service/src/manager.rs`, where the channel arrives **from
>   the wire**, which is `SEALED-SUBJECT`'s site verbatim, now visible instead of invisible.
> - When `crates/dp` lands, the function is deleted and the compiler enumerates the migration.
> - `new_verified` is deliberately **not** declared in the code yet: an unused constructor for a model
>   nothing produces is the orphan shape `scripts/orphan-model-gate.py` refuses.

Parallel shape to [`RealityId`](04a_core_types_and_session.md#realityid) (see [DP-K1](04a_core_types_and_session.md#dp-k1--core-types)) — same module-privacy story, same newtype discipline, compile-time forgery prevention.

### Tree structure

A reality's channel tree is a strict tree (not a DAG): every channel except the root has exactly one parent. Nodes carry metadata:

```rust
pub struct Channel {
    pub id: ChannelId,
    pub parent: Option<ChannelId>, // None for root
    pub reality_id: RealityId,
    pub level_name: String,        // free-form tag ("tavern", "cell", ...)
    pub display_name: Option<String>, // human-readable, optional
    pub depth: u8,                 // root = 0
    pub lifecycle: ChannelLifecycle, // Active | Dormant | Dissolved — full state machine in [17_channel_lifecycle.md](17_channel_lifecycle.md)
    pub metadata: serde_json::Value, // feature-level bag; DP does not interpret
    pub created_at: Timestamp,
    pub dissolved_at: Option<Timestamp>,
}

pub enum ChannelLifecycle { Active, Dormant, Dissolved }
```

Tree invariants:

- **Single root per reality.** Root's `id == ChannelId::reality_root(reality_id)`, `parent == None`, `level_name` conventional (e.g., `"reality"`).
- **No cycles.** Enforced by `depth` field (root = 0, children = parent.depth + 1) + referential integrity on `parent`.
- **Max depth ≤16.** Protects against pathological trees; feature-level books declaring deeper trees fail validation.
- **Dissolution is terminal.** A `Dissolved` channel cannot be re-activated; its events archive per 02_storage retention (→ Q33).

---

## DP-Ch2 — Channel registry (per-reality DB schema)

Lives in each reality's own Postgres database (the same DB that holds the reality's event log and projections). Owned by the reality's own data plane, not CP.

```sql
-- In each per-reality DB
CREATE TABLE channels (
    reality_id    UUID     NOT NULL,           -- ⚠ ADDED (REC-105)
    id            BIGINT   NOT NULL,           -- ⚠ AMENDED (REC-103): was UUID
    parent        BIGINT,
    level_name    TEXT NOT NULL,
    display_name  TEXT,
    depth         SMALLINT NOT NULL,          -- ⚠ CHECK moved below and NAMED (REC-105)
    lifecycle     TEXT     NOT NULL,          -- ⚠ CHECK moved below and NAMED (REC-105)
    metadata      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    dissolved_at  TIMESTAMPTZ,

    -- ⚠ ADDED (REC-106): not a fact about this channel — a fact about the one it
    -- claims as a parent, GENERATED from this row so it cannot disagree with
    -- `depth`. The root's value is -1 and no row can match it; the root does not
    -- need one, because its `parent` is NULL and the FK below is MATCH SIMPLE.
    parent_depth  SMALLINT GENERATED ALWAYS AS ((depth - 1)::smallint) STORED,

    PRIMARY KEY (reality_id, id),             -- ⚠ AMENDED (REC-105)

    -- ⚠ ADDED (REC-106): the FK's target, and its only purpose. `(reality_id,
    -- id)` is already unique; Postgres still requires a declared unique
    -- constraint on the exact referenced column list.
    CONSTRAINT channels_id_depth_uq UNIQUE (reality_id, id, depth),

    -- ⚠ AMENDED (REC-105): composite, so a channel in reality A cannot claim a
    -- parent in reality B.
    -- ⚠ AMENDED (REC-106): `parent_depth` joins the key, and that is DP-Ch1's
    -- own sentence (:97) turned into SQL. Along every parent edge depth
    -- decreases by exactly one, so a cycle of length k would need `d = d - k`.
    -- A cycle is not rejected — it is not REPRESENTABLE, including the one-node
    -- case. DEFERRABLE because a parent's depth is referenced by its children,
    -- so a subtree move must pass through an inconsistent middle; that does not
    -- weaken the guarantee, since the impossibility is arithmetic and a deferred
    -- cycle still fails at COMMIT.
    CONSTRAINT channels_parent_fk FOREIGN KEY (reality_id, parent, parent_depth)
        REFERENCES channels (reality_id, id, depth)
        DEFERRABLE INITIALLY IMMEDIATE,

    CONSTRAINT channels_depth_bounded CHECK (depth >= 0 AND depth <= 16),
    CONSTRAINT channels_lifecycle_known
        CHECK (lifecycle IN ('active', 'dormant', 'dissolved')),
    CONSTRAINT channels_no_orphan CHECK (
        (parent IS NULL AND depth = 0) OR (parent IS NOT NULL AND depth > 0)
    ),

    -- ⚠ ADDED (1b5-M4): `REC-103` carried the wire contract's WIDTH across and
    -- not its DOMAIN.
    CONSTRAINT channels_id_positive CHECK (id > 0),
    CONSTRAINT channels_level_name_nonempty CHECK (length(btrim(level_name)) > 0),

    -- ⚠ ADDED (1b7gap-L1): the domain was fixed at ONE end. `id = i64::MAX` was
    -- accepted and then `SELECT MAX(id) + 1` — the shape any allocator for this
    -- column will have — dies with `bigint out of range`. Reserving the top value
    -- means a successor always exists. NOTE: `contracts/game-wire/common.schema.json`
    -- types `Uint64String` as `^(0|[1-9][0-9]{0,19})$`, which admits `0` and
    -- values past `i64::MAX`; the column is the narrower of the two, which is the
    -- safe direction, and the contract needs the amendment.
    CONSTRAINT channels_id_allocatable CHECK (id < 9223372036854775807),

    -- ⚠ ADDED (1b7db-02): the assertion that makes `channels_parent_fk`'s
    -- arithmetic a fact about DATA rather than about DDL. `ALTER COLUMN
    -- parent_depth DROP EXPRESSION` needs only table ownership — no superuser,
    -- no rewrite — and then a caller supplies `parent_depth` by hand and a
    -- self-parent inserts in one statement. A CHECK survives DROP EXPRESSION.
    -- Vacuous only while the expression exists, which is exactly the condition
    -- it exists to outlive.
    -- ⚠ `IS NOT NULL` ADDED (1b12-03): `parent_depth` is NULLABLE, so after
    -- DROP EXPRESSION you do not FORGE a value — you OMIT the column. The CHECK
    -- then evaluates to NULL (not FALSE, so it passes) and the MATCH SIMPLE FK
    -- skips a key with a NULL member. A self-parent and a 2-cycle both INSERT,
    -- under a constraint reporting convalidated = t. The previous leg tested the
    -- exact probe its author imagined; the hole was one step to the side.
    CONSTRAINT channels_parent_depth_derived
        CHECK (parent_depth IS NOT NULL AND parent_depth = depth - 1),

    -- ⚠ REMOVED (REC-106): `channels_no_self_parent CHECK (parent IS NULL OR
    -- parent <> id)` stood here. `channels_parent_fk` now makes it unable to
    -- fail — a self-parented row would need a row with its own id at its own
    -- depth minus one, and `id` is unique per reality — and a CHECK that cannot
    -- reject anything is `NV-1`. That is `1bF-2`'s defect, in the same table,
    -- and keeping it for readability is how it got there the first time.

    -- ⚠ ADDED (REC-105), DP-Ch31..Ch37 (17_channel_lifecycle.md): a dissolved
    -- channel has a dissolution time and
    -- a live one does not. A biconditional, so neither direction can rot.
    CONSTRAINT channels_dissolved_at_iff_dissolved CHECK (
        (lifecycle = 'dissolved') = (dissolved_at IS NOT NULL)
    )
);

-- ⚠ AMENDED (REC-104): `CONSTRAINT channels_root_single UNIQUE (id) DEFERRABLE
-- INITIALLY DEFERRED` stood here and was VACUOUS — `id` is already the primary
-- key, so it could never fire, while its NAME states the real DP-Ch1 invariant
-- (a strict tree has exactly one root). This is that constraint, made able to
-- fail. A partial unique index is the only form Postgres offers for it.
-- ⚠ AMENDED (REC-105): keyed on `reality_id`, so the invariant is ONE ROOT PER
-- REALITY. Keyed on a constant it would have been one root per DATABASE, which
-- is a different and wrong claim once the table carries `reality_id`.
-- ⚠ NOTED (1b5-L3): this index ignores `lifecycle`, and DP-Ch33 keeps a
-- dissolved row indefinitely, so dissolving a reality's root FORECLOSES that
-- reality. Correct, and written down so it is a decision: DP-Ch11 never reissues
-- an id, and a `lifecycle <> 'dissolved'` predicate would let a reality be
-- re-rooted while the old tree's events still reference the old root.
-- ⚠ NOTED (REC-106): this index gives AT MOST one root. The parent FK gives AT
-- LEAST one for any non-empty reality — walk `parent` and depth strictly
-- decreases, so the walk terminates, and only `depth = 0` can terminate it,
-- which `channels_no_orphan` forces to be a root. Together: EXACTLY one.
CREATE UNIQUE INDEX channels_root_single ON channels (reality_id)
    WHERE parent IS NULL;

CREATE INDEX channels_parent_idx ON channels(reality_id, parent);
CREATE INDEX channels_level_idx ON channels(reality_id, level_name) WHERE lifecycle = 'active';
CREATE INDEX channels_lifecycle_idx ON channels(reality_id, lifecycle);
```

⚠ **ADDED (`1b5-L5`) — the two lifecycle rules `DP-Ch31` names and no row-level
mechanism enforced.** [`17_channel_lifecycle.md:57`](17_channel_lifecycle.md)
locks *Dissolved → (any)* as *"terminal, no transitions"* and `:77` attributes it
to a *"row-level rule"*; `:55` requires *"all descendants Dissolved"* before a
dissolution. Both are statements about a TRANSITION, which a `CHECK` cannot see,
and until `1b.5` both fell to a plain `UPDATE` while `:77` named a mechanism that
existed nowhere. The rule is a `BEFORE INSERT OR UPDATE` trigger — in the DB
and not only in the SDK, because `DP-Ch31` says *"row-level rule **+** SDK
transition validator"*, and an SDK-only check is one the next writer to reach
this table does not have.

⚠ **AMENDED 2026-08-08 (`1b7gap-H3`) — there are THREE rules, and the third is
what makes the other two's induction argument true rather than merely stated.**
This section originally justified checking CHILDREN rather than descendants by
claiming *"a child may only reach Dissolved when its own children are, so by
induction a Dissolved channel's whole subtree is Dissolved."* **That was false.**
Induction over TRANSITIONS says nothing about CREATION, and the trigger fired
`BEFORE UPDATE OF lifecycle` only. Measured on a live Postgres 18: dissolve
channel 2, then `INSERT (id 3, parent 2, 'active')` → `INSERT 0 1` — a live child
under a dissolved parent, which the state table above forbids in its own
precondition column (*"parent exists, parent not Dissolved"*) and which nothing
implemented. The trigger is now `BEFORE INSERT OR UPDATE` rather than
`UPDATE OF lifecycle`, because an `UPDATE OF lifecycle` trigger does not fire
when only `parent` changes — re-parenting under a dissolved node was the same
hole through a second door.

⚠ **`FOR UPDATE` and `AFTER INSERT` ADDED 2026-08-08 (`1b12-02`, `1b12-01`) — two
independent routes past the rule above, neither needing DDL or superuser.**
*(a)* Both guards were **unlocked predicate reads**, so plain READ COMMITTED
write-skew defeated them: T1 inserts a child under an active parent (reads
`active`, passes, uncommitted) while T2 dissolves that parent (`DP-Ch33`'s
`EXISTS` cannot see T1's row, passes). Both commit. **Two predicate reads that
each pass are not the same as the conjunction holding.** Locking the parent row
makes both paths contend on one row in either order. *(b)* Both guards only
inspected rows that ALREADY EXIST, so **reversing the insert order** inside the
sanctioned `SET CONSTRAINTS ... DEFERRED` hatch smuggled a dissolved parent in
underneath an already-inserted live child — and since `DP-Ch33` checks children
rather than descendants *on the strength of this rule*, every ancestor could then
be dissolved legally, leaving a fully dissolved tree with a live leaf.

```sql
CREATE OR REPLACE FUNCTION channels_lifecycle_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE parent_lifecycle TEXT;
BEGIN
    IF NEW.parent IS NOT NULL
       AND (TG_OP = 'INSERT' OR NEW.parent IS DISTINCT FROM OLD.parent) THEN
        SELECT c.lifecycle INTO parent_lifecycle FROM channels c
         WHERE c.reality_id = NEW.reality_id AND c.id = NEW.parent
           FOR UPDATE;                       -- 1b12-02: serialises against a concurrent dissolve
        IF parent_lifecycle = 'dissolved' THEN
            RAISE EXCEPTION 'channels_no_child_of_dissolved: ...' USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    IF TG_OP = 'INSERT' THEN
        RETURN NEW;
    END IF;
    IF OLD.lifecycle = 'dissolved' AND NEW.lifecycle <> 'dissolved' THEN
        RAISE EXCEPTION 'channels_dissolved_is_terminal: ...' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER channels_lifecycle_guard_trg
    BEFORE INSERT OR UPDATE ON channels
    FOR EACH ROW EXECUTE FUNCTION channels_lifecycle_guard();
```

⚠ **`DP-Ch33` is a SEPARATE, `AFTER`, CONSTRAINT trigger, and the shape is the
finding (`1b7db-07`).** As a `BEFORE`-row check this rule made a legitimate
operation *impossible* rather than merely awkward: dissolving a subtree in one
statement failed in **every** row order, including an explicit leaf-first
`ORDER BY depth DESC`, because a `BEFORE`-row trigger cannot see the other rows
the same command is updating. The only working shape was N separate single-row
statements — nowhere documented, and not something a caller would guess. A
constraint trigger fires at the **end of the statement**, so it sees the whole
effect; it is also `DEFERRABLE`, so a subtree dissolved across several statements
can defer to `COMMIT`. Same escape hatch as `channels_parent_fk`, same reason,
and it does not weaken the rule because the final state is still checked.

```sql
CREATE OR REPLACE FUNCTION channels_dissolve_order_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM channels c
                WHERE c.reality_id = NEW.reality_id AND c.parent = NEW.id
                  AND c.lifecycle <> 'dissolved') THEN
        RAISE EXCEPTION 'channels_dissolve_descendants_first: ...' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS channels_dissolve_order_trg ON channels;
CREATE CONSTRAINT TRIGGER channels_dissolve_order_trg
    AFTER INSERT OR UPDATE OF lifecycle ON channels
    DEFERRABLE INITIALLY IMMEDIATE
    FOR EACH ROW
    WHEN (NEW.lifecycle = 'dissolved')
    EXECUTE FUNCTION channels_dissolve_order_guard();
```

> ## ⚠ `REC-103` — `id` is `BIGINT`, not `UUID`, and this is the amendment `REC-102a` implied
>
> `REC-102a` (PO-approved 2026-08-07) settled `ChannelId`'s payload as **`i64`**, on three grounds
> measured at the time: the shipped `crates/dp-kernel/src/channel.rs` declares
> `pub struct ChannelId(pub(crate) i64)`; the client wire contract
> (`contracts/game-wire/common.schema.json`) types it `Uint64String`; and **`DP-Ch11`'s allocator is a
> monotonic per-channel COUNTER seeded from `MAX()`** — which is what a `BIGINT` is for and which a
> `Uuid` cannot do, because a `Uuid` cannot be incremented.
>
> That decision was applied to `DP-Ch1`'s newtype and to the code in the same commit. **It never
> reached this schema**, thirty lines below, which continued to declare `UUID` — so the one artifact a
> migration would be written from still said the thing `REC-102a` had ruled false. Found by slice 1b's
> Phase 0 (`1bF-1`) before any migration existed, which is the only reason it is an amendment rather
> than a schema.
>
> **This is `FLOW-2`'s shape from the inside:** a correction decided, applied where the author was
> looking, and not applied where they were not. `REC-102a` is why `spec_oracle` now compares documents
> to code; `1b.3` extends that to compare *this SQL* to the migration's SQL, so the next time these
> two disagree a test says so rather than a reader noticing eight weeks later.


> ## ⚠ `REC-105` — the table carries `reality_id`, and the spec did not
>
> **Derived from the shipped tables, not chosen.** Every other migration in
> `contracts/migrations/per_reality/` carries `reality_id UUID NOT NULL` inside its primary key —
> `events` is `PRIMARY KEY (reality_id, aggregate_type, aggregate_id, …)`, and `channel_writer_state`
> is `PRIMARY KEY (reality_id, channel_id)`. The directory's README states no reason for it.
>
> **`DP-Ch2` as written made `FLOW-19` unfixable by the migration that exists to fix it.** With
> `channels` keyed on `id` alone, a foreign key from `channel_writer_state (reality_id, channel_id)`
> is **not expressible** — so writing the spec literally would have shipped the table and left the
> lease still dangling, which is the exact defect `1b` was opened for.
>
> The composite key follows, and so do three things it makes possible: the parent FK becomes
> `(reality_id, parent) → (reality_id, id)`, which is what stops a channel claiming a parent in
> another reality; `channels_root_single` becomes **one root per reality** rather than one per
> database; and `DP-Ch11`'s `MAX()+1` allocator becomes per-reality, which is what a per-reality
> counter means.
>
> ⚠ **This is the one amendment in `1b` that is a judgement rather than a correction**, and it is
> recorded as such. If the intent is genuinely one database per reality with `reality_id` redundant,
> this shape is wrong — and it is cheap to change now, because **nothing has been applied to a real
> database**: the migration has only ever run against a throwaway. Say so and it comes out.
>
> Also added here because the live-smoke asked every constraint to fail and two had nothing to say:
> `channels_no_self_parent` (a self-parented row at `depth > 0` satisfies `channels_no_orphan`, and a
> one-node cycle is the cheapest way to make the tree a graph) and
> `channels_dissolved_at_iff_dissolved` (the `DP-Ch31`..`DP-Ch37` lifecycle, as a biconditional so neither
> direction can rot).

> ## ⚠ `REC-104` — `channels_root_single` was a check that could not fail
>
> The constraint read `UNIQUE (id) DEFERRABLE INITIALLY DEFERRED`. `id` is the **primary key**, so
> uniqueness on it is already total: the constraint added nothing, could never reject a row, and had
> been sitting in a LOCKED document since Phase 4.
>
> Its **name** is the tell, and it names a real invariant. `DP-Ch1`: *"A reality's channel tree is a
> strict tree (not a DAG): every channel except the root has exactly one parent."* Exactly one root
> means exactly one row with `parent IS NULL` — and **nothing enforced that**. `channels_no_orphan`
> is adjacent but weaker: it forbids a root at `depth != 0` and an orphan at `depth > 0`, and permits
> any number of roots.
>
> Replaced with the partial unique index above, which is the only shape Postgres offers for
> *"at most one row satisfying a predicate"*. It is `1b.4`'s first bite: drop it, insert a second
> root, watch it succeed.
>
> **Recorded rather than quietly fixed**, because this is `NV-1` — *a check that cannot fail is not a
> check* — inside a LOCKED spec, predating this run entirely. `docs/standards/non-vacuity.md` was
> written about the code tier; this is the same defect in the design corpus, and it suggests the
> standard's reach is shorter than its subject.

**Why per-reality DB and not CP:**

- Cell creation can be frequent (~10–100/minute per active reality). Putting this on CP makes CP a serialization point for channel churn → violates [DP-A2](02_invariants.md#dp-a2--control-plane--data-plane-split) "CP not on hot path."
- Channel operations are naturally reality-local — a cell in reality A doesn't affect reality B. Scaling per-reality matches the reality-scoped Postgres sharding already in [02_storage/R4](../02_storage/R04_fleet_ops.md).
- CP still knows about all channels via its cache (DP-Ch3), refreshed lazily + on delta stream.

**Writes to this table** happen via the SDK's channel-CRUD primitives (DP-Ch8), not via raw SQL. The SDK is the only writer; feature code goes through SDK.

---

## DP-Ch3 — CP channel tree cache + delta stream

CP holds a **cached snapshot** of every active reality's channel tree for fast `bind_session` handshake and for resolving ancestor chains. CP does NOT own the tree — it is a consumer of the per-reality registry.

### Cache shape

Per reality, CP holds:

- Full `Vec<Channel>` (all active channels) in memory
- Derived ancestor-chain map: `HashMap<ChannelId, Vec<ChannelId>>` (fast lookup for any channel → path to root)
- Version counter + last-sync timestamp

Size estimate: ~200–500 channels × ~300 bytes × 1000 active realities = ~150 MB in CP memory. Comfortable.

### Sync protocol

**Initial sync** — on reality warm (`frozen → active` per [DP-C7](05_control_plane_spec.md#dp-c7--cold-start-coordination)):

1. CP opens a read connection to the reality's Postgres.
2. `SELECT * FROM channels WHERE lifecycle IN ('active', 'dormant')`.
3. Build in-memory tree + ancestor map; record version = now.

**Delta stream** — during active reality life:

1. Reality's SDK emits a structured event `channel_tree_change { op: Insert|Update|Dissolve, channel: Channel }` onto a dedicated Redis Stream `dp:channel_changes:{reality_id}`.
2. CP consumes this stream with a durable cursor per reality.
3. On each event, CP updates its in-memory tree + invalidates the ancestor map for affected subtree.

### Serving to SDK

When an SDK calls `bind_session(reality_id, session_id, current_channel_id)`:

1. CP looks up `current_channel_id` in its cache for that reality.
2. CP returns the resolved ancestor chain + JWT with scope claims including `allowed_channels`.
3. SDK stores chain in `SessionContext.ancestor_channels`.

**SDK-side delta subscription** — an SDK can subscribe to `StreamChannelTreeUpdates(reality_id)` (new gRPC method on [DP-C3](05_control_plane_spec.md#dp-c3--grpc-service-surface)). CP forwards filtered channel-tree changes; SDK refreshes its own local ancestor cache.

### Degraded-mode

If CP is unreachable (per [DP-F3](07_failure_and_recovery.md#dp-f3--control-plane-outage--recovery)):
- Existing `SessionContext` ancestor chains remain valid (they were resolved at bind time).
- `move_session_to_channel` to a previously-unseen channel fails with `DpError::ControlPlaneUnavailable` — SDK cannot verify the target channel exists.
- Channel CRUD (create/dissolve) continues locally against per-reality DB; delta stream backlogs in Redis Stream; CP catches up on recovery.

---

## DP-Ch4 — Scope marker traits

```rust
/// Marker: aggregate is identified by (reality_id, aggregate_id).
/// Aggregate follows the reality, not any channel. Default scope.
pub trait RealityScoped: Aggregate {}

/// Marker: aggregate is identified by (reality_id, channel_id, aggregate_id).
/// Aggregate lives in a specific channel.
pub trait ChannelScoped: Aggregate {}
```

**Exclusivity:** an aggregate type implements **exactly one** of these. Enforced via `#[derive(Aggregate)]` macro:

```rust
#[derive(Aggregate)]
#[dp(scope = "reality", tier = "T2")]
pub struct PlayerInventory {
    pub player_id: PlayerId,
    pub items: Vec<Item>,
}
// -> generates: impl RealityScoped for PlayerInventory {}

#[derive(Aggregate)]
#[dp(scope = "channel", tier = "T2")]
pub struct ChatMessage {
    pub author: PlayerId,
    pub body: String,
}
// -> generates: impl ChannelScoped for ChatMessage {}
```

Accidentally declaring `#[dp(scope = "reality_and_channel")]` fails macro compilation with a clear error.

**Note on tier × scope orthogonality:**

- `PlayerInventory` is (T2, Reality) — durable, reality-scoped.
- `ChatMessage` is (T2, Channel) — durable, channel-scoped.
- `TypingIndicator` is (T0, Channel) — ephemeral, channel-scoped.
- `ReputationScore` is (T3, Reality) — durable-sync, reality-scoped (money-adjacent).

All 4 tiers × 2 scopes = 8 combinations, all valid.

---

## DP-Ch5 — Cache key format with scope marker

```
Reality-scoped:   dp:{reality_id}:r:{tier}:{aggregate_type}:{aggregate_id}[:subkey]
Channel-scoped:   dp:{reality_id}:c:{channel_id}:{tier}:{aggregate_type}:{aggregate_id}[:subkey]
```

The `r` / `c` marker at position 2 makes keys self-describing for debugging + operator tooling.

Macro `dp::cache_key!` is updated to dispatch on scope:

```rust
// Compile-time: macro knows scope from the aggregate type's trait impl
dp::cache_key!(ctx, T2, PlayerInventory, player_id)
// -> "dp:{reality}:r:t2:player_inventory:{player_id}"  (RealityScoped)

dp::cache_key!(ctx, T2, ChatMessage, msg_id; channel = tavern_id)
// -> "dp:{reality}:c:{tavern_id}:t2:chat_message:{msg_id}"  (ChannelScoped, channel arg required)
```

Macro compile-error cases:
- Passing `channel = ...` argument for a `RealityScoped` aggregate → rejected.
- Omitting `channel = ...` for a `ChannelScoped` aggregate → rejected.
- Passing a `ChannelId` that does not match the scope → rejected (type-level).

**Supersession:** [DP-A7](02_invariants.md#dp-a7--reality-boundary-in-cache-keys) is extended (not withdrawn) — the original "reality_id first" invariant still holds; scope marker `r`/`c` is inserted at position 2.

---

## DP-Ch6 — SessionContext extension

```rust
#[derive(Clone)]
pub struct SessionContext {
    // Existing (Phase 2, DP-K2):
    reality_id: RealityId,
    session_id: SessionId,
    node_id: NodeId,
    capability: CapabilityToken,
    bound_at: Instant,

    // NEW (Phase 4, DP-Ch6):
    current_channel_id: ChannelId,
    ancestor_channels: Vec<ChannelId>, // [current, parent, grandparent, ..., root]
}

impl SessionContext {
    pub fn current_channel(&self) -> &ChannelId { &self.current_channel_id }

    /// Ancestor chain INCLUDING current. First element = current, last = root.
    pub fn ancestor_chain(&self) -> &[ChannelId] { &self.ancestor_channels }

    /// Is `target` an ancestor (inclusive of current) of this session's channel?
    /// Used for visibility checks — events from target reach this session.
    pub fn is_ancestor(&self, target: &ChannelId) -> bool {
        self.ancestor_channels.contains(target)
    }
}
```

**Ancestor chain depth** = tree depth ≤ 16, so `Vec<ChannelId>` is small and cheap to clone.

**Mutation:** SessionContext is effectively immutable during its lifetime; to change channel, SDK issues `move_session_to_channel` which **creates a new SessionContext** (new ancestor chain, same session_id + capability-refresh if needed). Callers swap in the new context for subsequent ops.

---

## DP-Ch7 — Channel ancestor lookup

SDK exposes a synchronous helper for feature code that needs to walk the chain:

```rust
impl SessionContext {
    /// Walk ancestors starting from current, returning Some(channel_id) when
    /// the predicate matches; None if no ancestor matches.
    pub fn find_ancestor<F>(&self, predicate: F) -> Option<&ChannelId>
        where F: Fn(&ChannelId) -> bool;

    /// Ancestor at a given depth from root (0 = root, depth_from_root increases downward).
    /// None if depth exceeds the chain.
    pub fn ancestor_at_depth(&self, depth_from_root: u8) -> Option<&ChannelId>;
}
```

For richer queries (e.g., "find the nearest ancestor whose `level_name` is `'tavern'`"), feature code calls `read_projection_reality::<Channel>(ctx, channel_id)` and inspects metadata — channel metadata is a RealityScoped T2 aggregate under the hood.

---

## DP-Ch8 — Channel CRUD primitives

Channel lifecycle mutations are SDK primitives that write to the per-reality `channels` table + emit the delta-stream event.

```rust
impl DpClient {
    /// Create a new channel as child of parent. Feature code provides level_name
    /// and metadata; DP generates a new ChannelId + writes to channels table +
    /// publishes channel_tree_change { op: Insert }.
    pub async fn create_channel(
        &self,
        ctx: &SessionContext,
        parent: ChannelId,
        level_name: String,
        metadata: serde_json::Value,
    ) -> Result<ChannelId, DpError>;

    /// Update channel metadata or display_name. Level_name and parent cannot
    /// be changed (would invalidate ancestor chains of descendants).
    pub async fn update_channel_metadata(
        &self,
        ctx: &SessionContext,
        channel: ChannelId,
        updates: ChannelUpdate, // display_name, metadata
    ) -> Result<(), DpError>;

    /// Mark channel dissolved. Descendants must already be dissolved (SDK
    /// validates recursion). Dissolved channels retain events per retention policy.
    pub async fn dissolve_channel(
        &self,
        ctx: &SessionContext,
        channel: ChannelId,
    ) -> Result<(), DpError>;
}
```

**Validation NOT in DP scope:**
- Capacity limits per channel (how many cells per tavern) → feature-level rule.
- Prerequisites for creation (does player have rights to spawn a cell?) → feature + capability.
- Cascading effects on dissolve (migrate active sessions away first) → feature-level orchestration.

DP only enforces structural invariants (tree integrity, depth cap, no cycles, dissolve-descendants-first).

---

## DP-Ch9 — Moving a session to a different channel

```rust
impl DpClient {
    /// Issue a capability refresh + new ancestor chain for the session under
    /// the new channel. Returns a new SessionContext; caller swaps in.
    ///
    /// Fails with CapabilityDenied if the session's capabilities don't include
    /// the target channel. Fails with ChannelNotFound if target doesn't exist
    /// or is Dissolved.
    pub async fn move_session_to_channel(
        &self,
        ctx: &SessionContext,
        target: ChannelId,
    ) -> Result<SessionContext, DpError>;
}
```

**Observer effects (feature-level, not enforced by DP):**
- Feature that tracks "player is in cell X" emits appropriate leave/enter events (T2 writes).
- Bubble-up aggregators may react to presence changes (Q27 territory).

DP's concern is the SessionContext + capability refresh. Everything else is feature.

---

## DP-Ch10 — Channel-tree-change invalidation

When a channel is created, updated, or dissolved, multiple caches must be coherent:

1. **Per-reality DB** — authoritative, updated first (SDK write).
2. **Redis Stream `dp:channel_changes:{reality_id}`** — delta event published in same transaction (outbox pattern via [DP-K5](04b_read_write.md#dp-k5--write-primitives-tier-typed) / [02_storage R6](../02_storage/R06_R12_publisher_reliability.md)).
3. **CP in-memory channel tree cache** — consumes stream, updates.
4. **SDK-side ancestor caches on each node** — CP pushes to subscribed SDKs via `StreamChannelTreeUpdates`.
5. **Active SessionContexts holding stale ancestor chains** — see below.

### Stale SessionContext handling

A SessionContext's `ancestor_channels` is a snapshot from bind-time or last move. If the tree changes (e.g., a tavern's parent moves from town-A to town-B), existing SessionContexts are stale.

Policy:

- **Channel create / dissolve / metadata update does not invalidate existing SessionContexts** — their ancestor chains are still correct for their current_channel.
- **Re-parenting** is not permitted (see DP-Ch8 — `parent` cannot change). This is the reason; supporting re-parent would require invalidating every SessionContext in the affected subtree.
- **Channel dissolution while sessions hold it as `current_channel_id`** — SDK's subscribe stream receives the dissolution; subsequent ops from stale SessionContext fail with `DpError::ChannelDissolved`; feature code re-binds session to parent or a new cell.

### Redis Stream schema

```
Stream key:   dp:channel_changes:{reality_id}
Entry shape (MessagePack):
{
  "v": 1,
  "op": "insert" | "update" | "dissolve",
  "channel_id": "<uint64-string>",
  "parent": "<uint64-string|null>",
  "level_name": "<string>",
  "lifecycle": "active|dormant|dissolved",
  "version": <monotonic per reality>,
  "at": <unix ms>
}
```

Stream retention: 7 days or 1M entries per reality. Consumers (CP + SDK instances) use durable cursors.

---

## Summary

| ID | What it locks |
|---|---|
| DP-Ch1 | `ChannelId` newtype with module-private constructor; tree structure with level_name tag; max depth 16 |
| DP-Ch2 | `channels` table lives in **per-reality Postgres DB**, not CP; structural invariants enforced by DB constraints |
| DP-Ch3 | CP caches channel tree per reality; delta stream via Redis Stream; degraded-mode behavior |
| DP-Ch4 | `RealityScoped` vs `ChannelScoped` marker traits; `#[derive(Aggregate)]` enforces exactly one; orthogonal to tier |
| DP-Ch5 | Cache key format with scope marker `r`/`c` at position 2; `dp::cache_key!` macro dispatches on scope trait |
| DP-Ch6 | `SessionContext` adds `current_channel_id` + `ancestor_channels` chain; immutable, swapped on `move_session_to_channel` |
| DP-Ch7 | Ancestor walk helpers on SessionContext; complex metadata queries go through Channel aggregate read |
| DP-Ch8 | Channel CRUD primitives on DpClient; DP enforces structural invariants, feature enforces business rules |
| DP-Ch9 | `move_session_to_channel` issues capability refresh + new ancestor chain; feature-level leave/enter events separate |
| DP-Ch10 | Channel-tree-change invalidation via Redis Stream; no re-parenting; stale SessionContext handling on dissolve |

---

## Cross-references

- [DP-A13](02_invariants.md#dp-a13--channel-hierarchy-as-first-class-scope-phase-4-2026-04-25) — the axiom this file implements
- [DP-A14](02_invariants.md#dp-a14--aggregate-scope-reality-scoped-vs-channel-scoped-design-time-choice-phase-4-2026-04-25) — aggregate scope companion axiom
- [DP-A7](02_invariants.md#dp-a7--reality-boundary-in-cache-keys) — reality boundary; now extended with scope marker
- [DP-K2](04a_core_types_and_session.md#dp-k2--sessioncontext) — SessionContext (extended in file 04a)
- [DP-C3](05_control_plane_spec.md#dp-c3--grpc-service-surface) — CP gRPC surface (now has `StreamChannelTreeUpdates`)
- [02_storage R4](../02_storage/R04_fleet_ops.md) — per-reality Postgres; channel registry slots into existing sharding
- [02_storage R6](../02_storage/R06_R12_publisher_reliability.md) — outbox publisher used for channel-change events

---

## What Q26 leaves to other Phase 4 items

DP-Ch1..Ch10 give channels a concrete home in the DP contract. Other Phase 4 Qs still need resolution, now unblocked:

| Q | What it adds | Progress |
|---|---|---|
| **Q17** per-channel total event ordering | `channel_event_id` invariant + axiom DP-A15 | ✅ resolved 2026-04-25 in [13_channel_ordering_and_writer.md DP-Ch11](13_channel_ordering_and_writer.md#dp-ch11--channel_event_id-allocation-mechanism) |
| **Q30** ordering mechanism | Single-writer in-memory counter + DB UNIQUE constraint | ✅ resolved 2026-04-25 in [13 DP-Ch11](13_channel_ordering_and_writer.md#dp-ch11--channel_event_id-allocation-mechanism) |
| **Q34** channel writer node binding | Cell = creator's node + handoff; non-cell = CP-assigned + epoch fence | ✅ resolved 2026-04-25 in [13 DP-Ch12..Ch14](13_channel_ordering_and_writer.md#dp-ch12--writer-assignment-rules) |
| **Q15** per-channel turn/page boundary | First-class event type + subscribe-completion rule | Unblocked |
| **Q16** durable per-channel subscribe | `subscribe_channel_events_durable(ctx, channel_id, from_event_id)` | Unblocked |
| **Q27** event bubble-up | Aggregator at parent channel reading descendant events | Unblocked |
| **Q28** membership ops | T3 events for join/leave; feature-level validation | Unblocked (Ch8/Ch9 give structural primitives) |
| **Q31** channel lifecycle | Active/Dormant/Dissolved transitions + archive | ✅ resolved 2026-04-25 in [17_channel_lifecycle.md](17_channel_lifecycle.md) DP-Ch31..Ch37 |
| **Q18** T1 reframe for channel presence | T1 aggregate examples (typing indicator, presence) | Unblocked |
| **Q19** per-channel pause | `channel_pause(ctx, channel_id, reason)` + write-rejection | Unblocked |
| **Q32** privacy bubble-up | Channel visibility flag in metadata; bubble-up respects | Unblocked (metadata field supports it) |

Resolution order in Phase 4 continues with Q17 + Q30 + Q34 next (per-channel ordering + writer binding).
