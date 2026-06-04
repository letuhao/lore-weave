# Auto Reasoning (Thinking) Mode — design spec

> Auto-switch + user control of LLM "thinking" for the LOOM co-writer, grounded in how the industry does it. Reasoning is to creative writing what it is to coding — some passages are boilerplate (continue a line), some are architecture (weave canon, resolve a setup/payoff, turn a plot). The system decides when to think, the model thinks, the author can always override.

## Research (how the big players do it) — 2026-06
| Provider | Auto mechanism | Knob | Notes |
|---|---|---|---|
| **Anthropic** | `thinking:{type:adaptive}` — the MODEL self-decides whether/how much to think; `effort` (low..max) is soft guidance. Promptable ("think hard"). **Interleaved thinking** = thinks between tool calls (agentic, API-orchestrated). Summarized thinking = a 2nd model summarizes. | `effort` low/med/high/xhigh/max | Core is model-internal CoT; the *agentic* part is tool-loop + interleaved thinking + the "think" tool + Agent SDK — NOT the base reasoning. |
| **OpenAI GPT-5** | **A trained real-time ROUTER (separate model)** picks fast-vs-thinking by complexity/tool-need/intent. Clearest "code orchestrates thinking". | `reasoning_effort` none/minimal/low/med/high/xhigh | — |
| **Gemini 2.5** | `thinkingBudget = -1` → dynamic: model adjusts budget by complexity. | budget 0 / -1(auto) / N | model-internal dynamic. |
| **Qwen3 (local, our corpus)** | **No native auto.** Community (Better-Qwen3) runs an LLM classifier to toggle. `enable_thinking` + `/think` `/no_think`. | `reasoning_effort` (verified `"none"` works on LM Studio) | We MUST classify in code for local models. |
| **OSS routers** (vLLM Semantic Router, "When to Reason", arXiv 2510.08731) | Classifier (rule-based or ModernBERT): ≥N reasoning markers → reasoning tier; boilerplate → no-reason. | — | The pattern we mirror for local models. |

**Verdict on "Anthropic thinking = agentic pipeline":** partly true. Base extended thinking = model-internal reasoning block. The code/agentic orchestration is the surrounding agent loop (tool use + interleaved thinking + think-tool + summarizer + Agent SDK). OpenAI's GPT-5 router is the cleanest "code decides when to think".

## Principle (PO, 2026-06-05)
Build all 3 engines; the system **auto-selects the engine from the registered model's capability**, with user override. **Don't out-think a model that already self-orchestrates** — Anthropic/Gemini get **pass-through**; only models without native adaptive (Qwen3 local) get our classifier.

## Where it lives — SDK-first (reusable), domain-thin (revised 2026-06-05)
The **generic** reasoning machinery lives in the **`loreweave_llm` SDK** so EVERY service that calls the gateway (translation, extraction, chat, composition…) reuses one auto-thinking policy — the SDK already owns `reasoning_effort` / `ReasoningEffort`, so it is the natural home. Only the **domain scorer** (which signals matter, and their weights) stays in the consuming service.

- **SDK `loreweave_llm.reasoning`** (generic, reusable):
  - `ReasoningControl` + `infer_reasoning_control(provider_kind, name, flags)` — fully provider/model-driven, no domain knowledge.
  - `bucket_effort(score, *, high, medium, low)` — monotone score→effort bucketer for any rule-based "when to think" scorer.
  - `ReasoningDirective` + `resolve_reasoning(user_pref, model_control, auto_effort, *, auto_source)` — user-override > auto-dispatch (adaptive→passthrough / effort→use the caller's `auto_effort` / none→noop). The SDK does NOT know domain signals; the caller passes a precomputed `auto_effort`.
- **Composition `app/reasoning/policy.py`** (domain): the creative-writing `ReasoningSignals` + `score_effort` (uses the SDK `bucket_effort`), then calls the SDK `infer_reasoning_control` + `resolve_reasoning`. A future translation/extraction auto-think reuses the SDK + supplies its own signals.

## Architecture — capability-aware reasoning resolver
We already shipped the `reasoning_effort` knob (SDK→gateway→LM Studio) and the FE Off/Auto control — this adds the **auto decision** + **per-model strategy**, with the generic core in the SDK per above.

### 1. Model capability inference — `app/reasoning/capability.py`
`ReasoningControl = Literal["adaptive","effort","none"]`
`infer_reasoning_control(provider_kind, provider_model_name, capability_flags) -> ReasoningControl`
- explicit `capability_flags.reasoning_control` wins (operator/registry override).
- `anthropic` → `adaptive` (Claude 4+). `google`/`gemini` 2.5+ → `adaptive`.
- `openai` o1/o3/o4/gpt-5 → `effort`. `lm_studio`/`ollama` + name ~ /qwen3|deepseek-r1|.*thinking|.*reasoning/ → `effort`.
- else → `none`.
- pure table+regex, unit-tested. Model metadata (provider_kind, name) reaches composition as **request hints from the FE** (it already has them from listUserModels) — a UX policy, not an authz boundary, so a hint is acceptable; absent → safe default `effort` only if the user picked a concrete effort, else `none`.

### 2. Auto decision engines — `app/reasoning/policy.py`
`EngineKind = Literal["rule_based","llm_judge"]` (Work-settings selectable; default rule_based).
- **rule_based** `score_effort(operation, signals) -> effort`: weighted score over signals ALREADY computed by the packer — `n_canon_rules`, `n_present_entities`, `has_reveal_gate`, `tension`, `len(guide)`, reasoning-markers in `guide` (regex), and the `operation` (plan/weave → high; continue/rewrite-line → low/none; default med). Sub-ms, deterministic, no extra LLM. Mirrors vLLM "When to Reason".
- **llm_judge** (optional): one small pre-call rates difficulty → effort (Better-Qwen3 style). Behind a flag; +1 round-trip; for V1 quality if rule_based underperforms.

### 3. Resolver — `app/reasoning/resolve.py`
`resolve(user_pref, model_control, engine, operation, signals) -> ReasoningDirective`
`ReasoningDirective = {effort: ReasoningEffort|None, passthrough: bool, source: str}`
- `user_pref` ∈ {off, auto, low, med, high}.
- explicit (off→effort="none"; low/med/high→that) → override, source="user".
- `auto`:
  - `model_control=="adaptive"` → **passthrough=True, effort=None** (let the model decide; we add a light promptable hint only). source="adaptive".
  - `model_control=="effort"` → run `engine` → effort. source="rule_based"/"llm_judge".
  - `model_control=="none"` → effort=None (no-op). source="non_reasoning".
- composition sends `reasoning_effort = directive.effort` (omit when None/passthrough).

## Wiring
- **composition `/generate` (`routers/engine.py`)**: `GenerateBody` gains `reasoning: Literal["off","auto","low","medium","high"] = "auto"` + optional `model_kind`/`model_name` hints. Handler: pack → extract `signals` from the pack result → `resolve(...)` → pass `directive.effort` to `stream_draft`. Emit the resolved `source`/`effort` in the `job` SSE frame (transparency).
- **composition `cowrite.stream_draft`**: already takes `reasoning_effort`; for `passthrough` send nothing (model default/adaptive). (Anthropic adaptive via the OpenAI-shaped gateway = omit reasoning_effort; the provider applies its default adaptive.)
- **Work settings**: `reasoning_default` (off/auto/low/med/high, default auto) + `reasoning_engine` (rule_based/llm_judge). The per-generate `reasoning` overrides the Work default.
- **FE (`ComposeView`)**: control becomes **Off / Auto / Low / Med / High** (default Auto). Pass `model_kind`/`model_name` (from the selected user-model) as hints. Show the resolved badge ("Auto → high"). Persist the choice to Work settings as the default.
- **provider-registry**: NO schema change required for V0 (capability inferred FE-hint + heuristic). A future `capability_flags.reasoning_control` override is honored if present.
- **SDK/openapi**: unchanged — `reasoning_effort` already none/low/med/high; "auto" is a composition concept resolved to a concrete effort (or omitted) before the SDK call.

## Test plan
- **pure unit**: `capability.infer_reasoning_control` table (anthropic→adaptive, qwen3→effort, gpt-5→effort, unknown→none, explicit-override wins); `policy.score_effort` (plan-beat→high, continue→low, many-canon-rules+reveal_gate→high, empty→default); `resolve` matrix (user override beats auto; adaptive→passthrough; effort→engine; none→noop).
- **router unit**: `/generate` body `reasoning` validation (422 on bad); resolved effort threaded into stream_draft (fake SDK captures it); SSE `job` frame carries source/effort.
- **FE unit**: ComposeView Off/Auto/Low/Med/High → correct reasoning sent; Work-settings default; resolved badge.
- **live smoke**: auto + qwen3.6-35b-a3b (effort model) → resolver picks an effort → streams prose; auto + a simulated adaptive model → passthrough (no reasoning_effort on the wire). cross-service token.

## Out of scope (V1)
- Trained router / ModernBERT classifier (we use rule-based). Interleaved/tool thinking. Per-genre tuning of the scorer weights. provider-registry `reasoning_control` UI.
