# Plan — `response_format` json_object → text for LM Studio compat

**Size:** L (8 files; 1 logic change replicated; 0 side effects)
**Cycle:** 2026-05-26 (Track A live-smoke unblock)
**Driver:** session 68 — Track A model swap live smoke surfaced LM Studio HTTP 400 (`'response_format.type' must be 'json_schema' or 'text'`) on every extractor + judge call. Prior gateway-side `normalizeResponseFormatForKind` (server.go, commit db065152) lives on the retired `/internal/proxy/*` path; extractors migrated to `/internal/llm/jobs` async path (Phase 4a-α) and lost the normalization.

## Decision

Patch the source-of-truth (extractor + judge inputs) to send `{"type": "text"}` instead of `{"type": "json_object"}`. Prompts already include "Return only the JSON object" instructions + the aggregator's `extractJSONObject` helper (aggregator.go) parses fenced output (recovers from a leading ` ```json ` markdown fence + surrounding prose by extracting the outermost `{...}` object). OpenAI accepts `text` (it's the spec default — verified by OpenAI API reference; **live OpenAI smoke not run this cycle**, per `feedback_local_llm_first_cloud_is_fallback` cloud-cost-controlled stance). Anthropic adapter does NOT forward `response_format` at all — `anthropicAdapter.Stream` (adapters.go:929-959) builds its own body containing only `model`, `messages`, `max_tokens`, optional `temperature` + `system`, and tool fields; the gateway thus strips `response_format` for Anthropic targets before reaching the API. LM Studio finally happy.

Alternative rejected: gateway-side normalization in `forwardOptionalChatFields(adapters.go)` mirroring `normalizeResponseFormatForKind`. Tracked as separate cycle for defensive coverage (see follow-up).

## Files

| File | Change | Logic |
|---|---|---|
| `sdks/python/loreweave_extraction/extractors/entity.py:242` | `json_object` → `text` | 1 |
| `sdks/python/loreweave_extraction/extractors/relation.py:256` | `json_object` → `text` | 1 |
| `sdks/python/loreweave_extraction/extractors/event.py:372` | `json_object` → `text` | 1 |
| `sdks/python/loreweave_extraction/extractors/fact.py:316` | `json_object` → `text` | 1 |
| `sdks/python/loreweave_extraction/extractors/summarize.py:145` | `json_object` → `text` | 1 |
| `services/knowledge-service/tests/quality/llm_judge.py:407` | `json_object` → `text` | 1 |
| `services/knowledge-service/eval/QUALITY_EVAL_BASELINES.md` | New baseline section + comparison row | doc |
| **NEW** `services/knowledge-service/tests/unit/test_response_format_text_lock.py` | Regex-lock (whitespace-tolerant): every extractor + judge module must send `text`, not `json_object`. Imports SDK modules via `__file__` + locates `tests/quality/llm_judge.py` relatively, so the test runs cleanly in both monorepo and the knowledge-service Dockerfile test stage (line 33-37 — `pytest tests/unit/ -x -q`). | regression-lock |

## Verify evidence

- 9-chapter extraction eval: rule-based P=0.324 / R=0.560 (424.83s wall); LLM-judge P=0.93 / R=0.71 / coverage 100%/100%
- 1-chapter alice_ch01 smoke: 4 entities, 5 relations, 8 events, 14 facts in 30.3s
- **HIGH-1 (/review-impl) resolution**: post-eval root-cause check — re-ran the same async-jobs extractor on `journey_west_zh_ch01` in isolation and got **10 Chinese entities** (盤古, 三皇, 五帝, 四大部洲, 東勝神洲, 傲來國, 花果山, 玉皇大天尊玄穹高上帝, 千里眼, 順風耳). Raw model output capture showed the response was a ` ```json `-fenced JSON object containing those 10 entities — `extractJSONObject` recovered it cleanly. The original 0-entity result during the 9-chapter parallel eval was transient (concurrency/warmup) — NEITHER (a) CJK model weakness NOR (b) patch-induced regression. Patch is correct.
- Cross-service live-smoke evidence: extraction job through `/internal/llm/jobs` → gateway → LM Studio → 200 OK on huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated
- Memory anchor: `feedback_audit_all_callsites_when_adding_optional_kwarg` — every `response_format` callsite patched (regex grep `json_object` in extractor + judge files returns 0 hits post-patch)

## Follow-up

- **D-LM-STUDIO-RESPONSE-FORMAT-ASYNC-PATH** — port `normalizeResponseFormatForKind` (server.go, only on `/internal/proxy/*`) to async jobs adapter layer (`adapters.go::forwardOptionalChatFields`) as defensive coverage. Future extractor additions wouldn't have to re-discover the json_object regression.
- **D-JUDGE-EVAL-ASYNCIO-TEARDOWN** — pytest-asyncio fixture-scoping bug in `test_judge_eval.py`: `test_judge_discriminates_fabricated_items` leaks httpx connections + breaks subsequent `test_llm_judge_extraction_quality` with `RuntimeError: Event loop is closed`. Workaround: `pytest -k test_llm_judge_extraction_quality`.
- **D-EXTRACTION-PARALLEL-CONCURRENCY-FLAKE** — the 9-chapter concurrent eval (concurrency=4) produced a single transient zero-extraction on `journey_west_zh_ch01` that did not repro under isolated rerun. Suspect concurrency contention / model-swap warmup. Worth a follow-on cycle to add a per-chapter retry path or chunk-job re-submission when an extractor returns 0 candidates on a non-trivial chapter (heuristic — non-empty text, < N entity-density expectation).
- **D-AGGREGATOR-REASONING-CONTAMINATION-GUARD** — (`/review-impl` LOW-6) `extractJSONObject` (aggregator.go:376) assumes reasoning_content is on a separate stream channel and the `raw` arg holds only the answer content. If a model (or LM Studio config) emits reasoning as regular content tokens, the "first `{` to last `}`" boundary picks up the wrong region. Patch's switch to `text` makes loose-output more common; worth a defensive guard.
- **OpenAI live-smoke (deferred)** — patch was verified against LM Studio (live) + by spec for OpenAI. A one-off OpenAI BYOK smoke (`response_format: text` on entity_extraction prompt) would close the spec-only assumption, but is cost-controlled per `feedback_local_llm_first_cloud_is_fallback`. Bundle with the next platform-mode cloud test pass.
