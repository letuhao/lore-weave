# TMP_008 — LLM Integration (L3 + L4)

> **Conversational name:** "LLM Layers" (TMP-LLM). The V2 augmentation layer. L3 = LLM zone classifier (categorical entity placement). L4 = LLM regional narration (free-form prose per zone). LLM never sees raw tiles — only zone summaries. Cost bounded per tilemap regardless of grid size. Mirrors CSC_001 v3→v4 4-layer pattern; reuses AIT-A4 hybrid 2-stage generation.
>
> **Category:** TMP — Tilemap Foundation
> **Status:** **DRAFT 2026-05-13** (revised 2026-05-13 for license-hygiene framing; V2 feature; V1+30d ships with these layers disabled)
> **Owns:** TMP-23 + TMP-31 + TMP-32 + TMP-33 catalog entries
> **Builds on:** [CSC_001](../00_cell_scene/CSC_001_cell_scene_composition.md) v3→v4 architectural pattern, [AIT_001](../16_ai_tier/AIT_001_ai_tier_foundation.md) AIT-A4 hybrid 2-stage, [05_llm_safety/](../../05_llm_safety/) intent classifier + injection defense + World Oracle
> **Architectural pattern source:** LoreWeave internal — CSC_001 v3→v4 lessons. No external precedent for LLM-augmented procedural map generation in the genre prior art surveyed (§12); this is novel territory.

---

## §1 Why layered LLM augmentation

V1+30d ships engine-only generation: zones placed, terrain painted, treasures placed, obstacles filled. The tilemap is **playable** but **flat** — every zone in a "forest" template looks samey; the narrative scaffold (LLM NPCs, ambient prose) has nothing to anchor to.

LLM augmentation closes the gap. Two layers:

- **L3 LLM zone classifier** — LLM picks "this bandit camp goes in forest_west, not in mountain_pass" — categorical placement that respects narrative intent. Engine still picks the exact tile (per AIT-A4 hybrid: cheap engine stage + lazy LLM stage).
- **L4 LLM regional narration** — LLM writes 1-2 paragraphs of ambient prose per zone, cached. Used as context for NPC dialogue, travel narration, structural state changes. Gives LLM a stable "voice" for each region.

Combined cost: ~4-5K tokens per tilemap composition (one-time at bootstrap or Forge:RegenTilemap). Independent of grid size — LLM never sees tiles, only zone summaries (TMP-A9).

V1+30d ships these layers **disabled** (`tilemap_defaults.llm_enabled: false`). V2 default ON.

---

## §2 The CSC_001 v3→v4 lesson (why LLM is categorical, not spatial)

CSC_001 went through 3 architectural attempts. v3 had LLM generate the cell interior (16×16 tile grid) directly. Result: tokens scaled with grid area (256 tiles = lots of tokens); LLM struggled with spatial coherence (placed two adjacent walls; placed enemy inside wall); 3-4× higher cost than v4.

v4 pivoted to **categorical classification**: LLM picks "this enemy goes in the kitchen zone, not the hallway"; engine picks the exact tile within the kitchen zone. Result: 12.7× cost reduction; spatial coherence improved (engine guarantees no-overlap; LLM stays in lane).

TMP_008 directly inherits this pattern. **LLM is never spatial.** Engine handles all spatial reasoning (tile selection, footprint fit, connectivity). LLM only handles categorical assignment + free-form prose.

---

## §3 L3: LLM Zone Classifier

### 3.1 What L3 decides

After engine-only L2 generation completes, we have:
- All zones with terrain + treasures + obstacles + connections
- Generic `TilemapObjectKind::Treasure` piles placed everywhere

L3's job: **upgrade generic objects to canon-specific narrative-tagged objects**, classified by zone.

Examples:
- Generic `Treasure { value: 5000 }` in forest_zone → "abandoned bandit cache" (`BookCanonRef = bandit_legend`)
- Generic `Treasure { value: 12000 }` in mountain_zone → "ancient sect cultivation cave" (`BookCanonRef = sect_history`)
- Generic `MonsterLair` adjacent to bandit_cache → "bandit camp" not "wolf den"
- Generic `Landmark` in mountain_zone → "Eight Trigrams Hexagram boulder" (canon-grade)

The LLM doesn't decide locations (engine did that in L2). LLM decides **what the object IS** in the narrative sense.

### 3.2 L3 Input

LLM prompt input:

```
Place metadata:
  - channel_id, tier, reality_id, season
  - book_canon_refs available (e.g., "Wuxia Continent — Lotus Sect lore")
  - structural_state: "wartime" | "peaceful" | "crisis"

Zones in this tilemap (4-12 zones):
  - zone_1: {
      zone_type: "treasure",
      terrain: "grass",
      monster_strength: "normal",
      treasure_tier_summary: "1 high-value, 4 medium, 6 low",
      object_count_by_kind: { Treasure: 11, MonsterLair: 3, Landmark: 1 },
      author_narrative_hint: Some("ancestral homeland of Lotus Sect lay disciples")
    }
  - zone_2: { ... }
  - zone_N: { ... }

Objects to classify (15-50 placeholders):
  - obj_1: { kind: Treasure, value: 5000, current_zone: zone_1, suggested_canon_kind: [BanditCache, AbandonedCellar, OldShrine] }
  - obj_2: { kind: MonsterLair, strength: 2000, current_zone: zone_1, suggested_canon_kind: [BanditCamp, WolfDen, BeastTerritory] }
  - obj_N: ...
```

`suggested_canon_kind` is engine-pre-filtered: the engine knows that `Treasure { value: 5000 }` in `grass` terrain with `monster_strength: normal` could be Bandit Cache or Cellar or Shrine, based on canon tag list. LLM picks one (or proposes new but engine validates).

### 3.3 L3 Output

LLM emits JSON:

```json
{
  "classifications": [
    {
      "obj_id": "obj_1",
      "canon_kind": "BanditCache",
      "narrative_tag": "abandoned_bandit_cache_lotus_sect",
      "canon_ref": "bandit_legend_lotus_sect_v1",
      "rationale": "matches Zone 1's narrative_hint about Lotus Sect ancestral homeland; bandit cache fits ambient theme"
    },
    {
      "obj_id": "obj_2",
      "canon_kind": "BanditCamp",
      "narrative_tag": "wolf_pelt_camp_bandits",
      "canon_ref": "bandit_legend_lotus_sect_v1",
      "rationale": "monster lair near bandit cache → camp matches"
    },
    ...
  ]
}
```

`canon_ref` references a `book_canon` aggregate row (existing via NAR_001 / glossary-service). LLM picks from author-uploaded list; if author hasn't uploaded a fitting canon, LLM proposes new which goes through EVT-T6 Proposal flow → author Forge approval.

### 3.4 Validation + 3-retry feedback loop

Reuses the validation + retry pattern established at CSC_001 §6.4 (LoreWeave-internal pattern; see Prior Art §12).

```
attempt = 1
WHILE attempt <= 3:
    response = call_llm(prompt)
    validation_errors = validate(response)
    IF validation_errors is empty:
        apply_response()
        RETURN Ok
    ELSE:
        # Augment prompt with validation feedback
        prompt = original_prompt + "Validation errors: " + validation_errors + ". Retry."
        attempt += 1

# After 3 retries: fall back to canonical default
apply_canonical_default()
RETURN Ok (with degraded mode flag)
```

Validation rules:
- `obj_id` exists in input placeholders
- `canon_kind` is in `suggested_canon_kind` list for that obj (LLM doesn't invent)
- `canon_ref` exists in reality's `book_canon` aggregate (or is None)
- `narrative_tag` is valid snake_case (no spaces, ≤ 64 chars)
- All input obj_ids are classified (LLM didn't skip any)
- No duplicate `obj_id` entries

If LLM consistently fails (3 retries): canonical-default fallback. Each `suggested_canon_kind` list has a "default" pre-tagged (first entry). LLM never strictly required; system always succeeds.

### 3.5 Canonical default fallback

Per AIT-A4 + CSC_001 §6.4: the engine ALWAYS has a deterministic answer. LLM is augmentation, not requirement.

```rust
fn canonical_default_classification(placeholder: &Placeholder) -> Classification {
    Classification {
        obj_id: placeholder.obj_id,
        canon_kind: placeholder.suggested_canon_kind[0],  // first option in list
        narrative_tag: generate_default_tag(placeholder),
        canon_ref: None,                                   // no narrative tie-in
        rationale: "Canonical default (LLM unavailable or failed)".to_string(),
    }
}
```

Result: tilemap is **always playable**; LLM can fail silently and engine compensates.

---

## §4 L4: LLM Regional Narration

### 4.1 What L4 produces

Per zone, 1-2 paragraphs of Vietnamese-flavored ambient prose. Examples:

```
zone_1 (forest_zone, "ancestral homeland of Lotus Sect lay disciples"):
"Bạn bước vào khu rừng cổ thụ phía Tây Hangzhou, nơi tổ tiên môn phái Liên Hoa đã trồng từ
ngàn năm trước. Lá xanh ngả vàng theo gió, để lộ những hốc cây ẩn chứa bí mật. Đâu đó vọng
lại tiếng chuông đồng nhỏ — chuông canh của các sư huynh."

zone_3 (mountain_zone, "lost cultivation grounds of Diamond Sect"):
"Dãy núi Bạch Tuyết cao chót vót, mây bao phủ quanh năm. Các đỉnh núi tựa như kim cương đã
được mài giũa từ trí tuệ của hàng vạn cao thủ. Không khí mỏng khiến phổi nóng rát, nhưng
khí huyết của những ai tu luyện cao thâm lại càng tinh khiết hơn ở đây."
```

Used as **context for downstream LLM** calls (NPC dialogue, travel narration, structural-state changes). Cached aggressively.

### 4.2 L4 Input

```
Per zone:
  - terrain_kind, season, structural_state
  - L3 classified objects (incl. canon_refs)
  - book_canon for this zone (full text excerpts, ~200 tokens budget)
  - author_narrative_hint
  - prompt_template_version

Style hints (per reality):
  - tone (xianxia / wuxia / scifi / modern)
  - voice (first-person / second-person)
  - prose_length_target (1-3 paragraphs)
  - language (Vietnamese / English / etc.)
```

### 4.3 L4 Output

```json
{
  "zone_narrations": [
    {
      "zone_id": "zone_1",
      "narration": "Bạn bước vào khu rừng cổ thụ ...",
      "key_phrases_for_lookup": ["forest", "lotus_sect", "ancestral"],
      "prompt_template_version": 1
    },
    ...
  ]
}
```

`key_phrases_for_lookup` enable downstream LLM retrieval: "give me the regional narration that mentions 'lotus_sect'" returns this narration. Used by NPC roleplay (NPC_001/002) for grounding.

### 4.4 Caching

Per zone narration cached at:
```
key = blake3(zone_id || season || structural_state || prompt_template_version)
```

Cache hit: return cached narration; no LLM call. ~99% of reads.

Cache miss triggers:
- New zone created (rare)
- Season changed (4×/year fictional)
- `structural_state` changed (war declared → "wartime"; war ended → "peaceful")
- `prompt_template_version` incremented (engine ships new template; force re-narration)
- Forge:RegenTilemap (full re-generate)

Stored in DP as part of `tilemap_view.regional_narration: HashMap<ZoneId, String>` (T2/Channel scope).

### 4.5 L4 cost model

Per zone narration: ~500-1000 tokens (input prompt + output 1-2 paragraphs).
Typical tilemap: ~10 zones × ~750 tokens = ~7,500 tokens.

**First generation:** ~7,500 tokens × 10 tilemaps (continent + countries + districts + towns) = ~75,000 tokens. One-time cost per reality.

**Per-season refresh** (4×/year fictional, ~once per real-world day in normal-play time-flow): ~7,500 tokens × season-affected zones × ~5 tilemaps = ~37,500 tokens per refresh.

**Per-structural-state change:** rare; ~10 tokens × affected zones (~5 per change).

**Total V2 per-reality LLM budget for L4:** ~75k initial + ~150k/year ongoing = manageable; cached aggressively.

---

## §5 Combined L3+L4 cost model

| Phase | Token cost per tilemap | Frequency |
|---|---|---|
| L3 zone classification | ~3K tokens (15-50 objects, structured JSON) | Once at bootstrap; once per Forge:RegenTilemap |
| L4 regional narration (initial) | ~7.5K tokens (10 zones × ~750) | Once at bootstrap |
| L4 narration cache miss (per season change) | ~3-5K tokens (affected zones only) | ~4× per fictional year |
| L4 cache miss (structural-state change) | ~1-3K tokens (affected zones only) | Rare (war declared, etc.) |

**Per tilemap initial cost: ~10-15K tokens.**

**Per typical reality** (1 continent + 4 country + 16 district + 64 town = 85 tilemaps):
- Initial: ~85 × 12K = ~1M tokens (one-time)
- Ongoing: ~85 × 1K/season = ~85K tokens per season change

Conservative pricing at $1/1M tokens (Claude Haiku in 2026):
- One reality initial: ~$1
- One reality ongoing: ~$0.10 per season change × 4/year = ~$0.40/year

**Bounded.** Per TMP-A9, LLM cost is independent of grid size — 256×256 vs 64×64 same token count per zone.

---

## §6 Integration with 05_llm_safety

All L3 + L4 LLM calls go through `05_llm_safety` guardrails per the standard pattern:

1. **3-intent classifier** — incoming author-narrative-hint goes through intent classifier (creative / question / harmful). Harmful intents rejected before LLM call.
2. **Injection defense** — prompt template uses 05_llm_safety wrappers; sanitizes user input; uses delimiters; structured-output enforcement.
3. **World Oracle determinism** — LLM is told it's in role of "Zone Classifier" or "Regional Narrator", with explicit "do not contradict canonical facts" rule. World Oracle layer validates output against `book_canon`.
4. **Canon drift detector** — if LLM emits classifications/narrations that contradict existing canon, route to author Forge approval queue (not auto-apply).

Integration points:
- Prompt template lives in `05_llm_safety/prompts/tilemap_zone_classifier.md` and `tilemap_regional_narrator.md`
- LLM call wrapped by `05_llm_safety/llm_call_with_guardrails.rs`
- Output validation in `tilemap-service/src/llm/validation.rs`

---

## §7 Event-model flow (per TMP_001 §2.5)

V2 L3+L4 flow:

```
1. tilemap-service decides L3 classification needed (e.g., post-bootstrap; or Forge:RegenTilemap)
2. Emit EVT-T6 Proposal { aggregate_type: "tilemap_view", proposed_changes: L3_input_summary }
3. LLM call via 05_llm_safety wrappers
4. Validate output (§3.4)
5. IF validation passes:
   Emit EVT-T5 Generated { aggregate_type: "tilemap_view", classifications: [...], llm_model, attempts }
6. Apply classifications to tilemap_view.object_placements via DP-K5 write
7. Emit EVT-T3 Derived { aggregate_type: "tilemap_view", kind: "L3 classification applied" }

Same flow for L4 narration (with `kind: "L4 narration applied"`).
```

Replay-determinism preserved via:
- L3/L4 outputs cached in `tilemap_view.regional_narration` + per-object narrative_tag fields
- Replay reads cache (does NOT re-call LLM)
- On cache miss in replay: fall back to canonical default (LLM not called)
- TMP-A4 seed determinism guarantees same input → same engine output; cache key includes prompt_template_version so version bump → cache invalidation predictable

---

## §8 Author controls

V2 author can:

- **Enable / disable L3 per template:** `tilemap_template.llm_l3_enabled: bool`
- **Enable / disable L4 per template:** `tilemap_template.llm_l4_enabled: bool`
- **Author narrative hints per zone:** `zone_spec.narrative_hint: Option<String>` (feeds into L3 + L4 input)
- **Force re-narration:** `Forge:RegenTilemap { mode: NarrationOnly }` — V2 schema-additive variant — re-runs L4 only, preserves geometry
- **Veto LLM classifications:** in Forge UI, override individual `obj.canon_kind` selections; emits EVT-T8 Administrative `Forge:VetoLlmClassification`

V3 author can:

- **Tone / voice / language preferences per reality:** `tilemap_defaults.l4_style: L4Style { tone, voice, language }`
- **Provide reference passages:** `tilemap_defaults.l4_reference_passages: Vec<String>` (LLM in-context-learns voice)

---

## §9 Open questions

| ID | Question | Default proposal |
|---|---|---|
| TMP-LLM-Q1 | Should L3 + L4 share a single LLM call or separate calls? | Separate (different prompt templates, validation rules; separate retry budgets; V2+ might co-optimize but not V1+30d) |
| TMP-LLM-Q2 | When L3 proposes a new `canon_kind` not in author list, auto-add or require approval? | Require approval V2 (EVT-T8 Forge:ApproveCanonKind); V3 might auto-add if "minor" tag |
| TMP-LLM-Q3 | How to handle multilingual narration (author wants Vietnamese for zones in wuxia continent + English for sci-fi sector in same reality)? | Per-template `language` setting; default reality language fallback; V2+ feature |
| TMP-LLM-Q4 | Should LLM see surrounding-tilemap context (neighboring zones' narrations)? | YES V2 — provides cross-zone narrative continuity ("the forest narration mentions the mountain pass to the east"); cost: ~+500 tokens per zone |
| TMP-LLM-Q5 | What model to use V2? Haiku for cost, Sonnet for quality, or per-template choice? | Author-configurable via `tilemap_defaults.llm_model`; default Haiku 4.5 V2 (good enough; cheap); Sonnet upgrade in V2+30d |
| TMP-LLM-Q6 | Should we expose L3 / L4 outputs to player UI as "Zone Lore" tabs? | YES V2+ — sidebar showing per-zone narration on map hover/click; great for ambient world-building |
| TMP-LLM-Q7 | How to detect L4 narration that contradicts book canon? | World Oracle validation pass (§6); compare L4 output to canon excerpts via semantic similarity (knowledge-service); flag conflicts for author |

---

## §10 Connection to AIT_001 (AI Tier)

L3 LLM classifier is a Synthetic actor in AIT_001 taxonomy. Specifically:
- AIT canonical_tier = `Synthetic` (not Major / Minor / Untracked)
- AIT-A4 hybrid 2-stage applies: Stage 1 = engine deterministic L2 (placeholders generated); Stage 2 = LLM L3 classification (lazy)
- AIT-D21 V1+30d Stage 2 LLM-flavor synthesis prompt template ownership: TMP_008 owns `tilemap_zone_classifier.md` (analogous to PL_005 owning interaction synthesis); registered in `05_llm_safety/prompts/`

L4 narration is also Synthetic. AIT-A9 PromptDetail = `Condensed` for L4 (each zone gets condensed canonical context; not full Major-tier prompt budget).

---

## §11 V1+30d → V2 migration path

V1+30d ships with:
- `tilemap_defaults.llm_enabled: false` (default)
- `tilemap_view.generation_source: EngineGenerated` always
- `tilemap_view.regional_narration: None` always
- No L3/L4 emissions

V2 launch enables:
1. Author opts in via `tilemap_defaults.llm_enabled: true`
2. tilemap-service starts emitting EVT-T6 + EVT-T5 + EVT-T3 for affected channels
3. Existing `tilemap_view` rows get L3+L4 applied (one-time cost)
4. New tilemap_view rows get L3+L4 at bootstrap

Schema-additive per TMP-A8: V1+30d schema includes `regional_narration: Option<String>` + `generation_source: GenerationSource` with `LlmAugmented` variant pre-defined. No breaking change at V2.

Author can disable L3 + L4 independently. Granular opt-in.

---

## §12 Prior Art

### Architectural pattern (LoreWeave-internal source)

- [CSC_001 Cell Scene Composition](../00_cell_scene/CSC_001_cell_scene_composition.md). v3→v4 pivot established that **LLM as categorical classifier** (not spatial coordinate generator) bounds cost regardless of grid size. v3 had LLM emit raw tile placements at ~31K tokens; v4 has LLM emit zone-level categorical assignments at ~2.5K tokens (12.7× reduction). TMP_008 directly reuses this pattern.
- [AIT_001 AI Tier Foundation](../16_ai_tier/AIT_001_ai_tier_foundation.md). AIT-A4 hybrid 2-stage generation pattern: Stage 1 (engine cheap) + Stage 2 (LLM lazy). TMP L3 + L4 are Stage 2 implementations.
- [05_llm_safety/](../../05_llm_safety/). Guardrail patterns reused for L3 + L4 LLM calls.

### LLM-augmented procedural content generation

LLM-augmented PCG is an emerging research area; no mature genre prior art exists for tilemap-scale narrative LLM integration. Reference works that informed our design:

- **Sudhakaran, S., González-Duque, M., Glanois, C., Freiberger, M., Najarro, E. & Risi, S. (2023).** "Mariogpt: Open-ended text2level generation through large language models." *NeurIPS 2023* — Demonstrates LLM-emit-level approach + its scale limits; informs our v3→v4 anti-pattern lesson.
- **Todd, G., Earle, S., Nasir, M. U., Green, M. C. & Togelius, J. (2023).** "Level Generation Through Large Language Models." *FDG 2023* — Survey of LLM-PCG approaches.
- **Charity, M., Khalifa, A. & Togelius, J. (2020).** "Baba is Y'all: Collaborative mixed-initiative level design." — Mixed-initiative author + AI co-creation, similar to our L3 author-hint + LLM-classifier pattern.
- **Smith, G., Whitehead, J., Mateas, M. (2011).** "Tanagra: Reactive planning and constraint solving for mixed-initiative level design." — Constraint-respecting AI assistance.

### Genre prior art

- **Heroes of Might and Magic III** (1999, New World Computing). Genre prior art for the procedural map generation **substrate** (L1 + L2 layers); has no LLM integration. We extend with L3 + L4 LoreWeave-novel.
- **VCMI** (2007+, GPL v2+). Open-source HoMM3 engine reimplementation. Procedural substrate reference for L1 + L2; no LLM integration. Cited in TMP_001..TMP_007 Prior Art sections.
- **Dwarf Fortress** (2002+, Bay 12 Games). Procedural narration via "world history" generation — closest genre analog to our L4, though uses templates + Markov chains rather than LLMs.
- **AI Dungeon / NovelAI** (2019+). LLM-driven narrative games; demonstrate user appetite for LLM-grounded fictional worlds.

### LoreWeave internal references

- [TMP_001 §4](TMP_001_tilemap_foundation.md) — 4-layer composition architecture.
- [TMP_002..TMP_007](.) — L1 + L2 engine substrate that L3 + L4 augment.
