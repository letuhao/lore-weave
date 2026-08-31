//! `QTY-A12` — the resident-size budget for [`Ruleset`], and the log of every
//! decision that moved it.
//!
//! **Its own file because it is its own artifact.** `ruleset.rs` answers *what a
//! ruleset IS*; this answers *what it is allowed to COST*, and the two change for
//! different reasons — a new field edits the struct, a new field's PRICE edits
//! this. The repin log only ever grows, and it grows on a different schedule from
//! the type it guards.
//!
//! Split out at `LIM-1`, when `MAX_DECLARED_VERBS` 16 -> 64 pushed `ruleset.rs`
//! past `IMP-D3`'s 400-line ceiling. The ceiling was paid in a SPLIT rather than
//! an allowlist row, which is what the four rows before it did.

use crate::ruleset::Ruleset;

// QTY-A12 (doc 35 §6.4) — see the rationale on `StatBlock` in
// `services/commit-service/src/stats.rs`.
//
// A ruleset is interned per reality, not per actor, so its budget is generous
// by comparison — but it is the struct L2 will grow (declared quantities, the
// ordinal table, the O(n^2) element interaction table which QTY-A6.1 places
// HERE and not on the actor). It also backs a claim with an expiry date:
// `digest()` recomputes BLAKE3 on every call and justifies that with "the whole
// artifact is ~200 bytes". Watch this number.
//
// REPIN LOG — each entry is a decision someone had to write down, which is the
// entire mechanism. The assertion is not here to forbid growth.
//
// * 216 -> 224, 2026-07-29 (`Q0a`), for `law_version` (QTY-D13). Four bytes of
//   field, eight of struct after alignment. It bit on the very next slice after
//   it was added, which is the only evidence that a guard works.
// * 224 -> 1280, 2026-07-29 (`Q1`), for `quantities: QuantityTable` — and this
//   is the growth the paragraph above PREDICTED BY NAME. A 32-entry table of
//   32-byte identifiers is ~1 KB.
//
//   **Why that is affordable here and would not be on `Actor`:** QTY-A6.1 —
//   `O(n)` per ACTOR, `O(n²)` per RULESET. A `Ruleset` is interned once per
//   reality; ten thousand resident actors pay nothing for it. The same 1 KB on
//   `Actor` would be 10 MB and would be the exact mistake chaos made, where a
//   `[[f64;50];50]` interaction matrix sat INLINE on every actor and consumed
//   47 % of the struct.
//
//   **Boxing the table to keep the number small is FORBIDDEN.** That is
//   `QTY-A6 ⊥ QTY-A12` (non-vacuity register row 6): a heap pointer makes
//   `size_of` 16 bytes for every `n`, so this assertion would compile, always
//   pass, and never be able to fire again — for every future slice, not just
//   this one.
//
// * 1280 -> 2312, 2026-07-30 (`Q2`), for `resources: ResourceTable` — 32 rows
//   of a 32-byte `ResourceDecl`, plus its length. Measured, not estimated.
//
//   `ResourceDecl` is 32 B rather than the ~20 its fields sum to, because
//   `CeilingBinding::Slot(StatSlot)` inherits `StatSlot`'s `#[repr(usize)]`
//   8-byte alignment. Storing the slot as a bare `u8` would recover ~256 B
//   across the table and was NOT done: it would put an untyped ordinal in the
//   hashed bytes with nothing checking it against the enum, which is precisely
//   the drift `slots.rs` exists to prevent — and 256 B on a struct interned
//   ONCE PER REALITY is not worth buying with an untyped index.
//
//   **The paragraph above about `digest()` and "~200 bytes" is now stale, and
//   the distinction it glosses matters more than the number.** The STRUCT is
//   2.3 KB; the ENCODED bytes are not, because only `0..n` is written. A
//   reality declaring no pools encodes one extra length prefix over Q1 — four
//   bytes — and BLAKE3 hashes what is encoded, not what is resident. Watch the
//   encoded size, which is what `digest()` actually pays for.
// * 2312 -> 2344, 2026-07-30 (`S-1b`), for `progression: Option<ProgressionDigest>`.
//   Measured by probe, not estimated: `Option<[u8; 32]>` is 33 bytes and
//   `Ruleset` aligns to 8, so 2312 + 33 rounds to 2344.
//
//   **This is the whole reason progression is a POINTER and not a table.** The
//   old bound was `<= 2312` and `size_of` was EXACTLY 2312 — zero headroom,
//   which a bite-test confirmed (`<= 2311` fails to compile). Inlining even one
//   `TierDecl` was never on the table: `PROG_001` §5.6's worked example is 24
//   tiers in one kind, and a `TierDecl` transitively owns `String`/`Vec`/
//   `HashMap`, so it can never be `Copy`, never be `const`-constructed, and
//   cannot be measured by `size_of` AT ALL — the `QTY-A6 ⊥ QTY-A12` trap. 33
//   bytes of pointer buys a table of unbounded shape without giving up the
//   property this assertion exists to hold.
// * 2344 -> 2600, 2026-08-06 (`M1`), for `ResourceDecl::role: EngineRole` — ONE
//   byte of field, **256 bytes of struct**, and the multiplier is the decision
//   worth recording rather than the total.
//
//   `ResourceDecl` went 32 -> 40 (measured, not estimated), because it already
//   aligns to 8 through `CeilingBinding::Slot(StatSlot)`'s `#[repr(usize)]` —
//   so a single `u8` costs a whole 8-byte step, times 32 rows. **The paragraph
//   below already priced this exact trade in the other direction**: storing the
//   slot as a bare `u8` would recover ~256 B and was refused for putting an
//   untyped ordinal in the hashed bytes. The same answer holds here, and it is
//   the same 256 B: a `u8` role would be an untyped index into a closed enum
//   with nothing checking it, which is precisely the drift `slots.rs` exists to
//   prevent.
//
//   Affordable for the reason `Q1`'s entry gives: `QTY-A6.1`, `O(n)` per ACTOR
//   and `O(n^2)` per RULESET. This is per-reality, interned once; ten thousand
//   resident actors pay nothing for it. The ENCODED cost is one byte per
//   DECLARED pool — a reality with three pools pays three bytes.
// * 2600 -> 3696, 2026-08-06 (`M2`), for `verbs: VerbTable` — 16 rows of a
//   68-byte `VerbDecl` plus its length. Measured by probe, not estimated.
//
//   **This is the growth `Q1`'s entry predicted by name**, one table over: the
//   struct L2 grows is the struct that holds what an AUTHOR declares. A
//   `VerbDecl` is 68 B rather than the ~56 its fields sum to, because a
//   `QuantityName` is 33 bytes (32 + a length) and the two `Option<…Row>` each
//   carry a discriminant.
//
//   **Affordable here for the reason `QTY-A6.1` gives, and NOT affordable on
//   `Actor`:** `O(n)` per ACTOR, `O(n^2)` per RULESET. A ruleset is interned once
//   per reality; ten thousand resident actors pay nothing. The ENCODED cost is
//   `0..n` — a reality declaring one verb pays for one row, not sixteen.
//
//   **Boxing the table to keep this number small is FORBIDDEN**, the same call
//   the entry above makes: a heap pointer makes `size_of` 16 bytes for every `n`,
//   so this assertion would compile, always pass, and never fire again.
// * 3696 -> 6960, 2026-08-06 (`LIM-1`), for `MAX_DECLARED_VERBS` 16 -> 64.
//   Measured by probe, not estimated: `VerbDecl` is 68 B, so `VerbTable` goes
//   1090 -> 4356 and `Ruleset` 3696 -> 6960.
//
//   **This entry exists because the assertion refused the change and forced it
//   to be written down** — which is the entry above's claim (*"the assertion is
//   not here to forbid growth"*) demonstrated rather than restated. Nothing else
//   in the tree would have noticed a constant going 16 -> 64.
//
//   **The repin is not what changed; the AUTHORITY is.** Sixteen was acting as
//   *"how many actions a world may have"* — a design decision about somebody
//   else's world, living in this crate. It is now *"how many rows this binary
//   can hold"*, and the design decision moved to the manifest's `[limits]`
//   block (`LIM-1`, `crate::Limits`). Raising a capacity moves no digest,
//   because only `0..n` is encoded.
//
//   Affordable for the reason `Q1`'s entry gives and NOT affordable on `Actor`:
//   `QTY-A6.1`, `O(n)` per ACTOR and `O(n^2)` per RULESET. 3.2 KB once per
//   reality; ten thousand resident actors pay nothing. The same 3.2 KB on
//   `Actor` would be 32 MB.
const _: () = assert!(core::mem::size_of::<Ruleset>() <= 6960);
