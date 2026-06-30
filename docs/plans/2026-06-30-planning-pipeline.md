# Build Plan — Multi-step Planning Pipeline (decompose-and-refine)

> **Date:** 2026-06-30 · **Spec:** [`../specs/2026-06-30-planning-pipeline-architecture.md`](../specs/2026-06-30-planning-pipeline-architecture.md)
> · **Mode:** staged, validate-first (POC each stage before the next) · **Scope:** ONE arc.
> **Goal:** replace the one-shot `decompose` with an N-step authorial planning process that REUSES the
> ~30 existing composition engines (today planning touches ~2 of them).

## Capability audit — what we already have (the PO's "đã khai thác hết chưa?")

**Verdict: NO.** Planning currently uses `plan.decompose` (L1 beat-map + L2 scenes) and nothing else.
The composition service has ~30 engines; most are unused at plan time, and a whole **judge constellation**
sits idle until after prose exists.

| Group | Engines | Used at plan time? | Reuse for planning step |
|---|---|---|---|
| **Plan** | `plan` (decompose L1/L2), `adaptive_k` | ✅ (the only one) | step 6 (scene decompose) |
| **Arc** | `arc_apply`, `arc_materialize`, `arc_conformance`, `arc_conformance_orchestrate` | ❌ | **step 4** (arc-scale decompose from a template — `arc_apply` literally is "decompose at arc scale") + **step 7** (arc_conformance = structural plan check) |
| **Motif** | `motif_select`, `motif_embed`, `motif_mine`, `motif_deconstruct`, `motif_conformance`, `motif_conformance_*`, `succession_entailment` | ❌ | **step 1** (select/search), **step 5** (`succession_entailment` = does motif A's effects entail B's preconditions = causal continuity), **step 7** (`motif_conformance`) |
| **Promise / thread** | `narrative_thread`, `promise_audit` | ❌ (post-prose only) | **step 7** (setup→payoff / dropped-promise audit, adapted to synopses) |
| **Quality / canon** | `critic`, `critic_override`, `canon_check`, `canon_reflect`, `eval_judge` | ❌ (post-prose) | **step 7** (plan-judge logic), checkpoints |
| **Assembly / draft** | `assembly`, `chapter_gen`, `cowrite`, `stitch`, `select`, `compress`, `self_heal` | n/a (draft stage) | `self_heal` = the judge→satellite→splice PATTERN reused for **step 7** |
| **Glossary (sibling svc)** | entity CRUD + `/internal/.../extract-entities` bulk | ❌ at plan time | **step 2** (seed proposed cast), **step 3** (world/lore) |

⇒ The biggest unexploited surface is the **judge constellation** (promise_audit, succession_entailment,
arc_conformance, motif_conformance, critic) — exactly what **step 7 (plan self-heal)** needs. We don't
build new judges; we re-target existing ones from "post-prose verification" to "plan verification."

## Staged build (each stage: reuse → new → POC-validate, then PO checkpoint)

### Stage 0 — Cast & World seeding  *(biggest hole; unblocks grounding for ALL later steps)*
- **Reuse:** glossary entity-create + the bulk `extract-entities` API; the premise already names the cast.
- **New:** a `propose_cast` LLM step — extract the named cast from the premise + propose roles / traits /
  relationships + the supporting cast the arc needs → **seed into the glossary**; a lighter `propose_world`
  (sects, realms, locations, factions) → glossary/lore.
- **POC:** run on the Lâm Uyển premise → glossary holds the named cast (Lâm Uyển, Lâm Chấn Nhạc, …) +
  roles BEFORE planning ⇒ `_cast_roster` is non-empty ⇒ scene presence can populate.
- **STATUS — `propose_cast` validated 2026-06-30** (`engine/cast_plan.py`, 6 unit tests). Live on the
  Lâm Uyển premise: **10 cast = 6 named (extracted) + 4 NEW (proposed)** — the 4 invented supporting
  cast (Mộ Dung Tuyết foil, Hắc Sát/Tử Yên Nhi allies, Diệp Phàm rival) fill the exact gap the plan
  review found (anonymous new figures), with proper Hán-Việt names + role/archetype/traits/relationships.
  Fixed an intermittent truncation (cast JSON is verbose → `max_tokens` 2000→4000 + a salvage-truncated-
  array parse).
- **STATUS — Stage 0 CLOSED end-to-end 2026-06-30.** Added `GlossaryClient.seed_entities` (bulk
  write-through via `/internal/.../extract-entities`; needs the book ontology adopted first —
  `GLOSS_BOOK_NOT_SCAFFOLDED` otherwise). Seeded the 10-cast into the POC book's glossary (all created),
  then re-ran the threaded decompose: **39/39 scenes now carry `present_entity_ids`** (CH1 S1 = Lâm Uyển
  + parents + brother; CH1 S4 = Lâm Uyển + Cửu U Ma Cơ) — the presence loop is proven: propose_cast →
  seed → roster → scene presence. Bonus: CH1 spread to 4 scenes (less telescoped).
- **⚠ review-impl correction — PRESENCE unblocked, DEPTH not yet.** `seed_entities` persists only
  `{kind_code, name}` (the extract-entities decoder is strict — attributes/evidence → 422). So the
  glossary entities are **hollow** (name + an auto `"character: <name>"` desc); the role/archetype/
  traits/relationships `propose_cast` produced are **dropped**. Scene presence works, but grounded
  drafting can't ground on character DEPTH yet. **D-PLAN-CAST-ATTRS (deferred, next stage):** persist the
  cast's traits/role/relationships as glossary attributes/canon (needs attr_def mapping — extract-entities
  no-ops on unmatched attr codes; the canon-content/enrichment endpoints are per-entity). Fixed now:
  `is_new` string-coercion (`bool("false")` was True), + unit tests for `seed_entities` payload and the
  coercion.

### Stage 1 — Motif selection  *(make the theme explicit)*
- **Reuse:** `composition_motif_search` / `MotifRetriever` / `motif_select` (all built, W2).
- **New:** a discrete "select motifs for this premise/arc" step + a human approve/swap checkpoint; carry
  the bound motifs forward.
- **POC:** premise → N selected library motifs (xấu→hoàn mỹ, ma công phản phệ…) shown for approval.
- **STATUS — `select_arc_motifs` validated 2026-06-30** (`engine/motif_plan.py`, 5 unit tests). Reuses
  `MotifRetriever.retrieve` with NO beat/query (the degrade path = full in-genre pool, no min-score
  floor) → the LLM picks BY CODE (drops invented/unknown codes). Live on the Lâm Uyển premise: **4 arc
  motifs with distributed roles** — Kỳ-Ngộ→Truyền-Thừa (central spine), Xấu-hóa-mỹ (recurring), Ma-công-
  phản-phệ (foil), Phục-thù (climax payoff). Turns `motif_coverage={}` into a deliberate thematic
  structure. **Next-stage integration:** feed the selected motifs into the scene decompose (Stage 4) as
  thematic guidance + the arc-role placement.

### Stage 2 — Arc & beat shaping (deliberate tension curve)
- **Reuse:** structure templates + `arc_apply`/`arc_materialize` (arc-scale decompose) + L1 beat-map.
- **New:** a tension-curve / beat-budget intent so CH1 doesn't telescope to 100 (the review defect).
- **POC:** one arc, beats with a sane rising curve.
- **STATUS — `shape_tension_curve` validated 2026-06-30** (`engine/arc_plan.py`, 5 unit tests). DETERMINISTIC
  (pure, no LLM): beat-role → (base, peak) band; consecutive same-role chapters ramp base→peak. On the
  POC's 12-ch beats it turns the chaotic free-run (`95,95,85,65,85,85,0,100,100,100,100,95` — ch1
  telescoped to 95, flat 100-plateau, no resolution drop) into a textbook rising arc
  `45,65,35,58,55,68,82,66,90,88,100,52` — **ch1 capped at 45, 100 ONLY at the climax, resolution drops
  to 52**. Directly fixes the review's "ch1 telescopes to 100" + "limited dynamic range" defects.
  **Next-stage integration:** feed `tension_target` into the L2 decompose so scenes aim for the band.

### Stage 3 — Character arcs + introduction schedule  *(the second missing piece)*
- **New:** per-main-character trajectory across the beats; decide WHERE each new character is introduced
  (named, flagged for glossary add). `succession_entailment` can check the causal legality of the ordering.
- **POC:** each main char's arc + the introduction points for new figures.
- **STATUS — `plan_character_arcs` validated 2026-06-30** (`engine/character_plan.py`, 4 unit tests).
  Given the cast (Stage 0, `is_new`) + the beat sequence, the LLM emits each character's ARC + an
  `introduce_at_chapter` (parse maps by name — drops invented names; clamps the chapter to range; carries
  role through). Live (chained Stage 0→3 on the Lâm Uyển premise): MC + family "from start"; **scheduled
  introductions at fitting beats** — Cửu U Ma Cơ (mentor) @ch2, an ally @ch4, Thanh Vân Tông @ch5, a foil
  @ch7, an assassin @ch9, a final mentor @ch10. Fixes the "anonymous new characters" defect (names + arcs
  + entry points). Gemma even scheduled premise-named entities sensibly (Ma Cơ @ch2, not ch1).
  **Next-stage integration:** the decompose stages each new character's introduction at its chapter.

### Stage 4 — Grounded scene decomposition
- **Reuse:** `decompose` L2 + the cross-chapter threading (already shipped).
- **New:** feed present-cast (from stage 3), new-char introductions, bound motifs, and the tension budget
  INTO L2 → populate `present_entity_ids`, motif refs, introduction markers.
- **POC:** ~40 scenes with REAL present cast + introductions + motif tags + a sane tension curve.
- **STATUS — `grounded_decompose` validated 2026-06-30** (`engine/grounded_plan.py` + grounding block in
  `build_scene_decompose_messages`, 6 unit tests). Feeds all of Stages 0-3 into the threaded L2:
  `motifs_for_beat` (emphasise motifs by arc-role × beat), `intros_by_chapter` (stage each new character
  at its chapter), the tension target per chapter, + cross-chapter threading. Skips L1 when chapters
  arrive pre-mapped (the pipeline runs L1 once). **Live full Stage 0→4 on the Lâm Uyển premise: 12 ch / 34
  scenes, 34/34 with present cast**; tensions follow the deliberate band (CH1 = 35,45 — NOT 100; CH3
  establishment dips to 30,35); **Cửu U Ma Cơ introduced @ch2 per the schedule** (+ the rest at their
  planned chapters); motifs woven; "Tiếp nối từ…" threading intact. The cumulative payoff vs the original
  generic plan (ch1=95-100, no cast, anonymous chars). **Next-stage:** plan self-heal (Stage 5).

### Stage 5 — Plan self-heal  *(reuse the judge→satellite→splice pattern + the idle judges)*
- **Reuse:** `engine/self_heal.py` pattern (locate/splice are generic); adapt `promise_audit`
  (setup-without-payoff), `succession_entailment` (causal break), `arc_conformance` (structure),
  `motif_conformance` (motif coverage) judge-logic to read the OUTLINE instead of prose.
- **New:** a plan-judge that returns located plan-findings + a plan-satellite-edit (edit one scene synopsis).
- **POC:** the plan-judge flags real plan holes (pacing, unplanned character, unused motif, dangling setup)
  → satellite-fixes the offending synopsis → re-judge.
- **STATUS — `run_plan_self_heal` built 2026-06-30** (`engine/plan_heal.py`, 5 unit tests). The chapter
  self-heal pattern (judge→locate→satellite→splice) applied to the PLAN — simpler because scenes are
  discrete + INDEX-addressable: the plan-judge points at a scene by `(chapter, scene)` (no fuzzy locate),
  each flagged scene's synopsis is satellite-edited in isolation (+ neighbor context) and written back.
  Advisory + degrade-safe (skip out-of-range address / runaway expansion / judge fail). **Live POC folds
  into the Stage 6 full-pipeline run.**

### Stage 6 — Orchestration + human checkpoints
- Chain 0–5; checkpoints **blocking** at 1, 2, 4 (motif / cast / arc shape — wait for approval),
  **advisory** at 3, 5, 6, 7 (proceed, human edits after). The LLM proposes at every step (autonomous,
  tool-using); the human directs.
- **STATUS — `run_planning_pipeline` built 2026-06-30** (`engine/planning_pipeline.py`, 1 orchestrator
  unit test). Chains 0→1→L1(once)→3→4→5 end-to-end: Stage 0 propose→seed→roster (joins cast to entity-ids
  by name), Stage 1 motifs, L1 beat-map ONCE (feeds both Stage 3 char-arcs and Stage 4), Stage 4 grounded
  decompose (pre-mapped ⇒ skips its own L1), Stage 5 plan self-heal. Returns the healed plan + all
  intermediates (cast / motifs / arcs / heal report) so a UI can checkpoint between stages; end-to-end for
  the autonomous path. Each stage degrades independently (never hard-fails). Live full Stage 0→5 POC
  running.

## Sequencing & rationale
Start with **Stage 0** — empty cast is the root that starves every later step (motif binding, presence,
introductions, grounded drafting). Then 1 → 2 → 3 → 4 (each POC-validated, PO checkpoint), then 5
(plan self-heal) once a grounded plan exists to heal, then 6 wires the human-in-the-loop. One arc
throughout. Only after the plan reads well do we proceed to draft (the existing draft → chapter
self-heal pipeline).

## Out of scope (consciously)
No GUI yet (M0–M5 stay paused); no multi-arc; no new judge engines (we re-target existing ones); the
draft/chapter-self-heal pipeline is already proven and unchanged.
