# 40 — Progression planner — Index

> **Category:** PPL / PPO / PPB / EPL / GP / ICT / MOD / ENR / ASK / MEM / BLD — the **authoring tier** for progression systems.
> **Status:** DESIGN, unreviewed. Nothing here is locked and nothing is built.
> **One-line:** how a human + an LLM converge, in a loop, on a progression system strict enough to
> feed procedural generation — and what "strict enough" means, mechanically.

## Why this is a folder and not a numbered doc

It started as one document and became a set the moment the outcome question was asked. It will keep
growing in a predictable direction: **one shared engine, one CORE rule pack, and one pack per
gameplay profile** (`PPO-A4`). The profiles are the reason for the folder — they are the deliberate
*bias* the PO asked for, and each is a separate artifact with its own competency-question set.

## Documents

| # | doc | what it settles |
|---|---|---|
| 01 | [`01_planner_architecture.md`](01_planner_architecture.md) | **What a progression system IS** (variables · inflows · gates · couplings), the closure criterion, six provenances, the abductive register, the logic-engine choice. `PPL-A1..A10`, `PPL-T1..T9`. |
| 02 | [`02_outcome_contract.md`](02_outcome_contract.md) | **What the planner must PRODUCE.** One complex cultivation system surveyed loop-by-loop; the outcome defined as *a fact set that answers its profile's competency questions*; the profile roster and what we refuse to serve. `PPO-A1..A7`. |
| 03 | [`03_generator_boundary.md`](03_generator_boundary.md) | **Where the planner STOPS.** 01 and 02 were written broad enough to reach into the item/place/crafting modules — `CPL-A3` forbids exactly that. Fixes ownership (declare vs contribute), the three contract artifacts, and the **two-layer pipeline** that decouples every generator. `PPB-A1..A6`. **Corrects 01 and 02 in nine places — read it before acting on either.** |

| 04 | [`04_enum_pool.md`](04_enum_pool.md) | **The mechanism.** The contract layer is a **pool of closed sets**: modules register slot *shapes* in code, one loop fills the *members* with a human. Collapses 03's three artifacts into one and states the track's thesis — *the engine is deterministic functions, the manifest is the lists they range over*. `EPL-A1..A5`. |
| 05 | [`05_gameplay_inventory.md`](05_gameplay_inventory.md) | **The subject matter, shallow.** 147 gameplay loops in 18 families — Part 1 cultivation (91), Part 2 the general-RPG delta (56), one line each, stable ids — the worklist for per-entry deep-dives into contract specs. **No analysis on purpose.** Supersedes [`02` §1](02_outcome_contract.md)'s 18-loop first pass, which missed about four-fifths of it. `GP-*`. |
| 06 | [`06_item_contract.md`](06_item_contract.md) | **First per-module deep-dive.** Every field of `PL_007`'s `ItemDefDecl` classified by producer; the three-tier split (taxonomy / `ItemDef` table / instance); item's pool footprint (~5 slots, ~56 human decisions). **Retracts `PPB-A2`① and `PPB-A3`** — the progression→item seam already shipped as `InstrumentTag`. `ICT-A1..A3`. |
| 07 | [`07_module_organisation.md`](07_module_organisation.md) | **The implementation spec.** Four planner KINDS covering every slot; the `declare_pool_slot!` registration + generated `contracts/pool/registry.json`; storage that **reuses the tenancy-hardened `gamegen_*` decision layer** and adds two tables; the file layout; and five falsifiable claims that decide whether the pattern works. `MOD-A1..A2`. |
| 08 | [`08_retrieval_and_enrichment.md`](08_retrieval_and_enrichment.md) | **The two hard halves.** Retrieval replaces prompt-stuffing (POC-1's measured root cause); the query is derived from the slot, not the model; a `not_stated` answer must carry its query log; and enrichment is a **six-rung criteria ladder** with a **genre pack** supplying convention as CANON rather than model recall. `ENR-A1..A5`. |
| 09 | [`09_asking_and_sufficiency.md`](09_asking_and_sufficiency.md) | **How a planner asks and knows it is done.** Worked end-to-end on `item_grade`: never ask for a number, ask for the structure that determines it; three separate sufficiencies; a six-state slot machine whose `STARVED` and `DECLINED` states are the ones that matter. `ASK-A1..A4`. |
| 10 | [`10_spike_asking_results.md`](10_spike_asking_results.md) | **MEASURED.** Five probes of `40.9` against a real local model, expectations written before the run. Verdict: **usable for asking, not trustworthy for deciding** — the model obeys rules that tell it to PRODUCE and violates rules that tell it to RESTRAIN or REFUSE. `ASK-A5`. |
| 11 | [`11_member_schema.md`](11_member_schema.md) | **What a contract IS as data.** The member envelope + slot-typed body; `code` as the immutable contract; typed references as the logic structure. **Checks the item contract backwards against `ItemDefDecl` and finds it four fields short.** Round-3 spike forces a model into the schema. `MEM-A1..A4`. |
| 12 | [`12_operations_and_build.md`](12_operations_and_build.md) | **Part A** closes rounds 6–8: a planner kind needs an **operation**, not just an output shape — and the operation yields a criterion needing no answer key. **Part B** is the build plan: module layout, planners registered by KIND, per-kind workflow, and the LangGraph question answered with a measurement. `BLD-A1..A6`. |

**Read 04 first if you only read one; read 03 before you build anything.** 01 designs a machine;
02 defines what the machine is for; 03 draws the line around it; 04 is how it is actually built.
01 is not buildable until 02 is locked; 01 and 02 carry corrections listed in
[`03` §9](03_generator_boundary.md), and 03 is sharpened by [`04` §7](04_enum_pool.md) (its `PPB-A2`
and `PPB-A3` collapse; `A1`/`A4`/`A5`/`A6` survive).

**`PPB-A6` and all of `EPL-*` are bigger than this folder.** The two-layer contract→generate pipeline
and the enum pool govern **every** element module, not just progression. They are written here because
this is where the problem surfaced; they belong in doc 38 once reviewed. `EPL-A2` is
[`QTY-A6`](../35_quantity_architecture.md) generalised — the pattern is already built, for quantities.

## Planned, not yet written

| # | doc | when |
|---|---|---|
| 04 | `04_core_rule_pack.md` + `CORE.lp` | after 02 is PO-locked — the universal rules (a variable needs a socket · cycles illegal · provenance authority · requirements vocabulary-legal). Split internal vs assembly per [`03` `PPB-A5`](03_generator_boundary.md) |
| 05 | `profiles/Z+_llm_mmo_sim.md` + `.lp` | LoreWeave's own profile. CQ set drafted in [`02` §5](02_outcome_contract.md) — must first be split into planner-CQs vs assembly-CQs ([`03` §9](03_generator_boundary.md)) |
| 06 | `06_spike_results.md` | the falsifiable experiment — [`02` §7](02_outcome_contract.md) states the expected output **before** it is run |
| — | L0 slot registry (`declare_pool_slot!` in `crates/`, exported to `contracts/`) | the pool schema `EPL-A2` needs. Code, cross-module, so it does **not** live in this folder |
| — | `EPL-T1` lint — no game-specific closed set in engine code | the one check that would notice `EPL-A1` being violated. Sibling of `closed-set-gate.py` |

Profiles deferred or refused, with reasons, in [`02` §8](02_outcome_contract.md): `Y` combat MMO
(defer) · `X` idle/incremental (refuse for now) · `W` tabletop export (refuse — different outcome, not
a profile).

## Relationship to the docs outside this folder

| doc | relationship |
|---|---|
| [`39_progression_generation_pipeline.md`](../39_progression_generation_pipeline.md) | **Front half superseded** (S0–S3: corpus → brief → interrogation → fold become *one input path*, provenance ③). **Back half consumed unchanged** — `S-1` validator, S4 policy, S5 candidate, S6 pin are correct and shipped. Doc 39 stays where it is; it is cited too widely to move. |
| [`PROG_001`](../features/00_progression/PROG_001_progression_foundation.md) | the **runtime substrate** and, now, the **decision-space schema** the register is derived from. Two additive gaps found here: a depleting variable (`PPO-A2`, lifespan) and regression (`PPO-A3`). |
| [`35_quantity_architecture.md`](../35_quantity_architecture.md) | L2 declaration is the compile target. `QTY-A13` is what makes the Variable/Coupling split land correctly. |
| [`38_content_pipeline_architecture.md`](../38_content_pipeline_architecture.md) | three authorships, plus a fourth source this track adds: **CANON** (the authored wiki/glossary/KG). `CPL-A3` (one module per element) is what 03 enforces; **`CPL-A9`'s roster dependency *progression → place, item* ⚠ is RETRACTED** by `PPB-A6` — PROPOSED amendment, not yet applied to doc 38. |
| [PlanForge](../../../specs/2026-07-01-plan-forge/01_PLANFORGE_ARCHITECTURE.md) | the loop shape is borrowed; **the autonomy is not** (`PPL-A9`). |

## Status

| | |
|---|---|
| **PO checkpoint** | **OPEN** — 02's outcome contract + `PPB-A6`'s pipeline-wide adoption both need sign-off before 04/05 are written |
| **Built** | nothing. No code, no rule pack, no dependency added. |
| **Measured** | POC-1: four live end-to-end runs against a real model, zero manifests. Verdict **FAIL**, recorded in [`01` §10](01_planner_architecture.md) rather than laundered. |
| **Blocking decisions** | (a) how many of the 19 CQs must be answerable to ship ([`02` §10.4](02_outcome_contract.md)) — set the threshold *before* the spike prints its number; (b) whether `PPB-A6` + `EPL-*` are adopted pipeline-wide, which requires walking all seven of doc 38's roster entries ([`04` §8.4](04_enum_pool.md)) |
