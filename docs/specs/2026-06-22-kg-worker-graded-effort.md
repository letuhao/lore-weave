# D-KG-WORKER-GRADED-EFFORT — worker-ai honors the stored extraction effort (DETAIL DESIGN)

Status: **DETAIL DESIGN — ready to build** · 2026-06-22 · follow-up to Wave 4 (`14d13b89`)
The analog of translation's `D-RE-WORKER-GRADED-EFFORT` (cleared in Wave 1). Wave 4 made
knowledge-service CLAMP + STORE `extraction_jobs.reasoning_effort` (+ `wiki_gen_jobs`); this
makes the runner that actually executes the job APPLY that effort to the LLM call.

## Problem
`kg_build_graph` clamps + stores `reasoning_effort` on the knowledge `extraction_jobs` row, but
**worker-ai never reads it** and passes **no** reasoning/thinking control to its Pass-2
extraction LLM calls — so the stored effort is inert. Goal: read it off the job and inject the
same wire fields translation uses (`reasoning_effort` + `chat_template_kwargs`).

## The crux (why it's M, not S)
The LLM `input` dicts are **NOT built in worker-ai** — they're built inside the
`loreweave_extraction` SDK extractors (`build_entity_submit_kwargs`, relation/event/fact), and
**none spread `reasoning_fields`**. The job object is not in scope there. So the effort must be
threaded **through the SDK**, and `extract_pass2` + those builders are a **shared contract** also
imported by translation-service + knowledge-service → the param must be **optional, default
`"none"`** so existing callers stay byte-identical (the SDK already does this for `schema=None`/
`targets=None`).

`loreweave_llm.reasoning.reasoning_fields(ReasoningDirective(effort, passthrough=False,
source="user"))` is already available + exported (worker-ai depends on the SDK). worker-ai does
NO model-capability dispatch, so — exactly like translation — use a **direct `source="user"`
directive**, not `resolve_reasoning`.

## Exact seams

### Layer 1 — `loreweave_extraction` SDK (the real work)
1. `pass2.py` `extract_pass2(...)` (~L117): add `reasoning_effort: str = "none"` param; thread it
   into every `build_*_submit_kwargs` call.
2. The 4 builders — spread the wire fields into the `input` dict:
   - `extractors/entity.py` `build_entity_submit_kwargs` (input dict ~L296-313)
   - `extractors/relation.py` (~L299), `extractors/event.py`, `extractors/fact.py`
   - each: `**reasoning_fields(ReasoningDirective(effort=reasoning_effort, passthrough=False, source="user"))`
3. Decoupled submit builders `decoupled_extract.py` `assemble_entity_submit` /
   `assemble_trio_submits` (~L309-360): accept + forward the same param (they call the same
   builders).
4. SDK export already has `reasoning_fields`/`ReasoningDirective`; no new dep.

### Layer 2 — worker-ai (`services/worker-ai/app/runner.py`)
5. `_get_running_jobs` SELECT (~L685-699): add `reasoning_effort` to the column list.
6. `JobRow` dataclass (~L535-593): add `reasoning_effort: str = "none"`.
7. `JobRow(...)` builder (~L712-740): populate `reasoning_effort=row["reasoning_effort"]`.
8. **Sync path:** `_extract_and_persist` → `extract_pass2(...)` call (~L1354): pass
   `reasoning_effort=job.reasoning_effort`.
9. **Decoupled path:** `_start_decoupled_chunk` (~L1453-1547): stash `reasoning_effort` into the
   `resume_state` JSONB alongside `model_ref` so `llm_extract_consumer.py` rebuilds the submits
   with the SAME effort on resume — **missing it here silently drops effort for the decoupled
   flow** (the harder half).

## Decisions
- **D1 — hardcoded `chat_template_kwargs`** in `entity_recovery.py:236` + `pass2_filter.py:302`
  currently force `thinking:False`. Recommend **leave them force-off** (recovery + precision
  filter are cheap structural passes that shouldn't burn thinking tokens); graded effort drives
  only the core entity/relation/event/fact extraction. Document the carve-out.
- **D2 — no clamp in worker-ai.** The effort on the row is ALREADY clamped (mint, knowledge-side);
  worker-ai trusts the stored value (the runner is single-purpose + trusted, like its other job
  fields). No re-clamp.
- **D3 — wiki path** (`wiki_gen_jobs.reasoning_effort`): out of scope here — the wiki-gen worker
  is a separate call path. Track as `D-KG-WIKI-WORKER-GRADED-EFFORT` if wanted (W4 stored it; the
  wiki worker honoring it is a tiny symmetric follow-up).

## Size + risks
- **SIZE: M.** One new behavior (effort→wire) fanning across ~4 SDK builders + 2 worker-ai paths
  + the JobRow plumbing, crossing a shared SDK contract (translation + knowledge import it). Write
  a plan file; the SDK contract change is the load-bearing care-point.
- **Risks:** (a) shared-SDK back-compat — param optional/default none, assert translation +
  knowledge callers unchanged; (b) decoupled `resume_state` must carry the effort or it's dropped
  on the async/resume path; (c) the SDK-distribution split (D-SDK-DISTRIBUTION-SPLIT was resolved,
  but re-verify `loreweave_extraction` resolves to THIS repo at build for the new param).

## Test plan
- SDK unit: `extract_pass2(reasoning_effort="high")` → each builder's `input` carries
  `reasoning_effort:"high"` + `chat_template_kwargs.thinking:True`; default `"none"` → off.
- worker-ai unit: a `JobRow` with `reasoning_effort="high"` reaches `extract_pass2` (sync) AND is
  serialized into `resume_state` (decoupled).
- Back-compat: existing translation/knowledge SDK callers (no param) unchanged.
- Live smoke (≥2 services): a `kg_build_graph` (high) → worker-ai runs → the gateway chat-job
  input carries the reasoning fields.

## The other two branch deferrals (already detail-designed — for completeness)
- **D-EXTRACTION-REHOME-KNOWLEDGE** — designed in `docs/plans/2026-06-22-extraction-branch-deferral-clearing.md`
  (co-located worker move, NOT an HTTP cache-proxy); **blocked on `world-core-foundation`**.
- **D-GLOSSARY-MULTIROW-ATTR-VALUES** — designed in the same plan doc (child `entity_attribute_value_items`
  table + write-synced `original_value` cache + Go backfill + writers-first cutover); a glossary
  schema epic, own spec/branch.

**Conclusion:** these 3 are the complete open set for the extraction branch. With this doc, all
three now have a detail design — nothing else on this branch needs one.
