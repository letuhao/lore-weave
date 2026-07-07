# Hardcoded context-window constants — audit + fix plan

**STATUS (2026-07-08): Tier 0 + Tier 1 + Tier 2 SHIPPED, `/review-impl` pass done + fixes
applied.** See "Completion log" + "`/review-impl` findings + fixes" at the bottom for what
changed, where, and what's still open (Tier 3 only + 2 items reviewed and excluded).

**Origin:** user hit `sdks/python/loreweave_context/budget.py`'s hardcoded absolute cap
(`_TARGET_MAX_CAP = 200_000`) clamping the Context Inspector's soft target for a 1M-context
model to the same number a 200K model got. Fixed same-session (pure-fraction math, no
absolute cap). User then asked: **audit the rest of the codebase for the same bug class,
and plan the fixes rather than doing them all now** — then, in a follow-up session, asked
to execute the plan. Tier 0 + Tier 1 are now shipped (see completion log).

**The bug class:** a token/char ceiling for an LLM call is a flat literal instead of being
derived from the *actual* model's resolved context window (`context_length`, resolved
per-model via provider-registry-service). Symptom: a small-window model and a huge-window
model get the identical budget — the huge-window model's headroom is wasted, and (worse)
the small-window model can still overflow if the literal happens to exceed its real window.

**Method:** 4 parallel agent audits — `sdks/python`, `chat-service`, {`composition`,
`knowledge`, `translation`}-service, `provider-registry-service`. Each hit is one of three
shapes:
- **A — call site**: `context_length`/`model_ref` is already resolvable right there; just
  not used. Cheapest fix.
- **B — signature gap**: the consuming function has no `context_length` parameter at all;
  needs new plumbing through 1+ call layers.
- **C — resolution bug**: the *source of truth* (provider-registry) itself fabricates a
  guessed number instead of surfacing "unknown," poisoning every downstream consumer.

---

## Tier 0 — root cause, fix first (Shape C)

These matter most: fixing every downstream Tier 1/2 item is pointless if the number they'd
resolve to is itself fabricated.

1. **`services/provider-registry-service/internal/api/server.go:2743-2798`**
   `getModelContextWindow` (`GET /models/{model_ref}/context-window`) hardcodes
   `const fallback = 8192` and returns it as a concrete value — not `null` — on **5** distinct
   paths: bad UUID, model row not found, adapter resolve failure, `ListModels` failure, model
   not found in live list, **and** the genuine `context_length IS NULL` case. Contrast with
   `internal/jobs/repo.go:943-970` + `jobs_handler.go:347-394`, which correctly skip the
   overflow check on `NULL` rather than guessing — that's the pattern this endpoint should
   follow (return `null`/a `resolved: bool` flag, let the caller decide, same as
   `compute_target` already does).
2. **`services/translation-service/app/workers/chapter_worker.py:758-781`** — the confirmed
   live consumer of #1. Also has its **own** duplicate `_FALLBACK_CONTEXT_WINDOW = 8192`
   (line 25) as a second guess-layer. Flows into `block_batcher.py:75-87,144,177`
   (`available = context_window - overhead`, `max_tokens = context_window_tokens *
   budget_ratio`) — i.e. it silently drives real chapter chunk-sizing for every model whose
   real window differs from 8192 (which is most of them).
3. **`services/provider-registry-service/internal/provider/adapters.go:869-902`**
   (`parseOpenAIModels`) — the path used on every *successful* live OpenAI `/v1/models` call
   never populates `ContextLength` (always `nil`), even though `preconfig_openai.json`
   already knows e.g. `gpt-4o → 128000`. The preconfig is only consulted as an all-or-nothing
   fallback when the live call fails outright, never merged by model name into a successful
   result. Not a wrong-number bug (surfaces safely as "unknown"), but a functional regression
   — real OpenAI users get "unknown" far more often than the data available would require.
4. **Noted, not yet a bug**: `ollamaAdapter.ListModels` (`adapters.go:1240-1274`) never
   queries Ollama's `/api/show` for `num_ctx` — `ContextLength` is always `nil` from
   discovery for Ollama models (consistent with today's hard-required manual entry at model
   creation, but means Ollama windows are never actually *discovered*).

**Fix shape:** (1) change the endpoint contract to distinguish "resolved" from "unknown"
(never synthesize 8192); (2) delete `chapter_worker.py`'s duplicate fallback and treat
"unknown" the same way `compute_target` does (skip/widen, never guess); (3) merge
preconfig `context_length` into live OpenAI discovery by model name; (4) is a genuine new
capability (Ollama `num_ctx` discovery), lower urgency.

---

## Tier 1 — real bugs, cheap fix (Shape A: context_length/model_ref already in scope)

| # | File:line | Constant | Consumer |
|---|---|---|---|
| 1 | `services/chat-service/app/config.py:89` | `tool_result_token_cap: int = 8000` | `stream_service.py:1572` D7 single-tool-result overflow cap. `creds.context_length` resolved a few hundred lines away in the same call chain (`stream_service.py:2109`). |
| 2 | `services/chat-service/app/services/tool_surface.py:26-27` | `HOT_SEED_TOKEN_BUDGET=4000`, `ACTIVATED_TOOLS_TOKEN_BUDGET=6000` | Tool-schema advertising budget, called from `stream_service.py:2190,2508`, downstream of the same `context_length` resolution. |
| 3 | `services/chat-service/app/services/steering.py:34` | `STEERING_TOKEN_CAP=2000` | Per-book steering block (`stream_service.py:2301`), same enclosing scope as `context_length`. |
| 4 | `services/composition-service/app/config.py:50` | `pack_token_budget: int = 6000` | Scene-generation prompt packer (`packer/pack.py:527`, via `routers/engine.py:373`). `model_source`/`model_ref` already in hand one line earlier (`engine.py:350-351`) for `_compress_fn` but unused for sizing. |
| 5 | `services/composition-service/app/config.py:127,131` | `stitch_max_input_chars=24000`, `compress_max_input_chars=24000` | `engine/stitch.py:248→324`, `engine.py:353`. Same call chains already thread `model_source`/`model_ref`. |
| 6 | `services/composition-service/app/engine/quality_report.py:154` | `_COVERAGE_WINDOW_CHARS=12000` | Promise-coverage prompt windowing (`_score_windowed`, lines 177-235) — `model_source`/`model_ref` are parameters throughout. |
| 7 | `services/composition-service/app/engine/cowrite.py:132` | `SELECTION_MAX_CHARS=8000` | Selection-edit input cap; `model_source`/`model_ref` present in the same call chain. |
| 8 | `services/composition-service/app/config.py:205` | `motif_deconstruct_chunk_chars=12000` | `engine/motif_deconstruct.py:527`, BYOK model-driven, `context_length` not consulted. |
| 9 | `services/translation-service/app/workers/glossary_translate_worker.py:49-50` | `_GLOSSARY_TRANSLATE_MAX_OUTPUT_TOKENS=32768` (env-overridable) | `entity_output_budget()` ceiling, line 220. **Proof this is cheap**: the sibling `extraction_worker.py:836,930,934` in the *same service* already calls `extraction_model.get_model_context_window()` — just not wired into this path. |
| 10 | `sdks/python/loreweave_extraction/extractors/{entity,event,fact,relation}.py` (chunk_size / max_tokens fallback branches: `entity.py:310,330`, `event.py:480,495`, `fact.py:371,386`, `relation.py:309,324`) | `chunk_size=15`, `max_tokens=4096` (fallback branch) | **Root cause is one call site**: `services/worker-ai/app/decoupled_extract.py:320,348` calls `build_*_submit_kwargs(..., context_budget=None)` unconditionally — `model_ref`/`model_source` are already in `rs` at that call site, so this fallback fires on **every real extraction call today**, for every model. Highest-value fix in this tier: one wiring change unlocks all 4 extractors at once. |

**Note on composition-service specifically**: unlike translation-service, it has **no
existing helper** to resolve `context_length` from provider-registry — items 4-8 need that
helper added once, then reused. Slightly more lift than translation's item 9, but still
call-site-local (no signature changes needed on the consuming functions).

---

## Tier 2 — deeper wiring gaps (Shape B: no context_length parameter exists yet)

| # | File | Constant | Why it's deeper |
|---|---|---|---|
| 1 | `services/chat-service/app/services/story_state.py:25` | `STORY_STATE_TOKEN_CAP=1200` | Consumed via `app/db/session_blocks.py:164`, whose refresh function has no `context_length`/`creds` parameter — needs threading from `stream_service.py` down through a DB-layer call. |
| 2 | `services/chat-service/app/services/subagent_runtime.py:71` | `SUBAGENT_RESULT_CHAR_CAP=4000` | No `context_length`/`creds` reference anywhere in the module. Deepest gap in chat-service. |
| 3 | `sdks/python/loreweave_extraction/extractors/summarize.py:49,163` | `_MAX_CHILD_TEXT_CHARS=8000`, `max_tokens=1024` | `summarize_level()` has **zero** `context_budget`/`context_length` references — the function signature itself needs a new parameter, not just a call-site fix. Docstring literally says "keeps the prompt within a typical 4K-token context budget," a baked-in assumption. |
| 4 | `sdks/python/loreweave_extraction/entity_recovery.py:223`, `pass2_filter.py:287` | `max_tokens = 1024 + 200×n_items` / `1536 + 256×n_items` | Output budget scales only with item count, never with the model's window — no clamp against a real ceiling, so a large batch against a small-context model can silently request more output than the model can host. |
| 5 | `services/knowledge-service/app/config.py:71` | `mode3_token_budget: int = 6000` | Consumed in `context/modes/full.py:881`, `context/modes/multi_project.py:383`. `build_full_mode()`/its router take no `model_ref`/`context_length` — the actual consuming chat model is resolved downstream in chat-service, not here. Needs cross-service plumbing (pass the target model's context_length into the knowledge-service context-build call), not a local fix. |

---

## Tier 3 — latent, currently unreachable (fix before it's ever wired up)

- **`sdks/python/loreweave_extraction/context_budget.py:83,89`** — `DEFAULT_MODEL_CONTEXT=8192`,
  `DEFAULT_MAX_OUTPUT_TOKENS=4096` back `_build_budget_for_model()` and `planner.py`'s
  `ModelCaps` dataclass defaults.
  **CORRECTED 2026-07-08 (per CLAUDE.md's "verify against code, don't trust the doc" rule
  — this session's original claim below was wrong):** `_build_budget_for_model()` itself
  genuinely has zero callers anywhere in the repo (confirmed by grep) — that part stands.
  But `ModelCaps`/`planner.plan()` are **not** zero-instantiation: they're used by
  `services/translation-service/app/workers/extraction_prompt.py`'s
  `estimate_extraction_cost()`, called from `app/mcp/server.py:878` and
  `app/routers/extraction.py:193` — both real production paths (the pre-job cost/call
  quote). The DEFAULT_MODEL_CONTEXT fallback (`ModelCaps(context_window=model_context_window
  or DEFAULT_MODEL_CONTEXT)`) is still practically unreached today only because BOTH known
  callers always resolve a real `model_context_window` first via
  `extraction_model.get_model_context_window()` (which itself always returns a concrete int,
  never `None`) — but the function's own `model_context_window: int | None = None` parameter
  and its own test suite (`estimate_extraction_cost(chapters, profile, kinds)` with the arg
  omitted) prove the fallback path IS live/reachable for any caller that doesn't resolve it.
  Verdict: not a Tier-1/2-style urgent bug — this reachable path is a cost **estimate**
  fallback (same "estimate, not quote" category as the constants already excluded in "Ruled
  out" below), never drives a real LLM call's actual chunk sizing (that's `chapter_worker.py`,
  a separate, already-fixed mechanism) — so a wrong guess here just skews a pre-flight quote,
  it can't overflow a real request. Still fix the defaults before anything NEW routes real
  chunk-sizing through this planner, per the original note below.
  - **Separately discovered while verifying the above (NOT this bug class — flagged, not
    fixed, needs the user's call before touching it):** `estimate_extraction_cost()` appears
    to double-apply reasoning-effort output scaling on the planner path. It computes
    `output_per_call = 2000 * _EFFORT_OUTPUT_MULTIPLIER[effort]` (its own local table:
    `none/off=1.0, low=1.5, medium=2.5, high=4.0`) at `extraction_prompt.py:520-521`, then
    feeds that ALREADY-scaled value into
    `out_per_call = output_per_call * effort_output_multiplier(effort)` at line 539 — using
    `planner.py`'s SEPARATE table (`none=1.0, low=1.3, medium=1.8, high=2.5`). For
    `reasoning_effort="high"` that's `2000 × 4.0 × 2.5 = 20,000` — the effort scaling
    compounds instead of applying once. The flat-heuristic fallback path (used when the
    planner SDK import fails) is unaffected — it uses `output_per_call` alone, correctly
    scaled once. `test_estimate_cost_scales_with_reasoning_effort` (`test_extraction_windowing.py:69`)
    only asserts monotonic growth (`high > low > none`), not an exact value, so it wouldn't
    catch this. Root cause is clear but the CORRECT fix isn't purely mechanical — it's a
    product decision (which of the two multiplier tables should govern, or should the
    planner path stop re-scaling an already-scaled input) — so this was flagged for the
    user's decision rather than silently "fixed" against a guessed intent, per this repo's
    Debugging Protocol (no fixes without confirmed root cause AND correct target behavior).
    Blast radius: pre-job cost/call quote accuracy only (an "estimate, not quote" UI number)
    for `reasoning_effort != "none"` extraction jobs — does not affect real job execution or
    correctness, only how many LLM calls / what cost range the UI shows before the user
    confirms.
    **FIXED 2026-07-08 (user's decision: drop the planner-path re-scaling).**
    `extraction_prompt.py:539` no longer re-multiplies by `effort_output_multiplier` — it
    reuses `output_per_call` (already scaled once by this file's own table) directly as
    `out_per_call`, matching the flat-heuristic fallback path's behavior exactly. Dropped
    the now-unused `effort_output_multiplier` import. New test
    `test_estimate_cost_scales_effort_once_not_twice` (`test_extraction_windowing.py`) pins
    the expected magnitude per effort level (e.g. `high` ≈ 8,000, not the ~20,000 a
    reintroduced double-scale would produce) — the existing monotonic-growth test wouldn't
    have caught a regression back to compounding. translation-service full suite: 1042
    passed (up from 1041).

---

## Ruled out (audited, not this bug class — listed so this isn't re-investigated)

- `loreweave_llm/models.py`, `client.py` 4096/32000/4000 constants — documented OpenAI
  TTS/image API wire limits, not model-context budgeting.
- `loreweave_parse/pdf_walker.py` `DEFAULT_VISION_MAX_DIMENSION_PX`, `plaintext_parser.py`
  `_DETECT_WINDOW` — pixel dimension / char-sniffing window, unrelated to LLM context.
- `chat-service/client/knowledge_client.py:81 MESSAGE_MAX_CHARS=4000`,
  `services/evaluate.py:30 EVAL_MAX_MSG_CHARS=1500` — real external API/service constraints,
  not context-window-derived.
- `chat-service/routers/evaluate.py:110`, `compact_service.py:129` `max_tokens=1200/1400` —
  internal summarizer *output* length, not an input-context ceiling.
- `composition-service/schema_propose/engine.py:29 _MAX_OUTPUT_TOKENS=3000`,
  `translation-service/glossary_translate_prompt.py:97 ceiling=32768` — output-token caps
  (JSON payload size); weaker candidates since output size doesn't necessarily need to scale
  with context window.
- `translation-service/ontology/build_wiki_effect.py:29 _TOKENS_PER_WIKI_ENTITY=3000`,
  `book_client.py:10 _DEFAULT_CHAPTER_TEXT_LENGTH=8000` — cost-estimate heuristics, not budget
  ceilings.
- `provider-registry-service` adapters' nil-on-unknown pattern (`adapters.go:20-49,
  1038-1108,1384-1479`) and `jobs/repo.go:943-970`+`jobs_handler.go:347-394`'s
  NULL-skips-the-check pattern — both already correct (never guess; explicitly propagate
  "unknown").

---

## Recommended fix order (defer-gate reasoning per CLAUDE.md)

This whole audit is **defer-eligible under gate #2 (large/structural)** — 12 findings across
5 services, several needing new cross-service plumbing (Tier 2/3) — not a same-session fix.
Suggested order for whenever this is picked up:

1. **Tier 0 first, always** — fixing Tier 1/2 call sites is wasted if the resolved
   `context_length` feeding them is itself a fabricated 8192. Start with
   `getModelContextWindow` (server.go) + `chapter_worker.py`'s duplicate fallback.
2. **Tier 1 #10 next** (`decoupled_extract.py`'s `context_budget=None`) — one wiring change
   unlocks 4 extractors simultaneously, the highest fix-to-effort ratio in the whole audit.
3. **Tier 1 #1-3, #9** (chat-service + translation's glossary-translate) — cheapest
   remaining Shape-A fixes, `context_length` already resolvable locally.
4. **Tier 1 #4-8** (composition-service) — needs one new provider-registry-resolution helper
   first (doesn't exist in this service yet), then 5 call sites reuse it.
5. **Tier 2** — each needs a signature change + threading through 1-2 call layers; do
   opportunistically alongside other work in the same files rather than as a dedicated pass.
6. **Tier 3** — fix only if/when `loreweave_extraction.planner`/`ModelCaps` actually gets a
   production caller; no user-visible impact until then.

**Not in scope for this plan:** re-auditing Go/TS services outside provider-registry (no
evidence found of similar per-model token budgeting there — this bug class is specific to
LLM-call-adjacent Python services + the one Go resolution endpoint).

---

## Completion log (2026-07-08)

**Tier 0 — shipped:**
- `getModelContextWindow` (server.go) no longer fabricates `8192` — returns
  `{context_window: null, resolved: false}` on every unresolvable path; new Go unit test
  covers the bad-UUID case. `chapter_worker.py`'s duplicate fallback deleted, now imports
  the shared `extraction_model.get_model_context_window` (same helper `extraction_worker.py`
  already used) — one Python-side fallback definition, not two drifting copies.
- `parseOpenAIModels` now merges `preconfig_openai.json`'s known `context_length` by model
  name into live `/v1/models` results (new `contextLengthByName` helper + test) — a
  successful live sync no longer reports "unknown" for well-known models like `gpt-4o`.

**Tier 1 — shipped (all 10 items, one added helper, one excluded after review):**
- **`decoupled_extract.py` (#10, highest leverage):** discovered the bug was NOT
  scoped to the decoupled path alone — the sync `extract_pass2` SDK function also never
  threaded `context_budget`. Fixed both: new `loreweave_internal_client.resolve_context_length`
  SDK helper (mirrors `resolve_model_name`'s pattern) + `ProviderRegistryClient.get_context_length`
  (worker-ai) → resolved once per chapter in `runner.py` (`_start_decoupled_chunk` stashes
  `context_length` into resume_state; the sync `_extract_and_persist` path resolves it
  inline) → `extract_pass2` gained a `context_budget` param threaded to all 4 extractors →
  `decoupled_extract.py`'s `assemble_entity_submit`/`assemble_trio_submits` build a real
  `ContextBudget` from the stashed value instead of hardcoding `None`.
- **chat-service (#1-3):** added a new shared kernel helper,
  `loreweave_context.budget.scale_by_window(flat_default, context_length, tuned_window=200_000)`
  — `max(flat, fraction*window)`, never shrinks below the flat default, exported from both
  `loreweave_context` and chat-service's `token_budget.py` re-export. Wired into
  `tool_surface.py` (`HOT_SEED_TOKEN_BUDGET`/`ACTIVATED_TOOLS_TOKEN_BUDGET`, replacing the
  per-file scaling helper I'd drafted first), `steering.py` (`STEERING_TOKEN_CAP`), and
  `stream_service.py`'s D7 `tool_result_token_cap` — all now take an optional
  `context_length` param threaded from `creds.context_length` at each call site
  (`_stream_with_tools` gained the param too).
- **translation-service glossary_translate_worker.py (#9):** different shape than the rest —
  this is an OUTPUT ceiling, so the fix is a **clamp down** for small windows, not scale up
  (a flat 32768 output request can exceed a small local model's entire context). Resolves
  `get_model_context_window` once per job, clamps `entity_output_budget`'s ceiling to
  `min(flat_default, 0.8 × window)` when resolved.
- **composition-service (#4-8):** added `LLMClient.resolve_context_length` (mirrors the
  existing `resolve_planner_model` pattern — composition-service had no prior
  provider-registry resolver, per the plan's note). Wired `scale_by_window` (imported
  directly from `loreweave_context`, no wrapper module) into: `pack_token_budget` +
  `prompt_ceiling` + `compress_max_input_chars` (3 generate/selection-edit route handlers in
  `engine.py`), `stitch_max_input_chars` (both call sites: `engine.py` +
  `worker/operations.py`), `_COVERAGE_WINDOW_CHARS` (`build_promise_coverage`, already took
  it as a param — just needed the caller in `operations.py` to pass a scaled value),
  `motif_deconstruct_chunk_chars` (`deconstruct_reference`, same shape).
- **Excluded after review (not the same bug class):** `SELECTION_MAX_CHARS` (cowrite.py) is
  a Pydantic `Field(max_length=...)` request-validation constraint, evaluated at parse time
  before any handler code runs — can't be made dynamically model-aware without moving
  validation out of the Pydantic annotation into the handler body, a real API-contract
  change beyond this fix's scope; it's also explicitly a UX backstop (the FE already limits
  selection size), not a budget that benefits from scaling to a bigger window.
  `grounding.py`'s `budget_tokens=settings.pack_token_budget` call site is a read-only
  grounding **preview** endpoint with no model reference in scope at all (it doesn't call an
  LLM) — nothing to scale against.

**Verification:** every touched service's full test suite green (provider-registry-service
Go: all pass incl. 2 new tests; sdks/python: 778 passed, same 7 pre-existing unrelated
failures as before this session; worker-ai: 306 passed + 4 new tests, same 1 pre-existing
unrelated failure; translation-service: 1041 passed incl. 2 new clamp-regression tests;
chat-service: 1105 passed incl. new scaling tests; composition-service: 1670 passed incl.
new tests, 177 skipped (integration, needs live DB)). Multiple test fixtures (`_FakeLLM`,
`SimpleNamespace(sdk=...)` dependency overrides, bare `object()` stand-ins) needed a
`resolve_context_length` method added to keep working once the real code started calling it.

---

## Tier 2 completion log (2026-07-08, same-day follow-up)

All 5 Tier 2 items shipped, plus one design realization along the way: two of them
(`entity_recovery.py`/`pass2_filter.py`) turned out to need a **clamp-down**, not a
scale-up — the third shape variant found this session (glossary_translate_worker.py was
the first).

- **chat-service `story_state.py`** — `distill_story_state` already took `token_cap` as a
  param; just needed `session_blocks.py`'s `project_story_state` to accept `context_length`
  and pass `scale_by_window(STORY_STATE_TOKEN_CAP, context_length)` instead of the flat
  default, threaded from `stream_service.py`'s `creds.context_length`.
- **chat-service `subagent_runtime.py`** — `cap_result` gained a `char_cap` param;
  `_run_subagent_call` (stream_service.py) gained `context_length`, threaded from its one
  call site inside `_stream_with_tools` (which already had the param from Tier 1).
- **sdks/python `summarize.py`** — `summarize_level` gained `context_length`, scaling
  `_MAX_CHILD_TEXT_CHARS` (an input cap — the right shape for scale-up). Left the output
  `max_tokens=1024` untouched — it's sized to the task (a short summary), not the window;
  scaling it up for a bigger model would be the wrong fix, not a real bug. Needed a NEW
  cross-package import (`loreweave_extraction` → `loreweave_context`, no prior precedent —
  verified it resolves cleanly, both packages ship together via the same Dockerfile COPY).
  Knowledge-service's caller (`summary_processor.py`) got a new `resolve_context_length`
  shim (mirrors the existing `model_name.py` shim exactly) to resolve it before calling.
- **sdks/python `entity_recovery.py` + `pass2_filter.py`** — **shape correction**: these are
  OUTPUT budgets that scale with item count (`1024 + 200×n`, `1536 + 256×n`), not input
  budgets — scaling them UP for a bigger window doesn't make sense (a batch classification
  doesn't need more output just because the model has a bigger window). The real bug is the
  opposite: an uncapped formula can request MORE output than a small-context model can
  structurally host. Fixed with a clamp — `min(flat_formula, 0.8×context_length)` — added to
  `build_recovery_submit_kwargs`/`build_filter_submit_kwargs`, threaded through both the sync
  `pass2.py` path (`context_budget.model_context`) and the decoupled `decoupled_extract.py`
  path (`rs["context_length"]`, reusing the Tier-1 stash).
- **knowledge-service `mode3_token_budget`** — the one genuine cross-service contract
  change: added `context_length: int | None = None` as a new additive/optional field on
  `ContextBuildRequest` (matching this file's own established pattern, e.g.
  `current_chapter_id`), threaded router → `build_context` → `build_full_mode`/
  `build_multi_project_mode`, each scaling `settings.mode3_token_budget` via
  `scale_by_window`. chat-service's `KnowledgeContextClient.build_context` sends
  `creds.context_length` when known, omits it when not (byte-identical for an older
  knowledge-service). **Resolved by `/review-impl` (below): the ai-gateway hop for this
  call is `grounding.controller.ts`, a pure JSON-body pass-through with no DTO/validation
  pipe — it is NOT the same mechanism as MCP `tools/call` federation (that's a separate
  `/mcp` endpoint), so `context_length` does survive this hop unmodified.** The
  `gateway-drops-xprojectid-envelope` precedent doesn't apply here.

**Verification:** knowledge-service 3795 passed/529 skipped (0 failed); chat-service 1118
passed (0 failed, up from 1105 — new tests added); sdks/python 782 passed (same 7
pre-existing unrelated failures); worker-ai 308 passed (same 1 pre-existing unrelated
failure). New regression tests added for every fix, including the two-services-apart
`context_length` threading (chat-service sends it → knowledge-service scales with it).

**Still open (genuinely deferred):**
- **Tier 3** (latent/unreachable): `loreweave_extraction.context_budget`'s
  `DEFAULT_MODEL_CONTEXT`/`DEFAULT_MAX_OUTPUT_TOKENS` — still zero production callers. Fix
  only if/when `loreweave_extraction.planner`/`ModelCaps` actually gets wired up.

---

## `/review-impl` findings + fixes (2026-07-08)

3 parallel adversarial reviews (Tier 0/core, Tier 1, Tier 2) — one confirmed HIGH, two MED,
and several LOW test-coverage gaps. All fixed same-pass (none deferred — all cleared
CLAUDE.md's fix-now bar).

**HIGH — negative/zero `context_length` treated as "resolved," producing a negative
`max_tokens` sent to the provider.** `scale_by_window`/`compute_target` themselves already
guarded correctly (`context_length <= 0`), but the chain feeding them didn't:
- `provider-registry-service/internal/api/server.go` — `patchUserModel` had **zero**
  validation on `context_length` (unlike `createUserModel`'s ollama/lm_studio-only check).
  Fixed: both handlers now reject any non-nil `context_length <= 0` with
  `M03_VALIDATION_ERROR`.
- Falsy-only checks (`if cw else None`, `cw or FALLBACK`) let a negative value pass through
  as truthy in 3 places: `sdks/python/loreweave_internal_client/_context_length.py`,
  `services/composition-service/app/clients/llm_client.py`'s `resolve_context_length`,
  `services/translation-service/app/workers/extraction_model.py`'s
  `get_model_context_window`. All now explicitly require `> 0`.
- Defense-in-depth: `entity_recovery.py`/`pass2_filter.py`'s clamp guards
  (`if context_length:` → `if context_length and context_length > 0:`),
  `knowledge_client.py`'s `context_length` forward check, same pattern.
- `frontend/src/features/settings/EditModelModal.tsx` — the context-length input had no
  `min`; a user could type a negative value directly. Added `min={1} step={1}`.
- New tests: `test_scale_by_window_negative_context_length_keeps_flat_default`
  (sdks/python) proves a narrowed `< 0` guard (instead of `<= 0`) would regress.

**MED — subagent's nested `_stream_with_tools` call dropped `context_length`.**
`services/chat-service/app/services/stream_service.py`'s `_run_subagent_call` received
`context_length` (Tier 2, for `cap_result`'s char cap) but never forwarded it into the
nested tool-surface-budgeting call — the exact "second call site silently keeps the flat
default" pattern. Fixed: forwards `context_length` only when the subagent runs on the
**same** model as the caller (`sub_model_ref == model_ref`) — a subagent def can override
`model_ref`, and blindly reusing the parent's window for a genuinely different model would
misrepresent it; that case still correctly falls back to the flat default rather than
resolving a second model's window (a Tier-2-scale plumbing addition, not needed here).

**MED — composition-service's null-project pack path never scaled its budget.**
`app/packer/pack.py`'s `pack()` takes an already-`scale_by_window`'d `budget_tokens`, but
the greenfield/`project_id is None` short-circuit called `_pack_null_project(...)` without
it — that path read the flat `settings.pack_token_budget` directly, the one branch in the
whole Tier-1 composition-service fix that never scaled. Fixed: `_pack_null_project` gained
a `budget_tokens` param, threaded from `pack()`'s caller-scaled value.

**LOW (test-coverage gaps, all closed same-pass):**
- `context_window_test.go`'s header comment claimed DB-dependent paths were
  "integration-tested via docker-compose" — no such suite exists for this service (no
  `integration/` dir at all). Comment corrected to state the actual gap rather than
  overclaiming coverage (matches this repo's `checklist-is-self-report-enforce-by-tests`
  lesson: a claim of coverage needs a test proving it, not just a comment).
  DB-dependent paths (platform_model/user_model resolution, adapter failure, ListModels
  failure, model-not-in-live-list, genuine NULL) remain untested pending an integration
  harness — a real gap, tracked honestly now instead of masked.
- `test_context_length_scales_the_distill_cap` (chat-service) asserted only "more content
  survived" — strengthened to assert the exact expected scaled value
  (`scale_by_window(STORY_STATE_TOKEN_CAP, 1_000_000)`), which a wrong-but-still->1x scaling
  factor would have passed under the old assertion.
- `summarize_level`'s `_MAX_CHILD_TEXT_CHARS` scaling had zero SDK-level test (the only
  `context_length`-aware test mocked `summarize_level` entirely). Added
  `test_summarize_level_context_length_scales_the_truncation_cap` proving the real
  truncation math changes, not just that the kwarg is accepted.
- `build_multi_project_mode`'s `context_length → scale_by_window(mode3_token_budget)`
  wiring had no effect-proving test (unlike the sibling `full.py` path). Added
  `test_build_multi_project_mode_scales_shared_budget_with_context_length` proving
  `_enforce_shared_budget` actually receives the scaled value end-to-end.
- **Resolved, not a bug**: the plan's own flagged-open question — whether ai-gateway's MCP
  federation preserves `context_length` on the chat→knowledge hop. Traced: this call goes
  through `grounding.controller.ts`, a pure JSON-body pass-through (no DTO, no
  `ValidationPipe`) — a different mechanism from MCP `tools/call` federation. The field
  survives unmodified; the `gateway-drops-xprojectid-envelope` precedent doesn't apply.

**Verification:** every touched service re-run green post-fix — provider-registry-service
Go (`go build ./...` + `go test ./...`, all pass); sdks/python (785 passed, same 6
pre-existing unrelated failures, confirmed via clean `git status` on the untouched
`prompts/` dir); chat-service (1118 passed); composition-service (1674 passed, up from
1670); knowledge-service (3796 passed, up from 3795); translation-service (1041 passed);
worker-ai (308 passed, same 1 pre-existing unrelated failure). Frontend `tsc --noEmit`
clean on the `EditModelModal.tsx` change.
