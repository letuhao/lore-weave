# Plan — `D-FACTORY-EST-PROVIDER-KIND`: cloud/local badge on the estimate

**Date:** 2026-06-11 · **Branch:** feat/auto-draft-factory-gaps · **Size:** L (cross-service: provider-registry + campaign + FE)

**Goal:** the pre-launch estimate breakdown shows, per stage, whether the model runs **cloud** (paid) or **local** (self-hosted, $0). Closes the deferred half of polish #5 (the token columns shipped in `102c382e`).

## Contract change (additive, backward-compatible)
`POST /internal/billing/estimate` per-item result gains:
- `provider_kind: string` — the raw kind (`"openai"`, `"ollama"`, …); empty when not_found / bad_request.
- `is_local: bool` — server-side classification (`localProviderKinds` is the SSOT; FE never hardcodes the list).

Threaded → campaign `/estimate` `per_stage[]` → FE `StageEstimate`.

## Slices

### 1. provider-registry (Go)
- `internal/billing/default_pricing.go`: export `func IsLocalKind(kind string) bool` (`_, ok := localProviderKinds[kind]; return ok`). Keep `localProviderKinds` the single source.
- `internal/jobs/repo.go`: new `EstimateModelInfo(ctx, modelSource, owner, modelRef) (billing.Pricing, providerKind string, found bool, err error)` — ONE query returning `pricing, provider_kind` (user_models scoped to owner; platform_models global). Leaves `ModelPricing` untouched (2 other callers: jobs_handler, worker).
- `internal/api/estimate.go`: `modelPricer` interface method → `EstimateModelInfo`; `estimateResultItem` += `ProviderKind`, `IsLocal`; set both whenever the model is found (ok + unpriced); compute `IsLocal = billing.IsLocalKind(kind)`.
- `internal/api/estimate_test.go`: fake implements `EstimateModelInfo` (returns a kind); assert kind + is_local echoed for a local vs cloud item.

### 2. campaign-service (Python)
- `app/estimate.py` `assemble_estimate`: thread `result.get("provider_kind")` + `result.get("is_local")` into each `per_stage` dict (None/False for not-estimated stages with no oracle item).
- `app/models.py` `StageEstimate`: `provider_kind: Optional[str] = None`, `is_local: bool = False`.
- `app/clients/provider_registry_client.py`: docstring note (passes items through verbatim — no code change).
- `tests/test_estimate.py`: assert a priced stage carries provider_kind + is_local from the (mocked) oracle item; a not-estimated stage has `provider_kind=None, is_local=False`.

### 3. FE (TS)
- `types.ts` `StageEstimate`: `provider_kind: string | null`, `is_local: boolean`.
- `components/steps/ReviewStep.tsx`: a small badge column/inline pill — `🖥 local · free` (is_local) vs `☁ {provider_kind}` (cloud); nothing for empty kind.

## Verify
- provider-registry `go build ./... && go test ./internal/...`
- campaign `pytest tests/test_estimate.py tests/test_campaigns_api.py`
- FE `tsc --noEmit` + `vitest run src/features/campaigns`
- Cross-service (3 services) → **live-smoke**: real `/estimate` against the stack with a local + a cloud model → assert `is_local` flips. Defer with a token if the stack isn't bootable.

## Out of scope / deferred
- An `openai`-kind model pointed at a custom local base_url is reported `is_local=false` (can't detect from kind alone — same caveat as `DefaultPricing`). Documented, not fixed.
