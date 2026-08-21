# RUN-STATE — space substrate: dataflow + data architecture

> **Read this file FIRST after any compaction.** Then `git log`, then continue. Nothing in this run
> lives only in the conversation.
>
> **Sibling:** [`2026-08-02-actor-substrate-RUN-STATE.md`](2026-08-02-actor-substrate-RUN-STATE.md) —
> the actor track, which is the METHOD this run is copying. Read its dataflow spec before designing.

---

## 0 · The commitment

**PO, 2026-08-02, in substance:**

> **The map is where everything in the game happens. Every new feature will probably attach one more
> data layer onto the map. So if this is not designed well now, it will certainly break.**

**That thesis is the spec's subject, not its preamble.**

**DONE means:** a space dataflow + data architecture of the same *kind* as the actor spec — stages with a
boundary that dissolves findings, a per-phase read/write/emit contract, the absent tables written out, a
feature census, an adjudicated open register, and **measured** numbers where the design makes a cost
claim. Not the same LENGTH; the same STANDARD.

---

## 1 · Why this run exists — the admission

`36_map_architecture.md:560`, written by this project and shipped anyway:

> **`SPG-Q6`** — *Cost of loci acting has **never been measured*** — carried unchanged from `WSA-F5(c)`,
> and doc 21 §7 forbids inferring headroom.

**We recorded that we had not measured it, then sealed `SPG-A1` as an axiom on top.** The actor spec then
measured the neighbouring case (§19): **~33 000 actors/tick at a 100 ms budget, collapsing to ~4 100 once
statuses engage, against 65 536 loci in a single 256×256 zone** — *"roughly one zone per core."*

Our mitigation (`SPG-A12` lazy materialization + `WSA-A9` existence ladder — an unvisited cell is
`Untracked` and takes no turns) is **an architectural claim that has never been tested.** Testing it is
slice 1, because it is the only finding that can invalidate the containment design itself.

**The tell to remember:** the failure was not missing the question. We *wrote the question down* and
sealed the axiom anyway. An open question shipped as an axiom is a deferral with no mechanism wearing a
better costume.

---

## 2 · Invariants this run may not quietly break

| # | Invariant | Source |
|---|---|---|
| I-1 | `MapKind` is a **closed set**, extensible only by ruleset whitelist (`SPG-A2`) | doc 36 |
| I-2 | Containment is a **matrix validated on write**, never an ordinal ladder (`SPG-A3`) | doc 36 |
| I-3 | **No node stores an absolute position** — transforms are parent-relative (`SPG-A5`/`A17`) | doc 36 |
| I-4 | Containment (strict acyclic tree) and control (free, many-to-many) are **two graphs that never interact** (`SPG-A4`) | doc 36 |
| I-5 | Collision is **topology, not dynamics** — Graft/Merge/Breach/Sever; inter-frame rigid-body physics is explicitly refused (`SPG-A8`/`A9`) | doc 36 |
| I-6 | Generated world content is **content-addressed and immutable**; only divergence enters the event log (`WDS-A1`/`A2`) | doc 37 |
| I-7 | The generator's **bytes are the SSOT**; regeneration is the AUDIT path only (f32 determinism unproven cross-platform) (`WDS-A7`) | doc 37 |
| I-8 | DP is **agnostic to `level_name` semantics** — game vocabulary does not enter the data plane (`DP-A13`) | 06_data_plane |
| I-9 | Replay determinism: layer iteration order must be **fixed**, never hash-order or scheduler-order | EVT-A9 |

**A slice that needs one of these changed does not change it quietly — it goes in §5 as a decision with
its reason, and the amendment row is written before the edit.**

---

## 3 · Slice board — `done` is an evidence string, never a checkmark

| # | Slice | Status | Evidence |
|---|---|---|---|
| **R** | 7 research agents fan out (6 `MapKind`s + the feature-layer plugin question) | **COMPLETE — 8 reports** | `World` §9 · `Arena` §10 · `Region`+`Locale` §11 · `Passage` §12 · **`PLUGIN` §13** · `Universe` §14 · `Domain` §15 · dungeon-gen/housing §16 |
| **1** | **MEASURE the locus-tick cost** — settles `SPG-Q6` | **DONE 2026-08-02** | harness built + run (rustc 1.89, release/lto/cgu=1, best-of-7, single core). **Finding `M-1` below.** Table pasted in §8 |
| **2** | Stage boundary for space | **DONE** | doc 41 §1 — SEVEN stages (`SPAWN` splits into GENERATE + MATERIALIZE); `SDF-A1` *materialization is a STAGE not a FIELD* dissolves six findings |
| **3** | Per-phase read/write/emit contract | **DONE** | doc 41 §3 — six phases + the one determinism rule + `SDF-A4`'s six prohibitions |
| **4** | The absent tables, written out | **DONE** | doc 41 §5 — nine tables `T1..T9`; `T3`/`T9` are wrong-shape, not merely missing |
| **5** | Feature census | **DONE** | doc 41 §6 — 14 features; fog-of-war flagged a **tenancy defect** if shared |
| **6** | The plugin/layer attachment model | **DONE** | doc 41 §4 — `SDF-A5..A12`; layers bind to `MapKind` (~1000×); no `Default` on `UpdatePolicy`/`LifecyclePolicy` |
| **7** | Adjudicate every research finding | **DONE 2026-08-02** | §22 — all **66** rows adjudicated individually. **It found `SDF-F9`: eleven findings had been adopted NOWHERE** (8 folded into doc 41 on the pass · 1 became `SDF-Q18` · 2 routed to other tiers). The prose disposition *"the rest folded into `SDF-A1..A12`"* was a claim about 56 findings that nobody could check |
| **10** | **Reconciliation** — fold §9–§13's axioms back into the normative §1–§8 | **DONE 2026-08-02** | doc 41 §1 §3 §4 §5 §6 §7 §8. Two `LayerDef` fields (`edges`, `projection`), a 7th determinism rule, a scope column on `T1..T9`, `SDF-R7..R9`. **Found that `SDF-A27` argued from a field that did not exist** — drift #6 |
| **9** | **Feature census as a FALSIFICATION test** — present load counted, future load hypothesised | **DONE** | doc 41 §9 — 69 feature ids / 134 docs / 36 folders counted, plus 18 hypothesised. **Six features the model does NOT carry** (`SDF-F1..F6`), each now an open row `SDF-Q5..Q10`, plus `SDF-Q11` (reality scoping) |
| **8** | Open register | **DONE for this pass** | doc 41 §8 — `SDF-Q1..Q4` + three non-vacuity obligations stated **in advance**, incl. one against the design's own highest-risk recommendation |

---

> **⚠ ROUND 2 IS OPEN — see §23.** The board above is round 1 (design without a consumer). On
> 2026-08-22 the actor hub became the map's first consumer and the round-2 board lives in §23.2.

## 4 · Decisions (append-only)

| # | Decision | Reason |
|---|---|---|
| D-1 | **Measure before designing the layer model.** Slice 1 precedes slice 6. | If lazy materialization does not hold, the layer model is being designed against the wrong cost class — and `O(inputs) → O(residents)` is exactly the class change the actor spec caught by opening the kernel. |
| D-2 | **Fan out by MapKind, not by question.** | Each kind has genuinely disjoint prior art (EVE vs HoMM3 vs Space Engineers). Grouping by question would make 7 agents re-read one corpus — the anti-pattern CLAUDE.md names. |
| D-3 | **The plugin question gets its own agent**, not a section in each. | It is the PO's stated thesis and the thing that breaks last and worst. |

---

## 5 · Parked (blocked, not forgotten)

*(empty)*

---

## 6 · Debt taken on knowingly

| # | Debt | Trigger to repay |
|---|---|---|
| — | `D-WORLD-BASELINE-RETENTION` (`WDS-A5`/`A6` retention has no mechanism) | first pruner/retention job on either store |
| — | `D-SPEC-CODE-ENUM-PARITY` | a layer-aware notion of enum identity |
| ~~NEW~~ **DISCHARGED 2026-08-22** | ~~No gate catches a RETIRED AMENDMENT ROW cited as if live.~~ **`amendment-rot-gate.py` check E now does**, and it found EIGHT more sites in three other tracks that nobody knew about: docs 28/29/30 route the E2 extension path through `XST-R6` (retired -> `QTY-D4`) and doc 35 says three times that `WSA-R18` **owns the verb track** (retired -> `XST-R9`). All nine corrected by NAMING THE SUCCESSOR, which makes the sentence true rather than merely gate-silent. Two design notes worth keeping: the retired set is **discovered from the corpus**, not hand-maintained, so an empty discovery is itself a finding; and the citation window is **segmented at neighbouring ids**, because a plain proximity window lets a LIVE row's retirement word excuse an adjacent RETIRED one -- which is exactly how `36:147` survived three months. Both are bite-tested, and the segmentation bite-test was MUTATION-VERIFIED (disarm the clip -> selftest reds) | **repaid** |

---

## 7 · Drift log — near-misses, recorded because a clean log is a dishonest one

| # | Near-miss |
|---|---|
| 1 | **The premise of this run is a defect I shipped.** `SPG-Q6` recorded the unmeasured cost; the axiom sealed anyway. Caught by the PO reading a sibling spec, not by any gate. |
| 2 | **Doc-number collision caught by hand, not by a gate.** Wrote `39_space_dataflow.md` while a peer's `39_progression_generation_pipeline.md` already held it. Renumbered to 41. **Nothing checks top-level doc numbering.** |
| 3 | **`design-lint` caught me claiming a registration I had not made** — the doc header said *"registered 2026-08-02"* before `SDF` existed in either registry. `phantom-registration` exists because that defect shipped four times; it just caught a fifth. |
| 4 | **I pasted the PO's Vietnamese verbatim into two English artifacts** — the exact defect CLAUDE.md names *by example* (*"most often a verbatim PO quote dropped into a design doc"*). `doc-language-gate` blocked the commit. Fixed by quoting the MEANING in English, **not** by adding a pragma: a PO quote is exposition, not subject matter, so the hatch does not apply. |
| 5 | On resuming, I nearly re-committed work already landed — `63d122b36` and `dab52b446` are both ancestors of HEAD. Verified with `git merge-base --is-ancestor` before touching anything. |
| 6 | **`SDF-A27` argued from a `LayerDef` field that did not exist.** Its second consequence — *"no new authoring surface, because `EdgePolicy` is already required at layer registration"* — was **true of `R-46`'s research and false of our own §4**, which I had written myself two rounds earlier and did not reopen. The argument was sound and the premise was fabricated by paraphrase. Caught by the reconciliation pass, **not by any gate** — nothing checks that a doc's prose agrees with its own struct. The field is now there, so the claim is true *because this edit made it true*, which is not the same as having been true. |
| 7 | **The header understated the doc by 18 axioms.** It still read `SDF-A1..A12` / `F1..F6` / `Q1..Q11` after four analysis rounds took it to `A1..A30` / `F1..F9` / `Q1..Q18`. A reader trusting the header would have thought half the doc was not in it. |
| 8 | **A summary line was wrong twice in one sentence.** §21 said *"Twelve of seventeen resolved. The five that remain"* and then listed **four**. The table says 13 and 4. Both halves were arithmetic on a table sitting directly above the sentence. |
| 10 | **`SDF-R2` cited, as its lead evidence, a problem its own target had already solved.** `R-36`'s ULP table is correct and irrelevant: `SPG-A17` defines absolute position only up to the nearest coordinate root, so no chain spans fifteen orders of magnitude. The amendment was **right for a different reason than the one printed on it**, and only opening the target showed it — the fourth time in doc 36's history that habit has changed a finding (`SPG-R2`, `SPG-R7`, `REC-98`, now this). **An amendment row is a claim, and a claim that sits unapplied for three weeks decays against the doc it points at.** |
| 9 | **Slice 7 sat at `partial` for the entire arc, and I nearly closed the run without it.** The board said *"a row-by-row table is still owed"* in plain English. Doing it took one pass and found eleven unadopted findings — so the cost of the omission was not the table, it was the eleven. |


---

## 8 · Slice-1 measurement — `SPG-Q6` settled, and it changes a field in doc 36

**`M-1` — "lazy" as an ADJECTIVE is not lazy as a DATA STRUCTURE, and doc 36 currently specifies the
adjective.**

`SpaceNode.materialization: Materialization` is **a field**. A tick that honours it therefore reads
*every resident* to discover which to skip — `O(residents)`, no matter how few are live. Measured at
65 536 residents (one 256×256 zone), W=8:

| live | B · ladder as FIELD | C · ladder as INDEX | **B / C** |
|---:|---:|---:|---:|
| 0.1 % | 27.8 µs | 0.30 µs | **92.4x** |
| 0.5 % | 36.0 µs | 1.24 µs | **29.0x** |
| 1.0 % | 26.1 µs | 3.27 µs | **8.0x** |
| 5.0 % | 76.1 µs | 18.30 µs | **4.2x** |
| 25 % | 184.9 µs | 84.66 µs | **2.2x** |
| 100 % | 232.6 µs | 318.56 µs | **0.7x** |

**And the index is nearly free to maintain** — the objection that would kill it:

| churn/tick | index maintenance | C scan | **total C** | B scan |
|---:|---:|---:|---:|---:|
| 0 | 0.00 µs | 2.82 µs | **2.82 µs** | 28.5 µs |
| 64 | 0.09 µs | 3.02 µs | **3.11 µs** | 28.5 µs |
| 512 | 1.06 µs | 1.68 µs | **2.74 µs** | 28.5 µs |

Even at 512 materialize/dematerialize events per tick, maintenance is ~1 µs against a 28.5 µs scan it
removes. **The bookkeeping objection does not survive measurement.**

### Where the finding STOPS — stated, because half the value is refusing to over-claim

- **`M-1` is a claim about SCAN STRATEGY, not about capacity.** There is no headroom table here and
  there will not be one until the real per-locus work exists — doc 21 §7, and v1 of this harness had
  a capacity table that was meaningless (at ~1 ns synthetic work it measured memory bandwidth, not
  loci). Deleted rather than caveated.
- **The advantage collapses on two axes**, and both are honest limits:

  | work unit | B · FIELD | C · INDEX | B / C |
  |---|---:|---:|---:|
  | W=1 (a predicate) | 33.6 µs | 0.84 µs | 40.1x |
  | W=64 (a real evaluation) | 59.6 µs | 22.49 µs | 2.7x |
  | W=256 (heavy) | 194.3 µs | 154.93 µs | 1.3x |

  So the index matters **exactly when the per-node question is cheap** — *"does this locus have
  anything to do?"* — which is the common case, and stops mattering when the answer is expensive.
  Likewise at 100 % live the index is a small LOSS (0.7×). **The design must say which regime it is
  in, not assert the index is always right.**
- **The rows are noisy** — 1.0 % measuring lower than 0.5 % is not a real inversion, and strategy B is
  **not monotonic** in the live fraction because a balanced split is the worst case for the branch
  predictor. v1 of this harness mistook that for a result. §2 of the run probes it; note that its
  "branchless" control is itself imperfect (it performs the work then masks it), so it bounds the
  effect rather than isolating it.
- **The work unit is synthetic.** This measures shape, not loci.

### Consequence for the design

`SPG-A12` and `WSA-A9` are **upheld in intent and under-specified in mechanism.** The claim *"an
unvisited cell is `Untracked` and takes no turns"* is true of the SEMANTICS and false of the naive
IMPLEMENTATION, which still visits it. Amendment to raise against doc 36: **the existence ladder must
be an index the tick iterates, and `materialization` on the node is a DENORMALISATION of that index,
never its source of truth** — with the tick forbidden from scanning residents.

That is the same shape as `SPG-A5`'s parent-relative rule: the authoritative structure is the one the
hot path walks, and a field that merely records the answer invites an `O(n)` reader.


---

## 9 · Research intake — `World` (agent 1 of 7)

### `R-1` — INDEPENDENT CONVERGENCE with `M-1`, from the opposite direction

I measured that the existence ladder must be an **index**, not a field. The agent — researching Paradox,
Dwarf Fortress and Minecraft, with no access to my benchmark — arrived at the same requirement:

> *"a 'layer' must not imply '50 systems each iterating 500k cells every tick.' That would be 25M
> cell-updates/tick"* against the ~33k ceiling — **~750× over budget** — so an `ActiveSet` (a Roaring
> bitmap of live cells) is *"mandatory, not advisory."*

And the Dwarf Fortress finding is the same law stated by a shipped game: **world size costs storage;
EMBARK size costs frames.** Reducing embark 4×4 → 2×2 has *"an enormous impact on FPS"* while world size
mainly costs worldgen/save time.

**Two independent routes, one conclusion: the live set is a data structure, not an adjective.** That is
`M-1` corroborated, and it upgrades the doc-36 amendment from *my measurement* to *measurement plus
convergent prior art*.

### `R-2` — Paradox is the answer to the PO's thesis, and it has shipped for 15 years

The pattern: **one immutable ID raster + N cheap overlays keyed by ID.** `provinces.bmp` is structurally
unchanged since 2013 while `trade_winds.txt`, `climate.txt`, `provincegroup.txt` and dozens of DLC
overlays were added *around* it — because none of them live inside the province geometry. A "map mode" is
literally a **1-D palette of length = province count**; at 32 768 provinces × RGBA8 that is **128 KB per
map mode**, and a 40th map mode costs 128 KB and touches zero geometry.

CK3 ships **63 separate terrain-mask PNGs** — direct evidence that "many thin layers" is a tolerated,
shipped design rather than a theory.

**This is the PO's *"every feature attaches a data layer"* worry, already solved by a studio that lived it
for 15 years.** Adopt it.

### `R-3` — the three candidate shapes, and the one that loses badly

At 501 264 cells × 50 layers (agent's arithmetic, not measured — flagged as such):

| shape | memory | iterate one layer | add a layer |
|---|---:|---|---|
| **SoA columns** keyed by dense `CellIdx` | **24–60 MB** | sequential, SIMD-able | insert one registry row |
| per-cell `HashMap<LayerId, Value>` | **~790 MB** | 501k hash lookups + pointer chases | trivial |
| fat struct with 50 fields | ~50 MB | drags all 50 fields through cache | **edits the core type + migrates every save** |

**~13–33× worse AND slower**, plus 501 264 heap allocations. The fat struct is the one that violates the
requirement outright.

### `R-4` — three concrete numbers worth acting on

| finding | number |
|---|---|
| **EU4 hard-crashes past 32 768 provinces** — an `i16` somewhere | we are at 501 264. **`u32` cell ids from day one**; a `u16` caps at 65 535 |
| Our JSON is **~912 B/cell**; Delaunator-style flat integer arrays give full topology at **~84 B/cell** | **~42 MB vs 459 MB** — and CSR adjacency alone is ~14 MB |
| Point→cell needs **no spatial index at all** | our lattice is spherical-Fibonacci, and Keinert et al.'s *inverse* mapping is **O(1) closed-form**; nearest generator point *is* the containing Voronoi cell by definition |

### `R-5` — an ECS would be overhead here, for a specific reason

Archetype-ECS wins iteration, sparse-set wins composition churn. **Our cells never change composition** —
cell 41 203 has a biome for the world's lifetime. So we get the archetype iteration win *for free* with
exactly one archetype, and a general ECS would be machinery we pay for and never use.

### Gaps the agent marked rather than filled — do not build on these

Black Desert Online: **nothing technical found, zero sources.** ESO: zone-based only, no architecture
docs. WoW `ADT/v18`: the wiki 403s, so per-chunk vertex counts are unverified. Paradox internals:
**reconstructed from modding surface + community reimplementations, never disclosed.** All §4.2/§2.3
memory figures are **arithmetic, not measured**.

**Marked gaps are why this report is usable.** An agent that had filled them would have been worse.


---

## 10 · Research intake — `Arena` (agent 2 of 7)

### `R-6` — ⭐ THE STRUCTURAL FINDING: `Arena` (a place) and `Encounter` (a fight) are two different things

Doc 36 has `SPG-D1` — *combat sited in place where the space allows, an `Arena` otherwise* — and treats
that as a decision about **which node the fight lives in**. The research says the framing itself is the
problem:

> **The `Encounter` ALWAYS exists during a fight. The `Arena` node is OPTIONAL — merely a space the
> Encounter may point at.**

Foundry VTT is the shipped proof: its `Combat` document holds `scene` as a **foreign key, not
ownership**, and `combatants` as *references* to tokens. Multiple Combats can run on one Scene at once.

**Why this matters to us specifically.** If grid, initiative and status layers live *inside* the
`SpaceNode`, then in-place combat forces one of two bad outcomes: **(a)** carve an Arena anyway just to
have somewhere to hang the state — which defeats `SPG-D1` entirely — or **(b)** give every Locale and
Domain combat-shaped fields that are null 99.9 % of the time.

**With the split, the hybrid decision becomes a one-line branch instead of two code paths.**
`carved_arena: Option<NodeId>` — `None` is in-place, `Some` is carved, and everything else is identical.

### `R-7` — the gap `SPG-D1` never addressed: in-place combat is not replayable without a CLOSURE

XCOM 2's replay works because a tactical mission is a **closed world** — a start frame, an append-only
chain, and nothing external can inject. **An in-place fight in a persistent shared Locale is an OPEN
world**: a wandering NPC, a day/night tick, another party's AoE, a weather change can all perturb it.

Under our own constraint — *a fight must replay identically from its event log* — **`SPG-D1` as written
is not satisfiable.** The reframing that rescues it without reversing the PO's decision:

> **In-place means "no separate SPACE". It does not mean "no isolation boundary".** The Arena node is a
> spatial convenience; the **Encounter closure** is the correctness boundary, and it exists in BOTH
> branches.

Three concrete rules: everything the fight reads is **snapshotted at siting** into the log's opening
frame (≈2.3 KB for a 24×24 terrain slice — cheap); anything crossing mid-fight is an **explicit event**,
never an ambient effect; nothing outside the closure is mutated until an atomic commit at disposal.

**This is a real hole in our sealed design, found by research rather than by review.**

### `R-8` — HARD RULE, and it is `M-1` arriving from a third direction

> **Combat data layers are NEVER `SpaceNode`s.** A fire zone, an aura, a cover volume is not a child
> node. If features may add nodes per zone, the tree explodes and the measured per-node tick cost bites
> immediately.

My benchmark said the live set must be an index, not a field. The `World` agent said the active set must
be a Roaring bitmap. This one says feature data must not become nodes at all. **Three independent routes,
one law: do not let feature data enter the structure the hot path walks.**

### `R-9` — four layer SHAPES, not one — and this converges with `World`'s density argument

> *"A uniform 'everything is a dense grid' is what dies at 50 layers."*

| shape | prior art | cost |
|---|---|---|
| **Field** — dense per-cell scalar | Dave Mark's influence maps | `O(cells)` |
| **Region** — sparse shape + predicate | Foundry Scene Regions | `O(regions)` |
| **Effect** — per-entity declarative change | Foundry ActiveEffect | `O(participants × effects)` |
| **Derived** — recipe + cache, version-invalidated | — | recompute on demand |

`World` reached the same conclusion by density (dense `Vec` / Roaring / sorted-sparse / blob). **Two
agents, two domains, same answer: the encoding is chosen per layer, never globally.**

Dave Mark's chapter is worth reading in full — it gives a **composition algebra** (`AddMap`,
`MultiplyMap`, `Normalize`, `Inverse`, `GetHighestPoint`) where **the core never knows what a layer
MEANS**; meaning lives in the recipe. And it was *"originally developed for the prototypes of two large,
online RPG games"* — approximately our problem.

### `R-10` — the status-effect escape hatch, and it is worth ~37×

My measurement showed statuses cost ~8× (33k → 4k actors/tick). The answer is that **turn-based is a
lever we have not pulled**:

> Do not tick status effects on the world tick. Tick them on **encounter turn boundaries.** A fight with
> 8 participants over 6 rounds is ~48 turn boundaries *total*; spanning 3 minutes of wall-clock that is
> 48 evaluations instead of ~1 800 world ticks.

Requires modelling duration in **encounter time** (rounds/turns canonical inside a fight; convert to
seconds only for effects promoted into the world delta). Foundry already does exactly this.

### `R-11` — three determinism landmines aimed at THIS codebase

1. **`std::collections::HashMap` iteration order is randomly seeded per process.** Any layer set, effect
   set or participant set iterated from a `HashMap` produces a different replay **in the same binary on
   the same machine**. Use `BTreeMap`/`IndexMap` or sort by stable id. *Silent and intermittent — the
   worst failure mode.*
2. **`f32`/`f64` are not bit-reproducible** across platforms/compilers. Anything feeding a comparison —
   influence, initiative, damage, thresholds — must be fixed-point. (Note `WDS-A7` already reached this
   conclusion for world-gen; it generalises.)
3. **Foundry breaks initiative ties ALPHABETICALLY BY NAME.** In a multilingual project display names are
   localized and collation is locale-dependent — **the same fight yields a different turn order under a
   different locale.** Use `(−initiative, stable_entity_id)`. This is an ML-4-shaped bug in a place
   nobody would look for one.

### `R-12` — a documented hole in a mature shipped system, cited as a warning not a pattern

Foundry's docs **do not specify how overlapping Regions resolve conflicts.** With 50 layers, ties are
certain, and an unspecified tie order is replay divergence. Fix: a **total** order `(priority, LayerId)`
with ids stable across versions. Worth noting that a system with thousands of third-party modules still
has this hole — it is the kind of thing that only bites at layer counts nobody tested.

### Gaps the agent marked

⛔ BG3/DOS2 surface-grid internals — **no public technical source; do not cite Larian for architecture.**
⛔ XCOM 2 cover/LOS internals (the `History` architecture is well sourced; the tile cover system is not).
⛔ **WoW phasing/sharding/layering — search budget exhausted before reaching it, and the agent names this
as the highest-value remaining gap.** Directly relevant to "many concurrent fights across many realities".
⛔ Zone-of-control representation — requested, not delivered.
🔶 **Every "50 layers" cost number is the agent's arithmetic on cited inputs, not a measurement** — it
says so and says they should be benchmarked before being treated as budgets.


---

## 11 · Research intake — `Region` + `Locale` (agent 3 of 7)

**The first agent to read our SHIPPED CODE**, and that is why it is the only one so far to find defects in
the struct rather than around it. It corrected my own briefing on the way: the tilemap generator is
`services/tilemap-service`, not `crates/` — and **`SpaceNode`/`MapKind` do not exist in code at all**,
only in docs and two gate scripts. `build_state.rs` already carries **six parallel flat vectors**, so the
codebase has independently converged on SoA without being told to.

### `R-13` — ⭐ DEFECT IN `SPG-A17`: `Transform` cannot express a discrete tile anchor

> A `Domain` anchored at tile (137, 42) of a Locale, expressed as a float transform, **does not
> round-trip losslessly and will drift under repeated serialize/deserialize** — which is fatal under
> event-sourced replay.

I wrote `SPG-A17` two days ago and did not catch this. A house sitting on a tile is *the* common case for
`Locale → Domain`, and a float transform makes its position a rounding error rather than a fact. Fix:
either `Transform` gains a `GridAnchor { index: u32, orientation: Direction }` variant, or Locale-child
transforms are defined in **integer tile units**. **Amendment required before any implementation.**

### `R-14` — ⭐ GAP: containment ≠ connectivity, and `parent` cannot express traversal

Our tree has `parent` — that is *containment*. It has **nothing for traversal**. HoMM3's Monolith and
Subterranean Gate are edges that **deliberately violate containment**, and a single `parent` pointer
cannot express them. Neither can "the door of the house", which is a traversal edge between a Locale and
the Domain it contains.

Proposed `PortalSet`, and two properties matter:

- **Portals never store world coordinates** — only `(NodeId, LocalAnchor)`. Combined with parent-relative
  transforms, a Locale with `Mobility` (a ship deck) can move and **every portal into it stays valid with
  zero fixups.** `SPG-A5` earns its keep here in a way we had not noticed.
- **Never enumerate children by scanning for `parent == me`** — that is `O(all nodes)`, and it is the
  `M-1` mistake in a different costume.

### `R-15` — the memory outcome is decided by the DEFAULT, not the layer count

| mix @ 256×256 | per Locale | × 1 000 loaded |
|---|---:|---:|
| 50 × dense `u32` | 12.5 MiB | **12.5 GiB — dead** |
| 50 × dense `u8` | 3.2 MiB | **3.2 GiB — dead** |
| realistic mixed encodings | ~1.0 MiB | ~1.0 GiB — survivable |
| **`Uniform` default + lazy materialization** | **~100–300 KiB** | **~100–300 MB ✓** |

> *"Fifty layers is fine. Fifty **materialized dense** layers is not."*

Minecraft's rule generalised: **if a layer has one distinct value, the array is omitted entirely.** So
*declaring* a layer costs ~0 bytes, which is what makes "every feature gets a layer" affordable at all.
This is the direct answer to the PO's thesis.

And the per-tile component bag — the option that *looks* most architecturally correct — measures
**~6–8 MiB for one layer's worth and ~65 536 cache misses ≈ 5.2 ms**: 5 % of a 100 ms tick, for **one
sweep, on one Locale.**

### `R-16` — no layer ticks, and `Decay` computes ON READ

`UpdatePolicy` as a closed set checked at registration: `Static` (0) · `EventDriven` (`O(events)`) ·
`Decay{half_life}` (**0** — store `(value, as_of_tick)` and shift on read) · `Derived{deps}` (0 until read).

**RimWorld's `snowGrid` ticks — that is the named anti-pattern.** Scent, tracks, snow, corruption are read
far less often than they "update", so computing decay on read makes the per-tick cost *literally zero*.

**Fourth independent route to `M-1`.** My benchmark said index-not-field; `World` said `ActiveSet`;
`Arena` said layers-are-never-nodes; this says no-layer-ticks. **Per-tick work = |dirty chunks|, never
|tiles|.**

### `R-17` — fog of war in the shared map is a TENANCY DEFECT, by our own standard

Fog of war is not one layer, it is **N layers** — one per viewer. Putting it in the shared node means one
player's exploration is visible in, and mutable through, a row another player can reach. That is a
straight violation of **User Boundaries & Tenancy**, caught by an agent applying *our* standard to a
design we had not written yet. Per-`(viewer, locale)` Roaring bitmap, ≤8 KiB worst case, ~0 unexplored.

### `R-18` — two rot-shaped lessons from shipped games

- **HoMM3 spends 4 of 7 tile bytes (57 %) on RENDERER state** — autotile variant + flip flags baked into
  the map file. Consequence: the same logical map has many valid encodings, so the file **is not
  content-addressable**, and a renderer change forces a map-format migration. Under `WDS-A1` that is
  **disqualifying**. Store `terrain_type` only; derive the variant at render.
- **RimWorld has 15 hardcoded grid fields on `Map` AND a working reflection-registered `MapComponent`
  plugin path — and the core does not use its own extension point.** Adding grid #16 requires recompiling
  `Map`; a mod adds one for free. *"If the core doesn't dogfood the extension point, the extension point
  is decoration."* This is our own *"the API advertises only what the engine wires"* discipline, arrived
  at independently. **Core layers must register through the identical mechanism as plugin layers.**

### `R-19` — the determinism trap it rates most likely to bite

> **`LayerId` must come from an ordered, append-only manifest — never a compacted index, never `HashMap`
> order. Removing a plugin must not renumber the survivors, or every recorded event log misroutes.
> Tombstone retired ids; never reuse.**

Plus `BTreeMap` everywhere near layer enumeration (the third agent to flag `HashMap` iteration order), and
fixed-point for anything persisted or replayed — which is `WDS-A7` generalising off the world-gen path.

### `R-20` — it applied our non-vacuity standard to the proposed design, unprompted

> *"A test asserting 'the layer system is deterministic' over a Locale with only `Uniform` layers
> **cannot fail** — every representation agrees trivially. Any determinism gate here must be bite-tested
> against a Locale with at least one layer in each of the five representations, including one
> mid-promotion."*

That is NV-2 (*the subject cannot vary*) predicted **before the check exists**. Recorded as a standing
obligation for whatever gate this design ships with.

### Gaps marked

⛔ No published measured benchmark of dense-array vs component-bag tile storage in any shipped game —
§4.3's numbers are arithmetic; the only empirical anchor is `bevy_sparse_tilemap` existing *because*
entity-per-tile degrades around 200×200. ⛔ Roaring's 4096 array↔bitmap threshold **not confirmed** by the
pages fetched. ⛔ Civ V/VI `CvPlot` layout is not public — the cited thread is Civ4/Colonization-lineage.
⛔ DF bit layouts, Factorio per-tile bytes, HoMM3 object ceilings — all unpublished. **Search budget
(200 calls) exhausted mid-run**; later gaps filled by direct fetch.


---

## 12 · Research intake — `Passage` (agent 4 of 7)

### `R-21` — ⭐ the real argument for `Passage`-as-node is not gameplay, it is that routing engines PAY to get here

> **OSRM converts the entire road network into an "edge-expanded graph" — *making edges themselves into
> nodes* — purely so that turn costs and turn restrictions can be expressed**, and *"all subsequent
> algorithms (Multi-Level Dijkstra, Contraction Hierarchies) will be based on this edge-expanded graph."*

**Because a `Passage` is already a node, the edge-expanded graph is our NATIVE representation.** Turn
restrictions live on the `(in_portal, out_portal)` pair inside the passage, free:

> *"You may enter the pass from the north gate but not exit south while the blockade holds."*

An edge-based model cannot express that without the expansion blow-up. **This belongs in doc 36 — it is a
stronger justification than the one we wrote.**

Three unrelated bodies of practice confirm the same choice: **EVE ships it** (`mapDenormalize` holds
stargates as positioned celestials; `mapSolarSystemJumps` is explicitly a *derived convenience* —
*"the object is the truth; the adjacency is a derived index"*); **Neo4j's guidance prescribes it**
(*"if you want to index a relationship property, this signals you should reconsider the design"* →
reify into a node); and **the standards forbid the alternative** — GQL and SQL/PGQ have **no hyperedges**,
so a three-ended edge is unrepresentable while a node with three portals is trivial.

### `R-22` — ⭐ OSM's `:conditional` IS our feature list, and it is a warning in our own vocabulary

`maxspeed:conditional = 60 @ 23:00-05:00` — the syntax covers time windows, **seasons**, **weather**,
vehicle class, user groups. That is tolls, weather, blockades, seasonal closure and faction control,
already generalised. And it is `;`-separated with **"the last matching value becomes the effective
restriction value"**.

The agent named the shape without being told the phrase:

> ***`;`-separated, last-match-wins ordering is the "an adjacent decision defeats it" failure shape.***
> Two individually-correct layer authors write two individually-correct rules, and the effective value
> depends on the order they happened to be concatenated in.

**Ship a typed `PRIORITY: u16` + a declared `FOLD`, never an ordering-sensitive string.**

The measured cost of the free-form alternative, from live taginfo: **112 933 distinct keys**, while the
*average way carries 2.4 tags* — a catastrophic long tail. And the consequence, stated plainly:
**"a routing build can drop 4 % of roads because their speed limit failed to cast to an integer"** —
silently. Under our rules a decode failure at write must be a **rejected write**, not a runtime skip.

### `R-23` — CRP's two-phase split is the plugin answer, and it converges with everything else

Customizable Route Planning separates **metric-independent preprocessing** (topology only) from **metric
customization** (costs), so a new cost function is customised into a *continental* network in **~10 s**.

Applied here: layers resolve into a flat `MetricTable` **once per epoch**; pathfinding reads only that.
**Layers are invisible to the hot loop.** At ~14 k arcs that resolve is microseconds, which supports a
blunt and valuable decision:

> **On any layer change, recompute the entire metric table. Do NOT build incremental invalidation.**
> A 1000× headroom margin buys the elimination of the whole stale-cache replay-divergence class.

### `R-24` — do NOT build contraction hierarchies

Route-planning research exists for continental graphs; hub-labeling studies report methods failing against
**10-hour / 256 GB** limits. **Our graph is ~8 k nodes / 14 k edges — the largest shipped MMO travel graph
in existence — and Dijkstra runs on it in under a millisecond in Python.**

> **Borrow the ARCHITECTURE from routing research, not the algorithms.**

### `R-25` — the reference budget, and it is humbling

| | |
|---|---|
| EVE Tranquility tick rate | **1 Hz** |
| Under TiDi | floored at **0.1 Hz** |
| Systems per normal node | **83** |
| Systems per *reinforced supernode* during a fleet fight | **4** |

**Our stated budget is 10× EVE's tick rate — so we have LESS per-entity headroom than EVE grants itself,
not more.** Fifth independent route to `M-1`: iterate an `occupied` Roaring bitmap, never the passage set;
**an empty passage costs exactly zero.** Plus: ambient content is a scheduled min-heap entry, not an
actor; encounter rolls are stateless `hash(world_seed, passage_id, tick_bucket, actor_id)` so *"is there
an ambush here right now"* is a **pure function** needing no simulation.

### `R-26` — what makes a passage content, and it is measurable rather than authored

**Niarja, 2020** — the natural experiment. One node changed hands; the safe Jita→Amarr route went from
9–10 jumps to 45–46 (**+36 systems**), and the game's trade economy re-routed. Passage topology *is*
content.

Decomposed, the five ingredients are all properties of the passage: **forced concentration** (topology
leaves no alternative) · **a discrete arrival locus** (you arrive *at a gate, at a coordinate* — the one
thing an ocean cannot provide) · **an enforcement gap** (CONCORD takes ~19 s in 0.5 sec space; the content
lives in that window) · transferable stakes · asymmetric commitment.

And the counter-example is economic, not spatial: **BDO's ocean is empty because reward density sits below
the alternatives, so nobody goes, so nobody preys.** *Emptiness is self-reinforcing.* Elite's supercruise
*has* the ambush mechanic and still reads as empty — because a volume has no chokepoints.

> **Recommendation: instrument passage traversals in the event log and let content systems subscribe to
> measured high-centrality passages. Do not hand-place bandits.** EVE didn't; `gatecamp.space` exists
> because the camps are an emergent, *measurable* property of traffic.

And the design note worth keeping: **success is congestion.** The point of a chokepoint is that it draws
crowds. EVE's answer was TiDi — degrade the rate rather than drop players. `capacity` policy should be
decided deliberately (queue / shard / degrade), not discovered.

### Gaps — including one the agent flagged against ITSELF

⛔ **G-4, self-flagged: *"No shipped MMO was found that uses a formal layered-attribute system on travel
edges. §4.2 is my synthesis… This is the least-grounded part of the report and the part most worth
adversarially reviewing."*** That is exactly the honesty this fan-out was for — the layer model is
synthesis, not observed prior art, and must be treated as a hypothesis.
⛔ EVE counts disagree between sources (8 285/13 753 vs 5 201/6 894 — plausibly k-space vs k+J-space, **not
confirmed**). ⛔ Niarja jump counts differ by one across sources; **cite the delta (+36), not the
endpoints.** ⛔ CRP/hub-labeling benchmark tables **could not be extracted** — the ~10 s figure is from
prose, not a table read. ⛔ BDO evidence is **player-side only**; no developer postmortem exists.

---

## 13 · Research intake — ⭐ the FEATURE-LAYER PLUGIN question (agent 5 of 7)

**This agent carried the PO's thesis. It validated it — and moved the failure to a different axis.**

### `R-27` — the thesis, reframed

> **"The map will not break under the weight of layers; it will break under the weight of layers that
> share a table, share a lifecycle assumption, share an update loop, and share a version number."**
> Design for **ISOLATION BETWEEN LAYERS**, not for capacity.

Storage volume is *not* the problem — 20 layers × 16 384 cells at 4–8 B is ~2 MB. Query is solved given an
index. **What kills these systems is coupling, lifecycle and versioning**, and the evidence is unusually
consistent across four unrelated ecosystems.

### `R-28` — three ecosystems SHIPPED an attachment API and then rewrote it

| system | what went wrong |
|---|---|
| **Forge → NeoForge** capability rework (2023) | Conflated *data* with *behaviour*; had to **split into two APIs**. Repeated positional queries were slow enough to need `BlockCapabilityCache` + **explicit manual invalidation**. Had to add per-attachment lifecycle (`copyOnDeath`). `Level`-scope attachments **removed entirely** — the generic mechanism was wrong at one scale. |
| **Bukkit `Metadata`** | **Leaks by construction.** Entities removed by other plugins *"are never removed from the world's metadata store, resulting in memory leak… this can quickly lead to out of memory errors."* |
| **Flecs / Bevy state-tags** | Orthogonal state machines as components ⇒ **combinatorial archetype explosion**. |

> *"This is your design, four years later. The three things they had to bolt on — behaviour/data split,
> query cache + explicit invalidation, declared lifecycle policy — design them in, not on."*

**And our case is WORSE than Bukkit's**: our nodes can be dematerialized *and* re-materialized, so
**"leaked" and "correctly retained" are indistinguishable without a declared policy.**

### `R-29` — ⭐⭐ THE HIGHEST-LEVERAGE FINDING: bind every layer to a `MapKind`, not to "nodes"

> **Weather on a `Region` is 200 rows. Weather on every node is 300 000.**

Almost nothing wants a value on *every* node. **Scale is axis 1; density is only axis 2.** This is a
**~1000× reduction that costs nothing and requires no cleverness** — it falls straight out of the closed
`MapKind` set we already have.

`home_kinds` becomes a **required** field validated on write (`layer.kind_violation`, sibling to
`map.containment_violation`). A layer needing two scales registers **two layers plus an explicit
aggregation function** — forcing the designer to *state* the aggregation instead of discovering it later
as a bug. Factorio's insight in other clothing: pollution, enemy expansion and pathfinding all run **per
32×32 chunk, never per tile.**

### `R-30` — the number to internalise, and it is brutal

> **~150 Unreal components that do LITERALLY NOTHING cost 1 ms on console.**

Our budget is 100 ms. 18 layers × 16 384 nodes = **295 000 attachments**. If any layer's default is
*"tick"*, we are **~2000× over budget before doing any work.** Hence `UpdatePolicy` with **no default**:
`EventDriven` · `Lazy` · `Scheduled{every, phase}` · `Immutable` — and the honest reading of `M-1`:

> *"It does not say 'don't have many layers'. It says **don't let layers ride the actor tick**. Layers are
> not actors."*

### `R-31` — Stellaris shipped the same fix TWICE, and it is a granularity fix, not a loop fix

Pop-level simulation collapsed late-game. The 4.0 fix was **not faster per-Pop code** — it was
**aggregation into Pop Groups**. And the second-order effect is the one to steal:

> Pop Groups are keyed by (species × stratum × ethics × faction), so **adding one more layer to the key
> MULTIPLIES the group count.** That is archetype fragmentation appearing in a grand-strategy engine that
> has never heard of ECS — **the same defect twice, in two paradigms**, which is the best argument that it
> is structural rather than incidental.

### `R-32` — inheritance: epoch-stamped LAZY invalidation, `O(depth ≤ 16)`, never `O(subtree)`

Do **not** copy inherited values down (doubles storage; turns a one-node write into a subtree write). Bump
an `ancestry_epoch` on ≤16 ancestors; every descendant discovers staleness on its next read via **one
integer compare**.

> A weather change over a `Region` containing **5 000 locales** costs **16 increments** and touches
> **zero** descendants.

Two rules that must be enforced or it silently breaks: the fold op must be **associative with an identity**
(property-tested at registration — non-associative fold + caching is a replay divergence that takes weeks
to find), and `stop_at` must include every **coordinate-root boundary from `SPG-A17`** (a Universe's
"weather" is not a Locale's weather).

### `R-33` — ownership enforced in three places, and only one of them matters

Type level (a `LayerWriter<L>` token the registry issues once) · **event-log validator —
`layer.foreign_write`, rejected on APPEND** · replay level (falls out of the second).

> *"This is the load-bearing check, because it holds across process boundaries, across replay, and against
> a mod, which the type system does not."*

Cross-layer **reads** are declared (`Derived::inputs`), the registry builds the dependency graph at load
and **rejects cycles** — turning *"quests secretly read weather"* from an undiscoverable implicit contract
into a declared edge you can draw.

### `R-34` — six determinism prohibitions, one of which we would certainly have hit

The one that matters most: **`LayerOrd` must be derived from the sorted set of `LayerId`s in the PINNED
RULESET DIGEST — never from registration order.** Otherwise **installing a mod silently invalidates every
replay.** Also: no hash-ordered iteration in simulation (⇒ `Rare` storage is a *sorted `Vec`*, a
determinism decision and not merely a memory one) · no ordering derived from allocation or `swap_remove`
history · no non-associative parallel folds · dirty sets **collected freely, drained in `NodeOrdinal`
order** · a phase discipline forbidding cross-layer reads within a write phase.

**And it proposed its own falsification, in our vocabulary:**

> A CI leg that replays the golden corpus **twice in one process, with shuffled registration order and a
> randomised hash seed**, asserting identical final-state hashes. *"Without that leg, rules 1–4 are
> unfalsifiable claims."* A single-order replay **cannot fail** on three of the six.

### `R-35` — schema evolution: retire a decoder, never delete it

DFU's fix chain is **never pruned** — that is why a 2011 Minecraft world still loads. A layer removed in v4
becomes a `Retired { decodes_through, migrate_into }` **tombstone that still decodes**. Deleting the
decoder makes the log un-replayable, and for an event-sourced world **that means the world is gone.**
Exactly our `WDS-A6` precedent (*"a generator version may not be removed while any reality pins it"*),
generalised — with the same acknowledged ongoing cost.

### Gaps — including one aimed at its own headline recommendation

⛔ **No canonical published map-data-model post-mortem was found.** The thesis rests on *rewrite* evidence
— *"a rewrite is a post-mortem with a diff attached"* — which the agent states plainly is weaker.
⛔ Staffordshire ECS paper **403-gated**; the ~2× iteration figure is from the abstract, not the tables.
⛔ Paradox primary sources **not retrieved**; the Pop Groups shape is well attested, specific claims are not.
⛔ Roaring performance for this workload **unmeasured** — *"would not put a performance claim in the spec
without them. Flag as a spike."*
⛔ **`Fold`-on-dematerialize is the agent's own synthesis, not prior art** — *"the highest-risk piece of the
recommendation and should get a prototype before it gets an axiom."*

---

## 14 · Research intake — `Universe` (agent 6 of 7)

**The only agent that COMPUTED rather than cited.** It ran the precision arithmetic and the result
invalidates an assumption in `SPG-A17`.

### `R-36` — ⭐⭐ f64 covers ONE of our fifteen orders of magnitude

| magnitude | f64 ULP |
|---|---|
| 1e6 m (planet-ish) | 1.16e-10 m |
| 1e12 m (~7 AU) | 0.12 mm |
| **1e15 m (0.1 ly)** | **0.125 m** |
| **1e18 m (≈106 ly — EVE's cluster)** | **128 m** |

- **f64 holds 1 mm precision only to ≈60 AU** — *one star system*.
- **f64 holds 1 m precision only to ≈0.95 ly** — *less than one interstellar hop*.
- **i64 millimetres saturates at 0.97 ly.** Even integer fixed-point cannot be flat-global.
- f32 integers stay exact only to 2²⁴ = 16 777 216 — the documented 16 777 km failure threshold.

> **No single numeric type spans the `Universe → Domain` edge.** Parent-relative transforms are therefore
> **not an optimisation in this design — they are the only thing that works.**

`SPG-A5`/`SPG-A17` are emphatically validated. Empirical confirmation: EVE stores universe coordinates at
1.0 = 1 metre across a ~106 ly cluster, which genuinely carries **~128 m granularity at the rim** — it
works only because every system rebases to its star at `[0,0,0]`.

### `R-37` — ⭐ and it pushes back on my `Transform`, correctly

Our simulation is **replayable and event-sourced**, and floating point is not reproducible across
machines: x87 80-bit vs SSE 64-bit intermediates, FMA contraction, and **transcendentals differing between
AMD and Intel** (Battlezone 2 hit this in production). Proposed instead:

```rust
pub struct Transform {
    pos:       [i64; 3],  // parent-relative, in units of 2^scale_exp metres
    rot:       [i32; 4],  // quantised unit quaternion
    scale_exp: i8,        // metres-per-unit = 2^scale_exp
}
```

i64 at 1 mm/unit spans ±0.97 ly — right for a `World`'s interior; at `scale_exp = 40` it spans past the
observable universe for a `Universe`'s children. **Each node declares its own quantum; conversion between
frames is an integer shift, bit-exact on every platform.** Float appears *only* at the render boundary.

**This is the SECOND independent agent to find the same defect** — `Region`/`Locale` reached it from
`GridAnchor` (a house at tile 137,42 must round-trip), this one from interstellar ULP. **Two directions,
one conclusion: `SPG-A17`'s transform must be integer.** The agent is fair about the alternative: keeping
f64 is defensible *if* the spec then states a per-tick state checksum as the mitigation — *"rather than
inherit the hazard silently."*

### `R-38` — Star Citizen independently built our `SpaceNode`, and it cost them 14 months

> *"A zone host can be a celestial body, a ship, a transit car, or a space station. A zone host itself is
> an entity so has coordinates in the zone that host it, all the way up the tree until you hit the root
> zone which is the only zone host that contains itself (and never moves)."*

That is `parent: Option<NodeId>` + relative `Transform` + `holder: Option<EntityId>` + a self-parented
root — arrived at independently. It validates `holder` specifically (a ship's hold as a node interior).

**Timeline: proposed Jan 2015 → dev May 2015 → AreaManager rewritten Nov 2015 → Object Containers Jan 2016
→ hierarchical culling Mar 2016. ~14 months to RETROFIT nested coordinate frames into an existing engine.**
We get it by designing it in.

### `R-39` — archetype ECS is disqualified, and Unity's own docs name our exact scenario

> *"Having a high number of archetypes with a low chunk count each means that your project has too many
> entities with different sets of components… **This is a common issue when working with many optional
> components**, as each unique combination creates a different archetype."* — and the number: **100 000
> entities each with a unique archetype allocates >1.5 GB** = **16 KiB per node**.

Three more, each independently disqualifying:
- **Structural change is `O(total bytes on the entity)`** — toggling one layer on a 50-layer node copies
  the other 49. Measured: remove+add **24 ns sparse-set vs 246 ns archetype**.
- **`Optional` is the pathological query shape and it is exactly ours** — flecs: *"a query that only has
  `Optional` terms will match all entities."* *"Give me every node plus whichever of the 50 layers it
  has"* is the worst case by construction.
- **Bevy: archetypes are NEVER reclaimed** — *"empty archetypes are not removed, and persist until the
  world is dropped"*, and query conflict-checking grows with **all** (archetype, component) pairs, *"not
  just the ones that match."* In a long-lived server sim that churns layers, archetype count ratchets
  **monotonically upward and taxes every unrelated query. For a persistent MMO this is disqualifying on
  its own.**

### `R-40` — and the JSONB bag crosses a hard cliff at exactly our layer count

50 layers × 64 B ≈ **3 800 B per node** against PostgreSQL's **~2 032 B** inline threshold. Crossing it
costs **2–10× on EVERY read of ANY key**, because detoasting is whole-value. Wide sparse columns fail
differently: 1 600-column cap, and **dropped columns permanently consume the budget**.

### `R-41` — the existence proof, and the single best idea in the research

**Minecraft 1.20.5** replaced the untyped NBT blob on `ItemStack` with a **`DataComponentMap`** — keys are
registered types carrying a codec. **~89 shipped component types, >100 with variants.**

> *"This is your existence proof: the shape works at ~100 layers, on every item stack, on phones."*

And from **GeoPackage**, `scope: ReadWrite | WriteOnly` on each registered extension:

> *"It lets a consumer that has never heard of layer 37 decide **by policy, not by guessing**, whether it
> may still safely read the node. Without it, 'unknown layer' is undecidable."*

Plus the **NeoForge footgun to design out**: their `getData(type)` **allocates and attaches a default if
absent** while `hasData(type)` does not — so one read-heavy path using the auto-vivifying accessor
materialises all 50 layers on every node it touches. **Make the allocating call impossible to type by
accident** (`get_or_default` says so in its name; `get_layer` never allocates).

### `R-42` — the most reassuring finding in the whole fan-out

OpenUSD — the model `SPG-A14` already borrows from — reports that composition cost scales with **prims
populated** *"but much, much less so with the number of properties."*

> **Adding data to nodes is cheap. Adding NODES is expensive.**

Which is the PO's thesis answered in the reassuring direction — *provided* layers are composed/resolved
rather than walked per node, and provided we never let a feature create nodes per datum (`R-8`).

### `R-43` — `NodeId` should split authored from generated

Reserve the top bit. **Authored** = a monotonic event-sourced counter. **Generated** = the low 63 bits are
a truncated content hash of `(parent_id, generation_rule_ref, local_address)` — *derivable, never stored,
identical on every machine and every replay*. That is EVE's ID-range-as-discriminator, No Man's Sky's
derive-don't-store (a 64-bit seed yielding ~1.8e19 planets with *"very little data stored on servers"*),
and our content-addressing constraint, in one field.

Also worth stealing from EVE: **a separate `position2D`** — *presentation layout is a distinct attribute
from simulation position.* Do not let the renderer derive the star map by projecting real coordinates.

### `R-44` — do not build graph machinery

Contraction Hierarchies answer shortest-path on an **18 M-node** road network in 91 µs after 5–10 min
preprocessing. **Our graph is ~10⁴.** A CSR adjacency for 8 000 nodes / 10 400 edges is **0.11 MiB**.
*"Use an in-memory CSR adjacency list and plain BFS/Dijkstra. Do not introduce a graph database, and do
not preprocess a hierarchy, until you have >10⁶ nodes and a profile."*

**Third agent to say this** (`Passage` said don't build CH; `World` said point→cell needs no index).

### Gaps — and one is a warning about the whole fan-out

⛔ **"No public ECS benchmark exceeds 6 components. There is no published benchmark of a 50-layer scenario
in any engine."** The archetype argument is *mechanism plus adjacent measurements*, **not** a direct
measurement of our case. ⛔ Elite `id64` bit widths — source unreachable; **do not cite widths**.
⛔ ltree-vs-CTE millisecond benchmarks — 403. ⛔ **BFS timings are CPython**; the "50–100× for Rust"
conversion is a rule of thumb the agent did not measure. ⛔ Timing-wheel citation could not be fetched.
⛔ DataFixerUpper bootstrap cost — *"widely complained about, never quantified publicly."*

---

## 15 · Research intake — `Domain` (agent 7 of 7 — FAN-OUT COMPLETE)

### `R-45` — ⭐⭐ THE DELIVERABLE: how a layer survives a Merge or a Sever

RimWorld's answer, and it is the mechanism the whole topology-op design was missing. **It does NOT transfer
layer data along node identity.** Before a rebuild it snapshots the layer **onto the CELLS**; after the
rebuild it **re-derives** onto the new nodes with a layer-specific reduction:

```csharp
// before: per-cell snapshot
SetCachedCellInfo(c, new CachedTempInfo(group.ID, group.CellCount, group.Temperature));
// after: cell-count-weighted mean over unique cached groups
num += current2.numCells;  num2 += current2.temperature * (float)current2.numCells;
result = num2 / (float)num;
```

> **Split a hot room in half → both halves inherit the heat. Merge hot + cold → mass-weighted mixture.
> NEITHER CASE IS SPECIAL-CASED.**

The reduction is **per layer**, and that is the point: `mean` for temperature · `max` for on-fire ·
`union` for permissions · `sum` for stored volume · `min` for structural integrity. Note the naive path is
**wrong by default** — a new group's constructor sets outdoor temperature, so the layer is *lost* unless
snapshot/reduce runs.

**Three layer classes, three mechanisms** (all shipped): **derived/simulable** → snapshot-per-cell then
reduce · **authored/non-derivable** (ownership, permissions, storage, timers) → store at the *finest
authored granularity* so a Sever needs **no migration at all** (SE stores ownership per block and derives
grid ownership by majority) · **cheap-recompute caches** → just destroy and rebuild.

### `R-46` — Space Engineers ships all four ops as DISTINCT edges, differing exactly in which layers cross

| edge | kinematics | power | items | terminal | **atmosphere** |
|---|---|---|---|---|---|
| Landing Gear (lock) | ✅ | ❌ | ❌ | ❌ | ❌ |
| Connector (dock) | ✅ | ✅ | ✅ | ✅ | ❌ |
| Merge Block (fuse) | ✅ | ✅ | ✅ | ✅ | **✅** |

*"Subgrids or mobile grids parked inside a pressurized room are not automatically also pressurized."*

⇒ **`EdgePolicy` is a matrix of `(LayerId × EdgeKind) → Propagates | Attenuates(f) | Blocks`**, declared at
layer registration and validated on write. Barotrauma's `Gap` is the attenuating case; Rust's building
privilege is the propagating case; SE's airtightness is the blocking case.

### `R-47` — three shipped bugs we can pre-empt, and one is a security defect

1. **State acquired in a Merge is not reverted on Sever.** SE: merge a ship to a station → it converts to
   static; unmerge → **it stays static**. Keen first called it intended, then reproduced it.
   ⇒ **Merge must record what it changed** so Sever can invert it. *"An op that is not invertible from its
   own event record is not event-sourced."*
2. **Identity by heuristic is a data-loss bug wearing a heuristic's clothes.** RimWorld picks the survivor
   by `RegionCount`; SE by mass. Fine for temperature. **For ownership and permissions it is a security
   defect** — and on a tie the winner is decided by *iteration order*, which is also a determinism defect.
   ⇒ **`Sever`/`Merge` must carry the surviving `NodeId` explicitly in the event.** Never compute it from
   geometry. If a policy must choose, it runs once at command-validation and its output is *written into
   the event*.
3. **Reparenting a moving frame across a top-level boundary is what everyone gets wrong.** VS #829: the
   ship's transform updates, the dimension binding does not — a **silent partial Graft**.
   ⇒ Graft is **one atomic event** that rewrites the edge, bumps `frame_epoch` on the whole subtree, and
   invalidates every cached world transform. Partial application must be *impossible*, not discouraged.

### `R-48` — 🔴 direct hit on our `Domain → Domain` recursion

Barotrauma's own devs document that over-fragmenting into many small linked hulls makes the fluid layer
**numerically unstable** — *"large spikes of water throwing the crew about before it eventually
equalises"* — and their proposed fix is to **collapse linked hulls into ONE computational entity**.

> **A palace as a Domain-of-Domains with an atmosphere/temperature layer is exactly the over-fragmented
> hull graph.** Refusing rigid-body physics does **not** exempt us from designing the equalisation.

⇒ Budget for a **simulation grouping COARSER than the structural nesting**. `SPG-R5` made 16×16 a default
rather than an invariant and said a palace is a *Domain of Domains* — this says that decision has a cost
we have not priced.

### `R-49` — `Mobility` means "my transform is re-evaluated", never "my contents move"

**Every shipped implementation stores the interior in its OWN static coordinate space and PROJECTS it.**
Valkyrien Skies keeps ship blocks in a *"shipyard"* at chunk coordinates in the millions and renders them
through a custom view matrix; interactions are transformed **back** into shipyard space.

And the 1998 precedent: **MERL's patent US 5 736 990** subdivides space into *locales*, each with its own
origin, related by 4×4 transforms, with a *"discriminator"* that signals handoff — motivated by the
identical argument, that at 3 000 miles from a global origin 32-bit float degrades to **~15 inches**.
**Our design is the converged answer, patented in 1998** — and `R-36`'s ULP table is the same finding
computed 28 years later.

VS's hardest bugs are instructive: **physics works, interaction doesn't** (#1196) because the world→ship
inverse transform in the input path is a *separate code path* from the physics one. ⇒ the MERL warning
applies verbatim: **the parent→child transform is directional and the inverse is not automatic —
materialise both.**

### `R-50` — the invalidation GRAPH explodes, not the data

**EnderIO #680:** a 192-block multiblock registered invalidation listeners in all 6 directions, and Forge
had **no way to remove one**. Result: **14.1 GB of a 14.3 GB heap consumed in ~2.5 hours**, old-gen GC
pauses averaging **4.4 s**, server lockups every 4–8 s. **Halving the block count fixed it immediately** —
it scaled with cell count.

⇒ Two independent fixes, adopt both: **registration is idempotent and notification is broadcast** (one
registration serves every listener), and **a listener declares its own liveness** — NeoForge now *refuses*
one without it (`BlockCapabilityCache::create(..., BooleanSupplier isValid, Runnable listener)`).

### `R-51` — layer presence is a BIT, never part of the node's type

Unity again, independently of `R-39`: chunks are **16 KB**, one archetype per chunk, and *"100 000 entities
that all have their own unique archetype… will allocate more than **1.5 GB** of chunk data, most of it
empty."* N optional layers ⇒ up to **2ⁿ archetypes**, and memory is **chunk-granular, not data-granular**.

Unity's own fix is the recommendation: **enableable components toggle WITHOUT a structural change.**
⇒ fixed `SpaceNode` layout + `LayerMask` presence bits + per-layer side tables.

And the tick axis matters more than the storage axis: *"most performance implication of having multiple
components comes from having to call virtual functions like Tick."* **`TickPolicy::Inert` must be the
default.** *Fifty inert layers cost approximately nothing. Five ticking ones cost everything.*

### `R-52` — when a Domain dies, evacuate; never delete

**EVE Asset Safety** is the shipped precedent: a destroyed structure's contents go to a **claim queue**,
not to deletion — 5 days at 0.5 % of value, or 20 days auto-delivery at 15 %.

⇒ When a `holder` entity dies, **the Domain does not.** Emit `HolderLost{node, entity}` and reparent to a
well-known *Limbo* node with a claim record. **Deleting a player's palace because its holder despawned is
unrecoverable in exactly the way CLAUDE.md's destructive-ops rule exists to prevent.**
Also enforce `holder ∉ descendants(node)` on write — cheap to check, impossible to debug at runtime.

### `R-53` — our `Domain`+`Passage` is cells-and-portals (Teller, 1992)

World = convex cells, adjacency = portal polygons, renderer does a **BFS through the portal graph**. The
30-year-old lesson: **portals are first-class objects with their own identity, and object→cell membership
is maintained INCREMENTALLY on crossing, never recomputed by search.** That is `R-14`'s `PortalSet` and
`Occupancy` arriving from a third direction — and it gives the per-Domain occupancy index for free, which
is what makes lazy materialization possible: *a Domain with zero occupants and no pending timers is a
candidate for dematerialization.*

### Gaps — including one that names a hole in our own design

🕳️ **`Domain → World` (the 內天地 inner-world case): NO PRIOR ART FOUND.** *"You are designing this without
precedent."* Compact Machines is the nearest analogue and its implementation could not be obtained.
🕳️ **An entire parallel thread did not return** — dungeon generation, roguelike level storage, seed+delta
persistence, Bethesda interior cells, and **documented per-interior object caps in FFXIV / ESO / EQ2 /
SWG**. The agent states plainly: *"Your `definition`/`Materialization` design and your per-Domain object
budget are under-researched. Recommend re-running that thread."*
🕳️ Star Citizen's zone implementation — both best sources 403'd; §1.2 is second-hand paraphrase.
🕳️ SE's merge source path (`MergeGridInternal`) was not in the fetched file; merge behaviour is wiki-sourced.
🕳️ **"Every performance claim in these ecosystems is qualitative. If you need numbers, you will have to
generate them."** — Forge, NeoForge and Fabric all describe their caches as *"a dramatic speedup"* with
**no published benchmark**, and the same holds for per-component memory, RimWorld rebuild cost under
controlled conditions, and ONI's room-prober milliseconds.

---

## 16 · Research intake — dungeon-gen + housing persistence (agent 8 — the gap `Domain` flagged, closed)

The `Domain` agent marked this thread as **not returned** and recommended re-running it. It returned.

### `R-54` — ⭐⭐ FFXIV splits the PLACEMENT budget from the RENDER budget, and nobody else does

The only shipped game that publishes both numbers, and it is the answer to *"how many things can a Domain
hold"*:

| estate | placed (patch 7.5) | **drawn** |
|---|---:|---:|
| Mansion | **600** | **400 on-screen, max, for any estate** |

…with a **published, deterministic culling order**: *"objects on a different floor to your character stop
being displayed, with **small, more distant** furnishings hidden first."* Two budgets, two reasons.

**And Yoshida's stated bottleneck is not the one everyone assumes.** Object counts are *"information we
have to **manage entirely via our servers**"* — the binding constraint was **rehydration, not steady
state**: at 1.5× the cap a server restart means the CPU *"has to memorize everything all over again,"*
**potentially tripling maintenance duration across multiple Worlds.** Servers crashed in testing at 1.5×.

> **A recursive design that never rehydrates the whole tree at once dodges FFXIV's real bottleneck by
> construction.** That is `Materialization` earning its place for a reason we had not written down.

### `R-55` — the meta-finding that corrects an industry belief

Across a dozen shipped MMOs, **only two studios ever publicly stated a reason for an interior object cap**
— Square Enix (**server CPU / restart state**) and ZeniMax (**client min-spec**) — and they named
**different bottlenecks**. ArenaNet published a cap *change* with no rationale at all; BioWare and SSG have
**no traceable statement** about the hook model.

> *"The common belief that 'everyone caps objects for client framerate' is **not supported by the
> record**. The best-documented case in the industry is a **server persistence** problem whose client
> problem was solved separately, by a different mechanism."*

### `R-56` — ⭐ THREE storage states, not two — and an absent node costs 4 bytes

**Luanti/Minetest** is the cleanest statement: **absent from the DB** (never referenced) · **present but
the `generated` bit is clear** · **generated**. **Minecraft** agrees and prices it: an ungenerated chunk
costs **4 bytes** — its location-table entry — and its `Status` is an **11-value generation-stage enum**
(`empty → structure_starts → … → full`), with anything below `full` being an explicit **proto-chunk**.

⇒ `Materialization` should be **three states plus a stage enum**, not a boolean, and *definition-only must
be nearly free*. This is `R-52`'s Limbo and `WDS-A1`'s baseline meeting in one field.

### `R-57` — ⭐ preload before load: answer membership without materializing

**OpenMW** ships exactly the query a lazy recursive tree cannot live without:

```cpp
enum State { State_Unloaded, State_Preloaded, State_Loaded };
```

`preload()` builds **only the sorted ID list**; `load()` materialises references. So *"does object X live
in Domain Y?"* is a `binary_search` **without paying to materialise Y**.

### `R-58` — two key spaces in one system, stated outright

**Bethesda/OpenMW:** *"Interior cells are indexed by this (it's the 'id'), for exterior cells it is
optional."* **Interiors are keyed by NAME; exteriors by GRID COORDINATE.** An interior is *"one bit plus
the absence of `XCLC`"* — it has **no position in any worldspace**.

This is `R-43`'s authored-vs-generated `NodeId` split arriving from a second direction, and it says
something our containment matrix does not yet: **`Locale` and `Domain` may legitimately use different
addressing.**

### `R-59` — door endpoints must stay resident while their Domain is unloaded

Bethesda routes a reference flagged `0x400` into **GRUP type 8 (Cell Persistent Children)** — *"persistent
references that remain across saves"* — vs type 9, temporary. **A door endpoint must be persistent so it
stays addressable while its cell is unloaded.**

And the bug to avoid: `XTEL` stores **only a destination REFR + transform, never a destination cell id**,
so a door pair is *two independent one-way records* — *"which is exactly why one-sided door links are a
classic mod bug."*

⇒ `R-14`'s `PortalSet` must be **bidirectional and first-class**, and portal endpoints must be resident at
a lower materialization tier than their Domain.

### `R-60` — reset/expiry is lazy, per-node, evaluated on load. Nothing ticks.

```cpp
if (getWorld()->getTimeStamp() - mLastRespawn > 24 * 30 * iMonthsToRespawn)
```

`mLastRespawn` is **per-cell state serialised into the save**; the interval is data-driven. **Sixth
independent route to `M-1`** — and its known exploit (*re-enter before the timer*) is a design choice, not
a bug.

But note the correctness failure it produced: Skyrim's respawn-flagged containers **destroy stored items**
on reset, and `NoRestZone` is the opt-out that makes player homes safe. **A data-loss bug produced by a
performance feature** — precisely the class CLAUDE.md's destructive-ops rule exists for.

### `R-61` — the canonical cautionary tale for seed + delta at MMO scale

**No Man's Sky:** **15 000 terrain edits, 10 000 protected, 256 buffers.** Past the cap, unprotected
buffers are overwritten and *"whatever was overwritten will result in **respawned terrain**"* — bases
become buried or airborne. Worse for a shared world: **visiting other players' heavily-edited bases
consumes your buffers**, and can wipe your own protected edits.

> **The delta store is finite, and when it overflows the base regenerates UNDER player-authored content.**

And the version half of the same problem: **Minecraft shipped generator drift as visible chunk-wall seams
in 1.7, then had to build a purpose-built *blending* migration in 1.18** — with player structures
explicitly *"intact, buried, or deteriorated."* `WDS-A6`'s *"a generator version may not be removed while
a reality pins it"* is the right rule; this is what the failure looks like when it is not.

### `R-62` — ⭐ constraint-solving layout falls over at ~30 rooms, and recursion is the fix

**Edgar** (configuration spaces + chain decomposition + simulated annealing) states it plainly:
**"fewer than 30 rooms; not suitable for large levels"**, with a configurable **timeout in milliseconds**
existing specifically to prevent deadlock. For the platformer variant, cycles were so expensive that
*"it often took **tens of seconds** to find a valid level"* — annealing had to be replaced with a greedy
algorithm.

> **This is the single most important negative result for the `Domain → Domain` design.** A palace is not
> one solve over its entire recursive descendant set. **Solve 12 chambers, then solve each chamber's 6
> sub-rooms independently.** Recursion is what makes layout tractable — which is `SPG-R5`'s *"a palace is
> a Domain of Domains, not one oversized grid"* getting a quantitative justification it did not have.

### `R-63` — generation should annotate stable nodes, never move or delete them

**Unexplored** (~50 modules, ~5 000 rules, **24 cycle types**, a 5×5 starting grid): **nodes are never
deleted or moved, only annotated.** Generation is a sequence of annotations over a *stable node identity*
— *"extremely friendly to event sourcing and deterministic replay."* **Semantic edges are first-class and
survive spatial rearrangement**: keys stay linked to their locks through every rewrite even as positions
change. And **cycles nest** — *"a new cycle inside of an existing one"* — the recursion precedent.

Dormans' foundational separation underneath it: **mission graph** (task dependencies) vs **space graph**
(rooms and connections), *"the same mission can be mapped to many different spaces."*

### `R-64` — roguelikes store a dense per-tile array and NEVER a room-object graph

Consistent across every codebase read: **rooms exist only as generation-time scaffolding.** NetHack's
`roomno` is a **6-bit back-reference stamped into the tile**; Angband's room budget is a *generator*
parameter with no runtime structure.

And **Brogue CE ships our exact persistence model**: every level carries its own `levelSeed`, and **the
save file is the seed plus the complete input log** — `loadSavedGame()` sets `playbackMode = true` and
replays every event. *Event sourcing, shipped, in a roguelike.*

Angband's **chunk list** is the other half: *"a list of saved chunks of world which can be reloaded at any
time. The initial example is the town, which is saved immediately after generation and restored when the
player returns"* — **exactly "some Domains materialise once and stick, most never do."**

### `R-65` — containment compresses the budget, and two games ship it

**Ultima Online:** *"Locked down **containers** count as **one** lockdown."* **EQ2:** the Moving Crate has
its **own separate item limit** — 400 placed *and* 400 crated.

> ⇒ **An unmaterialised child Domain must not consume its parent's budget.** That is the seam a recursive
> tree wants, and it is shipped in two independent games.

Also worth stealing: **budget by object CLASS, not flat count** — ESO runs four separate buckets
(Traditional / Special / Collectible / Special Collectible) *because those classes have different runtime
costs*; New World caps light sources separately by tier (4/6/8/10); FFXIV reduced shadow-casting lights
specifically for PS4. **A flat count is a cheap proxy for a real cost budget, and everyone who shipped one
eventually added classes.**

### `R-66` — the authoring throughput number, and it justifies the 16×16 default

Skyrim's dungeon team: **400+ unique interior cells, 300+ dungeons, ~2.5 years, 10 people** (8 designers +
2 kit artists) — **~40 interior cells per person.** That rate is only reachable because kit pieces snap to
a grid with standardised footprints that are *"multiples of each other"*.

> **The constrained grid is what makes the throughput possible.** `SPG-R5` kept 16×16 as a *default*; this
> is the argument for why a default that authors actually snap to matters more than the number itself.

### Gaps

🕳️ **Valheim's `.fwl`/`.db` seed-vs-modification split** — *"notable gap, the closest analogue to
seed+delta with a documented generator-version break."* Both wikis blocked (402/401).
🕳️ **DunGen** — publisher domains no longer resolve; **no data-model detail obtained.**
🕳️ Dormans 2010 rule names/numbers — PDF extraction failed on all hosts. **Do not quote rule counts.**
🕳️ **SWG "sprawl broke it"** — *"no developer statement found, only player inference."*
🕳️ LOTRO/SWTOR hook-model rationale — **no dev statement exists.**
🕳️ No per-interior load-time measurement, and **no postmortem of an interior/instance system failing at
scale**, anywhere.


---

## 17 · The load test — what the census broke

Running §4's layer model against the **real** feature load (69 ids, 134 docs, 36 folders) plus a
hypothesised future load found **six shapes it cannot carry**. Recorded here because a census that only
confirms a model is not a test.

| # | the feature that breaks it | what is missing |
|---|---|---|
| `SDF-F1` | **`TDIL_001`** — a 4-clock relativity model with `ObservationAdvance` | `Decay`-on-read stores `(value, as_of_tick)` and **§4 named no clock**. Worse: if a value advances *on observation*, **who observed it changes the answer** — a replay divergence the moment two observers differ |
| `SDF-F2` | `FAC_001` · `PLT_001/002` · sect territory | **border/adjacency has no index and no phase.** A per-node `faction_id` answers *"who owns this"*, never *"where do two factions border"*. Paradox ships a separate `adjacencies.csv` for exactly this reason |
| `SDF-F3` | **`PROG_001` × `SPG-A1`** — a cultivator advancing a realm **grows their 內天地** | that is a *progression feature performing a Graft*. Layers have an `owner` enforced by `layer.foreign_write`; **topology has none.** The one graph everything hangs from is the only unowned thing in the design |
| `SDF-F4` | `DL_001` schedules · `R-26`'s measured passage traffic | `Derived{inputs: LayerSet}` is a function of *current layers*. *"How travelled is this passage"* — which `R-26` makes the load-bearing input for emergent content — is a function of **history** |
| `SDF-F5` | `PL_001..007` + every LLM NPC decision | **§3 is a WRITE contract.** The read that assembles *"what is here"* into a prompt must be deterministic AND bounded, and nothing specifies it. Doc 17's `R8` covers the actor side only |
| `SDF-F6` | formations (陣法) · auras · weather fronts | **layers are keyed by NODE; these are keyed by VOLUME.** `R-9`'s four-shape taxonomy had `Region` (sparse shape + predicate) for this and **§4 dropped it**, keeping only node-keyed classes |

**What the census CONFIRMED, and it is the model's best result here:** every non-hypothetical feature binds
to **exactly one `MapKind`** — the column is never ambiguous across all 69. `SDF-A5`'s required
`home_kinds` survives its first real load, and the ~1000× reduction is available to all of them.

**And a gap in what had just been committed:** `T1..T9` never says which tables are **reality-scoped**.
Doc 37 is explicit that the node tree is *"per-reality Postgres"* while the baseline is content-addressed
and shared by digest — §5 said neither, and **no multi-reality measurement exists for space** where the
actor track ran a whole red-team round on it. `SDF-Q11`.


---

## 18 · `SDF-F3` worked — and a bigger finding was underneath it

### `SDF-F7` — the matrix legalises an edge whose cost is unbounded, and nothing prices it

Three sealed facts nobody had put in one sentence: the 內天地 interior is **granted at RUNTIME by a
gameplay event** (doc 36:120 — *"not authored at world creation"*) · **`Domain → World` is legal**
(doc 36:396 + footnote — *"an interior that contains an entire world"*) · a production `World` is
**16 384 cells** (`GEO-D14`).

| scenario | inner-world nodes | vs the authored world |
|---|---:|---:|
| bare `Domain` + ~8 chambers, 500 cultivators | 4 000 | 0.24× — fine |
| inner world **contains a `World`**, 100 cultivators | 1 638 400 | **100×** |
| …500 cultivators | 8 192 000 | **500×** |

**It is a progression treadmill, so it grows monotonically with playtime.** `PCU`, `node budget` and
`quota` return **zero hits** across the map docs.

> **Not an argument to remove the edge** — it is the PO's stress case and doc 36 survived it deliberately.
> It is an argument that **legalising an edge is not pricing it**, and the matrix does the first only.

### The answer to `SDF-F3`

**A layer's single-owner rule does not transfer.** A layer is one column; **the tree is one structure many
features must legitimately modify.** So: a capability **per operation kind**, not ownership per node.

- **`SDF-A14`** `TopologyCapability { module, ops, home_kinds, budget }` → `topology.foreign_write`.
- **`SDF-A15`** invariants checked **centrally** — *"with six writers and five invariants there are thirty
  places to get it wrong instead of five."*
- **`SDF-A16`** one atomic event, **invertible from its own record** (VS #829's silent partial Graft; SE's
  merge-to-static that Sever cannot undo).
- **`SDF-A17`** a **node budget** charged to a principal, where a **Graft TRANSFERS the charge** — SE's
  PCU rule verbatim. **Exceeding it is a REFUSED WRITE, never a silent prune** (`R-61`: No Man's Sky
  overwrites the oldest buffers and bases end up buried). *A refused write is a design surface; a silent
  prune is data loss with a UI.*

> **`SDF-A17` gives `M-1` its missing half: the live set bounds what TICKS, the budget bounds what
> EXISTS.** Doc 36 had neither.

Not settled, each now an open row: the numbers (`SDF-Q12`) · whether a **dematerialised** subtree is
charged (`SDF-Q13`) · **Limbo's budget is unowned by construction** since a Domain outlives its dead
holder (`SDF-Q14` — a slow leak with a name).


---

## 19 · The growth cluster, analysed — five closed, one scoped, and the scoped one is the finding

PO: *these questions are not mine to settle; dig into them and analyse.* Correct — they are engineering
questions with researchable answers. **Six open rows turned out to be one question wearing six hats:
what bounds the world's growth?**

### The move that unlocked it — there are THREE budgets, not one

`SDF-Q13` looked contradictory because the research said both things. It said both things because
**"budget" meant three different costs**:

| budget | denominated in | cost class | charged when |
|---|---|---|---|
| **node budget** | nodes | **storage** — a row exists | **always** |
| **live set** | nodes | **CPU** — it ticks | only materialised |
| **object budget** | entities in a `Domain` | **render + sim** | only materialised |

⇒ `SDF-A18`. `R-65`'s evidence (UO's *"a locked-down container counts as one lockdown"*, EQ2's Moving
Crate) is about the **object** budget. **Dematerialising frees CPU, not storage** — a row does not stop
existing because nobody is looking at it. **This resolved `Q13` in the OPPOSITE direction to my earlier
lean.**

### The four other closures

- **`Q3` → `SDF-A19`: scale-bound `Domain → World`, do not quota it.** The containment matrix says *which*
  kinds nest; a **scale matrix** says *at what scale*. Bounded to `Pocket`: **16× cheaper**, genre-correct
  (洞天福地 — a grotto-heaven *is* a pocket realm), and it fails at **design** time rather than mid-breakthrough.
- **`Q14` → `SDF-A20`: Limbo is not a parent, it is a QUEUE WITH A DEADLINE.** A parent is unbounded; a
  deadline is not. EVE Asset Safety is the shipped model (5 d @ 0.5 %, 20 d @ 15 %, abandonment forfeits).
  It gives the deletion *a deadline, a price and a policy* rather than removing it.
- **`Q4` → `SDF-A21`: bound + refuse + COMPACT.** Refusing alone is worse UX than NMS's silent prune,
  because the player eventually cannot edit at all. Snapshot-compaction folds divergence into a new
  baseline `H'` so the bound is on **un-compacted** delta. **Not in doc 37 — `compact`/`truncate`/`fold`
  return zero hits. A gap in a doc committed two commits ago.**
- **`Q2` → `SDF-A22`: TWO numbers**, placement + render, with a published deterministic culling order.
  FFXIV is the only shipped game publishing both, and its real bottleneck was **rehydration** — which our
  lazily-materialised tree dodges by construction.

### `SDF-F8` — the one that does NOT close, and why that is the result

Node budget is **storage**, so it is denominated in bytes. At the computed 96 B/node, 1 M nodes ≈ 91.5 MiB.
Take 1 M per reality, reserve half for authored content, 1 000 active players ⇒ **500 nodes per player**.

> **A `Pocket` inner world is 1 024 cells — DOUBLE that.** So `SDF-A19`'s 16× improvement is **still
> insufficient if inner worlds are common.**

It closes only if **神境 is rare** — and *"how many players reach the realm that grants an interior"* is a
**`PROG_001` parameter that neither doc names.**

> **The spatial budget's viability depends on a progression decision, and a rebalance could multiply the
> map tier's storage by an order of magnitude with nobody noticing the coupling.**

⇒ `SDF-Q12` **cannot be closed by the space tier alone.** That is not a deferral for lack of effort — it
is the correct answer, and **it took doing the arithmetic to find it.** What would close it: a *measured*
node-row size including layer sidecars (this used a computed 96 B), plus a `PROG_001` statement of
expected realm distribution. The provisional numbers are stated **with their derivation** so they are
falsifiable rather than authoritative.


---

## 20 · The read-path cluster — three closed, and one of them by DELETING a design

Same shape as §19: three open rows, one question. **§3 is a WRITE contract, so what shape are the READS?**

**The asymmetry that makes reads a separate problem:** *a write names its target; a read must FIND its
targets.* Writes are localised by construction; every interesting read is relational.

### `SDF-A23` — all three reads produce ONE result type; only the producer differs

`Q9` *what is here* → an **interval** producer · `Q6` *where do factions border* → an **adjacency**
producer · `Q10` *what is under this shape* → a **geometry** producer. All three yield **a sorted
node-set**, and after that it is bitmap algebra.

This is not tidiness: it satisfies **`SDF-A4`'s determinism prohibitions structurally rather than by
discipline.** A sorted set intersected in fixed order cannot depend on hash order, allocation order, or
which feature asked first. The alternative makes `SDF-A4` a rule that must be *remembered* in a dozen
traversals.

### `SDF-Q10` closed by DELETING a storage class

`SDF-F6` said shapes are volume-keyed and `R-9`'s `Shape` class had been dropped from §4. The instinct is
to add it back. **Wrong.** `SDF-A24`: a shape is an **authoring/command** concept that resolves to a
node-set at **write time** and stores as ordinary `Sparse`.

Checked against every case that would break it — a formation over cells, a moving weather front
(`Scheduled{600}` over ~200 `Region`s), a blast radius in a transient `Arena` — all survive. **The only
defeater is a topology change under the shape, and `SDF-A16` already makes that an event, so the
re-resolve is a subscriber, not a scan.**

> Closing a finding by **removing** a permanent surface rather than adding one is the better outcome.

### `SDF-Q6` — the finding: there are TWO adjacency relations and only one was named

`SPG-A4`'s containment-≠-connectivity distinction, **arriving one level down.** Two `Locale`s can share a
geographic border with **no road between them** — and for territory purposes they plainly border each
other; an army marches overland.

| relation | source | mutable | ordering |
|---|---|---|---|
| **Geometric** | the generated mesh — `neighbors: Vec<Vec<u32>>`, *"sorted ascending + deduped; symmetric"* (`world-gen/src/mesh.rs:38`); degree validated ∈[3,12] | **no** — part of the baseline | **already sorted** |
| **Connective** | `PortalSet` (`T3`) | yes | maintained sorted |

**Both already exist in the repo; only one had a name.** Paradox corroborates from the other side —
`adjacencies.csv` ships *separately* from the province raster because special adjacency is not derivable
from geometric adjacency.

And the border query needs **no index and no cache**: one pass over the set's bits, ~6 000 membership
tests at |X|=1000 — cheaper than the invalidation bookkeeping a cache would need. The mesh's neighbours
being pre-sorted makes it deterministic for free.

### `SDF-Q9` — the projection is declared per LAYER, never per reader

The trap is subtle: if each **reader** picks which layers to include, the prompt's content is a function of
**which features happen to be loaded** — `SDF-A4` rule 2 (*a mod silently invalidates every replay*)
reappearing on the read path, where nobody would look for it.

`SDF-A26`: `LayerDef` gains `projection`, declared by the layer's **owner**, no default. **The reader
chooses a budget, never a set.** And the view's bounds mostly already exist — ancestors are capped at
**≤16 by `DP-Ch1`'s DB CHECK**, which is why reusing that invariant beats inventing a traversal limit.

Two new rows: `SDF-Q15` (fan-out/occupant caps — needs a measured prompt cost, same shape as `Q12`) and
`SDF-Q16` (does geometric adjacency exist above `Locale`? `R-2` suggests region adjacency is **authored or
derived once at S4**, not computed per query).


---

## 21 · The last four — and the register now closes on measurement, not on argument

Two pairs, and both resolved by finding that **the containment tree is not the only tree** — and that the
other trees **already exist in the repo, unnamed**.

### `SDF-Q1` → `SDF-A27`: the simulation group is per-LAYER connected components

`R-48` was the sharpest warning of the fan-out: Barotrauma's devs document that over-fragmenting into many
small linked hulls makes the fluid layer **numerically unstable** — *"large spikes of water throwing the
crew about"* — and propose collapsing them into one computational entity. **A palace as a Domain-of-Domains
with an atmosphere layer is that graph**, so `SPG-R5`'s decision has a real cost.

The instinct is a second, hand-authored coarser tree. **The right answer was already built:** `R-46`'s
`EdgePolicy` matrix, from SE shipping four topology edges with four propagation sets.

> **The group for layer `L` = connected components under `EdgePolicy(L) == Propagates`.**

Per-layer, and it **must** be — air does not group like heat, because a closed door blocks air and conducts
heat. No new authoring surface: an author saying *"this door blocks air"* has already declared the
grouping. And the cure is automatic — a palace of 30 chambers with open archways is **one** air group.
Barotrauma had to add `linked hulls` by hand.

### `SDF-Q5` → `SDF-A28`: the node's realm clock, and `LayerDef` needs no clock field after all

`SDF-F1` said `Decay` had four candidate clocks and named none, and that if a value advances *on
observation* then **who observed it changes the answer**. **The repo already answered this and doc 41 had
not looked:** `TDIL`:34 maps *"coordinate time t → realm_clock"* and :644 records the shipped mechanic —
**天上一日人間一年 via channel `rate = 0.0027`**. The realm clock is **already a per-channel property**.

So: a decaying layer advances on **the realm clock of its node's nearest realm-declaring ancestor, never
the reader's**. An observer *samples*; it does not advance. `TDIL-A11`'s lazy advance stays exactly as
specified — it advances the **channel's** clock.

Two consequences: **`LayerDef` does NOT need a clock field** (a finding resolved by *deleting* the fix it
appeared to demand — adding one would be a second source of truth for something the tree already knows);
and the **內天地 gets richer, not harder** — an inner world declaring its own rate is *literally the
Journey-to-the-West mechanic already supported*.

### `SDF-Q8` → `SDF-A29`: history aggregates are PROJECTIONS, and the tier already ships

`crates/projections`, `projection-golden`, `projection-reference` exist today, and doc 17 already specifies
projections as *"derived; rebuildable from `event_log`."* **A layer is read AND written by the simulation;
a projection is only read.** Putting a read-model in the layer store would give it a second rebuild
semantics — the *"one home, one name"* violation this repo has paid for before. The safety rule: a
projection read inside a tick must be against a **pinned version**, or it is `SDF-A4` rule 5 in a new
costume.

### `SDF-Q11` → `SDF-A30`: scope follows DERIVATION

**Seed-derived → shared by digest · log-derived → per-reality · registry → per-ruleset.** That settles all
nine tables at once, and it is more than bookkeeping: **a hundred realities forked from one book share ONE
baseline (14.9 MB at `Megaplanet`) and pay per-reality only for divergence.** That is `WDS-A1` delivering
its actual value, which nothing had stated in scope terms.

---

### Where the register stands

**Thirteen of seventeen resolved.** The four that remain — `Q12` (budget numbers), `Q15`
(fan-out/occupant caps), `Q16` (geometric adjacency above `Locale`), `Q17` (the multi-reality tax) —
**every one of them now needs a MEASUREMENT rather than an argument.**

> ⚠ **Corrected on the §22 pass.** This paragraph read *"Twelve of seventeen… the five that remain"* and
> then listed four — it was wrong twice in one sentence, in opposite directions. Counting the table gives
> **13 resolved, 4 open**. A miscount in a summary line is how a register stops being an inventory.

> That is the honest shape of a first pass reaching its limit: the design questions are answered, and what
> is left is the arithmetic nobody has run. `Q12` additionally cannot be closed by this tier at all, since
> its answer depends on a `PROG_001` parameter (`SDF-F8`).

---

## 22 · Slice 7 discharged — every research finding adjudicated, row by row

> **Why this was owed.** The slice board carried slice 7 as **partial** for the whole arc, with the honest
> note *"a row-by-row table is still owed."* The first pass adjudicated the fan-out **in prose** — six
> accepted as `SDF-R1..R6`, four routed to `SDF-Q1..Q4`, *"the rest folded into `SDF-A1..A12`."* **That
> last clause was the problem: it is a claim about 56 findings that nobody could check.**
>
> **What doing it found: `SDF-F9` — eleven findings had been adopted NOWHERE**, and not one of them had
> been *rejected*. The doc had taken each one's **conclusion** and dropped the **rule underneath it**.
> `R-51` is the clearest: *"do not use an archetype ECS"* was adopted; *"layer presence is a bit, never
> part of the node's type"* — the mechanism that makes the conclusion implementable — was not.
>
> **Eight were folded into doc 41 on this pass** (§1 · §4 · §5 · §11.5), **two became `SDF-Q18`**, and
> **one (`R-21`) is owed to sealed doc 36 with no amendment row** — eleven. *(`R-10` and `R-23` are also
> unadopted here but are **correctly** out of scope, routed to combat and travel; they are dispositions,
> not gaps.)* The table below is the evidence, and it is the artefact that made the gap visible: prose
> could hold *"the rest folded in"*; a table with 66 rows cannot.

**Legend.** `A→` adopted as an axiom · `R→` became an amendment against a sealed doc · `Q→` routed to an
open row · `F→` became a finding · `≡` corroborates something already decided (no new surface) ·
`⊘` dissolved — the design makes the problem not arise · `↗` another tier owns it · `✚` **folded in on
THIS pass** (had no home) · `▪` recorded as a warning/gap only.

### `World` (§9)

| # | subject | disposition |
|---|---|---|
| `R-1` | live set must be a data structure, not an adjective | `≡` `M-1` from the opposite direction — upgrades `SDF-R1` from *my measurement* to *measurement + convergent prior art* |
| `R-2` | Paradox: one immutable ID raster + N cheap overlays, shipped 15 years | `A→` `SDF-A5` + `SDF-A8`. **This is the PO's thesis already solved by a studio that lived it** |
| `R-3` | SoA vs `HashMap`-per-cell vs 50-field struct (13–33× worse) | `A→` `SDF-A8` |
| `R-4` | EU4 crashes past 32 768 provinces (`i16`); 84 B/cell flat vs 912 B JSON; point→cell needs no index | `✚` **id widths had no home** — now §5 `T1` (`u32` cells / `u64` `NodeId`). The byte figures feed `M-2` |
| `R-5` | a general ECS is machinery we pay for and never use — our cells never change composition | `✚` the **refusal was never stated**; now §4 `SDF-A8` |

### `Arena` (§10)

| # | subject | disposition |
|---|---|---|
| `R-6` | ⭐ `Arena` (a place) ≠ `Encounter` (a fight); Foundry ships `scene` as an FK | `R→` `SDF-R4` · `T9` |
| `R-7` | in-place combat is not replayable without a **closure** | `R→` `SDF-R4` — *"in-place means no separate SPACE, not no isolation boundary"* |
| `R-8` | HARD RULE: combat data layers are **never** `SpaceNode`s | `≡` third route to `M-1`; the prohibition lives in `SDF-A5` + `SDF-A17`'s node budget |
| `R-9` | four layer *shapes* (Field/Region/Effect/Derived) + Dave Mark's composition algebra | `A→` `SDF-A8` (Field/Effect/Derived). **`Region` was dropped** → `F→` `SDF-F6` → `⊘` `SDF-A24` (a shape is authoring, not storage). The algebra is partially covered by `SDF-A11`'s fold |
| `R-10` | tick statuses on **encounter turn boundaries**, not the world tick (~37×) | `↗` combat tier (`COMB_*`) — duration in encounter time is not a space concern. Recorded, not adopted here |
| `R-11` | `HashMap` seeding · f32/f64 not bit-reproducible · Foundry ties broken alphabetically | `A→` `SDF-A4` rules 1 + 6; the fixed-point half → `R→` `SDF-R2` |
| `R-12` | Foundry does not specify how overlapping Regions resolve | `⊘` **dissolved by `SDF-A7`** — one writer per layer means two authors cannot contend for one value; the total order survives as `SDF-A4` rule 2 |

### `Region` + `Locale` (§11) — the first agent to read our shipped code

| # | subject | disposition |
|---|---|---|
| `R-13` | ⭐ a float `Transform` cannot express a discrete tile anchor and drifts under replay | `R→` `SDF-R2` |
| `R-14` | ⭐ containment ≠ connectivity; `parent` cannot express traversal | `R→` `SDF-R3` · `T3` |
| `R-15` | the memory outcome is decided by the DEFAULT, not the layer count | `A→` `SDF-A8` (the mix table is quoted verbatim in §4) |
| `R-16` | no layer ticks; `Decay` computes on read; RimWorld's `snowGrid` is the anti-pattern | `A→` `SDF-A9` |
| `R-17` | fog of war in the shared map is a **tenancy defect** by our own standard | `A→` §6 census + `PerObserver` storage |
| `R-18` | HoMM3 bakes renderer state into the map file (not content-addressable); RimWorld's core does not dogfood its own extension point | `✚` **both halves had no home** — now §5 `T6` (*store semantics, derive presentation*; owed to doc 37) and §4 `SDF-A6` (*the core registers through the identical mechanism*) |
| `R-19` | `LayerId` from an ordered append-only manifest; tombstone, never renumber | `A→` `SDF-A4` rule 2 + `SDF-A12` |
| `R-20` | applied **our** non-vacuity standard to the design, unprompted | `A→` §8 obligation #1, quoted verbatim |

### `Passage` (§12)

| # | subject | disposition |
|---|---|---|
| `R-21` | ⭐ OSRM pays to build an edge-expanded graph; **because a `Passage` is a node, that is our native representation** | `▪` **the decision is already made; the better justification is owed to doc 36** and is not in any amendment row. Recorded here rather than silently kept |
| `R-22` | OSM `:conditional` is our feature list; `;`-separated last-match-wins is the adjacent-decision shape | `A→` `SDF-A4` rule 4 + `SDF-A11`'s declared fold; *decode failure at write ⇒ rejected write* → `SDF-A15` |
| `R-23` | CRP two-phase; recompute the whole metric table; do **not** build incremental invalidation | `↗` travel tier. Its *metric epoch* is cited by `SDF-A29`/`SDF-A4` rule 7 |
| `R-24` | do not build contraction hierarchies — our graph is 10⁴ | `↗` travel tier (third agent to say it) |
| `R-25` | EVE runs at **1 Hz**; we budget 10× that with less headroom | `≡` fifth route to `M-1` |
| `R-26` | passage traffic is **measurable**, and measured centrality should drive content | `F→` `SDF-F4` → `A→` `SDF-A29` (projections) |

### The plugin question (§13) — the PO's thesis, carried by its own agent

| # | subject | disposition |
|---|---|---|
| `R-27` | design for **isolation between layers**, not for capacity | `A→` the frame of all of §4 |
| `R-28` | three ecosystems shipped an attachment API and rewrote it | `A→` `SDF-A10` (declared lifecycle) + `SDF-A11` (invalidation) |
| `R-29` | ⭐⭐ bind every layer to a `MapKind` — 200 rows vs 300 000 | `A→` `SDF-A5` · `R→` `SDF-R5`. **The highest-leverage finding in the fan-out** |
| `R-30` | ~150 Unreal components doing nothing cost 1 ms | `A→` `SDF-A9` (no default) |
| `R-31` | Stellaris fixed it by **aggregation**, and adding a key multiplies the groups | `≡` archetype fragmentation in a second paradigm |
| `R-32` | epoch-stamped lazy invalidation, `O(depth ≤ 16)` | `A→` `SDF-A11` |
| `R-33` | ownership enforced in three places; only the event-log validator matters | `A→` `SDF-A7` |
| `R-34` | six determinism prohibitions + its own falsification leg | `A→` `SDF-A4` rules 1–5 + §8 obligation #2 |
| `R-35` | retire a decoder, never delete it (DFU's chain is never pruned) | `A→` `SDF-A12` |

### `Universe` (§14) — the only agent that computed rather than cited

| # | subject | disposition |
|---|---|---|
| `R-36` | ⭐⭐ f64 covers **one** of our fifteen orders of magnitude | `R→` `SDF-R2`; emphatically validates `SPG-A5` |
| `R-37` | ⭐ the integer `Transform` (`pos: [i64;3]`, `scale_exp: i8`) | `R→` `SDF-R2` — second agent, opposite direction |
| `R-38` | Star Citizen built our `SpaceNode` independently and paid 14 months to retrofit it | `≡` validates `holder` specifically |
| `R-39` | archetype ECS disqualified — `Optional` is the pathological shape, and it is ours | `✚` the **refusal had no home**; now §4 `SDF-A8` with all four reasons |
| `R-40` | a JSONB bag crosses Postgres' ~2 032 B TOAST cliff at exactly our layer count | `A→` `SDF-A8` / `T5` (one sidecar per layer) |
| `R-41` | Minecraft's `DataComponentMap` is the existence proof; GeoPackage's `scope`; **NeoForge's auto-vivifying accessor** | `A→` `scope` in `SDF-A6`. `✚` the **footgun had no home** — now §4: no accessor may materialise a layer as a side effect of reading it |
| `R-42` | adding data to nodes is cheap; adding **nodes** is expensive | `A→` `SDF-A17` · `F→` `SDF-F7` |
| `R-43` | `NodeId` should split authored (counter) from generated (content hash) | `Q→` **`SDF-Q18`, opened by this pass** |
| `R-44` | do not build graph machinery | `↗` travel tier |

### `Domain` (§15)

| # | subject | disposition |
|---|---|---|
| `R-45` | ⭐⭐ RimWorld snapshots layers onto **cells** and re-derives — never transfers along node identity | `A→` `SDF-A10` |
| `R-46` | Space Engineers ships four edges differing exactly in which layers cross | `A→` `SDF-A27` — **and the `edges` field it implies was missing from `LayerDef` until this pass** (§4) |
| `R-47` | Merge not invertible · identity by heuristic is a security defect · partial Graft | `A→` `SDF-A16` + `SDF-A10` (the surviving `NodeId` travels in the event) |
| `R-48` | 🔴 over-fragmented hulls make a fluid layer numerically unstable | `Q→` `SDF-Q1` → `A→` `SDF-A27` |
| `R-49` | `Mobility` means *my transform is re-evaluated*; materialise **both** directions | `A→` `T8` frame-epoch index; the inverse-transform warning is carried in §3 phase 2 |
| `R-50` | EnderIO: 14.1 GB of a 14.3 GB heap consumed by an invalidation listener graph | `⊘` **dissolved by `SDF-A11`** — epoch-stamped lazy invalidation registers no listeners, so there is nothing to leak |
| `R-51` | layer presence is a **bit**, never part of the node's type; `Inert` must be the default | `✚` the **presence bit had no home**; now §4 + §5 `T1`. The tick half was already `SDF-A9` |
| `R-52` | when a `Domain` dies, evacuate — never delete (EVE Asset Safety) | `Q→` `SDF-Q14` → `A→` `SDF-A20` |
| `R-53` | Teller 1992: portals are first-class; membership maintained **on crossing**, never by search | `A→` `T3` + `T7` |

### dungeon-gen + housing persistence (§16) — the thread `Domain` flagged as not returned

| # | subject | disposition |
|---|---|---|
| `R-54` | ⭐⭐ FFXIV publishes **both** caps (600 placed / 400 drawn) and its bottleneck was **rehydration** | `A→` `SDF-A22` |
| `R-55` | only two studios ever stated a reason for an object cap, **and they named different ones** | `▪` corrects an industry belief; informs `SDF-A22`'s framing |
| `R-56` | three storage states + an 11-value stage enum; an absent chunk costs 4 bytes | `⊘` **superseded by `SDF-A1`** — with the live set as an *index*, an absent node costs **zero**, not four bytes. The stage enum survives inside `SDF-A2`'s S4→S5 split |
| `R-57` | OpenMW's `preload()` answers membership **without materialising** | `A→` `T7` (the sorted id list *is* the node-set `SDF-A23` returns) |
| `R-58` | interiors keyed by NAME, exteriors by GRID COORDINATE — two key spaces | `Q→` **`SDF-Q18`** (with `R-43`) |
| `R-59` | door endpoints must stay resident while their `Domain` is unloaded; one-sided links are a classic mod bug | `R→` `SDF-R3` (bidirectional, first-class, resident at a lower tier) |
| `R-60` | reset/expiry is lazy, per-node, on load — nothing ticks | `≡` sixth route to `M-1`; `A→` `SDF-A9`. Its data-loss warning informs `SDF-A20` |
| `R-61` | No Man's Sky: past the cap the base regenerates **under** player content | `Q→` `SDF-Q4` → `A→` `SDF-A21` |
| `R-62` | ⭐ Edgar: constraint-solving layout fails past ~30 rooms, so recursion is mandatory | `R→` `SDF-R6` |
| `R-63` | generation **annotates stable nodes** — never moves or deletes them | `✚` **had no home**; now §1 under `SDF-A2` |
| `R-64` | roguelikes store a dense per-tile array; rooms are generation scaffolding. Brogue = seed + input log | `≡` `SDF-A8` + `WDS-A1` |
| `R-65` | containment compresses the budget; **budget by object CLASS, not flat count** | `A→` `SDF-A18` (containment half). `✚` the **class half had no home**; now §11.5 under `SDF-A22` |
| `R-66` | Skyrim: ~40 interior cells per person, only because kit pieces snap to a grid | `R→` `SDF-R6` |

### What the table says about the fan-out itself

**Every one of the eight `✚` rows was cheap, uncontroversial, and already written down by an agent.** None
was rejected; none was hard. They were lost in the step between *reading 66 findings* and *writing eight
axioms*, and the only thing that recovered them was being made to account for each row separately.

> **The generalisable lesson, and it is about how this project works rather than about maps:** a fan-out's
> output is not the findings, it is the **adjudication**. A research report that is summarised rather than
> adjudicated has been *read*, not *used* — and the difference is invisible until someone builds the
> table. Slice 7 was marked `partial` honestly and then sat there for the whole arc, which is exactly how
> long the eleven stayed lost.

---

## 23 · ROUND 2 — the map gets a consumer (2026-08-22)

### 23.0 · The commitment, and it is one sentence

> **An actor must be able to come into existence somewhere.**

Round 1 designed the map with **no consumer**: its census was a hypothesis, its research a survey, and its
own header said so. On 2026-08-03 `d3bb441da` sealed the **actor hub as feature #1** and explicitly
de-scoped *"spawn · maps and places"*. **That sentence above is now the scope seal for this round** —
the same discipline that cut the actor round's contracts from 1107 lines to 364 the moment its scope was
sealed. Anything the spawn demand does not require is round 3.

### 23.1 · What was measured before anything was written

| # | measured fact | why it changes the plan |
|---|---|---|
| **M2-1** | the hub registers **18** seams (`S-1..S-18`) and **not one is spatial**; `actor-hub/src/actor.rs` has no location field of any kind | the seam is **new and ours**. The hub's own membership test explains why: *what travels when you move a being to another world is intrinsic* — and **where you are stays behind**, so position is a relation (`T7`), never an actor field |
| **M2-2** | `contracts/migrations/per_reality/0019_channels.up.sql` ships a per-reality, parent-linked, `depth ≤ 16`, lifecycle-bearing tree that is **acyclic BY CONSTRUCTION** — a `parent_depth` column `GENERATED ALWAYS AS (depth - 1) STORED` inside the FK target | **`SPG-A4` is shipped in SQL and mechanised better than the doc specifying it.** §5's *"`T1` does not exist"* is true of the name and wrong about the substance |
| **M2-3** | **every `INSERT INTO channels` in the repository is in a test** | the gap is **not the schema**. Nothing in production has ever created a place. The work is a *birth path*, not a tree |
| **M2-4** | two `ChannelId` types exist — `dp::ChannelId(i64)` (real, `pub(crate)` mint, ratcheted by `scripts/channel-id-adoption-gate.py`) and `tilemap-service::ChannelId(String)` (**self-declared** *"Phase 0a… Phase 2 will swap in the real DP-K1 `ChannelId`"*) | `SDF-Q18`'s `R-58` half is a **disclosed placeholder**, not a competing design. The map tier must not add a third |
| **M2-5** | `ChannelTree` mints **authored ids only**; `Megaplanet` = 16 384 cells, `Gigaplanet` fixture = 501 264 | `SDF-Q18`'s `R-43` half is a **real gap** — and the answer is that generated cells are not rows at all |
| **M2-6** | `ChannelTier`, retired by `SPG-R1` on 2026-07-30, is **still live** in `services/tilemap-service` | **known and disclosed**, not a new find: `amendment-rot-gate.py` check D says in its own docstring that a retired identifier in `crates/`/`services/` is **not covered**. It becomes load-bearing because the tilemap is the `Locale` surface a spawn lands on |

### 23.2 · Board

| # | slice | status | evidence |
|---|---|---|---|
| **2-1** | Measure the consumer demand before designing to it | **DONE** | doc 41 §14.1–14.3 · `M2-1..M2-6` above |
| **2-2** | Close `SDF-Q18` — it blocks every node creation | **DONE** | doc 41 §14.4 — `SDF-A31`. **Authored node = a shipped `channels` row; generated cell = an index, never a row.** No new allocator, no new type |
| **2-3** | `SDF-R2` (integer `Transform`) — **now blocking, not theoretical** | **DONE 2026-08-22** | **APPLIED to doc 36 `SPG-A17`** — `position: [i64;3]`, `rotation: [i32;4]`, `scale_exp: i8`; float survives only at the render boundary. **Applying it struck its own lead evidence** (`R-36`'s magnitude argument was already dissolved by `SPG-A17`'s coordinate roots); what carries it is determinism + round-trip — `R-37`, `R-13`, `WDS-A7`. Blast radius verified first: **docs only, two sites, zero `.rs`** |
| **2-4** | ~~The map hub contract~~ **REFRAMED 2026-08-22 — it is a RECONCILIATION, not a hub** | **scoped, doc 41 §17** | Writing a hub contract would have been the encroachment the actor round exists to prevent: `PF_001` (CANDIDATE-LOCK **2026-04-26**) already owns *semantic place identity* and says so — it *resolves the "spawn-empty-place gap"* and defers spawn as *"consumer responsibility"*. The real work is **`PF_001` re-stated in `MapKind` terms** = `SPG-R9` + `SPG-R13` applied to the doc that owns spawn, which today speaks only the **retired** `ChannelTier` vocabulary |
| **2-5** | The production birth path | **DESIGNED ELSEWHERE, unbuilt** | `M2-3` was right about the code and wrong about the design. `PF_001` §5 ships a **numbered bootstrap order** at `RealityManifest` ingestion (§9 the manifest extension, §14.1 the worked sequence), and **step 5 IS the spawn**: *"NPC + PC canonical seeds place actors at cells whose place rows are now valid"*. Step 3 is a **refusing** validator (`place.missing_decl`), the shape `SDF-A17` rule 4 asks for — designed four months earlier by another tier. A build slice behind the 2-4 reconciliation |
| **2-6** | ~~`T7` occupancy~~ | **✅ CLOSED — `SDF-A34`, and it CORRECTED this doc** | The relation is `EF_001`'s **`entity_binding`**, richer than `T7` (closed `InCell \| HeldBy \| InContainer \| Embedded`). **`T7`'s `local_pos` column was wrong**: a **2026-06-20** reconciliation already settled the granularity — `InCell` is coarse, durable, evented on transition, layer 1 of `ILR-A2`'s three-layer stack, while fine position is `RTM-A1` realtime-owned and **never per-tick in the log**. `local_pos` would have put a continuous per-tick value into the event log. **`T7` struck from doc 41 §5** |

### 23.2b · Question-clearing pass, 2026-08-22

**Five closed, one measured, two left — and three of the closures corrected something.**

| row | outcome |
|---|---|
| `SPG-Q6` | **✅ was ALREADY ANSWERED and the register never noticed.** This project measured it on 2026-08-02 (`M-1`, 92.4×); doc 36 went on telling readers the cost was *"never measured"* for three weeks while doc 41 §2 printed the number. **A question can rot exactly like an amendment.** |
| `SPG-Q5` | **✅ the three options were not three mechanisms.** Authored / player-steered / simulated collapse to one: a trajectory is a **declared function of time, evaluated, never integrated**. "Simulated" is the option `SPG-A9` already refused, and `SDF-R2` now makes it unrepresentable — an integrated trajectory has no bit-exact form in an integer `Transform`. |
| `SPG-Q4` | **✅ closed by saying it is not ours.** `SPG-A10` already makes *N* actors per controller representable; turn order is `COMB_002`'s. Recorded as a seam, removed as an open row. |
| `SDF-Q16` | **✅ and it FALSIFIED the lean this doc recorded.** `R-2`'s Paradox evidence does not transfer: Paradox regions are *authored groupings* with no geometry, ours are a **Voronoi partition of the same mesh** (`hierarchy.rs`). Adjacency is exact, contiguous by construction, and one pass over already-sorted `neighbors` away — bounded by a **shipped test** (`mesh.rs:450`, degree 4..=10) at 164 k tests for `Megaplanet`. |
| **`M-2`** | **✅ MEASURED against real Postgres 18 and the real migration**, in a scratch database created and dropped for it. **251 B per node**, versus the **96 B** that had been computed by counting struct fields. **Indexes are 51.5 % of it** — the half an estimate structurally cannot see. |
| `SDF-Q17` | **✅ `SDF-A30` holds — 92 % saved at 100 realities** — and the measurement showed **`SDF-A31` is what makes it hold**: had generated cells been rows, `Gigaplanet` would cost 126 MB per reality against a 14.9 MB baseline and `SDF-A30` would be false. Two axioms written the same morning turn out to be load-bearing for each other. |
| `SDF-Q12` | **still open, and now measurably worse.** At 251 B a `Pocket` inner world is **5.4×** the per-player allowance, not 2×. Re-verified: `PROG_001` states **no** realm distribution. The space tier now knows its own number exactly and still cannot close the row. |
| `SDF-Q15` | **still open**, and honestly so: it needs a space view to measure and `2-4`/`2-6` have not built one. |

> **What the pass says about registers.** Three of the five closures were **not new work** — the answer
> already existed in this repo (a measurement, a refusal, another feature's ownership) and the register
> had not been told. **An open question decays against its own project exactly like an unapplied
> amendment**, and nothing checks a question the way check E now checks a row.

### 23.2c · The pattern is now the finding

**Four times in this run the gap had an owner one folder away**, and the space track had simply never
opened the file: `SPG-Q6` (already measured, by us, three weeks earlier) · `SDF-Q16` (already generated,
by `hierarchy.rs`) · the eight retired-row citations (already retired, with successors named) · and now
all three remaining round-2 slices (`PF_001`, `PF_001`, `EF_001`).

> **This project's most common defect is not a wrong design. It is a register that was never told.**
> Every instance was cheap to fix and invisible until something forced a row-by-row account — the slice-7
> table, check E, a falsification condition written in advance. **The mechanism that finds them is
> obligation to enumerate, not care.**

### 23.3 · What round 2 is deliberately NOT doing

Layers · portals · topology ops · the live set · budgets · projections. **All of it is designed (§4, §10,
§11) and none of it is required for an actor to come into existence somewhere.** Round 1's own finding
about the actor round applies to this one: a hub exists so that feature N+1 does not touch feature #1 —
**not so that this round can specify feature N+1**.

The four measurement rows (`Q12` `Q15` `Q16` `Q17`, §8.1) are **untouched by this round** and stay open;
none of them blocks a spawn.
