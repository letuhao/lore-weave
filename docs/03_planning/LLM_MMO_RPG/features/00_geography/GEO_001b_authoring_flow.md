# GEO_001b — CreativeSeed Authoring Flow

> **Conversational name:** "Authoring Flow" (AUTHOR — sibling of GEO_001 World Geometry). The write-side contract for CreativeSeed production. Specifies HOW the `CreativeSeed` value that GEO_001 consumes gets produced — LLM via S9-registered prompt template, manual form, third-party import, knowledge-service extraction, or hybrid. Schema-constrained generation REQUIRED; multi-turn iteration loop; validation + bounded retry; cost cap per S6; LLM-friendly `SpatialPreference` enum replacing raw `(f32, f32)` for V1+.
>
> **Category:** GEO — Geography Foundation (same as GEO_001; this is the write-side sibling per two-file split precedent PL_001 + PL_001b / WA_002 + WA_002b)
> **Status:** **DRAFT 2026-05-13** (single-cycle write-side discussion → design)
> **Catalog refs:** [`cat_00_GEO_geography_foundation.md`](../../catalog/cat_00_GEO_geography_foundation.md) — owns `GEO-*` namespace (this file: `GEO-AUTHOR-*` sub-prefix)
> **Builds on:** [GEO_001](GEO_001_world_geometry.md) (consumer of CreativeSeed) · [02_storage S6](../../02_storage/S06_llm_cost_controls.md) (cost cap pattern; `user_cost_ledger` table) · [02_storage S9](../../02_storage/S09_prompt_assembly.md) (prompt-assembly template registry + governance) · [02_storage S8](../../02_storage/S08_audit_pii_retention.md) (PII scrubbing in author intent prompts) · [05_llm_safety](../../05_llm_safety/) (intent classifier + injection defense for author intent text) · [CLAUDE.md two-layer pattern](../../../../CLAUDE.md) (knowledge-service planned per `101_DATA_RE_ENGINEERING_PLAN.md`)
> **Resolves:** Write-side contract gap surfaced 2026-05-13 deep-discussion (GEO_001 defined only the post-pipeline READ contract for prompt-assembly grounding; the LLM-produces-CreativeSeed write path was hand-waved with several gaps) · LLM-vs-procgen role split clarification (geometry stays in procgen; semantic creative direction stays in LLM; SpatialPreference enum replaces raw coordinates) · Producer abstraction (LLM is one producer; manual form / import / knowledge-extracted are also first-class V1 producers — no LLM dependency for V1 single-cell SPIKE_01 realities)
> **Defers to:** future **GEO_002 V1+30d** Political Layer Generator (consumes locked CreativeSeed; not part of write-side) · future **knowledge-service V1+** activation (planned per CLAUDE.md; V1 schema-reserves `KnowledgeServiceExtracted` producer; activates when knowledge-service ships) · future **MAP_002 V2+** asset pipeline (LlmGenerated image rendering of materialized world; orthogonal to authoring write-side)

---

## §1 Why this exists

GEO_001 §6 said "LLM produces the CreativeSeed value at world-creation time as structured creative direction" and stopped there. The deep-discussion pass 2026-05-13 surfaced that this leaves the actual write-side contract undefined:

**Gap 1 — LLM prompt template is implicit.** S9 §12Y mandates that every LLM call goes through a registered template at `contracts/prompt/templates/<intent>/v<N>.tmpl`. World authoring is an LLM intent. We didn't register one. Without it, world authoring violates the S9 governance invariant (every LLM call is template-routed).

**Gap 2 — Schema-constrained generation isn't mandated.** CreativeSeed has 12 fields with closed-enum constraints (12 WorldArchetype variants, 5 WorldScale variants, etc.) + length caps (culture_hints ≤ 16) + range constraints (positions ∈ [0, 1]). Without JSON-Schema-constrained generation (OpenAI structured outputs / vLLM grammar mode / equivalent), the LLM produces invalid output and we burn cycles on retry. V1 LLM calls MUST use schema-constrained generation.

**Gap 3 — Position fields ask the LLM to do geometry — its known weakness.** `culture_hints[].hearth_position_normalized: (f32, f32)` and `canonical_settlements[].position_normalized: (f32, f32)` ask the LLM for spatial coordinates. The 2026-05-13 survey identified geometric reasoning as a fundamental LLM weakness. We should let the LLM produce *named spatial intent* (Northern/Coastal/Highland/NearBiome/NearCulture) and let procgen do the actual placement. SpatialPreference enum is V1+ (additive per I14) per §11 below.

**Gap 4 — Multi-turn authoring iteration is undocumented.** A realistic flow has author intent → LLM proposes → author edits → LLM regenerates → author approves. Cost per S6 must accumulate; retry-on-invalid must bound; author-edit fallback must always work. None of this exists in GEO_001.

**Gap 5 — knowledge-service grounding is missing.** For canon-faithful authoring of "Thần Điêu Đại Hiệp" the LLM should consume canonical entities from the ingested book via knowledge-service, not invent them. V1 schema-reserves; V1+ activates when knowledge-service ships.

**Gap 6 — Non-LLM authoring isn't first-class.** Manual form authoring (no LLM) + third-party import (Azgaar JSON / Wonderdraft / etc.) + knowledge-service extraction should be first-class producers, not afterthoughts. V1 must support manual form even if LLM-authored is the default.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **AuthoringProducer** | Closed enum 5 variants (§4) describing how a specific CreativeSeed was produced | Stored as `authoring_metadata.producer` on RealityManifest extension; immutable post-bootstrap; replay-grade audit. |
| **AuthoringMetadata** | Struct (producer + cost + iteration count + author + timestamps) | Attached to RealityManifest as OPTIONAL field; absence implies legacy / no metadata captured. |
| **LlmAuthoringTemplate** | S9-registered prompt template at `contracts/prompt/templates/world_authoring/v<N>.tmpl` | V1 template version 1; bumps trigger CI fixture update per S9 governance §12Y.L9. |
| **AuthoringSession** | BFF-held UX state (NOT an aggregate; not event-sourced) | Held in api-gateway-bff during pre-bootstrap iteration; ephemeral. Cost is the durable concern (logged via S6 `user_cost_ledger`); content is BFF-only. |
| **AuthoringIteration** | One author-LLM turn within an AuthoringSession | Bounded N=10 V1 (iteration_count_max); exceeding rejects `authoring.iteration_cap_exceeded`. |
| **SpatialPreference** | Closed enum 14 variants (§4) replacing `(f32, f32)` for LLM-friendly spatial intent | V1+ additive per I14; CreativeSeed.schema_version 1→2 when GEO_001b LOCKs. V1=1 keeps `position_normalized` required; V1+=2 adds optional `spatial_preference` (at-least-one-Some validator). |
| **KnowledgeGrounding** | Struct (book_id + scope + max_entities) | V1 schema-reserved; activation V1+ when knowledge-service ships per CLAUDE.md two-layer plan. |
| **ProducerOutput** | Enum (LlmJson / ImportedManifest / ManualForm / ValidationError) | Carried in iteration log; LLM output specifically wraps a parsed-and-validated CreativeSeed candidate. |
| **AuthorAction** | Enum (Accept / RejectAndRetry / EditManually / Cancel) | Closes each iteration; Accept proceeds to bootstrap; RejectAndRetry triggers new LLM call; EditManually overrides LLM output. |
| **ValidationResult** | Enum (Valid / Invalid with Vec<RejectReason>) | Schema validator outcome per iteration; feeds retry-vs-author-fallback decision. |

---

## §2.5 Event-model mapping (per 07_event_model Option C taxonomy)

GEO_001b introduces no new EVT-T* category. AuthoringSession is BFF-held (no events during iteration); only the FINAL accepted CreativeSeed lands as part of EVT-T4 GeographyBorn (defined in GEO_001 §2.5) which now carries `authoring_metadata` in its payload.

| Authoring event | EVT-T* | Sub-type / payload | Producer | Notes |
|---|---|---|---|---|
| Author intent → BFF authoring session | (none — BFF-held UX) | — | api-gateway-bff | No DP event V1; authoring is pre-bootstrap UX state. |
| Per-iteration LLM call cost | (S6 cost ledger) | `user_cost_ledger` row per S6-D6 | usage-billing-service | Each LLM call appends to S6 `user_cost_ledger`; total cost summed into AuthoringMetadata.total_llm_cost_usd at bootstrap. |
| Final CreativeSeed → reality bootstrap | **EVT-T4 System** | `GeographyBorn { ..., authoring_metadata: Option<AuthoringMetadata> }` | DP-Internal RealityBootstrapper | GEO_001 §2.5 EVT-T4 row payload **extended** with `authoring_metadata` field (additive per I14). |
| LLM-extension of CreativeSeed post-bootstrap (V1+ via GEO-D12) | **EVT-T6 Proposal** | `GEO:CreativeSeedExtension` (V1+ reservation per GEO_001 §2.5) | future LLM CreativeSeed-extender Generator | V1+ when knowledge-service ships + Forge admin reviews. |
| Forge admin approves/rejects LLM extension proposal V1+ | **EVT-T8 Administrative** | `Forge:AcceptCreativeSeedExtension` / `Forge:RejectCreativeSeedExtension` (V1+ reservation) | WA_003 Forge | V1+ reservation; not active V1. |

**Key design choice:** AuthoringSession iterations are BFF-held UX state, not event-sourced. Rationale: pre-bootstrap (no reality exists yet), iterations are exploratory + cheap to replay, and per-iteration LLM cost is already captured in S6 `user_cost_ledger` (the audit trail that matters). Event-sourcing each iteration would balloon storage with rejected drafts. The ONLY durable record is the final accepted CreativeSeed embedded in GeographyBorn.

---

## §3 Aggregate inventory (no new aggregate)

**No new aggregate.** Authoring is pre-bootstrap UX state held in `api-gateway-bff`. The state shape (informational):

```rust
// BFF-held; NOT an aggregate; NOT persisted to per-reality DB; ephemeral
pub struct AuthoringSession {
    pub session_id: AuthoringSessionId,             // BFF-generated; not a DP SessionId
    pub author_user_id: UserId,                      // from auth-service JWT
    pub intent: I18nBundle,                          // initial author prompt
    pub producer: AuthoringProducer,
    pub iterations: Vec<AuthoringIteration>,         // bounded N=10 V1
    pub current_draft: Option<CreativeSeed>,         // latest valid candidate (None until first valid output)
    pub total_llm_cost_usd: Decimal,                 // mirrors S6 user_cost_ledger sum
    pub total_llm_calls: u32,
    pub state: AuthoringState,                       // InProgress | Accepted | Cancelled | CostCapped
    pub created_at: WallClock,
    pub last_activity_at: WallClock,
}

pub enum AuthoringState { InProgress, Accepted, Cancelled, CostCapped }
```

**Durable record on bootstrap** — embedded in RealityManifest + GeographyBorn payload:

```rust
pub struct AuthoringMetadata {                       // OPTIONAL on RealityManifest; carried into GeographyBorn payload
    pub producer: AuthoringProducer,
    pub total_llm_cost_usd: Decimal,                 // 0 for non-LLM producers
    pub total_llm_calls: u32,                        // 0 for non-LLM producers
    pub iteration_count: u32,                        // how many author-feedback turns
    pub author_user_id: UserId,
    pub authoring_template_version: Option<u32>,     // S9 template version used (Some for LLM producer)
    pub knowledge_grounding_book_id: Option<BookId>, // V1+ when knowledge-service ships
    pub authoring_started_at: WallClock,
    pub authoring_completed_at: WallClock,
}
```

---

## §4 Closed enums

### 4.1 AuthoringProducer (5 V1)

```rust
pub enum AuthoringProducer {
    LlmGenerated {
        template_ref: PromptTemplateRef,            // S9-registered template at contracts/prompt/templates/world_authoring/v<N>.tmpl
        knowledge_grounding: Option<KnowledgeGrounding>, // V1: always None (knowledge-service planned per CLAUDE.md)
    },
    AuthorManual {
        ui_form_version: u32,                       // V1 form V1=1; bumps when form fields evolve per I14 additive
    },
    Imported {
        source_format: ImportFormat,                // V1 schema-reserved variants; activation V1+
        source_ref: String,                          // opaque (filename / URL / paste hash)
    },
    KnowledgeServiceExtracted {                     // V1 schema-reserved; activation V1+ when knowledge-service ships
        book_id: BookId,
        extraction_template_ref: PromptTemplateRef,
    },
    Hybrid {                                        // any producer + author manual edits applied
        primary: Box<AuthoringProducer>,
        author_edits_applied: u32,                  // count of post-LLM manual field edits
    },
}

pub enum ImportFormat {                             // closed enum 4 V1 schema-reserved
    AzgaarFmgJson,                                  // V1+ via Azgaar Fantasy Map Generator (MIT) per algorithmic baseline
    WonderdraftJson,                                // V1+
    LoreWeaveManifest,                              // V1+ — export/import between LoreWeave realities
    Custom,                                         // V1+ — author-defined JSON; manual validator
}
```

### 4.2 SpatialPreference (14 V1+ — closed; CreativeSeed.schema_version 2 introduces this)

```rust
pub enum SpatialPreference {                        // procgen-friendly named spatial intents; replaces raw (f32, f32) for LLM authoring
    // Hemisphere
    Northern, Southern, Equatorial,
    // Coastal vs inland
    Coastal, Inland, Insular,
    // Elevation
    Highland, Lowland, RiverValley,
    // Climate-conditioned (lazy reference; resolved at stage 6 placement)
    NearBiome(BiomeKind),                            // e.g., NearBiome(Forest)
    NearClimate(ClimateZone),                        // e.g., NearClimate(Subtropical)
    NearCulture(CultureTag),                         // e.g., NearCulture("han_jiangnan")
    // Distance to anchor (refers to another canonical_settlement by name)
    NearSettlement(LocalizedName),
    FarFromSettlement(LocalizedName),
    // Escape hatch for canon-faithful authoring (e.g., Tang dynasty map with explicit Tương Dương coordinates)
    ExplicitPosition { x: f32, y: f32 },             // 0.0..=1.0; bypass LLM weakness when author has exact canonical position
    // Default
    Any,                                             // procgen picks freely
}
```

### 4.3 AuthorAction (4 V1)

```rust
pub enum AuthorAction {
    Accept,                                          // commit current draft → trigger bootstrap
    RejectAndRetry { feedback: I18nBundle },         // ask LLM to regenerate with feedback
    EditManually { edits: CreativeSeedPatch },       // author directly modifies CreativeSeed fields
    Cancel,                                          // abandon authoring session; no bootstrap
}
```

### 4.4 ValidationResult (2 V1)

```rust
pub enum ValidationResult { Valid, Invalid(Vec<RejectReason>) }
```

### 4.5 GroundingScope (V1+ schema-reserved)

```rust
pub enum GroundingScope {                            // V1+ when knowledge-service ships; controls how much of a book gets pulled into LLM context
    FullBook, ChapterRange { start: u32, end: u32 }, Glossary, LocationsOnly, CulturesOnly,
}

pub struct KnowledgeGrounding {
    pub book_id: BookId,
    pub scope: GroundingScope,
    pub max_entities: u16,                           // V1+ cap: 200 entities pulled into template hydration
    pub include_lore_hooks: bool,
}
```

---

## §5 LLM authoring contract (S9 template + schema-constrained generation)

### 5.1 Template registration

Per S9 §12Y.L2 versioned template registry: a new template is registered at `contracts/prompt/templates/world_authoring/v1.tmpl` + `.meta.yaml` + `fixtures/`. Template intent: `world_authoring`. Owner: GEO_001b.

### 5.2 8-section structure (per S9 §12Y.L3)

```
[SYSTEM]            "Produce a CreativeSeed JSON value conforming to schema {schema_url}.
                     Use SpatialPreference enum, not raw coordinates. Do not invent
                     entities outside the WORLD_CANON section. Honor culture_hints.len ≤ 16
                     and canonical_settlements.len ≤ 50 caps. ..."
[WORLD_CANON]       (V1+ knowledge-service grounding) book glossary entities — cultures,
                    locations, characters — pulled per KnowledgeGrounding.scope. V1: empty.
[SESSION_STATE]     empty (no reality exists yet; pre-bootstrap)
[ACTOR_CONTEXT]     author profile: prior authored realities, preferred archetypes, language
                    (for I18nBundle defaults). PII-scrubbed per §12X.L7 belt-and-suspenders.
[MEMORY]            empty (no NPC memory yet)
[HISTORY]           previous AuthoringIteration turns: author intent + LLM output + author
                    feedback. Bounded to last 5 turns to keep prompt tractable.
[INSTRUCTION]       "Produce a single JSON object conforming to CreativeSeed schema. Use
                    schema_version=2 (introduces SpatialPreference). Bind all
                    canonical_settlements to either an ExplicitPosition (if the source book
                    has canonical coordinates) or a SpatialPreference (otherwise — let
                    procgen place)."
[INPUT]             <user_input>{author_intent}</user_input>   (XML-escaped + delimiter-wrapped
                    per §12Y.L5 injection defense)
```

### 5.3 Schema-constrained generation REQUIRED

LLM call MUST use schema-constrained generation:

- **OpenAI / Azure OpenAI:** `response_format = { type: "json_schema", json_schema: { schema: <CreativeSeed JSON Schema>, strict: true } }`
- **vLLM / local:** GBNF / outlines grammar mode constraining to CreativeSeed schema
- **Anthropic:** structured output via tool-use binding (`tools = [{ name: "produce_creative_seed", input_schema: <CreativeSeed JSON Schema> }]`)

Provider-specific implementations live in chat-service per CLAUDE.md provider-gateway invariant. Templates declare the contract; chat-service implements per provider. The CreativeSeed JSON Schema is generated from the Rust struct at build time (via `schemars` crate or equivalent) and committed under `contracts/schemas/creative_seed.v2.schema.json` — bumped only on additive evolution per I14.

### 5.4 Token budget per S9 §12Y.L6

Per-intent budget caps (declared in template `.meta.yaml`):

| Section | Budget |
|---|---|
| `[SYSTEM]` | 1500 tokens (template-defined; immutable per request) |
| `[WORLD_CANON]` | 6000 tokens (V1+ knowledge-service-grounded; V1 = 0) |
| `[ACTOR_CONTEXT]` | 500 tokens |
| `[HISTORY]` | 4000 tokens (last 5 iterations) |
| `[INSTRUCTION]` | 1500 tokens |
| `[INPUT]` | 500 tokens (author intent) |
| **Total prompt** | ≤ 14000 tokens |
| **Output (response)** | ≤ 4000 tokens (CreativeSeed JSON typically 1000-3000 tokens depending on canonical_settlements count) |

Over-budget = hard error per S9 §12Y.L6 (NOT silent truncation — would drop canonical_settlements unpredictably).

---

## §6 knowledge-service grounding contract (V1 schema-reserved; V1+ activation)

When `KnowledgeServiceExtracted` producer is selected (V1+):

1. Author selects book_id (e.g., book of Thần Điêu Đại Hiệp ingested per CLAUDE.md two-layer pattern).
2. BFF calls knowledge-service: `GET /v1/books/{book_id}/entities?scope=Locations,Cultures,Glossary&limit=200`.
3. knowledge-service returns structured EntityRef list (anchored to glossary per `glossary_entity_id` FK).
4. BFF hydrates `[WORLD_CANON]` section of template with entity summaries (~30 tokens per entity × 200 = ~6000 tokens, matching §5.4 budget).
5. LLM produces CreativeSeed grounded in canon — `canonical_settlements` names come from book locations; `culture_hints.tag` references match book cultures; `naming_styles` per culture matches book corpus.
6. Validator includes referential check: every `canonical_settlement.canon_ref` MUST resolve via knowledge-service (V1+ active reject: `authoring.canon_ref_unresolved`).

**V1 status:** Schema-reserved. Knowledge-service is "planned" per CLAUDE.md `101_DATA_RE_ENGINEERING_PLAN.md`; not built. V1 LLM authoring uses `LlmGenerated { knowledge_grounding: None }` and produces ungrounded canon. V1+ activation when knowledge-service ships closes this gap.

---

## §7 Multi-turn iteration loop (BFF-held; bounded V1 caps)

```
[AuthoringState::InProgress]
  ↓ author submits intent → BFF creates AuthoringSession
  ↓ producer chosen (LLM | Manual | Imported | KnowledgeExtracted) → first iteration
  ↓ producer output (e.g., LLM JSON) → validator
  ↓ ValidationResult:
       Valid → AuthoringIteration logged; draft proposed to author
       Invalid → retry up to N=3 with error context (LlmGenerated only); else surface to author for manual fix
  ↓ AuthorAction:
       Accept → AuthoringState::Accepted → trigger reality bootstrap with AuthoringMetadata embedded
       RejectAndRetry { feedback } → new iteration with feedback in [HISTORY]; cost accrues per S6
       EditManually { edits } → patch current_draft; revalidate; producer.author_edits_applied++
       Cancel → AuthoringState::Cancelled
  ↓ cost cap check: total_llm_cost_usd > $5 paid / $20 premium (per S6-D2) → AuthoringState::CostCapped
  ↓ iteration cap check: iteration_count > 10 (V1 cap) → reject `authoring.iteration_cap_exceeded`
[AuthoringState::Accepted] → reality bootstrap proceeds
```

### V1 caps

- `iteration_count_max = 10` (rejects `authoring.iteration_cap_exceeded`)
- `retry_per_iteration_max = 3` (LLM-generated only; rejects `authoring.retry_cap_exceeded`)
- Cost cap inherited from S6-D2 (per-session $5 paid / $20 premium); warn at 80%, hard at 100%
- Session TTL = 24 hours wall-clock (BFF auto-cancels stale sessions)

### V1+30d enhancements (tracked GEO-AUTHOR-D2..D5)

- Auto-save draft (mirrors PO-D3 onboarding auto-save pattern)
- Resume cancelled session within 24h
- Multi-author collaboration (co-authors per PLT_001 Charter)
- Cost prediction before submit ("this LLM call will cost ~$0.50")

---

## §8 Validation + retry policy

| Step | What runs | Outcome |
|---|---|---|
| 1. JSON parse | serde_json parse of LLM output | Parse fail → `authoring.invalid_json` (retry with error context) |
| 2. Schema validation | CreativeSeed serde + schemars-generated JSON Schema validation | Validation fail → `authoring.schema_violation { field, error }` (retry) |
| 3. Cap validation | `culture_hints.len() ≤ 16` + `canonical_settlements.len() ≤ 50` + `position ∈ [0, 1]` for ExplicitPosition + others per GEO_001 §3 rules | Cap fail → `authoring.cap_violation { rule_id }` (retry) |
| 4. Reference validation | knowledge-service canon_ref resolution (V1+) | Resolve fail → `authoring.canon_ref_unresolved` (retry V1+; defer V1) |
| 5. Content safety | §12X.L7 PII scrubber + §12Y.L5 injection scanner on `lore_hooks_per_region.content` + `canonical_settlements.name` | Scrub fail → `authoring.content_safety_violation` (retry) |

Retry strategy: bounded N=3 per iteration. On exhaustion, surface to author with `authoring.retry_cap_exceeded` and offer `EditManually` fallback. Author edits move state to `Hybrid { primary: LlmGenerated{..}, author_edits_applied: N }`.

---

## §9 Producer abstraction

Five producers per §4.1:

| Producer | V1 status | Path |
|---|---|---|
| **LlmGenerated** | ✅ V1 active | chat-service via S9 template `world_authoring/v1.tmpl` per §5; cost via S6; bounded retry per §8 |
| **AuthorManual** | ✅ V1 active | BFF form UI v1; field-by-field validation matching CreativeSeed schema; no LLM call; no cost |
| **Imported** | 📦 V1+ | Source-format-specific validator (`AzgaarFmgJson` first; rest later); manual mapping to CreativeSeed shape; no LLM unless author chooses Hybrid |
| **KnowledgeServiceExtracted** | 📦 V1+ | Requires knowledge-service V1+; pre-hydrated `[WORLD_CANON]` section per §6 |
| **Hybrid** | ✅ V1 active | Any primary producer + author manual edits applied; `author_edits_applied` counter increments per edit |

**Why all 5 are first-class:** V1 single-cell SPIKE_01 realities don't need LLM authoring. V1 author who wants exact Tang dynasty canonical map uses Manual + ExplicitPosition for every canonical_settlement. V1+ author who imports Azgaar JSON for a non-canonical wuxia world skips LLM entirely. Producer abstraction means the procgen pipeline doesn't care which producer made the CreativeSeed — same downstream contract.

---

## §10 RealityManifest extension

Per `_boundaries/02_extension_contracts.md` §2: GEO_001b ADDS one OPTIONAL field to the existing extension block (additive per I14):

```rust
// Inline addition on the existing GEO_001 RealityManifestGeographyExtension block:
pub continent_geometries: Vec<ContinentGeometryDecl>,    // (existing per GEO_001 §11)
pub authoring_metadata: Option<AuthoringMetadata>,       // NEW V1: None implies legacy / no metadata captured
```

Why on RealityManifest (not on ContinentGeometryDecl): authoring is per-reality, not per-continent. A reality with 3 continents authored in a single LLM session shares one AuthoringMetadata.

---

## §11 CreativeSeed schema_version 1 → 2 migration (additive per I14)

When GEO_001b LOCKs, CreativeSeed.schema_version bumps 1 → 2:

| Field | V1 (=1) | V1+ (=2) |
|---|---|---|
| `hearth_position_normalized: (f32, f32)` (on CultureHint) | Required | **Optional** — defaultable to None if `hearth_preference` is Some |
| `hearth_preference: Option<SpatialPreference>` (NEW on CultureHint) | (absent) | Optional; **at least one of** (`hearth_position_normalized`, `hearth_preference`) MUST be Some — validator `authoring.spatial_intent_required` |
| `position_normalized: (f32, f32)` (on CanonicalSettlementDecl) | Required | **Optional** — same defaultability rule |
| `spatial_preference: Option<SpatialPreference>` (NEW on CanonicalSettlementDecl) | (absent) | Optional; same at-least-one-Some validator |
| `schema_version: u32` (on CreativeSeed) | = 1 | = 2 |

Upcaster pattern per R3: schema_version=1 CreativeSeed is readable by schema_version=2 implementer (treats missing `spatial_preference` as None, uses position). Schema_version=2 writer prefers `spatial_preference` for LLM-authored worlds and `position_normalized` for Manual + Imported producers. NO data migration required — both fields coexist forever.

Validator rule extension on CultureHint + CanonicalSettlementDecl: `hearth_position_normalized.is_some() || hearth_preference.is_some()` (at-least-one-Some); both Some is valid (procgen prefers spatial_preference; position is fallback / human-readable annotation).

---

## §12 Failure UX — `authoring.*` RejectReason namespace

Owned by GEO_001b. Registered in `_boundaries/02_extension_contracts.md` §1.4. V1 rule_ids (8) + V1+ reservations (4).

| Rule ID | Severity | Where raised | Vietnamese user copy (V1) | English fallback |
|---|---|---|---|---|
| `authoring.invalid_json` | user (LLM only) | Step 1 JSON parser | "LLM tạo dữ liệu không hợp lệ. Đang thử lại..." | "LLM produced invalid JSON. Retrying..." |
| `authoring.schema_violation` | user (LLM only) | Step 2 schema validator | "Dữ liệu LLM không khớp cấu trúc. Đang thử lại..." | "LLM output schema mismatch. Retrying..." |
| `authoring.cap_violation` | user | Step 3 cap validator | "Vượt quá giới hạn (ví dụ ≤16 văn hóa hoặc ≤50 thị trấn)." | "Cap exceeded (e.g., ≤16 cultures or ≤50 settlements)." |
| `authoring.content_safety_violation` | user (LLM only) | Step 5 PII + injection scan | "Nội dung bị chặn vì lý do an toàn." | "Content blocked for safety reasons." |
| `authoring.iteration_cap_exceeded` | user | Iteration loop | "Đã đạt giới hạn 10 lần lặp. Hãy chấp nhận bản thảo hiện tại hoặc bắt đầu lại." | "10-iteration cap reached. Accept current draft or restart." |
| `authoring.retry_cap_exceeded` | user (LLM only) | Retry loop | "LLM thử 3 lần không thành công. Hãy chỉnh sửa thủ công." | "LLM retry cap reached. Please edit manually." |
| `authoring.cost_cap_exceeded` | user | S6 cost-cap gate | "Đã đạt giới hạn chi phí cho phiên này. Hãy chấp nhận bản thảo hiện tại hoặc nâng cấp gói." | "Cost cap reached for this session. Accept current draft or upgrade plan." |
| `authoring.spatial_intent_required` | schema | V1+ schema_version=2 validator | "Mỗi văn hóa/thị trấn cần ít nhất tọa độ hoặc spatial preference." | "Each culture/settlement requires at least position or spatial preference." |

**V1+ reservations:** `authoring.canon_ref_unresolved` (V1+ knowledge-service active) · `authoring.template_version_deprecated` (V1+ when V1 template superseded) · `authoring.import_format_unsupported` (V1+ Imported producer) · `authoring.collaboration_conflict` (V1+ multi-author collaboration).

---

## §13 Cross-service handoff

| Service | Role | V1 status |
|---|---|---|
| **api-gateway-bff** | AuthoringSession owner — UX state held here; iteration coordination; producer routing | V1 |
| **chat-service** (LiteLLM) | LLM provider gateway — executes `world_authoring/v1.tmpl` with schema-constrained generation per §5.3 | V1 |
| **usage-billing-service** | S6 cost ledger — records each LLM call in `user_cost_ledger`; gates cost-cap per S6-D2 | V1 |
| **glossary-service** | LocalizedName + BookCanonRef storage (per GEO_001 §13) | V1 |
| **world-service** | RealityBootstrapper consumes final CreativeSeed + AuthoringMetadata; emits GeographyBorn | V1 |
| **knowledge-service** | (V1+ planned) — entity grounding per §6 contract | V1+ |
| **auth-service** | User profile for ACTOR_CONTEXT section + UserId for AuthoringSession.author_user_id | V1 |

No new service introduced. All work fits inside existing services.

---

## §14 Sequences

### 14.1 LLM-authored world (V1 happy path)

```
Author "Lý Minh" submits intent: "Wuxia world, Nam Tống dynasty, focus on Tương Dương region."
  ↓ BFF creates AuthoringSession {id, producer: LlmGenerated{template: world_authoring/v1, grounding: None}, author_user_id, iteration 0}
  ↓ BFF calls chat-service: render template v1; [INPUT] = author intent (XML-escaped); schema-constrained output
    against creative_seed.v2.schema.json; max_tokens=4000
  ↓ chat-service routes via LiteLLM to user's BYOK provider (or platform paid pool); S6 records cost ($0.12)
  ↓ LLM returns CreativeSeed JSON v2: {archetype: Wuxia, world_scale: Region, hemisphere: Northern, coastline:
    Coastal, culture_hints: [han_jiangnan + mongol_steppe with spatial_preference: NearBiome(Plain) +
    NearClimate(Boreal)], canonical_settlements: [Tương Dương with spatial_preference: NearSettlement(self_anchor),
    Khai Phong with spatial_preference: NearBiome(Plain)], naming_styles: {han_jiangnan: Markov corpus "tang_song_chinese"}}
  ↓ Validator: parse OK, schema OK, caps OK (2 cultures ≤ 16, 2 settlements ≤ 50), content-safety OK
  ↓ AuthoringIteration logged; current_draft = the CreativeSeed; author reviews UI rendering
  ↓ Author: "Add Yên Vũ Lâu near Tương Dương" → RejectAndRetry { feedback: I18nBundle{...} }
  ↓ Iteration 2: chat-service re-runs template with [HISTORY] including iteration 1 + feedback; cost $0.15
  ↓ LLM returns updated CreativeSeed with 3rd canonical_settlement Yên Vũ Lâu spatial_preference:
    NearSettlement("Tương Dương")
  ↓ Validator: pass; author Accepts
  ↓ AuthoringState::Accepted; AuthoringMetadata {producer: LlmGenerated, cost: $0.27, calls: 2, iterations: 2,
    template_version: 1, grounding_book_id: None} embedded in RealityManifest
  ↓ RealityBootstrapper emits EVT-T4 GeographyBorn with authoring_metadata payload
  ↓ world-service runs procgen pipeline; spatial_preferences resolved at stages 6+ (Tương Dương placed in
    Plain biome; Yên Vũ Lâu placed near Tương Dương; Khai Phong placed in another Plain region)
```

### 14.2 Manual-form world (V1; no LLM)

```
Author selects AuthoringProducer::AuthorManual{ui_form_version: 1}
  ↓ BFF renders 12-field form (archetype dropdown / world_scale dropdown / culture_hints dynamic-add /
    canonical_settlements with name+role+position OR spatial_preference picker / naming_styles file upload)
  ↓ Author fills in fields canonical_settlement-by-canonical_settlement; uses ExplicitPosition for known
    canonical coordinates (Tương Dương @ (0.4, 0.5)); uses SpatialPreference::NearBiome(Forest) for
    nondescript wilderness settlements
  ↓ Author submits; field-level validation; schema validation; cost = $0 (no LLM)
  ↓ AuthoringState::Accepted; AuthoringMetadata {producer: AuthorManual{ui_form_version: 1}, cost: $0, calls: 0,
    iterations: 1, ...} embedded
  ↓ Bootstrap proceeds normally
```

### 14.3 Knowledge-service-extracted world (V1+ when knowledge-service ships)

```
Author selects AuthoringProducer::KnowledgeServiceExtracted{book_id: "than_dieu_dai_hiep", extraction_template_ref}
  ↓ BFF calls knowledge-service: GET /v1/books/than_dieu_dai_hiep/entities?scope=Locations,Cultures,Glossary&limit=200
  ↓ knowledge-service returns 87 locations + 12 cultures + 156 glossary entries
  ↓ BFF hydrates [WORLD_CANON] section with entity summaries (~5400 tokens); routes to chat-service
  ↓ LLM produces CreativeSeed grounded in canon — every canonical_settlement.name matches a knowledge-service
    location; canonical_settlement.canon_ref populated; culture_hints reference book cultures; naming_styles
    per book corpus
  ↓ Validator step 4 (V1+ active): canon_ref resolution via knowledge-service — all 87 settlements resolve OK
  ↓ AuthoringState::Accepted; AuthoringMetadata embedded with grounding_book_id Some("than_dieu_dai_hiep")
  ↓ Bootstrap proceeds; ground truth = book canon, not LLM imagination
```

---

## §15 Acceptance criteria

10 V1-testable acceptance scenarios.

| ID | Scenario | Reject rule_id |
|---|---|---|
| **AC-AUTHOR-1** | LLM authoring happy path: author intent → schema-constrained generation → valid CreativeSeed → author Accepts → bootstrap with AuthoringMetadata{producer: LlmGenerated{template_ref: v1, grounding: None}, ...}. | — |
| **AC-AUTHOR-2** | LLM produces invalid JSON → retry with error context → succeeds on 2nd attempt → AuthoringMetadata.total_llm_calls = 2. | `authoring.invalid_json` (transient; resolved on retry) |
| **AC-AUTHOR-3** | LLM produces JSON failing cap validation (17 culture_hints) → retry-with-error-context exhausts after 3 tries → surface `authoring.retry_cap_exceeded` to author → author chooses EditManually → trims to 16 → Accepts → AuthoringMetadata.producer = Hybrid{primary: LlmGenerated, author_edits_applied: 1}. | `authoring.retry_cap_exceeded` + `authoring.cap_violation` |
| **AC-AUTHOR-4** | Author chooses AuthorManual producer → form-fills 8 canonical_settlements with mix of ExplicitPosition + SpatialPreference::NearBiome → submits → schema validates → bootstrap with AuthoringMetadata.cost_usd = 0. | — |
| **AC-AUTHOR-5** | LLM authoring session accumulates $5.01 cost across 7 iterations → cost-cap gate fires per S6-D2 → AuthoringState::CostCapped → author sees `authoring.cost_cap_exceeded` → can Accept current_draft or Cancel; cannot iterate further this session. | `authoring.cost_cap_exceeded` |
| **AC-AUTHOR-6** | Author runs 11 iterations → iteration cap fires → `authoring.iteration_cap_exceeded` → author must Accept or Cancel. | `authoring.iteration_cap_exceeded` |
| **AC-AUTHOR-7** | CreativeSeed schema_version=2 with culture_hint having both `hearth_position_normalized` Some + `hearth_preference` Some (NearCulture) → procgen at stage 8 prefers spatial_preference; position is fallback annotation; both coexist in stored CreativeSeed. | — |
| **AC-AUTHOR-8** | CreativeSeed schema_version=2 with culture_hint having NEITHER `hearth_position_normalized` NOR `hearth_preference` Some → reject `authoring.spatial_intent_required` at schema validation step 3. | `authoring.spatial_intent_required` |
| **AC-AUTHOR-9** | RealityManifest omits `authoring_metadata` (legacy reality bootstrapped before GEO_001b ships) → bootstrap proceeds normally; GeographyBorn payload carries `authoring_metadata: None`; no validator complaint (additive field per I14). | — |
| **AC-AUTHOR-10** | LLM authoring with `KnowledgeServiceExtracted` producer V1 → knowledge-service unavailable → reject `authoring.knowledge_service_unavailable` (V1+ active when knowledge-service ships); V1 falls back to `LlmGenerated{grounding: None}` automatically and emits warning to author. | (V1+) `authoring.knowledge_service_unavailable` |

---

## §16 Deferrals

| ID | Item | Tier |
|---|---|---|
| **GEO-AUTHOR-D1** | Knowledge-service V1+ activation (§6); unblocks AC-AUTHOR-10 V1+ active behavior + AuthoringProducer::KnowledgeServiceExtracted | V1+ |
| **GEO-AUTHOR-D2** | Auto-save authoring draft (mirrors PO-D3 onboarding) | V1+30d |
| **GEO-AUTHOR-D3** | Resume cancelled session within 24h | V1+30d |
| **GEO-AUTHOR-D4** | Cost prediction before LLM submit | V1+30d |
| **GEO-AUTHOR-D5** | Multi-author collaboration (PLT_001 Charter co-authors) | V2+ |
| **GEO-AUTHOR-D6** | AzgaarFmgJson import format activation (V1+ first import target) | V1+ |
| **GEO-AUTHOR-D7** | LoreWeaveManifest export/import for reality migration | V1+ |
| **GEO-AUTHOR-D8** | T6 LLM CreativeSeed extension proposal post-bootstrap (per GEO_001 GEO-D12) | V1+ |
| **GEO-AUTHOR-D9** | Hybrid producer counter-display in admin Forge ("this world was 70% LLM + 30% author edits") | V1+30d |
| **GEO-AUTHOR-D10** | Schema-version-2 deprecation of `position_normalized` (V2+ if all V1+ authoring uses SpatialPreference) | V2+ |

---

## §17 Open questions

| ID | Question | Resolution path |
|---|---|---|
| **GEO-AUTHOR-Q1** | Should AuthoringSession be persisted (T2/Reality) instead of BFF-held? Pro: audit trail of rejected drafts. Con: storage cost + privacy concerns (rejected drafts may contain LLM-generated content author chose NOT to canonize). | V1: BFF-held (chosen — keeps rejected content ephemeral). V1+ if audit need surfaces, persist accepted-only. |
| **GEO-AUTHOR-Q2** | Should `world_authoring/v1.tmpl` be hand-tuned per WorldArchetype (Wuxia-specific prompt vs. Cyberpunk-specific) or single template handles all 12 archetypes? | V1: single template (simpler). V1+ if archetype-specific quality differs, split per archetype. |
| **GEO-AUTHOR-Q3** | What's the FALLBACK if author refuses to use Manual edit after LLM retry cap exceeded? Cancel session? Force-accept the last valid draft? | V1: surface both Cancel + Accept-last-valid options; author picks. |
| **GEO-AUTHOR-Q4** | How does SpatialPreference::NearSettlement(LocalizedName) resolve if the referenced settlement doesn't exist in canonical_settlements? | V1+ (when SpatialPreference activates): validator reject `authoring.spatial_reference_unresolved`. |
| **GEO-AUTHOR-Q5** | Should manual edits (Hybrid producer.author_edits_applied counter) be granular (per-field) for fine-grained audit? | V1: just a counter (simple). V1+ per-field edit log if audit need surfaces. |

---

## §18 Cross-references

- [`GEO_001 §6 CreativeSeed`](GEO_001_world_geometry.md#6-creativeseed-llm-supplied-creative-direction) — the data shape this file's write-side contract produces
- [`GEO_001 §3 world_geometry aggregate`](GEO_001_world_geometry.md#31-world_geometry-t2--channel-continent--primary) — schema_version field on the OTHER side (WorldGeometry aggregate has its own schema_version per I14)
- [`02_storage/S06_llm_cost_controls.md`](../../02_storage/S06_llm_cost_controls.md) — cost cap pattern + `user_cost_ledger` table for cost tracking
- [`02_storage/S09_prompt_assembly.md`](../../02_storage/S09_prompt_assembly.md) — prompt-assembly template registry + governance + schema-constrained generation discipline
- [`02_storage/S08_audit_pii_retention.md`](../../02_storage/S08_audit_pii_retention.md) — PII scrubber on author intent text (`[INPUT]` section)
- [`05_llm_safety/04_injection_defense.md`](../../05_llm_safety/04_injection_defense.md) — injection defense on author intent text
- [`features/03_player_onboarding/PO_001_player_onboarding.md`](../03_player_onboarding/PO_001_player_onboarding.md) — sibling pattern (PO-A4 AI Character Assistant) for LLM-assisted authoring UX
- [`_boundaries/02_extension_contracts.md` §1.4](../../_boundaries/02_extension_contracts.md) — `authoring.*` reject namespace
- [`_boundaries/02_extension_contracts.md` §2](../../_boundaries/02_extension_contracts.md) — RealityManifest `authoring_metadata: Option<AuthoringMetadata>` extension
- [`CLAUDE.md`](../../../../CLAUDE.md) — knowledge-service planned per `101_DATA_RE_ENGINEERING_PLAN.md`; provider-gateway invariant for chat-service

---

## §19 Implementation readiness

**Design layer (this commit):** ✅ AuthoringProducer 5-variant + SpatialPreference 14-variant + AuthorAction 4-variant + ValidationResult 2-variant + AuthoringMetadata + AuthoringSession (BFF-held) shapes declared · S9 template `world_authoring/v1.tmpl` 8-section contract specified · schema-constrained generation REQUIRED · multi-turn iteration loop with V1 caps (iteration ≤ 10 / retry ≤ 3 / cost per S6-D2) · validation pipeline 5 steps · 5 producers (3 V1 active + 2 V1+ schema-reserved) · CreativeSeed.schema_version 1 → 2 additive migration plan · 8 V1 `authoring.*` rule_ids + 4 V1+ reservations · 10 V1-testable acceptance scenarios.

**Implementation phase (V1):** 📦 BFF AuthoringSession state + form UI + LlmGenerated routing through chat-service · S9 template registration with v1 fixtures · CreativeSeed JSON Schema generated from Rust struct via schemars · validation+retry loop · cost-cap integration with S6 user_cost_ledger.

**Downstream integration (V1+):** 📦 knowledge-service grounding when knowledge-service ships · AzgaarFmgJson Imported producer activation · Hybrid edit log granularity per GEO-AUTHOR-Q5.

**Status:** DRAFT. CANDIDATE-LOCK upon §15 acceptance scenarios passing integration tests against the reference BFF AuthoringSession implementation. LOCK upon V1 LLM-authored reality bootstrap end-to-end (AC-AUTHOR-1 fixture).
