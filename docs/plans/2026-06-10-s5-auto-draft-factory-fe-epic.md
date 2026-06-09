# S5 — Auto-Draft Factory wizard/monitor (epic decomposition + S5a design)

> The handoff framed S5 as an FE-only slice ("backend contracts frozen"). The
> CLARIFY checkpoint (2026-06-10) UNFROZE that: PO chose **(1)** a real backend
> cost/time estimate endpoint, **(2)** a **full 6-role** Model Matrix (all
> editable, incl. embedding), **(3)** wizard ends create+launch → minimal detail.
> That turns S5 into a multi-service epic. Decomposed like S3/S4.

## PO decisions (CLARIFY 2026-06-10)
- **Estimate:** build a backend estimate endpoint (not a client-side heuristic).
- **Matrix:** all 6 roles editable — extractor, embedding, reranker, translator,
  verifier, eval-judge.
- **Launch:** wizard calls create then `/start`, navigates to a minimal detail page
  (rich monitor = S6).
- **Decompose** into S5a / S5b / S5c, each its own loom + PO checkpoint + /review-impl.
  v2.2 self-review (PO has declined AMAW on every S-slice; same here).

## Grounding (verified in code, 2026-06-10)
| Role | Per-campaign today? | Effort to make it a wizard pick |
|---|---|---|
| extractor | ✅ `campaign.knowledge_model_source/ref` → saga dispatch | none |
| translator | ✅ `campaign.translation_model_source/ref` | none |
| verifier | ❌ campaign, ✅ translation **job** accepts `verifier_model_source/ref` (fallback→translator, `v3/orchestrator.py:209`) | +2 campaign cols + saga plumb |
| eval-judge | ❌ env-var only (`learning-service/config.py:23`, `knowledge coref_judge_model`) | cross-service: +2 cols + saga/event plumb + learning-service consumer refactor |
| embedding | ❌ per **project** (`knowledge_projects.embedding_model`) | **hazard** — see constraint below |
| reranker | ❌ per **project** (`knowledge_projects.rerank_model`, S0) | +cols or inherited-display |

- **Pricing source:** provider-registry `user_models.pricing` JSONB + `billing.Estimator`
  (`internal/billing/estimate.go`) + `Repo.ModelPricing` (`internal/jobs/repo.go:359`).
  No HTTP endpoint exposes it yet — S5a adds one.
- **Gateway** proxies `/v1/campaigns/*` generically (`gateway-setup.ts`) — no gw change for `/estimate`.

## ⚠ S5b hard constraint — per-campaign embedding safety
PO chose "all 6 editable incl. embedding". Changing a project's embedding model
**invalidates its existing vector space** (passages embedded with model A aren't
searchable by model B's query vectors). S5b MUST guard: a per-campaign embedding
override is only applied to a project with **no embedded passages yet** (the
Auto-Draft Factory's primary path builds a fresh project from raw chapters — the
common case). On a project that already has passages under a different embedding
model → reject (409) or force re-embed, never silently corrupt retrieval. Same
caution (lighter) for reranker. **Do not lose this in S5b.**

## Slices
- **S5a** — cost/time estimate endpoint (DONE, `53b3d630`). FS, cross-service. No schema change.
- **S5b** — verifier + embedding/reranker per-campaign (this doc, below). FS, schema migration + cross-service (campaign + translation + knowledge).
- **S5b-eval** — translation eval-judge pipeline (NEW feature, its own loom this session). PO chose to build it now; it's not plumbing (no translation judge exists today — see below).
- **S5c** — FE wizard (multi-step) + minimal detail page. FE-only against the S5a/S5b(/eval) contracts. i18n ×4.

---

# S5b — verifier + embedding/reranker per-campaign

> CLARIFY (2026-06-10): PO chose **build eval-judge now** (→ split to S5b-eval, a new
> cross-service feature, NOT plumbing — the campaign "eval" stage is advanced *passively*
> by `translation.quality`; there is no LLM translation-judge today), **embedding override
> allowed with confirm+graph-delete**, **v2.2 + /review-impl**. This loom = the 3 ready
> editable roles: verifier (→translation) + embedding/reranker (→knowledge). Reclassified L→XL.

## Grounding (verified)
- **Verifier ~done downstream**: translation `_resolve_and_create_job` already overlays +
  persists + publishes `verifier_model_source/ref` (jobs.py:100-103,164,179) and the V3
  orchestrator resolves it with translator-fallback (`v3/orchestrator.py:209`). The job
  `CreateJobPayload` already has the fields; `translation_jobs` already has the columns.
  ⇒ only `InternalDispatchPayload` needs the 2 fields + pass-through.
- **Embedding safety is already enforced by knowledge-service**: PATCH project 422s an
  embedding change when `extraction_status != 'disabled'` (has a graph); `PUT
  /embedding-model?confirm=true` probes the dim + deletes the graph + sets the model
  (extraction.py:982). So `extraction_status == 'disabled'` is the clean "no vector space
  yet" signal — no Neo4j passage count needed.
- Campaign references an EXISTING project (`create` requires `knowledge_project_id`).

## Design
### 1. Verifier (campaign → translation)
- `campaigns += verifier_model_source TEXT, verifier_model_ref UUID` (migrate.py).
- `CreateCampaignPayload`/`Campaign` += `verifier_model_source/ref`; `_CAMPAIGN_COLS` +
  `create_campaign` INSERT += them; `_campaign_row` test fixture += them.
- `TranslationDispatchClient.dispatch_job` += `verifier_model_source/ref` (params + body);
  driver passes them from the campaign row.
- translation `InternalDispatchPayload` += `verifier_model_source/ref` → forwarded to
  `CreateJobPayload` (downstream already threads them to the provider job).

### 2. Embedding + reranker (campaign → knowledge, applied at CREATE)
Applied ONCE at campaign create (user-initiated, confirm flag in the body) — NOT in the
per-tick driver. The project is the SSOT for these; the campaign does not store them
(avoids drift). New knowledge **internal** endpoint reuses the public destructive core:
- `POST /internal/knowledge/projects/{project_id}/set-campaign-models`
  (X-Internal-Token + asserted user_id) body `{user_id, embedding_model_source/ref?,
  rerank_model_source/ref?, confirm_embedding_change}`:
  - embedding override == current → no-op.
  - embedding override != current AND `extraction_status == 'disabled'` (fresh, no graph)
    → probe dim + `set_extraction_state(embedding_model, embedding_dimension)`. No confirm.
  - embedding override != current AND has a graph → **409 `KNOW_EMBEDDING_CONFLICT`** unless
    `confirm_embedding_change` → then probe dim + `_delete_project_graph` + set
    (extraction_status stays/→'disabled'). (Destructive; PO-approved.)
  - rerank override → `ProjectsRepo.set_rerank_model` (no vector-space hazard; applied at
    query time). New tiny repo setter (no version/If-Match dance for an internal call).
  - probe failure / unsupported dim → 422 (graph left intact — probe BEFORE delete).
- `CreateCampaignPayload` += `embedding_model_source/ref`, `rerank_model_source/ref`,
  `confirm_embedding_change: bool = False` (NOT persisted on campaigns).
- `KnowledgeDispatchClient.set_campaign_models(...)` (httpx; 409 → `EmbeddingConflict` →
  campaign `create` returns **409 `CAMPAIGN_EMBEDDING_CONFLICT`**).
- campaign `create_campaign`: after ownership verify + chapter enumerate, if embedding/rerank
  overrides present → call `set_campaign_models` BEFORE the campaign INSERT (a post-patch
  insert failure leaves the project with the user's chosen model — benign; documented).

## Edge cases
| Case | Handling |
|---|---|
| verifier null | translator model used (orchestrator fallback) — no campaign col needed beyond storing null. |
| embedding == project's current | no-op (no delete). |
| embedding differs, fresh project (disabled) | set freely, no confirm. |
| embedding differs, project has a graph, no confirm | 409 `CAMPAIGN_EMBEDDING_CONFLICT`. |
| embedding differs, has graph, confirm=true | probe → delete graph → set (destructive, PO-approved). |
| embedding probe fails / bad dim | 422, graph intact. |
| rerank set | applied directly (no re-embed needed). |
| set-campaign-models OK then campaign INSERT fails | project carries the chosen model; no campaign. Benign; user retries. |

## review-impl resolution (2026-06-10)
- **#1 LOW (embedding_model_source silently ignored)** → fixed: documented on the payload that
  it's accepted for FE Model-Matrix symmetry but ignored (knowledge embedding is always BYOK
  user_model; `knowledge_projects` has no embedding-source column — only `embedding_model_ref` applies).
- **#2 LOW (accept)** — the `'disabled' == no-graph` guard reuses knowledge-service's own
  PATCH-project signal (projects.py:289); any orphan risk from a hypothetical disable-without-delete
  is pre-existing + shared, not introduced here.
- **#3 LOW (accept) `D-S5B-EMBED-CREATE-ATOMICITY`** — patch-before-insert is the safer order
  (insert-first would leave a campaign pointing at an unpatched project); the destructive-confirm +
  insert-fail window is rare and the user already opted into the rebuild.
- **#4 LOW (accept)** — `rerank_model_ref=None` = "leave unchanged"; the campaign path sets but
  cannot CLEAR a reranker (clearing stays on the project form).
- **#5 COSMETIC (accept)** — the endpoint's probe-failure / dim-unsupported branches aren't in the
  new unit tests (logic reused verbatim from the tested public `change_embedding_model`).

## Deferred
- **`D-S5B-LIVE-SMOKE`** — real 3-service: create a campaign with verifier + embedding/rerank
  → verify the translation job carries `verifier_model_ref`, the project's embedding/rerank
  are patched (fresh-set + confirm-delete paths), and a graph-conflict create 409s.
- **`D-S5B-EMBED-CREATE-ATOMICITY`** — the project patch precedes the campaign INSERT (no
  cross-service transaction); a post-patch insert failure leaves a benign project mutation.
  Acceptable for a user-initiated create; revisit if it bites.

## Test plan
- campaign: create threads verifier into the translation dispatch (driver/dispatch_client);
  create with embedding/rerank → `set_campaign_models` called; 409 conflict propagates to
  `CAMPAIGN_EMBEDDING_CONFLICT`; verifier persists on the row.
- translation: `InternalDispatchPayload` verifier fields → `CreateJobPayload` (passthrough).
- knowledge: `set-campaign-models` — fresh-set (no confirm), conflict-no-confirm-409,
  confirm-delete, rerank-only, not-found, same-model no-op.
- VERIFY: campaign pytest; translation pytest; knowledge pytest. Live-smoke deferred.

---

# S5a — Campaign cost/time estimate endpoint

> The wizard's "cost + time review" screen calls `POST /v1/campaigns/estimate`
> before launch. Honest **band** (low/high) + per-stage breakdown + rough minutes.

## Acceptance
1. **provider-registry** `POST /internal/billing/estimate` (X-Internal-Token): a pure
   **pricing oracle**. Batch of items `{label, model_source, model_ref, dimension, input_tokens, output_tokens}`
   → per-item `{label, status: ok|unpriced|not_found, estimated_usd}`. Reuses
   `Repo.ModelPricing` + the existing `textCost`/`embeddingCost`. Per-item failure
   (unpriced / model-not-found) is a soft per-item status, NOT a request error —
   one bad model never 500s the estimate.
2. **campaign-service** `POST /v1/campaigns/estimate` (JWT, owner-scoped): owns the
   **heuristics**. Verify book ownership + enumerate in-range published chapters
   (reuse `BookClient`) → size from real `byte_size` (fallback: configured
   avg) → per-stage input/output token counts → calls the oracle → assembles
   `{estimated_usd_low, estimated_usd_high, estimated_minutes_low, estimated_minutes_high,
   chapter_count, per_stage: [{stage, model_source, model_ref, status, estimated_usd}], notes}`.
3. Heuristic constants live in config (documented, tunable). The estimate is an
   **upper-leaning band**, labelled rough — never sold as exact.
4. Tests: oracle (ok/unpriced/not_found/empty); aggregator (token math, per-stage
   sum, verifier→translator fallback, null-role skip, ownership 403/404, unpriced
   passthrough). Cross-service live-smoke deferred (`D-S5A-ESTIMATE-LIVE-SMOKE`).

## Division of responsibility
**provider-registry = USD-per-token (knows pricing, not the workload).**
**campaign-service = tokens-per-workload (knows chapters/stages, not prices).**
Keeps the oracle a dumb, reusable, well-tested pricing function; all the campaign
heuristics (per-chapter size, stage→model map, output ratios, fallbacks) sit in
one testable `app/estimate.py`.

### Why explicit token counts (not raw text) cross the wire
The estimator's `EstimateUSD` walks the job's *text* to count tokens. campaign-service
has 4,000 chapters' *sizes*, not their text — fetching all text pre-flight is far too
heavy. So S5a prices **explicit token counts**: campaign-service derives tokens from
`byte_size` (`tokens ≈ bytes / est_bytes_per_token`, CJK-tuned default 3.0) and the
oracle just multiplies by the model's per-MTok price. `dimension` selects which
pricing dimension applies: `text` (input+output) or `input_only` (embedding).

## provider-registry design
- `internal/billing/estimate.go`: export thin wrappers
  `PriceText(in, out, p) (float64, error)` = `textCost`, `PriceEmbedding(in, p)` = `embeddingCost`
  (reuse the same `ErrUnpriced` + `roundUpUSD` semantics — no new math).
- `internal/api/estimate.go` (new):
  - `type modelPricer interface { ModelPricing(ctx, source string, owner, ref uuid.UUID) (billing.Pricing, bool, error) }`
    (`*jobs.Repo` already satisfies it).
  - `estimateItems(ctx, pricer, owner, items) []estimateResultItem` — pure core,
    per item: `ModelPricing` → not found ⇒ `not_found`; else `PriceText`/`PriceEmbedding`
    by `dimension` → `ErrUnpriced` ⇒ `unpriced`; else `ok` + usd.
  - `internalBillingEstimate(w, r)` — parse → resolve owner UUID → `estimateItems` → 200 JSON.
    400 on malformed body / bad owner UUID; 401 from the existing `requireInternalToken`.
- `internal/api/server.go`: `r.Post("/billing/estimate", s.internalBillingEstimate)` in the `/internal` block.

## campaign-service design
- `app/config.py`: `provider_registry_internal_url` (default `http://provider-registry-service:8084`)
  + heuristics: `est_bytes_per_token: float = 3.0`, `est_fallback_chars_per_chapter: int = 3000`,
  `est_extraction_output_per_chapter: int = 400`, `est_translation_output_ratio: float = 1.5`,
  `est_judge_output_per_chapter: int = 200`, `est_low_factor: float = 0.5`,
  `est_seconds_per_stage_call: float = 20.0`, `est_concurrency: int = 4`.
- `app/clients/book_client.py`: add `byte_size: int = 0` to `ChapterRef`; capture it in
  `list_published_chapters` (the endpoint already returns it).
- `app/clients/provider_registry_client.py` (new): `ProviderRegistryEstimateClient.estimate(owner_user_id, items) -> list[dict]`
  (httpx + `X-Internal-Token`; raises `EstimateUnavailable` on network/5xx so the
  route can 502 — an estimate is informational, fail-soft is acceptable).
- `app/estimate.py` (new, pure): `build_pricing_items(*, total_tokens, chapter_count, models, cfg) -> (items, stage_meta)`
  and `assemble_estimate(priced, stage_meta, chapter_count, cfg) -> EstimateResponse`.
  Stage→model→operation map:
  | stage | model role | dimension | input tokens | output tokens |
  |---|---|---|---|---|
  | extraction | extractor | text | source_tokens | chapter_count × extraction_output_per_chapter |
  | embedding | embedding | input_only | source_tokens | 0 |
  | translation | translator | text | source_tokens | source_tokens × translation_output_ratio |
  | verify | verifier (→translator if null) | text | source_tokens × 2 | chapter_count × judge_output_per_chapter |
  | eval | eval-judge | text | source_tokens × 2 | chapter_count × judge_output_per_chapter |
  - reranker: listed in the breakdown as `status="not_estimated"` (no token pricing
    dimension — Cohere rerank is per-search; negligible vs the LLM stages). No oracle call.
  - A null model for a role (except verifier's fallback) ⇒ that stage skipped with
    `status="not_estimated"` and a note.
  - `estimated_usd_high` = Σ ok usd; `_low` = high × est_low_factor. `unpriced`/`not_found`
    items contribute $0 to the band but are surfaced in `per_stage` + `notes` (honesty:
    the band is a floor when a model is unpriced).
  - time: `minutes_high = ceil(chapter_count × active_stage_count × seconds_per_stage_call / concurrency / 60)`; `_low` = `× est_low_factor`.
- `app/models.py`: `EstimateModelRef {model_source: str|None, model_ref: UUID|None}`,
  `EstimateRequest {book_id, chapter_from?, chapter_to?, target_language?, models: dict[str, EstimateModelRef]}`,
  `StageEstimate`, `EstimateResponse`.
- `app/routers/campaigns.py`: `POST /estimate` — declared BEFORE the `/{campaign_id}`
  param routes; verify ownership + enumerate chapters (same `BookClient` flow as create,
  single try/finally close) → sum byte_size → `est_bytes_per_token` → tokens → build items
  → oracle → assemble → 200. 403/404 mirror create; 502 `CAMPAIGN_ESTIMATE_UNAVAILABLE`
  if the oracle is unreachable.

## Edge cases
| Case | Handling |
|---|---|
| model unpriced | per-stage `status=unpriced`, $0 to band, note "X unpriced — actual cost higher". |
| model deleted / wrong owner | `status=not_found`, $0 to band, note. |
| byte_size 0/missing | fall back to `est_fallback_chars_per_chapter × est_bytes_per_token`. |
| verifier model null | fall back to translator model (matches `v3/orchestrator.py`). |
| eval-judge / reranker null | stage `not_estimated`, excluded from band + noted. |
| no chapters in range | 400 `CAMPAIGN_NO_CHAPTERS` (same as create). |
| oracle 5xx / unreachable | 502 `CAMPAIGN_ESTIMATE_UNAVAILABLE` (estimate is informational). |

## Deferred
- **`D-S5A-ESTIMATE-LIVE-SMOKE`** — real 2-service: wizard payload → campaign `/estimate`
  → provider-registry oracle prices real registered models → band returned; unpriced model
  surfaces in `notes` (unit covers the contract both sides; live exercises the HTTP hop + real pricing JSONB).
- **`D-S5A-RERANK-COST`** — rerank has no token pricing dimension today; if rerank cost
  becomes material, add a per-search/per-doc pricing dimension + estimate it.
- **`D-S5A-SUMMARY-COST`** — knowledge summary-generation LLM spend (the `D-S4-SUMMARY-ATTRIBUTION`
  hop) isn't in the stage map; fold in when that attribution lands.

## review-impl resolution (2026-06-10)
- **#1 LOW (time tied to pricing success)** → fixed: time now counts stages-with-a-model
  (the 5 LLM stages, rerank excluded) from `metas`, not oracle `status=="ok"` — an
  unpriced-but-configured stage still runs, so it counts toward time (+test).
- **#2 LOW (verify/eval input under-count, money-review direction)** → fixed: input is
  now `source_tokens + translation_output` (~2.5× source) instead of `2× source` — leans
  the cost estimate UP, the safe side for a pre-spend screen (+updated assertion).
- **#3 LOW (one bad model_source nuked the whole batch)** → fixed: `estimateItems`
  validates `model_source ∈ {user_model, platform_model}` per-item → soft `bad_request`,
  preserving the "soft per-item" invariant (the pricer's hard error no longer escapes the
  batch) (+Go test).
- **#4 LOW (accept) `D-S5A-TARGET-LANG-RATIO`** — `target_language` is accepted but the
  expansion ratio is a flat 1.5 (zh→en expands more than zh→ja). Refine per-language when
  the sampling estimator lands.
- **#5 COSMETIC (accept)** — the thin `internalBillingEstimate` parse path is untested; the
  pure `estimateItems` core + the campaign-service route both have coverage.

## Test plan
- provider-registry `estimateItems`: priced text (in+out), priced embedding (input-only),
  unpriced (nil dimension), not-found model, empty batch, bad model_source.
- campaign-service `app/estimate.py`: token→item mapping per stage; verifier fallback;
  null-role skip; band low/high; time math; unpriced/not_found passthrough into notes.
- campaign-service route: ownership 403 / book-404 / no-chapters-400 / oracle-502;
  happy path assembles per_stage + band (oracle + BookClient mocked).
- VERIFY: provider-registry `go build/vet/test ./...`; campaign-service `pytest`. Live-smoke deferred.
