# MAP_001 — Map Foundation

> **Conversational name:** "Map Foundation" (MAP). The visual graph layer that makes the world navigable as a node-link map (Tiên Nghịch / EVE Online / Stellaris pattern). Owns the `map_layout` aggregate per channel, position + tier metadata for non-cell tiers, image asset slots (V1 schema; V1+ pipeline), graph connections at non-cell tiers with distance + canonical Travel duration. Cell-tier connections stay with PF_001 (no reopen); MAP_001 supplies cell-tier visual layer (position + image slots only).
>
> **Category:** MAP — Map Foundation (foundation tier; sibling of EF_001 + PF_001)
> **Status:** **DRAFT 2026-04-26** (Option C max scope per user direction "design now")
> **Catalog refs:** [`cat_00_MAP_map_foundation.md`](../../catalog/cat_00_MAP_map_foundation.md) — owns `MAP-*` namespace (`MAP-A*` axioms · `MAP-D*` deferrals · `MAP-Q*` open questions)
> **Builds on:** [PL_001 Continuum](../04_play_loop/PL_001_continuum.md) §16 RealityManifest (extends with `map_layout: Vec<MapLayoutDecl>`) · §13 Travel sequence (consumes MAP_001 `default_fiction_duration` for non-cell-tier travel cost), [PF_001 Place Foundation](../00_place/PF_001_place_foundation.md) (composes at cell tier — PF_001 owns place semantic + cell ConnectionDecl; MAP_001 owns cell visual layer + non-cell connections), [DP-Ch1..Ch53](../../06_data_plane/) channel hierarchy (every channel from continent to cell may have a `map_layout` row), [07_event_model](../../07_event_model/) Option C taxonomy (T3 Derived for layout deltas; T4 System for LayoutBorn; T8 Administrative for Forge layout edits)
> **Resolves:** Map UI gap (PF_001 + DP channel hierarchy gave semantic identity but no visual graph layer) · Cross-tier navigation gap (drill-down from continent → country → region → cell needs node-link rendering; demo `_ui_drafts/MAP_GUI_v1.html` validated approach) · Canonical Travel cost gap (PC's `/travel` previously had freely-proposed `fiction_duration_proposed`; MAP_001 distance + default_fiction_duration on edges removes ambiguity for non-cell-tier travel) · EnvObject orphan extension to media (PF_001 closed EnvObject seed; MAP_001 adds image asset slots for richer V1+ visualization)
> **Defers to:** future `TVL_001` Travel Mechanics feature for speed/method matrix (cultivation flying-sword, vehicle, FTL) · future `MAP_002` Asset Pipeline feature for V1+ author/player upload + LLM-generated image flows · WA_003 Forge for V1+ map-editor UI (Forge:EditMapLayout AdminAction) · PCS_001 (when designed) for V1+ per-PC discovered_nodes fog-of-war integration

---

## §1 Why this exists

Three concrete gaps in the V1 design surface that MAP_001 closes:

**Gap 1 — Map UI has no schema-level home.** Demo at [`_ui_drafts/MAP_GUI_v1.html`](../../_ui_drafts/MAP_GUI_v1.html) validated the node-link drill-down concept (Tiên Nghịch / EVE Online pattern), but rendering needs canonical data: position per node within parent viewport, image asset references, tier metadata for non-cell levels, edges at every tier. No existing feature owns this. PF_001 V1 strict invariant: only cell-tier has `place` rows (continent/country/district/town are aggregation tiers). MAP_001 fills the visual layer at all tiers without reopening PF_001.

**Gap 2 — Travel cost is currently freely-proposed by PC.** PL_001 §13 `/travel` accepts `fiction_duration_proposed: FictionDuration` from PC's TurnEvent. LLM or validator must judge "is 3 days from Hangzhou to Tây Vân realistic?". With multi-PC realities, two PCs can drift on same route ("PC A đi 1 ngày, PC B đi 1 tuần"). Space-game pattern (EVE Online jump-time, Stellaris hyperlane-days, FTL sector-hops) — quantitative distance + canonical travel duration on each edge — removes the ambiguity. MAP_001 declares both V1 (distance_units invariant + default_fiction_duration as OnFoot baseline; V1+ TVL_001 derives method-modified durations).

**Gap 3 — Image asset architecture undefined.** Authors / players investing in art (uploading custom backgrounds; V1+ LLM-generated portraits) have no schema slot to attach. V1 reserve fields, V1+ implement upload/generation pipeline. Reserved schema makes V1+ rollout purely additive.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **MapLayout** | Aggregate `map_layout` (T2 / Channel scope) — per-channel-id; covers all tiers (continent/country/district/town/cell) | One row per channel. For non-cell tiers: full schema (tier_metadata + position + image slots + connections). For cell tier: position + image slots only (tier_metadata=None; connections=[] — PF_001 ConnectionDecl on `place` aggregate is authoritative for cell-tier graph edges per Q2-b decision). |
| **MapPosition** | `(x: u32, y: u32)` within parent viewport | V1: normalized 0..1000 within parent's map view. Author-positioned absolute (per Q3-a). Continent-tier positions are within reality root viewport; country-tier positions within their continent viewport; etc. |
| **TierMetadata** | Optional struct on MapLayout — Some for non-cell, None for cell | Carries display_name (LocalizedName) + canon_ref (BookCanonRef) + description for non-cell tiers (continent/country/district/town). Cell tier reads display_name from PF_001 `place` (canonical source); MapLayout's tier_metadata is None to enforce. |
| **MapConnectionDecl** | Edge declaration on MapLayout | At non-cell tier: full edge schema (kind + distance + duration + canon_ref + bidirectional + gate_slot_id). At cell tier: empty (PF_001 cell ConnectionDecl is authoritative). |
| **MapConnectionKind** | Closed enum 5 V1 (matches PF_001 for consistency) — Public / Private / Locked / Hidden / OneWay | Same visual treatment as PF_001 cell ConnectionKind. V1+ extensions (TimePortal/PocketDimension) tracked under MAP-D2. |
| **distance_units** | u32 abstract leagues | Canonical book-derived; invariant across travel methods (V1+ TVL_001 derives method-modified durations from this). 1 unit = 1 abstract league per author convention; cross-tier scaling per author (continent=1000s, country=100s, region=10s — see §8). |
| **default_fiction_duration** | FictionDuration | Canonical OnFoot baseline V1. PC's `/travel` reads this directly V1; V1+ TVL_001 layers method speed-multiplier. |
| **ImageAssetRef** | Reference to S3/MinIO object — V1 schema, V1+ pipeline | All values None V1; UI falls back to default emoji icon + plain dark background. V1+ MAP_002 Asset Pipeline feature populates. |
| **AssetSource** | Closed enum 4 V1 — AuthorUploaded / PlayerUploaded / LlmGenerated / CanonicalSeed | Discriminator on ImageAssetRef. V1: schema only; V1+: per-source upload/gen flow. |
| **AssetReviewState** | Closed enum 3 — Pending / Approved / Rejected | V1+ Forge author-review queue gate. V1: assumed Approved (no values exist V1). |
| **MapLayoutDecl** | RealityManifest extension element — see §9 | Author-supplied bootstrap input declaring all V1 layouts at reality creation. REQUIRED V1: every channel from `root_channel_tree` (continent through cell) must have a MapLayoutDecl; channels without decl reject `map.missing_layout_decl` at first-use. |

---

## §2.5 Event-model mapping (per 07_event_model Option C taxonomy)

MAP_001 introduces no new EVT-T* category. Maps onto existing mechanism-level taxonomy:

| MAP event | EVT-T* | Sub-type | Producer | Notes |
|---|---|---|---|---|
| Layout birth at RealityManifest bootstrap | **EVT-T4 System** | `LayoutBorn { channel_id, tier, has_tier_metadata }` | DP-Internal RealityBootstrapper (Synthetic actor) | Emitted alongside DP create_channel + PF_001 PlaceBorn (at cell tier). One per channel from root_channel_tree. |
| Layout state delta (position move, tier_metadata edit, asset ref update, connection add/remove) | **EVT-T3 Derived** | `aggregate_type=map_layout` (field delta) | Aggregate-Owner role (world-service post-validate) | Causal-ref to triggering EVT-T8 Administrative (Forge edit) or EVT-T1 Submitted (V1+ in-fiction trigger) |
| Author-edit map layout via Forge | **EVT-T8 Administrative** | `Forge:EditMapLayout { channel_id, edit_kind, before, after }` | WA_003 Forge | Audit-grade; edit kinds V1: UpdatePosition / UpdateTierMetadata / UpdateConnections / UpdateImageAsset / Rename |
| Image asset upload (V1+ pipeline) | **EVT-T1 Submitted** + **EVT-T8 Administrative** | `MAP_002:AssetUpload` (V1+ feature) | future MAP_002 Asset Pipeline | Out of MAP_001 V1 scope; reservation only |
| LLM image generation (V2+ pipeline) | **EVT-T6 Proposal** + **EVT-T8 Administrative** | `MAP_002:AssetGenerated` (V2+ feature) | future MAP_002 Asset Pipeline | Out of MAP_001 V1 scope; reservation only |

No new EVT-T* row in `_boundaries/01_feature_ownership_matrix.md`. EVT-T4 System sub-types row gains `LayoutBorn` (MAP_001-owned alongside EF_001's EntityBorn + PF_001's PlaceBorn); EVT-T3 Derived sub-types row gains `aggregate_type=map_layout`; EVT-T8 Administrative sub-shapes registry gains `Forge:EditMapLayout`.

---

## §3 Aggregate inventory

One aggregate owned by MAP_001:

### 3.1 `map_layout` (T2 / Channel scope) — PRIMARY

```rust
#[derive(Aggregate)]
#[dp(type_name = "map_layout", tier = "T2", scope = "channel")]
pub struct MapLayout {
    pub channel_id: ChannelId,                            // primary key — covers ALL tiers (continent through cell)
    pub tier: ChannelTier,                                // denormalized: Continent | Country | District | Town | Cell
    pub position: MapPosition,                            // (x, y) within parent viewport (0..1000 normalized; Q3-a author-positioned)
    pub tier_metadata: Option<TierMetadata>,              // Some for non-cell tiers; None for cell (PF_001 supplies — Q1-a invariant)
    pub icon_asset: Option<ImageAssetRef>,                // V1: None (Q5-a slot reservation); V1+ author/LLM populates
    pub background_asset: Option<ImageAssetRef>,          // shown when this node IS the current map view
    pub inline_artwork: Option<ImageAssetRef>,            // centerpiece in info-pane sidebar
    pub connections: Vec<MapConnectionDecl>,              // for non-cell tiers; empty Vec for cell tier (Q2-b — PF_001 owns cell edges)
    pub last_layout_change_fiction_time: FictionTime,     // for movement audit + V1+ proximity computations
}

pub struct MapPosition {
    pub x: u32,                                           // 0..1000 within parent viewport
    pub y: u32,                                           // 0..1000 within parent viewport
}

pub enum ChannelTier {                                    // closed enum; matches DP channel hierarchy
    Continent,
    Country,
    District,
    Town,
    Cell,
}

pub struct TierMetadata {
    pub display_name: LocalizedName,                      // shared with PF_001 (LocalizedName lives at 00_foundation post-PF_001 PF-Q3 resolution)
    pub canon_ref: BookCanonRef,                          // shared schema; PF-D12 deferral
    pub description: String,                              // freeform; used for sidebar info pane
}

pub struct MapConnectionDecl {
    pub to_channel: ChannelId,                            // sibling channel within same parent (V1 cross-tier disallowed)
    pub kind: MapConnectionKind,                          // 5 V1 (Q9-a same as PF_001)
    pub canon_ref: Option<BookCanonRef>,                  // book-grounded; None for author-added
    pub bidirectional: bool,                              // V1 hint-only (mirrors PF_001 §6 convention)
    pub gate_slot_id: Option<String>,                     // for Locked V1+ (resolves at write-time against gating fixture)

    // ─── Distance + cost (Q11-a + Q12-a; space-game pattern) ───
    pub distance_units: u32,                              // canonical abstract leagues (invariant across methods)
    pub default_fiction_duration: FictionDuration,        // OnFoot baseline V1; V1+ TVL_001 derives method-modified durations
}
```

**Rules:**
- One row per `channel_id`. Primary key conflict = `map.duplicate_layout`.
- Every channel from `root_channel_tree` (continent through cell) MUST have a `map_layout` row at bootstrap. Channels without layout reject runtime ops with `map.missing_layout_decl`.
- `tier_metadata`: Some iff `tier ∈ {Continent, Country, District, Town}`; None iff `tier == Cell`. Mismatch rejects `map.invalid_tier_metadata`.
- `position.x` and `position.y` MUST be in `0..=1000` (inclusive); out-of-bounds rejects `map.position_out_of_bounds`.
- `connections[]`: non-empty only for non-cell tiers; cell-tier `connections` MUST be empty (cell graph edges live on PF_001 `place.connections`). Cell-tier non-empty connections reject `map.invalid_tier_metadata` (collapsed for V1; V1+ separate rule_id if needed).
- `connections[].to_channel` MUST resolve to existing map_layout row at SAME tier as `self` (cross-tier disallowed V1; rejects `map.cross_tier_connection_disallowed`).
- `connections[].to_channel` MUST NOT equal `self.channel_id` (no self-loops); rejects `map.self_referential_connection`.
- `connections[].distance_units > 0`; zero or unset rejects `map.connection_distance_invalid`.
- All asset_ref fields are `None` V1 (schema-only; V1+ MAP_002 populates). Reads with non-None values during V1 reject `map.asset_ref_unresolved` (defensive — should never fire V1).

---

## §4 MapConnectionKind closed enum

```rust
pub enum MapConnectionKind {                              // 5 V1 — matches PF_001 ConnectionKind 1:1 for consistency (Q9-a)
    Public,                                               // anyone can pass
    Private,                                              // canonical residents only (V1: hard-reject for non-residents)
    Locked,                                               // gated by fixture (V1: always reject; V1+ key-matching via TVL_001)
    Hidden,                                               // discoverable via Examine (V1: visible-to-all; V1+ per-PC discovered_nodes)
    OneWay,                                               // enter but not exit (reverse Travel reject)
}
```

**Why same as PF_001:** consumer features (PL_001 Travel resolver, UI map renderer, LLM AssemblePrompt) operate on a unified ConnectionKind taxonomy at all tiers. Adding tier-specific variants (TradeRoute / CulturalLink / etc.) was rejected V1 — V1 strictly mirrors PF_001 to avoid forking the kind taxonomy. V1+ extensions tracked under MAP-D2.

**Visual encoding mapping** (consumed by demo `MAP_GUI_v1.html` and future MAP renderer):

| MapConnectionKind | Stroke color | Stroke style | Marker |
|---|---|---|---|
| Public | `#4d5762` (neutral) | solid | none |
| Private | `#6e3a8a` (purple) | dashed (6,4) | none |
| Locked | `#d29922` (gold) | dashed (2,4) | gate icon at midpoint |
| Hidden | `#484f58` (muted) | dashed (1,3); 50% opacity | none |
| OneWay | `#f85149` (red) | solid | arrowhead at to-end |

---

## §5 Position model + viewport scaling

**Author-positioned absolute** within parent viewport (Q3-a):
- Continent-tier positions sit within reality-root viewport (0..1000 × 0..1000)
- Country-tier positions sit within their parent continent's viewport (0..1000 × 0..1000 — reset at each tier)
- District-tier positions within parent country's viewport
- Town-tier positions within parent district's viewport
- Cell-tier positions within parent town's viewport

**Why per-tier viewport reset:** UI renders one tier at a time (drill-down). Each tier's viewport is independent — author authoring a country's region layout doesn't worry about positions colliding with sibling country's regions. Demo `MAP_GUI_v1.html` validated this drill-down + viewport-reset pattern.

**Position constraints:**
- `0 ≤ x ≤ 1000` (inclusive both ends; rejects out-of-range with `map.position_out_of_bounds`)
- `0 ≤ y ≤ 1000`
- Two siblings MAY share exact position (visual overlap permitted; author responsibility to prevent in practice)

**V1+ deferrals:**
- MAP-D5: auto-layout (D3 force-directed) with author-pin override — V1 strictly author-positioned
- MAP-D6: relative-percentage positions (instead of absolute u32) for responsive UI — V1 absolute u32 for simplicity

---

## §6 TierMetadata for non-cell tiers

Non-cell tiers (continent/country/district/town) carry semantic info via `tier_metadata: Some(TierMetadata)`. Cell tier (`tier_metadata = None`) reads display_name from PF_001 `place.display_name` (canonical source).

**Why split:** prevents duplication. If MapLayout cell-tier carried display_name, it would have to mirror PF_001's. Mirror invariant maintenance is error-prone. Q1-a chose conditional schema (Option<TierMetadata>) to enforce single-source-of-truth.

**TierMetadata fields:**
- `display_name: LocalizedName` — multi-locale (vi V1; en V1+ per PF-Q3 LocalizedName ownership decision; will move to 00_foundation when more shared schemas adopt it)
- `canon_ref: BookCanonRef` — book-grounded source for the tier (e.g., "Đại Tống" anchored to Tiên Nghịch Q1; "Lâm An Phủ" anchored to Q3 C12); AuthorCreated for author-added non-canonical layouts
- `description: String` — freeform LLM context for AssemblePrompt scene narration; e.g., "Trung tâm văn hóa, ngàn năm hưng thịnh. Nhiều tông môn lớn." Used in info-pane sidebar + LLM prompt header.

---

## §7 Image asset architecture (V1 schema, V1+ pipeline)

```rust
pub struct ImageAssetRef {
    pub asset_id: Uuid,                                   // unique within reality
    pub source: AssetSource,                              // closed enum 4 V1
    pub mime_type: String,                                // "image/png" | "image/jpeg" | "image/webp"
    pub storage_uri: String,                              // s3://loreweave-assets/<reality_id>/<asset_id> for AuthorUploaded/PlayerUploaded
                                                          // s3://loreweave-canonical/<book_canon_ref>/<asset_id> for CanonicalSeed
                                                          // s3://loreweave-llm-gen/<reality_id>/<asset_id> for LlmGenerated
    pub uploaded_by: Option<UserId>,                      // None for CanonicalSeed + LlmGenerated; Some for {Author,Player}Uploaded
    pub uploaded_at_fiction_time: FictionTime,
    pub generation_prompt: Option<String>,                // present iff source == LlmGenerated
    pub author_review_state: AssetReviewState,            // V1+ Forge gate
}

pub enum AssetSource {                                    // closed enum 4 V1 (Q6-a)
    AuthorUploaded,                                       // co-author or owner uploads
    PlayerUploaded,                                       // PC owner uploads (gallery; per-reality scope)
    LlmGenerated,                                         // V2+ AI-generated via prompt; cost-gated per provider-registry
    CanonicalSeed,                                        // V1+ bundled with reality bootstrap (book-derived art)
}

pub enum AssetReviewState {                               // closed enum 3 V1 (Q6 sub-decision)
    Pending,                                              // V1+ author-review queue (Forge integration)
    Approved,                                             // visible to all in reality
    Rejected,                                             // hidden; audit trail kept
}
```

**V1 behavior:** all `ImageAssetRef` field values are `None` (icon_asset / background_asset / inline_artwork all None). UI falls back to:
- icon: emoji per PlaceType (cell tier; from PF_001 default-affordance + per-type hints in PF_001 §4 table)
- background: plain dark gradient (demo)
- inline_artwork: empty info-pane visual; just text description

**V1 never writes ImageAssetRef.** All asset fields are schema reservations only. The 5 demo cells in `MAP_GUI_v1.html` use emoji fallbacks, validating the V1 baseline UX without art.

**V1+ implementation phases (deferred to future MAP_002 Asset Pipeline feature):**

| Phase | Source enabled | Pipeline |
|---|---|---|
| V1+30d | AuthorUploaded + CanonicalSeed | Forge UI for upload; S3/MinIO storage; per-reality bucket; mime-type validation; size cap (e.g., 2MB) |
| V1+60d | PlayerUploaded | per-PC gallery; cost limits / quota; review queue (Pending → Approved/Rejected) via Forge |
| V2+ | LlmGenerated | provider-registry image-gen integration (DALL-E / Stable Diffusion / etc.); budget gating per usage-billing-service; generation_prompt audit; auto-Pending review state |

V1 schema slot makes V1+ rollout purely additive — existing MapLayout rows backfill with None → consumer features migrate field-by-field as MAP_002 phases land.

---

## §8 Distance + Travel cost integration (space-game pattern)

V1 V1+ scope split per Q11-a + Q12-a + Q14-a + Q15-b:

**V1 contracts:**
- Every non-cell-tier MapConnectionDecl carries `distance_units: u32` (canonical abstract leagues; > 0)
- Every non-cell-tier MapConnectionDecl carries `default_fiction_duration: FictionDuration` (OnFoot baseline)
- PL_001 §13 `/travel destination=<channel_id>` resolver consults MAP_001 to get duration
- PC's `fiction_duration_proposed` in TurnEvent is OPTIONAL V1 — if absent, resolver uses `default_fiction_duration`; if present, accepted as override (PC explicit choice — narrative time-skip, e.g., "I take 6 months" for cultivation breakthrough mid-travel)
- No V1 cap on duration (Q15-b); PC can /travel canonical edges of 6+ months

**V1 cell-tier:** PF_001 ConnectionDecl is unchanged (no distance_units / default_fiction_duration field per Q2-b). V1 cell-to-cell `/travel` falls back to per-reality default constant (1 hour V1; configurable in RealityManifest under `travel_defaults` field — see §9). Tracked as **MAP-D7** for V1+ PF_001 reopen if cell-tier canonical durations needed.

**Cross-tier scale interpretation** (author guidance, not enforced):

| Tier of edge endpoints | distance_units typical range | duration typical range |
|---|---|---|
| Continent ↔ Continent | 1000+ | months to years |
| Country ↔ Country | 100..1000 | weeks to months |
| District ↔ District | 10..100 | days to weeks |
| Town ↔ Town | 1..10 | hours to days |
| Cell ↔ Cell | (PF_001 owns; V1 default 1 hour) | (V1 constant) |

Author canonicalizes per book genre (Tiên Nghịch cultivation: cross-continent travel = years, fits canon). V1+ TVL_001 modulates `distance_units` by method speed → method-specific duration overrides default.

**V1 PL_001 §13 reopen** (light, in this commit):
- §13 step ④ Travel cost resolution — adds note that for non-cell-tier travel (which V1 PC can't initiate, but author scenarios may scripted-travel an NPC across tiers), `default_fiction_duration` from MAP_001 is the authoritative cost
- §13 step ④ for cell-tier travel — falls back to RealityManifest `travel_defaults.cell_to_cell_duration` (default 1 hour) — see §9

**V1 PC realistic flow** (cell-to-cell within a region):
```
PC issues /travel destination=cell:tay_thi_quan
  ↓ EVT-T1 Submitted PCTurn { kind: Travel, destination: cell_id, fiction_duration_proposed: None }
PL_001 §13 step ④:
  - resolve PF_001 connection (PF_001 §6.X resolve_travel_connection) → ConnectionDecl found, Public, OK
  - cell-tier travel: read RealityManifest.travel_defaults.cell_to_cell_duration → 1 hour
  - or: PC explicit fiction_duration_proposed=Some(6 hours) → accepted
  → fiction_duration commit
```

**V1+ PC realistic flow** (cross-region travel):
```
PC at cell A in Lâm An Phủ issues /travel destination=region:hangzhou_district  // cross-tier
  ↓ V1: hard reject — V1 cross-tier travel disallowed (LX-D-related; multi-hop pathfinding deferred per Q14-a)
V1+: Travel resolver computes shortest path via region-tier MAP_001 connections
   → multi-hop: cell A → region:lin_an_district → region:hangzhou_district → spawn cell within
   → total fiction_duration = sum(MAP_001 default_fiction_duration along path) + cell-arrival default
```

V1 keeps it simple: PC /travel to single edge (cell-cell or region-region author-driven). Pathfinding deferred MAP-D8.

---

## §9 RealityManifest extension + `map.*` RejectReason namespace

**Extension to RealityManifest** (per `_boundaries/02_extension_contracts.md` §2):

```rust
pub struct RealityManifest {
    // ... existing Continuum-owned + WA + NPC + PF fields ...

    // ─── MAP_001 Map Foundation extension (added 2026-04-26) ───
    pub map_layout: Vec<MapLayoutDecl>,                   // REQUIRED V1; one per channel from root_channel_tree
    pub travel_defaults: TravelDefaults,                  // V1 cell-to-cell fallback
}

pub struct MapLayoutDecl {
    pub channel_id: ChannelId,
    pub tier: ChannelTier,
    pub position: MapPosition,
    pub tier_metadata: Option<TierMetadata>,              // Some for non-cell; None for cell
    pub initial_icon_asset: Option<ImageAssetRef>,        // V1 always None; reservation
    pub initial_background_asset: Option<ImageAssetRef>,  // V1 always None
    pub initial_inline_artwork: Option<ImageAssetRef>,    // V1 always None
    pub connections: Vec<MapConnectionDecl>,              // non-empty for non-cell; empty for cell
}

pub struct TravelDefaults {
    pub cell_to_cell_duration: FictionDuration,           // V1 fallback when PC /travel cell→cell with no proposed duration
                                                          // and PF_001 ConnectionDecl has no canonical duration
                                                          // Default: 1 hour. Author override per reality.
}
```

**`map.*` RejectReason namespace V1** (owned by MAP_001; registered in `_boundaries/02_extension_contracts.md` §1.4):

| rule_id | Trigger | Vietnamese reject copy V1 | Soft-override eligible |
|---|---|---|---|
| `map.missing_layout_decl` | channel exists without `map_layout` row at runtime | "Vị trí chưa được tô hình bản đồ." | No (bootstrap invariant) |
| `map.duplicate_layout` | second write attempt for `channel_id` already with row | "Vị trí này đã có bản đồ." | No (write-time invariant) |
| `map.position_out_of_bounds` | x or y outside `0..=1000` | "Tọa độ không hợp lệ." | No (write-time validator) |
| `map.connection_target_unknown` | MapConnectionDecl `to_channel` references non-existent channel | "Đích kết nối không tồn tại." | No (write-time validator) |
| `map.cross_tier_connection_disallowed` | MapConnectionDecl `to_channel` is at different tier than `self` | "Kết nối khác cấp không được phép V1." | No (V1 invariant; V1+ may allow per MAP-D9) |
| `map.invalid_tier_metadata` | `tier_metadata = None` but `tier ≠ Cell`, OR `tier_metadata = Some` but `tier == Cell`, OR cell-tier `connections` non-empty | "Cấu trúc cấp bản đồ không hợp lệ." | No (write-time validator) |
| `map.asset_ref_unresolved` | asset_id doesn't exist in storage at read-time (V1 should never fire since all asset fields None) | "Không tìm thấy tài nguyên hình ảnh." | No (defensive) |
| `map.asset_review_pending` | UI requests asset that's still Pending review | "Hình ảnh đang chờ duyệt." | Yes (V1+ Forge integration; UI can fall back to icon emoji) |
| `map.connection_distance_invalid` | `distance_units == 0` for non-cell connection | "Khoảng cách không hợp lệ." | No (write-time validator) |
| `map.self_referential_connection` | `to_channel == self.channel_id` (self-loop) | "Kết nối không thể trỏ về chính nó." | No (write-time validator) |

**V1+ rule_id reservations** (additive per I14):
- `map.cross_reality_layout` — V1+ multiverse portal layouts spanning realities
- `map.layout_too_dense` — V1+ tier-density ceiling (e.g., > 50 sibling nodes hurts UI)
- `map.connection_method_unsupported` — V1+ TVL_001 method-matrix gating

---

## §10 DP primitives consumed

MAP_001 implements one aggregate against the locked DP contract; no new primitives needed.

| DP primitive | Used for | Pattern |
|---|---|---|
| `t2_read(map_layout, key=channel_id)` | look up node position + connections + tier metadata + asset refs for UI render | Hot-path on map open + drill-down; cached per DP-K6 subscribe |
| `t2_write(map_layout, key=channel_id, mutation)` | author-edit via Forge · runtime in-fiction layout updates V1+ | Aggregate-Owner role per DP-K5 |
| `subscribe(map_layout, filter)` | UI invalidation on layout change · LLM AssemblePrompt context refresh · WA_003 Forge admin UI live preview | DP-K6 durable subscribe |
| `t2_scan(map_layout, filter)` | rare admin queries (find all nodes in tier X) | NOT hot-path; admin/audit only — DP-A8 |

**No new DP-K* primitives requested.** MAP_001 fits within existing kernel surface.

---

## §11 Capability JWT claims

MAP_001 declares no new top-level capability claim. Reuses existing claims:
- `produce: ["AggregateMutation", "AdminAction"]` — required to write `map_layout` + Forge admin edits (already present for world-service)
- Per-aggregate write capability under `capabilities[]` per DP-K9 — needs `map_layout:write`

**Service binding:** world-service is the canonical writer for `map_layout`. Forge UI (V1+) routes admin edits through world-service per WA_003 pattern.

---

## §12 Subscribe pattern

UI invalidation + downstream feature consumption via DP-K6 subscribe.

**Subscribers V1:**

| Subscriber | Filter | Purpose |
|---|---|---|
| Frontend (player UI) | `map_layout WHERE channel_id ∈ ancestor_chain(current_channel)` | drill-down map render at current tier |
| LLM AssemblePrompt | `map_layout WHERE channel_id = current_channel.parent` | `[MAP_CONTEXT]` section in prompt: tier_metadata + neighboring node names + connection summary |
| WA_003 Forge author UI | `map_layout WHERE reality_id = current` | author map editor; live preview |
| PL_001 §13 Travel resolver | `map_layout WHERE channel_id ∈ {from, to}` | distance + default_fiction_duration lookup at /travel time |
| Future MAP_002 Asset Pipeline | `map_layout WHERE *_asset.author_review_state = Pending` | review queue |

**Validator slot considerations:** EVT-V_map_layout runs as part of write-validator pipeline for layout mutations (write-time invariant checks for position bounds, connection validation, cross-tier rejection). Slot ordering deferred to `_boundaries/03_validator_pipeline_slots.md` alignment review (extends EF-Q3 + PF-Q1; tracked as **MAP-Q1**).

---

## §13 Cross-service handoff

ChannelId is the natural identifier; cross-service serialization reuses existing channel-id JSON shape:

```json
{
  "channel_id": "country:dai_tong",
  "tier": "Country",
  "position": { "x": 200, "y": 180 },
  "tier_metadata": {
    "display_name": { "vi": "Đại Tống", "en": null },
    "canon_ref": { "type": "BookCanon", "chapter": "Quyển 1 — Hồng Hoang" },
    "description": "Trung tâm văn hóa, ngàn năm hưng thịnh."
  },
  "icon_asset": null,
  "background_asset": null,
  "inline_artwork": null,
  "connections": [
    {
      "to_channel": "country:tay_van",
      "kind": "Public",
      "canon_ref": { "type": "BookCanon", "chapter": "Quan đạo cổ" },
      "bidirectional": true,
      "gate_slot_id": null,
      "distance_units": 350,
      "default_fiction_duration": { "value": 14, "unit": "Day" }
    }
  ]
}
```

Causality token chain unchanged: layout mutations include CausalityToken referencing the triggering EVT-T8 Administrative (Forge edit) or EVT-T1 Submitted (V1+ in-fiction trigger). Replay-determinism preserved per EVT-A9.

---

## §14 Sequences (5 V1 representative flows)

### 14.1 Canonical layout birth at RealityManifest bootstrap

```
RealityManifest.map_layout[i] = MapLayoutDecl { channel_id: country:dai_tong, tier: Country, position: (200, 180), ... }
  ↓ (bootstrap step 5 per PL_001 §16.2 — runs after PF_001 step ①c places + canonical EnvObjects)
RealityBootstrapper emits EVT-T4 System LayoutBorn { channel_id, tier, has_tier_metadata: true } per layout
  ↓ (atomic with bootstrap transaction)
write map_layout row { channel_id, tier, position, tier_metadata: Some(...), connections: [...], asset slots None, ... }
Validation: every channel from root_channel_tree has corresponding map_layout (mismatch rejects with map.missing_layout_decl + offending channel ids)
```

### 14.2 UI drill-down render (player opens map)

```
Player session: bind to reality root channel
  ↓ Frontend subscribes map_layout WHERE channel_id = continent:chu_tuoc_tinh (current view)
  ↓ Frontend queries children of current_channel via DP channel-tree → channel_ids of countries
  ↓ Frontend reads map_layout for each child channel_id (5 countries V1)
  ↓ render: SVG nodes at country positions; edges from connections[]; emoji icons (asset slots None V1)
Player clicks "Đại Tống" node:
  ↓ Frontend updates current_channel = country:dai_tong; subscribes map_layout for that channel + reads children (regions)
  ↓ render: SVG with regions
... drill down to cell tier, where PF_001 place data also reads (display_name + structural_state) for visual encoding
Player clicks cell node:
  ↓ Frontend exits map UI; transitions to cell-scene UI (PCS_001 / PL_001 scene_state — out of MAP_001 scope)
```

### 14.3 Travel resolution with canonical distance + duration (non-cell-tier; V1+ multi-hop)

```
Author triggers scripted-travel for an NPC: NPC_001 internal /travel from country:dai_tong to country:tay_van
  ↓ EVT-T1 Submitted NPCTurn { kind: Travel, destination: country:tay_van, fiction_duration_proposed: None }
PL_001 §13 step ④ Travel resolution:
  - resolve MAP_001 connection (from current_channel to destination):
      query map_layout(country:dai_tong).connections[] → find to_channel=country:tay_van
      → ConnectionDecl found: kind=Public, distance_units=350, default_fiction_duration=14 Day, canon_ref=Quan đạo cổ
  - kind=Public → pass; canon_ref propagates into Travel narrator
  - fiction_duration = 14 Day (from MAP_001 default_fiction_duration; NPC has no proposed override)
  → resolved
  ↓ PL_001 §13 step ⑤: t2_write entity_binding (NPC) location InCell(country:tay_van.capital_cell)
  ↓ DP emits MemberLeft + MemberJoined; FictionClock advances by 14 Day; LLM narrator gets canon_ref + 14-day flavor hint
```

### 14.4 Author-edit map layout via Forge (WA_003)

```
Author issues Forge:EditMapLayout { channel_id: country:dai_tong, edit_kind: UpdatePosition, before: { x: 200, y: 180 }, after: { x: 220, y: 200 } }
  ↓ EVT-T8 Administrative Forge:EditMapLayout commits
WA_003 Forge writes:
  - t2_write map_layout: position = after; last_layout_change_fiction_time = now
  - emit EVT-T3 Derived { aggregate_type: map_layout, delta: { position: ... } }
  - emit ForgeEdit audit log (forge_audit_log per WA_003)
Frontend subscribers receive update; map renders with new position
LLM next-turn AssemblePrompt sees updated map context for any /travel attempts
```

### 14.5 V1+ Image asset upload (illustrative; out of V1 scope)

```
[V1+30d MAP_002 Asset Pipeline feature when implemented]
Author uploads tavern background art via Forge UI:
  ↓ POST /v1/realities/:id/assets — multipart upload; mime-type validated; size checked
  ↓ MAP_002 stores S3/MinIO; creates ImageAssetRef { source: AuthorUploaded, author_review_state: Pending, ... }
  ↓ author_review_state = Approved (auto for AuthorUploaded V1+; review queue gates PlayerUploaded V1+60d)
  ↓ author Forge:EditMapLayout sets background_asset = Some(ref) on cell:yen_vu_lau's map_layout
  ↓ Frontend subscribers see new asset; UI background updates
```

V1: this flow doesn't exist; all asset slots are None.

---

## §15 Acceptance criteria

10 V1-testable scenarios (AC-MAP-1..10):

1. **AC-MAP-1 — RealityManifest map_layout extension required:** RealityManifest with `map_layout: []` (empty) but channels declared in `root_channel_tree` rejects bootstrap with `map.missing_layout_decl { offending_channels: [...] }`. Tests §3.1 invariant + §9 bootstrap order.
2. **AC-MAP-2 — Cell-tier tier_metadata invariant:** writing map_layout with `tier = Cell, tier_metadata = Some(...)` rejects `map.invalid_tier_metadata`. Symmetric: writing `tier = Country, tier_metadata = None` also rejects. Tests §3.1.
3. **AC-MAP-3 — ChannelTier variant exhaustiveness (compile-time):** Rust unit test that uses `match channel_tier` without arms for all 5 V1 variants fails to compile. CI lint flags `_ =>` arms outside designated catch-all sites with `// CLOSED-ENUM-EXEMPT: <reason>` annotation (unified per PF/EF closure pass conventions).
4. **AC-MAP-4 — Position out-of-bounds rejects:** writing map_layout with `position.x = 1500` (or `y = -10` etc.) rejects `map.position_out_of_bounds`. Tests §5.
5. **AC-MAP-5 — Cross-tier connection disallowed V1:** writing MapConnectionDecl with `to_channel` at different tier (e.g., country layout connecting to a region) rejects `map.cross_tier_connection_disallowed`. Tests §3.1 + §4.
6. **AC-MAP-6 — Self-referential connection rejects:** writing MapConnectionDecl with `to_channel == self.channel_id` rejects `map.self_referential_connection`. Tests §3.1.
7. **AC-MAP-7 — Distance must be positive:** writing MapConnectionDecl with `distance_units = 0` for non-cell-tier connection rejects `map.connection_distance_invalid`. Tests §8 + §3.1.
8. **AC-MAP-8 — Travel resolver consumes default_fiction_duration:** NPC /travel from country:A to country:B (where MAP_001 connection has `default_fiction_duration = 14 Day`) and `fiction_duration_proposed = None` results in committed TurnEvent with `fiction_duration_proposed = 14 Day` (auto-resolved). Tests §8 V1 contract + §14.3 sequence + PL_001 §13 light reopen.
9. **AC-MAP-9 — V1 asset slots are None:** at bootstrap, all `icon_asset / background_asset / inline_artwork` fields on every map_layout row are `None`. Reads succeed; UI renders fallback icons + plain background. Tests §7 V1 schema-only contract.
10. **AC-MAP-10 — Forge:EditMapLayout 3-write transaction atomicity:** Forge:EditMapLayout executes 3 writes in single Postgres transaction: (a) update map_layout row, (b) emit EVT-T8 Administrative `Forge:EditMapLayout`, (c) append to forge_audit_log (WA_003-owned). Mid-transaction failure → all 3 rollback. Tests §14.4 sequence + WA_003 forge_audit_log integration (mirror PF_001 AC-PF-8 pattern).

---

## §16 Deferrals

| ID | What | Why deferred | Target phase |
|---|---|---|---|
| **MAP-D1** | V1+ ChannelTier extensions (e.g., StarSystem / Sector / Galaxy for sci-fi realities; PocketDimension for cultivation) | Not V1-blocking; additive per I14 | When first such genre feature designed |
| **MAP-D2** | V1+ MapConnectionKind extensions (TimePortal / PocketDimension / Resonance) | V1+ supernatural travel kinds; current V1 mirrors PF_001's 5 kinds | V1+ supernatural feature design |
| **MAP-D3** | V1+30d MAP_002 Asset Pipeline feature (AuthorUploaded + CanonicalSeed pipelines) | requires Forge UI extension + S3/MinIO bucket setup; per-reality quotas | V1+30d implementation |
| **MAP-D4** | V1+60d MAP_002 PlayerUploaded pipeline | per-PC gallery + cost limits + review queue | V1+60d implementation |
| **MAP-D5** | V2+ MAP_002 LlmGenerated pipeline | provider-registry image-gen integration; budget gating | V2+ |
| **MAP-D6** | V1+ auto-layout (D3 force-directed) with author-pin override | V1 strictly author-positioned; profiling V1+30d | V1+30d if author UX needs |
| **MAP-D7** | PF_001 cell-tier ConnectionDecl distance + duration fields | V1 cell-to-cell uses RealityManifest.travel_defaults.cell_to_cell_duration constant; if profile shows ambiguity, reopen PF_001 | V1+30d profiling |
| **MAP-D8** | V1+ multi-hop pathfinding for cross-tier `/travel` | V1: PC /travel to single edge; manual sequential turns. Pathfinding helper computes shortest path | V1+30d if quest/exploration needs |
| **MAP-D9** | V1+ cross-tier connection allowance | V1 strict same-tier; V1+ may allow cell-to-cell across regions for portal/teleport semantics | V1+ supernatural travel feature |
| **MAP-D10** | V1+30d per-PC discovered_nodes fog-of-war | V1: all nodes visible; V1+ Hidden ConnectionKind activates per-PC discovery flags (also tracked in PF-D10) | V1+30d quest/exploration |
| **MAP-D11** | V2+ relative-percentage positions for responsive UI | V1 absolute u32 (0..1000); V2+ percentage if mobile rendering needs | V2+ frontend rendering V2 |
| **MAP-D12** | V1+ TVL_001 Travel Mechanics feature (speed/method matrix) | V1: OnFoot baseline only; V1+ TVL_001 derives method-modified durations from distance_units / speed_multiplier | V1+ when first non-OnFoot method needed (cultivation flying-sword urgent for SPIKE_01 grounding) |
| **MAP-D13** | V1+ tier-density ceiling validator (`map.layout_too_dense`) | V1 no cap; if author creates 100 sibling regions in one country, UI degrades | V1+30d profiling |
| **MAP-D14** | `BookCanonRef` shared-schema registration | inherited from PF-D12; same boundary cleanup pass | Future boundary cleanup / IF_001 design |

---

## §17 Cross-references

- **PL_001 Continuum** §16 RealityManifest — extended with `map_layout: Vec<MapLayoutDecl>` + `travel_defaults: TravelDefaults` (this commit; light reopen). §13 Travel sequence step ④ — extended to consume MAP_001 `default_fiction_duration` for non-cell-tier travel; cell-tier falls back to `travel_defaults.cell_to_cell_duration`.
- **PF_001 Place Foundation** — composes at cell tier. PF_001 owns `place` (semantic identity + cell ConnectionDecl with kind/canon/access rules). MAP_001 owns cell-tier visual layer (position + image asset slots; tier_metadata=None; connections=[]). UI renders both layers — PF_001 supplies display_name + PlaceType + StructuralState; MAP_001 supplies position + asset refs.
- **EF_001 Entity Foundation** — no direct dependency. EnvObjects at cell tier are addressed via PF_001 fixture-seed; MAP_001 doesn't render individual EnvObjects on map (cell node icon represents the whole cell).
- **DP channel hierarchy** (06_data_plane DP-Ch1..Ch53) — every channel from continent through cell may have a `map_layout` row. Channel creation order: DP creates channel, then PF_001 creates place row (for cell tier only), then MAP_001 creates layout row. Bootstrap step ordering owned by RealityBootstrapper (per PL_001 §16.2 reopen).
- **WA_003 Forge** — `Forge:EditMapLayout` AdminAction sub-shape registered. Forge UI V1+ extension to support map editor (out of MAP_001 V1 scope; tracked as MAP-D3).
- **NPC_001 Cast** — V1+ NPC routine paths (DF1 daily life) reference MapConnectionDecl for canonical movement durations.
- **PL_005 Interaction** — V1+ Examine of map node (e.g., "examine the country") could read tier_metadata.description for narrator content; MAP-Q3 watchpoint for ExamineTarget extension to non-cell tiers.
- **PL_002 Grammar** — `/travel destination=<channel_id>` consumes MAP_001 connection-resolver at non-cell tier; cell tier consumes PF_001 resolver. Both via PL_001 §13.
- **PL_006 Status Effects** — V1+ if "the country is under siege" status effect needed (PlaceState analog at non-cell tier); V1: no.
- **WA_001 Lex** — V1+ Lex axioms can reference ChannelTier (e.g., "magic strength varies by tier: Wilderness +20%, OfficialHall −30%"); current V1: PlaceType only.
- **WA_002 Heresy** — V1+ if per-region contamination spread; V1: per-actor only.
- **PCS_001** (when designed) — PC spawn cell MUST have valid map_layout row (V1 invariant). V1+ per-PC discovered_nodes set integrates with MAP-D10.
- **MV12 (multiverse)** — V1+ multiverse portals = MapConnectionDecl with V2+ MAP-D9 cross-reality kind.
- **future TVL_001 Travel Mechanics** — consumes MAP_001 `distance_units` for method-speed-modified duration computation. MAP-D12 reservation.
- **future MAP_002 Asset Pipeline** — populates ImageAssetRef field values (V1: all None). MAP-D3/D4/D5 phased rollout.

---

## §18 Readiness checklist

- [x] Domain concepts table covers MapLayout / MapPosition / ChannelTier / TierMetadata / MapConnectionDecl / MapConnectionKind / distance_units / default_fiction_duration / ImageAssetRef / AssetSource / AssetReviewState / MapLayoutDecl
- [x] Aggregate inventory: 1 aggregate (`map_layout` primary; T2/Channel scope; covers all tiers)
- [x] ChannelTier 5 V1 closed enum (Continent / Country / District / Town / Cell)
- [x] Place ↔ Channel composition explicit (cell-tier MAP_001 visual layer; PF_001 semantic; non-cell tier MAP_001 owns end-to-end)
- [x] Connection graph: hybrid (DP hierarchy implicit + Vec<MapConnectionDecl> explicit horizontal); 5 V1 ConnectionKinds matching PF_001
- [x] Position model: author-positioned absolute u32 (0..=1000); per-tier viewport reset
- [x] Image asset architecture: 3 slot reservations + 4 source variants + 3 review states; V1 schema-only with V1+ phased pipeline
- [x] Distance + Travel cost integration: distance_units (invariant) + default_fiction_duration (OnFoot baseline) + V1 cell-tier fallback constant; space-game pattern (EVE / Stellaris / FTL)
- [x] RealityManifest extension `map_layout: Vec<MapLayoutDecl>` + `travel_defaults: TravelDefaults` (registered in `_boundaries/02_extension_contracts.md` §2)
- [x] Reference safety policy: 10 V1 rule_ids in `map.*` namespace + 3 V1+ reservations
- [x] Event-model mapping: EVT-T3 Derived (`aggregate_type=map_layout`) + EVT-T4 System (`LayoutBorn`) + EVT-T8 Administrative (`Forge:EditMapLayout`); V1+ MAP_002 sub-shapes reserved; no new EVT-T*
- [x] DP primitives: existing surface only (no new DP-K*)
- [x] Capability JWT: existing claims (no new top-level)
- [x] Subscribe pattern: 5 subscribers V1 (Frontend / LLM AssemblePrompt / WA_003 Forge / PL_001 Travel resolver / future MAP_002 review queue)
- [x] Cross-service handoff: ChannelId JSON shape; tier_metadata + connections embedded
- [x] 5 representative sequences (canonical bootstrap / UI drill-down / NPC scripted-travel with canonical duration / Forge author-edit / V1+ asset upload illustrative)
- [x] 10 V1-testable acceptance scenarios (AC-MAP-1..10)
- [x] 14 deferrals (MAP-D1..D14) with target phases — covers V1+ asset pipeline phases · auto-layout · pathfinding · cross-tier connections · TVL_001 method matrix · LocalizedName/BookCanonRef shared-schema cleanups
- [x] Cross-references to all 14 affected features + foundation docs
- [ ] Phase 3 review cleanup pending
- [ ] CANDIDATE-LOCK pending closure pass + downstream updates (PCS_001 brief reading list / PL_001 §13 + §16.2 reopen confirm / demo `MAP_GUI_v2.html` update with distance labels)

---

## §19 Open questions (post-DRAFT)

| ID | Question | Resolution path |
|---|---|---|
| **MAP-Q1** | Validator slot ordering: EVT-V_map_layout relative to EVT-V_entity_affordance + EVT-V_place_structural + EVT-V_lex (extends EF-Q3 + PF-Q1) | `_boundaries/03_validator_pipeline_slots.md` alignment review (single pass for all 3 watchpoints) |
| **MAP-Q2** | LocalizedName ownership — currently in MAP_001 §3.1 + PF_001 §3.1 (PF-Q3 watchpoint already tracks); should promote to 00_foundation | Boundary review V1+ when more shared schemas adopt; combine with PF-D12 BookCanonRef registration |
| **MAP-Q3** | PL_005 Examine of non-cell-tier map node ("examine the country") — requires PL_005 ExamineTarget extension to accept ChannelId at non-cell tier | PL_005 closure pass + V1+ if author content needs |
| **MAP-Q4** | Bidirectional MapConnectionDecl semantics — Q3-a author-positioned says hint-only V1 (mirror PF_001 §6 convention); confirm same here? | confirmed inheritance from PF_001 §6 hint-only V1; PF-D14 covers both |
| **MAP-Q5** | Travel-default cell_to_cell_duration in RealityManifest — should this be per-PlaceType (Tavern→Tavern faster than Wilderness→Wilderness)? | V1: single global default; V1+ MAP-D7 PF_001 reopen for per-edge cell distance |
