# 28 — Product definition: what this game IS, and what "extensible mechanics" concretely means

> **Status:** SEALED 2026-07-28 (DECISION). Decisions `PRD-D1..D3`, axioms `PRD-A1..A2`, findings
> `PRD-F1..F3`, open `PRD-Q1..Q3`. **Prefix `PRD` registered** in
> [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md).
>
> Written because the PO said the thing nobody had written down:
> *"chưa có, tôi còn chưa bao giờ thực sự làm cái này — hiện tại kiến trúc thì thiết kế kiểu để cho
> mở rộng thôi."*
>
> Every claim about the current system below was checked against the corpus or the code. Sources are
> named inline so a future reader can re-check rather than trust.
>
> 🔒 **SEALED** means the *reasoning* is closed and must not be re-litigated from memory — re-read it. Open questions listed in this file remain open, and the amendment rows are **PROPOSED, not applied**: no feature spec was edited by this arc.


---

## 1. The problem this closes

34 feature folders, 28 architecture docs, well over a hundred axioms — and **no document states what
the player does.** The corpus answers *"how do we extend it?"* in enormous detail while
*"extend what?"* has never been answered.

That is not a documentation gap. It is the reason several architectural questions have stayed open:

| Open question | Why it cannot be answered without this document |
|---|---|
| [XST-F9](27_extensibility_stress_test.md) — is the closed 10-slot stat set right? | Right for a fight-centric game. Wrong for a game about living somewhere, which needs needs/mood/standing. |
| XST-R9/R10 — do we need a trigger substrate? | Unnecessary if content is enemies and items. Mandatory if content is *situations*. |
| XST-F10 — must the damage packet be typed per element? | Only matters if build-crafting around damage conversion is a thing players do. |
| [IMP-Q2](26_implementation_architecture.md) — is `game-rules` a crate? | Depends on how much of "the rules" is world behaviour vs combat. |

**Same architecture, three different correct answers.** The product decision is upstream of all of
them, and it was missing.

---

## 2. PRD-D1 — the core loop (PO decision, 2026-07-28)

> **The loop is WORLD SIMULATION. The player controls one character who must genuinely live inside
> the environment.** In the PO's words: *"đây là 1 world simulation với focus vào việc điều khiển
> nhân vật tương tác với thế giới đó — nhân vật ta điều khiển phải thực sự sống trong môi trường của
> nó."*

What this **rules out**, stated so it stops being re-litigated:

* **Not combat-centric.** Fighting is a *consequence* of living somewhere — a thing that happens to
  you, not the reason you logged in. The measure of a session is not encounters cleared.
* **Not scene-based narrative.** The world is not a sequence of authored scenes with an LLM narrator.

**Immediate consequence for work in flight.** The combat spine already built (initiative, the 4-step
chain, hit/dodge/crit, KO, round-scoped status) is **necessary and, at its current depth, sufficient
for a long time.** The held slices — tactical grid, threat/targeting, abilities — are *not* the next
frontier under PRD-D1. The frontier moved to the world.

> **PRD-D3 — combat depth is demoted below world behaviour.** COMB_002/003 and ABL_001 stay held (they
> were already held by IMP-D9); they are now held for a *product* reason as well as a supply-chain
> one, and they do not resume automatically when the ruleset loader lands.

---

## 3. PRD-A1 — "really lives in the environment", made falsifiable

A product statement that cannot be observed is a slogan. So the phrase is decomposed into properties
that are each independently true or false, each with the observation that decides it.

> **PRD-A1 — a property of the world counts only if there is an in-game observation that would fail
> if the property were removed.** This is the [non-vacuity discipline](21_architecture_ceilings.md)
> applied to product claims instead of to performance gates.

| # | Property | The observation that decides it | Status today | Mechanism |
|---|---|---|---|---|
| **P1** | The world has a definite state at every moment, whether or not I am watching | Log out at dusk, return at dawn: the blacksmith is at the forge, not frozen where I left them | ✅ **TRUE** | DL-A4/DL-D1 — routines *evaluated* from `fiction_time` |
| **P2** | Quantities in the world move on their own | A field I did not visit has grain in it when I arrive | ✅ **TRUE** | RES_001 `Scheduled:CellProduction` + `last_regen_at_fiction_ts`, clamped by `stockpile_cap` |
| **P3** | My character has needs the world can fail to meet | Ignore food long enough and the character dies — including while offline | ✅ **TRUE** | `HungerTick`; DL-D13 `offline_vitals` coarse sweep can commit death |
| **P4** | Time is scarce — doing A means not doing B | An hour spent training is an hour the market was open and I was not there | ⚠️ **PARTIAL** | TDIL clocks exist and NPCs have `ScheduledActionDecl`; **nothing forces the PC to spend a time budget** |
| **P5** | NPCs have interior state that my actions change | Insult someone; next week they refuse to trade | ⚠️ **PARTIAL** | `actor_actor_opinion` + `ActorMood` (ACT_001 §3.1.1/§3.3) exist as *storage*; **drift is V2/V3, LLM-gated** |
| **P6** | The world acts on me without me starting it | A bandit camp I ignored raids the village | ❌ **FALSE** — see §4 | none |
| **P7** | What I do leaves a mark another player can find | Someone else's ruined farm is visible as ruined | ⚠️ **PARTIAL** | committed events are durable, but nothing *derives* world appearance from them |

**Four of seven are true or half-true, one is false, and the false one is the one the phrase was
actually about.** That is a good position, not a bad one — but it has to be said out loud.

---

## 4. PRD-F1 — the world moves, but the world does not ACT

This is the single most important finding in this document, and it was verified rather than assumed.

**Verified:**

* `Scheduled:CellProduction` fills a stockpile as `delta = base_rate × elapsed × multiplier`,
  clamped to `stockpile_cap` (RES_001 §; TDIL-A3 makes it O(1) regardless of elapsed magnitude).
* DL-A4: *"a V1 routine is a pure function of `(actor_class, fiction_time, cell)` — evaluated, never
  simulated forward"*, and DL-D1 keeps cold cells at literally zero cost.
* AIT_001's Untracked crowd is `blake3(reality_id ‖ cell_id ‖ fiction_day ‖ slot_index)` — a
  different crowd on Tuesday than Monday, from a hash, with no simulation at all.

Every one of these is a **function of the clock**. Together they buy P1–P3 very cheaply, and the
design is genuinely elegant about it. But they share one property:

> **PRD-F1 — nothing in the world DECIDES anything.** Quantities move; agents do not. No entity in
> the world forms an intention, acts on it, and leaves the world different as a result — unless a
> player acted, or an LLM ran (V2 `major_drift_summary` / V3 `relationship_drift`, both budget-capped
> and tier-gated by B3-D5).
>
> Put sharply: **today the world is a clock with scenery.** That is a defensible, cheap, replayable
> V1 — and it is *not* what "the character must genuinely live in the environment" describes.

**DL-A1 is where this got decided without being noticed.** It split ambient simulation by **cost** —
*deterministic ships V1, generative waits for V2/V3* — which is a sound cost argument. But the split
silently created a third category nobody named:

| | Deterministic | Generative |
|---|---|---|
| **Non-accumulating** (clock function) | ✅ V1 — routines, crowds, production | — |
| **Accumulating** (state begets state) | ⬜ **unnamed, unbuilt, and cheap** | V2/V3 — drift, beats, rumours |

The empty cell is where "a bandit camp grows if unchecked", "a village starves after a failed
harvest" and "a road falls out of use and becomes unsafe" live. **None of those needs an LLM.** They
need the world to be allowed to keep a consequence — which DL-D1's *"evaluated, never ticked"* forbids
by construction, for reasons that were about token cost and do not apply to them.

> **PRD-Q1 — is the world allowed to act deterministically?** If yes, DL-A1's cost split needs a third
> row and DL-D1 needs the same kind of narrow amendment DL_001 itself applied to B3-D1. If no, P6
> stays false forever and PRD-D1 is not achievable at V1. **This is the decision that unblocks the
> most work, and it is a product decision, not a technical one.**

---

## 5. PRD-A2 — a mechanic is a 4-tuple, which is what makes "extensible" checkable

The PO's second answer was *"cơ chế gameplay mới"* — with the honest caveat that the ambition is broad
and must be made concrete rather than abstract. This section is that.

> **PRD-A2 — a gameplay mechanic is `WHEN · IF · THEN · ON`.** An author can express a mechanic **iff
> all four of its parts already exist in the engine's vocabularies.**
>
> * **WHEN** — a moment the engine recognises and will dispatch on (a *trigger point*)
> * **IF** — a predicate over state the engine can evaluate
> * **THEN** — an operation the engine can perform
> * **ON** — the entities the engine can address

This converts *"can we add new mechanics?"* from an opinion into a **lookup**. It also gives every
proposed extension a falsifiable acceptance test: *name a mechanic, decompose it into the 4-tuple,
show each part exists.* If a part is missing, the mechanic is not addable — no argument required.

---

## 6. PRD-F2 — the four vocabularies, as they actually stand

| Part | What exists today | Verdict |
|---|---|---|
| **ON** (subjects) | `EntityId` taxonomy (EF_001), actors, places, cells, items (`ItemDefId`), factions | ✅ **rich** |
| **IF** (predicates) | `Precondition` (`IslandOwns`, `ResourceAtLeast`, …), `TrainingCondition`, `BreakthroughCondition`, `TargetMatch`, `InstrumentMatch`, `CapRule` | ✅ **adequate, and genuinely author-facing** |
| **THEN** (effects) | `EffectOp` (9 or 11 — [nobody knows, XST-F1](27_extensibility_stress_test.md)), progression `TrainingAmount`, resource deltas | ⚠️ **narrow and drifting** |
| **WHEN** (triggers) | **`TrainingRuleDecl.source`** — `Action{interaction_kind, target_match, instrument_match}` and `Time{DailyBoundary}` | ❌ **exactly one seam** |

> **PRD-F2 — there is precisely ONE author-declarable trigger in the entire system, and it is wired to
> precisely ONE effect.** `TrainingRuleDecl` lets an author declare *when a character trains*. There
> is no way to declare *when anything else happens*.

So the accurate, unglamorous statement of today's extensibility is:

> **An author can declare when a character trains, how fast, along which curve, up to which tier, under
> which breakthrough condition, wielding which tagged instrument. That is the only mechanic an author
> can declare.** Everything else an author writes is *values* and *content*.

Two things follow, and they pull in opposite directions:

1. **The existing seam is good work.** `TrainingSource::Action{…}` with `TargetMatch`/`InstrumentMatch`
   is a real WHEN·IF pair, and PL_007's ITM-C7 even **warns at bootstrap if a rule references an
   instrument tag no item carries** — the no-silent-no-op discipline, correctly applied. This is the
   shape to generalise, not to replace.
2. **It was built by hardcoding one domain's trigger into that domain.** Repeat that eight more times
   and you get eight incompatible trigger dialects — which is the `combat.rs` rot prediction
   ([XST-F6](27_extensibility_stress_test.md)) arriving through a different door.

---

## 7. PRD-F3 — the seams are all on the wrong axis for this product

Counting what an author may genuinely declare today:

| Declaration seam | Axis |
|---|---|
| `ProgressionKindDecl` (+ `BodyOrSoul`, `derives_from`) | character |
| `CurveDecl` · `TierDecl` · `BreakthroughCondition` · `CapRule` | character |
| `TrainingRuleDecl` | character |
| `StatSlotDecl` → the closed 10 slots | character |
| `ScheduledActionDecl` (routines) | world-*appearance* |
| `ItemDefDecl.instrument_tags` | content |
| `ProducerProfile` / `stockpile_cap` / `PriceDecl` | world-*quantities* |
| `RealityManifest` world-rule toggles (DF4) | configuration |

> **PRD-F3 — eight real extension seams exist and seven of them extend the CHARACTER. Zero extend what
> the WORLD does.** For a product whose loop is *living in a world*, the extensibility investment has
> been made almost entirely on the wrong axis.

This is the most actionable sentence in this document, and it is not a criticism of the work — the
character axis is genuinely well built. It is a statement about **where the next seam goes**.

---

## 8. PRD-D2 — "extension" scoped into three tiers, each with a test

> **PRD-D2 — the ambition (*"AI có thể thêm cơ chế gameplay mới"*) is accepted as the TARGET, and split
> into three tiers. A tier is "done" only when a named mechanic that previously required engine work
> can be added by writing a declaration — and a named mechanic is deliberately still REFUSED.**

| Tier | An author writes | Engine work needed | Must ADMIT | Must still REFUSE |
|---|---|---|---|---|
| **E1 · Values** | numbers, curves, tiers, items, enemies, places, routines, story | none — this largely works today | *"Iron ore yields 3/day instead of 5"*; *"a new 24-tier cultivation ladder"* | anything introducing a new noun or a new moment |
| **E2 · Quantities** (new nouns) | a new stat / resource / status / activity **kind**, declared per ruleset | [XST-R6](27_extensibility_stress_test.md) (retired 2026-07-28 -> [`QTY-D4`](35_quantity_architecture.md)) ruleset-owned slot set + [XST-R8](27_extensibility_stress_test.md) tag bitset; [XST-R12](27_extensibility_stress_test.md) status instances | *"add `Nội lực` (*inner force*) as a real resource with its own regen and caps"*; *"add `Danh vọng` (*renown*) as a quantity NPCs read"*; *"add fire resistance"* | a quantity that changes **when** something happens |  <!-- doc-language-gate: ok - `Nội lực` and `Danh vọng` are QUOTED AUTHOR REQUESTS naming in-fiction quantities a wuxia ruleset would declare. They are the worked example, not exposition: translating them away would delete the thing the row demonstrates. Glossed inline in English on first use, per the standard. -->
| **E3 · Mechanics** (new WHEN→THEN) | a rule `when ⟨trigger⟩ if ⟨predicate⟩ then ⟨effect⟩ on ⟨subject⟩` | a **general** trigger substrate ([XST-R9](27_extensibility_stress_test.md)) + composable effects ([XST-R10](27_extensibility_stress_test.md)), with a depth budget | *"when a cell's stockpile stays at 0 for 7 days, its owner's mood drops and they leave"*; *"when struck while wielding a shield, reflect 30 %"* | unbounded recursion; anything an author can write that makes a step non-terminating |

**The E2/E3 boundary is the useful line**, and it maps exactly onto PRD-F2: E2 adds **nouns** (ON, and
values for IF/THEN); E3 adds **moments** (WHEN). Everything the PO called *"cơ chế gameplay mới"* is E3,
and E3 is blocked on there being any WHEN at all.

**The order is forced, not chosen.** E3's triggers must fire *on* something, and under PRD-D1 the
interesting somethings are world quantities that E2 introduces. Building E3 first gives a trigger
system whose only subjects are combat stats — i.e. the fight-centric product PRD-D1 rejected.

---

## 9. What this decision changes about the open architecture questions

| Question | Before | Under PRD-D1 |
|---|---|---|
| [XST-F9](27_extensibility_stress_test.md) closed 10 slots | open, argued on performance then on expressiveness | **PROMOTED to blocking.** A world-simulation loop needs needs, mood, standing, resources as first-class quantities. The 10 slots refuse all of them, and `ActorMood`/`FlexibleState` already exist *outside* the block — the split is happening by accident. |
| [XST-F10](27_extensibility_stress_test.md) typed damage packet | open | **DEMOTED.** Elemental-conversion build-crafting is an ARPG concern. Revisit only if combat becomes a player's stated reason to log in. |
| [XST-R9/R10](27_extensibility_stress_test.md) trigger substrate + effect combinators | open | **This is E3, i.e. the stated product ambition.** Not optional, but correctly sequenced after E2. |
| [XST-F11](27_extensibility_stress_test.md) cold/hot boundary drawn by authoring time | open | **PROMOTED.** A living world re-resolves derived quantities on world events, which is precisely the case that falsifies "resolution is cold". |
| [XST-F6](27_extensibility_stress_test.md) `combat.rs` rot | preventable-now-only | **Still preventable-now-only**, and PRD-F2 shows the same rot starting on the trigger axis: one hardcoded WHEN per domain. |
| COMB_002/003, ABL_001 | held by IMP-D9 | **held by PRD-D3 as well** — a product reason, not just a supply-chain one |

**One thing this decision does NOT change:** [doc 26](26_implementation_architecture.md)'s
IMP-A1 (code owns shape, config owns values) and the F1/F2 ruleset-loader build order. E2 and E3 are
both *consumers* of a real ruleset with a real digest. PRD-D1 makes the loader more urgent, not less —
E2 literally cannot exist without it, because "a quantity declared per ruleset" presupposes a ruleset.

---

## 10. Open

| # | Question | Why it blocks |
|---|---|---|
| **PRD-Q1** | **May the world act deterministically?** (§4) — i.e. does DL-A1 get a third row for *deterministic + accumulating*, and does DL-D1's "evaluated, never ticked" get the same narrow amendment DL_001 gave B3-D1? | P6 is false until this is answered; P6 is the property PRD-D1 is actually about |
| **PRD-Q2** | **What is the smallest world-acting mechanic that would prove the loop?** One concrete mechanic, buildable, observable in a session — the equivalent of "one REAL encounter" for the world tier | without it, E2/E3 have no acceptance test and will be built to a spec instead of to a game |
| **PRD-Q3** | **Does the PC spend a time budget?** (P4) — NPCs have schedules; the player currently does not. If time is not scarce for the player, "living in the world" has no cost and no choices | decides whether TDIL is load-bearing or decoration |

---

## 11. Cross-references

* Loop substrate — [`features/12_daily_life/DL_001_daily_life_foundation.md`](features/12_daily_life/DL_001_daily_life_foundation.md)
* Actor interior state — [`features/00_actor/ACT_001_actor_foundation.md`](features/00_actor/ACT_001_actor_foundation.md)
* Progression + the one trigger seam — [`features/00_progression/PROG_001_progression_foundation.md`](features/00_progression/PROG_001_progression_foundation.md)
* Resource generators — [`features/00_resource/RES_001_resource_foundation.md`](features/00_resource/RES_001_resource_foundation.md)
* Clocks — [`features/17_time_dilation/TDIL_001_time_dilation_foundation.md`](features/17_time_dilation/TDIL_001_time_dilation_foundation.md)
* AI tiers — [`features/16_ai_tier/AIT_001_ai_tier_foundation.md`](features/16_ai_tier/AIT_001_ai_tier_foundation.md)
* Extensibility findings — [`27_extensibility_stress_test.md`](27_extensibility_stress_test.md)
* Code/config boundary + build order — [`26_implementation_architecture.md`](26_implementation_architecture.md)
* Medium + shape (stale in places, see its §0) — [`00_VISION.md`](00_VISION.md)
