# 40.1 — The progression planner: what a progression system is, and what plans one

> **Status:** DESIGN · **Date:** 2026-07-31 · **Prefix:** `PPL-`
> **Supersedes the front half of** [`39_progression_generation_pipeline.md`](../39_progression_generation_pipeline.md) (S0–S3).
> **Consumes** [`35_quantity_architecture.md`](../35_quantity_architecture.md) (L2/L3) ·
> [`38_content_pipeline_architecture.md`](../38_content_pipeline_architecture.md) (three authorships) ·
> [`features/00_progression/PROG_001_progression_foundation.md`](../features/00_progression/PROG_001_progression_foundation.md) (the runtime substrate).
> **Loop shape borrowed from** [`PlanForge`](../../../specs/2026-07-01-plan-forge/01_PLANFORGE_ARCHITECTURE.md)
> — **but not its autonomy.** See `PPL-A9`: PlanForge tries to *produce* a spec and check in at gates;
> this planner is an **assistant that keeps asking**, and the difference is a mechanism, not a tone.

---

> ### ⚠ Corrected by [`40.3 — the generator boundary`](03_generator_boundary.md), 2026-07-31
> This document was written broad enough to reach into other element modules' scope, which
> [`38`](../38_content_pipeline_architecture.md) `CPL-A3` forbids. **`PPL-A1`'s ownership of Gates, `PPL-A2`'s single closure check, `PPL-A7`'s `Demand{shape}` and `PPL-A10`'s output pair are all superseded there.** See
> [`40.3` §9](03_generator_boundary.md) for the full correction list. Kept in place rather than
> laundered — the drift is the finding.

---

## 0 — Why this document exists

The PO stopped the POC-1 build with this:

> *"This enrichment cannot be done the way it is being done. A game has N attributes; enrichment is a
> **loop**, not a one-shot prompt. The LLM only helps **enrich** — how many attributes there are and
> how they are controlled is a **bounded** proposal surface. A human has to author a pile of
> wiki/glossary/KG first. This is the **data-loading** step and it needs a spec and an architecture.
> A progression system is a system that deserves a serious architecture before anyone digs into LLM
> agents and workflows. The corpus is **just one idea**."*

This document is the answer, and it does not start from agreement. It starts from three measurements
taken **while doc 39's pipeline was running against a real model**, because the PO's objection turned
out to be provable rather than a matter of taste.

### 0.1 — The three measurements

**M1 — three live end-to-end runs, one local 26B model, the sealed wuxia fixture corpus.**

| run | answered | refused | fold |
|---|---|---|---|
| 1 | 4 / 11 | 7 | ⛔ refused |
| 2 | 4 / 11 | 7 | ⛔ refused |
| 3 | 3 / 11 | 8 | ⛔ refused |
| 4 (after 8 fixes + the anchor redesign) | 5 / 11 | 6 | ⛔ refused |

Every run died at the same place:

```
⛔ FOLD REFUSED — no approved answer for 'kind.quantity'. Without it the fold does not
   know which kinds exist, and inventing an empty list would produce a structurally
   valid element containing nothing.
```

Eight defect fixes and one redesign moved the count 4 → 4 → 3 → 5. **The pipeline never produced a
manifest, so the provenance census built to grade it never had anything to grade.**

**M2 — the question that killed every run is not an extraction question.** `kind.quantity` asks
*"which distinct progression systems does this world have?"* A novel does not contain that fact. A
novel contains a story in which cultivation happens; how many progression **kinds** a *game* built
from it should have is a design decision with a number as its answer, and the number is chosen by
whoever is building the game. A human answers it in ten seconds. No prompt makes a book answer it,
because the book is not a game.

**M3 — the brief covers one quarter of a progression system, and the other three quarters have no
producer anywhere in the pipeline.** All 11 questions in
`app/gamegen/briefs/progression_system.json`:

```
cardinality · kind_name · kind_type · curve · cap · start_tier
tier_count · tier_order · tier_name · tier_shape · breakthrough
```

Every one describes **the ladder**. Now grep the whole generation package for the rest of
`PROG_001`:

```
$ grep -ric "training|inflow|strike_formula|derives_from" app/gamegen/*.py
fold.py:3   generate.py:1   (everything else: 0)
$ grep -in ...   →  all four hits are PROSE INSIDE COMMENTS.
```

`PROG_001` §6 `TrainingRuleDecl` — how a value ever goes up — **is not asked and is not generated.**
§9 `strike_formula` — how a value ever matters — **is not asked and is not generated.**
§4.5 `derives_from` — how kinds relate to each other — **is not asked and is not generated.**

Doc 39's own review found *"23 schema positions had no producer at all"* and treated it as a coverage
bug to be closed by adding questions. **It is not a coverage bug. It is the wrong instrument.** A
question set derived from a schema will ask about every field of the schema and still produce
something unplayable, because playability is not a property of fields — §2 below.

### 0.2 — What this document changes

| | doc 39 (v2) | this document |
|---|---|---|
| the object being built | an **extraction** from a corpus | a **design artifact** with a designer as owner |
| the corpus | the pipeline's spine | **one evidence source among six** (`PPL-A5`) |
| the human | a gate that approves rows | the **author of the skeleton**, first, before any model runs |
| the LLM | the producer of the structure | an **enrichment proposer** inside a bounded loop |
| the shape | S0→S6, one pass, terminates | a **loop** that converges against an open-decision register |
| "done" | every question answered | **closure** — every variable has an inflow and a gate (`PPL-A2`) |

Doc 39's **back half survives intact** — S4 policy, S5 candidate, S6 pin, and `S-1`'s validator are
correct and shipped, and this document consumes them unchanged. What is demoted is S0–S3: corpus,
brief, interrogation, fold. They become **one input path into the planner**, not the planner.

---

## 1 — `PPL-A1` — what a progression system IS

> **`PPL-A1`.** A progression system is a **closed feedback loop between what an actor does and what
> an actor can do**. It has exactly four parts, and a description missing any one of them is not a
> progression system — it is a table of numbers.

| part | what it is | `PROG_001` / doc 35 home |
|---|---|---|
| **Variables** | the state an actor carries and that changes over time | `ProgressionKindDecl`, `ProgressionType`, `CurveDecl`, `TierDecl`, `CapRule` · L2 declared quantity |
| **Inflows** | what causes a variable to rise (and, later, fall) | `TrainingRuleDecl`, `TrainingCondition`, the action cascade, the day-boundary tick · atrophy (V1+) |
| **Gates** | what a variable's value *permits* — what the world refuses you without it | `BreakthroughCondition`, `strike_formula`, skill checks at `PL_005`, place/item access |
| **Couplings** | how variables feed each other and the rest of the rules | `derives_from`, `CapRule::TierBased`, L3 contributions and their aggregation order (`QTY-A9`) |

The industry literature converges on the same four under different names — attributes and derived
stats (variables), XP/practice/quest rewards (inflows), level and prerequisite gating on a DAG
(gates), and stat→derived-stat formulas (couplings) — and the economy-design literature is explicit
that the object being balanced is the **flow**, not the table:
prototype the *cumulative flow of resources through rewards and expenditures* before writing code.

**Why the four-part statement matters here and not merely as taxonomy:** doc 39's brief asks 11
questions and all 11 are Variables. The pipeline is not 45% complete. It is **100% complete on one
of four parts and 0% on three**, and no amount of running it harder changes that ratio.

---

## 2 — `PPL-A2` — the closure criterion: "playable" is a graph property, not a vibe

The PO's acceptance bar was *"it passes only if it is detailed enough AND playable"* — detailed enough
**and playable**. "Playable" has to be mechanically checkable or it is a rubber stamp, so:

> **`PPL-A2` — the closure criterion.** Build the directed graph whose nodes are Variables, Inflows
> and Gates and whose edges are `inflow ──feeds──▶ variable` and `variable ──permits──▶ gate`. A
> progression system is **closed** iff every Variable has **≥1 inbound inflow edge** and **≥1
> outbound gate edge**. A system that is not closed is not playable, and the violation names itself.

The two failure modes, and what each one *is* when you play it:

| violation | the graph | what the player experiences |
|---|---|---|
| **Dangling variable** — inflow, no gate | `train ──▶ inner_power` and nothing reads `inner_power` | a number that goes up and does nothing. Idle-game slop. |
| **Unreachable gate** — gate, no inflow | `foundation_establishment ──permits──▶ cold_pool` but nothing raises the tier | a wall. Content the player can see and can never reach. |

Two corollaries that are checkable at the same time:

- **`PPL-A2.1` — no orphan couplings.** A `derives_from` or L3 contribution whose source variable is
  itself dangling propagates the defect; closure is computed on the transitive graph, not per node.
- **`PPL-A2.2` — the gate must be refusable.** A gate whose condition is satisfiable by every actor
  at t=0 gates nothing. This is [`non-vacuity`](../../../standards/non-vacuity.md) `NV-1` applied to
  game content: *a gate that cannot refuse is not a gate.* The same discipline that governs our
  tests governs the rules we generate — and for the same reason, because a gate that never refuses
  reports progression it does not deliver.

**Run POC-1's actual output through this.** Even in the counterfactual where the fold had succeeded:
the ladder would exist (Variables ✓), nothing would raise a tier (Inflows ✗ — `TrainingRuleDecl` has
no producer), nothing would read a tier (Gates ✗ — `strike_formula` has no producer). **Zero of the
generated variables would be closed.** The run that failed and the run that "succeeded" ship the same
verdict; the failure merely arrived earlier and cheaper.

> **This is the honest POC-1 verdict the PO asked for: FAIL, and not on the margin.** Not "the model
> answered 5 of 11". The denominator was wrong. 11 questions could not have produced a playable
> system at 11/11.

`PPL-A2` is what the census instrument was missing. Provenance (*who chose this?*) and closure (*does
this system function?*) are orthogonal, and a 100%-human-authored system can be perfectly grounded
and completely unplayable.

---

## 3 — `PPL-A3` — the book is a WITNESS, not a source

> **`PPL-A3`.** A novel is **evidence that constrains** a progression design. It is never the design.
> Extraction can recover what the book *witnessed*; it is structurally incapable of producing what the
> book had no reason to state, and that is most of a game.

Doc 39 §1 already proved this and did not follow the proof. Its own five-owner table has **two** rows
owned by the book and **three** owned by someone else. A pipeline whose spine is the corpus is a
pipeline built around the minority owner.

Novels are silent on almost everything a ruleset needs, and the silence is not an oversight — it is
what novels are:

- **rates** — the protagonist spent three years in seclusion. Three years of *what per day*? The book has no
  reason to say, and a reader has no reason to want it.
- **the roster** — how many *kinds*. A book has one cultivation ladder because that is the story;
  a game may want three or one, and that is a product decision.
- **gates outside the ladder** — what *Foundation Establishment* permits beyond the plot beats it
  enabled once.
- **couplings** — whether *comprehension* raises *inner-power* gain, and by how much.
- **the closed set** — what an ordinary person *cannot* do. Fiction states the exceptional; a rules
  system is mostly a statement about the unexceptional.

**So the corpus keeps its place and loses its primacy.** Where the book *does* speak, its testimony is
the strongest evidence available and doc 39's citation machinery is exactly right: span-verified,
sealed-corpus, fabrication-impossible-by-construction. Across four live runs **zero fabricated
citations reached storage** — every one refused by name with its reason. That machinery is kept
verbatim. It just stops being the spine.

---

## 4 — `PPL-A4` — the denominator is a human declaration, and it comes FIRST

> **`PPL-A4`.** Coverage is a ratio, and a ratio needs a denominator. The denominator of a progression
> plan — **which kinds exist, of what type, in what roles** — is a design decision owned by the human
> and declared **before any model runs**. A pipeline that asks a model for its own denominator cannot
> know whether it is finished.

This is the PO's *"how many attributes there are and how they are controlled is a bounded proposal
surface"*, stated as a mechanism instead of a preference — and it is the direct root cause of M1. `kind.quantity` was
question #1 of 11 and it is the denominator of the other 10. Asking a model for it makes every
downstream coverage number self-referential: the pipeline reports 100% coverage of a roster the
pipeline invented.

**The skeleton the human declares** — small, closed, and the whole of it:

```
ProgressionSkeleton
  kinds: [ { id, type: Attribute|Skill|Stage|ResourceBound,
             body_or_soul, role, representation } ]      # PROG_001 §4, doc 35 §4.3
  genre_intent: free prose, one paragraph                # steers proposal, binds nothing
```

Ten to thirty decisions. Ten minutes of a designer's time. Everything downstream — names, ladders,
rates, conditions, formulas — is then **enrichment against a fixed denominator**, which is the job an
LLM is genuinely good at and the job the PO described.

**`PPL-A4.1` — the skeleton is revisable, and revising it is a first-class event.** Discovering
mid-loop that the book implies a fourth kind is normal and good. It is a **skeleton amendment**: an
explicit human act that widens the denominator, invalidates the coverage number, and re-opens the
register. What is forbidden is the denominator moving *silently* underneath a coverage claim.

---

## 5 — `PPL-A5` — six provenances, and the two that doc 39 was missing

Doc 39 has three answer shapes: `says[]` (cited), `proposed` (model-invented), `not_stated`. Everything
that fell through landed in the numeric policy file, which is how *"an all-`not_stated` run passed all
eight trust properties and shipped a manifest authored 100% by the policy file"*.

> **`PPL-A5`.** Every decision in a progression plan carries exactly one of **six** provenances. Each
> has a different trust level, a different audit obligation, and a different cost.

| # | provenance | who decided | audit obligation | cost |
|---|---|---|---|---|
| 1 | **DECLARED** | human, directly | the human's signature | human minutes |
| 2 | **CANON** | the authored SSOT — glossary entity / wiki page / KG edge | the record id + its version | human minutes, **paid once, reused everywhere** |
| 3 | **CITED** | the book | a verified span in a sealed corpus (`PGN-A14`) | model tokens |
| 4 | **PROPOSED** | the model, from nothing | marked, span-forbidden, **human-approved** (`PGN-A3`) | model tokens + human review |
| 5 | **DERIVED** | procedural expansion of an already-decided pattern | the rule id + its input decision | **~0** |
| 6 | **POLICY** | the numeric policy artifact (`PGN-A15`) | the policy hash, System-tier | ~0 |

**Provenance 2 (CANON) is the PO's *"a human authors a pile of wiki/glossary/KG"* — the data-loading
step.**
LoreWeave already has this substrate and doc 39 does not read it: `glossary-service` is the authored
SSOT and hosts the wiki (`wiki_*`); `knowledge-service` is the derived semantic layer anchored by
`glossary_entity_id`. A designer who writes *"inner_power — an Attribute; raised by seated meditation
in a quiet place; gates lightness_skill"* into the wiki has authored a Variable, an Inflow and a Gate in one sentence, permanently,
in a form the planner can read without a model and without a token. **This is the highest-leverage
missing input in the whole architecture** — a source that is more trustworthy than a citation, cheaper
than inference, and reusable across every reality built from the same lore.

**Provenance 5 (DERIVED) is the procedural half of *"raise the generative capability of BOTH the LLM
tier and the procedural tier"*.** M1 measured the LLM tier hitting a hard ceiling on transcription; the procedural tier
was never asked to help. Concretely: one CITED answer of the form *"sub-levels are named
"Layer One" … "Layer Nine" by convention"* — a **pattern, stated once** — expands to nine tier names for free, deterministically,
auditable back to a single span. Doc 39's `PGN-A0` already names naming-by-pattern as an owner. It is
not yet a provenance, so the expansion has no provenance of its own and cannot be counted. Making
DERIVED first-class converts one answer into nine decisions at zero marginal cost and zero fabrication
risk, and the same lever applies to per-tier curve shapes, symmetric training rules across kinds, and
`CapRule::TierBased` chains.

**The ordering rule.** For any decision the planner takes the **cheapest sufficient** provenance,
resolving in the order **1 → 2 → 5 → 3 → 4 → 6**, and records which one it used. Human-declared beats
canon beats derivation beats citation beats proposal beats default — cost rises to the right and
trust falls after 3. Provenance 6 is a *floor*, never a filler: a magnitude may take a policy default,
but a **structural** decision that reaches POLICY is a **refusal**, not a fallback. That single rule
is what makes an all-`not_stated` run impossible to pass.

---

## 6 — `PPL-A6` — the planner is a LOOP over an open-decision register

> **`PPL-A6`.** The planner's primary object is not a question set. It is the **open-decision
> register**: the live list of decisions the plan needs and does not yet have. The register is derived
> from the skeleton (`PPL-A4`) crossed with the four parts (`PPL-A1`), it is the human's worklist, and
> the loop terminates on **closure** (`PPL-A2`), never on "all questions answered".

This is the PO's *"enrichment is a loop, not a one-shot prompt"*, and it is the same shape
PlanForge landed on for books: a persisted typed spec as SSOT, `plan_self_check` supplying gaps so the
human need not point at fields, blocking checkpoints, and re-running only downstream phases on edit.
The HIL/ontology literature converges independently — competency questions refined by domain experts,
expert judgment overwriting predicted correctness, iterative confirm-and-refine.

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │                                                                          │
 │   ProgressionSpec  (typed · persisted · versioned · THE SSOT)            │
 │                                                                          │
 └───────┬──────────────────────────────────────────────────────▲───────────┘
         │                                                      │
         ▼                                                      │
   OPEN-DECISION REGISTER ──────────────────────────────────────┤
   every decision with no owner yet, ranked by blocking-power    │
         │                                                      │
         ├─▶ ① DECLARED    the human answers directly           │
         ├─▶ ② CANON       resolve from glossary / wiki / KG    │
         ├─▶ ⑤ DERIVED     expand a decided pattern             │
         ├─▶ ③ CITED       interrogate the sealed corpus  ◀── doc 39 S0–S2, kept
         ├─▶ ④ PROPOSED    ask the model, mark, queue for gate  │
         └─▶ ⑥ POLICY      magnitudes only; structural ⇒ REFUSE │
                                                                │
         ▼                                                      │
   CLOSURE CHECK (PPL-A2) ── not closed ──▶ new register rows ───┘
         │ closed
         ▼
   COMPILE ──▶ RealityManifest declarations ──▶ doc 39 S4 policy ──▶ S5 candidate
                                             ──▶ S-1 validator ──▶ S6 pin
```

**Why it is a loop and not a pass.** Answering a decision *creates* decisions. Declare that `inner_power` is a
Stage kind → the ladder's tiers open. Cite the tier list → each tier's breakthrough condition opens.
Learn that a breakthrough needs the *cold pool* → a **place** requirement opens, which is not a progression
decision at all (§8). The register grows before it shrinks, and a one-shot pipeline has nowhere to put
the growth. This is exactly why M1's runs could not have succeeded by answering harder.

**Termination.** The loop ends when the register is empty **and** closure holds. The register is empty
only against a human-fixed denominator (`PPL-A4`) — which is the second reason the skeleton comes
first, and the reason "convergence" here is a real predicate rather than a feeling.

**`PPL-A6.1` — the register is ranked by blocking-power, not by schema order.** A decision that
unblocks eleven others outranks one that unblocks none. M1's `kind.quantity` had maximal blocking
power and was asked as question #1 of an unranked list *of a model*; ranked and routed to provenance 1
it costs ten seconds and unblocks the run.

---

## 7 — The entity graph

The PO asked for *"the relationships between the entities"*. This is it — nodes are the planner's decision
subjects, edges are what one decision obliges of another.

```
                 ┌───────────────────────┐
                 │  ProgressionSkeleton  │  ① DECLARED, human, first
                 └───────────┬───────────┘
                             │ fixes the roster (PPL-A4)
                             ▼
    ┌────────────────────────────────────────────────────────────┐
    │                    ProgressionKind                          │  ◀── VARIABLE
    │   type · body_or_soul · role · representation               │
    └──┬──────────┬──────────────┬──────────────┬────────────┬────┘
       │          │              │              │            │
 derives_from  materialises   has_curve      capped_by   contributes_to
       │          │              │              │            │
       ▼          ▼              ▼              ▼            ▼
 ProgressionKind  L2 Declared   Curve      CapRule      L3 Source ──▶ strike_formula
   (COUPLING)     Quantity        │       (TierBased      (COUPLING)     · skill check
                 doc 35 §4        │        ──▶ another                   · access check
                 ordinal·width    │           Kind)                          (GATE)
                                  ▼
                              Tier[ ] ──gated_by──▶ BreakthroughCondition   (GATE)
                                  ▲                        │
                                  │                        │ requires
                        raises    │                        ▼
                     ┌────────────┴────────┐     ┌──────────────────────┐
                     │    TrainingRule     │     │  OUTBOUND DEMAND     │
                     │      (INFLOW)       │     │  Item · Place ·      │
                     └──┬──────────────┬───┘     │  Status · Actor      │
                        │              │         └──────────────────────┘
                 triggered_by    conditioned_on            │  §8
                        │              │                   ▼
                   Action · Tick   Place · Status ──▶ other element modules
                                                       (doc 38 §6 roster)
```

Reading it against `PPL-A1`: the **left column is inflows**, the **spine is variables**, the **right
column is gates**, and the **diagonals are couplings**. `PPL-A2` is a reachability query over this
graph, which is why it is checkable and why the check can go red.

Two structural facts fall straight out, and neither is expressible in doc 39's model:

1. **`derives_from`, `CapRule::TierBased` and L3 contribution are all Kind→Kind edges**, so the plan
   is a graph over its own roster, not a list of independent rows. Cycles are possible and must be
   refused — `PROG_001` §12.4 already owns cycle detection at the generator; the planner must refuse
   the cycle at **plan** time, where the human can still choose which edge to cut.
2. **Half the leaves of a breakthrough condition are not progression at all.** They are Items, Places,
   Statuses and Actors, owned by other element modules. §8.

---

## 8 — `PPL-A7` — a progression plan emits OUTBOUND DEMANDS, and cannot be a closed pipeline

> **`PPL-A7`.** A breakthrough condition that requires a pill and a sealed pool has authored a
> **requirement on the item module and the place module**. The progression planner does not own those
> elements, must not invent them, and must not silently drop them. It emits a typed **demand**, and an
> unsatisfied demand is a plan that is **not closed**.

This is already visible in the shipped code, as prose that has nowhere to go:

```python
# app/gamegen/fold.py
"place": "CPL-A3 place element module (TrainingCondition::LocationMatch needs a PlaceTypeRef)",
"item":  "CPL-A3 item element module (TrainingCondition::InstrumentMatch needs an ItemRef)",
```

A comment is not a mechanism — the same finding [`non-vacuity`](../../../standards/non-vacuity.md)
records against three prose-only deferrals, and the same finding the deferral registry now enforces
mechanically. A demand must be a **row**, not a string in a dict:

```
Demand { from_decision, target_module: item|place|status|actor,
         shape: "a consumable that permits a Stage advance",
         evidence: <the provenance that raised it>,
         state: open | satisfied(ref) | refused(reason) }
```

Three properties this buys, all of which the current design lacks:

- **`PGN-A20` gets its counterpart.** Doc 39 says an out-of-scope element is *"a REFUSAL that names its
  owner"*. Naming the owner is only half a mechanism if there is no channel to send it down. The
  demand register is the channel — and it makes the refusal **actionable** instead of terminal.
- **Cross-module closure becomes checkable.** `PPL-A2` extends: a Gate whose demand is `open` is an
  unreachable gate, caught at plan time rather than discovered by a player standing in front of a
  pool that does not exist.
- **Generation order stops being guesswork.** The demand graph across element modules *is* the build
  order for doc 38 §6's roster — derived, not decreed.

---

## 8A — The validator: three jobs, and only one of them needs a logic engine

The PO's requirement: *"there must be a rule-based validator that checks what is MISSING across the
whole architecture … human + LLM stay in a continuously self-improving loop … until a strict structure
is produced."*

**"A validator" sounds like one thing and is three.** Conflating them is why the question *"which
library?"* has no single answer — each job has a different one, and two of the three are already
solved in this repo.

| # | job | the question it answers | tool class | status here |
|---|---|---|---|---|
| 1 | **Shape** | is this well-formed? | typed schema — pydantic v2 / serde / JSON Schema | **shipped** (`S-1`, gamegen models) |
| 2 | **Constraint** | is this *combination* legal? | cross-field predicates — plain code, or a constraint lang | **shipped** (`CapRule`×`CurveDecl` matrix, `PROG_001` §5.5) |
| 3 | **Completeness** | **what is MISSING, and what does it block?** | **a logic engine — deduction + abduction** | **does not exist. This is the gap.** |

Job 1 and 2 are **closed-world shape checks**. JSON Schema `required` can say *"field `curve` is
absent"*. It **cannot** say *"`inner_power` has no inflow"* — that is a recursive query with negation over a
graph the schema does not know is a graph. `PPL-A2` closure, `PPL-A2.1` transitive orphans, cycle
detection over `derives_from`, and `PPL-A7` demand satisfaction are **all job 3**. That is the boundary,
and it is the reason a schema language is not the answer no matter how expressive it gets.

### 8A.1 `PPL-A8` — the register is an ABDUCTION, and that is why it can be computed

> **`PPL-A8`.** The open-decision register is not a hand-maintained checklist. It is the
> **abductive answer** to the query *"the plan is not closed — what minimal set of facts would close
> it?"* Deduction says **no**. Abduction says **what would make it yes**, and that is the next question
> to the human.

This is the single most important thing in this section. Three names for the same operation, from
three literatures, and all three are implementable:

- **Abductive Logic Programming** — designate some relations as *abducibles*; the solver assumes the
  minimal consistent set needed to satisfy the goal. Designed for exactly this: reasoning where the
  knowledge base is **known to be incomplete**.
- **"Why-not" provenance** — the Datalog debugging question *"an expected tuple does not appear; why?"*,
  answered as a derivation tree with holes. `PUG` and Soufflé-class provenance do this.
- **Minimal repair** — the constraint-solving framing: smallest edit that restores satisfiability.

**Why this collapses the architecture.** Without it, the register is a second artifact somebody must
keep in sync with the rules — a mirror, and mirrors drift (this repo has a standard about that). With
it, **there is exactly one artifact: the rules.** The register is a *query result*. Change a rule and
the register changes with it, automatically, with no possibility of drift, because it was never stored.

It also makes `PPL-A6.1`'s ranking free: blocking-power is *how many other abduced facts become
unnecessary once this one is supplied* — a count over the same derivation, not a heuristic anyone has
to tune.

### 8A.2 This is precisely the coding-agent loop, and the mapping is exact

The PO named it: *"it will be like the feedback loop of Claude Code or Cursor."* The mapping is not
an analogy — it is the same control structure with different nouns:

| coding agent | this planner |
|---|---|
| the artifact is **code** | the artifact is a **typed fact set** |
| the validator is **compiler + tests + linter** | the validator is the **logic program** |
| an error is *"undefined symbol `foo` at line 12"* | an abduced fact is *"`inflow(inner_power, ?)` is missing and it blocks 3 gates"* |
| the error text **becomes the next prompt** | the abduced fact **becomes the next question** |
| the human intervenes where intent is ambiguous | the human answers where provenance **must** be ① (`PPL-A9`) |
| loop ends when it **compiles and tests pass** | loop ends when the **repair set is empty** (`PPL-A2`) |

**The validator is the prompt generator.** That is the whole design. There is no separate "question
bank" to author and no `briefs/*.json` to maintain — M3 measured what happens when you hand-author the
question set: 11 questions covering one of four parts, and nobody noticed until a live run refused.
A question set derived from rules cannot have that defect, because the rules *are* the completeness
criterion.

### 8A.3 `PPL-A9` — the authority table lives IN the rules, not in the prompt

> **`PPL-A9`.** Which provenances are *permitted* for a decision class is a **fact in the logic
> program**, not an instruction in a prompt. A decision class marked human-only is never routed to a
> model — not because the prompt asks nicely, but because no rule permits it.

This is the PO's *"the LLM only helps enrich; how many attributes there are and how they are controlled
is a bounded proposal surface"*, and it is the concrete difference from PlanForge. PlanForge **proposes the whole spec**
and asks a human to approve it; approval-of-a-proposal is a weak gate, because a reviewer confronted
with a complete-looking document approves it. This planner **never proposes the roster at all**:

```prolog
% authority is data, and it is checkable
permits(roster,          declared).                        % ONLY ①. no model, ever.
permits(kind_type,       declared).  permits(kind_type, canon).
permits(tier_name,       cited).     permits(tier_name, derived).
permits(magnitude,       policy).    permits(magnitude, declared).
permits(breakthrough,    cited).     permits(breakthrough, proposed).  % ④ ⇒ human gate

violation(D) :- decided_by(D, P), class(D, C), not permits(C, P).
```

`violation/1` is a **refusal that can fire**, which `PPL-T1` bites. M1's failure was `roster` routed to
provenance ③/④; under `PPL-A9` that route does not exist and the run stops at the human in ten seconds
instead of dying four times.

### 8A.4 `PPL-A10` — the spec is a FACT SET; the manifest is the document

> **`PPL-A10`.** The planner's SSOT is a **flat set of typed facts**, each carrying its provenance and
> evidence. The nested strict-structure artifact (`data.json` / TOML) is a **compile projection** of
> that fact set, produced once at the end — never the thing being edited.

Every requirement above forces this, and a nested document defeats all four:

| requirement | why a fact set, not a tree |
|---|---|
| **partiality** | missing = *an absent tuple*. In a tree, missing = `null` vs `{}` vs key-absent vs default-applied — four encodings of one idea, and doc 39's policy-file laundering lived in that ambiguity |
| **abduction** | the abducible *is* a tuple. A solver consumes facts natively; a tree needs a lossy flattening pass first, and the flattener becomes a second place rules live |
| **provenance** | `PPL-A5` attaches to a **decision**, and a decision is a tuple. In a tree it becomes a parallel sidecar tree that must be kept aligned by hand |
| **the loop** | iterations produce diffs. Set difference is exact and order-free; JSON tree diff is neither |

Shape, concretely — one table, and the whole planner state is in it:

```
Decision {
  spec_id, class, subject, slot,      # class+slot = what PPL-A9 grants authority over
  value,                              # typed union; ABSENT is a legal state, not null
  provenance: 1..6,                   # PPL-A5
  evidence,                           # signature | record_id+version | span | ∅ | rule_id | policy_hash
  status: open | decided | refused | superseded
}
```

Load that into the engine, run the rules, read back `missing/2` and `violation/1`. The strict structure
the PO wants is then a **compile output that cannot be authored into an invalid state**, because it is
only ever generated from a fact set that already passed.

### 8A.5 The library answer

**Two engines, two jobs — and it is not a mirror**, because they compute different things:

| | planner (Python) | admission (Rust) |
|---|---|---|
| question | *what minimal decisions close this?* — **abduction** | *is this closed?* — **deduction** |
| needs | search, optimization, choice rules, negation | a graph reachability query |
| may be | slow, interactive, non-deterministic in *ordering* | fast, deterministic, version-stamped (`PGN-A7`) |
| **recommend** | **`clingo`** (Potassco ASP) + **`clorm`** ORM | **`ascent`** (Datalog as a Rust proc-macro) — or 30 lines of plain Rust |

**Why ASP (`clingo`) for the planner.** Answer Set Programming is Datalog plus the two things the
register needs and Datalog lacks: **choice rules** (which encode abducibles directly) and
**optimization statements** (which rank the register by blocking-power in the same solve). Potassco
maintains it, `clorm` gives a typed Python ORM over it so `Decision` rows map to atoms without
hand-written string munging, and the standard caveat — **ASP grounds, so it explodes on large domains**
— does not bind here: the domain is 10–30 kinds and a few hundred decisions. This is the size ASP is
excellent at and precisely why it is the right call *for this problem* and would be the wrong call for
the sim tier.

**Why Ascent for the engine side.** It is a proc-macro: rules compile to native Rust at `rustc` time,
no solver ships, no runtime dependency, and the relations are ordinary Rust types. It fits the existing
`ruleset-loader` validator shape with nothing new in the deployed binary. Honestly: closure *is* simple
enough to write by hand — use Ascent if the rule set grows past a screen, plain code if it doesn't.
**Do not put a solver in the admission path.**

**The parity test that makes the split safe.** `repair_set(plan) = ∅` (clingo) **iff** `closed(plan) =
true` (Rust), asserted over every fixture. That is a real bite-test with a real failing subject: today's
POC-1 output must come out `closed = false` **and** produce a non-empty repair set naming the missing
inflows. If the two ever disagree, one of them is wrong and CI says so — `PPL-T8`.

**Considered and rejected**, with the reason, so nobody re-opens these:

| candidate | verdict |
|---|---|
| **CUE** | genuinely excellent at jobs 1+2 — unified type/value lattice, order-independent merge, reports inconsistency before application. **Cannot do job 3**: no recursion, no derivation. Also Go-native, and this repo is Rust+Python. |
| **JSON Schema** | keep it — for the **wire contract of the compiled artifact**, which is what it is good at. Not a completeness engine. |
| **SHACL / ShEx** | RDF-shaped; we are not RDF. `knowledge-service` has Neo4j but the planner's SSOT is Postgres relations. Wrong impedance. |
| **OPA / Rego** | policy decisions over JSON with partial evaluation — close, but weak recursion and a Go runtime to deploy. |
| **Z3 / MiniZinc (SMT/CP)** | overkill for structural closure. **But keep the pointer**: §13's open question #3 — *pacing* — is a numeric constraint problem (*"tier 9 in ten hours or ten years?"*) where a CP/SMT solver is the right tool. Different question, later. |
| **`cozo` / `mnestic`** | embedded Datalog *databases* — the register would be a persisted query, which is attractive. Cozo went quiet after Dec 2024; `mnestic` is the maintained fork (Mozilla Public License 2.0). Revisit if the fact set outgrows Postgres; not needed at this size. |
| **`nemo`** (TU Dresden) | Rust Datalog with **tracing provenance** — the "why" explanations. Worth watching if clingo's justifications prove too coarse for the human-facing *"why are you asking me this?"*. |

---

## 9 — Where the planner lives, and what it is made of

**Service.** `lore-enrichment-service` (Python) — the language rule puts AI/LLM work there, the
gamegen tables and the sealed-corpus machinery are already there, and the loop is LLM-driven.
The **compile target and every validator** stay in Rust (`ruleset-core` / `ruleset-loader`), unchanged
from doc 39 S-1/S4–S6.

**Agentic surface — MCP-first.** The planner is agentic (a model reasons multi-step over tools and
data), so per the MCP-first invariant it is exposed as **MCP tools on the owning domain service and
federated through `ai-gateway`** — never a bespoke HTTP endpoint over a raw prompt. This is also what
makes it drivable from chat, which is how PlanForge's HIL actually gets used in practice.

| tool | phase | notes |
|---|---|---|
| `prog_declare_skeleton` | 0 | `PPL-A4`. Human. Blocking. |
| `prog_open_register` | loop | `PPL-A6`. The worklist, ranked. |
| `prog_resolve_canon` | loop | provenance ② — glossary/wiki/KG. No model. |
| `prog_derive_pattern` | loop | provenance ⑤ — procedural expansion. No model. |
| `prog_interrogate` | loop | provenance ③ — doc 39 S0–S2, **kept whole**. |
| `prog_propose` | loop | provenance ④ — marked, span-forbidden, queued for gate. |
| `prog_closure_check` | loop | `PPL-A2`. The gate that can go red. |
| `prog_demands` | loop | `PPL-A7`. Cross-module register. |
| `prog_compile` | exit | → RealityManifest decls → doc 39 S4/S5/S6. |

**Tenancy.** Per User Boundaries, every planner table carries a scope key. `ProgressionSpec` and the
registers are **per-book** (`book_id` + `owner_user_id`), matching the gamegen tables shipped in S2.
The numeric policy stays **System-tier default, narrowed per book** (`PGN-A15`, and the read-time
containment re-check that S4's review installed). No shared row is user-writable.

**What is reused rather than rebuilt:** `source_corpus` + seal, `gamegen_decision` / `gamegen_answer`
(the approval unit is already the assertion class, `PGN-A11`), `gamegen_numeric_policy`,
`gamegen_candidate`, both Rust CLIs, and the whole citation-verification path. The planner is
mostly **new orchestration over shipped parts**, plus two genuinely new stores: the open-decision
register and the demand register.

---

## 10 — Verdict on POC-1, stated plainly

**FAIL.** Recorded here rather than laundered, per the same discipline doc 39 §0.1 applied to itself.

| the PO asked | answer |
|---|---|
| *can we define a cultivation system deeply enough?* | **No — not by this route.** Four live runs, zero manifests. The blocking question was a design decision routed to a model. |
| *usable in-game, or must the human add manually at the manifest step?* | **Neither, as built.** Even a fully-answered run produces a ladder with no inflows and no gates: unplayable at 11/11 (`PPL-A2`). The human would not be "adding manually at the manifest step" — the human would be authoring three of the four parts from scratch. |
| *detailed enough and playable?* | **Not playable**, and now that is a graph check rather than a judgement. |

**What POC-1 did prove**, and it is not nothing: the trust machinery works. Across four runs against a
real model, **zero fabricated citations reached storage** — every one refused by name with its reason,
via span-derivation against a sealed corpus. Tenancy holds under adversarial probing (five HIGH
findings found and closed). The validator, the two-pass pin, the policy-hash equality check and the
fold's magnitude refusal all fired correctly on real input. **That layer is kept whole and this
document is built on top of it.** What failed is the claim that a corpus plus one pass of questions
constitutes a progression system.

---

## 11 — Trust properties

| id | property | mechanism | can it fail? |
|---|---|---|---|
| `PPL-T1` | the roster is human-owned | `prog_compile` refuses a spec whose skeleton has no human signature | yes — a model-authored roster reaches compile and is refused |
| `PPL-T2` | a shipped system is playable | `prog_closure_check`: every Variable has ≥1 inflow and ≥1 gate | yes — the POC-1 output fails it today, which is `PPL-T2`'s first bite-test |
| `PPL-T3` | a gate can refuse | `PPL-A2.2` — a condition satisfiable by every t=0 actor is refused | yes — an unconditional breakthrough is admitted by the schema and rejected here |
| `PPL-T4` | no structural decision defaults | provenance ⑥ is magnitude-only; structural ⇒ refusal | yes — an all-`not_stated` run now refuses instead of shipping |
| `PPL-T5` | every decision names its provenance | the six-way enum is non-null on every register row | yes |
| `PPL-T6` | a cross-module requirement is not lost | `prog_demands`; an `open` demand blocks closure | yes — the current `fold.py` comment-string version fails it |
| `PPL-T7` | coverage is measured against a fixed denominator | skeleton version is an input to the coverage number; an amendment invalidates it | yes — a silent roster change reds the coverage claim |
| `PPL-T8` | the two engines agree | parity: `repair_set = ∅` (clingo) **iff** `closed = true` (Rust), over every fixture | yes — and POC-1's output is the first failing subject: `closed=false` + a non-empty repair set |
| `PPL-T9` | no decision class is silently re-routed | `violation(D) :- decided_by(D,P), class(D,C), not permits(C,P).` (`PPL-A9`) | yes — `roster` decided by a model fires it |

**`PPL-T2`, `PPL-T3` and `PPL-T6` each have a real failing subject available today**, which is the
[`non-vacuity`](../../../standards/non-vacuity.md) bar: the bite-test's output is the deliverable, and
three of these can be bitten against the code as it stands rather than against a hypothetical.

---

## 12 — What this changes elsewhere

| doc | change |
|---|---|
| `39` | S0–S3 demoted to **one input path** (provenance ③). §2's stage chain gains a preceding loop. S-1, S4, S5, S6 unchanged. §0.1's honesty table gains this document as its sequel. |
| `38` | `CPL-A10`'s three authorships gain a fourth source: **CANON** (authored SSOT). Doc 38 assumed LLM-or-procedural-or-human-gate and did not model the wiki as a *generator input*. |
| `35` | unchanged. L2 declaration is the compile target; `QTY-A13` (a source contributes, never declares) is what makes the Variable/Coupling split in `PPL-A1` land correctly. |
| `PROG_001` | unchanged as a runtime substrate. It is now also the **decision space schema** — the planner's register is derived from it, so §6 and §9 stop being unreachable. |
| `glossary-service` | new read path: the planner resolves provenance ② out of `wiki_*` + entity records. **No writes.** Read-only, scope-filtered. |
| standards | none violated; MCP-first, tenancy, provider-gateway and language-rule all bind as noted in §9. |
| **new deps** | `clingo` + `clorm` in `lore-enrichment-service` (Python, first logic engine in the repo — verified absent today); `ascent` in `ruleset-loader` **only if** the closure rules outgrow hand-written Rust. Both are additive; neither ships a solver into the game runtime. |
| `PlanForge` | no change to PlanForge itself, but `PPL-A9` is a **finding against its gate model** worth carrying back: approval-of-a-complete-looking-proposal is a weak gate. If the novel planner has classes that should be human-only, it has the same hole. |

---

## 13 — Open

1. **What is the minimum skeleton?** §4 sketches ~10–30 decisions. The real number wants one designer
   sitting down with the wuxia fixture and a blank spec — measured, not guessed.
2. **How does CANON get authored at scale?** The wiki is the highest-leverage input (`PPL-A5`) and
   also the one with the most human cost. Does the planner *propose wiki edits* back — a second loop,
   with glossary as SSOT and the same six-provenance discipline? Attractive, and a write path into the
   authored SSOT needs its own gate design before anyone builds it.
3. **Is `PPL-A2` sufficient for "playable"?** It is necessary and it is checkable. A closed system can
   still be *badly paced* — closure says nothing about whether tier 9 takes ten minutes or ten years.
   Pacing is magnitudes, i.e. doc 39 S4's policy, and grading it needs simulation, not a graph query.
   **Stated as a limit rather than hidden**, per doc 39 §11.1.
4. **Demand cycles.** Progression demands a place; the place module demands a progression gate. Refuse,
   or seed one side? Probably refuse-and-name, matching `PROG_001` §12.4's posture on kind cycles.
5. **Where does `genre_intent` bind?** It steers proposal quality and binds nothing, which makes it
   unauditable by construction. Acceptable, or does it need to be a first-class DECLARED artifact?

---

## Sources

External research consulted while writing §1, §2 and §6:

- [RPG Stat Systems Explained: Designing Character Progression](https://www.strayspark.studio/blog/rpg-stat-systems-character-progression-design) — core attributes vs. derived stats; the tooltip-as-trust argument
- [RPG Game Design (Fundamentals, Patterns, Mechanics)](https://gamedesignskills.com/game-design/rpg/)
- [RPG Progression Systems](https://adrianfr99.github.io/RPG-progression-system/) — XP, levels, skill trees, attributes as distinct components
- [Game Economy Balancing With Spreadsheets](https://www.strayspark.studio/blog/game-economy-balancing-spreadsheets) — prototype the flow before the code
- [A 7-Step Framework for Game Economy Design](https://gamedevessentials.com/a-7-step-framework-for-game-economy-design/) — resource flow → pricing/progression curves ordering
- [My Approach To Economy Balancing Using Spreadsheets](https://www.gamedeveloper.com/design/my-approach-to-economy-balancing-using-spreadsheets)
- [AGWM: Affordance-Grounded World Models for Environments with Compositional Prerequisites](https://arxiv.org/pdf/2605.06841) — tech trees as DAGs; frontier vectors; edges active only when both endpoints unlocked
- [SkillDAG: Self-Evolving Typed Skill Graphs](https://www.researchgate.net/publication/405852828_SkillDAG_Self-Evolving_Typed_Skill_Graphs_for_LLM_Skill_Selection_at_Scale) — prerequisite/specialization/composition/conflict edge typing
- [Skill Tree Design: Ultimate Guide](https://adriancrook.com/skill-tree-design-ultimate-guide-for-freemium-games/) — gating patterns
- [From human experts to machines: An LLM supported approach to ontology and KG construction](https://arxiv.org/abs/2403.08345) — competency questions refined by domain experts
- [Knowledge graph validation by integrating LLMs and human-in-the-loop](https://www.sciencedirect.com/science/article/pii/S030645732500086X) — expert judgment overwrites predicted correctness
- [LLM-Driven Ontology Construction for Enterprise Knowledge Graphs](https://arxiv.org/html/2602.01276v1) — expert-defined schema + LLM expansion from authoritative sources

Consulted while writing §8A (the logic-engine survey):

- [Abductive Logic Programming](https://www.artificial-intelligence.blog/terminology/abductive-logic-programming) — abducibles; inferring the best explanation when facts are missing
- [Reasoning on Datalog± Ontologies with Abductive Logic Programming](https://www.researchgate.net/publication/323669227_Reasoning_on_Datalog_Ontologies_with_Abductive_Logic_Programming)
- [PUG: Why & Why-Not Provenance](https://arxiv.org/pdf/1808.05752) — explaining answers *and non-answers* over Datalog
- [Provenance for Large-scale Datalog](https://arxiv.org/pdf/1907.05045) — the two debugging scenarios, incl. "an expected tuple does not appear"
- [User Guided Abductive Proof Generation for ASP Queries](https://arxiv.org/pdf/2209.07948)
- [clorm — a Python ORM for the clingo ASP reasoner](https://github.com/potassco/clorm)
- [Exploring Clingo](https://medium.com/design-bootcamp/exploring-clingo-a-comprehensive-guide-5e577f163036) — choice rules + optimization statements
- [Ascent — logic programming in Rust](https://s-arash.github.io/ascent/) · [docs.rs](https://docs.rs/ascent/latest/ascent/) · [ascent-interpreter](https://crates.io/crates/ascent-interpreter/0.1.2)
- [crepe — Datalog as a Rust proc-macro](https://github.com/ekzhang/crepe)
- [CozoDB](https://rustutils.com/tools/cozodb/) · [mnestic — the maintained fork (Mozilla Public License 2.0)](https://www.mnesticdb.com/)
- [CUE — data validation use case](https://cuelang.org/docs/concept/data-validation-use-case/) · [how CUE works with JSON Schema](https://cuelang.org/docs/concept/how-cue-works-with-json-schema/)
- [SHACL Satisfiability and Containment](https://arxiv.org/pdf/2009.09806) · [xpSHACL](https://arxiv.org/pdf/2507.08432)
