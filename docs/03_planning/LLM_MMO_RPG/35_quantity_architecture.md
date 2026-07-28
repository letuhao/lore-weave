# 35 — Quantity architecture: the four layers, and what is allowed to grow

> **Status:** DESIGN 2026-07-28, **revised the same day after an adversarial red-team round**.
> Governs **which quantities exist**, who may add one, and what it costs.
> Axioms `QTY-A1..A14`, decisions `QTY-D1..D13`, open `QTY-Q5..Q11` (`Q1..Q4` closed — §13.1).
>
> ⚠️ **`QTY-A6` was REVERSED by the red team** — per-reality array width is out; fixed width with
> declared identities inside it is in. **§4.2 is the section to read first**, and §10 records
> everything the round killed, including three of this document's own miscitations.
> **Prefix `QTY` registered** in [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md).
>
> Written after the PO stopped the F-track build with: *"tôi nghi ngờ thiết kế của lore weave ban đầu
> có vấn đề chỗ này … giờ hãy dừng build và update spec, lấy điểm mạnh của chaos vào spec của chúng ta
> và loại điểm yếu của nó."*
>
> **Evidence base:** four cold-start sub-agent audits run 2026-07-28 — two over
> `chaos-backend-service` / `chaos-actor-module` (the RUST rebuild), one over this repo's shipped
> `ruleset-core` / `ruleset-loader` / `commit-service`, one adversarial over the design corpus. Every
> claim below carries its `path:line`. The adversarial pass **refuted three of four planks** of the
> position this document replaces; §10 records what it killed.
>
> **This document supersedes [XST-R6](27_extensibility_stress_test.md) and revises
> [WSA-R02](31_world_simulation_architecture.md).** Both proposed opening the `StatSlot` set. That is
> the wrong fix — **§10.5** says why, and **§3.1** gives the replacement.

---

## 0. The question this answers

> *"Kiến trúc mới có thể implement toàn bộ [luyện khí · luyện thể · ma pháp · kinh nghiệm thăng cấp ·
> mị ma song tu · ngự khí · ngự thú] mà không phải đập đi xây lại kiến trúc hay phải sửa rất nhiều
> code nếu nhét thêm hệ thống mới?"* — and its sharper follow-up: *"derived stats vẫn phải hard code
> … nhưng chúng phải có khả năng mở rộng, chứ không phải định nghĩa derived xong rồi không thêm mới
> được."*

Both halves are load-bearing and they pull in opposite directions. This document holds them apart by
putting them on **different layers with different costs**.

---

## 1. QTY-F1 — the finding: LoreWeave has L0 and L1 and nothing else

The code audit is unambiguous. `StatSlot` is ten variants closed in the binary
(`crates/ruleset-core/src/slots.rs:25-46`) and **all ten are derived combat outputs** — `MaxHp`,
`MaxStamina`, `StrikePower`, `Armor`, `Accuracy`, `Dodge`, `CritChance`, `CritMult`, `Speed`,
`MoveRange`. There is no `Strength`, no `Qi`, no `Intelligence`.

The entire authorable surface is `RulesetPatch` — 20 optional fields
(`crates/ruleset-loader/src/patch.rs:31-47`, `:145-155`) — and **every one of the 20 is a number**.
`Ruleset` holds no collection at all; the loader's own header states it
(`crates/ruleset-loader/src/lib.rs:21-25`).

Three consequences, all verified against code rather than inferred:

* **The `primary → derived` arrow does not exist.** `melee_archetype: [i32; SLOT_COUNT]`
  (`patch.rs:154`) lets an author write derived values *directly*. That is why
  `ModifierSource::Progression` exists as a label (`services/commit-service/src/stats.rs:116`) and is
  passed an **empty slice** in the one production call site
  (`services/commit-service/src/combat.rs:145`) — there is nothing for it to carry.
* **Pools are conflated with stats.** `MaxHp`/`MaxStamina` are the *ceiling of a container*, filed in
  the same dense array as `Accuracy`. [27 §5](27_extensibility_stress_test.md) already caught this:
  *"'Project into 10 slots' is true for derived quantities and false for pools. A pool is not a
  projection target — it is a container with a max, a current, a regen and a zero-behaviour."*
* **Elements do not exist.** `elem_mult_pm` is one global `i64` multiplied into **every** attack
  (`crates/ruleset-core/src/combat.rs:41`, applied at `services/commit-service/src/combat.rs:294`).
  A ruleset can say *"all damage is ×1.3"*. It cannot say *"fire beats wood"*.

**So a qi-cultivation reality and a mana-magic reality on the same binary are the same ten slots with
different integers in them.** The engine supports differently-*tuned* instances of exactly one
progression system.

### 1.1 And the growth path out of it is currently a spine break

Moving `SLOT_COUNT` today costs ~13 sites across 6 source files — and worse:

| Site | What happens |
|---|---|
| `crates/ruleset-core/src/canon.rs:213-226` | `LengthMismatch` — **every stored `.canon` stops decoding** |
| `crates/ruleset-loader/src/store.rs:142` | ⇒ `StoreError::Malformed` ⇒ every reality `Unloadable` |
| `crates/ruleset-core/src/ruleset.rs:96-101` | forces a `RULESET_SCHEMA_VERSION` bump that refuses old artifacts |
| `crates/ruleset-core/tests/digest.rs:41-51` | golden digest reds with **no legal repin** under digest-pinned replay |
| `upcaster.rs` | versions **event** schemas, not **rules** — [27 §11.6](27_extensibility_stress_test.md) records *"there is no migration story"* |

> **QTY-F1.** LoreWeave is ~13 sites into becoming the exact god class `chaos-backend-service` was
> rebuilt to escape — *"Mỗi khi thêm system mới phải sửa class này!"*
> (`chaos-backend-service/docs/actor-core/ACTOR_PERFORMANCE_ANALYSIS.md:60-61`), diagnosed there as
> *"Quá nhiều systems → God Class quá lớn / **Không thể biết trước tất cả systems**"*
> (`crates/actor-core/docs/PLUGIN_ARCHITECTURE_FOR_GOD_CLASS.md:13-18`).
> **The difference: chaos lost one struct. We would lose the digest/replay spine.**

---

## 2. QTY-A1 — the line, stated correctly

The prior framing was *"code owns SHAPE, config owns VALUES"* ([IMP-A1](26_implementation_architecture.md)).
True, and too coarse to decide the cases that matter. The chaos audit found a sharper cut, drawn in
that codebase's *data* and not in its prose:

> **QTY-A1 — ARITHMETIC is code. ARRANGEMENT is data.**
>
> The operators, the formulas, the law chain, the order of the four damage steps: **code**.
> The order things combine in, the clamps, the caps, the priorities, the weights, the identity and
> metadata of a quantity: **data**.

Evidence that this is the real line and not a restatement: chaos declares per-dimension `bucket_order`
and `clamp {min,max}` in `crates/actor-core/configs/combiner.yaml:4-39` while the arithmetic itself is
a `match` on `Bucket` in `src/bucket_processor/mod.rs:115-155`; and predicates are declared data
(`ConditionConfig {function_name, operator, value, parameters}`,
`crates/condition-core/src/types.rs:32-39`) dispatched through a registry of **Rust-implemented**
functions (`src/resolver.rs:10-11`).

**This is why chaos needs no expression parser, no eval, no sandbox — and neither do we.** Designers
compose *arrangements*; engineers own *arithmetic*. It is the single most reusable decision in that
codebase and we do not currently have it.

---

## 3. QTY-A2 — the four layers

> **QTY-A2.** Every quantity in the game belongs to exactly one layer. The layer determines **who may
> add one** and **what adding one costs**.

| | Layer | Contents | Who may add | Cost of adding |
|---|---|---|---|---|
| **L0** | **Laws** | the damage chain, initiative, regen, defeat — the arithmetic | engineers | engine release **+ §6.2** |
| **L1** | **Roles + derived** | the names laws bind to; the closed dense output block | engineers | engine release **+ §6.1** (bounded, auditable) |
| **L2** | **Declared quantities** | primary stats · resources/pools · elements · tags | **authors, in the ruleset** | a ruleset edit ⇒ new digest ⇒ epoch switch. **No engine release.** |
| **L3** | **Sources** | progression/cultivation systems that contribute into L1/L2 | engineers (a trait impl) | a new module; **zero core edits** |

L2 is the layer that does not exist today. L3 exists only as an unfilled label.

### 3.1 QTY-A3 — laws bind to ROLES, not to quantities

This is the axiom the whole design turns on, and it is what the earlier "closed head + open tail of
slots" proposal got wrong.

> **QTY-A3.** A role is the binding between a **closed law** and a **declared (L2) quantity**. Where a
> law must read something whose *identity* is authored, it names a **role**; the ruleset binds one of
> its declared quantities to that role. The role set is closed in the binary; the quantity set is not.
>
> **A law reading an L1 derived slot needs no role** — the slot is already a closed, stable name.
> Roles exist only at the L1↔L2 boundary.

Concretely: `evaluate_outcome` does not read `hp`. It reads the quantity bound to role `Vital`, and
tests it against role `Vital`'s zero-behaviour. But `resolve_attack` reads slot `StrikePower`
**directly**, because that slot is closed and the ruleset has nothing else to put there.

> **Review note (self-review, same session).** The first draft of this section gave roles to
> `StrikePower`/`Armor`/`Speed`/`MoveRange` as well. That was **indirection with no consumer** — an
> author cannot rebind a closed derived slot to anything, so the role added a layer and bought
> nothing. It is the same defect this repo has refused twice before (a `Manifest` with no resolver;
> `Canon::u64` with no caller), and it is recorded rather than silently deleted because *"a shape with
> no consumer"* is a recurring failure mode here, not a one-off.

* A wuxia reality binds `Vital → hp`.
* A cultivation reality where dispersing your core is death binds `Vital → qi`.
* Both run the **same compiled law**, with no engine release and no new slot.

**This is not invented here.** It is the cultivation stress-test agent's own S6, which this document's
predecessor misread as an objection: *"The behaviors stay closed; only the **identity** opens"*
(`27a_stress_test_agent_reports.md:739`). That agent objected to author-declared **stat slots**
(`27a:730`, `27a:747`) and simultaneously proposed author-declared **pool identity**. Both positions
are correct and this axiom is where they meet.

Roles are few, stable, and each one exists because a specific law needs it. The V1 role set is
`QTY-D1` (§4.3). A role is added the same way a law is: an engine release.

---

## 4. L2 — the declared layer

### 4.1 QTY-A4 — a pool is not a stat

> **QTY-A4.** A **resource** is `{ current, max, min, base, regen_rate, regen_type, zero_behaviour,
> deps, tags }`. Its **current** is actor state. Its **max** is a derived value. Everything else is a
> **declared row**, not a slot.

chaos gets this exactly right and it is worth copying wholesale: the actor holds only the current
scalar (`crates/actor-core/src/types.rs:26,28` — `core_resources: [f64; 9]` plus a `custom_resources`
overflow map, described as a deliberate hybrid at `src/constants/resource_indices.rs:1-11`), while
identity, bounds and regen policy live on a registry row
(`ResourceDefinition`, `src/runtime_registry/resource_registry.rs:15-31`) declared in YAML.

**Adding a pool is therefore a declared row, not a `SLOT_COUNT` change.** That alone removes the
single most likely spine-breaking event the adversarial audit identified.

### 4.2 QTY-A5..A6 — ordinals and width

> **QTY-A5 — ordinals are ASSIGNED, never authored; monotonic; never reused on removal; and the
> assignment table is INSIDE the hashed ruleset.**

The first three clauses are chaos's (`crates/element-core/src/unified_registry/unified_element_registry.rs:114-117`
assigns by `AtomicUsize::fetch_add`; `:133-134` drops without reuse). The fourth is ours and it fixes
chaos's one real defect here: chaos derives ordinals from a **`sort()` over whatever configs are
present** (`src/config/elemental_config_loader.rs:77-79`), so **adding one element YAML renumbers
every element after it** — reproducible for one snapshot, not stable across edits, with no persisted
id→ordinal map anywhere. Putting the table in the hashed bytes makes an ordinal shift a *different
ruleset with a different digest*, which the existing early-binding machinery already refuses to apply
to a live reality (`crates/ruleset-loader/src/binding.rs:142-159`).

> **QTY-A6 — the ARRAY WIDTH is a compile-time constant. The IDENTITIES inside it are declared per
> reality and pinned by the digest.** A reality uses a prefix `0..n` of a fixed `N`; `n` is in the
> hashed bytes, `N` is in the binary.

### ⚠️ A6 was REVERSED by red team, 2026-07-28 — read this before quoting the old form

The first draft of A6 said *"array width is a **per-reality** constant, not a compile-time cap"* and
called it *"the one place the LoreWeave architecture is genuinely ahead."* **Three independent red-team
agents killed it, on three separate grounds. It was wrong.**

1. **A6 and [QTY-A12](#64-qty-a12--the-memory-budget-is-an-assertion) were mutually exclusive.** A
   runtime width forces `Box<[i32]>`/`Vec`, and `size_of::<Box<[i32]>>()` is **16 bytes for n = 3 and
   for n = 500, on every target, forever.** The `const` assertion A12 demands would compile, always
   pass, and **never be able to fire** — precisely the vacuity §10.2 uses to discredit the 1.08 %
   benchmark. The document took chaos's discipline while removing chaos's precondition for it
   (`MAX_ELEMENTS = 50`) in adjacent sections, without noticing.
2. **It is probably not implementable here.** The const-generic escape — `Ruleset<const N>` ⇒
   `CombatDomain<N>` ⇒ `Island<CombatDomain<N>>` — dies at the manager, which is monomorphic:
   `Managed { island: Island<CombatDomain> }` in a `BTreeMap<i64, Managed>`
   (`services/commit-service/src/manager.rs:56-57,72`). `Domain` is **not object-safe** (associated
   types + `Self`-typed methods), so there is no `Box<dyn>` escape. Const-generic ⇒ **one width per
   binary**, which is the compile-time cap A6 claimed to refuse.
3. **Its benefit does not exist at our scale.** A6's entire case was chaos's 41.5 KiB/actor — a figure
   driven by `f64` **and** a per-actor `n²` matrix, **neither of which we would copy** (see A6.1).
   Measured on the real structs: `Actor` is **192 B** today; at a fixed `[i32; 32]` it is ≈ **280 B**,
   at `[i32; 64]` ≈ **408 B**. Ten thousand resident actors at the widest option cost **+2.2 MB total**.
   84 % of 408 B is 343 B. The waste A6 existed to prevent is a rounding error.

**What survives, and it is most of the value:** identity is still author-declared, ordinals are still
assigned and pinned inside the hashed bytes ([QTY-A5](#42-qty-a5a6--ordinals-and-width)), iteration is
still dense `0..n`, and a five-phase wuxing reality still *uses* five. It simply does so inside a fixed
`N` rather than by resizing the array. Density — the property the ARPG stress-test agent required
(*"survives only if `ElementId` is engine-closed and small"*, `27a:274`) — is preserved, and now it is
preserved in the binary too, which is what that agent actually asked for.

**And one property is gained that A6 did not have:** `size_of::<Actor>()` stays a compile-time
constant, so A12 becomes a check that can bite. That is the whole reason for the reversal.

### A6.1 — the scoping rule A6's first draft omitted, which was the real lesson from chaos

> **`O(n)` per ACTOR. `O(n²)` per RULESET.**

Doc 35's first draft answered chaos's 41.5 KiB by shrinking `n` and **never said where the interaction
matrix lives** — which is the half that actually cost chaos the memory: `[[f64;50];50]` = 20,000 B
**inline on every actor** (`crates/element-core/src/core/elemental_data.rs:594`), 47 % of the struct.
Shrinking `n` alone would have reproduced that bug at n = 50 under a new axiom number.

Per actor: the `O(n)` affinity/resist vector. Per ruleset: the `O(n²)` element-vs-element table, which
is a property of the *world*, identical for every actor in it, reached through the `&rules` reference
`apply` already holds — exactly where its predecessor `elem_mult_pm` lives today
(`crates/ruleset-core/src/combat.rs:41`, read at `services/commit-service/src/combat.rs:294`).
At n = 12 that is 576 B **once**, not 576 B × every actor.

### 4.3 QTY-D1 — the V1 role set (closed, and deliberately tiny)

| Role | Bound to | Law that reads it | Why it needs a role |
|---|---|---|---|
| `Vital` | an L2 resource | defeat / `evaluate_outcome` | **cardinality — see below.** It is the only law input that requires exactly one answer and cannot degrade if it gets zero |

**ONE role. `Effort` was cut — `QTY-D12`.** An action's cost is *content*: `ABL_001` already ships
`costs: Vec<AbilityCost>` where each cost **names its own pool** (`ABL_001:140-141,161`), so admission
iterates a declared list and asks "≥ amount?" of each named quantity. No law ever needs *"the"* cost
pool. Every candidate consumer was checked and each is served by a declared property, not a role: regen
by `RegenRule` per vital (`RES_001:308-316`), exhaustion by `OnZeroEffect` per vital (`RES_001:604`),
AI affordability by the pre-filtered usable set (`ABL_001:582`), UI by `display_priority`
(`RES_001:139`). And `Vec<AbilityCost>` is decisive on its own: **an ability may declare many costs**,
so "the cost pool" was already contradicted by the shipped design's shape.

> **Why `Vital` survives the identical argument — and this must be written down, because without it
> the next reviewer deletes `Vital` too and is locally correct.**
>
> The red team's strongest attack was that `OnZeroEffect` is *already* a declared per-pool row
> (`RES_001:604`), so a reality that wants qi-dispersal to be death just sets that flag — and `Vital`
> is then indirection with no consumer, exactly the defect §3.1 records.
>
> The answer is **cardinality, not world-choice.** Both `Vital` and `Effort` are world decisions; only
> `Vital` needs a *totality* guarantee. `evaluate_outcome` requires **exactly one** answer to *"whose
> exhaustion ends this"*. A role is a total function role→quantity. A declared flag is a predicate
> satisfiable **0 or N times** — and **N = 0 is a silently unlosable world**, which no test would
> catch. That asymmetry is the whole reason one role survives and the other does not.
>
> **The cheaper alternative, considered and rejected:** a loader validator asserting *"exactly one
> declared pool carries `EmitMortalityTrigger`"* buys the same guarantee, and
> `crates/ruleset-loader/src/validate.rs` is where it would go. Rejected because a validator is a
> runtime refusal while a role is a type-level total function, and doc 16's discipline prefers
> structural over procedural. It is a close call and it is recorded so it is not re-litigated blind.

**One role, not six.** Every other law input is an L1 derived slot the law names directly
(`resolve_attack` reads `StrikePower`, `Armor`, `Accuracy`, `Dodge`, `CritChance`, `CritMult`;
initiative reads `Speed`; movement derives `MoveRange`). Those need no indirection — see the review
note in §3.1.

The rule for adding a role: **a role is justified only when a ruleset would legitimately bind a
different quantity to it.** If the answer is always the same slot, it is not a role.

`QTY-Q1` asks whether `Effort` should be plural (a world with both stamina and qi costs). A third
role, `DamageAffinity`, is the likely arrival with `Q3` (elements) and is not being reserved in
advance — reserving a role with no consumer is the defect §3.1 records.

### 4.4 QTY-A7 — one representation per quantity

> **QTY-A7.** A quantity has exactly one home. A second read path for the same value is a defect, not
> a convenience.

chaos violates this and it is instructive: a resource lives in **three** places simultaneously — the
typed array (`types.rs:26`), the `custom_resources` map (`:28`), and an untyped
`actor.data["hp_current"]` blob that the regeneration subsystem actually reads
(`src/subsystems/resource_management/resource_regeneration.rs:354-365`). The same disease appears in
its ceilings: the array says 50 (`elemental_data.rs:22`), the config says 50
(`registry_config.rs:200`), the registration path says **1000**
(`unified_element_registry.rs:103`) — so registration and storage disagree and element 51 panics on
an unchecked write (`src/factory/elemental_factory.rs:560-570`).

### 4.5 QTY-A14 — an ordinal never travels without its digest

> **QTY-A14.** An L2 ordinal is meaningless without `(reality_id, ruleset_digest)`. **Any datum that
> leaves the island carrying an ordinal MUST carry the digest that gives it meaning.** A consumer that
> cannot resolve the digest must refuse the datum, never guess.

Added after the red team walked the concrete failure, which is worth stating in full because it fails
*silently* and would be permanent:

> Reality A declares ordinal 3 = `qi`. Reality B declares ordinal 3 = `mana`. A player acquires a
> sword in A; the item event commits with `ruleset_digest = D_A` and a modifier keyed by ordinal 3.
> The row lands in B's `pc_inventory_projection` with `origin_reality_id = A` and the bare integer in
> `metadata` (`contracts/migrations/per_reality/0006_projections.up.sql:112-127`). B resolves ordinal
> 3 against **its own** table and the sword now grants mana. **Nothing fails**: no digest mismatch
> (nothing compares), no validator (`DF7-V2` only checks kinds resolve *within* the local
> declaration — and 3 does resolve), no length error (`canon.rs:213-226` guards width, not meaning).
> It is a wrong number in a committed, digest-pinned, replayable log — reproducible forever, and
> undetectable because **both realities replay it "correctly."**

**There is a live code defect on this path today, independent of L2:** the publisher's SELECT does not
include `ruleset_digest` (`services/publisher/pkg/pgsource/pgsource.go:56-72`) while the envelope
field is `omitempty` (`contracts/events/envelope.go:57`) — so **the pin is dropped the moment an event
leaves its reality DB, invisibly.** Tracked as `D-PUBLISHER-DROPS-RULESET-PIN`. It must be fixed before
`Q1`, because L2 is what makes the loss consequential.

**Note the collision with a LOCKED axiom, deliberately not resolved here.** RLS-A6 states that
identical strings across realities are **unrelated by design** (`16:296-298`). So a *global* quantity
vocabulary — which would dissolve this whole class — is not available; cross-reality transfer needs an
explicit **per-reality-pair mapping** with a declared behaviour for unmapped quantities (drop / refuse
travel / quarantine). `PROG_001`'s current behaviour is a **silent drop** (`PROG_001:932,963`), which
is a defect, not a policy. This is `QTY-Q5` and it retires the reasoning behind `DF7-D12`.

### 4.6 QTY-D9 — the tenancy tier of a declared quantity

Required by CLAUDE.md's User Boundaries rules, and absent from the first draft — which contained zero
occurrences of *owner*, *user*, *tenant* or *scope key*.

| | |
|---|---|
| **Tier** | **Per-reality.** A declared quantity set belongs to the reality, and its scope key is `reality_id` — inherited transitively because the declarations live *inside the hashed ruleset*, which a reality is bound to once (RLS-A3). |
| **Who may write** | Whoever may author that reality's ruleset. **Never a regular user against a shared row** — there is no shared row: content-addressing makes every declaration set private to the digest that contains it. |
| **System tier** | `engine_default.toml` — read-only to every user, admin-managed, cloned rather than edited. Same discipline as RLS-D19's presets (`16:230-232`), which QTY inherits rather than restates. |
| **The one thing needing a scope key of its own** | The **ordinal-assignment ledger** that QTY-A5's never-reuse rule implies. It is per-reality state, not content, and it belongs with the binding — i.e. in `reality_registry`, not on disk. See `QTY-Q6`. |

---

## 5. L3 — sources, and the seam that makes them cheap

### 5.1 QTY-D2 — a progression system is a trait impl, not a config format

chaos's strongest single decision: `trait Subsystem` is **three methods** — `system_id`, `priority`,
`async contribute(&self, actor) -> SubsystemOutput` (`crates/actor-core/src/interfaces.rs:18-28`) —
with every optional capability layered as a **separate supertrait** (`ConfigurableSubsystem`,
`ValidatingSubsystem`, `CachingSubsystem`, `LifecycleSubsystem`, …, `:31-94`) rather than fattened
into one interface. Registration is one call (`PluginRegistry::register`, `:279-303`).

**Adding a cultivation system touches zero core files.** That is the property the PO asked for, and
it is bought by keeping the core trait small and the capabilities opt-in.

We take the shape and drop the `async` (our resolution is cold and synchronous — [IMP-A3](26_implementation_architecture.md)).

### 5.2 QTY-A8 — contributions carry CAPS, not just values

> **QTY-A8.** A source contributes `{ primary, derived, caps }`. A cultivation realm **raises the
> ceiling**; a buff **fills toward it**. These are different verbs and the seam must carry both.

`SubsystemOutput { system_id, primary, derived, caps, meta }`
(`crates/actor-core/src/types.rs:209-226`). Without the `caps` arm, every ceiling change becomes an
edit to a core formula — which is the god class returning through the back door. We have **no**
cap-contribution concept today.

### 5.3 QTY-A9 — aggregation order is total and declared

> **QTY-A9.** Two ordered levels: **source priority**, then **stage**. Both declared. **Never a map
> iteration.**

chaos designed this correctly (`registry.rs:42-50` sorts subsystems by priority; bucket priority
loads from `configs/bucket_priorities.yaml` with a hardcoded fallback, `enums.rs:61-70`) and then
**violated it in every implementation**: the hierarchical root aggregator iterates a `HashMap`
(`crates/actor-core-hierarchical/src/core/global_aggregator.rs:122`) and carries a `priority` field it
never reads (`hierarchical_actor.rs:50`); actor-core's deterministic `bucket_processor` is called only
by tests. Three specs promise deterministic order; none implements it.

For a replay-pinned deterministic simulation this is not a quality issue, it is a correctness one. Our
L2 iteration is `0..n` over ordinals by construction (QTY-A5), which gives total order for free —
**provided nothing ever iterates a name-keyed map.** [IMP-D4](26_implementation_architecture.md)'s
`hot-path-gate.py` is the mechanism; it is **unbuilt, and `Q1` cannot be declared done without it**,
because `Q1` is precisely the slice that introduces string names. The gate cannot be a naïve
`grep BTreeMap` — doc 26 already flags the hard part: *"`BTreeMap` on `CombatState.actors` is a keyed
collection over entities, not a per-stat lookup … **this distinction must be encoded, not assumed**"*
(`26:185-188`). The rule is *no map whose KEY type is a string or a quantity id, inside
`Domain::apply`/`check`/`game-rules`*.

The named site that would go wrong: the shortest path from a TOML `[[resources]] name = "qi"` to a
working `Q2` is `resources: BTreeMap<String, ResourceState>` on `Actor`, after which
`evaluate_outcome`'s three closures each do a string compare + tree descent, and `outcome_of` runs
them **five times per call**, on every landed Strike and every `EndTurn`
(`services/commit-service/src/combat.rs:445-454`, `domain.rs:507,574`). Determinism survives —
`BTreeMap` is ordered — so **no existing test would red.**

### 5.4 QTY-A13 — a source CONTRIBUTES; it never DECLARES

> **QTY-A13.** An L3 source may contribute into declared quantities. It may **never declare one.**
> Declaration is L2, author-owned, inside the hashed ruleset — full stop.

Without this rule the ruleset digest becomes a function of **which modules were compiled in**, so the
same `.toml` yields different digests on two builds and RLS-A13's whole pin dies. A new progression
system that needs a new quantity therefore costs **two separately-priced events**: an engine release
(its trait impl) *and* a ruleset edit (the declaration). It is enforced by a loader validator that
refuses a contribution to an undeclared ordinal — which also gives `Q4` the testable exit criterion it
otherwise lacks.

**And a correction to §3's L3 row, which said *"a new module; zero core edits"*.** True, and
misleading. Zero core edits is not zero engine release. The PO's question was *"không phải sửa rất
nhiều code nếu nhét thêm hệ thống mới"* — the honest answer is **few edits, still a release**, and the
things that cost *no* release are L2 declarations and content.

---

## 5.5 L2 is NOUNS. The VERBS are already designed, elsewhere — do not build a second dialect

The red team's sharpest strategic finding was that an author who can declare a `qi` pool but cannot
declare *"meditating at a spirit vein raises qi"* has a noun and no sentence — citing PRD-F2:
*"there is precisely **ONE** author-declarable trigger in the entire system, and it is wired to
precisely ONE effect"* (`28:160-168`).

**That is a scope boundary, not a defect in this document, and the verbs are not undesigned.** They
have four homes already:

| The verb machinery | Where | Status |
|---|---|---|
| **Generators** — the resource sources | `RES_001` — four named: `Scheduled:CellProduction` · `NPCAutoCollect` · `CellMaintenance` · `HungerTick`, via `OutputDecl`, firing **per turn** with an elapsed-time parameter (TDIL-A3, O(1) regardless of `time_flow_rate`) | designed |
| **Conservation** — what makes a source *declared* | [`EXC-L1`](30_exchange_model_and_dataflow.md) — deltas sum to zero except at a declared source/sink, with a bite test | designed; **the ledger does not exist in code** ([WSA-R14](31_world_simulation_architecture.md)) |
| **How reactions resolve** | [`TRG-A1..A11`](33_trigger_group_order.md) — ordered groups, the **wave** model, depth budget, attribution by ownership | designed |
| **The author's WHEN seam** | `TrainingRuleDecl.source` — `Action{interaction_kind, target_match, instrument_match}` + `Time{DailyBoundary}` | `PROG-9` ✅ V1 |

So PRD-F2 is a statement that the **author-declarable vocabulary is narrow**, not that the substrate is
missing — and widening it already has an owner: [**WSA-R18**](31_world_simulation_architecture.md),
*"a closed `TriggerPoint` set with a depth budget, **generalising the ONE seam that exists**
(`TrainingRuleDecl.source`) rather than adding a second dialect"*.

> **QTY-D10 — this document does NOT design triggers, effects or generators, and no slice of §12 may.**
> A trigger vocabulary bolted next to `TrainingRuleDecl.source` is the `combat.rs` failure mode
> ([32 §146](32_locus_as_actor.md)). Nouns here; verbs at WSA-R18. The two tracks meet only at the
> declared-quantity ordinal, which is the correct and only seam.

---

## 6. QTY-A10..A11 — what happens when L1 must grow

**This is the PO's actual requirement and no codebase in either repo has solved it.** The audit
searched all three chaos crates for `schema_version`, `migration`, `serde(default)`: every `version`
found is a *config-file* version; `Actor.version` is a cache-invalidation counter
(`types.rs:34`, used at `aggregator/mod.rs:255`); `deprecation/` generates **human-readable migration
documents**, not data migrations (`src/deprecation/migration_guide.rs:13-30`). chaos's actor-core
escapes by accident — `primary`/`derived` are `HashMap<String,f64>` so an old actor simply lacks the
key — and its **element-core, the dense-array layer that is shaped like ours, does not escape at
all**: it defers the problem by having no persistence, `// use serde::{…}; // Removed for now`
(`crates/element-core/src/core/elemental_data.rs:19`).

We have neither escape. So we design one.

### 6.1 QTY-A10 — two kinds of engine change, two different costs

> **QTY-A10.** Distinguish them explicitly and never let a change be silently the third thing.
>
> **(a) ADDITIVE** — a new L1 slot or role that no *existing* law reads differently. Old events
> replay **identically**, because no law's inputs changed. Cost: a canon schema version + an upcast
> function + an **epoch-switch event**.
>
> **(b) BEHAVIOURAL** — an existing law's arithmetic or order changes. **No encoding trick preserves
> replay.** This requires either retained versioned law sets or an explicit checkpoint boundary, and
> it is a rare, recorded, deliberate decision.

Most growth is (a). "Add `MaxMana`", "add a `Ward` role", "add a fifth damage-chain *input*" are all
additive. The four-step chain's *order* changing is (b), and [IMP-A4](26_implementation_architecture.md)
already locks that order for V1+.

### 6.2 QTY-D3 — the additive path, end to end

Reality `R` was created under engine v1, bound to digest `D1` over stored bytes `B1` (10 slots).
Engine v2 adds slot #11.

1. **`B1` is never touched.** It stays in the append-only store (RLS-D6) and still hashes to `D1`, so
   `store.get` re-digest verification still passes (`crates/ruleset-loader/src/store.rs`) and every
   event already pinned to `D1` still resolves to the exact bytes that produced it (RLS-D18).
2. **The decoder learns to read a narrower artifact** — QTY-A11 below.
3. **Upcast is explicit**: `upcast_rules(v1 → v2)` fills slot #11 from its declared engine default.
   The upcast runs **after** digest verification, in memory. The stored bytes and their digest are
   untouched.
4. **The result is a NEW resolved ruleset**, stored as new bytes `B2` with digest `D2`.
5. **The binding moves `D1 → D2` via an epoch-switch event** in `R`'s own log (doc 16 §9). This is
   what keeps RLS-A3 intact: *there is no path by which a reality's rules change without an event in
   its own log*. An upcast that silently swapped the effective rules would be exactly the bug
   `create_reality`/`load_reality` was split to prevent
   (`crates/ruleset-loader/tests/early_binding.rs:40-65`).
6. **Replay reads the pin per event** and resolves `D1` for pre-epoch events, `D2` after.

> **The result: adding a derived slot is a bounded, auditable, four-artifact operation — not a
> teardown.** That is the direct answer to *"derived phải có khả năng mở rộng"*.

### 6.3 QTY-A11 — the canonical encoding must be length-declared

> **QTY-A11.** A canonically-encoded sequence carries its own length. The decoder accepts
> `n ≤ N_current` and fills `[n..N_current]` from declared engine defaults; `n > N_current` is a
> refusal.

Today `canon.rs:213-226` errors on **any** length mismatch, with the correct reasoning — *"an artifact
written when `SLOT_COUNT` was 10 must not silently half-fill an 11-slot array"*. The guard is right;
its **strictness is what makes growth fatal**. Length-declaring keeps the guard (a truncated or
corrupt artifact is still caught, because the declared `n` must match the bytes present) while making
the widening case legal and explicit.

**This is the highest-leverage code change in the whole document**, because it is what turns every
future L1 addition from a spine break into an epoch switch.
[27 §11.6](27_extensibility_stress_test.md) already stated the deadline: *"Slot ordinals must be
decided **before** they are serialised into replay logs."*

**Two corrections from the red team, both of which make it cheaper and one of which makes it bigger:**

* **The encoding is ALREADY length-prefixed.** `crates/ruleset-core/src/canon.rs:205-226` reads
  `let n = self.u32()?` and errors only on `n != N`. A11 is a **one-branch policy change** — accept
  `n ≤ N`, fill the tail from engine defaults — **not** an encoding change, and **it moves no existing
  digest**. Calling it a rewrite overstated it.
* **A11 alone is insufficient.** `Ruleset::from_canon_bytes` refuses on
  `schema_version != RULESET_SCHEMA_VERSION` (`crates/ruleset-core/src/ruleset.rs:94-101`) **before**
  you ever hold a struct to upcast. `Q0` needs **version-dispatched decode** as well; §6.2 step 2 did
  not say so.

### 6.3.1 — REMOVAL is the third kind of change, and the first build order committed it

A11 refuses `n > N_current`. The original slice `Q2` said *"`MaxHp`/`MaxStamina` **leave the slot
array**"* — i.e. `SLOT_COUNT` 10 → 8, under which **every artifact ever written at n = 10 is refused**.
Slot removal is neither additive nor behavioural: it is exactly the third thing
[QTY-A10](#61-qty-a10--two-kinds-of-engine-change-two-different-costs) says never to let a change
silently be, and the document's own build order was it.

> **QTY-A10(c) — REMOVAL. A declared slot ordinal is never reused and never removed.** Retiring a slot
> means marking it dead in the manifest and leaving its ordinal permanently occupied — the same
> never-reuse discipline [QTY-A5](#42-qty-a5a6--ordinals-and-width) applies to L2, applied to L1.
> Reclaiming the width would require a full re-encode of every stored ruleset and is not a supported
> operation.

`Q2` is corrected accordingly: `MaxHp`/`MaxStamina` **stay**, and become the slots a declared resource
**binds its ceiling to** — which is what `RES_001` already specifies (`RES_001:1083` binds
`max_value` to those slots). The pool concept arrives additively; nothing is removed.

### 6.4 QTY-A12 — the memory budget is an assertion

> **QTY-A12.** Every dense per-actor structure carries
> `const _: () = assert!(size_of::<T>() <= BUDGET);`
>
> **This axiom is only satisfiable because [A6 was reversed](#42-qty-a5a6--ordinals-and-width).** A
> runtime width puts the payload behind a pointer, where `size_of` cannot see it — the check compiles,
> always passes, and can never bite. A12 and the first draft of A6 were mutually exclusive, and A12 is
> the one worth keeping: a guard that cannot fire is worse than no guard, because it reads as one.
> Baseline to assert against, measured: `Actor` **192 B** today; ≈ 280 B at `[i32;32]`; ≈ 408 B at
> `[i32;64]`.

chaos's active design doc computes **"~22KB per system instance"** against a stated budget of
**"Acceptable up to 20KB"** (`docs/element-core/12_Performance_Optimization_Design.md:17,51`) — from a
**four-field illustrative struct**, not the fifty-seven-field real one. Its own archived analysis got
the true figure right: **"~45,000 bytes"**
(`docs/element-core/archive/old_architecture/ARRAY_VS_HARDCODE_PERFORMANCE_ANALYSIS.md:51`). Two other
docs claim 2–3 KB, off by ~15×. There is no `size_of::<…>()` assertion anywhere in the three crates.

A doc drifted by 2× for months because nothing checked it. One `const` assertion would have reddened
the day the fortieth array landed. **Copy the discipline; add the assertion chaos never wrote.**

---

## 6.5 The seven systems, walked

The first draft named the PO's seven systems in §0 and then **never walked one of them** — a red-team
finding, and a fair one: a document whose §0 declares *"this is the question this answers"* owes at
least one worked case. All seven, honestly:

| System | L2 kinds needed | Verdict | What it waits on |
|---|---|---|---|
| **luyện thể** (body refining) | a 2nd Stage kind, `BodyOrSoul::Body`, terms into `MaxHp`/`Armor` | ✅ **works today, with no QTY at all** | nothing — `PROG_001:1331,1532` already claims it native. QTY adds no capability here and should not pretend otherwise |
| **luyện khí** (qi refining) | Stage kind **+ a pool** | ✅ after `Q2` | the pool half only; the Stage half already resolves |
| **ma pháp** (mana) | pool + cost binding | ✅ after `Q2` | `VitalKind` is an engine-closed enum (`RES_001:203-207`) while `ABL-V3` requires *"the reality's declared vitals"* (`ABL_001:683`) — **the corpus was already self-contradictory here before QTY**, and `Q2` is what resolves it |
| **kinh nghiệm thăng cấp** (XP levels) | Stage kind, tiers = levels | ⚠️ **mechanically fine, blocked by an axiom** | `DF7-A9` forbids the concept outright — *"DF7 exposes **no** aggregate 'level'"* (`DF07_001:170-173`), per an earlier PO direction. **This is a PO decision, not an engineering gap**, and QTY does not amend it |
| **ngự khí** (weapon spirit) | item-owned progression + a cross-entity product | ⏳ `PROG_001` reserves `actor_progression` owner=`Item` for V1+30d (`00_CONCEPT_NOTES:402`, 御剑 named at `PROG_001:1332`) | that reservation, **plus** the product below. `ModifierSource::Equipment` is `Flat`/`Percent` only, so *"the sword's own realm multiplies your strike"* needs `QTY-D11` |
| **mị ma song tu** (dual cultivation) | 2 primaries + a **product** term + **cross-actor** input | ❌ **not expressible** | `QTY-D11` (the product) **and** `QTY-Q7` (the cross-actor seam) |
| **ngự thú** (beast taming) | a source whose **input is another actor** | ❌ **not expressible** — the L3 trait is `contribute(&self, actor)`, single-actor by signature | `QTY-Q7`. Note the trap: changing the trait *signature* breaks every impl — **a core edit**, i.e. the god-class regression QTY-F1 exists to prevent. The seam must be right the first time |

**Read honestly: four of seven land on QTY's own slices, one lands on a PO decision, and two need a
seam QTY has not settled.** That is a better answer than the first draft implied and a worse one than
"the architecture carries all seven."

### 6.5.1 QTY-D11 — adopt XST-R7, and record its three unsolved edges

The first draft claimed elsewhere that this document *"leans on [XST-R7](27_extensibility_stress_test.md)"*.
**It did not — R7 appears nowhere in it.** Adopted now, because `mị ma song tu` and `ngự khí` both
require it:

> **XST-R7 — `StatSlotDecl { …, combine: Sum | Product }`**, a stage-scoped operator. Because terms in
> one slot's pool carry **distinct `kind_id`s**, `combine: Product` over `[{qi, w1}, {body, w2}]` **is**
> a cross-quantity product. The false dichotomy "product of contributions to the same slot" vs
> "product of two different primaries" collapses — here they are the same object.

Three edges it does **not** solve, recorded rather than glossed:

1. **`combine` is per-slot-decl, not per-term**, so a mixed polynomial — `attack = 2×str + (qi×body)`,
   which is the genre's actual form — is inexpressible. All-sum or all-product, and
   `stat.duplicate_slot_decl` (`DF07_001:673`) forbids the two-declarations workaround.
2. **Any zero term annihilates the slot** under Product: an actor with no body cultivation resolves
   `StrikePower = 0`.
3. **The milli divisor for an n-ary product is unspecified** anywhere in the corpus — contrast
   `combat.rs:301-305`, where the analogous `1000⁴` is called out explicitly *because getting it wrong
   scales every hit by 1000×*.

These are `QTY-Q8`.

### 6.5.2 The conditional-term hole

*"attack = 2×strength + 0.5×qi, **but only above realm 3**"* — the single most common xianxia affix
shape — **has no home**. `StatTerm`'s only conditional is `instrument_match`, which tests the equipped
main-hand and nothing else (`DF07_001:100,274`); a term is never threshold-conditional. All four
candidate mechanisms fail: a second declaration is forbidden (`DF07_001:673`); a threshold-gated L3
source turns a *content* conditional into a *code* change, contradicting the no-engine-release claim;
a `TierDecl` gate is history-dependent, not state-dependent (the bonus persists after you drop below);
and ARPG's `ModifierGuard` (`27a:373-374`) is neither adopted nor deferred anywhere. Recorded as
`QTY-Q9` — **the hole an author is most likely to hit first.**

---

## 7. What we take from chaos

| # | Taken | Source | Why it is right |
|---|---|---|---|
| 1 | Arithmetic code / arrangement data | `combiner.yaml:4-39` vs `bucket_processor/mod.rs:115-155` | designers get real control with no expression parser, no eval, no sandbox |
| 2 | config → registry → **assigned** ordinal → dense array | `unified_element_registry.rs:114-117,133-134` | YAML-declarable identity at array speed; never-reused ordinals mean stale data cannot silently rebind |
| 3 | Capped array + overflow map for pools | `types.rs:26,28`; `resource_indices.rs:1-11` | hot set branch-free, long tail open; a performance ceiling, not a design one |
| 4 | Resource **metadata as a registry row** | `resource_registry.rs:15-31` | actor stores only `current`; adding a pool is a declared row |
| 5 | 3-method core trait + optional capability supertraits | `interfaces.rs:18-28` vs `:31-94` | a new cultivation system costs **zero core edits** |
| 6 | Contributions carry **caps** | `types.rs:209-226` | a realm raises the ceiling without editing a core formula |
| 7 | Two-level declared order (source priority → stage) | `registry.rs:42-50`; `enums.rs:61-70` | total, reproducible aggregation regardless of registration order |
| 8 | Predicates as declared data over a **function registry** | `condition-core/src/types.rs:32-39`; `resolver.rs:10-11` | the *right* half of "formulas as data" to actually build |
| 9 | Derived stored on the node that owns its inputs | `elemental_data.rs:504,524,808-825` | nothing outside a subsystem knows its formula |

## 8. What we refuse

| # | Refused | Where it bit chaos | Our rule |
|---|---|---|---|
| 1 | Ordinals from `sort()` / load order | `elemental_config_loader.rs:77-79` — one new YAML renumbers everything after it | **QTY-A5**: assignment table inside the hashed ruleset |
| 2 | Map iteration in aggregation | `global_aggregator.rs:122`; `priority` carried but never read (`:50`) | **QTY-A9** + [IMP-D4](26_implementation_architecture.md) `hot-path-gate.py` |
| 3 | Disagreeing ceilings | array 50 (`elemental_data.rs:22`) · config 50 (`registry_config.rs:200`) · register path **1000** (`unified_element_registry.rs:103`) ⇒ panic at 51 | **QTY-A6**: one width, per reality, in the digest |
| 4 | Multiple representations of one quantity | typed array · `custom_resources` · `actor.data["hp_current"]` (`resource_regeneration.rs:354`) | **QTY-A7** |
| 5 | Memory budgets that live only in prose | 22 KB claimed vs 41.5 KiB real, undetected | **QTY-A12** |
| 6 | An `n²` interaction table **inline on every actor** | `[[f64;50];50]` = 20,000 B per actor, 47 % of chaos's struct (`elemental_data.rs:594`) | **QTY-A6.1**: `O(n)` per actor, `O(n²)` per ruleset. *(This row originally refused the compile-time cap itself — red team showed that was the wrong target: the cap is fine, the **placement** was the bug.)* |
| 7 | Unvalidated property-bag escape hatches | already caught as [WSA-R05](31_world_simulation_architecture.md) | extension keys become **declared** L2 quantities |

**QTY-Q4 records the one trade we have not decided:** chaos deliberately chose *duplicated
per-subsystem scaffolding* over one shared registry, on the ground that a generic registry recreates
the god class one level up — the *"God Registry Problem"*
(`docs/actor-core/EXTENSIBLE_HIERARCHICAL_DESIGN.md:121-137`, and `:557` *"Copy elemental system
structure to create new systems"*). That is a real argument and a real cost. We have not made this
call and must not drift into either side.

---

## 9. What LoreWeave already has that chaos does not

Recorded so the next reader does not conclude the audit was one-directional. Each is load-bearing and
each is *why* our growth problem is harder than chaos's — a spine that actually holds is a spine that
actually constrains.

* **Derived is genuinely computed.** chaos's two production aggregators return
  `derived: HashMap::new()` (`src/aggregator/mod.rs:253`, `optimized.rs:145`) and its ~40 formulas
  live only in a Markdown table (`docs/actor-core/designs/21_Dimension_Catalog.md:36-56`). Ours run.
* **Determinism.** Ours holds; chaos's is broken in every implementation (§5.3).
* **Integer-only resolution** (DF7-A4) — no float anywhere in the stat path.
* **Digest-pinned replay + early binding** (RLS-A3/A13, `tests/early_binding.rs`) — chaos has no
  concept of it.
* **Cold projection** ([IMP-A3](26_implementation_architecture.md)) — strictly better than chaos's
  hybrid, which kept the map **on the hot path** for anything custom.

---

## 10. What the adversarial audit killed

Recorded because these claims are in sealed documents and will mislead the next reader otherwise.
Amendments are listed in §11.

1. **[27 §6](27_extensibility_stress_test.md) convergence #2 is misattributed.** It credits
   *"immersive · cultivation · ARPG"*. The raw reports show **one** genuine source — immersive-sim
   (its own extension-point #1, `27a:502-511`). The cultivation agent wrote the opposite (*"None of these introduces a map, a
   float, **or an author-declared slot**"*, `27a:730`; *"What I would not change: **the dense closed
   array**"*, `27a:747`) and the ARPG agent proposed growing the **binary's** enum
   `[i32;10] → [i32;26]` with *"the 88× HashMap argument is untouched"* (`27a:349`). The second voice
   for the head/tail form is the adversarial agent reading our code (`27a:980`), not a genre. **A
   synthesis pass attributed one agent's proposal to three, and this document's predecessor cited it
   as its strongest evidence.**
2. **[27 §9.4](27_extensibility_stress_test.md)'s re-measurement is unverified.** The numbers
   (1.384 / 1.496 / 11.952 ns, `27a:851-855`) come from a probe whose own method note says
   *"probe file written, run, then **deleted**"* (`27a:782`). No benchmark file exists in the repo for
   this comparison; `StatId` has **zero** hits in `.rs`. In a repo whose stated discipline is the
   bite-test, this cannot be quoted as fact.
3. **"The 88× justification was wrong" is itself wrong.** The two figures measure **different
   competitors**: 88× is closed-array vs `HashMap`; 1.08× would be closed-array vs
   **interned-ordinal array**. chaos's *committed* criterion output supports the former
   (`target/criterion/…` — 8.2 ns for 50 ordinal reads vs 704.9 ns for 50 `HashMap<u64>` reads).
   **88× was never an argument against QTY-A5/A6 — it is an argument against chaos's own map**, and
   QTY-A6 keeps the dense array, so it is not in tension with either number.
4. **XST-R6's "medium cost" was self-authored and self-contradicted** — *"medium"* at `27:299` versus
   *"Cheap now (two accessors, ~11 tests)"* at `27:722`, sizing **two different designs**, never
   reconciled. Reality: **102 `StatSlot::` references across 6 files.**
5. **"Closed head + open tail of slots" buys almost nothing.** The laws read **9 of 10** slots by
   name (`services/commit-service/src/combat.rs:122-129`, `stats.rs:92,105`); only `MaxStamina` is
   unread. The open tail would be one dead slot, while every pressure case cited needs a *head* slot.
   **QTY-A3 replaces it: the closed set is ROLES, not slots.**

### 10.6 What the SECOND round — the red team on this document — killed

Four agents attacking performance · multiverse · gameplay extension · the four open questions. Two
findings were raised **independently by three of the four**, which is why they are treated as settled.

| # | Killed | Where it is now handled |
|---|---|---|
| 1 | **`QTY-A6` ⊥ `QTY-A12`** — a runtime width puts the payload behind a pointer where `size_of` cannot see it, so A12's guard could never fire. Raised by 3 of 4 | §4.2 — A6 reversed; A12 kept |
| 2 | **`QTY-A6` is probably unimplementable** — the const-generic route dies at the monomorphic `Managed { island: Island<CombatDomain> }`, and `Domain` is not object-safe | §4.2 |
| 3 | **`QTY-A11` refused this document's own `Q2`** — slot *removal* is the third kind of change A10 forbids being silent | §6.3.1 — `QTY-A10(c)`; `Q2` corrected so nothing is removed |
| 4 | **The `n²` interaction table was unscoped** — shrinking `n` without moving the matrix off the actor reproduces chaos's exact 20 KB bug at n = 50 | §4.2 A6.1 |
| 5 | **The ordinal-carrier rule was missing**, and there is a **live code defect** on that path: the publisher's SELECT drops `ruleset_digest` while the envelope field is `omitempty` | §4.5 — `QTY-A14` + `D-PUBLISHER-DROPS-RULESET-PIN` |
| 6 | **Tenancy was absent** — zero occurrences of owner/user/scope key, a CLAUDE.md violation | §4.6 — `QTY-D9` |
| 7 | **An L3 source could implicitly declare a quantity**, which would make the digest a function of the compiled module set and kill RLS-A13 | §5.4 — `QTY-A13` |
| 8 | **The document never walked one of the seven systems** it opens by naming | §6.5 |

**And three miscitations of my own, recorded because a wrong citation in a sealed document is how the
last round's errors happened:**

* *"`recovery.rs` documents why replay rather than a checkpoint, which argues for versioned laws"* —
  **it argues for neither.** That passage rebuilds a dedup set and a turn counter from a 2 000-event
  tail and evaluates **zero laws**.
* *"`PROG_001:83` reserves `TrainingSource::CrossActor` with an `f32`"* — **line 83 has no `f32`.** It
  is at `:461`, commented out, and belongs to `PROG-D8`, a different deferral. There are eleven.
* *"doc 35 leans on `XST-R7`"* (said in discussion) — **R7 appeared nowhere in it.** Now adopted
  deliberately as `QTY-D11`, §6.5.1.

**What the round did NOT kill, and this matters as much:** `QTY-A1` (arithmetic/arrangement),
`QTY-A5` (assigned ordinals inside the hashed bytes), `QTY-A11` (length-tolerant decode — and it turns
out the encoding is *already* length-prefixed, so this is one branch), `QTY-A4` (a pool is not a stat),
`QTY-A8` (caps), `QTY-A13`, and the `Effort`-cut. `QTY-A3` survives narrowed to a single role, on
cardinality grounds it did not originally state.

**One thing the round said that this document should stop doing:** relitigating nanoseconds. The
measured system ceiling is **p50 5.4 ms per commit, 53 % of it WAL fsync**; a stat read is ~1.4 ns.
Array-vs-map is ~0.0001 % of the budget. §10.2–10.3 exist to correct a *citation* error, not because
the performance question is live — and they should not invite the next reader to re-fight it.

---

## 11. QTY-D4..D8 — amendments this document forces

| Id | Target | Change |
|---|---|---|
| **QTY-D4** | [`27 §7`](27_extensibility_stress_test.md) **XST-R6** | **RETIRED.** Opening `StatSlot` is the wrong fix — see §10.5. Replaced by QTY-A3 (roles) + QTY-A6 (per-reality L2 width) |
| **QTY-D5** | [`31 §3`](31_world_simulation_architecture.md) **WSA-R02** | **REVISED, finding preserved.** ONT-F2 (*"a person is not ten numbers"*) stands; the mechanism changes from "declare more slots" to "declare L2 quantities and bind them to roles". `DF7-A1` stays closed |
| **QTY-D6** | [`DF07_001`](features/DF/DF07_pc_stats/DF07_001_actor_stat_block.md) **DF7-A1** | **AMENDED, not overturned.** The closed slot set is correct **at L1**. Add: slots are the *derived* layer; `StatTerm.kind_id` refers to an **L2 declared quantity ordinal**, not a free string; pools leave the slot array per QTY-A4 |
| **QTY-D7** | [`26 §1`](26_implementation_architecture.md) | The SUPERSEDED banner asserts the 1.08× figure as fact. Correct it per §10.2–10.3: the figure is **unverified**, and 88× was never the relevant comparison |
| **QTY-D8** | [`27 §6`](27_extensibility_stress_test.md) + [`27 §9.4`](27_extensibility_stress_test.md) | Correct convergence #2's attribution; mark the re-measurement **UNVERIFIED — no committed harness** |
| **QTY-D11** | [`27 §7`](27_extensibility_stress_test.md) **XST-R7** | **ADOPTED** (§6.5.1) — `combine: Sum \| Product` is required by `mị ma song tu` and `ngự khí`, and terms carrying distinct `kind_id`s make it a genuine cross-quantity product. Its three unsolved edges become `QTY-Q8` |
| **QTY-D13** | [`16 §9`](16_ruleset_loader_and_registry.md) **RLS-A14** + `Q0` | A **behavioural** law change gets a **checkpoint boundary**, not versioned law sets — and `LAW_VERSION` must enter the hashed bytes first, because until it does a behavioural change moves no digest and is undetectable (§13.1) |

---

## 12. Build order

Replaces the `stat_archetypes → templates → F3` order, which is blocked: all three add content bound
to a derived set that cannot yet grow.

| # | Slice | Done when |
|---|---|---|
| **Q-1** | **The two mechanical gates, FIRST** — `IMP-D4 hot-path-gate.py` (keyed on the KEY type, per §5.3) + the `QTY-A12` `size_of` assertion | each gate reds against a deliberately-introduced violation. **Hours, and both must exist before the code they guard, not after** |
| **Q0** | **[QTY-A11](#63-qty-a11--the-canonical-encoding-must-be-length-declared) length-tolerant decode + version-dispatched decode + `LAW_VERSION` + `upcast_rules` + the epoch-switch path** (§6.2) | an artifact written at 10 slots loads on an 11-slot engine, the old digest still verifies, the transition appears as an event in the reality's log — **bite-proven**. See the two prerequisites below; this slice is bigger than the first draft said |
| **S2** | **`game-rules` extraction** ([IMP-A5](26_implementation_architecture.md)) — laws move out of `domain.rs`, take `Rules` by ref | `game-rules` has no I/O dependency, enforced by a gate. **A hard prerequisite for Q2–Q4**: role plumbing must not be written into files that are about to be split (`domain.rs` 592 lines, `combat.rs` 456 — both already over the IMP-D3 ceiling) |
| **Q1** | **L2 substrate** — declared-quantity registry, ordinal table inside the hashed ruleset, the assignment ledger, `QTY-A13` validator | a reality declares a quantity that does not exist in the engine and it survives create → store → load → digest with ordinals unchanged. **Blocked on `D-PUBLISHER-DROPS-RULESET-PIN`** (§4.5) |
| **Q2** | **Resources** ([QTY-A4](#41-qty-a4--a-pool-is-not-a-stat)) + the `Vital` binding **+ the caps arm** ([QTY-A8](#52-qty-a8--contributions-carry-caps-not-just-values)) | a reality binds `Vital → qi` and the defeat law is **unchanged**. `MaxHp`/`MaxStamina` **stay** and become ceiling-binding targets (§6.3.1). **The caps arm moved here from Q4** — a pool's max *is* a ceiling, so building resources without it means every max lands as a formula edit and Q4 then retrofits it |
| **Q4** | **L3 sources** — the contribution trait, two-level declared order ([QTY-A9](#53-qty-a9--aggregation-order-is-total-and-declared)) | two progression systems contribute to one actor with a total, reproducible order; a contribution to an undeclared ordinal is **refused** |
| **Q3** | **Elements** as L2 + the interaction table replacing `elem_mult_pm`, **`O(n²)` per ruleset** (§4.2 A6.1) | two realities with different element sets on one binary. **Last, and explicitly droppable** — it is the only L2 family with zero pressure from the seven systems (§6.5); fire-beats-wood is a flourish |
| **Q5** | then `stat_archetypes` · templates · F3 | as previously specified, now against a set that can grow |

**Q0's two prerequisites, both of which the first draft assumed and neither of which exists:**

1. **`RulesetEpochActivated` has ZERO occurrences in `crates/` or `services/`** — it is documented in
   `16 §9` (RLS-A14) and nowhere else. There is no handler, no type, no migration.
2. **`BindingStore` has no mutating method at all.** Its surface is `create` / `load` / `digest_for`
   (`crates/ruleset-loader/src/binding.rs:143,181,197`); `create` hardcodes `epoch: 1` (`:162`) and
   refuses a second call. A binding is described in its own module doc as *"mutable state — it moves
   when an epoch switch happens"* and is **write-once in shipped code**. It is also a **node-local
   TOML file** (`:138-140`), so on a multi-node deployment there is no consistent target to write.
   Moving it to `reality_registry` (`binding.rs:40-47` already names this) is part of `Q0`, not later.

**The deadline is real but not ticking.** `create_reality` has **no production caller** — only
`tests/early_binding.rs` and a CLI flag (`services/commit-service/src/bin/spine.rs:52`). Zero
production realities exist, so the clock is under our control. `Q0` is still first, on the better
ground that it is the **cheapest** slice (one branch in `canon.rs`, one version dispatch in
`ruleset.rs`) and it converts every later slice from a break into an epoch switch.

**What is NOT in this build order, deliberately:** triggers, effects and generators. See §5.5 —
`WSA-R18` owns the verb track, and a second dialect here would be the `combat.rs` failure mode.

---

## 13. Open

### 13.1 The four original questions — CLOSED by the red-team round, 2026-07-28

| Id | Resolution |
|---|---|
| ~~**QTY-Q1**~~ | ✅ **CLOSED — `QTY-D12`: cut `Effort`, keep `Vital` on CARDINALITY grounds.** The plurality question had been asked of the wrong role. §4.3 |
| ~~**QTY-Q2**~~ | ✅ **CLOSED — `QTY-D13`: checkpoint boundary, NOT versioned law sets; and first make the change DETECTABLE.** Three findings reversed the proposal. (a) The stated rationale was a **scope error**: `recovery.rs:21-28` rebuilds a dedup set and a turn counter from a 2 000-event tail — **it evaluates zero laws**, so it argues for neither side. (b) The drop rule is **not computable**: `reality_registry` has no ruleset/digest column and the binding is a node-local file, so *"no live reality is bound to V"* needs a filesystem scan, not a query. (c) Retiring every old law set today would break **nothing that runs** — the per-event `ruleset_digest` is **write-only**: every replay decoder hard-nulls it (`world-service/src/rebuild/event_source.rs:114`, `bin/replay-aggregate.rs:272`, `crates/rebuilder/src/lib.rs:552`) and `tests/conformance/` has zero ruleset hits. **Meanwhile the checkpoint already exists and already carries the digest** (`crates/sim-core/src/checkpoint.rs:32`, `Island::restore` refuses a mismatch) and `16 RLS-D9` already specifies it. **The prerequisite, and the deepest hole either option leaves: the digest does not cover the LAW.** `Ruleset::digest()` hashes `CANON_DOMAIN + schema_version + combat + stats` (`ruleset.rs:59-72`) — two engine builds with different `resolve_attack` arithmetic produce the **identical digest**, so a behavioural change is currently **undetectable and cannot trigger any boundary**. Add `LAW_VERSION: u32` to the hashed bytes in `Q0`. Keep the ADR gate and the golden-trace conformance test — but note the harness must be **built**, not reused |
| ~~**QTY-Q3**~~ | ✅ **CLOSED — fix the floats, do NOT reserve the shape.** The original citation was wrong twice: `PROG_001:83` contains no `f32` (it is at `:461`, on a **commented-out** line belonging to `PROG-D8`, a *different* deferral). And there are **11 `f32`s in that file**, six of which a 2026-07-26 closure note declares converted to milli **in prose only** — the code blocks still read `f32`. Fix all eleven; delete the commented-out variant rather than "fixing" it. **`SourceRef` is NOT reserved:** the line is not code-vs-doc but *"can this un-consumed shape be wrong in a way only the consumer would reveal?"* — COMB_002's arena generator was self-contained and testable alone, so it could not rot; `SourceRef`'s `OtherActor(role)` depends on a **kernel** question nobody has answered (entity-in-exactly-one-island is *structural* in `sim-core`). Register the **question**, not the enum → `QTY-Q7` |
| ~~**QTY-Q4**~~ | ✅ **CLOSED — the split is correct, plus `QTY-A13`.** Verified mechanically: all nine "God Registry Problem" bullets are about **behaviour** (`EXTENSIBLE_HIERARCHICAL_DESIGN.md:121-137`), and a grep for `declar\|ordinal\|identity` across both chaos architecture docs (1 045 lines) returns **zero matches** — chaos never distinguished declaration from behaviour, it transferred the conclusion by conflation. Measured cost of its duplication: **62 `*Registry`, 10 factories, 13 aggregators, ~9 187 LOC**, one trait **byte-identical in two copies in one crate**, six ordinal-assignment sites across three incompatible mechanisms, and three disagreeing element ceilings (50/50/**1000**) producing an unchecked out-of-bounds write. And the collapse case **already happened to chaos on the declaration side**: `HybridElementRegistry` is a field-for-field clone created because a second *kind* of quantity could not be added — duplication lost. Their own consolidation plan targets **5 registries → 1**. Our repo already made the same call for declaration: *"Do not create a third registry"* (`_boundaries/01_feature_ownership_matrix.md:22-25`) |

### 13.2 Still open

| Id | Question |
|---|---|
| **QTY-Q5** | **Cross-reality quantity translation.** RLS-A6 says identical strings across realities are unrelated **by design** (`16:296-298`), so a global vocabulary is not available. That leaves an explicit per-reality-pair mapping with a declared behaviour for unmapped quantities. `PROG_001`'s current behaviour is a **silent drop** (`:932,963`), which is a defect. **This retires the reasoning behind `DF7-D12`**, whose justification (*"slots re-derive automatically"*) assumed both realities share a slot set |
| **QTY-Q6** | **Where does the ordinal-assignment ledger live?** QTY-A5's never-reuse rule implies durable per-reality state that is *not* content. It belongs with the binding in `reality_registry`, which is also `Q0`'s prerequisite — but nobody has specified its write path or who may mutate it |
| **QTY-Q7** | **Can an L3 source read or mutate a SECOND actor?** (dual cultivation, master→disciple, owner→pet.) This is a **kernel** question before it is a shape question: `sim-core` makes entity-in-exactly-one-island structural, so a cross-actor source spanning islands is not merely a signature change. Blocks `mị ma song tu` and `ngự thú` (§6.5). `PROG-D33` defers the *accrual* half to V1+30d; the *stat-term* half is unowned |
| **QTY-Q8** | **XST-R7's three edges** (§6.5.1): `combine` is per-decl not per-term (mixed polynomials inexpressible); any zero term annihilates under Product; the n-ary milli divisor is unspecified corpus-wide |
| **QTY-Q9** | **Threshold-conditional terms** — *"+0.5×qi, but only above realm 3"* has no home (§6.5.2). The hole an author is most likely to hit first |
| **QTY-Q10** | **Is the shared declaration table the right SHAPE for four structurally different families** (pools, elements, tags, primary stats)? `QTY-A13` closes the digest hole and is sound; this is the different worry — that one table accretes a discriminant, then per-kind optional fields, then per-kind validators, and becomes the god class by a slower road. That is the shape `RulesetPatch`'s 20 optional fields already have. Untested, and untestable before building |
| **QTY-Q11** | **The question this document never asked, and `28_product_definition.md` does not answer: will more than a handful of realities, or more than one team, author genuinely different quantity sets?** If the project ships one flagship reality authored by the same people who write the engine, the author/engineer distinction is fictional and L2 is indirection with one binding. **QTY earns its cost only if the answer is yes.** Named here because the honest scenario in which this whole document is the wrong call needs to be written down |
