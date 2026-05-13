<!-- CHUNK-META
source: design-track manual seed 2026-04-26
chunk: cat_00_RES_resource.md
namespace: RES-*
generated_by: hand-authored (foundation-tier catalog seed)
-->

## RES — Resource Foundation (foundation tier; sibling of EF + PF + MAP + CSC; **5th and final V1 foundation feature**; value substrate for entities)

> Foundation-level catalog. Owns `RES-*` stable-ID namespace.
>
> | Sub-prefix | What |
> |---|---|
> | `RES-A*` | Axioms (locked invariants) |
> | `RES-D*` | Per-feature deferrals (across V1+30d / V2 / V3 phases) |
> | `RES-Q*` | Open questions (closure pass items) |

### Core architectural axioms

**RES-A1 (Owner = Entity):** Every resource unit is owned by exactly ONE EntityRef at a time (single-owner invariant per CONCEPT_NOTES axiom 1). Co-ownership / shared-ownership is V2+ feature. EntityRef = PC | NPC | Cell V1; Item V1+30d; Faction V3.

**RES-A2 (Vital body-bound non-transferable):** Body-bound vital resources (Hp/Stamina/Mana) live in `vital_pool` aggregate (separate from `resource_inventory`) and CANNOT be transferred between actors. Type-system enforced (no transfer event accepts vital_pool source/target). Q3 split LOCKED.

**RES-A3 (Open economy + sinks):** LoreWeave is open-economy (NPCs produce resources; resources exit world via sinks). V1 ships 3 sinks: food consumption (Q5 hunger) + cell maintenance cost (Q2c) + trade buy/sell spread (Q12b). Without sinks, NPC hoarding creates dead-economy at scale. (Per CK3/EU4/Civ/Stellaris/Vic3 8/10 reference games — see `01_REFERENCE_GAMES_SURVEY.md` §3 P6.)

**RES-A4 (Day-boundary tick model):** All time-driven production/consumption fires when fiction-time crosses fiction-day boundary. NOT continuous accrual; NOT per-turn; specifically per-day. Sleep 8h (no day-cross) → 0 production; Travel 5 days → 5 days' production batch-emitted. No float arithmetic V1.

**RES-A5 (Body-bound cell ownership for xuyên không):** Cell ownership follows the BODY entity, not soul (Q9c LOCKED). When PC's soul transmigrates into another body, old body's cell ownership chain transfers automatically to new soul. Vital pool follows body; resource_inventory.owner=Actor follows body's actor identity. PCS_001 owns the xuyên không mechanic; RES_001 documents the resource-side implication.

**RES-A6 (NPC finite liquidity):** NPC trade is constrained by NPC's actual `resource_inventory` balance (Q12c LOCKED). PC can deplete NPC; trade halts until NPC's cells produce more (Q4f auto-collect refills inventory). NPCs are economic agents with finite capacity, NOT trade-vending-machines. Validator RES-V3 enforces.

**RES-A7 (English IDs + i18n display):** All stable identifiers in code/schema/rule_ids are English `snake_case` (e.g., `resource.trade.npc_insufficient_funds`, `aggregate_type=vital_pool`, `VitalKind::Hp`). User-facing strings use `I18nBundle { default: String, translations: HashMap<LangCode, String> }` with English `default` required. RES_001 is the FIRST adopter; pattern propagates engine-wide. (See RES_001 §2.)

### Catalog entries

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| RES-1 | `vital_pool` aggregate (T2/Reality, body-bound, actor-only, NON-TRANSFERABLE) | ✅ | V1 | EF-1, DP-A14 | [RES_001 §4.1](../features/00_resource/RES_001_resource_foundation.md#41-vital_pool-aggregate) |
| RES-2 | `resource_inventory` aggregate (T2/Reality, portable, EntityRef-any) | ✅ | V1 | EF-1, DP-A14 | [RES_001 §4.2](../features/00_resource/RES_001_resource_foundation.md#42-resource_inventory-aggregate) |
| RES-3 | `ResourceKind` enum (5 V1 categories: Vital/Consumable/Currency/Material/SocialCurrency; forward-compat with V1+30d Item, V2 Recipe, V3 Knowledge/Influence) | ✅ | V1 | RES-1, RES-2 | [RES_001 §3.1](../features/00_resource/RES_001_resource_foundation.md#31-resourcekind-enum-forward-compatible-per-evt-a11) |
| RES-4 | `VitalKind` closed enum (V1: Hp + Stamina; V1+ Mana reserved) | ✅ | V1 | RES-1 | [RES_001 §3.2](../features/00_resource/RES_001_resource_foundation.md#32-engine-fixed-enums-closed-sets) |
| RES-5 | `SocialKind` closed enum (V1: Reputation only — wuxia/xianxia danh tiếng; V2: Prestige/Piety/Influence) | ✅ | V1 | RES-2 | [RES_001 §3.2](../features/00_resource/RES_001_resource_foundation.md#32-engine-fixed-enums-closed-sets) |
| RES-6 | Author-declared kinds (ConsumableKindId/CurrencyKindId/MaterialKindId — open per-reality via RealityManifest) | ✅ | V1 | RES-3 | [RES_001 §3.3](../features/00_resource/RES_001_resource_foundation.md#33-author-declared-kinds-open-per-reality) |
| RES-7 | `ResourceBalance` shape (`{ kind, amount: u64, instance_id: Option<ItemInstanceId> }` — instance_id reserved V1, used V1+30d Item kind, zero migration) | ✅ | V1 | RES-2 | [RES_001 §4.2](../features/00_resource/RES_001_resource_foundation.md#42-resource_inventory-aggregate) |
| RES-8 | `VitalProfile` shape + `RegenRule` enum (TimeBased/RestBased/Manual) + `OnZeroEffect` enum (EmitMortalityTrigger/ApplyStatus/NoOp) | ✅ | V1 | RES-1 | [RES_001 §4.1](../features/00_resource/RES_001_resource_foundation.md#41-vital_pool-aggregate) |
| RES-9 | Cell-as-economic-entity model (cell owns resource_inventory; ProducerProfile per PlaceType; NPC owner auto-collect daily; PC owner manual harvest) | ✅ | V1 | RES-2, PF-1 | [RES_001 §6.1](../features/00_resource/RES_001_resource_foundation.md#61-producerprofile-realitymanifest-declaration) |
| RES-10 | Day-boundary Generator tick model (4 V1 Generators: CellProduction → NPCAutoCollect → CellMaintenance → HungerTick) | ✅ | V1 | RES-1, RES-2, EVT-G2 | [RES_001 §10](../features/00_resource/RES_001_resource_foundation.md#10-generator-bindings) |
| RES-11 | Soft hunger loop V1 (PC+NPC symmetric; PL_006 Hungry magnitude 1→7; 7=mortality via WA_006 Starvation cause_kind) | ✅ | V1 | RES-2, PL-6, WA-6 | [RES_001 §7.2](../features/00_resource/RES_001_resource_foundation.md#72-hunger-tick-generator) |
| RES-12 | 3 V1 sinks (food consumption / cell maintenance cost / trade buy-sell spread) | ✅ | V1 | RES-2 | [RES_001 §7.1](../features/00_resource/RES_001_resource_foundation.md#71-consumption-sources-v1) |
| RES-13 | Body-bound cell ownership semantics (cell_owner field on entity_binding; xuyên không auto-inheritance via PCS_001 mechanic; orphan handling) | ✅ | V1 | EF-1 | [RES_001 §5.2](../features/00_resource/RES_001_resource_foundation.md#52-cell-ownership-q9-locked) |
| RES-14 | NPC finite liquidity validator (RES-V3 trade pricing + balance check) — NPCs are economic agents | ✅ | V1 | RES-2 | [RES_001 §8.3](../features/00_resource/RES_001_resource_foundation.md#83-npc-finite-liquidity-q12c-locked) |
| RES-15 | Author-configurable currencies (RealityManifest declares N currencies + cross-rates; default single Copper; multi-tier display via I18nBundle formatter) | ✅ | V1 | RES-3 | [RES_001 §2.4](../features/00_resource/RES_001_resource_foundation.md#24-author-content-example-vietnamese-xianxia-reality) + [§9](../features/00_resource/RES_001_resource_foundation.md#9-realitymanifest-extensions) |
| RES-16 | Global trade pricing (RealityManifest declares per-kind buy/sell spread; per-cell variance V1+30d) | ✅ | V1 | RES-2 | [RES_001 §8.2](../features/00_resource/RES_001_resource_foundation.md#82-trade-pricing-q12-locked) |
| RES-17 | RES-V1..V4 validator slots (ResourceBalanceCheck / VitalDepletionGuard / TradePricingValidator / MaintenanceLiquidityCheck) | ✅ | V1 | RES-1, RES-2, PL-5 | [RES_001 §11](../features/00_resource/RES_001_resource_foundation.md#11-validator-chain) |
| RES-18 | `resource.*` RejectReason namespace (12 V1 rule_ids + 3 V1+ reservations) | ✅ | V1 | RES-1..2 | [RES_001 §13.1](../features/00_resource/RES_001_resource_foundation.md#131-resource-namespace-registered-in-_boundaries02_extension_contractsmd-14) + [`_boundaries/02_extension_contracts.md` §1.4](../_boundaries/02_extension_contracts.md) |
| RES-19 | RealityManifest 9 OPTIONAL V1 extensions (resource_kinds / currencies / vital_profiles / producers / prices / cell_storage_caps / cell_maintenance_profiles / initial_resource_distribution / social_initial_distribution) | ✅ | V1 | RES-1..14 | [RES_001 §9](../features/00_resource/RES_001_resource_foundation.md#9-realitymanifest-extensions) + [`_boundaries/02_extension_contracts.md` §2](../_boundaries/02_extension_contracts.md) |
| RES-20 | EVT-T3 Derived sub-types (aggregate_type=vital_pool + aggregate_type=resource_inventory) | ✅ | V1 | RES-1, RES-2, EVT-A11 | [RES_001 §12.8](../features/00_resource/RES_001_resource_foundation.md#128-07_event_model-integration) |
| RES-21 | EVT-T5 Generated sub-types (4 V1 generators registered) | ✅ | V1 | RES-10, EVT-A11, EVT-G1..G6 | [RES_001 §10](../features/00_resource/RES_001_resource_foundation.md#10-generator-bindings) |
| RES-22 | EVT-T8 Administrative sub-shapes (Forge:EditCellProducerProfile / Forge:EditPriceDecl / Forge:EditCellMaintenanceCost / Forge:GrantInitialResources) | ✅ | V1 | RES-9, WA-3, EVT-A11 | [RES_001 §12.8](../features/00_resource/RES_001_resource_foundation.md#128-07_event_model-integration) |
| RES-23 | Engine-standard i18n contract (English IDs + I18nBundle for user-facing strings; cross-cutting type added to TurnEvent envelope §1 RejectReason.user_message) | ✅ | V1 | (cross-cutting) | [RES_001 §2](../features/00_resource/RES_001_resource_foundation.md#2-i18n-contract-new-cross-cutting-pattern) + [`_boundaries/02_extension_contracts.md` §1](../_boundaries/02_extension_contracts.md) |
| RES-24 | V1+30d — Item kind activation (ItemInstanceId + history + provenance per DF/M&B pattern; schema reserved V1) | 📦 | V1+ | RES-3, RES-7 | [RES_001 §15.1 RES-D1](../features/00_resource/RES_001_resource_foundation.md#151-v130d-res_002--within-30-days-of-v1-ship) |
| RES-25 | V1+30d — PC inventory weight cap enforcement (CapacityProfile schema reserved V1 on entity_binding via Q6b) | 📦 | V1+ | EF-1, RES-2 | [RES_001 §15.1 RES-D2](../features/00_resource/RES_001_resource_foundation.md#151-v130d-res_002--within-30-days-of-v1-ship) |
| RES-26 | V1+30d — Hydration loop (Thirsty status + water consumption tick) | 📦 | V1+ | PL-6 closure (add Thirsty status) | [RES_001 §15.1 RES-D5](../features/00_resource/RES_001_resource_foundation.md#151-v130d-res_002--within-30-days-of-v1-ship) |
| RES-27 | V1+30d — Per-cell price variance + RateModifier chain (Status/Weather/Skill multipliers) | 📦 | V1+ | RES-9, RES-16 | [RES_001 §15.1 RES-D3 + RES-D7](../features/00_resource/RES_001_resource_foundation.md#151-v130d-res_002--within-30-days-of-v1-ship) |
| RES-28 | V1+30d — Equipment wear / condition (per-instance condition counter on Item kind) | 📦 | V1+ | RES-24 | [RES_001 §15.1 RES-D4](../features/00_resource/RES_001_resource_foundation.md#151-v130d-res_002--within-30-days-of-v1-ship) |
| RES-29 | V1+30d — Multi-tier currency per-denomination tracking (V1 uses total-smallest-unit; V1+30d adds per-denomination + change-availability constraint) | 📦 | V1+ | RES-15 | [RES_001 §15.1 RES-D8](../features/00_resource/RES_001_resource_foundation.md#151-v130d-res_002--within-30-days-of-v1-ship) |
| RES-30 | V1+30d — PC-to-PC trade + PC-buy-from-NPC cell ownership transfer (PL_005 dedicated TradeKind/BuyKind extensions) | 📦 | V1+ | PL-5, RES-13 | [RES_001 §5.2](../features/00_resource/RES_001_resource_foundation.md#52-cell-ownership-q9-locked) |
| RES-31 | V2 — Production chains (Recipe aggregate + crafting feature; multi-step input → output chains per Anno/Banished pattern) | 📦 | V2 | RES-2 | [RES_001 §15.2 RES-D11](../features/00_resource/RES_001_resource_foundation.md#152-v2-economy-module--13_economy-folder-future) |
| RES-32 | V2 — Supply/demand dynamic prices (Market aggregate per region; Vic3/EU4 trade nodes pattern) | 📦 | V2 | RES-2, RES-16 | [RES_001 §15.2 RES-D12](../features/00_resource/RES_001_resource_foundation.md#152-v2-economy-module--13_economy-folder-future) |
| RES-33 | V2 — Trade routes + convoys (TradeRoute aggregate; auto-running per Anno/Civ/Stellaris) | 📦 | V2 | RES-2 | [RES_001 §15.2 RES-D13](../features/00_resource/RES_001_resource_foundation.md#152-v2-economy-module--13_economy-folder-future) |
| RES-34 | V2 — Per-town aggregation (Town aggregates cell production; vassal-tier income flow) | 📦 | V2 | PF-1 | [RES_001 §15.2 RES-D14](../features/00_resource/RES_001_resource_foundation.md#152-v2-economy-module--13_economy-folder-future) |
| RES-35 | V2 — NPC-job system (Occupation per NPC; LLM allocates labor; Stellaris/Vic3 pop-based pattern) | 📦 | V2 | NPC-1, RES-2 | [RES_001 §15.2 RES-D15](../features/00_resource/RES_001_resource_foundation.md#152-v2-economy-module--13_economy-folder-future) |
| RES-36 | V2 — Quality grade tiers (DF/M&B pattern; affects exchange rate + crafting yield) | 📦 | V2 | RES-31 | [RES_001 §15.2 RES-D16](../features/00_resource/RES_001_resource_foundation.md#152-v2-economy-module--13_economy-folder-future) |
| RES-37 | V2 — Maintenance/upkeep recurring sinks at multiple tiers (army wages / building upkeep V1+) | 📦 | V2 | RES-12 | [RES_001 §15.2 RES-D17](../features/00_resource/RES_001_resource_foundation.md#152-v2-economy-module--13_economy-folder-future) |
| RES-38 | V2 — Decay/spoilage (food rots; equipment tarnishes; DF/RimWorld pattern) | 📦 | V2 | RES-2 | [RES_001 §15.2 RES-D18](../features/00_resource/RES_001_resource_foundation.md#152-v2-economy-module--13_economy-folder-future) |
| RES-39 | V3 — Per-faction treasury aggregation (Civ/EU4/CK3 empire-tier pool) | 📦 | V3 | EF-1 (Faction variant) | [RES_001 §15.3 RES-D19](../features/00_resource/RES_001_resource_foundation.md#153-v3-strategy-module--future) |
| RES-40 | V3 — Hierarchical income flow (vassal → liege; cell → town → faction; CK3 pattern) | 📦 | V3 | RES-39 | [RES_001 §15.3 RES-D20](../features/00_resource/RES_001_resource_foundation.md#153-v3-strategy-module--future) |
| RES-41 | V3 — Loans + banking + interest (EU4 banking sub-feature) | 📦 | V3 | RES-39 | [RES_001 §15.3 RES-D21](../features/00_resource/RES_001_resource_foundation.md#153-v3-strategy-module--future) |
| RES-42 | V3 — Inflation mechanic (controlled currency sink at faction level; EU4 minting model) | 📦 | V3 | RES-39 | [RES_001 §15.3 RES-D22](../features/00_resource/RES_001_resource_foundation.md#153-v3-strategy-module--future) |
| RES-43 | V3 — Tax system (% flow lower→upper tier; CK3/EU4) | 📦 | V3 | RES-40 | [RES_001 §15.3 RES-D23](../features/00_resource/RES_001_resource_foundation.md#153-v3-strategy-module--future) |
| RES-44 | V3 — Diplomatic resource exchange (Civ/EU4 deal pattern; cross-faction gifting + tribute) | 📦 | V3 | RES-39 | [RES_001 §15.3 RES-D24](../features/00_resource/RES_001_resource_foundation.md#153-v3-strategy-module--future) |
| RES-45 | V3 — `Knowledge(KnowledgeKind)` activation (CK3 secrets pattern; LLM tracks who-knows-what; political leverage) | 📦 | V3 | RES-3 | [RES_001 §15.3 RES-D25](../features/00_resource/RES_001_resource_foundation.md#153-v3-strategy-module--future) |
| RES-46 | V3 — `Influence(InfluenceKind)` activation (political/factional leverage; CK3/Stellaris pattern) | 📦 | V3 | RES-3 | [RES_001 §15.3 RES-D26](../features/00_resource/RES_001_resource_foundation.md#153-v3-strategy-module--future) |
| RES-47 | V3+ — Pop-system (each NPC = pop with class stratification; Vic3 model — research frontier) | 🔬 | V3+ | NPC-1, RES-35 | [RES_001 §15.3](../features/00_resource/RES_001_resource_foundation.md#153-v3-strategy-module--future) |
| RES-48 | OUT OF SCOPE — Cross-reality trade (multiverse arbitrage; conflicts with R5 anti-pattern policy) | 🚫 | n/a | (out) | [RES_001 §15.3 RES-D27](../features/00_resource/RES_001_resource_foundation.md#153-v3-strategy-module--future) |

### V1 minimum delivery

12 V1 catalog entries (RES-1..23 all ✅ V1) — comprehensive value substrate for foundation tier completion. RES_001 ships:

- **2 aggregates** (vital_pool body-bound + resource_inventory portable)
- **5 ResourceKind categories** (Vital/Consumable/Currency/Material/SocialCurrency) with engine-fixed + author-declared sub-enums
- **3 V1 sinks** for open-economy balance (food / cell maintenance / trade spread)
- **4 V1 Generators** day-boundary tick (production + auto-collect + maintenance + hunger)
- **4 V1 RES-V validator slots** (balance check + vital depletion + trade pricing + maintenance liquidity)
- **12 V1 rule_ids** under `resource.*` namespace + 3 V1+ reservations
- **9 OPTIONAL RealityManifest extensions** (all engine-defaulted)
- **25 forward-looking deferrals** (V1+30d / V2 / V3) with explicit RES-D1..27 IDs ensuring no scope creep

### V1+ deferred (RES-24..30)

7 deferrals planned for the 30-day fast-follow window after V1 ship. Most schema reservations already in place (Item via instance_id field; CapacityProfile via entity_binding optional field) — zero schema migration cost.

### V2+ deferred (RES-31..38)

8 deferrals for the **Economy module** (`13_economy/` folder, future) — production chains / supply-demand dynamic / trade routes / per-town aggregation / NPC jobs / quality grades / maintenance tiers / decay-spoilage. Per `01_REFERENCE_GAMES_SURVEY.md` mapping, this is where LoreWeave grows from RPG-with-resources into Anno/M&B/Vic3-tier sim/strategy.

### V3+ deferred (RES-39..47)

9 deferrals for the **Strategy module** — faction treasury / hierarchical income / banking / inflation / tax / diplomacy / Knowledge / Influence / pop-system. Per CK3/EU4 reference patterns. RES-48 is OUT OF SCOPE per R5 anti-pattern policy.

### Coordination / discipline notes

- **Foundation tier completion 5/5 (2026-04-26):** RES_001 closes V1 foundation tier. WHO (EF) + WHERE-semantic (PF) + WHERE-graph (MAP) + WHAT-inside-cell (CSC) + **WHAT-flows-through-entity (RES)** all DRAFT or higher.
- **Sibling boundary discipline:** Resource value/pool/transfer stays in RES_001. Status flags stay in PL_006 (Resource is numeric pool; Status is categorical). Death state machine stays in WA_006 (Resource provides HP=0 trigger). Stats modifiers stay in DF7 PC Stats V1+ (Resource = pool; Stats = modifier rate). Ownership scope stays in EF_001. Transfer mechanics stay in PL_005.
- **i18n NEW pattern propagation:** RES_001 §2 establishes engine-wide standard. Future feature designs SHOULD use English IDs + I18nBundle. Existing Vietnamese hardcoded reject copy is functional V1; cross-cutting audit deferred (low priority, cosmetic, doesn't block V1 functionality).
- **Body-substitution / xuyên không (Q9c):** PCS_001 brief at [`../features/06_pc_systems/00_AGENT_BRIEF.md`](../features/06_pc_systems/00_AGENT_BRIEF.md) needs §X update (downstream tracked) to fold in body-bound cell ownership inheritance — RES_001 documents resource-side; PCS_001 owns mechanic.
- **17 downstream impact items** tracked in [RES_001 §17.2](../features/00_resource/RES_001_resource_foundation.md#172-deferred-follow-up-commits-downstream-features) for follow-up commits (HIGH: PL_006 Hungry promotion / WA_006 Starvation / PL_005 trade+harvest rules / EF_001 fields / PCS_001 brief / 07_event_model 4 sub-types; MEDIUM/LOW: NPC_001 / WA_003 / PL_001 / PF_001 / i18n audit).
