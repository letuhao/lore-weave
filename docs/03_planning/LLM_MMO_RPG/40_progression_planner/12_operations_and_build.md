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
