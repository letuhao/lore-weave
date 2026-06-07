# Plan — E5B-integrate: wire the cross-encoder reranker into raw-search

Branch `raw-search/foundation` · **XL** · v2.2 · routes via **provider-registry** (PO choice, mirrors embed). Guide: [rerank integration](../integrations/2026-06-08-rerank-service-integration.md). Reranker proven (full golden set: positives median 0.86 vs negatives max 0.29; floor 0.30 → 5/5 negatives rejected, 0 genuine positives lost).

## Routing decision
Reranker is a **single platform service** (not per-user BYOK) → provider-registry holds `RERANK_URL` + `RERANK_SERVICE_TOKEN` in **config** and proxies; no DB credential / encryption. Still through the gateway (honors the invariant). knowledge → provider-registry `/internal/rerank` (same base+token as `/internal/embed`).

## BUILD

### PR1 — provider-registry (Go)
- `internal/config/config.go`: `+RerankURL, RerankServiceToken, RerankModel` (env `RERANK_URL`, `RERANK_SERVICE_TOKEN`, `RERANK_MODEL` default `bge-reranker-v2-m3`). All optional — empty `RerankURL` ⇒ rerank disabled.
- `internal/provider/rerank.go`: `RerankResult{Index int; Score float64}`; `Rerank(ctx, client, baseURL, token, model, query, docs) ([]RerankResult, error)` → `POST {trimV1(base)}/v1/rerank` (Bearer token) `{model,query,documents}` → parse `{results:[{index,relevance_score}]}` sorted desc. Errors mapped like embed.
- `internal/api/server.go`: `internalRerank` handler — validate `{query, documents}`; `RerankURL==""` ⇒ 503 `RERANK_UNAVAILABLE`; `model` from body or `cfg.RerankModel`; call `provider.Rerank(s.invokeClient, …)`; return `{model, results}`. Register `r.Post("/rerank", s.internalRerank)` under `/internal`.
- `internal/provider/rerank_test.go` + handler test (httptest rerank stub).

### K1 — knowledge client (Python)
- `app/clients/reranker_client.py`: `RerankerClient.rerank(query, documents) -> list[dict]|None` → POST `{provider_registry_internal_url}/internal/rerank` (X-Internal-Token) `{model, query, documents}`; degrade to `None` on any failure. `init/get_reranker_client` singleton (mirror embedding_client).
- `app/config.py`: `+rerank_enabled=True, rerank_model="bge-reranker-v2-m3", rerank_top_n=30, min_rerank_score=0.30, rerank_timeout_s`.
- `app/deps.py`: `get_reranker_client`.

### K2 — orchestrator (`app/routers/public/raw_search.py`)
- Params `+rerank: bool = True`, `+min_rerank_score: float = MIN_RERANK_SCORE`.
- After `rrf_fuse` (before floor/cap), when `mode in {semantic,hybrid}` and `rerank` and `settings.rerank_enabled`:
  1. `cand = fused[:rerank_top_n]`; `docs = [h.snippet for h in cand]`.
  2. `scores = reranker.rerank(q, docs)`; if `None` → `degraded["rerank"]="unavailable"`, skip (keep RRF order).
  3. else: set each cand `relevance = rerank_score`, **re-sort by rerank score desc**, drop `relevance < min_rerank_score`.
- Then existing `cap_per_chapter` + `[:limit]`. (`min_relevance` E5 floor still applies; rerank replaces the semantic-cosine relevance.)
- Tests (`tests/unit/test_raw_search_api.py`): rerank reorders + sets relevance; floor drops below-threshold; reranker-None degrades (keeps fusion, `degraded.rerank`); lexical mode unchanged (no rerank call).

### CFG — `infra/docker-compose.yml`
- provider-registry env `+RERANK_URL=http://host.docker.internal:28417`, `+RERANK_SERVICE_TOKEN=change-me`, `+RERANK_MODEL=bge-reranker-v2-m3`. (provider-registry already reaches host.docker.internal for embeddings.)

### E — `scripts/run_rawsearch_eval.py`
- `--rerank/--no-rerank` (default on) + `--min-rerank-score`; thread to `search()`; report negatives-rejected + per-mode metrics.

## VERIFY (≥2 services → live-smoke)
- `go test ./internal/...` (provider-registry); knowledge `pytest`.
- Rebuild provider-registry + knowledge; confirm reranker reachable.
- Live: `run_rawsearch_eval.py --rerank` → **negatives return 0 results**; hybrid MRR/ndcg@10 ≥ E5 baseline; reranker-down (stop service or bad URL) degrades, no 500. Evidence string with the numbers.

## REVIEW(code) 2-stage → QC → POST-REVIEW (STOP; suggest /review-impl — new service contract + external dep) → SESSION → COMMIT → RETRO.
Deferred after: E6 FE (relevance/rerank display + toggles); EVAL-CI; warm-latency benchmark under load.
