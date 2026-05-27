# SPIKE_04 — GEO Procgen + Authoring Validation

> **Status:** DRAFT 2026-05-13 — exploratory walk-through validating GEO_001 + GEO_001b contracts against acceptance scenarios AC-GEO-1..11 + AC-AUTHOR-1..10 before V1 implementation locks them in. No code; no implementation; surface design gaps that the schema lock and POST-REVIEW didn't catch.
>
> **Scope:** Walk through 6 concrete test scenarios that collectively exercise all 21 acceptance criteria against fixture data (Thần Điêu Đại Hiệp Nam Tống reality from SPIKE_01 + GEO §14.1). Surface concrete design gaps, ambiguities, and missing sub-contracts. Output: observations + open questions + graduation recommendations.
>
> **NOT in scope:** Implementation (V1 phase). New aggregates. Boundary lock claims (no new namespace; this is read-only against locked GEO_001 + GEO_001b). Image rendering. Strategy substrate consumption (GEO_002+ V1+/V2+).
>
> **Conversational name:** "GEO Validation Spike" — feeds V1 implementation phase + V1+30d deferred-item triage.

**Active:** main session 2026-05-13 (DRAFT this commit; observations + graduation in §9-§11)

---

## §1 — Why this spike exists

GEO_001 DRAFT + fix cycle + GEO_001b DRAFT have established the *materialized schema* (GEO_001) + *write-side authoring contract* (GEO_001b) + 11 + 10 = 21 acceptance scenarios. Two prior validation passes (POST-REVIEW + /review-impl) caught 11 architectural issues that surfaced as concrete schema bugs. But:

- POST-REVIEW = author-blind self-review (caught 0; rubber-stamped).
- /review-impl = adversarial self-review against the doc (caught 11; very valuable).
- **Neither walked the acceptance scenarios end-to-end with fixture data.** AC text says "Bootstrap continent → world_geometry has 2048 cells" but doesn't verify the operational sequence: who emits which event, in what order, what does the validator see, what gets persisted where. The gap between "the schema says X" and "an implementer can produce X from the schema" is the gap this spike closes.

Per `_spikes/_index.md` rule "a design question is unclear in the abstract; one concrete example would force the answer" — six concrete scenarios force six categories of answers.

---

## §2 — Fixture reality

Reuse SPIKE_01's Thần Điêu Đại Hiệp Nam Tống setting + GEO §14.1 fixture:

| Field | Value |
|---|---|
| reality_id | `R_alpha_southern_song` |
| author_user_id | `Lý Minh` (from SPIKE_01) |
| continent_channel_id | `continent:southern_song` |
| master_seed | `0xA1B2C3D4` |
| world_scale | `Region (~2048 cells)` |
| archetype | `Wuxia` |
| coastline_profile | `Coastal` |
| hemisphere_orientation | `Northern` |
| canonical_settlements (3) | Tương Dương (Capital), Khai Phong (City), Yên Vũ Lâu (Town) |
| culture_hints (2) | han_jiangnan + mongol_steppe |
| naming_styles (2) | `tang_song_chinese` Markov corpus + `mongolian_pastoral` Markov corpus |
| pipeline_version | 1 |

---

## §3 — Scenario 1: LLM-authored bootstrap (AC-AUTHOR-1 + AC-GEO-1 + AC-AUTHOR-7)

**Setup:** Author Lý Minh submits intent: "Wuxia world, Nam Tống dynasty, focus on Tương Dương region. Han Jiangnan culture + Mongol steppe culture at northern border."

**Walk-through:**

```
T0: BFF receives POST /v1/realities/draft → creates AuthoringSession{
      session_id: BFF-generated UUID,
      author_user_id: Lý Minh,
      intent: I18nBundle{vi: "Wuxia, Nam Tống...", default: vi},
      producer: AuthoringProducer::LlmGenerated{
        template_ref: PromptTemplateRef("world_authoring/v1"),
        knowledge_grounding: None  // V1 (knowledge-service not yet shipped)
      },
      iterations: [],
      current_draft: None,
      total_llm_cost_usd: 0,
      total_llm_calls: 0,
      state: InProgress,
      created_at: 2026-05-13T10:00:00Z,
    }

T1: BFF calls chat-service /v1/generate with:
    - template_ref: "world_authoring/v1"
    - context: {
        [SYSTEM]: 1240 tokens (template-defined),
        [WORLD_CANON]: 0 tokens (V1 ungrounded; knowledge_grounding=None),
        [SESSION_STATE]: 0 tokens (pre-bootstrap),
        [ACTOR_CONTEXT]: 340 tokens (Lý Minh profile; PII-scrubbed),
        [MEMORY]: 0 tokens (no NPC memory yet),
        [HISTORY]: 0 tokens (iteration 0),
        [INSTRUCTION]: 1180 tokens (CreativeSeed schema instructions + SpatialPreference enum reference),
        [INPUT]: 120 tokens (author intent XML-escaped),
        TOTAL PROMPT: ~2880 tokens (well under 14000 budget per §12Y.L6)
      }
    - response_format: { type: "json_schema", json_schema: { schema: <creative_seed.v2.schema.json>, strict: true } }
    - max_output_tokens: 4000

T2: chat-service routes via LiteLLM to user's BYOK provider (or platform pool per S6).
    Provider returns CreativeSeed JSON v2 (~1840 output tokens):
    {
      "schema_version": 2,
      "archetype": "Wuxia",
      "world_scale": "Region",
      "hemisphere_orientation": "Northern",
      "coastline_profile": "Coastal",
      "climate_bias": null,
      "culture_hints": [
        {
          "hearth_position_normalized": null,            // V1+ schema_version=2: optional
          "hearth_preference": "NearBiome(Plain)",       // NEW V1+: LLM picks named spatial intent
          "naming_style_ref": "han_jiangnan",
          "value_tags": ["scholar", "merchant", "honor"]
        },
        {
          "hearth_position_normalized": null,
          "hearth_preference": "NearClimate(Boreal)",
          "naming_style_ref": "mongolian_pastoral",
          "value_tags": ["warrior", "nomad", "horse"]
        }
      ],
      "canonical_settlements": [
        { "name": {"vi": "Tương Dương", ...}, "position_normalized": null,
          "spatial_preference": "NearBiome(Plain)", "role": "Capital", "population_tier": 4, "canon_ref": null },
        { "name": {"vi": "Khai Phong", ...}, "position_normalized": null,
          "spatial_preference": "NearBiome(Plain)", "role": "City", "population_tier": 3, "canon_ref": null }
      ],
      "canonical_provinces": [],
      "lore_hooks_per_region": [],
      "naming_styles": {
        "han_jiangnan": {"markov_corpus_ref": "tang_song_chinese", "llm_prompt_template": null},
        "mongolian_pastoral": {"markov_corpus_ref": "mongolian_pastoral", "llm_prompt_template": null}
      }
    }

T3: Provider response → chat-service records cost ($0.12) in S6 user_cost_ledger.
    AuthoringSession.total_llm_cost_usd: 0 → 0.12; total_llm_calls: 0 → 1.

T4: BFF validation pipeline (5 steps):
    1. JSON parse: OK (response was schema-constrained)
    2. Schema validation: OK
    3. Cap validation: 2 cultures ≤ 16, 2 settlements ≤ 50, all positions/preferences valid
    4. Reference validation: V1 SKIP (knowledge-service not shipped)
    5. Content safety: OK (no PII in lore_hooks; no injection patterns)

T5: AuthoringIteration logged in session. current_draft = the CreativeSeed.
    UI renders draft for author review (UI for Wuxia archetype + 2 cultures + 2 settlements).

T6: Author: "Add Yên Vũ Lâu town near Tương Dương" → AuthorAction::RejectAndRetry{
      feedback: I18nBundle{vi: "Thêm Yên Vũ Lâu...", default: vi}
    }

T7: BFF calls chat-service with [HISTORY] now containing iteration 1:
    - author intent + LLM output JSON snippet + feedback ("add Yên Vũ Lâu")
    - History tokens: ~620 tokens
    - Total prompt: ~3500 tokens
    Provider returns new CreativeSeed v3 with 3rd canonical_settlement:
    { ..., canonical_settlements: [..., { name: "Yên Vũ Lâu",
      spatial_preference: "NearSettlement(\"Tương Dương\")",  // closed-enum reference
      role: "Town", population_tier: 2, canon_ref: null }] }

T8: Validation: ✓. Cost: $0.15 (slightly higher due to longer prompt).
    AuthoringSession.total_llm_cost_usd: 0.12 → 0.27; total_llm_calls: 1 → 2.

T9: Author Accepts → AuthorAction::Accept → AuthoringState::Accepted.
    AuthoringMetadata constructed: {
      producer: LlmGenerated{template_ref: "world_authoring/v1", knowledge_grounding: None},
      total_llm_cost_usd: 0.27,
      total_llm_calls: 2,
      iteration_count: 2,
      author_user_id: Lý Minh,
      authoring_template_version: 1,
      knowledge_grounding_book_id: None,
      authoring_started_at: 2026-05-13T10:00:00Z,
      authoring_completed_at: 2026-05-13T10:03:42Z,
    }

T10: BFF calls world-service /v1/realities/bootstrap with full RealityManifest +
     authoring_metadata embedded. RealityBootstrapper emits:
     EVT-T4 System GeographyBorn{
       continent_channel_id: continent:southern_song,
       seed: GeographySeed{master_seed: 0xA1B2C3D4, ...},
       creative_seed_hash: blake3(creative_seed_json) = 0x1234...,
       voronoi_cell_count: 2048,
       generator_pipeline_version: 1,
       authoring_metadata: Some(authoring_metadata)  // NEW per GEO_001b
     }

T11: world-service runs procgen pipeline stages 1-4 deterministically from
     sub-seeds. Stage 4 sub-stages: 4a hydraulic erosion → river_flux; 4b
     connected-components → Ocean (~30% cells in main water body) vs Lake
     (isolated water cells, mostly inland in mountain regions); 4c biome
     mapping. Canonical settlement materialization V1: Tương Dương / Khai
     Phong / Yên Vũ Lâu placed at cells satisfying their spatial_preference
     (NearBiome(Plain) for first 2; NearSettlement("Tương Dương") radius
     ≤ 0.1 normalized for Yên Vũ Lâu).

T12: world_geometry aggregate persisted (T2/Channel-continent); ~1MB on disk.
     ✅ AC-AUTHOR-1 PASS, ✅ AC-GEO-1 PASS, ✅ AC-AUTHOR-7 PASS.
```

**Observations / gaps surfaced:**

- **GAP-S1.A** — `creative_seed.v2.schema.json` generation pipeline isn't specified. WHEN does schemars run? Build-time → ship the JSON alongside the binary? Or at chat-service runtime → derive from compiled Rust struct via reflection? Build-time is cleaner (versionable, diffable, fixturable per S9 §12Y.L9). Should declare in GEO_001b §5.3.
- **GAP-S1.B** — CreativeSeed JSON size for typical worlds: ~1840 tokens output observed in scenario 1. For Megaplanet scale with 50 canonical_settlements + 16 culture_hints + full lore_hooks, could reach ~3500 output tokens. Token budget §12Y.L6 says ≤4000 output — TIGHT. V2+ may need budget bump.
- **GAP-S1.C** — `canonical_settlements.name` UNIQUENESS not enforced anywhere. If LLM produces 2 settlements both named "Tương Dương" by mistake, no schema rule rejects. SpatialPreference::NearSettlement("Tương Dương") becomes ambiguous. Need explicit validator: `authoring.duplicate_settlement_name` reject + uniqueness rule in GEO_001 §3.
- **GAP-S1.D** — Forward-reference DAG: SpatialPreference::NearSettlement(name) where the referenced settlement is *also being declared in the same canonical_settlements array*. Stage 6 placement needs topological sort. What if A.preference=NearSettlement(B) AND B.preference=NearSettlement(A)? Cycle. Procgen must reject or break cycle deterministically. Needs new reject rule_id `authoring.spatial_preference_cycle`.

---

## §4 — Scenario 2: Replay determinism (AC-GEO-2)

**Setup:** Two separate realities R_alpha and R_zeta both author identical CreativeSeed (same seed, same culture_hints, same canonical_settlements, same naming_styles). Expected outcome: byte-identical world_geometry aggregate after stages 1-4.

**Walk-through:**

```
T0: R_alpha bootstrapped with master_seed=0xA1B2C3D4, creative_seed_json (sorted-key JSON).
T1: world-service runs pipeline:
    - voronoi_seed = blake3(master_seed, b"voronoi") = 0x7F3E... (deterministic)
    - Stage 1 Voronoi: Poisson-disk sample with voronoi_seed → 2048 cell centers
      (Fortune's algorithm; deterministic ordering by cell.center.x then center.y)
    - Stage 2 Heightmap: Perlin with erosion_seed=blake3(master, "erosion")
      + radial Coastal falloff → per-cell u16
    - Stage 3 Climate: latitude+altitude+ocean-distance → per-cell ClimateZone
    - Stage 4a: river_flux f32 per cell (deterministic — flux accumulates
      downhill; tie-break by cell_id ascending)
    - Stage 4b: connected-components water network — flood-fill from border
      water cells (deterministic — BFS order = cell_id ascending)
    - Stage 4c: BiomeKind per cell

T2: R_zeta bootstrapped with IDENTICAL master_seed + creative_seed_json.
T3: Pipeline reruns deterministically — same blake3 sub-seeds; same Poisson-disk
    sample; same Voronoi; same heightmap; same biomes.

T4: Compare R_alpha.world_geometry serialized bytes vs R_zeta.world_geometry:
    - cells[]: identical (same Voronoi seed + same order)
    - neighbors[][]: identical (deterministic Delaunay dual)
    - heightmap[]: identical
    - climate_zones[]: identical
    - river_flux[]: identical
    - biomes[]: identical
    - is_coast[]: identical
    - settlements[] (canonical-pinned): identical IF settlement_seed stage 6 V1+
      activation is consistent (V1 only canonical_settlements materialized, so
      same input → same output)
    - naming_styles HashMap → SERIALIZED via sorted BTreeMap iteration
    - ✅ AC-GEO-2 PASS
```

**Observations / gaps surfaced:**

- **GAP-S2.A** — HashMap normalization is a real implementation concern. `naming_styles: HashMap<CultureTag, NamingStyleDecl>` — Rust's HashMap iteration order is non-deterministic. The serialization layer (postgres COPY / messagepack / etc.) MUST sort keys (CultureTag is sortable as String). GEO_001 §5 says "modulo HashMap iteration order, which the generator MUST normalize via deterministic sort" but the implementation discipline isn't enforceable from doc alone. Need CI gate: snapshot test producing byte-hash of world_geometry → compare against fixture hash per (master_seed, creative_seed_hash).
- **GAP-S2.B** — Stage 4a river_flux uses f32; non-associative floating-point arithmetic could drift across SIMD vs scalar paths. Need either: (a) deterministic floating-point mode (-ffp-contract=off / strict IEEE); or (b) fixed-point representation (i32 with implicit decimal). Spec doesn't say. Implementation risk → CI gate.
- **GAP-S2.C** — `creative_seed_hash` computation: blake3(creative_seed_json) — but JSON serialization is not unique (key order, whitespace). MUST use canonical JSON serialization (RFC 8785 JCS or equivalent). Implementation cannot rely on `serde_json::to_string` (key order is arbitrary). Need explicit spec.
- **GAP-S2.D** — Cross-platform determinism: Rust target tier (x86_64 vs ARM vs WASM) may produce different blake3 output for identical input? Should be IDENTICAL (blake3 is byte-deterministic), but worth a CI gate snapshot test across platforms.

---

## §5 — Scenario 3: Admin canonization workflow (AC-GEO-4 + AC-GEO-5 + AC-GEO-11)

**Setup:** Reality R_alpha already bootstrapped (Scenario 1). Author plays a session; Tiểu Long Nữ founds Cold Pool Academy at cell 1247 (mountain biome). Author canonizes via Forge.

**Walk-through:**

```
T0: world_geometry state: geography_deltas=[]; last_delta_event_id=None;
    settlements has 3 canonical (Tương Dương, Khai Phong, Yên Vũ Lâu).

T1: Author opens Forge UI; selects continent_channel_id=continent:southern_song;
    selects DeltaKind=AddNamedSettlement; fills:
    cell_id: 1247 (Mountain biome cell selected via map UI)
    name: I18nBundle{en: "Cold Pool Academy", vi: "Học Viện Hàn Trì"}
    role: SettlementRole::Hamlet
    population_tier: 1
    prev_delta_id: None  (geography_deltas is empty)
    reason: I18nBundle{vi: "Tiểu Long Nữ thành lập học viện ẩn cư trong đỉnh Hàn Sơn..." 78 chars}

T2: BFF POST /v1/forge/geography/edit-delta → world-service emits
    EVT-T8 Administrative Forge:EditGeographyDelta{
      continent_channel_id: continent:southern_song,
      delta_kind: AddNamedSettlement{cell_id: 1247, name, role, population_tier},
      delta_payload: <bincode>,
      prev_delta_id: None,
    }

T3: Validator pipeline:
    1. AuthorizationGate: Lý Minh's JWT has can_edit_geography for continent ✓
    2. SchemaGate: AddNamedSettlement payload typecheck ✓
    3. ReferentialIntegrityGate: cell_id=1247 ∈ cells; biomes[1247]=Mountain
       (valid for Hamlet); ✓
    4. OrderingGate: prev_delta_id=None matches world_geometry.last_delta_event_id=None ✓
    5. ContentSafetyGate: reason scrubbed via §12X.L7 PII regex; name scrubbed
       via §12Y.L5 injection scanner; ✓

T4: All pass → EVT-T3 Derived emitted: aggregate_type=world_geometry, field_delta:
    geography_deltas.push(GeographyDelta{
      id: GeographyDeltaId(1),  // first delta this aggregate row
      kind: AddNamedSettlement{...},
      authored_by_actor_id: Lý Minh,
      reason: <i18n bundle>,
    });
    last_delta_event_id = <this_event_id_42>;
    settlements.push(Settlement{
      id: SettlementId::new(),  // <-- GAP-S3.E
      name, cell_id: 1247, role: Hamlet, population_tier: 1,
      canon_ref: None, channel_id: None
    });
    ✅ AC-GEO-4 PASS.

T5: Stale prev_delta_id test:
    Author submits SECOND delta with prev_delta_id=None (stale; should be 42).
    OrderingGate fails: prev_delta_id=None != last_delta_event_id=42.
    Reject: geography.delta_order_violation
    User copy: "Thứ tự chỉnh sửa địa lý sai. Tải lại và thử lại."
    Author refreshes UI; resubmits with prev_delta_id=42; succeeds.
    ✅ AC-GEO-5 PASS.

T6: HookScope resolution test (AC-GEO-11):
    Earlier CreativeSeed had lore_hooks_per_region with:
    [0] {scope: SettlementByName(LocalizedName{vi: "Yên Vũ Lâu",...}), content: ...}
    [1] {scope: PositionRegion{center: (0.45, 0.55), radius_normalized: 0.05}, content: ...}
    [2] {scope: Archetype, content: ...}

    Post-stage-6 resolution:
    [0] SettlementByName → settlements.iter().find(|s| s.name == query) →
        Some(SettlementId::for_yen_vu_lau).
        Hook binds to that settlement; LLM prompt-assembly for cells within
        Yên Vũ Lâu's neighborhood fetches this hook.
    [1] PositionRegion → cells.iter().filter(|c|
        distance(c.center, (0.45, 0.55)) ≤ 0.05).collect() →
        Vec<GeoCellId> covering the 0.05-radius disc (~30 cells).
        Hook binds to those cells; LLM prompt-assembly for any cell in set
        fetches this hook.
    [2] Archetype → applies globally; LLM prompt-assembly always fetches.
    ✅ AC-GEO-11 PASS.
```

**Observations / gaps surfaced:**

- **GAP-S3.E** — `SettlementId::new()` generation strategy NOT specified. Options: (a) sequential u32 per continent (`settlements.len() as u32`; risks reuse on rollback); (b) UUID v4 (no reuse but verbose); (c) blake3-derived from (continent_channel_id, settlement_index_at_emit, delta_id) (deterministic + collision-resistant). Strategy (c) is replay-deterministic; should be specified in GEO_001 §3 alongside GeoCellId construction rule.
- **GAP-S3.F** — `SettlementByName` ambiguity policy: what if 2 canonical_settlements both named "Tương Dương" survive Scenario 1 validation (per GAP-S1.C, no uniqueness validator yet)? V1: first-match in canonical-declaration order? Reject at HookScope resolution? Decision needed → fold into GAP-S1.C fix.
- **GAP-S3.G** — `PositionRegion.radius_normalized` semantics — 0.05 of WHAT? Continent-normalized [0..1]? Cell-scale ratio? Per GEO_001 it's `radius_normalized: f32` (the field name is the spec). Probably continent-normalized. Worth a comment / example in GEO_001 §6 HookScope declaration.
- **GAP-S3.H** — Concurrent admin Forge edits (2 admins, same prev_delta_id, in flight). Optimistic locking via OrderingGate works (first wins; second rejects `geography.delta_order_violation`). UX: user re-submits with fresh prev_delta_id. ACCEPTED — this is correct V1 behavior; not a gap, but worth documenting as expected.
- **GAP-S3.I** — Reason text "Tiểu Long Nữ thành lập..." is canonical content; should it be PII-scrubbed (regex-based per §12X.L7) or LEFT INTACT (it's in-fiction, not user PII)? Tension: §12X.L7 says scrub ALL admin reasons; but in-fiction text has different sensitivity profile. Probably scrub anyway (defense in depth); a NAMED character is not PII. Worth a §12 note in GEO_001 or a deferral.

---

## §6 — Scenario 4: Snapshot fork (AC-GEO-8)

**Setup:** Parent reality R_alpha at event_id=5000 has 3 deltas [d1, d2, d3] (d3 emitted at event_id=4800). Player creates fork; child R_beta inherits up to event 5000.

**Walk-through:**

```
T0: R_alpha.geography_deltas = [d1(id=1, AddNamedSettlement),
                                 d2(id=2, RenameRegion),
                                 d3(id=3, SetBiomeOverride)].
    R_alpha.last_delta_event_id = 4800.

T1: Player triggers fork at event 5000. DP SnapshotForker (synthetic actor;
    EVT-T4 System producer) emits PER CONTINENT:
    EVT-T4 System GeographyForkInherited{
      child_reality_id: R_beta,
      parent_continent_channel_id: continent:southern_song@R_alpha,
      fork_point_event_id: 5000,
      copied_delta_count: 3,
    }

T2: For each continent in R_alpha:
    a. Create new ChannelId in R_beta's channel registry (per DP-Ch3).
    b. Initialize world_geometry row at new ChannelId with:
       - schema_version: 1 (inherited)
       - generator_pipeline_version: 1 (inherited and pinned per MED-4)
       - seed: copied from parent (bit-identical GeographySeed)
       - creative_seed: copied from parent
       - geography_deltas: copied PARTIAL — only those emitted at event_id ≤ 5000:
         R_alpha.geography_deltas where generating_event_id ≤ 5000 = [d1, d2, d3]
       - last_delta_event_id: <this GeographyForkInherited event_id in R_beta>
       - cells: REGENERATED from seed (deterministic; matches parent's cells
         exactly per AC-GEO-2 invariant). NOT copied byte-by-byte; replay-derived.
       - climate_zones / biomes / river_flux / is_coast: REGENERATED.
       - settlements: regenerated from canonical declarations + d1's added settlement.

T3: Verify: R_beta.world_geometry.cells == R_alpha.world_geometry.cells (byte-
    identical per Scenario 2 invariant). ✅
    R_beta.world_geometry.geography_deltas == [d1, d2, d3]. ✅
    R_beta.world_geometry.last_delta_event_id != R_alpha.world_geometry.last_delta_event_id
    (per-aggregate namespace per HIGH-3 fix). ✅

T4: Divergence test:
    R_beta appends d4_beta via Forge:EditGeographyDelta. R_beta.last_delta_event_id
    updated. R_alpha unaffected.
    R_alpha appends d4_alpha (different content). R_alpha.last_delta_event_id
    updated. R_beta unaffected.
    NO cross-pollination. ✅ AC-GEO-8 PASS.
```

**Observations / gaps surfaced:**

- **GAP-S4.J** — Fork mid-flight delta race: what if a Forge:EditGeographyDelta is in EVT-V validator queue at the moment SnapshotForker emits GeographyForkInherited? Three sub-cases:
  - (a) Delta validator passes before fork → fork inherits the new delta.
  - (b) Delta validator passes after fork → child does NOT inherit (event_id > fork_point); parent does.
  - (c) Delta validator fails after fork → neither inherits (delta never landed).
  Decision: per existing snapshot-fork semantic (`event_id ≤ fork_point` per `03_multiverse/03_fork_and_cascading.md` §6), cases (a)/(b)/(c) are well-defined. No bug; clarification only.
- **GAP-S4.K** — Multi-continent reality fork: if R_alpha has 3 continent channels, SnapshotForker emits 3 separate GeographyForkInherited events. Order? Parallel? Should be PARALLEL — each continent's world_geometry is independent. But ALL 3 must complete before R_beta is "ready" for play. Bootstrap orchestration: SnapshotForker emits all 3; waits for all 3 EVT-T4 to commit; then signals R_beta ready. Should specify this orchestration somewhere — currently implicit.
- **GAP-S4.L** — Delta replay vs delta copy: T2 says "regenerated from seed" but `geography_deltas` is "copied". Inconsistent semantics: cells/biomes are SCHEMA-recomputed; deltas are VALUE-copied. Replay invariant: same seed → same cells/biomes; same deltas → same delta-applied state. Therefore byte-identical world_geometry post-stage-4 + post-apply_delta. Worth a sentence in GEO_001 §9 multiverse inheritance.
- **GAP-S4.M** — `GeographyForkInherited.copied_delta_count` is a UI/audit hint, not a contract. The actual filter is `event_id ≤ fork_point`. If `copied_delta_count` is computed by SnapshotForker before scanning the delta array, it could drift. Recommend deriving from `child.geography_deltas.len()` post-fork (audit-only field).

---

## §7 — Scenario 5: LLM authoring failure paths (AC-AUTHOR-2 + 3 + 5 + 6)

**Setup:** Author Lý Minh starts new LLM-authored reality. Test 4 failure paths.

**Walk-through:**

```
T0: AuthoringSession created, producer=LlmGenerated, iteration 0.

[AC-AUTHOR-2: invalid JSON → retry succeeds]
T1: LLM call 1 → provider returns malformed JSON (trailing comma).
    Validator step 1 JSON parse fails: authoring.invalid_json.
    Retry context: error_message = "JSON parse failed: trailing comma at offset 1247".
    Retry count for iteration: 1/3.
T2: LLM call 2 with retry context appended to [HISTORY] → returns valid JSON.
    Validator passes. AuthoringSession.total_llm_calls: 0 → 2.
    ✅ AC-AUTHOR-2 PASS.

[AC-AUTHOR-3: retry cap → EditManually fallback]
T3: New iteration 2. LLM call 3 → returns CreativeSeed with 17 culture_hints.
    Validator step 3 cap fails: authoring.cap_violation { rule_id: "culture_hints_too_many" }.
    Retry 1/3.
T4: LLM call 4 with retry context "you must produce ≤16 culture_hints" → returns
    18 culture_hints (still wrong). Retry 2/3.
T5: LLM call 5 → returns 19 (worse). Retry 3/3.
T6: Retry cap exhausted: authoring.retry_cap_exceeded.
    BFF surfaces fallback UI: "LLM thử 3 lần không thành công. Hãy chỉnh sửa
    thủ công." with [Edit Manually] [Cancel] buttons.
T7: Author chooses EditManually. UI loads the latest LLM output (19 cultures
    pre-populated in form). Author trims to 16 manually + Accepts.
    AuthoringMetadata.producer: changed to Hybrid{primary: LlmGenerated, author_edits_applied: 1}.
    AuthoringSession.total_llm_calls: 5; total_llm_cost_usd: 0.60.
    ✅ AC-AUTHOR-3 PASS.

[AC-AUTHOR-5: cost cap]
T8: Different scenario, fresh session. Cost cap S6-D2 paid tier: $5.00 per session.
    Iterations 1-7 accumulate cost: 0.50 + 0.80 + 0.65 + 0.70 + 0.85 + 0.95 + 0.56 = $5.01.
    BFF cost-cap gate fires BEFORE LLM call 8: total_llm_cost_usd > cap.
    AuthoringSession.state: InProgress → CostCapped.
    UI: "Đã đạt giới hạn chi phí cho phiên này. Hãy chấp nhận bản thảo hiện
         tại hoặc nâng cấp gói." with [Accept Current Draft] [Upgrade Plan] [Cancel].
    Author cannot iterate further this session.
    Reject rule: authoring.cost_cap_exceeded.
    ✅ AC-AUTHOR-5 PASS.

[AC-AUTHOR-6: iteration cap]
T9: Different scenario, fresh session. Iteration cap V1: N=10.
    Author runs 10 iterations (each Accepts → RejectAndRetry, never finalizing).
    iteration_count: 10. Author submits 11th feedback.
    BFF iteration-cap gate fires BEFORE LLM call 11:
    Reject: authoring.iteration_cap_exceeded.
    UI: "Đã đạt giới hạn 10 lần lặp. Hãy chấp nhận bản thảo hiện tại hoặc
         bắt đầu lại." with [Accept] [Restart].
    ✅ AC-AUTHOR-6 PASS.
```

**Observations / gaps surfaced:**

- **GAP-S5.N** — Retry prompt structure: at T2, retry call includes "error_message" in [HISTORY]. WHICH section? [HISTORY] is meant for previous iterations, not error context. Better: dedicated [RETRY_CONTEXT] meta-section inside [INSTRUCTION] OR appended to [SYSTEM]. S9 §12Y.L3 8-section structure should clarify retry semantics. Currently ambiguous.
- **GAP-S5.O** — EditManually UI state: T7 says "UI loads the latest LLM output (19 cultures pre-populated in form)". But the latest LLM output FAILED validation. Form must show validation errors inline + let author fix. This is form UX design, not GEO_001b scope, but should be flagged.
- **GAP-S5.P** — Hybrid producer counter granularity: T7 sets `author_edits_applied: 1` for the whole session, not per-field. Per GEO-AUTHOR-Q5, V1 is per-session counter (chosen for simplicity). V1+ per-field log if audit need surfaces. Spec is clear; not a gap.
- **GAP-S5.Q** — Cost cap pre-check vs post-deduct: T8 fires BEFORE call 8 — based on accumulated cost from prior calls. But the cost of call 8 is unknown until provider responds. So the gate is "if current_total > cap, don't make next call". This means a single big call CAN exceed the cap. Should specify: pre-call gate checks total + predicted call cost (per S6-D4 cost prediction V1+30d). Currently underspecified.
- **GAP-S5.R** — Iteration cap fires PRE-call (T9 says "before LLM call 11"). But what about iteration 10 producing a valid draft author wants to Accept? T9 implies that's fine (Accept doesn't trigger LLM call; just transitions state). Worth a sentence in §7.

---

## §8 — Scenario 6: Producer alternatives (AC-AUTHOR-4 + 9 + 10)

**Setup:** Test the 4 V1-active non-LLM producers (well, 3: Manual + legacy-None + KnowledgeService-fallback-to-LLM-None).

**Walk-through:**

```
[AC-AUTHOR-4: Manual form authoring]
T0: Author opens "New Reality" UI → chooses AuthoringProducer::AuthorManual.
T1: UI renders 12-field form (form_version=1):
    - archetype dropdown (12 options)
    - world_scale dropdown (5 options)
    - hemisphere_orientation dropdown (3 options)
    - coastline_profile dropdown (5 options)
    - climate_bias dropdown (8 ClimateZone variants + "Balanced")
    - culture_hints dynamic-add (each: hearth_position {x,y sliders} OR
      hearth_preference SpatialPreference picker; naming_style_ref combobox;
      value_tags multi-select)
    - canonical_settlements dynamic-add (each: name LocalizedName; position OR
      spatial_preference; role dropdown; population_tier slider 0..6; canon_ref
      optional)
    - canonical_provinces (V1+ stage 5; V1 shown but read-only-empty)
    - lore_hooks_per_region dynamic-add (each: HookScope picker; content
      I18nBundle editor)
    - naming_styles file upload (Markov corpus file per culture)

T2: Author fills:
    - archetype: Wuxia, world_scale: Region, hemisphere: Northern, coastline: Coastal
    - 2 culture_hints (han_jiangnan + mongol_steppe) with mix of ExplicitPosition
      (for han_jiangnan author knows is on (0.3, 0.4) per canonical book map)
      + NearClimate(Boreal) (for mongol_steppe, no exact position needed)
    - 8 canonical_settlements: 5 with ExplicitPosition (canonical Nam Tống book
      positions) + 3 with SpatialPreference::NearBiome(Plain)

T3: Author submits form → client-side validation → server-side validation per §8
    (schema validation + cap validation + content safety). All pass.
    AuthoringMetadata: {
      producer: AuthorManual{ui_form_version: 1},
      total_llm_cost_usd: 0.00, total_llm_calls: 0,
      iteration_count: 1, ...
    }
    No LLM was called; cost = $0.
    Bootstrap proceeds normally. ✅ AC-AUTHOR-4 PASS.

[AC-AUTHOR-9: Legacy reality (pre-GEO_001b authoring_metadata=None)]
T4: A pre-GEO_001b reality R_legacy was bootstrapped before GEO_001b shipped.
    Its RealityManifest carries `authoring_metadata: None`.
T5: Player loads R_legacy. Bootstrap re-replay (e.g., projection rebuild per
    R2 mitigation) proceeds normally:
    - GeographyBorn payload deserializes with authoring_metadata field absent
      (per I14 additive — old serialized data is forward-compatible)
    - Treated as None; world-service generator runs identically
    - No validator complaint (Option<AuthoringMetadata> being None is valid)
    - audit UI shows "Authoring metadata: not captured (pre-2026-05-13)"
    ✅ AC-AUTHOR-9 PASS.

[AC-AUTHOR-10: KnowledgeService unavailable V1 → fallback to LlmGenerated{grounding: None}]
T6: Author chooses AuthoringProducer::KnowledgeServiceExtracted{
      book_id: "than_dieu_dai_hiep",
      extraction_template_ref: PromptTemplateRef("world_authoring_grounded/v1"),  // V1+
    }
T7: BFF calls knowledge-service /v1/books/than_dieu_dai_hiep/entities?... →
    knowledge-service returns 503 Unavailable (not yet shipped V1) OR connection
    timeout (5s budget per S11).
T8: BFF receives unavailable signal. V1 BEHAVIOR (per AC-AUTHOR-10):
    - Emit warning toast to author: "Knowledge service unavailable; falling
      back to ungrounded LLM authoring. World will use general wuxia knowledge."
    - AuthoringSession.producer is REWRITTEN: KnowledgeServiceExtracted → LlmGenerated{
        template_ref: "world_authoring/v1",  // ungrounded template
        knowledge_grounding: None,
      }
    - Iteration 0 proceeds with the LlmGenerated path per Scenario 1.
    V1+ when knowledge-service ships: gate flips and KnowledgeServiceExtracted
    is V1+ active. Reject rule_id authoring.knowledge_service_unavailable
    becomes V1+ active.
    ✅ AC-AUTHOR-10 PASS (V1 fallback behavior).
```

**Observations / gaps surfaced:**

- **GAP-S6.S** — Manual form UI version bump policy: T1 form_version=1. If form gains new fields V1+ (e.g., culture_hints.value_tags becomes a closed enum), bump to form_version=2. Old AuthoringMetadata records persist `ui_form_version: 1`. This is correct I14 additive. Worth a note.
- **GAP-S6.T** — Hybrid producer for Manual form: T3 doesn't trigger Hybrid (no LLM was called). But if author later uses Forge:EditGeographyDelta to post-bootstrap modify the world, does that count as "Hybrid"? NO — Forge edits are post-bootstrap deltas, not pre-bootstrap authoring. The producer field reflects pre-bootstrap creation method; delta-overlay is orthogonal. Worth clarifying in §3 / §9.
- **GAP-S6.U** — Producer rewrite on fallback (T8): rewriting `producer` from `KnowledgeServiceExtracted{...}` to `LlmGenerated{...}` loses the author's intent ("I wanted grounding"). Should AuthoringMetadata record BOTH? E.g., `producer: LlmGenerated{...}, intended_producer: Some(KnowledgeServiceExtracted{...})`. Then audit shows "author requested knowledge-service grounding; service unavailable; fell back". V1+ when service ships. Trade-off: schema bloat vs audit fidelity. Recommend adding `intended_producer: Option<AuthoringProducer>` V1+30d.
- **GAP-S6.V** — Knowledge-service unavailable detection: T7 says "503 OR connection timeout (5s budget per S11)". The exact health check + timeout policy is in S11 §12AA but not cross-referenced in GEO_001b §6. Worth a §6 cross-ref.
- **GAP-S6.W** — AC-AUTHOR-10 says "emits warning to author". UX: blocking modal? Inline banner? Toast? Form UX concern; specify in V1 implementation phase.

---

## §9 — Design observations summary

**21 acceptance scenarios walked. 23 design gaps surfaced.** Categorized:

| Category | Count | Severity | Recommended action |
|---|---:|---|---|
| **Schema bugs** (HIGH — schema-correctness issues) | 3 | — | GAP-S1.C uniqueness + GAP-S1.D cycle detect + GAP-S3.E SettlementId strategy: fold into GEO_001b §11 schema_version 1→2 migration; activate at LOCK |
| **Implementation discipline** (MED — CI gate needed to enforce contract) | 5 | — | GAP-S2.A HashMap normalize / GAP-S2.B float determinism / GAP-S2.C canonical JSON / GAP-S2.D cross-platform / GAP-S3.E SettlementId blake3-derive — all CI gates in V1 implementation phase |
| **Underspecified semantics** (MED — contract clear in spirit, ambiguous in letter) | 7 | — | GAP-S1.A schemars build pipeline / GAP-S3.G PositionRegion radius units / GAP-S4.K multi-continent orchestration / GAP-S4.L replay-vs-copy / GAP-S5.N retry section / GAP-S5.Q cost cap pre/post / GAP-S6.U intended_producer — clarification edits in next cycle |
| **UX-layer concerns** (LOW — UX implementation, not GEO_001/b scope) | 4 | — | GAP-S5.O EditManually form / GAP-S6.S form version / GAP-S6.W toast vs modal — V1 implementation phase UX spec |
| **Tension / non-bug clarifications** (LOW) | 4 | — | GAP-S3.H concurrent edit / GAP-S3.I in-fiction PII / GAP-S4.M copied_delta_count / GAP-S6.T post-bootstrap Hybrid — doc clarifications |

### 4 most critical pre-implementation-phase tasks

1. **CreativeSeed JSON Schema build pipeline** (GAP-S1.A): set up `cargo build` step to run `schemars` against `CreativeSeed` Rust struct → emit `contracts/schemas/creative_seed.v2.schema.json`; commit alongside code; CI gate snapshot test that hashes match. Without this, schema-constrained generation cannot be implemented.
2. **Canonical JSON serialization** (GAP-S2.C): adopt RFC 8785 JCS (or equivalent canonical_json crate) for `creative_seed_hash` computation. Must be specified BEFORE first reality is bootstrapped (changes the hash; can't change later without invalidating fixture hashes).
3. **SettlementId strategy** (GAP-S3.E): pick blake3-derived (replay-deterministic) over sequential. Specify in GEO_001 §3 alongside GeoCellId construction. Update schema accordingly.
4. **HashMap normalization CI gate** (GAP-S2.A): byte-hash snapshot test of materialized world_geometry against fixture per (master_seed, creative_seed_hash). Fails on any non-determinism (HashMap iteration, float drift, etc.). CI runs every build.

### 5 sub-decisions needing user approval before V1 implementation phase

- **D-S04-1** (GAP-S1.C): canonical_settlements + culture_hints name uniqueness — V1 reject duplicates OR V1 allow + first-match in resolution? Recommend reject (cleaner; LLM-friendly via prompt instruction). Adds reject `authoring.duplicate_canonical_name`.
- **D-S04-2** (GAP-S1.D): SpatialPreference::NearSettlement(name) cycle detection — reject at validation OR break cycle deterministically? Recommend reject (clearer; LLM can be re-prompted). Adds reject `authoring.spatial_preference_cycle`.
- **D-S04-3** (GAP-S2.B): floating-point determinism strategy — strict IEEE compile flag OR fixed-point representation? Recommend strict IEEE V1 (cheaper); fixed-point V1+ if drift surfaces.
- **D-S04-4** (GAP-S3.I): admin Forge reason PII scrubbing for in-fiction text — scrub regardless (defense in depth) OR allow named characters? Recommend scrub regardless (matches existing §12X.L7 admin discipline).
- **D-S04-5** (GAP-S6.U): record `intended_producer` separately when fallback fires? Recommend V1+30d (low-priority audit improvement; not blocking V1 launch).

---

## §10 — Open questions surfaced

| ID | Question | Resolution path |
|---|---|---|
| **SPIKE-04-Q1** | Should the spike walk an actual `world_authoring/v1.tmpl` text out, or is the §3 walk-through abstraction sufficient? | Defer to V1 implementation phase — actual template text lives in `contracts/prompt/templates/` per S9 governance. |
| **SPIKE-04-Q2** | Should §6 fork scenario validate cross-continent ordering (3-continent reality)? | Single-continent scenario sufficient V1 (SPIKE_01 + GEO §14.3 also single-continent). V2+ multi-continent test when GEO-D11 activates. |
| **SPIKE-04-Q3** | Should §5 cost-cap scenario walk per-iteration cost prediction (V1+30d per GEO-AUTHOR-D4)? | Defer to GEO-AUTHOR-D4 design when V1+30d cost prediction lands. |
| **SPIKE-04-Q4** | What's the equivalent test for `KnowledgeServiceExtracted` producer ONCE knowledge-service ships? | Defer to GEO-AUTHOR-D1 activation when knowledge-service V1+ ships; reopen this spike OR create SPIKE_NN. |
| **SPIKE-04-Q5** | What if cohort sentence "ChannelTier::Continent" doesn't exist in MAP-2 enum? Was it actually added? | Verify — read MAP_001 §3 and confirm ChannelTier::Continent is locked V1. If not, file as MED-level fix to MAP_001. (Pre-checked: it IS — MAP_001 §3 ChannelTier enum has 5 V1 variants Continent / Country / District / Town / Cell per cat_00_MAP_map_foundation.md.) |

---

## §11 — Graduation path

### Outputs of this spike

| Output | Disposition |
|---|---|
| **§9 4 critical pre-implementation tasks** | Folded into V1 implementation-phase plan; tracked as Deferred Items in SESSION_HANDOFF (next cycle) |
| **§9 5 sub-decisions (D-S04-1..5)** | User-approval batch in NEXT design cycle; folds into GEO_001 + GEO_001b minor revision OR explicit decisions log entry |
| **§9 23 design gaps GAP-S1..S6.* tagged** | Categorized by severity; HIGH/MED schema bugs fold into another GEO fix cycle; LOW/clarifications fold into doc maintenance |
| **§10 5 open questions SPIKE-04-Q1..5** | Tracked as deferrals; some defer to V1+30d, V1+ knowledge-service activation, etc. |
| **AC-GEO-1..11 + AC-AUTHOR-1..10 walked end-to-end** | ✅ 21/21 validated as REACHABLE; no blocking unsatisfiable scenarios |

### What graduates where

- **HIGH/MED schema gaps** (D-S04-1 + D-S04-2 + GAP-S3.E + GAP-S2.A..D): user-approval cycle → fold into a GEO_001 / GEO_001b minor revision (additive per I14) + CI gate setup task list for V1 implementation phase.
- **No new aggregate** introduced by spike. No new namespace. No boundary lock claim needed.
- **No new feature file** beyond this spike. AC-GEO-1..11 + AC-AUTHOR-1..10 stay as-is in GEO_001 / GEO_001b (verified-walked); GEO_001 / GEO_001b LOCK gating remains unchanged.
- **This spike stays in `_spikes/`** as permanent reference per `_spikes/_index.md` graduation policy.

### V1 implementation-phase work this spike enables

The spike's MAIN deliverable: a concrete handoff to V1 implementation phase. Implementer reads spike → understands the 6 operational sequences (LLM bootstrap / replay / admin canonization / fork / failure paths / producer alternatives) → builds:

1. `world-service/geography-generator` Rust module (Voronoi + heightmap + climate + biome + erosion + canonical-pinning)
2. `api-gateway-bff/authoring-session` state + form UI
3. `chat-service` `world_authoring/v1.tmpl` template registration + schema-constrained generation wiring
4. `contracts/schemas/creative_seed.v2.schema.json` build pipeline + CI gate
5. CI snapshot tests against fixture: byte-hash world_geometry per (master_seed, creative_seed_hash)
6. S6 user_cost_ledger integration for per-iteration cost accumulation
7. Forge:EditGeographyDelta admin endpoint + 5-step validator pipeline
8. SnapshotForker EVT-T4 GeographyForkInherited emission per continent

### Next priority candidates

- **V1 implementation phase** (per V1 implementation-phase work above) — biggest payoff
- **User-approval batch for D-S04-1..5** — small (5 decisions, 1 cycle)
- **GEO_001 / GEO_001b minor revision** folding spike findings — clarifications + 2 new reject rule_ids
- **SPIKE_05 V1+ knowledge-service activation walk-through** — when knowledge-service ships

---

## §12 — Cross-references

- [GEO_001 World Geometry](../00_geography/GEO_001_world_geometry.md) — schema being validated (read-side + materialized data)
- [GEO_001b CreativeSeed Authoring Flow](../00_geography/GEO_001b_authoring_flow.md) — schema being validated (write-side)
- [SPIKE_01](SPIKE_01_two_sessions_reality_time.md) — fixture inspiration (Thần Điêu Đại Hiệp Nam Tống setting; canonical_settlements Tương Dương + Khai Phong + Yên Vũ Lâu)
- [SPIKE_02](SPIKE_02_reference_games_gap_analysis.md) — sibling reference (cross-cat gap analysis; pre-V1)
- [SPIKE_03](SPIKE_03_tilemap_world_view.md) — sibling reference (HOMM3-style camera-rendered visual layer; complementary to GEO procgen)
- [03_multiverse/01_four_layer_canon.md](../../03_multiverse/01_four_layer_canon.md) — L1/L2/L3 cascade context for fork semantics in §6
- [03_multiverse/03_fork_and_cascading.md](../../03_multiverse/03_fork_and_cascading.md) — MV6 snapshot-fork semantics validated in §6
- [02_storage/S06_llm_cost_controls.md](../../02_storage/S06_llm_cost_controls.md) — cost cap pattern validated in §7 AC-AUTHOR-5
- [02_storage/S09_prompt_assembly.md](../../02_storage/S09_prompt_assembly.md) — template + schema-constrained generation discipline applied throughout
- [02_storage/S11_service_to_service_auth.md](../../02_storage/S11_service_to_service_auth.md) — knowledge-service availability detection §8 AC-AUTHOR-10
- World-map landscape survey 2026-05-13 (research report; Patel + O'Leary + Azgaar baseline) — algorithmic foundation underlying §3 Scenario 1 pipeline walk-through
