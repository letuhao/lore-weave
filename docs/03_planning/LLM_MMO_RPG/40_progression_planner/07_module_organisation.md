# 40.7 — Module organisation: planner kinds, registration, storage, and what proves it works

> **Status:** DESIGN · **Date:** 2026-07-31 · **Prefix:** `MOD-`
> **Builds on** [`40.4`](04_enum_pool.md) `EPL-A2`/`A4`/`A7`/`A8` and [`40.6`](06_item_contract.md)
> `ICT-A1..A3`. **This is the implementation spec** — organisation, registration, storage, and the
> falsifiable proof. It designs no new game semantics.

---

## 0 — The question

> *"Each of those contracts needs its own planner, not a wandering all-in-one. At the start we thought
> the item generator and the planner were one thing — but here we actually have **four**. Now spec the
> module organisation: how to group, how registration into the contract pool works, how to implement,
> and how the data is stored. Prove it works, and the remaining quantities just follow the pattern."*

The count of four is the finding. Item has five slots ([`40.6` §3](06_item_contract.md)) and they do
**not** want five bespoke planners — they want **four kinds**, and item happens to need one of each.
That is what makes item the right proving ground.

---

## 1 — `MOD-A1` — there are four PLANNER KINDS; a slot declares which one plans it

> **`MOD-A1`.** A planner is written **per SHAPE, not per slot and not per module.** The set of shapes
> is closed and small. Registration binds `slot → planner_kind`, so adding a slot adds a **row**, never
> a program. An all-in-one planner is refused because the four shapes ask genuinely different
> questions; five hand-written planners are refused because four of them would be the same code.

| kind | shape it plans | the question it asks | item's | progression's |
|---|---|---|---|---|
| **`Enumeration`** | unordered closed set, flat members | *"which X does this world distinguish?"* | `instrument_tag` | `trigger_class` |
| **`Ladder`** | **ordered** closed set, often with a naming pattern | *"how many, and name them lowest-first"* | `item_grade` | `realm_tier` |
| **`Profile`** | bounded set with a strong **engine default** the author overrides | *"keep the default, or replace it?"* | `equip_slot` | — |
| **`Composite`** | members whose fields **reference other slots** | *"for each member: which class, which tags, which slot?"* | `item_archetype`, `item_affix` | `progression_kind` |

**Five slots, four kinds — and the same four cover progression.** That is the whole basis for the PO's
*"prove it works and the rest follow the pattern"*: the pattern is the kind, not the slot.

### 1.1 What differs between kinds is real, not cosmetic

Each kind differs in **four** places, which is precisely why one planner cannot serve all of them:

| | `Enumeration` | `Ladder` | `Profile` | `Composite` |
|---|---|---|---|---|
| **cardinality comes from** | the answer | the answer, and it is load-bearing | the default, unless overridden | the answer |
| **order** | none | **total; ordinals assigned** (`QTY-A5`) | declaration order | none |
| **provenance ⑤ DERIVED** | rarely | **the main lever** — one pattern answer expands to N members | n/a | per-field |
| **can open cross-module rows** | no | no | no | **yes** — its fields are references (`EPL-A8`) |

The `Ladder` row is the one that pays. *"Sub-levels are named Layer One … Layer Nine by convention"* is
**one** cited answer that expands to nine members, deterministically, auditable to a single span. Only
`Ladder` has that structure, and building it into the kind means every ordered slot gets it free.

The `Composite` row is the one that costs. It is the only kind whose members can **reference** another
module's slot, so it is the only kind that can raise a cross-module open row — `EPL-A8`'s mechanism
has exactly one home, which makes it testable in one place.

---

## 2 — Each kind, specified

Every kind implements one interface. This is the *whole* extension surface: a fifth kind is a real
architecture decision, and there is deliberately no plugin hook that makes it cheap.

```python
class PlannerKind(Protocol):
    def open_rows(self, slot: SlotShape, filled: PoolState) -> list[OpenDecision]:
        """What is still missing for THIS slot. Feeds the shared register (EPL-A4)."""

    def ask(self, row: OpenDecision, ctx: Context) -> Question:
        """The question form. Kind-specific; this is why one planner cannot serve all four."""

    def expand(self, answer: Answer, slot: SlotShape) -> list[Member]:
        """Provenance ⑤ DERIVED. Ladder expands a pattern; Enumeration is 1:1."""

    def validate(self, members: list[Member], slot: SlotShape) -> list[Violation]:
        """Arity, ordering, member-field types, reference legality (EPL-A7 visibility)."""
```

| kind | `open_rows` | `expand` | `validate` adds |
|---|---|---|---|
| `Enumeration` | one row while the set is empty; none after | 1:1 | arity bounds · uniqueness |
| `Ladder` | cardinality first, then names, then order | **pattern → N members**, ordinals assigned monotonically | total order · no ordinal reuse (`QTY-A5`) |
| `Profile` | one row: *accept default or override* | default set, or the override | arity cap (`equip_slot` ≤ 12) |
| `Composite` | one row **per unresolved field per member** | per-field | every referenced slot is **SHARED** (`EPL-A7`) and the member exists — else a cross-module open row |

**`Composite.open_rows` is where `EPL-A8` actually happens**, and it is worth being exact: it does not
*write* into another module's slot. It emits an open row **addressed to** that slot, and the loop —
one loop, one human (`EPL-A5`) — fills it.

---

## 3 — `MOD-A2` — three orthogonal groupings, and conflating them is the classic mistake

> **`MOD-A2`.** *Ownership*, *implementation* and *scheduling* group the same slots three different
> ways. A directory layout that serves one of them will fight the other two unless the split is
> deliberate.

| grouping | groups by | why | where it shows up |
|---|---|---|---|
| **ownership** | **module** — item owns its five | `EPL-A2`: the owner registers the shape; `EPL-A7`: the owner decides visibility | `crates/**/pool/slots/item.rs` |
| **implementation** | **planner kind** — four, shared by everyone | `MOD-A1`: the code is per shape | `app/pool/planners/ladder.py` |
| **scheduling** | **reference depth** — `Composite` after its referents | a composite needs its referenced slots to exist before its fields can resolve | the register's ranking, **not** a directory |

Scheduling is *not* a static ordering and must not become one. `EPL-A8` says slots reopen; a fixed
build order would freeze `item_archetype` before progression demanded a tag from it. The register's
blocking-power ranking (`PPL-A6.1`) already produces the right order dynamically — reference depth is
an **input to the ranking**, not a phase.

---

## 4 — Registration: one source in Rust, one exported artifact, one drift test

Closes [`40.4` §8.3](04_enum_pool.md) (*"where does the registry live?"*). It must be readable by the
Rust engine and the Python loop **without a mirror**, and this repo already has the pattern: doc 39's
schema fingerprint is declared in Rust and exported, with a drift test.

```rust
// crates/ruleset-core/src/pool/slots/item.rs — the OWNER registers
declare_pool_slot! {
    id:         "item_grade",
    owner:      ELEMENT_ITEM,
    visibility: SHARED,                  // EPL-A7
    planner:    Ladder,                  // MOD-A1
    arity:      2..=16,
    ordered:    true,
    tier:       Reality,                 // tenancy (User Boundaries)
    member:     { name: I18nBundle, rank: Ordinal },
}
```

```
crates/ruleset-core/src/pool/
  declare.rs          the macro + SlotShape
  slots/item.rs       item's 5      slots/progression.rs   ...one file per owning module
  export.rs           writes contracts/pool/registry.json at build time
  validate.rs         arity / ordering / visibility — the ENGINE's own check (PGN-A7)

contracts/pool/registry.json     GENERATED. Never hand-edited. Read by Python.
```

Three properties, each with a check that can go red:

| property | mechanism |
|---|---|
| the Python loop and the Rust engine agree on every slot | `registry.json` is generated; a **drift test** regenerates and diffs — same shape as the doc-39 fingerprint |
| a module cannot register a slot it does not own | `owner` is compared against the file's module path at macro expansion |
| a `Composite` cannot reference a `PRIVATE` slot of another owner | `validate.rs`, at registration — `EPL-A7`, checked in code rather than in review |

---

## 5 — Storage: reuse the decision layer that already exists; add two tables

**Do not build a second decision store.** The POC-1 S2 work shipped six `gamegen_*` tables whose
decision/evidence layer is already tenancy-hardened — composite FKs carrying `owner_user_id` after
five HIGH cross-tenant findings, UUID-checked `chunk_id`, and `length(quote) = end - start` pinning
character offsets over CJK. That is exactly the layer the pool loop needs, and it was built and probed
against a live adversary.

| table | status | role in the pool |
|---|---|---|
| `gamegen_corpus_seal` | **reuse as-is** | provenance ③ CITED reads only through the seal |
| `gamegen_decision` | **reuse as-is** | one row per open decision; the approval unit is the assertion class (`PGN-A11`) |
| `gamegen_answer` | **reuse as-is** | `says[]` / `proposed_text` / `not_stated`, span-verified |
| `gamegen_numeric_policy` | **reuse, per owner** | magnitudes — outside the pool (`EPL-A3`), one artifact per generator |
| `gamegen_creative_structure` | **retire from this path** | superseded by `pool_member`; it was progression-shaped |
| `gamegen_candidate` | **reuse** | the tier-2 / compile output, per module |
| **`pool_member`** | **NEW** | the filled members |
| **`pool_reference`** | **NEW** | edges between members — what the register abduces over |

```sql
CREATE TABLE pool_member (
  book_id        uuid    NOT NULL,
  owner_user_id  uuid    NOT NULL,          -- tenancy scope key, every query filters
  slot_id        text    NOT NULL,          -- FK-by-convention to registry.json (code, not a table)
  member_key     text    NOT NULL,          -- snake_case, stable
  member_json    jsonb   NOT NULL,          -- validated against the slot's member schema
  ordinal        int,                       -- NOT NULL for ordered slots; monotonic, never reused
  provenance     smallint NOT NULL,         -- PPL-A5, 1..6
  decision_id    uuid    NOT NULL,          -- who decided it, and on what evidence
  status         text    NOT NULL,          -- proposed | approved | superseded
  PRIMARY KEY (book_id, slot_id, member_key),
  FOREIGN KEY (decision_id, owner_user_id)  -- composite: the S2 tenancy fix, kept
      REFERENCES gamegen_decision (decision_id, owner_user_id)
);

CREATE TABLE pool_reference (
  book_id        uuid NOT NULL,
  owner_user_id  uuid NOT NULL,
  from_slot      text NOT NULL, from_member text NOT NULL, from_field text NOT NULL,
  to_slot        text NOT NULL, to_member   text,           -- NULL = DANGLING = an open row
  raised_by      uuid NOT NULL,                             -- the decision that created the need
  PRIMARY KEY (book_id, from_slot, from_member, from_field)
);
```

**`to_member IS NULL` is the entire cross-module mechanism.** `EPL-A8`'s *"progression adds a type to
the item enum"* is one row in `pool_reference` with a null target; the register abduces it; the loop
fills it; the row becomes non-null. No message passing, no per-module queue, no second protocol.

**Tenancy** follows the locked rules unchanged: every table carries `book_id` + `owner_user_id`, every
query filters on them, the slot **registry** is System-tier (code, admin-changed) while every
**member** is per-book — which is `EPL-A2`'s split landing exactly on the tenancy tiers.

---

## 6 — Implementation layout

```
crates/ruleset-core/src/pool/          REGISTRY + engine-side validation          (Rust)
services/lore-enrichment-service/app/pool/
  registry.py      loads contracts/pool/registry.json; typed SlotShape
  planners/        enumeration.py · ladder.py · profile.py · composite.py   ← the four, shared
  register.py      the abductive open-decision register                     (clingo, PPL-A8)
  loop.py          orchestration: rank → ask → resolve → validate → repeat
  store.py         pool_member / pool_reference repository
  freeze.py        content-address the pool; emit the digest                (PPB-A6)
contracts/pool/registry.json           GENERATED
```

Language split is the existing rule, not a new choice: **Rust** for the registry and the engine's own
validator (kernel-derived, and `PGN-A7` requires the engine to validate with its own code), **Python**
for the LLM loop (AI/LLM work), **clingo** in Python for the register.

**Per-module planner code: none.** A module contributes `slots/<module>.rs` and nothing else. If a
module ever needs bespoke planner logic, that is the signal a fifth `PlannerKind` is being discovered —
and it should be argued as one, not smuggled in as a module special case.

---

## 7 — What "it works" means, and it is falsifiable

The PO's bar: *prove it works, and the rest follow the pattern.* So the proof must exercise **the
pattern**, not item. Five claims, each with a way to be wrong:

| # | claim | proven by | falsified if |
|---|---|---|---|
| 1 | four kinds cover five slots | register item's 5, run the loop, no bespoke code | any slot needs a fifth kind or a special case |
| 2 | `Ladder` expansion is real leverage | one cited pattern answer → N members, one span | expansion needs a per-member answer anyway |
| 3 | **`EPL-A8` works** — cross-module demand | run progression's `Composite` → a `pool_reference` with `to_member IS NULL` on **item's** `instrument_tag` → the register surfaces it → the loop fills it | the demand never appears, or appears as a message rather than a null reference |
| 4 | registry has no mirror | edit a slot in Rust → regenerate → the drift test reds until Python re-reads | Python needs a hand edit |
| 5 | the loop converges | freeze with `pool_reference` having zero nulls | it does not terminate — **log demand-chain depth per round** ([`40.4` §3B.1](04_enum_pool.md)) |

**Claim 3 is the one worth running first.** It is the newest mechanism, it is the one with no prior
art in this repo, and if it fails the whole two-layer pipeline (`PPB-A6`) fails with it. Claims 1, 2
and 4 all have precedent — 4 is doc 39's fingerprint pattern, already working.

**Not proof:** filling item's pool by hand and declaring the shape sound. Every claim above has to fail
in a way someone can see.

---

## 8 — Open

1. **Is `Profile` really a kind, or is it `Enumeration` with a default?** It has one row and one
   question. Fold it and there are three kinds — cheaper, but the arity cap and the *"accept the
   engine default"* question are genuinely different. **Decide before writing the fourth file**; this
   is the kind of thing that is free now and expensive later.
2. **Where do `gamegen_*` tables get renamed?** They are named for a progression POC and are about to
   be the general decision layer. Renaming is cheap now and a migration later. Same class of decision
   as #1.
3. **Does `pool_reference` need a `kind` column?** A reference from a `Composite` field and a reference
   from a progression *condition leaf* may want different resolution. Unknown until claim 3 runs.
4. **What retires a member?** `QTY-A5` forbids ordinal reuse, and `status = superseded` exists — but
   nothing yet says what happens to references pointing at a superseded member. Doc 35 §6.3.1 records
   that **removal was the third kind of change and the first build order committed it**. Same trap,
   one layer up.
5. **`ItemClass` is engine-fixed with 8 variants, yet `item_archetype` members carry one.** If a
   reality's taxonomy does not fit the 8, the archetype planner has nowhere to put it — and the fix is
   a `PL_007` schema change, not a pool change. Worth confirming against a second genre before item is
   used as the proof.
