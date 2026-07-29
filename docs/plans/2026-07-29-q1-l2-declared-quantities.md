# Q1 — the L2 declared-quantity substrate

> **Status:** PLAN 2026-07-29. One XL run, **three risk boundaries** (one commit each).
> **Spec:** [`35_quantity_architecture.md`](../03_planning/LLM_MMO_RPG/35_quantity_architecture.md)
> §4.2 (`QTY-A5`/`A6`), §4.5 (`A14`), §4.6 (`D9` tenancy), §5.4 (`A13`), §12 build order.
> **Standard that shaped the plan:** [`non-vacuity.md`](../standards/non-vacuity.md) NV-1..6.

---

## 0. The §12 sweep — what the build order says vs what the code says

The PO asked for the whole table verified rather than the one row this slice touches. Result:
**3 of 6 verifiable claims are stale, and all 3 of `Q0b`'s are still true.**

| Row | Claim | Verdict |
|---|---|---|
| **Q1** | *"Blocked on `D-PUBLISHER-DROPS-RULESET-PIN`"* | ❌ **stale** — cleared in `Q-1`; `e.ruleset_digest` is in pgsource's SELECT |
| **S2** | *"`domain.rs` 592 · `combat.rs` 456, both over the ceiling"* | ❌ **stale** — shipped `ce8bee02b`, largest owned file 317 |
| **Q0a** | — | ✅ done, already marked |
| **Q0b** | `RulesetEpochActivated` has **zero** occurrences | ✅ still true (0 across `crates/ services/ contracts/ migrations/`) |
| **Q0b** | `BindingStore` has no mutating method | ✅ still true — surface is `new`/`create`/`load`/`digest_for` |
| **Q0b** | `create` hardcodes epoch 1 | ✅ true — `epoch: RulesetEpoch(1).0` |

**The discovery that changes B2.** `crates/meta-rs` is already the *formal* Rust hot-path port of the
Meta Access Library (`metawrite`, `transitions`, `allowlist`, `audit`) and is deliberately
**driver-agnostic** — *"concrete sqlx adapters: caller-supplied."* So the ledger does not need a new DB
client, only an adapter and a pool. But every meta write goes through `meta_write` **plus an
allowlist** whose SoT is **`contracts/meta/events_allowlist.yaml`**, parsed by *both*
`contracts/meta/allowlist.go` and `crates/meta-rs/src/allowlist.rs`. The ledger table therefore needs a
row in a **polyglot machine contract**, not just a migration — the §B category where "one language
updated, the other silently drops it" lives.

---

## 1. The shape `const fn` forces, and it is the shape the spec wanted

`Ruleset::engine_default()` is a **`const fn`**. A `Vec` cannot be const-constructed, so the declared
set cannot be a growable collection. That is not an obstacle — **it is `QTY-A6` arriving by a second
route**:

> *"The ARRAY WIDTH is a compile-time constant. The IDENTITIES inside it are declared per reality and
> pinned by the digest. A reality uses a prefix `0..n` of a fixed `N`; `n` is in the hashed bytes, `N`
> is in the binary."*

```rust
pub const MAX_DECLARED_QUANTITIES: usize = 32;          // N — in the binary

pub struct QuantityName { bytes: [u8; 32], len: u8 }     // no String: const-constructible
pub struct QuantityTable {
    n: u16,                                              // in the hashed bytes
    names: [QuantityName; MAX_DECLARED_QUANTITIES],
}
```

**Only `0..n` is encoded.** Two consequences, both wanted: the unused tail cannot influence the digest,
and **raising `N` later does not move any existing digest** — `N` is genuinely in the binary, exactly as
A6 says. The alternative (encoding the full array) would make a capacity bump a rules change for every
reality in existence.

### 1.1 `QTY-A12` will bite, and that is the mechanism working

`size_of::<Ruleset>()` is asserted `<= 224`. A 32-entry name table is ~1 KB, so **the assertion fails on
the first build** and must be repinned with a written reason. That is not friction to route around — the
assertion's own comment predicted this exact growth:

> *"it is the struct L2 will grow (declared quantities, the ordinal table, the `O(n²)` element
> interaction table which `QTY-A6.1` places HERE and not on the actor)"*

A `Ruleset` is interned **per reality**, not per actor, so ~1.3 KB is affordable in a way the same
number on `Actor` would not be — which is the whole content of `QTY-A6.1` (`O(n)` per actor, `O(n²)`
per ruleset). **Boxing the table to dodge the assertion is forbidden**: that is `QTY-A6 ⊥ QTY-A12`
(register row 6) and would make `size_of` blind for every future slice.

---

## 2. What has a subject in Q1, and what does not

Doc 35's `Q1` row bundles the substrate with three enforcement arms. Checked one at a time, **two of
them have no subject until a later slice** — the same finding as `S1a`/`S1b`, now for the third time in
this build order.

| Arm | Subject exists in Q1? | Where it goes |
|---|---|---|
| ordinals **assigned**, never authored | ✅ — a layer declares names, the loader assigns | **build** |
| `n > N` refused | ✅ — declare `N+1` | **build** |
| duplicate / empty / oversized name refused | ✅ | **build** |
| **`QTY-A5` never reused on removal** | ❌ — a binding is **write-once** (`RLS-A3`), so a reality's declared set cannot change until an epoch switch | **trigger → `Q0b`** |
| **`QTY-A13`** a contribution to an undeclared ordinal is refused | ❌ — **there are no L3 sources until `Q4`**; there is nothing that could contribute | **trigger → `Q4`** |

Building either of the last two now would ship a validator that returns *permitted* for every input
that can exist — `NV-2`. Each gets an **asserted trigger** that reds the day its subject arrives, the
same device as `s1b_has_no_subject_yet_and_says_so`.

> **This is now a pattern in doc 35 §12 itself, not three coincidences.** Its rows bundle *mechanism +
> enforcement*, and the enforcement's subject frequently arrives one or two rows later. Worth recording
> against the build order so the next reader sizes a row by what it can *prove*, not by what it names.

---

## 3. Slices

| # | Boundary | Done when |
|---|---|---|
| **B1** | **L2 substrate in the hashed bytes** — `QuantityName`/`QuantityTable`, `Ruleset.quantities`, canon `v2→v3` + upcast, `A12` repin, `UnionById` merge in `RulesetPatch`, the three validators that bite, S1b's floor+mutability arms (forced — the trigger reds), classification rows | a reality declares `qi` (an identity the engine has never heard of) and it survives **create → store → load → digest** with ordinals unchanged; a v2 artifact still loads |
| **B2a** | **the binding gets a home in the meta DB** — `migrations/meta/033_reality_ruleset_binding`, the `events_allowlist.yaml` row + a mirror test in **each** language, live migration smoke | the table exists, is append-only against every role *including* the mode that turns triggers off, and both parsers agree the row is there |
| **B2b** | **Rust reaches it** — sqlx adapter for `meta-rs`, `BindingStore` behind a trait, `--meta-url` on the spine, live create → load through Postgres | Q0b's blocker is gone: a reality's binding survives a process restart in a table rather than a file |
| **B3** | **doc 35 §12 sweep** + 16a/26 cross-refs + handoff | no row in §12 states a fact that contradicts the code |

**POST-REVIEW at the end of B1** — it is the load-bearing half (author-declared identities entering
hashed bytes are permanent once a reality binds), and it is where `/review-impl` earns its keep.

## 4. Invariants B1 must not break

* **A v2 artifact must still load.** `Q0a` built version dispatch for exactly this; B1 is its **second
  real exercise** and the first with a *field added* rather than a version bumped.
* **The golden digest MOVES, deliberately** — a field entered the hashed bytes. That move is the proof,
  same as `LAW_VERSION`'s. Repin with the reason, per the repin log.
* **`n = 0` must be the identity.** Every existing reality declares nothing; their behaviour, and every
  law, must be byte-identical to today.
* **No string-keyed lookup reaches the step path.** `QTY-A5` puts a name→ordinal map in
  `ruleset-core` for *encoding*; `hot-path-gate` is expected to fire on it and the correct answer is a
  pragma stating the map is resolved at `create_reality` and never read in `apply` — **not** widening
  the gate's scope.
