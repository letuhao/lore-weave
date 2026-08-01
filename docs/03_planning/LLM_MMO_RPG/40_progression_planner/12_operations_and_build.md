# 40.12 — The four operations, and how the contract generator gets built

> **Status:** MEASURED + DESIGN · **Date:** 2026-07-31 · **Prefix:** `BLD-`
> **Part A** closes the round 6–8 investigation: the four planner kinds needed a second axis nobody
> had named. **Part B** answers the build questions — module shape, planner registration, per-kind
> workflow, and whether this repo's architecture is strong enough to carry it without duplication.
> Probes in `templates/spikes/item_grade_chat/` (git-ignored); doc 40.10/40.11 hold rounds 1–5.

<!-- design-lint: ok prefix ACP — `ACP-13` is the Agent Control Plane standard, owned by
     docs/standards/agent-control-plane.md on the PLATFORM track. It is CITED here (§11) because it
     already decided the external-framework question this document was asked to re-evaluate.
     Registering `ACP` in this track's id catalog would claim ownership of another track's namespace,
     which is the opposite of what the catalog is for — same reasoning as the `ML-*` pragma at the top
     of this track's SESSION_HANDOFF. -->

---

# Part A — rounds 6–8: kinds have a SHAPE and an OPERATION

## 1 — What rounds 6–8 measured

Round 5 tuned one slot (`item_grade`, a `Ladder`). Rounds 6–8 ran the **same rig** — setting charter,
member schema, fidelity gate, one self-heal round — at the other three item slots, to test
[`MOD-A1`](07_module_organisation.md)'s claim that four kinds cover everything.

| probe | slot | kind | gate said | actually |
|---|---|---|---|---|
| P18 | `equip_slot` | `Profile` | 1.0 PASS | ✅ correct — kept the 6-slot engine default, `DECLARED` |
| P17 | `instrument_tag` | `Enumeration` | 1.0 PASS | ❌ **wrong** — returned the individual treasures |
| P19 | `item_archetype` | `Composite` | 0.9 PASS | ⚠️ half — refused the mounts correctly; archetypes were objects, and the register was dropped |

> **Three of four "passed" and two of the passes were wrong in the same way, invisibly.**

**P17 is the diagnostic one.** Asked for a *form vocabulary* it returned `金環 Gold Ring`,
`鐵鞭 Iron Whip`, `名劍 Named Swords` — **tier-2 `ItemDef` names**, which is what the item generator
produces, not what the contract generator does. It **jumped a tier**. And it emitted a mount as a tag,
while P19 — same rig, same facts — refused the same mounts correctly.

## 2 — `BLD-A1` — a kind has an output SHAPE and an OPERATION; `MOD-A1` named only the shape

> **`BLD-A1`.** The four planner kinds differ on **two** axes, and `MOD-A1` declared only the first.
> **Shape** is what the output looks like (ordered / unordered / defaulted / referential).
> **Operation** is what the planner *does to its evidence*, and it is what decides whether the answer
> is at the right tier at all.

| kind | shape | **operation** | criterion the operation yields — **needs no answer key** |
|---|---|---|---|
| `Ladder` | ordered set | **PARTITION** — a design axis cut into bands | the count follows the stated derivation |
| `Enumeration` | unordered set | **ABSTRACT** — n observed objects → m categories | **m < n**; every category covers ≥1 object; ≥1 category covers ≥2 |
| `Profile` | defaulted set | **CONFIRM/OVERRIDE** — compare a default to the source | equals the default, or the diff cites evidence |
| `Composite` | referential set | **CLASSIFY + LINK** — assign kinds, wire references | every reference resolves; classes are not all identical |

**This is the answer to a question doc 40.11 §5 left open** — *how do you write a semantic criterion
for a question whose answer you do not know?* You do not need the answer. You need the **operation's
signature**. P17 returned 11 categories for 11 objects: a 1:1 map is *by definition* not an
abstraction, checkable with no knowledge of what the right tags are.

**Measured (P20):** naming the operation and requiring a coverage map took 11 objects → **6
categories**, compression 0.55, three categories covering 2+. The tier-jump disappeared in one round.

## 3 — `BLD-A2` — the operation is not enough; the AXIS comes from the consumer

P20 abstracted, but along the wrong axis — grouping by outward shape, so a silk sash, a spear and a
string of pearls landed in one *"elongated"* tag. *"+swordsmanship while wielding a long thing"* is not
a rule anyone would write. Cause: the prompt said *"the shape of the thing"*, and that phrase beat the
purpose stated under it.

> **`BLD-A2`.** A slot's abstraction axis is derived from **who consumes its members and what they
> condition on** — never from how the evidence looks. For `instrument_tag` the consumers are
> `PROG_001` training rules and `DF07` stat terms, so the axis is *what a practitioner trains with*.

**Measured (P21):** with the consumer named, `軟器` grouped sash + whip + pearl-cord — a real martial
family (軟兵器) — and correctly split the spear into `刺器`. The grouping improved substantively.

**But compression got worse**: 8 tags for 11 objects (0.73, from 0.55), and only **one** tag covered
2+. §5 explains why, and it is the most useful finding of the three rounds.

## 4 — `BLD-A3` — refusal must be its own channel

P20 emitted a tag literally named *"non-implement"* covering two mounts and a register. The prompt had
invited it to *"say so"* and given it nowhere to say it, so **refusal disguised itself as a member**.

> **`BLD-A3`.** Every planner emits `{members, refused}`. A thing that does not belong to the slot can
> then never be a member, because there is nowhere in `members` to put it. Each refusal names the
> module that should own it instead.

**Measured (P21):** three refusals — both mounts → `bestiary`, the register → `bureaucracy` — each
naming an owner, **zero leakage into `tags`**. This fix worked completely and needs no follow-up.

## 5 — `BLD-A4` — asking a model to justify its own output yields justification, not scrutiny

P21 required a `rule_sentence` per tag, on the theory that a useless tag would read as nonsense and
expose itself. It produced:

```
+momentum  while wielding a 輪器      +authority while wielding a 旌器
+precision while wielding a 剪器
```

**It invented a new stat per tag** so that every sentence read fine. Instead of exposing thin
categories, the device **licensed arbitrary granularity** — and that is what pushed compression from
0.55 down to 0.73.

> **`BLD-A4`.** A self-justification field is not a check. A criterion must rest on something the
> model does not control — `m < n` held across every round; *"write why this is good"* inverted the
> thing it was meant to measure.

## 6 — And for the third round running, the broken instrument was mine

P21's checker flagged `flexible_implements` for containing a banned shape-word. The word was **"long"**
— inside the *evidence quote* (`a red silk sash, seven chi long`), not in the tag name. The checker
serialised the whole member and substring-matched.

| round | the instrument's defect | how it surfaced |
|---|---|---|
| 5 | a copied `0.85` threshold could not fail on 1-of-7 | bite-testing the gate |
| 6 | hygiene criteria only; no semantic criterion at all | reading the output |
| 8 | the scan matched inside evidence, not inside the name | reading the output |

**Not once did the score reveal it.** Every defect in the measuring apparatus was found by comparing
output against what it *should* have been. That is worth stating as plainly as the model findings:
**the gate is code, and code has bugs, and a green gate is evidence about the gate as much as about
the model.**

---

# Part B — how this gets built

## 7 — Module shape

```
crates/ruleset-core/src/pool/          REGISTRY + engine-side validation        (Rust)
  declare.rs        declare_pool_slot! + SlotShape (shape · operation · arity · visibility)
  slots/item.rs     one file per OWNING module — item's five
  export.rs         emits contracts/pool/registry.json at build time
  validate.rs       arity / ordering / visibility / reference legality

contracts/pool/registry.json           GENERATED. Never hand-edited. Read by Python.

services/lore-enrichment-service/app/pool/
  registry.py       typed loader over registry.json — one source, no mirror
  kinds/            enumeration.py · ladder.py · profile.py · composite.py   ← FOUR files
  criteria.py       the per-operation criteria of BLD-A1, shared
  register.py       the abductive open-decision register            (clingo)
  loop.py           rank → probe → ask → resolve → validate → repeat
  store.py          pool_member / pool_reference
  freeze.py         content-address the pool, emit the digest
```

**Per-slot Python: none.** A module contributes `slots/<module>.rs` and nothing else. That is the
whole reuse claim, and it is falsifiable: if adding a sixth slot requires a Python file, `MOD-A1` is
wrong.

## 8 — `BLD-A5` — planners register by KIND; slots bind to kinds in data

> **`BLD-A5`.** The planner registry is keyed by **kind**, not by slot. A slot names its kind in its
> Rust registration; the Python side resolves `kind → PlannerKind` through one table. **Adding a slot
> never touches planner code**, and adding a *kind* is a deliberate architecture decision with four
> files' worth of friction, exactly as it should be.

```python
PLANNERS: dict[Kind, PlannerKind] = {
    Kind.ENUMERATION: EnumerationPlanner(),   # operation = ABSTRACT
    Kind.LADDER:      LadderPlanner(),        # operation = PARTITION
    Kind.PROFILE:     ProfilePlanner(),       # operation = CONFIRM
    Kind.COMPOSITE:   CompositePlanner(),     # operation = CLASSIFY + LINK
}
```

The `PlannerKind` protocol gains two methods over [`40.7` §2](07_module_organisation.md), both forced
by Part A:

```python
def axis(self, slot, registry) -> Axis:        # BLD-A2 — derived from the slot's CONSUMERS
def criteria(self, slot) -> list[Criterion]:   # BLD-A1 — the operation's own checks
```

`axis()` is computed, not authored: read `registry.json` for every slot whose members reference this
slot, and the consumers *are* the axis. `instrument_tag`'s consumers are progression training rules
and DF07 stat terms, so the axis falls out of the registry rather than out of a prompt.

## 9 — Per-kind workflow

Identical spine, four bodies. The differences are exactly `BLD-A1`'s operations.

```
   probe(slot)            ── retrieval, multi-modal, through the seal      ENR-A1/A2
        ↓
   ask(open_row)          ── closed-option questions, kind-specific        ASK-A2
        ↓
   emit                   ── {members, refused}, member schema             BLD-A3 / MEM-A1
        ↓
   criteria(slot)         ── operation checks + HARD/SCORED split          BLD-A1 / MEM-A7
        ↓  fail
   heal(failed)           ── one round, failing criteria only              round 5
        ↓  pass
   human gate             ── approve · re-query · answer directly · DECLINE
```

| kind | probe | ask | criteria beyond the shared hygiene set |
|---|---|---|---|
| `Ladder` | boundary probes — a ladder is found by its ends | 3 structural questions, then **compute the count** | count follows the derivation · total order · ordinals **planner-assigned** |
| `Enumeration` | concept + known members as seeds | *"which forms does this world distinguish?"* + coverage map required | **m < n** · coverage ≥1 · some category ≥2 |
| `Profile` | the default set's members, looking for contradiction | one question: accept or override | equals default, or the diff cites evidence |
| `Composite` | one query per unresolved field | per-field, seeded by the member | references resolve · classes vary · **cross-module rows raised** |

**Rounds 4–8 in one line:** every decision moved off the model — ordinals, then cardinality, then the
axis — took an error class to **zero**, not down. The model keeps naming, ordering-by-meaning, and
judging relevance.

## 10 — Storage and the seam: reuse, do not rebuild

Unchanged from [`40.7` §5](07_module_organisation.md): reuse the tenancy-hardened `gamegen_*` decision
layer, add `pool_member` and `pool_reference`. The LLM seam is `lore-enrichment-service`'s existing
`make_complete_fn` → provider-registry `/internal/llm/stream` — already used across **12 files** in
that service, already `model_ref`-resolved with no model name in code.

## 11 — `BLD-A6` — do we need LangChain / LangGraph? **No, and the repo already decided why**

The standard is explicit, and it was written before this track existed:

> **`ACP-13`** — *"Framework-agnostic port, not a dependency: an external framework (LangGraph/…)
> integrates as an adapter onto the hook port, subject to the invariants; never a rebuild ON it, and
> never built ahead of a real consumer."*

Three reasons it is the right call **for this loop specifically**, beyond the standard:

1. **There is no graph to orchestrate.** `PPL-A8` makes the next step an **abduction** — a query
   result over the register — not an edge someone drew. A DAG framework solves a problem this design
   deliberately does not have, and adopting one would re-introduce it as a maintained artifact.
2. **The invariants are the hard part, and a framework does not carry them.** Provider-gateway,
   no-hardcoded-model, per-user `model_ref`, tenancy scope keys, sealed-corpus citation,
   provenance-with-resolvable-evidence — every one would have to be re-imposed on top of the
   framework's own call path. `ACP-13` calls this *"a rebuild ON it"* and forbids it.
3. **The measured failure modes are not orchestration failures.** Rounds 1–8 found: bounds ignored in
   prose, a state machine invented around, provenance fabricated, a self-justification field
   inverting its own check, three broken measuring instruments. **No framework addresses any of
   those.** They are answered by a registry, a schema, and criteria that rest on things the model
   does not control.

### 11.1 The reuse question, answered with a measurement rather than an opinion

The repo has **18 Python SDK packages** under `sdks/python/` and an `SDK-First` standard. But:

| measured | |
|---|---|
| composition-service `app/engine/` modules | **43** |
| of those importing the shared `llm_client` | **19** |
| lore-enrichment files using its own `CompleteFn` seam | **12** |

So there are already **two divergent LLM-call idioms in two services** — composition's job-based
`LLMClient.submit_and_wait` and lore-enrichment's streaming `make_complete_fn` — and fewer than half
of composition's engine modules go through even its own shared client.

> **`BLD-A6`.** The duplication risk here is **real and already realised**, and it is not the kind a
> framework fixes. Adopting LangGraph would make it **three** idioms. The contract generator reuses
> `loreweave_llm` through lore-enrichment's existing seam and adds **four planner files plus a shared
> criteria module** — and the reuse claim is falsifiable: *if a sixth slot needs a fifth planner file,
> the design is wrong.*

**What is worth building for reuse** (and only when a second consumer exists, per `ACP-13`): the
`PlannerKind` protocol + `criteria.py` as an SDK package once the place or actor module needs them.
Not before — the repo's own standard says *never built ahead of a real consumer*, and this track has
exactly one.

---

## 12 — Open

1. **P21's compression regression is unexplained beyond `BLD-A4`.** Removing `rule_sentence` and
   adding a hard `m ≤ n/2` is the obvious next probe; it was not run.
2. **`axis()` is computed from consumers — but `instrument_tag`'s consumers live in `PROG_001` and
   `DF07`, neither of which has registered a slot yet.** Until they do, the axis has to be authored.
   That is the same shape as `MEM-A4`'s `lex_tag` gap: **item's contract keeps being blocked on other
   modules not having registered theirs.**
3. **The checker's scan bug (§6) means every earlier round's "pass" is worth one re-read.** Not
   re-run — re-read. A pass produced by a checker with a known scoping bug is weaker evidence than it
   looked at the time.
4. **Nothing here is built.** Part B is a plan; the only running code is git-ignored probes.

---

# Part C — the four-kind cycle, measured

Part B was a plan and said so ("nothing here is built"). It is built now: `contracts/pool/registry.json`
plus `services/lore-enrichment-service/app/pool/{registry,criteria,register,kinds,loop}.py`, 41 tests,
and repeated live runs against a local model through provider-registry.

The cycle shipped in two steps. Step one was two slots and two kinds, both owned by `item`. Step two —
this part — registered `PROG_001`'s two slots, which forced the two planner kinds that had until then
existed only as a `NotImplementedError` naming them.

## 13 — What the second step was actually testing

Not "does it run". Three claims that could each have come back false:

| Claim | Where it would have failed |
|---|---|
| `BLD-A5` — a slot is a registry row, never a file | a fifth planner file, or an `if slot.id ==` anywhere |
| `EPL-A8` — demand is a register, not a list | registering `progression_kind` failing to REMOVE its row |
| the kinds generalise past their author's slot | `Ladder`/`Profile` needing item-shaped assumptions |

All three held. Adding two slots owned by a **different module** added two registry rows and two kind
classes keyed by **operation**; no file names a slot, and `planner_for` still refuses a fifth operation
by name. `progression_kind`'s `unregistered_target` row disappeared the moment it was registered, and
`equip_slot` is deliberately left unregistered so the channel still has a subject — a demand list that
only ever grows is not a register.

> **`BLD-A7`.** The reuse claim survived its first real test: **two owning modules, four operations,
> zero per-slot code.** The claim stays falsifiable and the falsifier is unchanged — *a fifth operation
> is an architecture decision; a fifth planner FILE for an existing operation means `MOD-A1` is wrong.*

## 14 — Five defects the live runs found, and the one shape they share

Every one was in **this project's code**, not the model's. Ordered by how badly each hid.

**1. The register was compiling model text as solver source.** Member codes went into the ASP program
bare. `24_pearls` is a syntax error and crashed a run; the dangerous one is `Blade`, which **parses** —
as an ASP *variable*. A capitalised code would have made the register answer a different question with
nothing to show for it. Model-supplied values are now quoted terms; registry identifiers are validated
at load, since those still go in bare.

> **`BLD-A8`.** A validator the parser depends on for its own parsing is one adjacent decision from
> being defeated. The criteria reject a bad code **and** the register cannot be broken by one — two
> layers that hold independently, because a single layer here was an injection.

**2. Rejected members were readable as approved.** `PoolRun.pool` returned any slot that had members,
including slots the criteria had HARD-FAILED. Three things then read rejected material as approved: the
register stopped calling the slot open, the next planner was offered its codes, and `references_resolve`
accepted a pointer into it. The tell was a log line reading `NOT FROZEN — 0 slot-level open row(s)` —
a refusal that reports nothing to refuse.

> **`BLD-A9`.** This is `ASK-A5` a second time inside the same loop, and the second instance has a
> distinct shape worth naming. The first **ignored** the verdict (`approve()` was called regardless).
> This one **laundered** it: the rejection was recorded correctly on the slot and then read from a
> place that did not carry it. A verdict is not enforced by being stored; it is enforced by every
> reader being unable to bypass it.

**3. The envelope did not declare a field the operation required.** `covers` is demanded by ABSTRACT
and is not a slot body field, so a slot with `member: {}` gave the model nowhere legal to put it. It
duly invented a different home each run — `body.covers` once, `body.instrument_match` the next, which
failed the same two criteria three times in a row with a sound answer underneath. **The first fix went
into the checker**, teaching it to read both positions.

> **`BLD-A10`.** Treating the instrument again — the fifth time in this track. The prior four were
> measurement bugs; this one shipped into product code as a *tolerance*, which is worse, because a
> tolerance looks like robustness. It then collided with `no_undeclared_body_fields`: one rule
> accepting exactly what another rejected. **A requirement belongs in the artifact that states the
> contract, not in the checker that reads it.**

**4. The heal round asked the model to repair an answer it could not see.** The prompt said *"fix only
these and keep the rest"* without including the previous attempt, so each heal was a fresh roll wearing
a repair's name. With the rejected answer and the findings both present, three slots that had failed
three times each began converging on attempt 1 or 2.

**5. A truthiness test on model text is not a test.** `refusals_name_an_owner` checked `r.get("owner")`,
and a live run produced the **string** `"null"` — truthy, so the refusal passed while routing nowhere.
The model can always supply a truthy nothing.

## 15 — What the ordinal seam taught

`QTY-A5` says the planner assigns ordinals. The obvious criterion — *ordinals are contiguous 1..N* —
is **vacuous**: the planner assigns them 1..N by construction, so it cannot fail. What *can* fail is the
seam: the model emitting a number of its own, which the probe rounds did. So the criterion runs on the
**raw** model output and the planner stamps afterwards, at settle.

> **`BLD-A11`.** Ordering is a two-part contract with a mandatory sequence: **validate what the model
> returned, then stamp.** Stamping first makes the check read the planner's own field. And settle is
> the right moment for the other half of the reason — you cannot number a ladder that is still
> changing.

## 16 — Open, and one of them is a dead state

1. **`REOPENED` is declared and unreachable.** Nothing moves a slot into it. The trigger is real and
   was measured: `item_archetype` requires a list of `instrument_tag` codes, and the model omitted the
   field on every archetype no settled tag covered — refusing to lie, correctly. Healing cannot fix
   that, because the fix is **upstream in a slot that has already settled**. Reopening on downstream
   under-coverage is a feature with its own termination question and is not built. A test asserts the
   state is currently unreachable and **re-reds when it becomes reachable**, so whoever wires it has to
   state the bound they chose.
2. **A refusal carries two different meanings and one field.** `owner` means *"this belongs to another
   module"* for ABSTRACT and CLASSIFY_LINK, but for PARTITION a refusal means *"this axis has no
   ladder"* — nothing is being routed. Live runs duly put the slot's own name in `owner`. The channel
   needs either two shapes or an explicit reason kind.
3. **A slot cannot bind another slot's refusal.** `instrument_tag` refused the two mounts to `beings`;
   `item_archetype`, in the same run, classified both as archetypes. Whether a refusal in one slot
   constrains another is a **boundary decision** (`PPB-A4` — a gate belongs to whoever refuses), not a
   bug to patch, and it is unresolved.
4. **`registry.json` is still hand-authored.** `"generated": false` says so, and a test asserts the
   flag rather than letting a reader assume. The Rust `declare_pool_slot!` export and its drift test
   are not built.
5. **The freeze is per-module.** `PPB-A5` says a planner is done when it is internally closed, and the
   cycle freezes on that basis while `equip_slot` is still open elsewhere. A pool-wide freeze across
   modules is a different gate and does not exist.

---

# Part D — the consumer half, and what the freeze actually reaches

Everything up to Part C **produced** contract. The pool was filled, validated, hashed and read by
nobody: the digest was computed and thrown away. That means `PPB-A6` — *two layers separated by a
freeze, and no module ever reads another module's L2 output* — had never been under load in either
direction. Nothing existed to violate it, and nothing existed to show it was satisfiable either.

This part is the load: `app/pool/freeze.py` (the artifact), `app/pool/consume.py` (the only surface a
generator gets), `app/generators/item_l2.py` (the first consumer), and a separate process that reads
the artifact file and nothing else.

## 17 — The number `ICT-A2` was asserting without one

`ICT-A2` says the item module's pool footprint is **small** and its bulk is tier 2, which it produces
itself. Resolved against a real freeze, field by field over `PL_007`'s 14-field `ItemDefDecl`:

| | count | fields |
|---|---|---|
| **FROZEN** — the contract supplies it | 2 | `class` · `instrument_tags` |
| **OWN** — this generator produces it | 10 | ids, vocabulary, and every magnitude (`PGN-A5`) |
| **BLOCKED** — the contract owes it and no module registered the slot | 2 | `equip` → `equip_slot` · `lex_tags` → `lex_tag` |

`ICT-A2` holds, and holds harder than it claimed: the contract's footprint is 4 of 14 fields, and it
currently delivers **half** of its own scope. The ratio is deliberately `frozen / (frozen + blocked)`
rather than `frozen / total` — dividing by all fields would make the number fall as the generator grew
fields of its own, which reads as the contract getting worse when nothing about the contract changed.

> **`BLD-A12`.** The two blocked fields are **exactly** the two targets the abductive register has
> reported since the first cycle — `equip_slot` and `lex_tag`. Two mechanisms built for different
> purposes, one over the registry's reference graph and one over a downstream struct's fields,
> independently name the same pair. A test asserts they agree, because the day they stop agreeing one
> of them is reading a stale list.

## 18 — The freeze was the wrong SHAPE, and three live runs said so before any test did

The first freeze was **pool-wide**: the artifact was emitted only when every registered slot in the
whole registry had settled. Three consecutive runs against a real model produced no artifact at all,
and in two of them the blocker was `progression_stage` — a slot `item` does not reference and cannot
be affected by. **Item's contract was complete and unusable.**

That is `PPB-A5` inverted by its own implementation. *A planner is done when it is internally closed* —
and "internally" is neither of the two obvious readings:

* **its own slots** drops `progression_kind`, which `item_archetype.gates_on` points at, so the
  artifact would carry a code the consumer cannot resolve;
* **the whole pool** drags in every unrelated module, which is what blocked those runs.

The right unit is the **transitive closure of the references** (`freeze.closure_for`). For `item` that
is `{instrument_tag, item_archetype, progression_kind}` — a proper superset of its own slots and a
proper subset of the pool. With it, item froze on a run where `progression_stage` never settled.

> **`BLD-A13`.** A boundary that has never been crossed has not been tested; it has only been drawn.
> The pool-wide gate passed every unit test for two cycles because no test had a consumer in it, and
> the defect appeared within three runs of one existing. **The first consumer is a test of the
> contract, not of the consumer.**

## 19 — Making `PPB-A6` a mechanism rather than a rule

Three things now enforce what doc 03 asserted:

**The surface is an absence.** `PoolView` exposes `members` · `codes` · `member` · `has` ·
`visible_slots` · `unmet` · `digest`, and **nothing that could return another module's generated
content**. A test pins that exact set, so adding `view.output_of(module)` reds here rather than
becoming a code-review topic again.

**The import graph is checked.** A generator may import the freeze and the view. Importing
`app.pool.loop`, `.criteria`, `.kinds` or `.register` means it is reading the machinery that produced
the pool rather than the pool; importing another generator means it is reading someone else's L2.
Both are asserted by walking the AST of every file under `app/generators/`, and the test refuses to
pass with an empty file list — a scope that reaches nothing is the default-uncovered shape.

**The artifact is self-describing and self-checking.** It carries its digest and `verify()`
recomputes it, because a hash stored beside content and never recomputed is a label; a consumer pins
that digest into everything it generates, so a mismatched artifact would put truthful-looking
provenance on different bytes. It also carries the **unmet demands forward**: `equip_slot` is present
as a named hole naming who else waits on it, never as an empty list that reads *"this world has no
equip slots"*. That confusion has now been caught twice in this project — once in the register, once
in the pool — which is why it is a raise and not a return value.

`EPL-A7`'s SHARED/PRIVATE split is enforced here too, and this is where it first had anything to
enforce against. Both registered slots are SHARED, so the PRIVATE subject is constructed in the test.
That is legitimate — the check reads the freeze's **data**, and the data varies — but it is worth
saying plainly: no production slot exercises it yet.

## 20 — A closed set that was not the RIGHT closed set

The live consumer run admitted 14 of 14 defs and refused none. That is weak evidence on its own, and
inspecting it found the reason it was weak: `accept` checked `instrument_tags` against the **union of
all frozen tags**, not against the archetype's own. The model happened to reproduce each archetype's
tags exactly, so the run would have looked identical if every tag had been shuffled between
archetypes.

> **`BLD-A14`.** A closed-set check answers *"is this value in a legal set"*, and getting the SET
> wrong is invisible in exactly the runs that pass. The check now reads the archetype's own tags, and
> permits narrowing but not reaching — a def may carry fewer tags than its archetype, never one that
> belongs to a different archetype.

Nine mechanisms in this part were bite-tested — digest verification, the unmet hole, the closure in
both wrong directions, the missing-slot raise, visibility, the tag set, the digest pin, and the
per-owner gate.

## 21 — Open

1. **`lex_tag` and `equip_slot` are still unregistered**, and they are now blocking a named,
   measurable thing rather than an abstract one: 2 of the 4 fields the item contract owes.
2. **No production slot is PRIVATE**, so `EPL-A7`'s enforcement has only a constructed subject.
3. **The whole-pool freeze rate is low** and was not measured before this part. Four slots each with
   an independent chance of failing a hard criterion means the pool-wide digest is rare; per-closure
   artifacts make that mostly irrelevant, but the run-level `digest` still reports the strict answer.
4. **The consumer's own L2 has no store.** `accept` returns admitted defs and nothing persists them,
   so nothing yet tests that a *second* generator cannot read them — which is the other half of
   `PPB-A6` and still has no subject.
