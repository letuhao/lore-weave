# RES_001 Resource Foundation — Reference Games Survey

> **Status:** RESEARCH 2026-04-26 — companion to [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md). Informs Q1-Q7 + surfaces Q8-Q12 about long-term strategy/simulation expansion.
>
> **Scope clarification (user input 2026-04-26):** LoreWeave is **simulation/strategy game with RPG core**, NOT pure RPG. V1 ships RPG-first vertical slice; V2+ expands toward complex resource economy + giao thương + kinh tế module. Resource Foundation must be designed for V1 simplicity AND V2+ extensibility — not an RPG-shaped local optimum that requires rewriting later.
>
> **Method:** Survey 10 reference games covering simulation, strategy, RPG-strategy hybrid genres. Distill recurring patterns. Map each pattern to LoreWeave V1 / V2 / V3 phase. Update Q1-Q7 recommendations in CONCEPT_NOTES based on findings.

---

## §1 — Why this survey exists

The user clarified the game's genre on 2026-04-26 after seeing initial CONCEPT_NOTES recommendations:

> "đây là game simulation chứ không phải rpg, rpg chỉ là 1 trong các yếu tố core của game ở v1 nhưng mở rộng thì game này là 1 game chiến thuật có yếu tố nhập vai thì đúng hơn / dó đó trong tương lại nó sẽ có hệ thống resource và giao thương cực kỳ phức tạp / chúng ta cần chuẩn bị trước đầy đủ các định nghĩa về quản lý tài nguyên và kính tế (sẽ có module kinh tế sau) để mở rộng trong tương lại"

Translation: "This is a simulation game, not RPG — RPG is only one V1 core element. The expanded game is a strategy game with RPG aspects. Future game will have extremely complex resource + trade systems. We need to prepare full resource + economic definitions UPFRONT to enable expansion."

**Implication for RES_001 design:**

- ❌ Designing as "RPG inventory + simple gold + cell production" (CONCEPT_NOTES §6 provisional) is too narrow — fits V1 but creates schema migration debt for V2 economic depth
- ✅ Resource ontology must accommodate strategy-game patterns: production chains, supply/demand, faction economies, trade routes, scarcity events, social currencies — even if V1 doesn't ship them
- ✅ Aggregate shape must support both per-actor (RPG inventory) AND per-cell-treasury (sim/strategy) AND per-faction-pool (strategy) without requiring schema-V2 break

This survey establishes the **terminology + pattern catalog** so RES_001 DRAFT can explicitly say "we support pattern X via aggregate shape Y; V1 ships subset, V2 extends without migration."

---

## §2 — Game-by-game review

10 reference games chosen for relevance to LoreWeave's NPC-driven, multi-tier-scope, turn-based, LLM-mediated context. Ordered by closest match to LoreWeave's expected V2+ shape.

### G1. Crusader Kings 3 (Paradox, 2020) — closest match

**Genre:** Grand strategy with character RPG core. Real-time-with-pause.

**Resource model:**
- **Gold** — single universal currency. Income from holdings (counties → baronies → temples/cities); recurring monthly accrual; expense from levies/men-at-arms maintenance + diplomacy.
- **Prestige** — accrues from feudal achievements (won wars, marriage, vassal management); spent on hooks, claims, decisions.
- **Piety** — accrues from religion (going on pilgrimage, donating to faith); spent on excommunication, holy wars, doctrines.
- **Renown** — dynastic resource, accrues for whole dynasty; unlocks legacies (permanent buffs).
- **Levies** — manpower, drawn from holdings; replenishes over time; consumed in war.
- **Men-at-Arms** — professional troops, fixed roster, paid in gold maintenance.
- **Hooks/Secrets** — social leverage (binary, per-character relationship); can be spent (hook = single-use favor; secret = revealable for shame).

**Key mechanics:**
- Vassal hierarchy: liege gets % of vassal income (taxes) + levy contribution
- Marriages as resource transfer (alliance, claim acquisition, dowry)
- Council positions (5 seats, vassals fill, each provides bonus)
- Building tier upgrades increase holding income
- Crime/sin generates piety penalty + hook opportunity for others
- Schemes (long-term covert actions) consume time + risk

**LoreWeave applicability:**
- ✅ **Single primary currency + multiple social currencies** = strong template for V1+
- ✅ **Hierarchy income flow** (vassal → liege) = template for cell → town → reality treasury (V2+)
- ✅ **Hooks/secrets as soft resources** = template for "social capital" tracking (very LLM-friendly — LLM can reason about who owes who)
- ✅ **Per-character resource sheet** = matches LoreWeave's PC/NPC = entity = owner pattern
- ❌ Real-time clock; LoreWeave is turn-based — adapt to fiction-time accrual

### G2. Mount & Blade Bannerlord (TaleWorlds, 2022) — RPG+strategy hybrid

**Genre:** Open-world RPG with kingdom strategy layer.

**Resource model:**
- **Denars** (gold) — universal currency
- **Inventory** with weight cap per character (PC + companions)
- **Trade goods** (~30 commodity types: grain, hides, pottery, velvet, etc.) — fungible, regional price variance
- **Equipment** (weapons, armor, mounts) — unique items with stats + condition (degrade over use)
- **Influence** (per-faction) — used to call vassals to war, make decisions
- **Renown** (per-character) — unlocks party size cap, vassal eligibility

**Key mechanics:**
- **Workshops** — buy a building in a town, it produces goods passively (income); choose what to produce (tannery, brewery, smithy)
- **Caravans** — buy a caravan unit, NPC operates it, generates passive income proportional to trade route safety
- **Smithing** — recipes → quality output based on smithing skill; consumed inputs + produced output
- **Trade arbitrage** — regional price variance + caravan delays = profit
- **Fief ownership** — castle/town generates income, requires garrison maintenance
- **Tournaments + bandit hunts** — alternative income for early game

**LoreWeave applicability:**
- ✅ **Workshops = cell-as-producer** (direct 1:1 — LoreWeave's tiểu điếm == M&B workshop)
- ✅ **Regional price variance** = essential V2 trade module pattern
- ✅ **Caravan as automated trade** = template for NPC-AI-driven trade (LLM decides routes)
- ✅ **Inventory weight cap** = realistic V1+ constraint (defer V1)
- ✅ **Item condition/degrade** = V2+ pattern (item stat + condition resource)
- ✅ **Influence per faction** = matches LoreWeave's potential faction economy

### G3. Anno 1800 (Ubisoft, 2019) — supply chain depth

**Genre:** City-builder / economic simulation.

**Resource model:**
- **Gold** — universal currency, accrues from positive trade balance + tax income
- **Production chain commodities** (~40 in vanilla): wood → planks → houses; potato → schnapps; iron → steel → weapons; cocoa → chocolate
- **Population tiers**: Farmers → Workers → Artisans → Engineers → Investors. Each tier consumes specific needs (food, beer, soap, beer, jewelry) at increasing complexity.
- **Influence** — used to claim territory, sign treaties
- **Construction materials** — separate inventory from trade goods

**Key mechanics:**
- **Production chains** are the core game: 3-step (potato farm → schnapps brewery → bar) common; 5-step (cotton → yarn → fabric → clothing → tailor) advanced
- **Population tier progression**: satisfy needs → tier upgrades → unlock new buildings → new needs → new chains
- **Trade routes** between islands (auto-running ships transport goods)
- **Storage** per island (warehouse capacity)
- **Demand-driven**: tier population needs determine production targets
- **Tourism/entertainment** = soft secondary income

**LoreWeave applicability:**
- ✅ **Production chains** = template for V2+ crafting (gỗ → ván → đồ nội thất; iron ore → ingot → sword)
- ✅ **Population tier needs** = template for NPC daily-life consumption profiles (DF1 daily life feature)
- ✅ **Trade routes** = template for V2+ inter-cell/inter-town trade
- ❌ Anno's centralized building queue + non-character ownership doesn't match LoreWeave's per-NPC-owns-stuff model

### G4. Civilization VI (Firaxis, 2016) — abstract yields + strategic resources

**Genre:** 4X strategy. Turn-based.

**Resource model:**
- **Yields** (per-turn accrual): Gold, Science, Culture, Faith, Production, Food
- **Strategic resources**: Iron, Horses, Niter, Coal, Oil, Aluminum, Uranium — required for unit construction, accrued from tile improvements
- **Luxury resources**: Wine, Silk, Citrus, Diamonds, Gypsum, etc. — provide amenity (happiness) per copy
- **Bonus resources**: Wheat, Cattle, Stone, Fish, etc. — provide tile yield bonus
- **Great People** (Great Engineer, Great General, etc.) — point-accrued, spent for one-shot bonuses

**Key mechanics:**
- **Yield-per-turn** model: every city contributes; aggregate at empire level
- **Strategic resources** are stockpiled (excess) and consumed (unit production)
- **Trade routes** between cities/civs provide gold + science + culture
- **Tech tree** unlocks new resource uses
- **Production overflow** mechanic (carry over surplus)

**LoreWeave applicability:**
- ✅ **Yield-per-turn model** = closest match to LoreWeave's fiction-time accrual (each fiction-day → batch yield)
- ✅ **Resource categorization** (yields vs strategic vs luxury vs bonus) = clean ontology pattern
- ✅ **Tech tree gating** = template for V2+ recipe unlocks per reality
- ❌ Empire-level aggregation doesn't match per-character ownership

### G5. Stellaris (Paradox, 2016) — multi-resource economy

**Genre:** 4X grand strategy.

**Resource model:**
- **7 main resources**: Energy Credits, Minerals, Food, Alloys, Consumer Goods, Influence, Unity
- **Strategic resources**: Rare Crystals, Volatile Motes, Exotic Gases, Dark Matter, Living Metal, Zro
- **Per-pop production**: each population unit (pop) works a specific job, produces resources
- **Trade Value** — fluid resource that flows along trade routes, converts to Energy + Consumer Goods + Unity at capital

**Key mechanics:**
- **Specialized jobs**: Miner produces minerals, Farmer produces food, Researcher produces science, etc.
- **Production methods**: planet specialization (Generator World, Mining World, etc.) provides bonuses
- **Trade Value piracy**: trade routes can be raided (currency sink)
- **Habitability + amenity**: pops require housing + amenity to be productive
- **Galactic Market** (mid-game): cross-empire commodity exchange with dynamic prices
- **Resource bottlenecks**: missing one resource cascades production failures

**LoreWeave applicability:**
- ✅ **Multi-resource categories with distinct production chains** = template for V2+ economy
- ✅ **Pop-as-producer** = template for "NPC has occupation, produces resource" (LLM-friendly)
- ✅ **Trade Value flowing through routes** = template for trade route flow (V2+)
- ✅ **Resource bottleneck cascade** = realistic constraint for V2+ scarcity events
- ❌ Pops as nameless aggregates doesn't match LoreWeave's named NPC

### G6. Dwarf Fortress (Bay 12, 2006-) — material specificity

**Genre:** Colony simulation.

**Resource model:**
- **Per-item ownership**: every weapon, every piece of clothing, every meal is a tracked instance
- **Material properties**: each item has material (iron, copper, leather, etc.), quality (rough, fine, exceptional, masterwork, artifact), wear, mass, decorations
- **Stockpiles** with capacity + filter rules (only food, only weapons, etc.)
- **Hauling labor**: dwarves physically move items between locations (transport as constraint)
- **Decay**: food rots, corpses rot, steel doesn't but bronze tarnishes

**Key mechanics:**
- **Skill affects quality**: novice mason produces "crude" furniture, legendary mason produces "artifact" with unique name + history
- **Crafting recipes** with input + skill + tool requirements
- **Trade caravans** (annual): barter system, no fixed prices, value based on material + quality + decoration
- **Item history**: tracks creator, kills (for weapons), engravings — full provenance

**LoreWeave applicability:**
- ✅ **Item history/provenance** = template for V2+ unique items (Mặc Vô Kiếm có lịch sử)
- ✅ **Material × quality × wear** = template for unique-item attribute model
- ✅ **Hauling labor** = template for NPC physical transport (xuyên không slip mechanic)
- ✅ **Stockpile filter rules** = template for cell storage configuration
- ❌ DF's complete simulation depth is overkill for V1; cherry-pick for V2+ unique items

### G7. RimWorld (Ludeon, 2018) — needs-based consumption

**Genre:** Colony simulation with character emphasis.

**Resource model:**
- **Per-pawn needs**: Food, Rest (sleep), Joy, Comfort, Mood, Beauty, Outdoors. Each decays over time, requires action.
- **Per-pawn inventory** with weight cap
- **Stockpile zones** (similar to DF)
- **Silver** as currency, traded with caravans
- **Materials** (steel, wood, cloth, plasteel, gold) for construction + crafting
- **Health** as multi-part body system (each limb/organ tracked)

**Key mechanics:**
- **Mood-driven behavior**: pawn mood < threshold → mental break (berserk, sad-wander, run-away)
- **Need decay rates** balanced for ~24 in-game-hour cycles
- **Trade caravans** appear randomly with different inventories
- **Refrigeration** prevents food spoilage
- **Storyteller AI** drives random events (raids, weather, traders)

**LoreWeave applicability:**
- ✅ **Per-character needs with decay** = template for V1+ hunger/thirst/rest loops (deferred Q5)
- ✅ **Mood as derived from needs** = template for LLM persona state (Hungry → grumpy → bad dialogue)
- ✅ **Storyteller-driven events** = matches LoreWeave's LLM Generator pattern (EVT-G)
- ✅ **Body-part health** = template for granular wound system V2+ (Wounded extends per-limb)

### G8. Victoria 3 (Paradox, 2022) — pop-driven economy

**Genre:** Grand strategy, economic emphasis.

**Resource model:**
- **Pop-as-economic-agent**: each population stratum has needs (food, basic luxuries, common luxuries, etc.), wages, savings
- **Goods market**: each good has supply/demand → dynamic price within market region
- **Production methods**: each industry can choose technology level (low-tech vs high-tech) — different input/output ratios
- **Construction sector**: building queue with construction-points cost
- **Trade routes** between markets with trade capacity

**Key mechanics:**
- **Supply/demand price** is the core: oversupply → price drops → industry unprofitable → workers fired → unemployment → starvation OR migration
- **Pop happiness** depends on wages + needs satisfaction + social status
- **Class stratification**: Capitalists, Aristocrats, Workers, Peasants — each has different needs profile + income source
- **Currency**: gold standard / fiat / GDP — abstract macro-economic indicators
- **Investment pool**: capitalists invest in new buildings autonomously

**LoreWeave applicability:**
- ✅ **Supply/demand dynamic price** = template for V2+ market price discovery
- ✅ **Pop-as-agent with needs** = template for NPC daily-life consumption (each NPC = 1 pop equivalent)
- ✅ **Class stratification** = template for NPC tier needs profiles (peasant vs scholar vs noble)
- ✅ **Multi-method production** = template for V2+ technology unlocks
- ❌ Macroeconomic abstraction (GDP, market regions) is V3+ scope

### G9. Europa Universalis 4 (Paradox, 2013) — trade nodes + inflation

**Genre:** Grand strategy, mercantilism era.

**Resource model:**
- **Ducats** (gold currency)
- **Manpower** (military pool)
- **Sailors** (navy pool)
- **Monarch points**: Admin, Diplomatic, Military — abstract "ruler attention" resource
- **Trade goods** (~30 types): produced by provinces, valued at trade nodes
- **Inflation** — % drag on income, accumulates from minting (currency sink mechanic)

**Key mechanics:**
- **Trade nodes** (~80 worldwide) form a directed graph; trade flows from peripheral nodes to home node
- **Trade power** (% control of node) determines % of trade value collected
- **Minting** generates currency at cost of inflation (controlled-inflation knob)
- **Loans** with interest (debt-based currency expansion)
- **Stability** (modifier resource, -3 to +3) affects everything

**LoreWeave applicability:**
- ✅ **Inflation as controlled mechanic** = template for V2+ currency-sink design (open economy needs sinks)
- ✅ **Trade node graph** = template for V2+ supply-network model
- ✅ **Loans with interest** = V3+ banking module template
- ❌ Empire-level abstraction doesn't match per-character

### G10. Patrician IV / Port Royale (Kalypso, 2010) — trade-economic core

**Genre:** Trade simulation in historical setting.

**Resource model:**
- **Gold** (currency)
- **Trade goods** (~20 commodities: grain, fish, wine, cloth, weapons, etc.)
- **Per-city supply/demand** with dynamic price
- **Ships** with cargo capacity + speed + crew + condition
- **Reputation** per city (affects trade access + missions)
- **Buildings** (workshop, warehouse) generate goods + provide income

**Key mechanics:**
- **Buy low, sell high** is the core gameplay loop
- **Per-city price variance**: same good costs different prices in different cities
- **Production buildings** with input/output (e.g., brewery: grain in → beer out)
- **Convoy management**: assign ships to auto-trade routes
- **Pirate raids** as random events (currency sink)
- **Reputation gating**: high rep unlocks premium trade contracts

**LoreWeave applicability:**
- ✅ **Per-location price variance** = essential V2 trade module
- ✅ **Convoy auto-trade** = template for NPC-AI-driven trade
- ✅ **Reputation gating** = template for faction reputation effect on trade
- ✅ **Buildings as production source** = matches cell-as-producer

---

## §3 — Recurring patterns synthesis (12 dimensions)

Cross-cutting patterns that appear in 5+ of the 10 reference games. These are the **stable design dimensions** that LoreWeave RES_001 should accommodate (V1 implements subset; V2+ extends without schema break).

### P1. Resource categorization (8/10 games — universal)

Every strategy/sim game uses **multiple resource categories with distinct rules**. Categorization axes:
- **Numeric pool** (gold, food count, manpower) vs **Identity-tracked** (specific item, named character)
- **Body-bound / actor-bound** (HP, mood) vs **Portable** (gold, goods)
- **Universally fungible** (gold) vs **Regionally fungible** (M&B trade goods with price variance) vs **Non-fungible** (DF artifact weapon)
- **Direct-consume** (food → satiety) vs **Exchange-medium** (gold → buy anything)
- **Produced-and-consumed** (gold cycles) vs **Consumed-only** (manpower, depletes from war) vs **Produced-only** (renown, accumulates)

**LoreWeave V1 minimum:** 4 categories (Vital / Consumable / Currency / Material). **V2+:** add Item-unique + Property + Social-currency (Prestige/Reputation/Influence). **V3+:** add Knowledge/Information as resource (CK3 secrets pattern).

### P2. Owner = entity (10/10 games — universal)

Every game ties resources to an owner: pop / character / building / city / nation / empire. **Owner type varies but is always typed**. CK3 = character; M&B = character; Civ = city/empire; Anno = island; DF = item-instance owned by stockpile/dwarf.

**LoreWeave:** Owner = `EntityRef` (PC / NPC / Cell / Item / Faction-V2+). Already aligned with EF_001.

### P3. Production model — time-driven OR action-driven OR both (10/10)

| Pattern | Games using | LoreWeave fit |
|---|---|---|
| **Time-driven (auto-accrual)** | Civ, CK3, Stellaris, Anno, EU4 | ✅ EVT-G2 FictionTimeMarker — V1 use |
| **Action-driven (PC harvest)** | RimWorld, DF, M&B (smithing) | ✅ PL_005 Use kind — V1 use |
| **Hybrid (passive + bonus)** | Anno (auto + warehouse), M&B (workshop + manual trade) | ✅ V1+ extension |
| **NPC-job-driven** | Stellaris (pop jobs), Vic3 (employment) | ✅ V2+ NPC AI feature |

**LoreWeave V1:** time-driven + action-driven. **V2+:** add NPC-job-driven.

### P4. Consumption model — needs-based, action-cost, time-decay (9/10)

| Pattern | Games using | Mechanism |
|---|---|---|
| **Needs-based decay** | RimWorld, Vic3, Anno (pop tier needs), CK3 (food at events) | Per-fiction-day decay; satisfied by consume action |
| **Action-cost** | M&B (combat → wound), DF (mining → tool wear), Civ (build → production cost) | Per-action atomic deduction |
| **Time-decay** | Banished (food spoils), DF (corpses rot), EU4 (manpower regen but slow) | Per-fiction-tick passive |
| **Maintenance recurring** | All strategy (army wages, building upkeep) | Per-fiction-period recurring sink |

**LoreWeave V1:** action-cost only (PL_005-driven). **V1+30d:** add needs-based for hunger loop. **V2+:** add maintenance + time-decay for full economy.

### P5. Transfer mechanisms — universal classes (10/10)

Every game has all of: **trade (consensual exchange), gift (one-way no-consideration), theft (forced transfer), loot (post-mortem transfer), production (creation), consumption (destruction)**.

**LoreWeave:** All map to PL_005 Interaction kinds:
- Trade → V1: Give (consideration via reciprocal Give); V1+: dedicated Trade kind
- Gift → V1: Give kind (already exists)
- Theft → V1: Strike kind cascade (deferred); V1+: dedicated Steal kind
- Loot → V1: Examine + Use on corpse; V1+: dedicated Loot kind via WA_006 cascade
- Production → V1: EVT-T5 Generated (no PL_005 path needed)
- Consumption → V1: PL_005 Use kind

### P6. Conservation laws — open economy with sinks dominates (8/10)

| Model | Games | Notes |
|---|---|---|
| **Closed economy** | Banished (small-scale only), DF (small caravan trade) | Only viable for small-scale |
| **Open + multiple sinks** | All grand strategy (Civ, EU4, CK3, Stellaris, Vic3), Anno, M&B | DOMINANT pattern |
| **Open + no sinks** | RimWorld (early game), casual sims | Causes inflation; not used at scale |

**Standard sinks observed:**
- Building maintenance / upkeep (Anno, Civ, CK3 holdings)
- Army wages (M&B, EU4, Civ, CK3)
- Inflation (EU4 — explicit; Civ — implicit via cost scaling)
- Decay/spoilage (DF, RimWorld, Banished)
- Loss to events (raids, fires, pirates) — random sinks
- Tax to higher tier (CK3 vassal-to-liege, EU4 estates)
- Tribute / diplomatic gifts (Civ, EU4)

**LoreWeave V1 recommendation update:** open economy with **at least 2 V1 sinks** even if minimal:
- Sink 1: NPC daily consumption (food → eaten over time, even V1 minimal)
- Sink 2: Item wear / breakage (V1+30d if not V1)

Without sinks, currency hoarding by NPCs creates dead-economy state at scale. Cheaper to design sinks in from V1 than retrofit.

### P7. Storage / capacity (7/10)

| Pattern | Games | LoreWeave V1 fit |
|---|---|---|
| **Unlimited universal pool** | Civ (yields, gold), CK3 (gold), EU4 (ducats) | V1 default — simple |
| **Per-actor inventory cap (weight or slots)** | M&B, RimWorld, Kenshi, DF | V1+ extension |
| **Per-building storage** | Anno (warehouse), DF (stockpile), Banished | V2+ for complex chain |
| **Stockpile with filter rules** | DF, RimWorld | V2+ |

**LoreWeave V1:** unlimited. **V1+30d:** per-PC weight cap. **V2:** per-cell storage cap.

### P8. Trade price models (8/10 games have at least one)

| Model | Games | V1 fit |
|---|---|---|
| **Fixed price (canonical)** | Civ basic mode | V1 default — author-declared in RealityManifest |
| **Per-NPC variance** | M&B, Patrician (each city has own price), Kenshi | V1+ — author-declared per-cell + LLM-narrated |
| **Supply/demand dynamic** | Vic3, Anno, EU4 (trade nodes), Stellaris (Galactic Market) | V2+ — needs market simulation |
| **Barter (no money)** | DF, RimWorld (with caravans), Kenshi (early game) | V1+ — implementable as Trade with non-currency consideration |

**LoreWeave V1:** fixed price (author-declared in RealityManifest per resource kind per region). **V1+30d:** per-cell variance. **V2:** supply/demand.

### P9. Quality / grade variation (5/10)

DF (artifact tier), M&B (item tier), Kenshi (item rarity), Diablo (random affixes), CK3 (cultural artifact tier).

**LoreWeave V1:** none (uniform). **V2:** add tier-based grade for crafted items + consumables.

### P10. Decay / spoilage (5/10)

DF, RimWorld, Banished (food), EU4 (inflation), Stellaris (rare item degradation in some events).

**LoreWeave V1:** none. **V1+30d:** food spoilage if hunger loop added (Q5). **V2:** equipment wear.

### P11. Production chains (multi-step recipes) (4/10)

Anno (deepest), Banished, Frostpunk, Vic3.

Pattern: input₁ + input₂ + ... + skill + tool → output (with skill/quality variance). Often nested: ore → ingot → tool → weapon.

**LoreWeave V1:** none (cells produce direct outputs, no chains). **V2:** add Recipe aggregate + crafting feature.

### P12. Faction / aggregate-tier ownership (8/10)

Per-character resources at one tier; pooled at higher tier (faction, town, empire).

| Tier | Games |
|---|---|
| **Per-character** | CK3, M&B, RPG-leaning |
| **Per-building/cell** | Anno, DF, Banished, Stellaris (planet) |
| **Per-region/town** | Anno (island), Civ (city), Total War (province) |
| **Per-faction/empire** | Civ, EU4, Stellaris, Total War |

**LoreWeave V1:** per-character (PC/NPC) + per-cell (cell-as-entity owns its production output until harvested). **V2:** per-town aggregation. **V3:** per-faction.

---

## §4 — LoreWeave phase mapping (V1 / V1+30d / V2 / V3)

Based on §3 patterns, here's the recommended phase rollout for resource + economy features:

### V1 (initial ship — turn-based RPG core with simulation foundation)

**Aggregate shape (final, no migration needed for V2+):**
- 1 aggregate `resource_pool` (T2/Reality, scope-flexible)
- Owner: `EntityRef` (PC / NPC / Cell / Item / Faction-V2+)
- Pool entries: `Vec<ResourceBalance>` where each `ResourceBalance { kind: ResourceKind, amount: u64, instance_id: Option<ItemInstanceId> }`
- ResourceKind enum (extensible per EVT-A11 sub-type ownership):
  - V1: `Vital(VitalKind)` / `Consumable(ConsumableKind)` / `Currency(CurrencyKind)` / `Material(MaterialKind)`
  - V1+30d reserved: `Item(ItemKind)` / `SocialCurrency(SocialKind)` / `Knowledge(KnowledgeKind)`

**Mechanics shipped V1:**
- Time-driven production (cell-tier place owns ProducerProfile; EVT-G2 FictionTimeMarker)
- Action-driven consumption (PL_005 Use kind)
- Action-driven transfer: Trade (PL_005 Give kind reciprocal), Gift (PL_005 Give kind one-way), Theft (PL_005 Strike kind cascade)
- Open economy with **2 minimum sinks**: NPC food consumption (per-fiction-day) + production cap (cell storage limited V1+)
- Body-bound flag on Vital kinds (HP/Stamina non-transferable)
- HP=0 → MortalityTransitionTrigger emit → WA_006 consumes
- Wounded status (PL_006) = derived from HP threshold

**Author-declared in RealityManifest V1:**
- `resources: Vec<ResourceDecl>` — initial distribution
- `producers: Vec<ProducerProfile>` — cell-tier place producer rates
- `prices: HashMap<ResourceKindId, Price>` — fixed price per kind (author canonical)

### V1+30d (within 30 days of V1 ship — RES_002 + PL_005 closure extensions)

- Add `Item(ItemKind)` to ResourceKind (unique items with `ItemInstanceId` + history)
- Add inventory weight cap per PC/NPC (CapacityProfile in entity_binding)
- Add cell storage cap (CellStorageProfile in PF_001 extension)
- Add hunger/thirst loop (PL_006 Status `Hungry` derived from food-since-last-meal counter)
- Add equipment wear (per-instance condition counter)
- Add per-cell price variance (RealityManifest extends `prices` to per-region)

### V2 (months out — Economy module)

- New feature folder `13_economy/` with ECO_001..ECO_NNN
- Production chains (Recipe aggregate + crafting feature)
- Supply/demand dynamic prices (Market aggregate per region)
- Trade routes (TradeRoute aggregate; convoys auto-running)
- Per-town resource aggregation (Town aggregates cell production)
- NPC-job system (NPC has Occupation; LLM decides production allocation)
- Maintenance/upkeep recurring sinks
- Quality grade tier (3-tier or 5-tier per kind)
- Decay/spoilage for food + organics
- Add `SocialCurrency(SocialKind)` (Prestige/Reputation/Influence) for V2 social mechanics

### V3 (long-term — Strategy module)

- Per-faction treasury aggregation
- Hierarchical income flow (cell → town → faction)
- Loans + debt (banking sub-feature)
- Inflation mechanic (controlled currency sink at faction level)
- Tax system (% flow from lower tier to upper tier)
- Diplomatic deals (resource-for-resource between factions)
- Galactic-Market-equivalent: cross-faction commodity exchange
- Knowledge/Information as resource (CK3 secrets pattern; LLM tracks who-knows-what)
- Resource scarcity events (raids, harvest failures, plagues — EVT-G triggers)

### V3+ (research frontier — not committed)

- Pop-system (each NPC = pop with class stratification — Vic3 model)
- Macroeconomic indicators (GDP equivalent per reality)
- AI-driven economic balance (LLM proposes adjustments to author)
- Cross-reality trade (multiverse arbitrage) — currently OUT of scope per R5 anti-pattern policy

---

## §5 — Updated Q1-Q7 recommendations (incorporating findings)

The original CONCEPT_NOTES §5 recommendations were RPG-shaped. Here's the revised set after surveying strategy/sim games:

### Q1 — V1 Resource categories: which to include?

**ORIGINAL recommendation:** Option A (4 categories — Vital / Consumable / Currency / Material).

**REVISED recommendation:** **Option A (4 categories) confirmed, BUT**:
- Reserve `ResourceKind` enum with V1+30d / V2 / V3 variants explicitly named (not "future") so RES_001 design doc enumerates the full forward-compatible set
- Add explicit field `instance_id: Option<ItemInstanceId>` to ResourceBalance V1 (always None for V1, becomes Some in V1+30d when Item kind ships) — no schema migration needed

**Rationale:** §3 P1 + §4 V1+30d show Item-unique is high-priority next-step. Reserving the field shape now prevents schema break.

### Q2 — Conservation: closed economy or open with sinks?

**ORIGINAL recommendation:** Option B (open + sinks).

**REVISED recommendation:** **Option B (open + sinks) STRONGLY confirmed**, but **V1 must ship at least 2 sinks** (not "no sinks V1"):
- Sink 1: NPC daily food consumption (Generator-driven per-fiction-day, even if minimal)
- Sink 2: Cell production cap (storage stops at threshold; producer NPC must move/sell to clear)

**Rationale:** §3 P6 shows 8/10 strategy games use open+sinks; "no sinks V1" creates dead-economy by NPC hoarding within first reality lifetime. Cheaper to design sinks in V1 than retrofit. Sinks above are minimal (one per axis: consumption + production), don't bloat V1 design.

### Q3 — HP/Stamina là Resource hay tách Vital tier riêng?

**ORIGINAL recommendation:** Option A (unified ResourceKind with Vital variant).

**REVISED recommendation:** **Option A (unified) confirmed**.

**Rationale:** §3 P2 + §4 V1 — single aggregate `resource_pool` simpler; flags handle differential rules. Matches PL_006 pattern (single actor_status aggregate for all 4 status flags).

### Q4 — Production trigger model: auto vs action vs hybrid?

**ORIGINAL recommendation:** Option A (auto-only V1).

**REVISED recommendation:** **Option C (hybrid) — V1 ships BOTH auto + action**:
- Auto: cells produce per fiction-time (EVT-G2 FictionTimeMarker)
- Action: PC can harvest manually (PL_005 Use kind on cell-as-target) — empties cell stockpile + bonus
- This is the M&B workshop pattern (passive income + manual interaction option)

**Rationale:** §3 P3 shows hybrid is dominant for player-facing content. Auto-only is too "set and forget"; action-only forces grinding. Both paths use already-LOCKED infrastructure (EVT-G + PL_005), no new mechanism.

### Q5 — V1 hunger loop: skip eating → HP loss?

**ORIGINAL recommendation:** Option A (no hunger V1).

**REVISED recommendation:** **Option B (soft hunger V1)** — minimal per-fiction-day food-tick:
- Per-fiction-day: -1 food from inventory; if 0 → apply Status Effect `Hungry` (PL_006)
- 3+ days hungry → apply `Starving` (PL_006 reserved variant)
- 7+ days starving → emit MortalityTransitionTrigger (WA_006)
- No active HP damage in V1 (statuses do the damage via PL_006 modifiers V1+30d)

**Rationale:** §3 P4 shows 9/10 sim games have needs-based decay; pure "no consumption V1" creates passive-economy where food becomes an unused stockpile. Soft hunger via PL_006 statuses (already designed) is cheap to implement, justifies food production existence, and creates V1 player tension. AND it serves as the "Sink 1" required by Q2 revised recommendation.

### Q6 — Capacity limits (inventory cap, cell storage cap) V1?

**ORIGINAL recommendation:** Option A (no caps V1).

**REVISED recommendation:** **Option B-modified (cell cap V1, no PC cap V1)**:
- Cell storage cap: yes (provides Sink 2 from Q2 revised — production stops at cap)
- PC inventory cap: no (defer to V1+30d; weight cap requires per-item weight metadata which depends on Item kind not in V1)

**Rationale:** §3 P7 + Q2 — cell cap is the cheaper sink (cell production has author-declared cap; trivial to enforce). PC cap is more invasive (requires weight metadata across all kinds). Split.

### Q7 — Quality / grade variation V1?

**ORIGINAL recommendation:** Option A (no grade V1).

**REVISED recommendation:** **Option A (no grade V1) confirmed**.

**Rationale:** §3 P9 + §4 V2 — quality is a V2 feature tied to crafting/recipes. V1 single-rate keeps trade math simple.

---

## §6 — New questions surfaced by survey (Q8-Q12)

Strategy/sim game patterns surface 5 new questions not in original CONCEPT_NOTES Q1-Q7:

### Q8 — Aggregate-tier ownership: per-character only V1, or per-cell too V1?

**Context:** §3 P12 — strategy games typically have ownership at multiple tiers. LoreWeave's "cell-as-entity owns production" implies cell-tier ownership.

**Options:**
- (A) **Per-character only V1**: Cell production materializes as event → goes to cell-owner-PC's inventory immediately (no cell-tier balance). Simpler.
- (B) **Per-character + per-cell V1**: Cell has own resource_pool entry (treasury). Production accrues there. PC must "harvest" or cell auto-distributes to owner over time.

**Recommendation:** **Option B**. Required by Q4 hybrid (auto + action) — cell needs own balance for harvest target. Also natural for V2 town aggregation (town = sum of cell balances).

### Q9 — Who is the cell owner V1? Author-declared or PC-claimable?

**Context:** Cell as entity needs an owner. M&B has "buy workshop"; Anno has "build building"; CK3 has "fief grant".

**Options:**
- (A) **Author-declared V1**: RealityManifest declares cell ownership at creation. PC can't change it V1.
- (B) **PC-claimable V1**: PC can buy/claim cells in-game.
- (C) **Mixed V1**: Author seeds initial; PC can buy via Trade transaction.

**Recommendation:** **Option A (author-declared V1)**. Claiming/buying cells = entire feature surface (real-estate-as-feature) — defer V2. V1 cells have author-canonical owner; ownership transfer V2+.

### Q10 — Currency denominations V1: 1 kind or hierarchical (đồng/lượng bạc/lượng vàng)?

**Context:** Vietnamese xianxia/wuxia tone implies multi-tier currency (đồng = copper, lượng bạc = silver tael, lượng vàng = gold tael). CK3 has single gold; M&B has single denar; CK3 fluid; Anno uses single gold.

**Options:**
- (A) **Single currency V1**: Đồng only. Multi-tier V1+.
- (B) **3-tier currency V1**: Đồng / lượng bạc / lượng vàng with author-declared exchange rate.
- (C) **Author-configurable V1**: RealityManifest declares N currencies with cross-rates. RES_001 doesn't fix kinds.

**Recommendation:** **Option C (author-configurable)**. Reality Manifest extension allows author to declare 1 (default đồng) or N currencies. RES_001 owns the `Currency(CurrencyKind)` shape; CurrencyKind is author-declared per reality (not closed enum at RES_001 level). Pattern matches NPC_001 ActorId model — substrate fixes type, author declares instances.

### Q11 — Production rate balance: where is the source-of-truth?

**Context:** "Đồng lúa produces 5 rice per fiction-day" — where is "5" stored?

**Options:**
- (A) **In RealityManifest** (author-declared per ProducerProfile) — canonical
- (B) **In cell aggregate** (mutable runtime state) — drifts from author intent
- (C) **In cell aggregate + author override** (hybrid)

**Recommendation:** **Option A**. ProducerProfile is canonical (RealityManifest), cell aggregate caches the rate as immutable lookup. Mutability happens at the production EVENT (cell can have temporary modifiers from Status / Weather etc. V1+) but rate base is canonical.

### Q12 — Trade pricing V1: who sets the price?

**Context:** §3 P8 — V1 fixed price recommended. But "set by whom"?

**Options:**
- (A) **Author-declared global** (RealityManifest canonical price per kind) — Civ pattern
- (B) **Author-declared per-cell** (each cell has its own price) — M&B/Patrician pattern
- (C) **NPC-declared (LLM proposes)** — LLM-driven; risk drift

**Recommendation:** **Option A V1, B V1+30d**. Global canonical V1 (one price per kind per reality); per-cell variance V1+30d as RealityManifest extension. Option C V2+ with proper validators.

---

## §7 — V1 scope summary (revised after survey)

If user approves all REVISED recommendations (Q1-Q12), V1 scope becomes:

**Aggregates:**
- 1 new aggregate: `resource_pool` (T2/Reality, scope-flexible owner via EntityRef)
  - Cell-tier instances (per cell-as-entity owner)
  - Actor-tier instances (per PC/NPC owner)
  - Reality-tier instances (rare; faction-pool reserved V3)

**ResourceKind enum (forward-compatible, V1 ships subset):**
- V1 active: `Vital(VitalKind)` / `Consumable(ConsumableKind)` / `Currency(CurrencyKind)` / `Material(MaterialKind)`
- V1+30d reserved: `Item(ItemKind)`
- V2 reserved: `SocialCurrency(SocialKind)` / `Recipe(RecipeId)`
- V3 reserved: `Knowledge(KnowledgeKind)` / `Influence(InfluenceKind)`

**RealityManifest extensions (V1):**
- `resources: Vec<ResourceDecl>` — initial distribution
- `currencies: Vec<CurrencyDecl>` — author-declared currency kinds + cross-rates
- `producers: Vec<ProducerProfile>` — cell-tier producer rates
- `prices: HashMap<ResourceKindRef, Price>` — global canonical price per kind
- `cell_storage_caps: HashMap<PlaceTypeRef, u64>` — per-cell-type storage cap

**Mechanics V1:**
- Time-driven production (EVT-G2 FictionTimeMarker per fiction-day; cell ProducerProfile drives rate)
- Action-driven consumption (PL_005 Use kind)
- Action-driven transfer (PL_005 Give for trade/gift; Strike for theft)
- Hybrid harvest (PL_005 Use targeting cell empties cell stockpile to PC)
- Body-bound Vital (HP/Stamina non-transferable; flag-driven)
- HP=0 → MortalityTransitionTrigger emit
- Soft hunger loop (per-fiction-day food consumption; Hungry/Starving statuses via PL_006; 7-day starving → mortality)
- Cell storage cap V1 (Sink 2 — production halts at cap)
- Open economy V1 with 2 sinks (food consumption + cell cap)
- Author-declared global prices V1
- Author-declared cell ownership V1 (PC cannot claim)

**Defer to V1+30d (RES_002):**
- Item-unique kind (ItemInstanceId + history + provenance)
- PC inventory weight cap
- Per-cell price variance
- Equipment wear/condition

**Defer to V2 (Economy module — `13_economy/` folder):**
- Production chains (Recipe aggregate + crafting)
- Supply/demand dynamic prices
- Trade routes + convoys
- Per-town aggregation
- NPC-job system
- Quality grade tiers
- Maintenance/upkeep sinks
- Decay/spoilage

**Defer to V3 (Strategy module):**
- Per-faction treasury
- Hierarchical income flow (vassal → liege)
- Loans + banking
- Inflation mechanic
- Tax system
- Diplomatic resource exchange
- Knowledge/Information as resource

---

## §8 — Change log

- **2026-04-26** — Created. Initial 10-game survey + 12-pattern synthesis + 4-phase mapping (V1/V1+30d/V2/V3) + revised Q1-Q7 + new Q8-Q12. Companion to `00_CONCEPT_NOTES.md`.
