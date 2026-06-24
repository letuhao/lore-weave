# S5 — Web-search / deep-research for the glossary assistant

**Status:** DESIGN (2026-06-21) · **Size:** XL (net-new subsystem) · scenario S5 (+ S16 evidence, S20 async, S21 cost-gate, S24/INV-6 injection)
**Branch:** `feat/glossary-assistant-coverage`

## 1. Goal

Scenario S5: *"tra cứu thêm về nhân vật này và bổ sung mô tả có dẫn nguồn"* — the assistant runs a
web-search / deep-research pass on an entity, proposes an enriched `short_description`, and attaches
the fetched **source URLs as evidence**, which the human reviews + approves.

Today: **entirely missing.** No web-search anywhere (grep-clean of Tavily/Perplexity/Bing/SerpAPI).
`knowledge.memory_search` is internal project memory only.

## 2. Invariants this MUST honor (non-negotiable)

| Invariant | Consequence for S5 |
|---|---|
| **Provider-gateway (ENFORCED)** | the outward web-search HTTP call lives ONLY in `provider-registry-service`. No consuming service imports a search SDK or holds a `*_URL`/`*_KEY` for it. |
| **Local/self-hosted ≠ exception (BYOK)** | the web-search provider is a **BYOK provider-registry credential** (`provider_credentials.kind='web_search'` + `endpoint_base_url` + `secret_ciphertext`) resolved via `user_models` (`capability_flags {"web_search": true}`). NO per-service env for it. |
| **No hardcoded model names** | the search model/endpoint resolve from provider-registry, never literal in runtime code. |
| **MCP-first (agentic logic)** | the deep-research agent capability is an **MCP tool through ai-gateway**, on the owning domain service (glossary). Not a bespoke HTTP+raw-prompt endpoint. |
| **S21 cost gate** | research is paid + outward-facing → **class-C confirm** with a cost estimate before any outward call. |
| **INV-6 / S24 injection** | fetched web text is **hostile DATA**, never instructions. Neutralized before it touches a prompt or lands as evidence. |
| **Tenancy** | every write binds to `claims.BookID`; the entity-in-book guard holds; the user's OWN web_search credential is used (caller-pays). |

## 3. Architecture (3 layers, mirrors embed/rerank BYOK)

```
chat (LLM) --MCP--> ai-gateway --federates--> glossary-service
   glossary_deep_research  (class-C: estimate -> mint confirm token)
   glossary_confirm_action (human Apply) -> effect:
        -> provider-registry  POST /internal/web-search   (BYOK web_search model)
              -> WebSearch adapter (Tavily-shaped) -> outward HTTPS  [ONLY here]
        -> neutralize + summarize results (user's LLM via provider-registry, INV-6)
        -> propose short_description edit  +  attach source URLs as EVIDENCE (draft)
```

### 3a. provider-registry-service — the web_search capability (BE foundation, slice 1)
- **Adapter** `internal/provider/web_search.go` — `WebSearch(ctx, client, baseURL, token, query, opts) ([]WebSearchResult, error)`.
  Tavily-shaped request (`POST {base}/search` `{query, max_results, search_depth, include_answer}`),
  parses `{results:[{title,url,content,score}], answer}`. Receives **resolved** baseURL/token (no SDK,
  no config) — same shape as `Rerank(...)`.
- **Capability** `web_search` — a new `capability_flags` value (JSONB, **no migration** — the column is
  free-form; `capability_filter` already treats unknown flags strictly like `embedding`). The
  `web_search` capability is strict (must be explicitly flagged; never defaulted from `{}`).
- **Internal route** `POST /internal/web-search` (internal-token gated, like `/internal/embed`):
  body `{owner_user_id, query, max_results?, search_depth?}` → resolve the owner's active
  `web_search` user_model JOIN provider_credentials → decrypt secret → call the adapter →
  `{provider, results:[{title,url,content,score}]}`. Meters usage (per-search pricing from
  `user_models.pricing`, like rerank/embed).
- **Tests:** adapter parse (mock HTTP), resolution (seed cred+model, capability filter excludes
  non-web_search), strict-capability (undeclared `{}` is NOT web_search-eligible), no-model→clear 4xx.

### 3b. glossary-service — `glossary_deep_research` MCP tool (slice 2)
- **Class-C, cost-gated.** Input `{book_id, entity_id, query, max_results?, target_language?}`.
  Edit-grant gated; entity-in-book guarded. Mint phase: estimate cost (n searches × the user's
  web_search price + a summarize-LLM token estimate) → mint a `deep_research` confirm descriptor
  (binds `entity_id` to `claims.BookID`). NEW descriptor in `action_confirm_token.go`.
- **Confirm effect** (`pipeline_confirm.go`): re-validate entity-in-book → call provider-registry
  `/internal/web-search` (caller's model) → **neutralize** each result (`content` is DATA: strip/escape,
  cap length, tag provenance) → summarize into an enriched `short_description` via the user's LLM
  (through provider-registry, prompt frames results as untrusted quoted DATA, INV-6) →
  write the description as a DRAFT edit (reuse the propose-edit/atomic path; never auto-canon) →
  attach each source `url` as an **evidence** row (`evidence_type='reference'`, `original_text` =
  neutralized snippet, note = title+url) via `createEvidenceCore`.
- **Preview** surfaces the entity + the proposed description + the source list (no outward call at
  preview if cached; else a bounded fetch). Single-use jti (`consumed_tokens`).
- **Tests:** mint/grant gate, non-owner deny, confirm→effect with a STUBBED provider-registry
  web-search (httptest), evidence-attached count, INV-6 neutralization (a `content` carrying
  `"ignore previous instructions"` lands as inert evidence text, never reaches the summarize prompt
  un-quoted), verified-description not clobbered.

### 3c. FE — research review card (slice 3)
- The class-C confirm card is **descriptor-keyed** (`deep_research`) → the generic `ConfirmActionCard`
  renders it with the cost estimate (S21) + the source list; Apply commits via
  `/v1/glossary/actions/confirm`. The resulting draft description + evidence are reviewed in the
  existing entity editor (EvidenceTab + AttrCard). A light research-specific summary (sources with
  favicons/links) is a polish add on top of the generic card.

## 4. Provider choice (default)

**Tavily** as the reference `web_search` provider (clean AI-oriented search API: `POST /search`,
returns ranked `{title,url,content,score}` + an optional synthesized `answer`). The adapter is
Tavily-shaped but provider-agnostic at the credential layer (any Tavily-compatible `endpoint_base_url`
works; Perplexity/Brave can be added as alternative adapters keyed by `provider_credentials.kind`
detail later). **BYOK** — the user supplies their own key in Settings; the platform ships no key and
makes no un-owned outward calls.

## 5. Cost / live-verification note

Live web-search needs a real BYOK key (Tavily). Unit tests stub the outward HTTP (httptest), so the
adapter + resolution + tool + neutralization + evidence are fully test-covered WITHOUT a key. A real
end-to-end smoke is gated on the user registering a `web_search` credential →
`D-S5-LIVE-SMOKE` (live infra: needs user BYOK key).

## 6. Build order (slices, each its own commit/risk-boundary)

1. **provider-registry web_search** — adapter + capability + `/internal/web-search` + tests. *(invariant-critical foundation)*
2. **glossary deep_research MCP tool** — class-C descriptor + effect (web-search→neutralize→summarize→draft edit + evidence) + tests.
3. **FE** — generic confirm card already renders it; add the sources summary; i18n.
4. **gateway** — `AI_GATEWAY_PROVIDERS` already federates glossary; no change (the tool rides the existing glossary provider).

## 7. Out of scope (tracked, not silently dropped)

- Multi-provider search fan-out / re-ranking across providers (one BYOK provider first).
- A standalone deep-research *agent loop* (iterative query refinement) — v1 is single-pass search→summarize.
- Non-glossary research targets (chapter/world enrichment) — same pattern, later.
