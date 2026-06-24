# C27 live-smoke — delta flywheel closes

**Token:** `live smoke: approve dị bản chapter → delta enriches next-scene grounding`

## Setup
- Rebuilt + restarted `composition-service` (:8217) + `knowledge-service` (:8216) — both `/health`=200.
- Genderbend derivative Work `019ec734-3f0d-7c37-b777-ab6112a68fdd` (is_derivative=true, branch_point=3),
  source work `019ec5f4-…` → source/base knowledge project `019eb683-8de9-…`, book `019eb60e-…`.
- Baseline: derivative delta partition `019ec734` had **0** :Entity nodes in Neo4j.

## 1. Approve a dị bản chapter → extraction into the DERIVATIVE's OWN project (delta, G2)
`POST /v1/composition/works/019ec734-…/chapters/019eb60f-3c30-… (ch4, sort_order 4 > branch 3)/approve`
with `model_ref=019eb620-… (qwen2.5-7b-instruct)`:

```json
{"dispatched":true,"reason":"delta_dispatch",
 "project_id":"019ec734-3f0d-7c37-b777-ab6112a68fdd",
 "source_project_id":"019eb683-8de9-7cc4-8aec-e120166cfffd",
 "extraction":{"entities_merged":30,"relations_created":11,"events_merged":46,
               "facts_merged":3,"evidence_edges":79,"duration_seconds":120.38}}
```

- Extraction targeted the **derivative's OWN project_id** `019ec734` (the DELTA), NOT the source `019eb683`.
- Neo4j after: delta partition `019ec734` → **30 :Entity + 55 :Event** (was 0). COW held: the source/canon
  partition `019eb683` (its own 55 entities) was **NOT** written by the flywheel.

## 2. Flywheel CLOSES — next scene's pack reflects the new delta facts (reconcile-by-truth)
`GET /v1/composition/works/019ec734-…/scenes/019ec75a-353e-… (ch5, story_order 50)/grounding`:
- delta-fact `云儿` (侍女云儿, established in ch4) **in grounding: True**
- delta-fact `九天明帝经` (the cultivation art, established in ch4) **in grounding: True**
- Composition logs (reconcile-by-truth — the packer's OWN C25 delta-read path):
  `GET …/v1/knowledge/timeline?project_id=019ec734-…&before_order=5000000 → 200`
  `GET …/v1/knowledge/drawers/search?project_id=019ec734-… → 200`
  i.e. the new delta facts surfaced through the SAME C25 delta-read predicate, not a parallel query.

## Live-smoke bug caught + fixed
The first approve returned `knowledge_unavailable` — the composition KnowledgeClient's 5s read-lens
timeout silently aborted the (slow) Pass-2 LLM extract-item call. Fixed: `extract_item` now uses an explicit
180s per-request timeout (LLM extraction is slow). Rebuilt → the re-run extracted 30 entities into the delta.

## Result
`dispatched=true` into the DERIVATIVE's delta partition (never the source/null), the delta went 0→30
entities, and the next scene's grounding pack reflected the new delta facts via the C25 read path — the
flywheel closes.
