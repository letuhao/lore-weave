# Actor Hub — feature #1

**Round:** 2026-08-02 · **Status:** design sealed · **feature #1 BUILT** — [`crates/actor-hub`](../../../crates/actor-hub)
**Run state:** [`../../plans/2026-08-02-actor-substrate-RUN-STATE.md`](../../plans/2026-08-02-actor-substrate-RUN-STATE.md) — `D-1`..`D-475`

> **Actor hub is feature #1 of roughly a thousand, across dozens of categories.**
> **Features are PLUGINS. The actor is the HUB.** The hub's job is to make adding feature #2 cheap —
> **not to pre-empt it.**

---

## Read this to know WHAT IS DECIDED — the contracts

| file | lines | owns |
|---|---|---|
| [`2026-08-02-actor-hub.md`](2026-08-02-actor-hub.md) | 202 | the hub: identity · intrinsic quantities · existence · attachment · the fold · the contribution seam |
| [`2026-08-02-engine-substrate.md`](2026-08-02-engine-substrate.md) | 157 | the layer beneath: the two SSOTs · rule identity · ordinals · the fold arithmetic · the mechanism/vocabulary discriminator |
| [`2026-08-02-seams-and-triggers.md`](2026-08-02-seams-and-triggers.md) | 66 | **18** measured seams to features that do not exist yet — a register, **not a design** |

**425 lines total.** They were 1 107 before the scope seal; the cut is recorded in `D-292`..`D-295`.

<!-- actor-hub-figures:end index -->

## Read this to REUSE THE ANALYSIS — `analysis/`

**Nothing here is a decision.** It is worked analysis that cost real effort, kept so a later feature can pick
it up instead of re-deriving it. **A later round may take any of it, amend it, or discard it — no part of it
binds anyone.**

| file | what it is worth reusing for |
|---|---|
| [`analysis/2026-08-02-actor-dataflow.md`](analysis/2026-08-02-actor-dataflow.md) | **the derivation record** — how every decision was reached, which claims were retracted and why, 23 diagrams, and the drift log of 22 recorded mistakes. **Read it to understand HOW, never to know WHAT** |
| [`analysis/2026-08-02-actor-data-structure.md`](analysis/2026-08-02-actor-data-structure.md) | the earliest decision record (`D-1`..`D-14` era) plus the first red-team round. **Predates the plugin frame entirely** |
| [`analysis/2026-08-02-value-model-analysis.md`](analysis/2026-08-02-value-model-analysis.md) | **for any feature that needs a NUMBER that spans orders of magnitude** — power creep as a domain error rather than a width error, the log domain and its measured limits, permille pools, a unified ceiling model, band deltas, and the industry precedent for numeric squishes. **Cut from the contract because it serves features that do not exist; kept because it will be needed the day one does** |
| [`analysis/2026-08-02-feature-notes.md`](analysis/2026-08-02-feature-notes.md) | **for combat, progression and ownership** — measured findings about shipped code with the reasoning attached: a damage floor that lets attrition beat scale, a validator that states a genre claim as a law, a currency requirement no existing representation meets. **These were once written as PROPOSALS, which was a scope violation. They are notes** |

## What this round did NOT decide

Damage · thresholds and bands · tier ladders · currency and denominations · pools and regeneration · the log
domain · ceilings beyond the fold's clamp · archetypes · spawn · maps and places.

**Each is a category with its own feature.** Feature #1 measured where it touches them
([`seams-and-triggers`](2026-08-02-seams-and-triggers.md)) and stopped.

## Built

| | |
|---|---|
| [`crates/actor-hub`](../../../crates/actor-hub) | the hub: ordinals · `PluginSet` · the declaration registry · the contribution rows · the fold · the `Actor` struct · the explain path |
| [`crates/entity-existence`](../../../crates/entity-existence) | `GoneState`, moved DOWN out of `dp-kernel` so a pure crate can hold hub item 3. `dp_kernel::entity_status::GoneState` is unchanged |
| `crates/ruleset-core/src/modifier.rs` | `ModifierOp`, moved DOWN out of `game-rules` for the same reason. `game_rules::stats::ModifierOp` is unchanged |
| `scripts/hashed-substrate-float-gate.py` | `U-9` — no float in the bytes that become a ruleset's NAME |
| `scripts/citation-gate.py` | `U-10` — the `file:line` citations in **these documents** now resolve mechanically. `D-281` measured that no repo gate could reach them |

The slice board, with per-slice test output, bite-tests and verifier reports, is
[§6-BUILD of the RUN-STATE](../../plans/2026-08-02-actor-substrate-RUN-STATE.md).

## Verification

Five adversarial lenses, **112 findings**, all folded in: citation/measurement · implementability · logical
validity · regression-on-the-fixes · absence. **Round 4 has not run**, so this is a *fixed* state, not a
*verified* one. The programme's own stated limit: agents drawn from one model have correlated blind spots,
and **a clean round is a stopping rule, not a proof** (`D-224`).
