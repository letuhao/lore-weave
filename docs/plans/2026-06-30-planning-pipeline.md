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
  + parents + brother; CH1 S4 = Lâm Uyển + Cửu U Ma Cơ) — the grounding loop is proven: propose_cast →
  seed → roster → scene presence. Bonus: CH1 spread to 4 scenes (less telescoped). ⇒ grounded drafting
  (the packer pulls present entities' KG state) is unblocked.

### Stage 1 — Motif selection  *(make the theme explicit)*
- **Reuse:** `composition_motif_search` / `MotifRetriever` / `motif_select` (all built, W2).
- **New:** a discrete "select motifs for this premise/arc" step + a human approve/swap checkpoint; carry
  the bound motifs forward.
- **POC:** premise → N selected library motifs (xấu→hoàn mỹ, ma công phản phệ…) shown for approval.

### Stage 2 — Arc & beat shaping (deliberate tension curve)
- **Reuse:** structure templates + `arc_apply`/`arc_materialize` (arc-scale decompose) + L1 beat-map.
- **New:** a tension-curve / beat-budget intent so CH1 doesn't telescope to 100 (the review defect).
- **POC:** one arc, beats with a sane rising curve.

### Stage 3 — Character arcs + introduction schedule  *(the second missing piece)*
- **New:** per-main-character trajectory across the beats; decide WHERE each new character is introduced
  (named, flagged for glossary add). `succession_entailment` can check the causal legality of the ordering.
- **POC:** each main char's arc + the introduction points for new figures.

### Stage 4 — Grounded scene decomposition
- **Reuse:** `decompose` L2 + the cross-chapter threading (already shipped).
- **New:** feed present-cast (from stage 3), new-char introductions, bound motifs, and the tension budget
  INTO L2 → populate `present_entity_ids`, motif refs, introduction markers.
- **POC:** ~40 scenes with REAL present cast + introductions + motif tags + a sane tension curve.

### Stage 5 — Plan self-heal  *(reuse the judge→satellite→splice pattern + the idle judges)*
- **Reuse:** `engine/self_heal.py` pattern (locate/splice are generic); adapt `promise_audit`
  (setup-without-payoff), `succession_entailment` (causal break), `arc_conformance` (structure),
  `motif_conformance` (motif coverage) judge-logic to read the OUTLINE instead of prose.
- **New:** a plan-judge that returns located plan-findings + a plan-satellite-edit (edit one scene synopsis).
- **POC:** the plan-judge flags real plan holes (pacing, unplanned character, unused motif, dangling setup)
  → satellite-fixes the offending synopsis → re-judge.

### Stage 6 — Orchestration + human checkpoints
- Chain 0–5; checkpoints **blocking** at 1, 2, 4 (motif / cast / arc shape — wait for approval),
  **advisory** at 3, 5, 6, 7 (proceed, human edits after). The LLM proposes at every step (autonomous,
  tool-using); the human directs.

## Sequencing & rationale
Start with **Stage 0** — empty cast is the root that starves every later step (motif binding, presence,
introductions, grounded drafting). Then 1 → 2 → 3 → 4 (each POC-validated, PO checkpoint), then 5
(plan self-heal) once a grounded plan exists to heal, then 6 wires the human-in-the-loop. One arc
throughout. Only after the plan reads well do we proceed to draft (the existing draft → chapter
self-heal pipeline).

## Out of scope (consciously)
No GUI yet (M0–M5 stay paused); no multi-arc; no new judge engines (we re-target existing ones); the
draft/chapter-self-heal pipeline is already proven and unchanged.
