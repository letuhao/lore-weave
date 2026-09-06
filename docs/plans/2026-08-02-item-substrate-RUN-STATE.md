# RUN-STATE — Item data structure (DESIGN)

> **Read this file FIRST after any compaction**, then `git log --oneline -15`, then continue.
> Never re-derive a sealed decision (§4, §5) from memory — re-read it here.

**Started:** 2026-08-02 · **Branch:** `feat/game-logic` · **Base:** `50bff49a4` · **Size:** XL
(files=10 logic=14 side_effects=0 — `workflow-gate.sh size XL 10 14 0 30`)

**Phase:** CLARIFY → DESIGN → REVIEW → **STOP at the PO checkpoint.** No code this round.

**Companion round:** [`2026-08-02-actor-substrate-RUN-STATE.md`](2026-08-02-actor-substrate-RUN-STATE.md)
(`D-1`..`D-109`). This round **inherits** those decisions and may not re-open them. Where this round
finds one of them wrong *for items*, that is a finding to record, not a licence to re-decide.

---

## 1. What this round is

Design the **item and its data structure**. Item is **feature #2**, and the actor round named it by
name: `D-101` / `O-121` — *"the quantity substrate, ordinals, `granted`, the fold, phases 0-6,
`commit_with_modifiers`, the slot table and never-reuse are **engine**: **feature #2 (items) needs all
of them and needs no actor**."*

Item is also the substrate under every **ownership** feature — inventory, equipment, containers,
storage, loot, gifting, trade, crafting, group holdings. None of those can be designed until *what a
held thing IS* is settled, and today it is settled three incompatible ways across ~3 155 lines of
design and **0 lines of code**.

## 2. Standing invariants

1. **English in every persisted artifact** — docs, comments, commit messages, test names.
2. **No code this round.** The deliverable is a spec pair plus corrections to existing specs.
   The PO's standing direction from the actor round applies: *stub code and garbage cost a great deal
   to de-rot later* (`D-35` is the receipt — a 649-line stub misled that spec four times).
3. **Do not touch the data-ingest tier** — no glossary-service, knowledge-service, extraction, KG.
4. **Never `git add -A`; never `--no-verify`.**
5. **Rot is deleted, not layered over.** An outdated statement left standing next to a corrected one
   produces two answers to one question.
6. **Do not decide a sealed question again.** §4 is what is inherited; §5 is what is open.
7. **Measure, do not assert.** The actor round's single most repeated failure was declaring a thing
   missing or present without grepping for it (`D-41`: four consecutive rounds; `D-57`: the inverse;
   `D-85`: the claim asserted most confidently had no field behind it). **A presence claim about code
   must cite code.** Read the standards index → `contracts/<concern>/` → `dp-kernel/src/<concern>.rs`
   → *then* design (`D-42`).

## 3. What is IN and what is OUT

| IN | OUT |
|---|---|
| **What an item IS** — the definition/instance split, and the line between an instanced thing and a fungible quantity | **Trade · economy · auction · banking** — `D-22` handed these to a separate per-reality feature built from escrow and order books. This round designs the **transfer primitive** they will stand on, and stops there |
| **Ownership** — who may hold, where the edge lives, and what a holder is | **Crafting** — `14_crafting`, V2. This round owns *item birth* as a mechanism, not recipes |
| **The transfer primitive** — atomicity, conservation, what it emits | **Loot generation** — `COMB_004`'s reward rules. This round owns the seam only |
| **Stacking / quantity** on an instanced thing | **Combat vocabulary** (`D-14`) — reach, strike kinds, damage. The weapon's *seam* is in; the combat numbers are not |
| **How an item reaches an actor's numbers** — re-derived under `D-27` (a contribution is DATA, never CODE) | **Splitting engine core from the actor feature** (`C-3`) — a separate round. This round must not *deepen* the entanglement, and records where it touches it |
| **Item lifecycle** across the four axes, and disposal under `D-51` | **The trigger / generator mechanism** (`D-9`) — leave the hook, build nothing |
| **Provenance** — what the ledger owes vs what the row owes | Any implementation |
| **A rot sweep of the existing item corpus**, with the cost of each removal | |

## 4. Inherited and NOT re-openable — the actor round's decisions that bind this one

Pointers, not copies. Full text in the actor RUN-STATE §4.

| # | What it binds for items |
|---|---|
| `D-2` · `D-98` | The engine closes on **mechanism**, the manifest on **vocabulary** — and the discriminator is whether **the engine's arithmetic differs per member**. `ItemClass`'s 8 closed variants must survive that test or they are the item feature's vocabulary in costume. |
| `D-25` · §12.4 | **The edge is on the MANY side.** An actor owns an item ⇒ the edge is on the **item** (`EF_001` `LocationKind::HeldBy`). The actor has no `inventory` field and must never grow one. **This is already the item feature's property, decided in the actor round.** |
| `D-27` · `D-30` | **A contribution is DATA, never CODE.** A feature leaves `ModifierRow`s; the engine folds rows; the engine never calls a feature and never learns the word *"equipment"*. Adding item must touch **zero files** in actor core. |
| `D-28` · `D-50` | Staleness is **impossible, not detectable**: the modifier row is written and removed in the **same commit** as the feature row that justifies it, through `commit_with_modifiers(feature_row, modifiers)` — the engine is the sole writer of `modifier_rows`. |
| `D-29` | A conditional modifier's condition is a **declared threshold ordinal**, never a predicate grammar. |
| `D-15` | 31 actor-keyed aggregates are the **correct** decomposition. Only the `id` crosses a context boundary. |
| `D-23` · `D-51` | **Canon is what is written to the LEDGER.** A materialised row is a **fold over the ledger**; disposal is **cache eviction, not deletion**. |
| `D-76` | **Quantities are addressed by ORDINAL** (dense, inside the hashed bytes, never reused); **content is addressed by OPAQUE ID** (sparse, referential, validated by existence). **An item def is CONTENT.** |
| `D-74` · `D-75` | The manifest's structure is **ours**; the vocabulary is the author's. Four declaration kinds — **ROSTER · RELATION · TUNING · GEOMETRY**. A new feature declares a *member*, never adds a *field*. |
| `D-12` · §5.3 | Lifecycle states are **vocabulary**; the machine is **mechanism**. Lifecycle is **four axes** — tier · existence · residency · control — and **a movement on the residency axis must be INVISIBLE IN THE FICTION**. |
| `D-22` | A transfer is **island-local and face-to-face**. Remote trade is a different feature. A cross-island transfer is **refused by name**, and that is a boundary, not a limitation. |
| `D-105` · `C-2a` | `StatSlot` is two concepts sharing one array and is being dismantled. **Any item design that names `StatSlot` is building on a condemned structure.** |
| `D-101` · `C-3` | Engine core is entangled with the actor feature and is not split yet. Item must build against the **engine** half and say so explicitly wherever it cannot tell them apart. |

## 5. Open — the spec must answer these

| # | Question |
|---|---|
| **Q1** | **What IS an item**, and where exactly is the line between an *instanced thing* and a *fungible quantity*? `ITM-A2`'s representation rule (entity **or** resource row, never both) predates `D-7`'s unified quantity substrate and `D-10`'s opening of the stat slot set. Re-derive it or replace it. |
| **Q2** | **Who may HOLD?** Actor · cell · container · **and the group** — `D-93` left exactly this residue open (`O-118b`): *a sect treasury IS held by the group as such, and a faction is neither a place nor a person.* `ActorKind` has no `Group`. Decide whether a holder is an actor, or whether *holder* is a wider concept than *actor*. |
| **Q3** | **The transfer primitive** — what makes give/take atomic, what it emits, what conserves, and what makes item **duplication** unrepresentable rather than merely invalid. `D-22` bounds its reach; nothing states its shape. |
| **Q4** | **Stacking.** Is a stack of 50 arrows one entity with a count, or 50 entities? The answer decides whether the ownership edge is per-thing or per-quantum, and it is the same cardinality question `D-25` answered one level up. |
| **Q5** | **How an item reaches an actor's numbers.** `PL_007` §6.3 answers this with `impl EquipmentStats for World { fn equipped_modifiers(..) }` — **feature code the engine calls during resolution**, which is precisely the trap `D-27` / dataflow §13.1 names and closes. Re-derive equipment as rows. |
| **Q6** | **Item lifecycle across four axes.** `PL_007` §8.1 is written against `EF_001`'s single closed enum. Which item states are *existence* (fiction-visible vocabulary), which are *residency* (engine, invisible), what is an item's *tier*, and does an item have a *control* axis at all? |
| **Q7** | **Provenance.** `PL_007` §4.3 stores 3 fields on the row. Under `D-23` the ledger already holds the whole history. State what the row owes that the ledger does not, or delete the field. |
| **Q8** | **The rot list**, with the schema cost of each removal — which entries touch hashed bytes and therefore move every digest. |

## 6. Slice board — `[ ]` todo · `[~]` in flight · `[x]` done (needs evidence) · `P` parked

| # | Slice | Done when |
|---|---|---|
| `[x]` **S0** | This RUN-STATE | written; scope, inherited decisions and `Q1`–`Q8` recorded |
| `[x]` **S1** | **Prior-art sweep**, three directions — the ownership feature family · **group** ownership · provenance + transfer/duplication | **10 sources, each with what it settled AND what it did not** — dataflow §10. Two changed a decision: EVE's packaged/assembled produced `ITD-2` (and `IDR-1` records that the reasoning alone would have shipped the rot), Bethesda's owner-overrides-container produced `ITD-1` |
| `[x]` **S1b** | **Sandbox survey** (PO-requested) — Wurm · Space Engineers · ARK · Dual Universe · Eco · Ultima Online · Rust | dataflow §10.0. **6 of 7 separate owner from location**; the 7th (Rust) omits ownership *deliberately*, which is what turns `ITD-1` from a nicety into *the field that makes theft a concept*. Minecraft 1.20.5 ships `ITD-2` as a **load-time validator** (`max_stack_size > 1` may not combine with `max_damage`). Wurm's lossy creator signature **amends `IR-7`**. Opened `IO-11`..`IO-13` — three questions the design had not asked |
| `[x]` **S2** | **Corpus census** — every statement in the item corpus measured against `D-1`..`D-109` and against code | dataflow §11. **Every item symbol = 0 occurrences** in `crates/`+`contracts/`+`migrations/`; `EntityRef` = 21 hits and **all of them are a different `EntityRef`**; 0 of 113 registry types are game-tier |
| `[x]` **S3** | **Rot sweep** — `file:line` + `U`/`D` action for every contradicted statement | decision spec §9 — **30 rows** `IR-1..IR-30` across 5 files, each with a cost column. **Nothing is `⛓`**: no reality is pinned (`D-11`), so every entry costs a re-authoring pass at most |
| `[x]` **S4** | The decision spec — [`../specs/2026-08-02-item-data-structure.md`](../specs/2026-08-02-item-data-structure.md) | `Q1`–`Q8` answered as `ITD-1..ITD-9`; **4 escalated to the PO** as `IPO-1..IPO-4` rather than decided; `IA-1..IA-6` written for the red team by the author |
| `[x]` **S5** | The dataflow spec, **PART I** — [`../specs/2026-08-02-item-dataflow.md`](../specs/2026-08-02-item-dataflow.md) §0–§13 | reasoning, the 20-cell axis enumeration, the measured census, prior art with citations, register `IO-1..IO-13`, drift `IDR-1..IDR-3` |
| `[x]` **S5b** | **PART II — the specification proper**, §14–§19. *PO direction: finish the specification first; applying the rot sweep to the existing corpus comes after* | **§14** declaration surface — 2½ new tables, the rest reused · **§15** runtime shapes, quantum 32 B / instance 56 B, and `IPO-3`'s three container options · **§16** the **closed 12-operation set** + the conservation law · **§17** validator ladder V0/V1/V2, 19 checks · **§18** the 8 event types item must register · **§19** 9 acceptance criteria, **each with its bite-test and whether it is writable today** — 3 of 9 are |
| `[x]` **S6** | **Execute the sweep** — apply `IR-1..IR-30` to the 5 files | **26 staged files.** `PL_007` +394/−145 · `PL_007b` +63 · `PL_007c` +16 · `EF_001` · `06_item_contract`. Three new id namespaces (`ITD` · `IR` · `IO`) **registered in `00_foundation/06_id_catalog.md`** after design-lint refused them. Gates: `doc-language-gate --staged` **OK** · `design-lint --staged` **OK** (0 unregistered-prefix, 0 broken-link, 0 phantom-registration, 0 count-drift) · every reference to a deleted mechanism re-grepped and confirmed to survive **only inside dated history or an amendment note** |
| `[x]` **S7** | **Adjudicate the register** — a ruling for every open row | dataflow §20. **17 rows → 1 to the PO.** 9 decidable-and-decided · 4 unbuilt (`IO-3` · `IO-6` · `IO-10`, the last handed back to `T1-1`) · 1 downgraded (`IO-2`) · **two merges**: `IO-2`+`IO-11` were one decision seen from two sides, and `IPO-2`+`IO-4`+`IO-5`+`IA-1` were **one optional choice and its three consequences** |
| `[x]` **S8** | **Score against the BLIND wish corpus** — the 18 item expectations `D-90` filed, written before this design existed | dataflow §21. **✅ 2 · ⚠ 2 · ❌ 4 of 8** representative wishes. The four failures are **three causes**: the derived-magnitude arrow (`O-107`, **fifth** independent arrival) · **no `OnTime` trigger** (a gap in the *actor* round's surface that only an item exposes) · and **my own closed `InstanceStateSlot` set**, which fails `D-98`'s test — a reforge counter is arithmetically identical to `Charges`. Cost: **reading one table, no agents.** Opened `IO-14`..`IO-16` |
| `[~]` **S9** | PO checkpoint | design + sweep + adjudication + wish scoring presented. PO signs off or redirects. **STOP HERE — nothing committed.** |

**Gate evidence (S4+S5):** `doc-language-gate.py --staged` → *"OK — no non-English prose in lines added by
21 staged file(s)"* · `design-lint.py --staged` → *"OK — no findings"* (0 broken-link, 0 unregistered-prefix
— **note it scans only `docs/03_planning/LLM_MMO_RPG`, so it did not reach these two files**; their 7
relative links were resolved separately and all 7 exist) · no code touched, so no test suite applies.

## 7. Registers — append as you go

### 7.1 Decisions PROPOSED this round — **none is sealed until the PO signs off**

Full text in the decision spec. Listed here so a compaction cannot lose them.

| # | Decision | answers |
|---|---|---|
| **`ITD-1`** | **Ownership and location are two axes, and one field is answering both.** The gap between them *is* borrowed / stolen / stored / consigned / inherited. The corpus already split them — for cells only (`entity_binding.cell_owner` beside `location`, and `WSA-F4` calls that field *evidence* that the economy work reached past the closed enum). Bethesda arrives at the same split from outside, and names the consequence: **theft** | `Q2` |
| **`ITD-2`** | **Stackability is EARNED, not declared.** No per-instance state ⇒ a **quantum** `(owner, location, def_id, count)` with no row per unit. Acquire state ⇒ an **instance** with an id. EVE's packaged/assembled. This replaces `ITM-A2`'s author-picks-at-declaration rule, and dissolves the *"awkward middle"* `PL_007b` §2 deferred to `ITM-Q3`/`ITM-D1` | `Q1`, `Q4` |
| **`ITD-3`** | **The holder is wider than the actor** — `Owner ∈ {Actor · Place · Item · Group · None}`, and `None` is a value. **Closes `O-118b` without `ActorKind::Group`**: a group is never an actor, only ever the subject of an owner edge. The vocabulary already exists as `EF_001`'s `EntityRef` | `Q2` |
| **`ITD-4`** | **Equipment is ROWS; the `EquipmentStats` trait comes out.** `D-27`+`D-28`+`D-50`. Three documented defects **dissolve** rather than get fixed — the `blocked_by_primary` double-count, `equipment_version` monotonicity (`ITM-Q1`), and the item-side destroy cascade | `Q5` |
| **`ITD-5`** | **The single-place rule IS the anti-duplication mechanism** — label it, never weaken it for a cache. Converges exactly with OpenMU's post-mortem fix. And the dupe root cause it names — *timing of saving* — needs two writable copies of the truth; `D-36`+`D-23` leave one | `Q3` |
| **`ITD-6`** | A quantum transfer is a **two-delta**; an instance transfer is a **one-edge move**. Conservation is checkable for quanta, structural for instances | `Q3`, `Q4` |
| **`ITD-7`** | **Item has THREE axes; control is empty** — and that is evidence the four are orthogonal rather than a bundle. `ITM-C4`'s carefully-corrected contradiction **dissolves**: `Suspended` is residency, which is fiction-invisible by law | `Q6` |
| **`ITD-8`** | Item disposal is `D-51`'s, unchanged — **cache eviction, not deletion** | `Q6` |
| **`ITD-9`** | **Permissions are a pair-keyed RELATION and are NOT item core's** — item core owns the owner edge and stops. EVE's Query-vs-Take split and WoW's per-tab/per-rank + withdrawal limits + access log give the rights vocabulary to whoever builds it | `Q2` |
| **`ITD-10`** | **A def reference inside a runtime ROW is an INTERNED INDEX, and that index is a CACHE** — the ledger and the hashed bytes carry the opaque `def_id`; the index is rebuilt at load, never persisted, not stable across loads. `P-F` applied to a field. **Written down because an unwritten cache gets persisted** | `Q1` |
| **`ITD-12`** | **NO OWNERSHIP DEFAULTING.** The owner edge is explicit on every row; insertion never changes it, and ownership is **never resolved transitively**. Putting something in the sect vault does not make it the sect's — transferring it does. **The laundering hole closes by construction**; `IO-2` drops from 🔴 to minor (nothing walks the graph, so a cycle cannot loop); and `owner = None` inside a group vault stays a **findable** state rather than being silently consumed. It is the complaint EVE's players make — *"who owns the contents, the pilot or the corporation"* — and **the complexity IS the defaulting** | `Q2`, `Q3` |
| **`ITD-11`** | **The operation set is CLOSED at twelve, and every operation either CONSERVES or is a declared SOURCE/SINK.** `Σ count` per def becomes a property test that can red — **and duplication is exactly a violation of it.** Six operations a designer reaches for (*trade · loot · craft · repair · rename · cross-island transfer*) all decompose, which is the evidence the set is closed in the right place | `Q3` |

**`Q7` (provenance)** is answered inside `IR-7`: under `D-23` the ledger holds the history, so the row is a
**derived copy** and must carry `(reality_id, seq)` per `D-53` or be deleted. **`Q8` (the rot list)** is
decision spec §9 — 30 rows.

### 7.2 To the PO — **ALL FOUR NOW CLOSED (2026-08-02)**

**The last one was answered by the PO supplying a CRITERION rather than a choice**, and the criterion
produced three decisions the binary question could not have reached.

| # | |
|---|---|
| ✅ **`ITD-13`** | **DYNAMIC, ONE-WAY.** PO criterion: *we are building a **simulator of worlds**, not one game, so the answer depends on **the limit it places on extension**.* Applied, it **reversed my STATIC recommendation** (less surface ≠ more extensible: STATIC forces the author to choose *cheap bulk* XOR *the possibility of individuality*, per def, before knowing which things the fiction will make special — `ITM-A2`'s failure one level up). Then it **dissolved the trade-off**: the transition is **two directions**, and all four costs I charged to "dynamic" belong to **`repackage`**, which exists only to serve a market — `D-22`'s. ⇒ **`assemble` in, `repackage` out**, deferred with a named trigger. Closes `IPO-2` · `IO-4` · `IO-5` · `IA-1` |
| ✅ **`ITD-14`** | **BIRTH declares the shape; `instance_state` declares only the CAPACITY.** From the PO's second correction — *you cannot store 50 swords as one row; look at how Diablo stores it.* **My worked example was genre-wrong**: ARPG equipment is **born rolled**, so the 50-identical-swords population I priced does not exist there. Measured: D2's **simple vs non-simple item record** is a **per-row** compact-storage decision (our `state: StateRef = None`), and PoE's currency tab is `(kind, count)` **beside** per-row items. ⇒ Diablo's sword = capacity yes, **born instance**; a sect's mass-produced talisman = **born quantum**, assembled later; arrows = no capacity, always quantum. **Three genres, three behaviours, one mechanism** — and `ITD-13` stands with its justification **replaced**: not compressing identical swords, but *a class that is ordinary in bulk and occasionally becomes individual*, which is a world-simulation shape an ARPG does not have |
| ✅ **`ITD-15`** | **STACK MANAGEMENT is first-class** — PO: *some items have one stack, some are n stacks.* `max_stack` on the def. Taking it seriously **found a defect in this round's own rot sweep** (`IR-16` kept `PL_007b`'s bag-of-holding *"one slot regardless of amount"*, which a `max_stack` replaces) and **deleted three operations**: `merge` is what the **unique key** does, `split` is `move` with a **count**, and `repackage` was already gone. ⇒ **12 → 9 operations.** Correction: **storage and slots are different questions** — one row per key with unbounded `count`; **slots = `ceil(count / max_stack)`** |

<details><summary>The question as it was put, kept because the framing error is the lesson</summary>

| # | |
|---|---|
| ~~THE ONE LEFT~~ | **STATIC or DYNAMIC stacking.** Dataflow §14.4 took EVE's **dynamic** rule; adjudicating the register showed that choice was carrying **four open rows by itself** (`IPO-2` · `IO-4` · `IO-5` · `IA-1`), and all four vanish under Minecraft's **static** rule (`instance_state` non-empty ⇒ never stacks, checked at load). **Recommend STATIC** — 12 operations → 10, and the benefit the dynamic rule buys (bulk-identical **market** storage) belongs to **trade + economy**, which `D-22` handed away. Cost: 50 durability-bearing daggers are 50 rows (2.8 KB; 10 000 = 560 KB, materialised only when touched under `D-23`). ⚠ **This reverses my own §14.4**, on nothing but counting the rows that choice was carrying |
| ~~`IPO-1`~~ | ✅ **CLOSED by `D-84`** — the ownership split is a **reversal**, and *"take the reversal's decision now even if its code lands later"*. `D-11` supplies the window. ⚠ **It ships with its minimum consumer** — `V2-3`, operations `give`/`claim`/`release`, and the *what am I carrying that is not mine* query — **or it is a stored-and-never-read field, which is a defect**, not a feature |
| ~~`IPO-2`~~ | ✅ **ABSORBED** into the one question above |
| ~~`IPO-3`~~ | 🔁 **REFRAMED — and the measurement damaged the number I meant to borrow.** `TierCapacityCaps` = **0 occurrences in `crates/`**; its real shape is `max_major_tracked 20` / `max_minor_tracked 100` / **`Untracked unlimited`**; and it caps **AI attention**, not state. ⇒ **`D-94`'s *"hard stateful population cap is 120"* is a cap over a DIFFERENT LADDER** — the exact conflation `D-21` retired the word *tier* to prevent, committed inside a decision that used it to close a layout question. **Recorded, NOT re-opened** (invariant 6). What replaces it is better than the question: adopt the **mechanism** — authored cap · engine defaults · overflow **defers, never drops** (`DL-D6`) — and `D-94`'s own revisit trigger (*a stateful cap above ~10 000*) becomes the layout **decision rule** instead of a coin toss |
| ~~`IPO-4`~~ | ✅ **CLOSED with `IPO-1`** — one line, already reserved as `EF_001`'s `EntityRef::Faction`, and `ITD-3` established that a group is only ever the **subject** of an owner edge, so no `ActorKind` change |

</details>

> **What this exchange demonstrates, recorded because it is the round's most useful process finding.** I
> put a **binary** to the PO. The PO did not pick a side — they said the question was unclear, supplied
> the **criterion** (*a world simulator's answer depends on the limit it places on extension*), and then
> corrected the **example** the whole cost argument rested on. That produced `ITD-13`, `ITD-14` and
> `ITD-15`, **none of which was reachable from either branch of the binary**, plus a defect in this
> round's own sweep. **A binary put to a PO is usually a sign the question has not been decomposed far
> enough** — and the tell was that neither branch could express the case that actually mattered.

### 7.3 Parked

| # | |
|---|---|
| `IP-1` | **`ITD-9`'s permission relation** → the social / faction feature, with EVE + WoW's rights vocabulary attached. Handoff, not a deferral (defer-gate #1) |
| `IP-2` | **`bound_to` / soulbinding** (`IO-8`) → trade + economy per `D-22`; it is an economy lever, and its home on the owner axis is stated |

### 7.4 Debt

| # | |
|---|---|
**Adjudicated 2026-08-02 (dataflow §20) — 13 rows → 3 unbuilt + 1 downgraded. The rest are closed.**

| # | |
|---|---|
| `IO-14` | **🔴 `InstanceStateSlot` is closed at six and fails `D-98`'s OWN test** — a reforge counter is arithmetically identical to `Charges`, so a seventh variant would be treated uniformly, which is the definition of *vocabulary in costume*. **Fix is not the reflex one** (`D-109`: opening a god-list removes the compiler's ability to notice): a closed set of storage **KINDS** with an author-declared **member roster** on top — `D-75`'s three columns one level down. **I applied that pattern to `item_classes` in the same section and missed it here** |
| `IO-15` | **Items have no STATUS axis, and a blind author needed one** — a poison coating is temporary, runtime-granted, expiring, source-tagged: exactly `status_active`'s shape on the actor. `ITD-7` celebrated the empty *control* axis as evidence of orthogonality; **the absence worth examining may have been a different one.** Cheap candidate answer: a `ModifierRow` targeting the wielder with the weapon as `source` — free, and possibly the whole thing |
| `IO-16` | **`TransitionDecl.trigger` has no `OnTime`** — a keycard expires on a date, an actor rarely does. **A gap in the ACTOR round's declaration surface, exposed only by an item wish.** Handed back with its evidence |
| `IO-3` | **C — unbuilt, bite-test DATED.** `ITD-5`'s no-save-step claim stays unfalsifiable until something writes an item. **Trigger: the first item write.** Test: attempt a second location write in a different transaction, require refusal |
| `IO-6` | **C — unbuilt.** `InContainer(item)` and `SPG-A1`'s `SpaceNode.holder` are one edge from two sides; the check owed is that every operation one defines has a home in the other. A reading pass, not a decision |
| `IO-10` | **C — and it belongs to `T1-1`, not here.** Measured: **0 of 113** registry types are game-tier, for **any** feature. Handed back to the actor round's work item, one size larger than filed |
| `IO-2` | ⚠ **DOWNGRADED to minor by `ITD-12`** — with no transitive resolution nothing walks the graph, so a cycle is nonsense fiction rather than an unbounded loop; `V2-4` stays as a cheap bounded check. *Original hazard, kept because it is real:* the ownership edge is a **reference** edge and escapes `DP-Ch1`'s containment guard, exactly as `SPG-A5b` warned |
| ~~`IO-1`~~ | ✅ **CLOSED** — ours renames to `OwnerRef`; `dp-kernel`'s `EntityRef` keeps the name it already has call sites for |
| ~~`IO-4`~~ · ~~`IO-5`~~ | ✅ **die with the dynamic rule** if §7.2's one question takes STATIC — a quantum def with no `instance_state` has no unbounded delta and no provenance to merge away |
| ~~`IO-7`~~ · ~~`IO-8`~~ | ✅ **CLOSED** by `ContainerDecl.max_depth` (the `NV-2` restriction becomes an authored number, so the guard becomes reachable) and by `OwnershipDecl.binds_on` (soulbinding is a **non-transferability predicate on the owner axis**) |
| ~~`IO-9`~~ | ✅ **CLOSED — `D-24`'s test DOES apply.** A treasury without permissions is **a shared chest**: the substrate does not break, the fiction is flatter — the same shape as flatter NPCs. What item core owes the receiving feature is one hook, already in the ladder: `V2-3` delegates the group check at commit |
| ~~`IO-11`~~ | ✅ **CLOSED by `ITD-12`** — merged with `IO-2`; they were one decision seen from two sides |
| ~~`IO-12`~~ | ✅ **CLOSED — different axes, and they must never share a word.** **Eviction** is residency: engine, fiction-**invisible**, always safe. **Decay** is an existence transition: declared, fiction-**visible**, a real event. UO's *"locked down items do not decay"* is an **owner-side flag a declared transition's precondition reads** — no new mechanism. The invisibility law is the discriminator, for the fourth time |
| ~~`IO-13`~~ | ✅ **CLOSED — the key is `(actor-or-group, entity) → rights`.** ARK's per-structure rank slider and Dual Universe's per-element Tags both go finer than a container, so **the container is the common case, not the schema**. Handed to the social feature with the measured rights vocabulary: `view` / `deposit` / `withdraw`, with a **rate limit on withdraw** |
| `IO-12` | **`ITD-8`'s eviction must not absorb an authored DECAY rule** — UO's lockdown pins an item against decay *and* movement. Eviction is invisible and always safe; decay is neither |
| `IO-13` | **`ITD-9`'s permission key may be too coarse** — filed as `(group, container, rank)` from EVE/WoW; **ARK and Dual Universe both go per-item** |

### 7.5 Drift — near-misses, recorded because **a run that ends with an empty drift log is dishonest**

| # | |
|---|---|
| `IDR-1` | **I nearly wrote `ITD-2` as `stackable: bool`** — `ITM-A2` respelled, failing `D-98` identically. Prior art, not the reasoning, produced the right answer. Skipping the search would have shipped the rot this round exists to remove |
| `IDR-2` | **The first census `bash` loop timed out and returned WRONG counts** (`HeldBy 6`, `InContainer 100` — it was walking vendored trees). One sentence from writing *"`HeldBy` has 6 occurrences in code."* True count: **0**. `D-85`'s exact shape, caught because the number looked implausible, **not** because the method was sound |
| `IDR-3` | **I wrote *"L1 retention: inherited"*** before noticing an heirloom outlives every actor who held it, which makes ledger truncation **worse** for items, not equal. `D-42`'s corollary: a spec silent about a solved problem reads exactly like one with an unsolved problem — here it would have read *solved* while being *worse* |
| `IDR-4` | **The language gate caught me pasting a verbatim Vietnamese PO quote into this file** — *"an English document with Vietnamese fragments pasted through it… most often a verbatim PO quote dropped into a design doc"*, which is the exact example CLAUDE.md uses to define the rule. Fixed by quoting the **meaning** in English. **Recorded because the mechanism caught it and I did not** — and because it landed in the register whose subject is intent-versus-mechanism |
| `IDR-6` | **`design-lint` refused the sweep with 77 findings — I introduced THREE new id namespaces (`ITD` · `IR` · `IO`) into the planning corpus without registering them.** The track has an id catalog and a gate that enforces it; I cited 56 `IR-*` ids across five locked design docs and registered none. **Fixed by registering all three.** Recorded because it is the same shape as the round's own subject matter: *intent is not a mechanism* — I intended the ids to be traceable, and the only reason they are is that a script refused the commit |
| `IDR-7` | **🔴 Deleting a SECTION does not delete its CITATIONS, and three of the survivors were live claims.** After replacing `PL_007` §6.3 wholesale, `grep` found **11 more** references to `EquipmentStats`/`equipment_version` in the same file and **5** in siblings. Most were history and correctly stay — but `PL_007b`:252 still asserted the invalidation rule, `PL_007c` §12.5 still told DF07 it *"needs no change to accept it"*, and `ITM-Q1` was still an **open deferral with a watched trigger** for a mechanism that no longer exists. **A wholesale section replacement reads as complete and is not.** Found by grepping the deleted symbols afterwards, not by the edit — and that grep should be a step in every sweep, not a habit |
| `IDR-8` | **🔴 `IDR-5` HAPPENED AGAIN, worse, one hour later — and this time it destroyed the file.** A Python edit script opened this RUN-STATE with `io.open(p, "w")` — which **truncates immediately** — then raised `UnicodeEncodeError` on a lone surrogate before writing a byte. **174 lines → 0.** Worse, the shell's `&&` did not short-circuit, so the failed result was `git add`ed over the good index entry, destroying the recovery path I would have reached for. **Recovered from a dangling git blob** (`git fsck --unreachable` → `git cat-file`), which worked only because every earlier `git add` had left one. **The lesson `IDR-5` recorded was "verify the tail, not the exit code" — and I recorded it, then wrote three more scripts with the same shape.** The actual fix is mechanical, not attentional: **write to a temp path and rename**, or use the file-edit tool, which cannot truncate on failure. *Intent is not a mechanism* — recorded for the third time this round, and the third time it was me |
| `IDR-5` | **A `cat` heredoc appending §14–§19 was silently truncated mid-sentence** (`warning: here-document delimited by end-of-file`) and left a half-written `ContainerDecl` block in the committed-to-disk file. Caught by `wc -l` + `tail`, not by the write succeeding. **A shell append that half-succeeds looks exactly like one that succeeded** — the fix was to write via the file tool and splice with `head`, and the lesson is to verify a generated file's *tail*, not its exit code |
