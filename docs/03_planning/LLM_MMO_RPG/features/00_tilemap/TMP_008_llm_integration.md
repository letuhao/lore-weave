# TMP_008 — LLM Integration (L3 + L4)

> **Conversational name:** "LLM Layers" (TMP-LLM). The V2 augmentation layer. L3 = LLM zone classifier (categorical entity placement). L4 = LLM regional narration (free-form prose per zone). LLM never sees raw tiles — only zone summaries. Cost bounded per tilemap regardless of grid size. Mirrors CSC_001 v3→v4 4-layer pattern; reuses AIT-A4 hybrid 2-stage generation.
>
> **This doc covers the architecture / V-tier / cost story.** The detailed I/O contract (prompt template, structured-output schema, validation rules, retry+fallback algorithm, prompt-injection defense, cacheable-prefix discipline, cache key derivation) lives in the sibling [TMP_008b LLM Contract Spec](TMP_008b_llm_contract_spec.md). Follows project's existing split pattern (PL_001/PL_001b, WA_002/WA_002b, PLT_002/PLT_002b).
>
> **Category:** TMP — Tilemap Foundation
> **Status:** **DRAFT 2026-05-13** (revised 2026-05-13 for license-hygiene framing + split with TMP_008b for I/O contract detail; V2 feature; V1+30d ships with these layers disabled)
> **Owns:** TMP-23 + TMP-31 + TMP-32 + TMP-33 catalog entries
> **Builds on:** [CSC_001](../00_cell_scene/CSC_001_cell_scene_composition.md) v3→v4 architectural pattern, [AIT_001](../16_ai_tier/AIT_001_ai_tier_foundation.md) AIT-A4 hybrid 2-stage, [05_llm_safety/](../../05_llm_safety/) intent classifier + injection defense + World Oracle
> **Detailed contract:** [TMP_008b](TMP_008b_llm_contract_spec.md) §1-§14 covers prompt template + structured output schema + validation + retry + injection defense + caching + cost model.
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

## §3 L3: LLM Zone Classifier (architecture)

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

### 3.2 L3 contract summary

Detailed contract in [TMP_008b §3 + §4 + §5 + §6](TMP_008b_llm_contract_spec.md). Headline shape:

- **Input:** reality context (cacheable per reality version) + zone summaries (4-12 zones with terrain + monster_strength + object_count + delimited author_narrative_hint) + objects-to-classify (15-50 placeholders, each with engine-pre-filtered `suggested_canon_kind` list of 2-4 options)
- **Mechanism:** Anthropic tool-use with strict `input_schema` (TMP_008b §3) — `tool_choice` forces a single `submit_zone_classifications` tool call
- **Output:** array of `{obj_id, canon_kind, narrative_tag, canon_ref, rationale}` — LLM picks `canon_kind` from `suggested_canon_kind`; LLM never invents
- **Validation:** 5 rules (every obj_id classified exactly once; canon_kind in suggested_canon_kind; canon_ref in book_canon_refs or null; narrative_tag snake_case ≤64 chars; no duplicates)
- **Retry:** per-object granularity (TMP_008b §5) — accept good entries, retry only the failing subset with structured per-case error messages (TMP_008b §4.2)
- **Fallback:** per-object canonical default (suggested_canon_kind[0]); system always succeeds (TMP_008b §6)
- **Cost:** ~6280 effective tokens per call (was claimed ~3K; corrected per TMP_008b §12); ~$0.018/call at Haiku 4.5 rates

### 3.3 LLM never decides location

Critical V2 design lesson (from CSC_001 v3→v4 pivot): **LLM is categorical classifier, NOT spatial coordinate generator.** LLM picks "this enemy goes in forest_west zone"; engine picks the exact tile. Bounds LLM token cost regardless of grid size — 64×64 vs 256×256 same tokens per zone.

### 3.4 V1+30d → V2 activation

V1+30d: L3 disabled (`tilemap_defaults.llm_enabled: false`); engine uses canonical-default `suggested_canon_kind[0]` for every object; tilemap fully playable. V2 launch flips the flag; existing tilemap_view rows get L3 applied (one-time backfill cost). Schema-additive per TMP-A8.

> **Full I/O contract** — see [TMP_008b §3-§6](TMP_008b_llm_contract_spec.md): structured tool-use schema (§3), validation rules + per-case retry feedback (§4), per-object retry granularity (§5), canonical default (§6).

---

## §4 L4: LLM Regional Narration (architecture)

### 4.1 What L4 produces

Per zone, 1-2 paragraphs of ambient prose in the requested `language` + `tone`. Examples:

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

Used as **context for downstream LLM** calls (NPC dialogue, travel narration, structural-state changes). Cached aggressively (~99% read-from-cache after warm-up).

### 4.2 L4 contract summary

Detailed contract in [TMP_008b §3.3 + §4.3 + §8 + §10 + §11](TMP_008b_llm_contract_spec.md). Headline shape:

- **Input:** per-zone (terrain_kind, season, structural_state, L3 classified objects with canon_refs, delimited author_narrative_hint, book_canon excerpts capped at ~300 tokens) + style hints (closed-enum `NarrativeTone` / `NarrationLanguage` / `NarrationVoice`)
- **Mechanism:** Anthropic tool-use with `submit_zone_narrations` tool (TMP_008b §3.3); strict input_schema enforces structured output
- **Output:** per-zone `{zone_id, narration}` only — `key_phrases_for_lookup` extracted deterministically post-LLM via TF-IDF (TMP_008b §10), not LLM-emitted
- **Validation:** every input zone_id has narration; no duplicates; length bounds (50-2000 chars enforced by tool schema); language-detection check (R4); V2 World Oracle semantic check against book_canon
- **Caching:** per zone, key = `blake3(zone_id, season, structural_state, l3_classifications_digest_for_this_zone, style_hints_version, prompt_template_version)` — **includes L3 digest** so Forge:OverridePlacement on L3 correctly invalidates stale L4 narration (TMP_008b §8.2)
- **Cost:** ~4170 effective tokens per call (10 zones batched); ~$0.014/call at Haiku 4.5 rates

### 4.3 L4 cache amortization

Cache miss triggers (TMP_008b §8.2):
- New zone created (rare)
- Season changed (4×/year fictional)
- `structural_state` changed (war declared → "wartime"; war ended → "peaceful")
- L3 classifications changed (Forge:OverridePlacement; engine cascade)
- `prompt_template_version` incremented (engine ships new template)
- `style_hints_version` incremented (author adds new tone variant)
- Forge:RegenTilemap FullRebootstrap

> **Full I/O contract** — see [TMP_008b §3.3 + §4.3](TMP_008b_llm_contract_spec.md): submit_zone_narrations tool schema, validation rules, language-detection check, cache key derivation with L3-digest, deterministic key-phrase extraction.

---

## §5 Combined L3+L4 cost model

Detailed token-by-token breakdown lives in [TMP_008b §12](TMP_008b_llm_contract_spec.md). Realistic numbers (corrected from the pre-revision optimistic claim of ~3K tokens/L3 call):

| Phase | Effective tokens per call (after prompt caching) | $ per call (Haiku 4.5) | Frequency |
|---|---|---|---|
| L3 zone classification | ~6280 tokens (input ~5050 with ~1800 cached at 10% rate; output ~2850) | ~$0.018 | Once at tilemap bootstrap; once per Forge:RegenTilemap FullRebootstrap |
| L4 regional narration (per tilemap, 10 zones batched) | ~4170 tokens (input ~2700 with ~1200 cached; output ~2550) | ~$0.014 | Once at bootstrap |
| L4 narration partial cache miss (per season change; affected zones only) | ~1500-2500 tokens | ~$0.005 | ~4× per fictional year |
| L4 cache miss on Forge:OverridePlacement (L3 changed) | ~500-1500 tokens (affected zones) | ~$0.002 | Rare (author edit) |

**Per tilemap initial cost: ~$0.032** (L3 + L4 combined; was claimed ~$0.01 — actual ~3× higher but still bounded).

**Per typical reality** (1 continent + 4 country + 16 district + 64 town = 85 tilemaps):
- **Initial: ~$2.72** (one-time)
- **Per season refresh** (4×/year): ~$1/refresh × 4 = ~$4/year
- **Total Y1 (initial + 4 seasons): ~$7 per reality**

**Bounded.** Per TMP-A9, LLM cost is independent of grid size — 256×256 vs 64×64 same token count per zone. Anthropic prompt caching saves ~30-45% on the ongoing path (TMP_008b §2). Author + player opt-in via `tilemap_defaults.llm_enabled`.

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
