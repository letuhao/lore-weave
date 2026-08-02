# Seams and triggers — what feature #1 measured and did NOT decide

**Status:** register · **Date:** 2026-08-02
**Replaces:** `2026-08-02-handoffs-to-features.md`, which was itself a scope violation — it made
**proposals** about other features' mechanics.

---

## Why this file is a list and not a design

Actor hub is **feature #1 of roughly a thousand**, across dozens of categories. **A plugin exists so that
adding feature N+1 does not touch feature #1 — not so that feature #1 can specify feature N+1.**

The prior version of this file carried worked proposals for combat, progression and ownership: a damage
model, a threshold rule, a tier-fall enum, a currency representation. **None of that was ours to write.**
Writing it costs the owning feature its design freedom and costs this round its finish line.

> **The rule for every row below: a MEASURED FACT about shipped code, the SEAM it touches, and the TRIGGER
> that makes it someone's problem. No mechanics. No proposals. No numbers we chose.**

Everything deleted from the previous version survives in
[`2026-08-02-actor-dataflow.md`](analysis/2026-08-02-actor-dataflow.md) (the derivation record) and in the
[RUN-STATE](../../plans/2026-08-02-actor-substrate-RUN-STATE.md). **Nothing is lost; it is de-scoped.**

---

## The register

| # | measured fact | seam | trigger — whose, and when |
|---|---|---|---|
| **S-1** | `attack.rs:135` and `:185` both floor at `.max(1)`, so a landed hit always deals ≥1; `:109-111` returns 0 on a miss | a far weaker attacker can defeat a far stronger one by attrition | **combat**, when it designs damage |
| **S-2** | `StatSlot` is used by name inside the shared fold (`resolve.rs:131`) and the shared stat block (`block.rs:76`, `:89`) | the slot table cannot become combat-private until those two uses move | **combat**, before `C-2` |
| **S-3** | `melee_archetype` and `slot_defaults` are `[i32; SLOT_COUNT]` over ten combat slots; `StatBlock::from_defaults` exists because *"playable with zero declaration is a hard requirement"* | the only source of a playable actor today is combat-shaped | **combat or a future archetype feature**, when either is designed |
| **S-4** | `block.rs:89` `self.set(StatSlot::MoveRange, …)` overwrites a value six modifier layers just resolved | an Equipment `Flat(+2)` on `MoveRange` is accepted and silently discarded | **combat**, when it owns the derivation |
| **S-5** | `validate.rs:212-219` refuses a ladder whose `tier_max` does not rise; the message states a genre claim aloud | a reality wanting a rank to be revocable cannot say so | **progression**, when it designs tiers |
| **S-6** | `progression/mod.rs` declares caps as `u64`; `decode_cap` reads `r.u64()?` unbounded | a width decision at the hub tier narrows what progression can declare | **progression**, when a cap is authored |
| **S-7** | `ResourceDecl.min` is signed *"because a pool may model debt"* and is an **absolute** value | any fractional representation of `current` needs a conversion | **resource**, when pools are designed |
| **S-8** | `docs/specs/2026-08-02-item-data-structure.md` exists and inherits `D-1`..`D-109`; this round continued to `D-291` | the item round is building on a superseded snapshot | **item/ownership**, at its next checkpoint |
| **S-9** | `EntityId(u64)` is *"identity within a reality"*; `GoneState` is keyed by `EntityRef { uuid, aggregate_type, reality_id }`; **zero conversion sites exist** | the hub cannot key a platform-tier lifecycle operation | **platform**, when the hub first meets it |
| **S-10** | `crates/ruleset-loader/src/layer.rs:22` ships `enum Layer` with an ascending fold order | a second unqualified "layer" would be one name for two concepts | **already handled** — this round uses `fold_layer` |

---

## What feature #1 deliberately did NOT decide

Damage · thresholds and bands · tier ladders and falls · currency and denominations · pools and regeneration
· the log domain and power scale · ceilings beyond the one the fold needs · archetypes · spawn · maps and
places.

**Each is a category with its own feature. Feature #1 measured where it touches them and stopped.**
