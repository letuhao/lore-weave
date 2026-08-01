# F1 — `ruleset-core`: the digest becomes real, and it hashes something that governs

> **Task size:** L (files ≈ 20, logic 10, side effects 3 — new workspace crate · public API change
> across `commit-service` · a new pre-commit gate).
> **Spec:** [16 §8 RLS-A13/D5/D6](../03_planning/LLM_MMO_RPG/16_ruleset_loader_and_registry.md) ·
> [26 §6 F1](../03_planning/LLM_MMO_RPG/26_implementation_architecture.md) ·
> [31 §build order](../03_planning/LLM_MMO_RPG/31_world_simulation_architecture.md).
> **Exit criterion (26 §6):** *a digest is computed from bytes and two different rulesets are
> distinguishable; `RulesetDigest([0u8;32])` count is 0 outside tests.*

---

## 1. Why this is not "add a hash function"

`RulesetDigest([0u8; 32])` appears in **15 places** (IMP-D6). An all-zero digest means RLS-A13's pin
is inert: two realities with different rules produce indistinguishable events and replay cannot
detect that the rules moved underneath it.

But making the digest *real* while the game constants are still Rust literals produces something
worse than an inert digest — a **confident** one. It would hash a struct holding
`{schema_version, ko_duration_rounds}` and report "same rules" for two builds whose damage chain
differs by a factor of two, because `MAX_HIT`, the variance band, the hit floor/ceiling and all ten
slot defaults live in `combat.rs`/`stats.rs` where no digest can see them.

> **This is the point [XST-D5](../03_planning/LLM_MMO_RPG/27_extensibility_stress_test.md) made and
> the reason F3's test cannot be written today: *"edit one constant → the digest moves"* has nothing
> to edit.** The inability to write the test is the tell, not a gap in the test suite.

So F1 folds in the constant migration that doc 26 §6 lists under **D1**. Stated as a deliberate
re-ordering, not a silent one: **D1's constant sourcing moves into F1 because a digest over a struct
containing no game constants is vacuous, and a vacuous digest is worse than an absent one** — it
answers "did the rules change?" with a confident No.

### What F1 does NOT do (so the boundary is legible)

| Deferred to | What |
|---|---|
| **F2** | the loader: provider stack, presets, merge algebra, tombstones, interning, validation, the `TODO(F2)` empty-clamp refusal. **No `Manifest` type in F1** — a manifest with no resolver is a shape with no consumer, which is the stored-but-never-read anti-pattern one level up. |
| **F3** | the digest *bites*: replay under a mismatched digest is REFUSED. F1 only makes the first half (*edit → digest moves*) writable. |
| **S1** | 16a's layer floors / `Tunable` vs `AdditiveOnly`. |
| **S2** | the `game-rules` crate extraction — laws stay in `commit-service` for now, but they now take `&Rules` by reference (IMP-D2's precondition). |

---

## 2. Crate placement, and the one dependency question that had a wrong answer

`RulesetDigest` lives in `sim-core` today. The obvious move is to relocate it into `ruleset-core`
(the digest is the *ruleset's* identity — RLS-A13 is written in doc 16, not doc 14) and have
`sim-core` depend on `ruleset-core`.

**Rejected.** `sim-core/Cargo.toml` states its invariant in its own header:

> *ZERO runtime dependencies, deliberately: determinism is the product, and every dependency is a
> determinism liability to audit.*

`ruleset-core` needs `blake3`, so relocating the type would push a hash implementation into the
kernel's dependency tree to serve a 32-byte newtype that the kernel only ever **carries**.

> **Decision F1-D1 — the TYPE stays in `sim-core`; the COMPUTATION lives in `ruleset-core`, which
> depends on `sim-core`.** `RulesetDigest` is an opaque identity the island carries; producing one
> from canonical bytes is the ruleset's job. Dependency direction:
> `commit-service → {ruleset-core → sim-core}`. No cycle, and the kernel's stated invariant holds.

```
crates/ruleset-core/          (no I/O; deps: sim-core + blake3)
  src/canon.rs      — the canonical encoder (RLS-D5)
  src/slots.rs      — StatSlot + SLOT_COUNT: the closed vocabulary the ruleset names
  src/combat.rs     — CombatRules  (15 constants)
  src/stats.rs      — StatRules    (slot defaults, move derivation, melee archetype)
  src/provenance.rs — Provenance (RLS-A15) + RulesetEpoch
  src/ruleset.rs    — Ruleset · ResolvedRuleset · digest()
```

Each file stays under IMP-D3's 400-line ceiling.

---

## 3. What moves, and what correctly stays a literal

The line is IMP-A1 / IMP-D1: **a law's STRUCTURE is code, a law's CONSTANTS are config.** Applying
it to every number currently in `combat.rs` / `stats.rs`:

### Moves into `CombatRules` (15)

| Field | Was | Site |
|---|---|---|
| `hit_base_pm` · `hit_floor_pm` · `hit_ceiling_pm` | 500 · 50 · 950 | `hit_chance_pm` |
| `roll_band_lo_pm` · `roll_band_hi_pm` | 850 · 1150 | variance band |
| `elem_mult_pm` · `resist_pm` | 1000 · 0 | the V1-identity chain steps |
| `defend_divisor` | 2 | `defending` halving |
| `max_hit` | 1e9 | `MAX_HIT` (`TODO(IMP-D5)` — this row retires that TODO) |
| `ko_duration_rounds` | 5 | already in `CombatRules` |
| `av_base` | 10 000 | `action_value` numerator |
| `av_slowed_pm` · `av_hasted_pm` · `av_stunned_pm` · `av_initiator_first_pm` | 1200 · 800 · 2000 · 750 | status multipliers |

### Moves into `StatRules`

| Field | Was |
|---|---|
| `slot_defaults: [i32; SLOT_COUNT]` | `StatSlot::default_value()`'s 10 arms |
| `move_base` · `move_speed_per_tile` · `move_max` — ~~`move_floor`~~ | `StatTuning::default()`. **`move_floor` was DROPPED at review** (§8): it contradicts this document's own next section, and `DF07_001 §5.2` declares three fields, not four |
| `melee_archetype: [i32; SLOT_COUNT]` | `CombatStats::archetype_melee`'s 12/2/450/100 |

### Stays a literal — and why it is not debt

- **`1000` as the per-mille divisor.** The *unit* is shape; the *value expressed in that unit* is
  config. Making the divisor configurable would not tune a rule, it would redefine what "per-mille"
  means — every other constant's meaning changes underneath it.
- **`crit_mult_pm = 1000` for a non-crit.** The multiplicative identity. A tunable identity is a
  second, hidden global damage multiplier.
- **`(1000 - resist_pm)`, `max(1, …)` on base, `.max(1)` on damage, `max(0)` on the percent factor
  (EC-2), `speed.max(1)`.** These are the law's *structure* — floors that keep the encounter
  resolvable and the arithmetic total. A configurable floor of 1 is a configurable division by zero.
- **`SLOT_COUNT = 10` and the `StatSlot` variants.** DF7-A1: authors project into slots, they never
  add one. R02 (doc 31) proposes making the slot set ruleset-declared; that is an **amendment not yet
  applied**, and applying it here would be scope creep into a design decision that is still PROPOSED.

---

## 4. The digest, and how it is kept honest

`Ruleset::digest()` = BLAKE3 over the canonical encoding (RLS-A13). Computed on demand, never cached
— a cached digest is a staleness bug waiting for a mutation path.

**Canonical encoding (RLS-D5 — part of the contract, not an implementation detail):** a domain
separation prefix, then every field big-endian fixed-width in a fixed order. No serde, no floats, no
maps. Fixed-width integers are self-delimiting, so there is no `("ab","c")` vs `("a","bc")`
ambiguity to length-prefix around.

### The failure mode this design is actually about

A hand-written `canon()` that forgets a field produces a digest that **silently stops covering it** —
the same shape as `ModifierSource::ALL` (a closed set with a hand-written companion list), which is
the bug XST-D7 and `closed-set-gate.py` exist for. Two independent mechanisms, each catching what the
other misses:

| Mechanism | Catches | Misses |
|---|---|---|
| **Exhaustive destructuring** — `let Self { a, b, … } = self;` with **no `..`** opening every `canon` impl | a field ADDED to the struct and not encoded ⇒ **E0027, a compile error** | a field bound then encoded *twice* while another is dropped (unused binding is a warning) |
| **Per-field perturbation test** — mutate one field, assert the digest moves | a field bound but not encoded, or encoded from the wrong binding | a field ADDED to the struct (no perturbation row exists for it yet) |
| **Golden digest** of `Ruleset::engine_default()`, pinned as hex | *any* change to any field or to the encoding ⇒ red, forcing a conscious update — including the one that should prompt a new perturbation row | — |

The perturbation table is the only hand-maintained list in the design. It is guarded by the golden
test, which reds whenever the struct changes. **State it as discipline where it is discipline** — the
lesson from `ModifierSource::ALL` is that describing a companion list as a *guard* is the actual bug.

### Provenance exclusion is structural, not remembered

`Provenance` (RLS-A15 — `author_user_id`, `preset_ref`, authoring cost/timestamps) is excluded from
the digest, so that two behaviourally identical realities dedupe. The exclusion is made **mechanical
by containment**: `ResolvedRuleset { ruleset, provenance, epoch }` and `digest()` walks only
`ruleset`. `Provenance` has no `canon()` impl at all, so including it would not compile.

The test is non-vacuous *because* `Provenance` sits inside the same container: same rules + different
provenance ⇒ **same** digest; different rules ⇒ **different** digest.

---

## 5. The API changes, and the one deliberate compile-error

Laws gain a `&…Rules` parameter — RLS-A12's seam, now carrying something:

```rust
hit_chance_pm(rules: &CombatRules, accuracy_pm, dodge_pm)
resolve_attack(rules: &CombatRules, atk, def, defending, seed, attacker, action_idx)
action_value(rules: &CombatRules, speed, status, is_initiator_first_turn)
resolve_block(archetype, modifiers, slot_clamps, lex_clamps, rules: &StatRules)
Actor::new(rules: &Ruleset, max_hp)      // the archetype is content
CombatDomain::Rules = Ruleset            // was CombatRules
```

> **`impl Default for StatBlock` is REMOVED rather than redefined.** It currently means *the engine
> default block*, which after this change is a function of `StatRules` and cannot be produced from
> nothing. Redefining it as "zeroed" would leave ~19 call sites compiling with silently different
> semantics. Removing it makes each one a compile error to be fixed deliberately —
> `StatBlock::zeroed()` where an accumulator was meant, `StatBlock::from_defaults(&rules)` where the
> engine defaults were meant. Mechanism over discipline, same reasoning as the destructuring above.

**`CombatRules::strike_damage` is DELETED, not migrated.** Its own doc-comment says *"no longer
consulted for a Strike"*; `grep` confirms zero reads. Migrating it into the hashed struct would mean
a field nobody reads changing the digest — a rules change that changes no rule.

---

## 6. Zero-digest: the literal becomes a declaration, then a gate

F1's exit criterion is *zero `RulesetDigest([0u8;32])` outside tests*. Four non-test sites:
`commit-service/src/main.rs`, `src/bin/spine.rs`, `crates/sim/src/bin/{bench,stress}.rs`.

The first two get a **real** digest from `Ruleset::engine_default()`. The two `crates/sim` bins drive
`TestDomain` — there is no game ruleset for them to hash, and inventing one would be a lie. They get
`RulesetDigest::UNPINNED`, a **named** constant meaning *"this island runs a kernel harness domain,
not a content ruleset."*

This is the `MAX_HIT` move again: **a declared zero is a different object from an emergent one.**

> **`scripts/zero-digest-gate.py`** — bans the anonymous `RulesetDigest([0u8; 32])` literal
> everywhere, and bans `UNPINNED` outside `crates/sim` and test files. Wired into `.githooks/pre-commit`.
> The gate is F1's own exit criterion made mechanical rather than asserted once and left to rot
> (IMP-A7: rule + SoT + gate + test).

---

## 7. Verification plan

| # | Check | Bites when |
|---|---|---|
| V1 | golden digest of `engine_default()` | any constant or the encoding changes |
| V2 | per-field perturbation (every field of `CombatRules` + `StatRules`) | a field is not covered by `canon` |
| V3 | two different rulesets ⇒ different digests (26 §6's exit criterion, literally) | the digest is constant |
| V4 | same rules + different `Provenance` ⇒ same digest | provenance leaks into the digest |
| V5 | digest is stable across calls and across a clone | nondeterministic encoding |
| V6 | the existing 85 `commit-service` tests, re-pointed at `engine_default()` | the constant migration changed any number |
| V7 | **bite-proof**: add a field to `CombatRules` without touching `canon` ⇒ compile error (pasted) | the destructuring mechanism is decorative |
| V8 | `zero-digest-gate.py --self-test` + a real run | the gate matches nothing |
| V9 | `closed-set-gate` + `design-lint` still green (`StatSlot` moved crates) | the move broke the existing gates |

**V6 is the load-bearing one.** The migration must be *value-preserving*: every number that arrives
via `engine_default()` must equal the literal it replaced, and the existing suite is what proves it.
A test that needed its expected value changed is a migration bug until proven otherwise.

---

## 8. Outcome (2026-07-28)

**Shipped.** `154 tests pass, 0 fail` (13 new · 85 commit-service · 56 kernel);
`cargo build --workspace --all-targets` exit 0; clippy clean on both touched crates; rustdoc clean;
every gate green (`closed-set` · `zero-digest` · `design-lint` · `db-safety` · `ai-provider` ·
`host-paths` · `language-rule`).

| Check | Result |
|---|---|
| V1 golden digest | `807d5b52…f4fe01` pinned |
| V2 per-field perturbation | 15 combat + 8 stat rows, all move the digest, none collide |
| V3 exit criterion | two rulesets differing by **one point of hit floor** are distinguishable |
| V4 provenance excluded | different author/preset/epoch ⇒ same digest; a rules change ⇒ different |
| V5 stability | 64 recomputations + a clone + an independent reconstruction all agree |
| V6 **value preservation** | **not one pre-existing test's expected value was edited** |
| V7 destructuring bite | field added, `canon` untouched ⇒ **E0027** at `combat.rs:128` |
| V8 gate bite | pre-F1 literal restored ⇒ `zero-digest-gate` FAIL; `--self-test` bites |
| V9 existing gates | green, including after `StatSlot` changed crates |

### What the plan got wrong, caught in self-review

1. **`move_floor` should never have been a field.** §3 of this plan states that floors keeping the
   game resolvable are *structure*; I then made the move-range floor configurable anyway, and
   `DF07_001 §5.2`'s `StatTuningDecl` declares three fields, not four. **Inventing a knob the spec
   never asked for is the same failure as leaving a constant hardcoded, mirrored** — both put a
   number where the design did not put it. Deleted.
2. **`Ruleset` derived `Copy`.** RLS-A13's whole point is that identical rules **intern** into one
   shared `Arc`; `Copy` invites the by-value duplication that undermines. Dropped.
3. **`Canon::u64` had no consumer.** Removed.

### Debt created or made visible

- **IMP-D3's 400-line ceiling has no gate**, and this change grew two files past it: `domain.rs`
  **592** (was 551), `combat.rs` **456** (was 426). Both were already over. The split is **S2**.
- **IMP-D5 `no-magic-game-constant.py` remains unbuilt** — now *possible*, which it was not before,
  and it is what keeps the count at zero rather than trusting one careful run.
- **IMP-D4 `hot-path-gate.py`** unbuilt.
- **`D-EMPTY-PORTABLE-SIDE`** — `Domain::extract` on an absent entity fabricates a placeholder (now
  the explicit `Actor::absent()`), and installing it materialises a side-B actor at 0 HP that
  `outcome_of` reads as *present but not standing* — an empty-case handoff can register as a
  **Victory**. Pre-existing; made visible; sim-core handoff semantics, out of F1's scope.

### What F2 inherits

Four `TODO(F2)` refusals the laws now flag at runtime, three of which DF7-V1 **already specifies** at
Stage 0 (`stat.tuning_invalid`) — so the loader implements a written spec rather than inventing one:

| Refusal | Runtime fallback today |
|---|---|
| empty clamp intersection (`[50,100] ∩ [200,300]`) | floor wins |
| `roll_band_hi_pm < roll_band_lo_pm` | width saturates to 1 |
| `defend_divisor < 1` | clamped to 1 |
| `hit_floor_pm > hit_ceiling_pm` | floor wins |

Each fallback is deterministic and never panics. **That is so a bad ruleset degrades predictably —
not so bad rulesets are acceptable.**

---

## 9. `/review-impl` findings (2026-07-28, pre-commit)

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | **MED** | `services/game-server/src/rooms/ChannelRoom.ts:451` — the same zero-digest bug, in TypeScript: `ruleset_digest: … ?? '0'.repeat(64)` on `w0.bind`, against a schema that says *the client caches by digest*. Every reality shares one cache key. **Latent** — `frontend/src` never reads the field. | **Tracked `D-WIRE-DIGEST-ZERO`**, target F2. Gate extended to `.ts`/`.tsx`; the site carries an explicit pragma. Not fixable in F1: the digest lives in commit-service, and `LW_CHANNEL_RULESET_DIGEST` is an env var holding a per-reality value — the wrong shape before the wiring even starts. |
| 2 | **MED** | Four author-controlled **overflow** sites whose guards were computed by overflowing arithmetic — `roll_band_width` (`hi - lo + 1`), `hit_chance_pm` (`base + acc − dodge`), the resist complement (`(1000 - resist) as i128` — cast on the wrong side), `derive_move_range` (`move_base + speed/per_tile`). `release-commit` inherits `release` ⇒ **`overflow-checks` off**: tests panic, production **wraps silently**. | **FIXED**, with two adversarial-ruleset tests; both bite-proven by reverting. |
| 3 | **MED** | The new gate's pragma window was a fixed 2 lines — so the one real justification (11 lines) did nothing, and the bite-test reported the finding with *and* without it. **The identical vacuity bug as `closed-set-gate`, same week.** | **FIXED** — walks the contiguous comment block; proven by removal → finding, restore → clean. |
| 4 | LOW | `StatSlot` changed crates — does `closed-set-gate` still see it? | **Verified non-vacuous**: deleting `CritMult` from `ALL` in its new home fires the gate. |
| 5 | LOW | `cargo test --workspace`: **649 pass / 6 fail**. The six are `service-http` auth tests panicking in `jsonwebtoken-10.4.0`. | **Pre-existing, outside F1** (`cargo tree` — no dependency on anything F1 touched; the `Cargo.lock` diff is one new crate). Recorded because the prior "workspace green" claim came from a **build**, not a test run. |

**Checked and clean:** provider-gateway invariant · hardcoded model names · tenancy (no tables) ·
secrets (none) · gateway I1 (no new external surface) · destructive DB ops (no SQL) · frontend-tool
contract (no tool schema) · language rule (`crates/` is out of `language-rule.yaml`'s scope, as for
every other crate) · MCP-first (no agent logic). The only machine contract touched is
`contracts/game-wire/session.schema.json`'s `ruleset_digest`, which is finding #1.

**The most useful output of the review was that my own VERIFY evidence overclaimed.** The handoff
said the zero digest was at "ZERO occurrences — everywhere". It was zero **in Rust**. One remained,
in the language the gate did not scan.

---

## 10. Second `/review-impl` pass — "is F1 finished?"

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 6 | **HIGH** | `Island::new` took `rules` and `digest` as **two independent parameters**, with nothing forcing them to agree. An island could report a digest for a ruleset it was not running — the divergence the digest exists to detect, made constructible inside the mechanism meant to prevent it. F1's exit criteria never asked this. | **FIXED structurally.** `Domain::rules_digest` added; the `digest` parameter is **removed**. Mismatch is now a compile error — there is no argument to pass. Bite-proven. |
| 7 | **MED** | `Island::restore(cp, rules)` takes the checkpoint's stored digest and the rules, and never compares them. | **Intentionally left**, with a `TODO(F3)` at the line: a restored island's stored digest is a *historical* fact that may legitimately disagree, and refusing on that disagreement **is** F3. Both values are now available at that line, which they were not before. |
| 8 | **MED — completeness** | **The digest has no consumer.** `EventEnvelope` has no `ruleset_digest` field; every occurrence in the tree is an assignment (island → checkpoint → restored island). **RLS-A13 is not implemented.** | Legitimate by the build order (F2's done-when is *"the digest lands in a committed envelope"*) — but recorded as **a write-only field**, in the same words this arc used for every other stored-but-never-read defect. |
| 9 | LOW | Nothing forces `RULESET_SCHEMA_VERSION` to be bumped when the *encoding* changes; only the golden test reds, and a human decides. | Accept + document. A mechanical version bump would fire on every rules change too, which is the opposite error. |
| 10 | LOW | No **decoder** for `canon_bytes`. RLS-D18 says the digest addresses the **stored bytes**, not the upcast struct; today `digest()` re-encodes from the struct every time. | F2. When it stores bytes it must assert `blake3(stored) == digest(decode(stored))`, or the two representations can drift. |

### Completeness

**F1 against its own exit criteria: complete**, plus one hole those criteria did not name (#6),
now closed. **F1 as a working mechanism: roughly a third of the way** — the artifact is correct,
guarded by three independent mechanisms and unforgeable; it is **wired to nothing**. The digest
starts *earning* its existence when F2 stamps it into the envelope and F3 refuses a mismatched
replay. Until then its value is potential, and saying otherwise would be the same overclaim §9
already caught once.
