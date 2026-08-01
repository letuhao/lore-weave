# 38 — The content pipeline: book → baseline → manifest

> **Status:** OVERVIEW, 2026-07-30. Prefix `CPL-*`.
> **Scope:** the tier between a LoreWeave **book** and a loadable **reality**. It does not redesign
> the ruleset ([16](16_ruleset_loader_and_registry.md), [35](35_quantity_architecture.md)), the
> baseline **store** ([37](37_world_data_storage.md)), or seeding ([18](18_reality_bootstrap.md)) —
> it is what feeds all three.
> **This is an overview.** Each element's generator gets its own document. Deciding the *shape* first
> is the point: eight generators built to eight different contracts is the failure this exists to
> prevent.

---

## 0 — Why this document exists

The load chain was traced end to end on 2026-07-30 and has a hole in the middle:

```
Phase 0  authoring (TOML layers)              ✅ built
Phase 1  reality creation → digest → binding  ✅ built
Phase 2  SEEDING                              ❌ does not exist
Phase 3  node boot → island Cold→Hot          ✅ built
Phase 4  actor spawn                          ⚠  hp + one hardcoded archetype, nothing else
Phase 5  the room projects the log            ✅ built
```

Phases 1 and 3 are joined by the ruleset digest, and everything it covers is replay-safe by
construction. Phase 2's input — the `RealityManifest` — appears in **eight design documents and zero
lines of code**. It has no type, no table, no producer, and no hash in the reality binding.

`grep -rl "RealityManifest" --include=*.rs --include=*.go --include=*.ts  →  one file, and it is a comment.`

So the engine can load a reality's **rules** and cannot load its **world**. `Actor::new` gives an
actor hp and a melee archetype because there is nowhere for anything else to come from.

> **`CPL-F1` — the missing tier is not "the manifest type". It is the pipeline that produces one.**
> Declaring a `RealityManifest` struct tomorrow would leave every field unpopulated. The work is the
> chain from a book — which is prose, glossary entries and a knowledge graph — to a validated,
> pinned, engine-loadable artifact.

---

## 1 — The pipeline

```
  ┌──────────┐   ┌───────────┐   ┌──────────────┐   ┌──────────┐   ┌──────────┐
  │   BOOK   │──▶│ EXTRACTION│──▶│  ENRICHMENT  │──▶│ BASELINE │──▶│ MANIFEST │──▶ reality
  │ glossary │   │           │   │  per element │   │ per elem │   │ assembly │
  │ wiki, KG │   │ what the  │   │ what it does │   │ validated│   │          │
  │  prose   │   │ book SAYS │   │  NOT say     │   │ + pinned │   │ + pinned │
  └──────────┘   └───────────┘   └──────────────┘   └──────────┘   └──────────┘
       │               │                │                │              │
       └───────────────┴────────────────┴────────────────┴──────────────┘
                        a HUMAN GATE at every arrow (CPL-A5)
```

Five stages, and the boundary between the middle two is the load-bearing one:

| Stage | Question it answers | Authority |
|---|---|---|
| **Extraction** | *what does the book actually state?* | the book — never invented |
| **Enrichment** | *what must be true for this to be playable that the book never said?* | LLM + procedural, gated |
| **Baseline** | *is it structurally valid, normalized, and engine-admissible?* | deterministic validators |
| **Manifest** | *does it compose into one loadable reality?* | cross-element consistency |
| **Reality** | *resolve, hash, bind* | already built (Phase 1) |

> **`CPL-A1` — extraction and enrichment are different pipelines and must never be one function.**
> Extraction is *lossless and attributable*: every output cites a book span. Enrichment *invents*, and
> everything it produces is a guess until a human accepts it. Merging them produces a manifest in
> which nobody can tell what the author wrote from what a model made up — and the first time a reader
> cannot tell, the book has stopped being the source of truth.
>
> This is the same split [`ruleset_boot`](../../../services/commit-service/src/ruleset_boot.rs) makes
> between **create** (resolves) and **load** (does not), for the same reason, after the same bug.

---

## 2 — What the research says, and what we take from it

Searched 2026-07-30. The field has converged on one finding that matters here:

> **LLM-based generation produces outputs that are structurally invalid or incompatible with real-time
> game engines.** The answer that works is not a better prompt — it is *schema governance,
> deterministic normalization, and engine-aligned admission checks*
> ([G-KMS](https://www.mdpi.com/2079-8954/14/2/175), MDPI 2026).

Three more that shape the design:

- **Dependency-driven ordering.** Generate in dependency order — world before quests — rather than
  all at once ([World-Gen to Quest-Line](https://arxiv.org/html/2604.25482v1)).
- **Specialized agents, structured hand-off.** One agent per concern, with a *structured format* as
  the link between steps, beats one agent doing everything
  ([PCG-with-LLMs survey](https://www.emergentmind.com/topics/procedural-content-generation-with-llms)).
- **Grammar-guided decoding + deterministic validation + a repair agent** rather than
  reject-and-retry ([SINE](https://www.mdpi.com/2076-3417/16/6/2932)).

**What we already have that the literature is reaching for.** The repo's ruleset tier is a
schema-governed pipeline: `deny_unknown_fields`, closed-set enums refused by name, `RLS-A7`
normalization before hashing, a `validate()` that is the *same* function the engine runs, and a
content-addressed store keyed by the digest. **The content pipeline should be that, applied to eight
more element types** — not a new discipline.

> **`CPL-A2` — the generator's output is admitted by the ENGINE'S OWN validator, not by a copy of
> it.** A second implementation of "is this legal" is a mirror nothing forces to agree, and it fails
> in the direction that ships broken content. Where the engine has no validator for an element yet,
> **that validator is the first thing built** — before the generator that would feed it.

---

## 3 — The per-element generator contract

The PO's constraint, stated plainly and adopted:

> *"we only focus for each element, not make a perfect generator that can make anything — nothing
> like that exists in the real world."*

> **`CPL-A3` — there is no universal generator. There is one MODULE per element, and one CONTRACT
> they all implement.** The contract is what makes eight modules a pipeline instead of eight
> programs.

Every element module provides exactly six things:

| # | Part | Why it is in the contract |
|---|---|---|
| 1 | **Schema** — the element's typed output, closed sets as enums | the thing the LLM is *governed* by, not asked to respect |
| 2 | **Extractor** — book → candidates, each citing a span | keeps `CPL-A1`'s split mechanical |
| 3 | **Enricher** — fills what the book left unsaid (LLM and/or procedural) | the only part that invents |
| 4 | **Normalizer** — deterministic; decimals → fixed point, names → machine keys, ordering canonical | `RLS-A7`: the hash is over the NORMALIZED form, or a reformat looks like a new world |
| 5 | **Admission** — the engine's own validator | `CPL-A2` |
| 6 | **Repair** — a bounded loop that feeds the validator's message back, then gives up LOUDLY | reject-and-retry hides the failure; silent drop is worse |

> **`CPL-A4` — an element that cannot state its schema is not ready for a generator.** The order is
> always schema → validator → extractor → enricher. Building the enricher first produces content
> whose only definition of correct is whatever it happened to emit.

---

## 4 — Three authorships, and which one owns what

The PO named the three: **LLM + procedural + human artifact**. They are not interchangeable, and
assigning the wrong one is how the pipeline produces slop.

| Authorship | Owns | Never owns |
|---|---|---|
| **Procedural** | the **generator spine** — every instance, at build time and at runtime: geometry, distances, adjacency, distributions, rolls, layout, combination | anything requiring meaning or taste |
| **LLM** | the **creative vocabulary** the procedural generator draws from — names, descriptions, relationships, motives, archetypes, affix wordlists, story beats | anything a formula settles · anything load-bearing that is not then validated · **the deterministic path, ever** (`CPL-A10`) |
| **Human** | the **gate** at every stage, and *adjustment* — the final say on any generated fact | the bulk. A human who must author every cell is a human who will not finish |

### 4.1 `CPL-A10` — the LLM is a CREATIVE SOURCE, not a generator

> **`CPL-A10`.** The procedural generator is the **spine**. The LLM is a **plug-in that fills its
> vocabulary**, never a replacement for it. Every element generator must be able to run with a
> hand-authored vocabulary and no model at all.

**This is the Diablo 2 shape, and naming it is the point.** D2 ships fixed acts, fixed quests, a
fixed item-base table and a fixed affix table — all *authored data*. Nothing about "of the Whale" or
"Cruel" is generated at runtime; what is generated is the **roll**: base + affixes, from a seed, in
microseconds, for free, forever. The tables are the expensive human work, paid once.

LoreWeave changes exactly one thing: **the tables are authored by an LLM from the book instead of by
a designer from imagination** — then gated by a human, then pinned. The roll stays procedural.

Two consequences the PO named, both of which this axiom is derived from:

- **Cost.** LLM spend becomes a *build-time budget* — bounded, per reality, paid once. Put a model
  in the drop path and the spend is unbounded and paid forever, per item, per player, per session.
- **Randomness.** A model is random in the wrong way: unrepeatable. A seeded PRNG is random in the
  right way: unrepeatable-looking and exactly reproducible. Loot needs the second kind.

> **`CPL-A11` — the rule is CAPTURE, not timing. An LLM may never run *inside* resolution; it may
> absolutely run *at runtime*, provided its output is committed to the ledger before anything depends
> on it.**
>
> A model inside `apply` makes replay impossible — the same bytes would produce different outcomes.
> A model that **proposes**, is validated, and whose result is **committed as an event** is replayed
> by reading that event, and never contacts a provider again.
>
> `AGT-A6` already works this way for combat: *"the driver returns a PROPOSAL; nothing here
> executes"*, with `AGT-A2`'s vocabulary fallback on reject or timeout. The log records the
> *proposal*, not the call.

> ### ⚠ Correction, 2026-07-30 — the first draft of `CPL-A10` was too strong, and it would have
> ### killed the product
>
> The draft said the LLM fills a **build-time vocabulary** and the runtime is procedural-only. The PO
> refused it with one example:
>
> > *"a new artifact falls from the sky to the mortal realm — new item, new name. It can be made by
> > an LLM generator at runtime and stored to the ES ledger. This is a major event that needs an
> > LLM."*
>
> That is correct and the draft could not express it. **A world that can only roll from pre-authored
> tables is Diablo 2** — and D2 is the right model for *loot*, not for *a world that is alive*. If
> nothing genuinely new can ever enter a reality, the LLM tier is decoration.
>
> The error was conflating *"an LLM inside the deterministic step"* (forbidden — replay dies) with
> *"an LLM at runtime"* (necessary — it is the product). `CPL-A10` now governs **which tier** a piece
> of content belongs to, and `CPL-A14` names the three.

---

## 4A — Build time and runtime are the SAME generators, different inputs

The PO's second correction, and it changes the shape of the pipeline:

> *"we don't run only one — this can run when game loading for event/item/quest… so it is prebuild
> manifest and runtime build manifest."*

```
BUILD TIME  ── once per reality · expensive · human-gated ──────────────────────
   book ──▶ extraction ──▶ LLM creative pass ──▶ VOCABULARY + TABLES
                                                      │
                          procedural generator ◀───────┘
                                  │
                                  ▼
                        ★ PINNED MANIFEST ★   content-addressed, digest, immutable
                          (bases · affix pools · archetypes · quest templates ·
                           story beats · progression kinds · rules)

RUNTIME  ── every load, every drop, every quest roll · cheap · deterministic ───
                        the SAME procedural generators
                                  │
              f(pinned manifest, seed, tick) ──▶ instances
                                  │
                    ┌─────────────┴─────────────┐
              small │                           │ large
                    ▼                           ▼
            an EVENT in the log      a pinned content blob
                                     + ONE event referencing it  (WDS-A3)
```

> **`CPL-A12` — there is ONE manifest, and runtime generation does not produce another.** Runtime
> output is `f(pinned manifest, seed)` and its result is an **event**, never a rules change.
>
> The distinction is not pedantry, it is what keeps replay alive. A second, runtime-written manifest
> would make the rules mutable and the digest meaningless — a reality would be unable to say what
> rules produced its own log. With the manifest pinned and the **seed in the event**, replay
> reproduces every roll exactly, on any node, a year later, with no generator re-run.
>
> Again this is D2: the map seed is stored per game, and `seed + version` reproduces the same map
> forever. `WDS-A6` already learned the `version` half the hard way — `content_hash` was re-baselined
> once on an intentional algorithm change, so a *generator version* is part of the pin.

**When runtime output is large** — a generated dungeon, a rolled region — `WDS-A3` already answers
it: pin the bytes, emit **one** `…Pinned` event, do not emit 33 000 per-cell events. Genesis is
`O(1)`. The same store, the same discipline, at a different moment.

### 4A.0 `CPL-A14` — three content tiers, and picking one is a per-element decision

> **`CPL-A14`.** Every piece of content belongs to exactly one of three tiers. Choosing wrongly is
> expensive in one direction and lifeless in the other.

| Tier | What it is | Author | Cost | Replay reads | Example |
|---|---|---|---|---|---|
| **Rolled** | high volume, combined from pinned tables | procedural, seeded | ~0 | the seed | a magic sword drop · a minor mob · a wandering merchant |
| **Authored** | **rare, major, genuinely new** — nothing in any table implies it | **LLM at runtime**, validated, committed | real, **budgeted** | the committed event | *an artifact falls from the sky* · a sect is founded · a legendary NPC's true name is revealed |
| **Pinned bulk** | large generated structure | procedural | one blob | one `…Pinned` event (`WDS-A3`) | a dungeon layout · a rolled region |

**The Authored tier is the product.** It is what a reality can do that a table cannot: produce a
thing no one wrote down, name it, and make it *true*. Removing it — which the first draft did by
accident — leaves an LLM that only ever wrote the loot tables.

**The Rolled tier is the cost control.** It is what stops the Authored tier from being asked to name
every dagger. `CPL-A10`'s D2 argument applies **within the Rolled tier**, not against the Authored
one.

### 4A.0.1 `CPL-A15` — runtime-authored content becomes CANON, and its gate is COMPENSATING

A build-time gate is **prior**: a human approves the tables before they are pinned. A runtime gate
cannot be — **a live world cannot block on a human**, and an artifact that falls from the sky must
land now, not after review.

> **`CPL-A15` — runtime-authored content is committed first and vetoed after.** It enters as canon;
> the human gate is a *compensating* action, not an admission check.

The machinery already exists and was built for exactly this shape:

| Event | Role in the Authored tier |
|---|---|
| `canon.entry.created` (`canon_layer: L2_seeded`, `lock_level`) | the new artifact becomes **true in this world** |
| `canon.entry.promoted` | it graduates — a one-off becomes part of the world's settled lore |
| `canon.entry.decanonized` | it is retracted |
| `admin.canon.override.{requested,consented,vetoed,compensating}` | the **posterior human gate**, with consent and veto and a compensating path |

So the Authored tier's flow is:

```
LLM proposes ─▶ schema-governed validation (CPL-A2) ─▶ COMMITTED as canon
                                                            │
                                       replay reads the event, never the model
                                                            │
                          human reviews LATER ─▶ promote · leave · veto (compensating)
```

Note what this buys beyond correctness: the artifact's name and stats live in the **ledger**, so they
are auditable, attributable, diff-able and revocable — the same properties the build-time gate gives
the tables, obtained without stopping the world.

### 4A.0.2 `CPL-A16` — the EFFECT generator is a separate element, and it is gated the other way

The PO's third correction, and it splits an element I had treated as one:

> *"item effect or skill effect can be generated by LLM too — so LLM can generate prefix/affix. But
> it is an **effect generator**, it is **not part of the item generator**. We have fixed effects
> handcrafted by the platform, because an effect generator **can break game balance** — so it is not
> frequent, but it exists."*

> **`CPL-A16` — combining over the effect vocabulary and EXTENDING the effect vocabulary are two
> different generators, with two different frequencies and two different gate polarities.**

| | **Item / skill generator** | **Effect generator** |
|---|---|---|
| What it does | picks a base, rolls affixes **from the pool** | adds a new affix/effect **to the pool** |
| Frequency | constantly, every drop | patch-scale — *rare, but it exists* |
| Balance risk | **bounded** — the pool is finite, so the best possible roll is computable | **unbounded** — a new effect interacts with every existing one |
| Gate | none needed at runtime; the pool was gated when it was pinned | **PRIOR**, unlike `CPL-A15` |
| Tier (`CPL-A14`) | Rolled | Authored — but *not* the same gate as an artifact |

**Why the gate polarity flips, and this is the part worth keeping.** `CPL-A15` lets a falling
artifact be committed first and vetoed after, because retracting an *object* removes an object. An
**effect** cannot be retracted that way: by the time it is known to be broken it has been rolled onto
items, learned as skills, and **its outcomes are already resolved in the ledger**. Decanonizing it
does not delete a thing — it *invalidates history*.

So the two Authored-tier sub-cases are:

```
artifact  →  commit  →  play  →  human may VETO after      (CPL-A15, compensating)
effect    →  human APPROVES first  →  enters the pool  →  rolled forever  (CPL-A16, prior)
```

**The handcrafted set is the baseline, not a fallback.** The platform ships a complete, tuned effect
vocabulary; a reality with **zero** generated effects is a complete game. Generation is *additive to
a working baseline* and never fills a gap the platform declined to design — which is what stops
*"the LLM will handle it"* from becoming a design decision.

### 4A.0.3 `CPL-A17` — a generated effect is a COMPOSITION, never new logic

> **`CPL-A17`.** An effect generator arranges **engine primitives**. It may never emit executable
> logic, and it may never invent a primitive.

The vocabulary already exists and is closed: `ABL_001`'s ordered op list (`Damage { power:
PowerTerm }`, `StatusApply{…}`, …) with magnitudes as
[`ModifierOp`](../../../crates/game-rules/src/stats/modifier.rs) — `Flat(i32) | Percent(i32)`. The
LLM chooses *which ops, in what order, with what magnitudes*. It does not write code.

Three things fall out, and the second is the load-bearing one:

1. It is `QTY-A1` — *"arithmetic is code, arrangement is data"* — applied one level up, to effects.
2. **It is what makes `CPL-A2` satisfiable for this element at all.** You can validate an
   *arrangement* against a schema; you cannot validate arbitrary logic. If a generated effect were
   code, there would be no engine validator to admit it and the whole schema-governance discipline
   would collapse precisely where balance matters most.
3. A generated affix inherits the engine's existing structural balance properties for free —
   **`DF7-A5` already makes percent modifiers SUM into one factor rather than chain**, which kills
   exponential buff stacking. A generated `Percent` affix cannot reintroduce it, because the
   summation is in the law, not in the affix.

### 4A.1 What this means for the element contract

`CPL-A3`'s six parts are unchanged, but their **order of authority** is now explicit:

1. the **procedural generator** is mandatory and is the spine;
2. the **creative vocabulary** it draws from is an input — LLM-authored, human-gated, or
   hand-written, and the generator cannot tell which;
3. therefore **every element generator must be runnable at build time and at runtime** — the Rolled
   tier differing only in which seed it is handed and where its output goes, the Authored tier
   differing in that it calls a model and commits the result as canon.

A **Rolled**-tier generator that cannot run at runtime has hidden an LLM call inside itself, which is
what `CPL-A11` forbids. An **Authored**-tier generator that cannot run at runtime has simply not been
built — and `CPL-A14` is the decision record for which one an element is.

> **`CPL-A5` — a human gate at every stage boundary, not only at the end.** A single review at the
> end asks a person to accept or reject a whole world, which in practice means accepting it. Gates
> are per-stage and per-element so that what is being approved is small enough to actually read.
>
> Doc 37 already lives by this on the geometry side: `WDS-D3` records a **PO decision** on payload
> stripping with its measurement and a wake-up trigger. That is the shape — a decision, recorded,
> with what would reopen it.

> **`CPL-A6` — every generated fact carries provenance, and provenance is part of the pinned bytes.**
> `(source_span | procedural_seed | model_ref, generator_version, approved_by, approved_at)`. Doc 37
> already requires `(seed, CreativeSeed, generator_version)` for the world baseline (`WDS-A5`,
> `WDS-A6`) — this generalizes it. Without it, "why is this NPC hostile?" has no answer a year later,
> and a regenerated baseline cannot be compared against the one that shipped.

---

## 5 — Determinism, and why the artifact is the SSOT

An LLM is not deterministic. A float-noise generator is not *portably* deterministic — doc 37
measured that and made it an axiom (`WDS-A7`, `WDS-D2`).

> **`CPL-A7` — the pipeline runs ONCE, its output is content-addressed and pinned, and nothing
> re-runs it at load time.** The reality loads *bytes*, verified against their hash. Regeneration is
> the **audit** path — proving a year-old world was what it claimed — and an audit mismatch is a
> *finding*, never a repair.

This is `RLS-A3` early binding and `WDS-A7` stated once for the whole tier. It is also what closes
the hazard that stopped the Q2 build:

> **`CPL-A8` — the manifest is pinned into the reality binding, exactly as the ruleset is.** A
> reality is identified by **both** hashes. Today `reality_ruleset_binding` carries one; an unpinned
> manifest means a reality's progression systems, class defaults and world content can all change
> with **no digest moving and nothing going red** — replay diverges silently.
>
> That is precisely the defect `LAW_VERSION` was added to close (`QTY-D13`): two engine builds with
> different arithmetic hashed identically, so a behavioural change was undetectable and could trigger
> nothing. The same hole, one tier up.

---

## 6 — The element roster

Per `CPL-A3`, each gets its own module and its own document. Listed with the **one question** each
must answer first, because that question is the module's real difficulty:

| Element | The question its schema must answer | Depends on |
|---|---|---|
| **World / geography** | *(answered)* — [37](37_world_data_storage.md) `WorldBaselineStore` | — |
| **Place** | what makes a book location a `space_node` with a `MapKind`? ([36](36_map_architecture.md)) | world |
| **Character / actor** | which glossary entities become actors, and what are their starting values? | place |
| **Item** | what makes a named object in prose an item with stats? | — |
| **Progression system** | how does a book's cultivation ladder become `ProgressionKindDecl`s bound to L2 ordinals? (`QTY-D6`) | rules, **place, item** ⚠ |
| **Rule / ruleset layer** | which genre conventions become a `Preset` layer vs this reality's overrides? | — |
| **Story event** | which book events are *history* (pre-t=0 baseline) vs *hooks* (live content)? | place, character |

> **`CPL-A9` — dependency order is a property of the pipeline, not a scheduling convenience.** A
> character's starting place must exist before the character; a progression kind's terms must
> reference quantity ordinals that exist before the kind. The literature's finding
> ([World-Gen to Quest-Line](https://arxiv.org/html/2604.25482v1)) matches what `QTY-D6` already
> requires here.

**Two of these are already partly answered and must not be re-litigated:** the world baseline
(doc 37) and where a progression kind's terms bind (`QTY-D6` — an L2 declared quantity ordinal, not a
free string, which is the seam into `Q1`/`Q2`'s ordinal space).

---

## 7 — What this changes elsewhere

⚠ **PROPOSED, not applied** — same discipline as docs 32, 36 and 37.

| Target | Change | Row |
|---|---|---|
| [17](17_game_data_architecture.md) `GDA-D3` | *"the manifest is the only seeding input"* stands, and gains a producer: this pipeline | `CPL-R1` |
| [18](18_reality_bootstrap.md) | seeding consumes **pinned baselines**, not a manifest assembled at seed time | `CPL-R2` |
| `reality_ruleset_binding` | carries a **manifest hash** beside the ruleset digest (`CPL-A8`) | `CPL-R3` |
| `PROG_001` §11 | `progression_kinds` are pipeline output; `kind_id` binds to an L2 ordinal per `QTY-D6` | `CPL-R4` |
| [37](37_world_data_storage.md) `WDS-Q1` | *"who writes the baseline and when"* — answered by this pipeline's stage 4 | `CPL-R5` |

---

## 8 — Open

| # | Question |
|---|---|
| **CPL-Q1** | **Is `RealityManifest` one artifact or two?** Rules-shaped content (progression kinds, class defaults) is replay-critical and belongs with the ruleset's discipline; world content (places, layout, canonical actors) is bulk and belongs with `WDS-A4`'s store. Doc 17 `GDA-D3` collapsed two rival *bootstrappers*; it did not rule on whether the manifest itself is one thing. |
| **CPL-Q2** | **What is the human gate's UI, and who is the human?** The author of the book, a game designer, or an operator? The answer changes what a gate can reasonably ask a person to read. |
| **CPL-Q3** | **What happens when the book changes after a reality exists?** `RLS-A3` says a later preset edit never touches a live reality. Is a book edit the same — or does it want the epoch-switch path Q0b just built? |
| **CPL-Q4** | **What is the repair loop's budget, and what does giving up look like?** An unbounded repair loop is an unbounded LLM spend; a silent give-up is the `PROG_001` silent-drop defect (`QTY-Q5`) again. |
| **CPL-Q6** | **Where does a runtime roll's SEED come from, and who guarantees it is in the log before the roll is read?** `sim-core` has `DetRng` per island, but a drop rolled from the island seed alone is not reproducible across a rebuild unless the tick and the input id enter the draw. This is the one question `CPL-A12` depends on, and it is a `sim-core` question, not a content one. |
| **CPL-Q10** | **What POWER BUDGET must a generated effect fit, and who computes it?** `CPL-A16` says the item generator's risk is bounded *because the pool is finite and the best roll is computable* — which is only true if someone computes it. A budget function over `ABL_001`'s ops (a `Damage` op costs X, a `StatusApply` costs Y, scaled by magnitude and duration) is the obvious shape, and it is also the thing that lets a human gate say *"this is 1.4x the band"* instead of *"this feels strong"*. Without it, `CPL-A16`'s prior gate is a taste review. |
| **CPL-Q11** | **Does an effect enter the pinned manifest or the ledger?** It is Authored (`CPL-A14`) but prior-gated (`CPL-A16`), which puts it in neither box cleanly: an approved effect behaves like a *table extension*, i.e. a manifest change, i.e. an **epoch switch** — the path `Q0b B3` just built. If that is right, effect generation is the first real consumer of the epoch machinery, and the answer to `CPL-Q3` (what happens when the book changes) is probably the same answer. |
| **CPL-Q8** | **What is the Authored tier's BUDGET, and who enforces it?** `CPL-A14` calls it *"rare, major, budgeted"* and names no number. Unbounded, a busy reality is an unbounded model bill; too tight, the world stops surprising anyone. Is the budget per reality, per epoch, per player-hour — and is exhausting it a refusal or a downgrade to the Rolled tier? |
| **CPL-Q9** | **What TRIGGERS an Authored-tier generation?** The falling-artifact example is a world event, but nothing yet says what decides that this moment deserves a new artifact rather than a rolled one. A world-sim trigger ([33](33_trigger_group_order.md)), an admin action, a player achievement, or an LLM already in the loop proposing it — each has a different failure mode. |
| **CPL-Q7** | **What is the vocabulary's granularity per element?** D2's affix table is one flat pool with level ranges; a story-beat pool may need to be per-region or per-faction. Too coarse and every world sounds identical; too fine and the LLM pass gets expensive again — which is the cost `CPL-A10` exists to bound. |
| **CPL-Q5** | **Does an element module run per-book or per-reality?** Two realities from one book: shared extraction, separate enrichment — or shared both? Content addressing makes sharing free (`WDS-Q2` asks the same thing for baselines). |

> Deliberately **not** open: whether there is a universal generator (`CPL-A3` — there is not),
> whether generated content is replayed as events (`CPL-A7`/`WDS-A1` — it is pinned content),
> whether the engine's validator is reused or copied (`CPL-A2` — reused), whether an LLM may run
> inside a step (`CPL-A11` — never, and `AGT-A6` already forbids it for combat), and whether runtime
> generation writes a second manifest (`CPL-A12` — it does not; it emits events against a pinned
> one).
