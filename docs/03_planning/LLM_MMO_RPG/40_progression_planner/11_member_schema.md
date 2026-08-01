# 40.11 — The member schema: what a contract actually IS as data, and whether it feeds the item generator

> **Status:** DESIGN + MEASURED · **Date:** 2026-07-31 · **Prefix:** `MEM-`
> **Answers three questions** posed against [`40.6`](06_item_contract.md) and
> [`40.7`](07_module_organisation.md): *do we have a contract yet? name/code/description/tag — then
> what? is there a logic structure? and is this enough for the item generator to RUN from?*
> **§4 was rewritten the same day** — its first version applied a test that would have collapsed
> tier 1 into tier 2.
> **Round 3 of the spike** (`templates/spikes/item_grade_chat/probe3.py`) forces a real model to emit
> members against this schema. Results in §5.

---

## 0 — Do we have a contract yet? **No.**

`40.6` §3 declared five **slot shapes**. `40.7` §5 stored members as `member_json jsonb` — a blob with
no schema. So what exists is *where members live* and *how many are allowed*, and **not one line
saying what a member is**. That gap is why the question *"is this enough to feed the item generator?"*
had no answer: nothing was defined precisely enough to check.

This document defines it, then checks whether the item generator can RUN from it — §4. (The first version of that check asked the wrong question; the correction is kept in place, not laundered.)

---

## 1 — `MEM-A1` — every member is an ENVELOPE plus a slot-typed BODY

> **`MEM-A1`.** One envelope for every member of every slot in every module. Only the `body` varies,
> and it is typed by the slot's registration. A slot may not add an envelope field, and the envelope
> may not be slot-aware.

```jsonc
{
  "slot_id":     "item_archetype",
  "code":        "sword",            // THE CONTRACT — see MEM-A2
  "ordinal":     null,               // integer iff slot.ordered; ASSIGNED, never authored
  "name":        { "zh-Hant": "劍", "en": "Sword" },
  "description": { "zh-Hant": "…",  "en": "…" },

  "body":        { /* exactly the slot registration's member:{…} — MEM-A3 */ },

  "provenance":  "CITED",            // closed enum, 6 values
  "evidence":    { "kind": "span", "chunk": "book/ch12", "quote": "…" },
  "status":      "approved",         // proposed | approved | superseded
  "decision_id": "…"                 // joins gamegen_decision, carries the human signature
}
```

**So the answer to *"name, code, description, tag — then what?"*** is: **four more envelope fields that
were missing, and they are the ones that make it auditable rather than merely typed** —

| missing field | why it is not optional |
|---|---|
| **`ordinal`** | an ordered slot without it is not ordered. **Assigned by the engine, never authored** (`QTY-A5`: monotonic, never reused). Round 3 P9 got this wrong and a mechanical check caught it — §5 |
| **`provenance`** | without it, a citation and an invention are the same row. The entire trust argument of this track lives in this field |
| **`evidence`** | a provenance with no evidence is a label. Discriminated by provenance: span / record / rule / analogy / author / ∅ |
| **`status` + `decision_id`** | approval is a human act with a signature; a member with no decision behind it never passed a gate |
| **`evidence` must RESOLVE** | `MEM-A5` (§5A.1) — measured: given five provenance labels and a verifier for only one of them, the model invented referents for the other four |

And `tag` is **not** an envelope field — it is a `body` field of exactly one slot. Putting it in the
envelope would make every slot in every module carry item's vocabulary.

## 2 — `MEM-A2` — `code` is the contract; `name` is decoration

> **`MEM-A2`.** `code` is ASCII `snake_case`, unique within its slot, and **immutable once approved**.
> Every cross-slot reference, every generated `ItemDefId`, every crafting recipe and every loot table
> holds a `code`. `name` is an `I18nBundle` and may be re-translated freely; nothing may reference it.

This is the repo's existing i18n discipline (`RES_001` §2 — English snake_case ids + `I18nBundle`
display) applied to the pool, and it is what stops a Chinese-language reality being unreferenceable
from English code. Renaming 劍 → 寶劍 must be a translation edit, never a schema migration.

## 3 — `MEM-A3` — the "logic structure" is TYPED REFERENCES, and they are the edges

The question *"is there a logic structure, or just flat records?"* — there is, and it is not
free-form. Bodies come in exactly the two shapes `EPL-A3` permits:

| body shape | slots | logic content |
|---|---|---|
| **flat** — envelope only | `item_grade`, `instrument_tag`, `equip_slot` | none. The member *is* its identity |
| **referential** | `item_archetype`, `item_affix` | **fields holding other slots' `code`s** |

```jsonc
// item_archetype — every body field is a reference or an engine-fixed enum
"body": {
  "class":           "Weapon",          // -> ItemClass, ENGINE-FIXED, 8 variants
  "instrument_tags": ["blade"],         // -> instrument_tag.code[]
  "equip_slot":      "main_hand"        // -> equip_slot.code, nullable
}
```

**Those reference fields ARE `pool_reference`** (`40.7` §5). The member body and the edge table are one
thing viewed two ways: the body is how a human reads it, the edge table is how the register queries
it. A reference whose target does not exist is a row with `to_member IS NULL` — which is `EPL-A8`'s
entire cross-module mechanism, and it needs no separate protocol because it is just an unresolved
body field.

**What a body may NOT contain**, and this is the line that keeps the pool a pool: **no magnitude.** No
damage, price, weight, rate, duration or probability. Cardinality, order, names and references only
(`EPL-A3`). Round 3 tests this against a source stuffed with numbers — §5.

---

## 4 — The sufficiency test — and the first version of this section applied the wrong one

> ### ⚠ Corrected 2026-07-31, same day, by the PO
> The first draft of this section asked: **"does the pool supply every field of `ItemDefDecl`?"**,
> found four missing, and proposed adding four fields to `item_archetype`'s body.
>
> **That is the wrong test, and acting on it would have collapsed the architecture.**
> `ItemDefDecl` is the **item generator's** output — tier 2 in [`ICT-A1`](06_item_contract.md). The
> contract generator produces **tier 1: the lists**. Demanding that the contract pre-supply every
> field the generator will produce makes the contract *become* the `ItemDef` table, which is exactly
> the failure `ICT-A1` names: *"put it in the pool and a human is asked to hand-author three hundred
> rows."* Three tiers were separated in `40.6` and re-collapsed here five documents later.

### 4.1 `MEM-A4` — the contract's job is INPUTS, not OUTPUTS

> **`MEM-A4`.** The contract generator is sufficient when the specific generator has every **input**
> it needs to decide the rest — **not** when the contract already contains the answers. A field the
> generator can *decide* is not a contract gap. The generator draws on three sources, and only the
> first is the pool:
>
> | source | supplies | owner |
> |---|---|---|
> | **the frozen pool** | vocabulary and axes — what kinds exist, what tags exist, what order things come in | contract generator |
> | **its own numeric policy** | every magnitude | the specific generator (`EPL-A3`) |
> | **its own LLM half** | naming, description, flavour | the specific generator (`EPL-A6`) |

### 4.2 The walk, redone with the right question

For each `ItemDefDecl` field: is it **(P)** supplied by the pool, **(G)** decidable by the generator
from pool + policy + seed, or **(✗)** neither?

| `ItemDefDecl` field | | why |
|---|---|---|
| `class` · `equip.slot` · `instrument_tags` | **P** | they are the taxonomy; that is what tier 1 is |
| `display_name` · `description` | **G** | the LLM half, seeded by the archetype and grade names |
| `def_id` | **G** | derived from `(archetype.code, grade.code)` |
| `use_effect` op selection | **G** | *a healing pill restores* is the generator composing an item from a closed `EffectOp` set it can already see |
| `equip.combat.strike_kinds` | **G** | derivable from the archetype's `instrument_tags` |
| `equip.requirements` — which progression kind | **G** | `progression_kind` is a **SHARED** slot; the generator reads the codes and picks |
| `equip.requirements` — the threshold | **G** | a magnitude — numeric policy, correctly outside the pool |
| `modifiers[].stat_slot` | **P** | `item_affix.body.stat_slot` |
| `modifiers[].value` · `price` · `weight` · `max_charges` · `reach` | **G** | magnitudes |
| `consume_on_exhaust` · `destructible` | **G** | functions of `class` |
| **`lex_tags`** | **✗** | `WA_001` owns this vocabulary and **has registered no pool slot for it**. Item can only reference what someone published |

**One gap, not four — and it belongs to another module.** The fix is not four new fields on
`item_archetype`; it is `WA_001` registering `lex_tag` as a SHARED slot, after which item's generator
reads it the same way it reads `progression_kind`. Nothing about item's contract changes.

### 4.3 The recurring error, recorded because it will happen again

This is the **third** time in this track that downstream responsibility was pulled upstream:

| # | where | the pull |
|---|---|---|
| 1 | `PPL-A7` | `Demand{shape: "a consumable that…"}` — the planner specifying item design |
| 2 | `PPO-A1` | *"the planner declares `alchemist_grade` and demands the mechanism"* — specifying crafting |
| 3 | `MEM-A4` v1 | the contract required to contain every generator output field |

Each was caught by the PO, not by a check. The shape is always the same: **an upstream layer asked to
guarantee a downstream layer's result instead of supplying its inputs.** It is worth a lint if one can
be written — a body field whose only consumer is one generator's output field is the smell.

---

## 5 — Round 3: a real model, forced into the schema

Same local model, same seam. Three slots, one per planner kind that has one, and **mechanical checks
that can fail**: unique ascii codes · locale-map names · provenance in the enum · ordinals contiguous
for ordered slots · **no magnitude anywhere in a body**.

| probe | slot | kind | parse | checks |
|---|---|---|---|---|
| **P9** | `item_grade` | `Ladder` | OK, 4 members | **FAIL** |
| **P10** | `instrument_tag` | `Enumeration` | OK, 12 members | pass |
| **P11** | `item_archetype` | `Composite` | OK, 10 members | **PASS** |

### P9 — the failure is instructive, and the check caught it

Ordinals came back **`[9, 8, 7, 1]`** for four members. Not a typo: the model was numbering positions
**on the 9-realm ladder** rather than on the grade ladder it was asked to build. A defensible mental
model, silently wrong output, and **no prose in the reply revealed it** — only the contiguity check
did.

It also emitted **4** members where the author's answers implied 5–6, and named them in generic
western-fantasy vocabulary for a classical-Chinese world — the same naming leak round 1 showed, now
visible as data instead of prose.

**This is `ordinal` earning its place in the envelope** (§1). Had ordering been implicit in array
position, the output would have looked fine.

### P11 — the slot predicted to be hardest passed cleanly

Ten archetypes, **all mechanical checks green**, and three things worth naming:

- **`封神榜` → `scroll` → `class: "Document"`.** It did **not** force a Weapon. That is fixture tooth
  `I9` — *not everything is a weapon* — answered correctly on the first try, against a source where
  every other object is a weapon.
- **References used `code`s, never display names** (`MEM-A2`), and stayed inside the settled tag and
  slot vocabularies it was given.
- **No magnitude leaked** — from facts containing *seven chi*, *twenty-four segments*, *twenty-four
  pearls*. The prohibition held where round 1's did not, because the schema made it checkable rather
  than merely stated.

Two judgement calls worth a human's eye rather than a check: `banner → Tool` (defensible; `Trinket`
also arguable) and `wheel → equip_slot: feet` (a nice reading of a ridden object). Both are exactly
the kind of thing a gate exists for.

### What round 3 adds to `ASK-A5`/`ASK-A6`

Rounds 1–2: rules that **restrain** fail in prose. Round 3: **a rule that is a schema does not fail** —
the no-magnitude rule held under pressure, and the one violation that did occur (`ordinal`) was caught
by a check rather than by reading. Same lesson, from the artifact side: **put the constraint where the
output has to pass through it.**

---

---

## 5A — Round 4: take the ordinal off the model, and the list comes out clean

P9's only failure was ordinals `[9, 8, 7, 1]`. `QTY-A5` already says ordinals are **assigned, never
authored** — so the fix was not a better prompt but **deleting the field from the model's job**. Round
4 changes exactly that one variable: the schema has no rank field, **the array order IS the ladder**,
and the planner numbers it afterwards.

| probe | change | members | checks |
|---|---|---|---|
| **P9** (round 3) | model emits `ordinal` | 4 | **FAIL** — ordinals `[9,8,7,1]` |
| **P12** | ordinal removed | 7 | **PASS** |
| **P13** | P12 + the world's own naming register | 8 | **PASS** |

**The structural defect vanished the moment the model stopped being asked for it.** That is the same
shape as `ASK-A5`/`ASK-A6` from the other side: rounds 1–2 showed a constraint in prose fails; round 4
shows **a decision the model never makes cannot be got wrong.** Strip a decision off the model and
that class of error goes to zero rather than getting smaller.

### 5A.1 `MEM-A5` — provenance is worthless unless the evidence RESOLVES

Both probes passed every check. The checks were not enough.

**P12 labelled three members `CANON`** with evidence pointing at genre packs named `base_items` and
`mid_tier_assets` — and **no genre pack was ever mentioned to it.** It also emitted two `DERIVED`
members citing rules `9_realm_landmark_1` and `9_realm_landmark_5` that were never stated as rules.
The enum values were legal, the evidence objects were well-formed, and **every referent was invented.**

> **`MEM-A5`.** A provenance label is trustworthy only when its evidence **resolves against a real
> artifact**: `CITED` → a span inside a sealed chunk · `CANON` → a record id that exists in a real pack
> · `DERIVED` → a rule id that a prior decision actually created · `PROJECTED` → a slot that exists ·
> `DECLARED` → a signature. **Unresolvable evidence is a REFUSAL, not a warning.** Doc 39 built exactly
> this for `CITED` (`PGN-A14`, span-verified against a sealed corpus) and nobody built it for the other
> five. Round 4 shows the gap is not theoretical: given five labels and no way to check four of them,
> the model used the uncheckable ones.

This also explains P13's result and makes it the more interesting one. **Given the world's own
vocabulary, it labelled all eight members `PROPOSED`** — honest, because it had real material to work
from and no need to dress an invention as a record. *The false CANON in P12 was a symptom of having
nothing to cite.*

### 5A.2 The count still is not derived — and the fix is the same fix again

The author's answers (*landmarks of a 9-realm ladder, plus a story-only top*) imply **5–6**.
P12 produced **7**, P13 produced **8**. Both inside the `3..9` suggest range, so both passed — and
**neither honoured the derivation it was given.** `ASK-A2` exists precisely to stop a count being
picked rather than computed, and the model picked.

The fix is the ordinal fix, one level up: **the planner computes the cardinality from the structural
answers and asks the model only for names, in order.** Round 4 removed ordinals and that error class
went to zero; removing the count should do the same. What is then left for the model is what it is
actually good at — **naming, and ordering by meaning** — which is exactly the division `EPL-A6`
predicts and P13 demonstrates.

### 5A.3 Naming: the register fixes it, the instruction does not

P12, told nothing about vocabulary, produced *Common Relic* … *Mythic Singularity* — generic
western-fantasy tiers in a classical-Chinese world, the same leak round 1 showed in prose.

P13, handed the world's own register, produced an eight-rung ladder entirely in that register, with
both locales populated. **No instruction to avoid western naming was needed in P13 — it had better
material, and used it.** Where the corpus can supply the vocabulary, supplying it beats forbidding the
alternative.


---

## 5B — Round 5: it was missing CONTEXT, and the fidelity gate had to be bitten to be believed

The PO's read of round 4's *Common Relic … Mythic Singularity*: **missing context**, not a missing
word list — PlanForge already solves this by injecting setting reminders and then gating on a fidelity
rubric with a self-heal round (`06_FIDELITY_POC_EVAL`: rubric → score → gate ≥ 0.85, and a rejected
round causes **no regression**).

That read was right, and testing it exposed a defect in the gate I built to test it.

### 5B.1 A setting charter alone fixes naming — and fixes the count too

**P14** supplies a `SETTING CHARTER` (work, language, register, era feel, and one hard rule that
modern rarity-tier vocabulary belongs to a different tradition) and **no word list at all**. Round 4's
P13 had needed a curated lexicon, which does not generalise — you cannot hand-curate a vocabulary per
slot per world. A charter you can always write.

Result: a five-rung ladder entirely in the world's own register, both locales populated, `凡 → 靈 →
神 → 仙 → 天道`. And **five members** — which is what the author's stated derivation implied and what
round 4 had drifted past (7, then 8).

> **`MEM-A6` — supply the register, do not forbid the alternative.** Round 4's P12 had the same task,
> the same schema and no charter, and produced a western tier ladder. P13 fixed it with a word list;
> P14 fixed it with **context**, which is the instrument that scales. The count drifting back into
> line was not asked for and is the more interesting half: **a model that knows what world it is in
> makes better structural decisions, not just better-sounding ones.**

### 5B.2 The gate could not fail, and only a bite-test showed it

**P16** deliberately weakens the charter to reproduce round 4's conditions, so the gate has something
to catch. First run:

```
round 0: 6 members · fidelity 0.857 · PASS
    ✗ no_generic_tier: western rarity vocabulary (offenders: ['grade_mythic_fable'])
```

**The criterion fired and the gate passed anyway.** Seven categorical criteria, one failure, 6/7 =
0.857 — over a 0.85 threshold. The naming rule the whole rubric exists to enforce was
**unenforceable**, and every run so far had been graded by an instrument that could not fail on a
single violation.

The root cause is a copied number: PlanForge's 0.85 is tuned over ~51 fine-grained checks, where one
failure moves the score by 0.02. Copied onto a 7-criterion categorical rubric it becomes a rubber
stamp — the only failing scores are ≤ 5/7.

> **`MEM-A7` — a weighted score is the wrong instrument for a small rubric of categorical criteria.**
> Register fidelity is not a percentage. Criteria split into **HARD** (any failure fails the gate,
> whatever the score) and **SCORED**. Here `no_generic_tier`, `codes_ascii`, `no_invented_evidence`
> and `in_suggest_range` are HARD. A hard-broken round can also never *be* the retained best, which
> the first version got wrong too.

### 5B.3 With the gate fixed, the self-heal loop works — measured

Re-run of the same bite-test:

```
round 0: 6 members · fidelity 0.714 · FAIL (hard criterion)
    ✗ no_generic_tier: offenders ['grade_common','grade_uncommon','grade_rare',
                                   'grade_epic','grade_legendary','grade_mythic']
    ✗ no_invented_evidence: CANON claimed, and no genre pack exists (MEM-A5)
round 1: 5 members · fidelity 1.0 · PASS
```

Round 0 under the weak charter produced **the western rarity ladder verbatim** — round 4's failure,
reproduced on demand. Round 1, fed only the failing criteria, repaired to the world's register and
converged in **one** heal round. **The self-heal loop is now proven rather than assumed**, which it
was not while P14 kept passing on the first try.

### 5B.4 The finding nobody was looking for: run-to-run variance

P14 was run twice with an identical prompt.

| run | fidelity | verdict |
|---|---|---|
| first | 1.0 | PASS |
| second | 0.857 | **FAIL (hard)** — `no_invented_evidence`: it claimed `CANON` with no pack in existence |

**Same prompt, same model, same settings — one clean pass and one hard failure.** `MEM-A5`'s invented
provenance is not a deterministic defect; it surfaces on some runs and not others.

That settles a question this spike had been circling: **a single good run proves nothing about a
planner.** The gate is not there to catch a bad model; it is there because *the same model is both
runs*. Anything that ships on "it worked when I tried it" is sampling, not engineering.


## 6 — Open

1. **`WA_001` must register a `lex_tag` slot** (§4.2) — the one real gap. It is not item's to fix.
2. **Is `equip.requirements`'s *kind* really the generator's call?** §4.2 says G because
   `progression_kind` is SHARED and readable. The counter-argument is that *which* kind gates a sword
   is a world-design statement, not a composition detail. If it turns out to be P, it is **one** field
   on `item_archetype` — not four. Decide with a worked reality, not in the abstract.
3. ~~P9's ordinal confusion~~ **CLOSED by round 4** (§5A) — ordinals removed from the model's job,
   the failure class went to zero, and the check that caught it is now unreachable. **Do the same for
   cardinality** (§5A.2): the planner computes the count, the model supplies names in order.
4. **Run §4.2's walk for `place` and `actor`** before `PPB-A6` goes pipeline-wide — but run it with
   the corrected question (*does the generator have its inputs?*), not the first draft's
   (*does the contract contain the outputs?*). The wrong question manufactures gaps.
