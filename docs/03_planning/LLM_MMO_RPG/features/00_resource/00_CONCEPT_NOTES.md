# RES_001 Resource Foundation — Concept Notes

> **Status:** CONCEPT 2026-04-26 — awaiting user Q1-Q7 answers before promotion to RES_001 DRAFT.
>
> **Purpose:** Capture the brainstorm + gap analysis + open questions for the Resource Foundation feature. This is NOT a design doc; it is the seed material for the eventual `RES_001_resource_foundation.md` design.
>
> **Promotion gate:** When user has answered Q1-Q7 in §5, main session (or assigned agent) drafts `RES_001_resource_foundation.md` with locked V1 scope, claims `_boundaries/_LOCK.md`, registers ownership in matrix + extension contracts, and creates `catalog/cat_00_RES_resource.md`.

---

## §1 — User's core definition (5 axioms, 2026-04-26)

User-stated, in original Vietnamese (preserved verbatim for fidelity):

1. **Tài nguyên là 1 hoặc nhiều đơn vị giá trị thuộc sở hữu về 1 entity nhất định.** — Resource = 1+ units of value owned by some entity.
2. **Mỗi entity sẽ tiêu thụ 1 hoặc nhiều tài nguyên hoặc là không có cái nào.** — Every entity consumes 0+ resources.
3. **Mỗi entity sẽ tạo ra 1 hoặc nhiều tài nguyên hoặc không có cái nào.** — Every entity produces 0+ resources.
4. **NPC/PC sẽ sở hữu 1 hoặc nhiều tài nguyên.** — NPCs and PCs own 1+ resources (a strict subset of axiom 1).
5. **Tài nguyên có loại tiêu thụ trực tiếp bới entity hoặc làm giá trị trao đổi 1 hoặc nhiều entity hoặc các loại tài nguyên khác.** — Resources are either directly-consumed-by-entity OR exchange-value (currency-like).

### Implicit corollaries (from axioms)

- C1. Resource ownership is scoped to ONE entity at a time (axiom 1: "thuộc sở hữu về 1 entity nhất định"). → Implies single-owner invariant per resource unit. Shared/co-ownership = explicit V1+ extension.
- C2. Production and consumption are entity-properties, not resource-properties (axiom 2+3). → Each entity has its own producer/consumer profile.
- C3. Mode (consume vs exchange) is a property of the resource KIND, not the resource INSTANCE (axiom 5). → ResourceKind enum carries the mode.

---

## §2 — User's worked examples (2026-04-26)

User-provided concrete scenarios:

| # | Example | Entity type | Resource | Mode | Notes |
|---|---|---|---|---|---|
| E1 | NPC/PC have HP / Stamina / lương thực | Actor (PC/NPC) | HP, Stamina, food | direct-consume | Body-bound vital pool — non-transferable |
| E2 | NPC/PC own currency (đồng / lượng bạc) | Actor (PC/NPC) | gold/silver | exchange-value | Transferable; used to buy other resources/items |
| E3 | Tiểu điếm (cell) sản xuất tiền tệ | Cell-as-entity | gold currency | production-source | Inn produces revenue over time |
| E4 | Đồng lúa (cell) sản xuất lương thực | Cell-as-entity | rice (food) | production-source | Field produces food over time |
| E5 | Thành trấn = aggregate of cells, sản xuất nhiều loại tài nguyên theo thời gian | Place-aggregate | multiple kinds | production-source | Town = sum of constituent cell production |

### What examples cover well

- ✅ Body-bound resources (HP/Stamina) vs portable resources (food/currency)
- ✅ Direct-consume vs exchange-value distinction
- ✅ Cell-as-entity producing resources (binds to PF_001 cell-tier place)
- ✅ Aggregation pattern (Town = sum of cells)
- ✅ Time-driven production ("theo thời gian nhất định")

### What examples DO NOT cover

- ❌ Item-unique resources (1 thanh Mặc Vô Kiếm cụ thể, có lịch sử riêng) — user only mentioned fungible kinds
- ❌ Material resources (gỗ / sắt / quặng) — input to crafting, distinct from food (consumable) and currency (exchange)
- ❌ Quality / grade variation (gạo hảo hạng vs phế phẩm)
- ❌ Decay / spoilage (lương thực hết hạn?)
- ❌ Ownership transfer mechanics (atomic? consensual? trade vs theft vs gift vs loot?)
- ❌ Conservation laws (closed economy vs open with sinks?)
- ❌ Container / capacity (inventory cap? cell storage cap?)
- ❌ Hunger/thirst loop (skip eating → HP loss?)
- ❌ Production preconditions (đồng lúa cần seed/water/season?)
- ❌ Renewable vs depletable (mine that runs out)

---

## §3 — Gap analysis (10 dimensions A-J)

### A. Resource ontology — chỉ 2 mode là chưa đủ

User's axiom 5 distinguishes "direct-consume vs exchange-value" — but real V1 needs **at least 6 categories** with materially different behavior:

| Category | Examples | Fungible? | Body-bound? | Transferable? | Owner-stack policy |
|---|---|---|---|---|---|
| **Vital pool** | HP / Stamina / Mana | yes (numeric) | **YES** (đi với body, xuyên không?) | NO | Sum-clamped (0..max) |
| **Consumable** | lương thực / thuốc / nước | yes | no | yes | Sum (count) |
| **Currency** | đồng / lượng bạc / vàng | yes | no | yes | Sum (count) |
| **Material** | gỗ / sắt / quặng / da thú | yes | no | yes | Sum (count) |
| **Item (unique)** | 1 thanh Mặc Vô Kiếm cụ thể | **NO** | no | yes (1 instance) | Identity (each has ItemId) |
| **Property** | bản thân cell / nhà cửa | no (1-of-1) | no | yes (đắt đỏ) | Identity (each is unique entity) |

**Decision needed:** Q1 (V1 categories list).

### B. Lifecycle — resource có "trạng thái" không?

- **Decay / spoilage**: lương thực có hết hạn? Thuốc giảm hiệu lực?
- **Quality / grade**: cùng kind nhưng khác phẩm chất → khác giá trao đổi?
- **Provenance**: gạo từ ruộng nào? (kết nối WA_001 Lex contamination + WA_002 Heresy nếu gạo từ "thế giới khác")
- **Renewable vs depletable**: đồng lúa tự sinh, mỏ đào hết quặng

**Decision needed:** Q1 V1 minimum scope (default: no decay/no grade/no provenance V1; renewable/depletable both V1).

### C. Container / location — resource luôn ở ĐÂU đó

User's axiom 1 says "thuộc sở hữu về 1 entity" but doesn't define the **physical/logical container**:

- **Inventory** của PC/NPC — capacity hữu hạn? (Lý Minh không thể mang 1000kg lúa)
- **Kho** của cell — capacity hữu hạn? (tiểu điếm có két tiền giới hạn?)
- **Body** — container đặc biệt cho vital pool (HP/Stamina)
- **Property hierarchy** — gold trong két của tiểu điếm (cell), tiểu điếm thuộc Lý Minh (PC) → effective_owner = PC?

**Decision needed:** Q6 (capacity limits V1?).

### D. Production model — thiếu chi tiết

- **Rate / period**: bao lâu đồng lúa tạo 1 đơn vị? Gắn vào fiction-time (per MV12) hay per-turn?
- **Trigger source**:
  - Auto theo fiction-time (Generator-driven, EVT-G2 `FictionTimeMarker`)
  - Theo PC/NPC action (Interaction OutputDecl, PL_005)
  - Hybrid (auto-base + harvest-bonus)
- **Precondition / input**: đồng lúa cần seed + water + mùa vụ?
- **Cap**: kho đầy thì dừng sản xuất?
- **Dynamic rate**: rate thay đổi theo điều kiện (mùa vụ, thời tiết, kỹ năng PC)?

**Decision needed:** Q4 (production trigger model).

### E. Consumption model — thiếu hoàn toàn

- **Hunger/thirst loop**: PC không ăn → HP giảm theo fiction-time → tới ngưỡng → trigger WA_006 Mortality?
- **Tốc độ tiêu hao**: HP giảm khi nào? Stamina hồi phục khi nào?
- **Time-batch**: travel 8 giờ fiction → bao nhiêu HP/Stamina/Food tốn?
- **State-driven**: PL_006 Status Effects (Drunk/Exhausted) có modify consumption rate?

**Decision needed:** Q5 (V1 hunger loop?).

### F. Exchange / transfer — chỉ "trao đổi" là chưa đủ

User's axiom 5 nói "làm giá trị trao đổi" nhưng chưa phân biệt các cơ chế:

| Mechanism | Description | Atomic? | Consent? | V1 path |
|---|---|---|---|---|
| **Trade** | A↔B with consideration (mua bán) | yes | yes (both) | PL_005 Interaction Give kind extended? Or new TradeKind? |
| **Gift** | A→B no consideration | yes | yes (giver) | PL_005 Give already exists |
| **Theft** | A→B no consent | yes | NO | PL_005 Strike kind? Or new StealKind? |
| **Loot** | NPC chết → resource rơi → PC nhặt | per-pickup | implicit (corpse can't refuse) | WA_006 Mortality cascade + PL_005 Examine/Use? |
| **Production** | none → A (cell creates) | yes | n/a | EVT-T5 Generated (Generator framework) |
| **Consumption** | A → none (consumed by self/time) | yes | yes (self) or n/a (time) | PL_005 Use kind? Or auto via Generator? |

**Decision needed:** Q4 (which mechanisms V1) + boundary with PL_005.

### G. Conservation laws — quyết định game balance toàn cục

CỰC KỲ QUAN TRỌNG — quyết định cả chục feature về sau:

| Model | Description | V1 implications |
|---|---|---|
| **Closed economy** | Total currency in world conserved. NPC bán = NPC khác mua. | Cần balance đầu setup (RealityManifest currency_total). Khó scale; harder to design starter quests. |
| **Open economy + sinks** | NPC có thể spawn money (work/produce). Cần currency-sink (taxes, decay, theft cleanup). | Linh hoạt hơn; risk inflation if sinks under-tuned. Standard in most games. |
| **Hybrid** | Per-faction closed; cross-faction open. | Complex V1; defer to V2+. |

**Decision needed:** Q2 (closed vs open V1).

### H. Boundary intersections với feature đã LOCK

5 đụng độ cần xử lý cẩn thận trong RES_001 DRAFT:

| Đụng độ | Vấn đề | Hướng giải đề xuất |
|---|---|---|
| **PL_006 Status Effects** (Drunk/Exhausted/Wounded/Frightened) | "Wounded" có chồng lấp HP-low không? | **Status = categorical flag** (đã có); **Resource = numeric pool** (RES_001). Wounded có thể là **derived** từ HP threshold (read-side projection), KHÔNG ghi đè aggregate. Boundary: resource owns numeric value; status owns categorical state. |
| **WA_006 Mortality** | "death" condition ai phán? | Mortality vẫn giữ state machine. RES_001 cung cấp HP=0 → emit `MortalityTransitionTrigger` event → WA_006 consumer chạy state transition. Resource không owns death; chỉ owns "HP value reaches 0" signal. |
| **PCS_001 stats stub + DF7 PC Stats** | Stats vs Resource? | **Resource = pool tiêu hao/sản xuất** (HP, gold count). **Stats = modifier ảnh hưởng rate** (STR makes Stamina cost less per attack). KHÁC NHAU. PCS_001 chỉ giữ stats stub V1; DF7 expand V1+. RES_001 reference stats by name, không own giá trị. |
| **PL_005 Interaction OutputDecl** | Resource update qua đâu? | Reuse `OutputDecl { aggregate_type: "resource_*", ... }` — không cần path mới (giống PL_006 đã làm). PL_005 owns transfer kind/intent; RES_001 owns aggregate shape + invariants. |
| **EF_001 Entity Foundation** | Resource owned-by-entity → reference entity_binding | RES_001 aggregate references `EntityRef` (PC/NPC/Cell/Item). Owner field = `EntityRef`. Cascade: entity destroyed → resource ownership cascade per EF_001 §6.1 HolderCascade pattern. |

### I. Time semantics — fiction-time, không real-time

Per MV12: tất cả production/consumption gắn fiction-time (in-fiction clock), không real-time. Page-turn time-advancement (sleep/travel command compress 8h fiction in 1 turn) → cần **batch production/consumption** logic:

- 1 turn fiction = 5min → cell produces 0 (rate < threshold)
- 1 turn fiction = 8h (sleep) → cell produces 8 cycles batched as 1 EVT-T5 emission
- Determinism: replay must reproduce same batch counts (per EVT-A9 RNG determinism)

**Decision needed:** confirmed Q4 model + EVT-G integration shape.

### J. V1 scope discipline — phải cắt gọn

User's examples implicitly imply scope:
- **V1 minimum** (suggested default): HP / Stamina / food (consumable) / 1-currency-kind (đồng) + cell-production fixed-rate + simple PC inventory + Trade via PL_005 + atomic transfer + closed economy
- **V1+ (1-3 months)**: Material (gỗ/sắt) + crafting precondition / multi-currency / inventory capacity / production preconditions / hunger loop
- **V2+**: Item-unique with provenance / decay-spoilage / quality grades / national economy / contamination integration

**Decision needed:** Q1 + Q5 + Q6 + Q7 lock V1 cut.

---

## §4 — Boundary intersections summary table

| Touched feature | Status | RES_001 owns | Other feature owns | Integration mechanism |
|---|---|---|---|---|
| EF_001 Entity Foundation | CANDIDATE-LOCK | Resource ownership (Owner = EntityRef) | EntityRef + cascade rules | EF_001 cascade triggers resource ownership reassignment/destruction |
| PF_001 Place Foundation | CANDIDATE-LOCK | Cell-as-producer model | Cell as place semantics | RES_001 `producer_binding` references PlaceId (cell-tier) |
| PL_005 Interaction | DRAFT | Resource aggregate shape + invariants | Transfer kind (Give/Strike/Use) + intent | OutputDecl `aggregate_type=resource_*` |
| PL_006 Status Effects | DRAFT | Numeric pools (HP/Stamina) | Categorical flags (Drunk/Wounded) | Read-side derived: Wounded threshold from HP |
| WA_006 Mortality | CANDIDATE-LOCK | HP=0 signal emission | Mortality state machine + transition | Resource emits `MortalityTransitionTrigger`; Mortality consumer applies state |
| PCS_001 PC Substrate | brief LOCKED, not drafted | Resource pool per PC (HP/Stamina/inventory) | PC identity + stats modifier rates | PCS_001 references RES_001 aggregate types; RES_001 references PCS_001 stats by name only |
| DF7 PC Stats | placeholder | (none — DF7 modifier-side) | Stats modifier rates | RES_001 consumption_rate accepts stats modifier as multiplier (V1+ wired in DF7 design) |
| 07_event_model EVT-T5 Generated | LOCKED | Resource production/consumption events | Event taxonomy + Generator framework | EVT-G2 trigger source `FictionTimeMarker` for periodic production; sub-types `aggregate_type=resource_*` |
| RealityManifest extension | locked envelope | `resources: Vec<ResourceDecl>` for initial declarations | Manifest envelope rules | Per `_boundaries/02_extension_contracts.md` §2 additive-only |
| `resource.*` rule_id namespace | not yet registered | All resource RejectReason variants | RejectReason envelope (Continuum) | Per `_boundaries/02_extension_contracts.md` §1.4 — register at RES_001 DRAFT |

---

## §5 — Open Questions Q1-Q7 (USER ANSWERS NEEDED)

These 7 questions lock V1 scope. Once answered, RES_001 DRAFT can proceed with disciplined scope.

### Q1 — V1 Resource categories: which to include?

**Options:**
- (A) **Minimum 4**: Vital pool (HP/Stamina) + Consumable (food) + Currency (1 kind) + Material (gỗ/sắt fungible). EXCLUDE Item-unique + Property (V2+).
- (B) **Standard 5**: A + Item-unique (1 thanh Mặc Vô Kiếm có history). EXCLUDE Property (V2+).
- (C) **Full 6**: B + Property (cell-as-resource). HARD V1 — overlap với PF_001 cần boundary tightening.

**Recommendation:** Option A (minimum 4 categories). Item-unique introduces ItemId namespace + history tracking + provenance — tốn 30%+ design surface, trì hoãn V1.

### Q2 — Conservation: closed economy or open with sinks?

**Options:**
- (A) **Closed**: Total currency conserved per reality. Author seeds initial distribution. NPC trade chỉ shuffle. Game balance dễ predict, ít drift.
- (B) **Open + sinks**: NPC produce money (work/cell). Currency sinks: taxes / decay / breakage / theft cleanup. Standard MMO model.
- (C) **Hybrid (V2+)**: Per-faction closed, cross-faction open. SKIP V1.

**Recommendation:** Option B (open + sinks). Closed economy quá restrictive cho LLM-driven open-world; sẽ gặp NPC "cạn tiền không buy được" gameplay issue. V1 sinks: simple decay (không recommend) hoặc tax (cần PLT integration) — start với "no sinks V1, accept inflation, fix V1+30d".

### Q3 — HP/Stamina là Resource hay tách Vital tier riêng?

**Options:**
- (A) **Unified**: HP/Stamina là 1 ResourceKind variant (Vital). 1 aggregate `resource_pool` cho tất cả. Body-bound flag = `transferable: false`.
- (B) **Tách**: 1 aggregate `vital_pool` (T2/Reality, body-bound) + 1 aggregate `resource_inventory` (portable). 2 path khác nhau.
- (C) **Hybrid**: Body-bound như part của entity_binding (EF_001) extension; portable là resource_inventory. Tránh aggregate explosion.

**Recommendation:** Option A (unified với fungibility/body-bound flags trong ResourceKind). Đơn giản hơn 1 aggregate; rule engine khác biệt qua flags. PL_006 Status đã apply pattern tương tự (1 actor_status aggregate cho cả 4 flags).

### Q4 — Production trigger model: auto vs action vs hybrid?

**Options:**
- (A) **Auto-only (Generator)**: Cells produce theo fiction-time tự động. PC chỉ "harvest" = transfer-from-cell-to-PC (PL_005 Use kind). Đơn giản, deterministic.
- (B) **Action-only**: PC phải "gặt lúa" mới có resource. Cells không tự sản xuất; PC trigger qua PL_005. Realistic hơn nhưng forces grinding.
- (C) **Hybrid**: Cell auto-produce với cap; PC harvest thì empty cap + bonus. Best UX, complex impl.

**Recommendation:** Option A (auto-only V1). EVT-G framework đã LOCKED, gắn vào tự nhiên. Hybrid V1+30d nếu cần. Action-only forces tedious gameplay.

### Q5 — V1 hunger loop: skip eating → HP loss?

**Options:**
- (A) **No hunger V1**: HP chỉ giảm bởi combat/Strike (PL_005). Stamina chỉ giảm bởi action. Food là pure consumable không loop.
- (B) **Soft hunger V1**: Per-fiction-day no-food → -10% Stamina max (Status Effect: Hungry). Không HP. Simple Generator + PL_006 status integration.
- (C) **Full hunger V1**: No-food N days → HP loss → Mortality. Full survival mechanic.

**Recommendation:** Option A (no hunger V1). Hunger loop tốn boundary work với WA_006 + PL_006 + Generator + Status Hungry/Starving. V1+30d add Option B.

### Q6 — Capacity limits (inventory cap, cell storage cap) V1 có không?

**Options:**
- (A) **No caps V1**: PC inventory unlimited; cell storage unlimited. Đơn giản, không overflow rule.
- (B) **PC cap only**: PC inventory có max_weight or max_slots. Cell unlimited. Realistic-light.
- (C) **All caps**: Both PC + cell capped. Need overflow rules (drop / refuse / oldest-purge).

**Recommendation:** Option A (no caps V1). Caps tạo overflow rule complexity (drop semantics + UI feedback + LLM context bloat). V1+30d add PC cap (Option B) khi feedback từ playtesting.

### Q7 — Quality / grade variation V1 có không?

**Options:**
- (A) **No grade V1**: Mọi gạo cùng giá. Mọi gold = gold. Single rate per kind.
- (B) **Tier system V1**: 3 tiers (low/standard/high) per consumable kind. Affects exchange rate + consumption value.
- (C) **Float quality V1**: Continuous quality 0.0-1.0. Highly granular.

**Recommendation:** Option A (no grade V1). Grade variation cần per-instance tracking → kéo Item-unique vào V1 → đụng Q1. Single uniform rate đơn giản đủ V1 + first prototype.

---

## §6 — Provisional V1 scope (if all recommendations approved)

If user approves recommendations on all Q1-Q7, V1 scope becomes:

**V1 Resource Foundation (RES_001 V1 minimum):**
- 4 ResourceKind variants: `Vital(VitalKind)` / `Consumable(ConsumableKind)` / `Currency(CurrencyKind)` / `Material(MaterialKind)`
- Sub-enums (V1 minimum):
  - `VitalKind`: HP / Stamina (2 V1; Mana V1+)
  - `ConsumableKind`: Food / Drink (2 V1; Medicine V1+)
  - `CurrencyKind`: Đồng (1 V1; lượng bạc / lượng vàng V1+)
  - `MaterialKind`: Wood / Iron / Stone (3 V1; Cloth/Leather V1+)
- 1 aggregate: `resource_pool` (T2/Reality scope, references EntityRef as owner)
- Stack policies: Sum (count) / SumClamped (vital, 0..max)
- Body-bound flag: Vital body-bound (non-transferable); others transferable
- Production: Auto via EVT-G framework (FictionTimeMarker trigger); cell-tier place owns producer profile
- Consumption: PL_005 Use kind (PC-driven); EVT-G Generator-driven for time-based decay (V1+ — none V1)
- Transfer: PL_005 Give kind (gift) / new "Trade" kind (exchange) / Strike kind (theft via cascade) — register `interaction.trade.*` rule_ids in PL_005 closure pass
- HP=0 → emit `MortalityTransitionTrigger` event → WA_006 consumes
- Wounded status (PL_006) = derived from HP threshold (read-side, no aggregate write)
- Open economy, no sinks V1 (accept inflation)
- No capacity limits V1 (unlimited inventory + cell storage)
- No quality grade V1 (uniform per kind)
- No hunger loop V1
- No decay/spoilage V1
- No Item-unique V1

**Aggregate count:** +1 new aggregate (`resource_pool`)
**Event count:** +N sub-types under EVT-T3 / T4 / T5 (`aggregate_type=resource_pool`)
**Rule_id namespace:** `resource.*` (registered in `_boundaries/02_extension_contracts.md` §1.4)
**RealityManifest extension:** `resources: Vec<ResourceDecl>` — declares initial distribution + cell producer profiles

**Estimated DRAFT size:** ~700-800 lines (matches NPC_001 / PF_001 / MAP_001 / CSC_001 precedent).

---

## §7 — What this concept-notes file is NOT

- ❌ NOT the formal RES_001 design (no Rust struct definitions, no full §1-§N section structure, no acceptance criteria)
- ❌ NOT a lock-claim trigger (no `_boundaries/_LOCK.md` claim made for this notes file)
- ❌ NOT registered in ownership matrix yet (deferred to RES_001 DRAFT promotion)
- ❌ NOT consumed by other features yet (other features should NOT cite this file as a contract — only RES_001 DRAFT counts)

---

## §8 — Promotion checklist (when Q1-Q7 answered)

Before drafting `RES_001_resource_foundation.md`:

1. [ ] User answers Q1-Q7 (or approves all recommendations as default)
2. [ ] Update §6 V1 scope based on answers (replace recommendations with locked decisions)
3. [ ] Claim `_boundaries/_LOCK.md` (4-hour TTL)
4. [ ] Create `RES_001_resource_foundation.md` with sections: §1 user story · §2 aggregate definitions · §3 ResourceKind ontology · §4 ownership/transfer rules · §5 production/consumption model · §6 boundary integrations (per §H above) · §7 RejectReason rule_ids · §8 RealityManifest extension · §9 EVT-T* sub-types · §10 PL_005 transfer kind extensions · §11 acceptance scenarios · §12 deferrals · §13 open questions
5. [ ] Update `_boundaries/01_feature_ownership_matrix.md` — add `resource_pool` aggregate ownership row
6. [ ] Update `_boundaries/02_extension_contracts.md` §1.4 — add `resource.*` RejectReason prefix
7. [ ] Update `_boundaries/02_extension_contracts.md` §2 — add RealityManifest `resources` extension
8. [ ] Update `_boundaries/99_changelog.md` — append entry
9. [ ] Create `catalog/cat_00_RES_resource.md` — feature catalog
10. [ ] Update `00_resource/_index.md` — replace concept row with RES_001 DRAFT row
11. [ ] Release `_boundaries/_LOCK.md`
12. [ ] Commit with `[boundaries-lock-claim+release]` prefix

---

## §9 — Status

- **Created:** 2026-04-26 by main session
- **Phase:** ~~CONCEPT~~ → **DRAFT 2026-04-26** (RES_001 promoted via single `[boundaries-lock-claim+release]` commit). Q1-Q12 ALL LOCKED + i18n cross-cutting pattern introduced.
- **Promoted file:** [`RES_001_resource_foundation.md`](RES_001_resource_foundation.md) — 18 sections, ~900 lines.
- **Next action:** Apply 17 downstream impacts per RES_001 §17.2 in follow-up commits (HIGH priority: PL_006 Hungry promotion / WA_006 Starvation cause_kind / PL_005 trade+harvest rule_ids / EF_001 cell_owner+inventory_cap fields / PCS_001 brief body-substitution + RES_001 reading / 07_event_model 4 EVT-T5 sub-types).

---

## §10 — Q1-Q5 LOCKED decisions (2026-04-26 deep-dive)

> **Note:** §5 (original Q1-Q7 with recommendations) and §6 (provisional V1 scope) are SUPERSEDED for Q1-Q5 by this section. Q6-Q7 in §5 + Q8-Q12 in `01_REFERENCE_GAMES_SURVEY.md` §6 remain open. §7 of `01_REFERENCE_GAMES_SURVEY.md` "V1 scope summary" needs revision to reflect Q1-Q5 changes (deferred to RES_001 DRAFT promotion).

### Q1 LOCKED — V1 Resource Categories: 5 (CHANGE from 4)

| Sub | Decision |
|---|---|
| Q1a | ResourceBalance shape | `{ kind: ResourceKind, amount: u64, instance_id: Option<ItemInstanceId> }` — lock from V1 (instance_id=None V1, Some V1+30d when Item kind ships) |
| Q1b | Material V1 ship | YES (kept as trade-only category V1; semantic distinction from Consumable; future-proof V2 crafting) |
| Q1c | **SocialCurrency V1 ship** | **YES — CHANGE from V2 → V1.** Variant = `SocialCurrency(SocialKind)`; SocialKind V1 = `Reputation` only; V2 expand to Prestige/Piety/Influence |
| Q1d | Property in ResourceKind | NO (handled by EF_001 entity_binding ownership flag — boundary clarity) |
| Q1e | Knowledge in enum | RESERVED (typed-only V1, ship V3) |

**V1 ResourceKind enum (forward-compatible):**
```rust
pub enum ResourceKind {
    // V1 active
    Vital(VitalKind),              // body-bound — moved to vital_pool aggregate per Q3
    Consumable(ConsumableKind),
    Currency(CurrencyKind),
    Material(MaterialKind),
    SocialCurrency(SocialKind),    // NEW V1 — wuxia/xianxia danh tiếng

    // V1+30d reserved (typed but not used)
    Item(ItemKind),

    // V2 reserved
    Recipe(RecipeId),

    // V3 reserved
    Knowledge(KnowledgeKind),
    Influence(InfluenceKind),
}
```

**Note:** `Vital(VitalKind)` exists in the enum for forward-compat / discriminator parity with other kinds, BUT the actual storage moves to a separate `vital_pool` aggregate per Q3 LOCKED. Resource_inventory aggregate stores the other 4 V1 active variants.

### Q2 LOCKED — Open Economy + 2 V1 Sinks (CHANGE: sink 2)

| Sub | Decision |
|---|---|
| Q2a | Economy model V1 | OPEN |
| Q2b | Sink 1 | NPC + PC food consumption (per Q5) |
| Q2c | **Sink 2** | **CHANGE: cell maintenance cost** (was "cell cap" — that's a production constraint, not a true sink) |
| Q2d | RealityManifest extension | NEW field: `cell_maintenance_profiles: HashMap<PlaceTypeRef, MaintenanceCost>` (author-declared per cell type) |
| Q2e | Cell with owner=None | Production halts (no maintenance trigger, no production trigger) |
| Q2f | Maintenance failure | Owner balance < cost → cell production halts (V1+30d: cell decays toward Destroyed via PF_001 StructuralState) |

**Cell cap retained but reclassified** as supply-side production constraint (not a sink). Cell stockpile fills to cap, production halts, NPC/PC must clear (auto-collect or harvest). Cap = author-declared per PlaceType in RealityManifest.

### Q3 LOCKED — Split 2 Aggregates (CHANGE from unified)

| Sub | Decision |
|---|---|
| Q3a | **Aggregate count** | **CHANGE: 2 aggregates** (was unified 1) — `vital_pool` + `resource_inventory` |
| Q3b | `vital_pool` scope | T2/Reality, owner = Actor only (PC/NPC); body-bound; non-transferable type-system enforced |
| Q3c | `resource_inventory` scope | T2/Reality, owner = EntityRef (PC/NPC/Cell); portable; transferable |
| Q3d | VitalKind V1 active | `Hp`, `Stamina` (Mana V1+; Satiety NOT a Vital — tracked via PL_006 Hungry status magnitude per Q5) |
| Q3e | VitalProfile shape | RES_001 owns: `{ kind, max_value, regen_rule, depletion_rule, on_zero_effect }`; PCS_001/NPC_001 reference per-actor max; RealityManifest declares per-actor-class default |
| Q3f | RegenRule enum | `TimeBased { per_fiction_hour: u32 }` / `RestBased { per_rest_action: u32 }` / `Manual` (no auto-regen) |
| Q3g | OnZeroEffect | `EmitMortalityTrigger` (HP=0) / `ApplyStatus(StatusFlag)` (Stamina=0 → Exhausted) / `NoOp` |

**Rationale for split:** type-system-enforced body-bound invariant > flag-based; differential mechanics (regen rules, depletion, on-zero effects) cleanly separated; matches PL_006 "1 aggregate per concern" pattern (actor_status doesn't swallow everything).

**V1 aggregate count update:** RES_001 contributes **+2 aggregates** (was +1), totaling 6 V1 foundation aggregates across 5 foundation features.

### Q4 LOCKED — Hybrid Production (Finer-Grained)

| Sub | Decision |
|---|---|
| Q4a | Production model | Hybrid: cell auto-produces (Generator) + NPC owner auto-collects (Generator) + PC owner manual-harvests (action) + no-owner halts |
| Q4b | PC harvest semantics | Drain stockpile → PC inventory (no bonus mechanic V1) |
| Q4c | Production timing | **Day-boundary Generator tick** (fires when fiction-time crosses fiction-day boundary; no float arithmetic V1) |
| Q4d | Production rate V1 | Fixed (RealityManifest declares per PlaceType); Skill/Weather/Status modifiers V1+30d |
| Q4e | Cell owner types V1 | `NPC` / `PC` / `None` (Faction V3+) |
| Q4f | NPC owner auto-collect | Daily Generator transfers full cell stockpile → NPC inventory |
| Q4g | PC owner auto-collect | NO — PC must visit + harvest (preserves player agency) |
| Q4h | No-owner cell | Production halts (no maintenance trigger, no production trigger) |

**Generator bindings (RES_001 will register at DRAFT):**
- `Scheduled:CellProduction` (EVT-T5 Generated, EVT-G2 trigger source `FictionTimeMarker` day-boundary)
- `Scheduled:CellMaintenance` (EVT-T5 Generated, same day-boundary trigger; consumes from owner balance)
- `Scheduled:NPCAutoCollect` (EVT-T5 Generated, same day-boundary trigger; transfers cell stockpile to NPC owner inventory)

3 Generators total V1, all day-boundary triggered, all deterministic per EVT-A9 RNG.

### Q5 LOCKED — Soft Hunger V1 (Symmetric PC+NPC)

| Sub | Decision |
|---|---|
| Q5a | Hunger applies to | PC + NPC both V1 (symmetric — prevents NPC infinite-food hoarding) |
| Q5b | Status enum | Reuse `Hungry` from PL_006 reserved → promote to V1 active (downstream impact: PL_006 closure pass) |
| Q5c | Severity model | Magnitude scaling on Hungry: 1=mild, 4=severe (narratively "Starving"), 7+=critical → emit MortalityTransitionTrigger |
| Q5d | Tick model | Day-boundary Generator: each fiction-day boundary, every actor consumes 1 food from inventory |
| Q5e | Empty inventory effect | magnitude += 1 (Hungry intensifies) |
| Q5f | Eating effect | magnitude = 0 (full reset on any nutritional consumable) |
| Q5g | Status effect V1 | Narrative-only (LLM aware via context; no Stamina/HP penalty V1) |
| Q5h | Hydration V1 | **NO** (deferred V1+30d) |
| Q5i | Consumption rate | Universal 1 food/day V1; per-actor-class override V1+30d |
| Q5j | "Food" definition | Any Consumable kind tagged `nutritional: true` (RealityManifest declares per ConsumableKind) |
| Q5k | Mortality trigger threshold | Magnitude 7 = ~1 fiction-week of starvation → MortalityTransitionTrigger |

**Generator binding:** `Scheduled:HungerTick` (EVT-T5 Generated, day-boundary; iterates all actors with inventory; deducts food OR increments Hungry magnitude).

### §10.5 — Downstream impacts (apply at RES_001 DRAFT promotion)

When RES_001 promotes from concept to DRAFT, the following features need lock-coordinated updates:

| Feature | Update | Why |
|---|---|---|
| **PL_006 Status Effects** | Promote `Hungry` from V1+ reserved → V1 active | Q5 hunger loop ships V1; Hungry magnitude scaling becomes core mechanic |
| **PL_006 Status Effects** | Document magnitude semantics (1=mild, 4=severe-narrative-Starving, 7=critical-mortality-trigger) | Q5c severity model |
| **WA_006 Mortality** | Add `MortalityTransitionTrigger` consumer for `cause_kind=Starvation` | Q5k mortality threshold |
| **PL_005 Interaction** | Confirm `Use` kind targets cell-stockpile-as-target (PC harvest action); register `interaction.harvest.*` rule_ids | Q4b PC harvest action |
| **PL_005 Interaction** | Confirm `Give` kind reciprocal for trade (V1 trade = double-Give); V1+ dedicated Trade kind | Q1c+Q2 trade mechanism |
| **PCS_001 brief §4.4 reading list** | Add RES_001 mandatory reading | Q3e PCS references VitalProfile per-actor max |
| **NPC_001 Cast** | Document NPC owner auto-collect Generator (Q4f) — NPC inventory grows from cell production | Q4f auto-collect |
| **PF_001 Place Foundation** | Document MaintenanceCost author-declared per PlaceType (RealityManifest extension) | Q2d cell maintenance |
| **PF_001 Place Foundation** | Document cell-stockpile cap author-declared per PlaceType | Q2c production constraint |
| **EF_001 Entity Foundation** | Confirm Property NOT in ResourceKind (boundary line) | Q1d boundary clarity |
| **`_boundaries/01_feature_ownership_matrix.md`** | Register `vital_pool` + `resource_inventory` aggregates owned by RES_001 | Q3 split |
| **`_boundaries/02_extension_contracts.md` §1.4** | Register `resource.*` rule_id namespace | RES_001 RejectReasons |
| **`_boundaries/02_extension_contracts.md` §2** | Register RealityManifest extensions: `resources` + `currencies` + `producers` + `prices` + `cell_storage_caps` + `cell_maintenance_profiles` + `social_initial_distribution` | Multi-extension |
| **`07_event_model/03_event_taxonomy.md`** | Register EVT-T3 sub-types `aggregate_type=vital_pool` + `aggregate_type=resource_inventory`; EVT-T5 Generated sub-types `Scheduled:CellProduction` + `Scheduled:CellMaintenance` + `Scheduled:NPCAutoCollect` + `Scheduled:HungerTick` | EVT taxonomy registration |

All updates lock-coordinated under single `[boundaries-lock-claim+release]` commit at RES_001 DRAFT promotion (per established pattern).

### §10.6 — Q6-Q12 LOCKED 2026-04-26 (deep-dive batch 2)

All Q6-Q12 LOCKED after second deep-dive (continuing from Q1-Q5 batch). User approval received for all decisions including 3 NEW big changes surfaced (Q9c body-substitution / Q12b buy-sell spread / Q12c NPC finite liquidity).

| Q | Decision LOCKED |
|---|---|
| **Q6** | NO PC inventory cap enforcement V1; SCHEMA RESERVED on EF_001 entity_binding `inventory_cap: Option<CapacityProfile>` (None V1 → Some V1+30d slot cap; zero migration) |
| **Q7** | NO quality/grade variation V1 (V2 with crafting module); no schema reservation needed (additive bump V2 acceptable per I14) |
| **Q8** | RESOLVED implicitly by Q3+Q4 — both per-character + per-cell ownership tier (resource_inventory.owner = EntityRef any, cells own own balances) |
| **Q9** | Author-declared V1 + 3 V1 transfer paths: (1) Author Forge (WA_003) / (2) **Body-substitution xuyên không** (PCS_001 mechanic Q9c — body-bound cell ownership) / (3) NPC death → orphan. PC-to-PC trade + PC-buy-from-NPC V1+30d. |
| **Q10** | Author-configurable currencies (default single Copper); multi-tier display via I18nBundle formatter; storage = total smallest unit V1; per-denomination V1+30d |
| **Q11** | RESOLVED by Q4d — production rate canonical in RealityManifest (fixed V1; modifier chain V1+30d) |
| **Q12** | Global pricing V1 + **buy/sell spread** (sink #3 NEW — was missing in original recommendation) + **NPC finite liquidity** validator-enforced (RES-V3, was implicit assumption); per-cell variance V1+30d |

---

## §11 — i18n cross-cutting pattern decision (LOCKED 2026-04-26)

User direction 2026-04-26 at promote-to-DRAFT moment:

> "tên resource nên hỗ trợ i18n thay vì dùng tiếng việt as default / game của chúng ta là game quốc tế, lấy tiếng anh làm chuẩn"

Translation: "Resource names should support i18n instead of using Vietnamese as default. Our game is international; English is the standard."

### §11.1 Decision

LoreWeave engine standard going forward:
- **Stable identifiers** (rule_ids, aggregate_type, sub-types, enum variants) = English `snake_case` / `PascalCase`
- **User-facing strings** (resource names, reject messages, narrative copy) = `I18nBundle { default: String, translations: HashMap<LangCode, String> }` with English `default` required
- **Author content** (currency names, custom resource kinds) = author declares I18nBundle in any language(s) per reality

### §11.2 RES_001 conformance (first adopter)

- All `rule_id` strings English: `resource.trade.npc_insufficient_funds`, `resource.harvest.empty_cell`, etc.
- All `aggregate_type` English: `vital_pool`, `resource_inventory`
- All EVT-T5 sub-types English: `Scheduled:CellProduction`, `Scheduled:HungerTick`
- All engine enum variants English: `VitalKind::Hp`, `SocialKind::Reputation`
- All user-facing strings I18nBundle: `CurrencyDecl.display_name`, `ResourceKindDecl.display_name`, `RejectReason.user_message`

### §11.3 Cross-cutting envelope extension

`RejectReason` envelope (Continuum-owned in `_boundaries/02_extension_contracts.md` §1) adds:
```rust
pub struct RejectReason {
    pub rule_id: String,                  // English stable ID (existing)
    pub user_message: I18nBundle,         // NEW — multi-language user-facing
    pub detail: serde_json::Value,        // existing
}

// I18nBundle — engine-wide cross-cutting type, RES_001 introduces
pub struct I18nBundle {
    pub default: String,                              // English-required fallback
    pub translations: HashMap<LangCode, String>,      // ISO-639-1 lowercase
}
pub type LangCode = String;
```

Additive per I14. Existing features can migrate to I18nBundle gradually (cosmetic cleanup, doesn't affect functionality).

### §11.4 Existing feature audit deferred

PL_006 / NPC_001 / NPC_002 / PL_002 / WA_001..006 currently have hardcoded Vietnamese reject copy strings. These remain functional V1 (engine renders them as `default` field with English fallback empty string, OR migrates to bilingual at next closure pass). Cross-cutting i18n audit is **LOW priority cosmetic** — doesn't block V1 functionality. Tracked in RES_001 §17.2 downstream impacts.

### §11.5 Vietnamese xianxia author content example

Author declares Vietnamese xianxia reality:
```rust
RealityManifest {
    currencies: vec![
        CurrencyDecl {
            kind_id: CurrencyKindId("copper"),    // English stable ID
            display_name: I18nBundle {
                default: "Copper Coin".to_string(),    // English required
                translations: hashmap! {
                    "vi".to_string() => "Đồng".to_string(),
                    "zh".to_string() => "銅錢".to_string(),
                },
            },
            base_rate_to_smallest: 1,
            display_priority: 0,
        },
        // ... silver / gold tiers ...
    ],
}
```

LLM narration: at active locale `vi`, renders "Lý Minh đặt 30 đồng lên bàn"; at active locale `en`, renders "Lý Minh placed 30 copper coins on the table".

### §11.6 Why this pattern

- **International game** — English is the universal engine standard (matches industry — Unity, Unreal, RPG Maker, etc.)
- **Author flexibility** — authors declare any language(s) for their reality content
- **LLM-friendly** — LLM narrates in active locale; doesn't need to translate stable IDs
- **Replay-safe** — locale switch doesn't break determinism (stable IDs are locale-invariant)
- **Future-proof** — easy to add new locales without schema migration
