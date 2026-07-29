# Reasoning wire-fields — back to one SSOT

**Size:** L (files=25, logic=8, side_effects=2) · **Date:** 2026-07-30
**Trigger:** a live empty-draft on the FE Generate button. Root cause was not the model.

---

## 1. The defect, stated once

Clicking **Generate** in Scene Compose returned `text=""`, 800 output tokens billed,
`status: completed`. The same model, same scene, through the **auto/diverge** path returns prose.

One model. Two code paths. Opposite outcomes. That is not a model problem — it is a
**drift** problem, and the drift is that composition-service holds **three different dialects**
for a decision that has exactly one right answer.

## 2. Inventory (counted, not estimated)

| Dialect | Where | Count |
|---|---|---|
| **1 — the SSOT** | `loreweave_llm.reasoning.reasoning_fields()` / `no_thinking_fields()` | adopted by chat, translation, knowledge, lore-enrichment · **composition: 0 call sites** |
| **2 — hand-copied `_NO_THINK`** | `world_plan` `self_heal` `eval_judge` `select` `error_block_heal` `compress` `promise_audit` `character_plan` `plan_heal` `cast_plan` `motif_plan` `plan` `plan_forge/llm` + inline in `critic` `motif_conformance` `narrative_thread` | **16** copies of the same 2-key dict, + 4 cross-imports (`stitch←select`, `intent_fsm←compress`, `glossary_build←compress`, `llm_json←compress`) |
| **3 — hand-rolled collapse** | `engine.py`: `reasoning_effort=None if reasoning.passthrough else reasoning.effort` | **9** sites — and every one **silently drops `chat_template_kwargs`** |
| **3b — re-derive in the worker** | `operations.py:346,470,559`: `effort_arg = None if input.get("reasoning_passthrough") else effort` | **3** |

The SDK docstring for `reasoning_fields` literally says it *"replaces translation's
`thinking_llm_fields` + **composition's inline copies**."* Every service named in that sentence
adopted it except the one it named specifically. The replacement was written and never landed.

**Two serialization conventions in the same file:** `engine.py:501` stores the raw effort +
a separate `reasoning_passthrough` flag and lets the worker collapse it; `engine.py:1352` stores
the *already-collapsed* effort. Same directive, same file, two shapes.

## 3. Why dialect 2 works and dialect 3 does not

```python
# select.py:76 · stitch.py:330   — None ⇒ fail-SAFE
**({"reasoning_effort": e} if e is not None else _NO_THINK)

# engine.py (9×) → cowrite.stream_draft — None ⇒ fail-OPEN
reasoning_effort=None if reasoning.passthrough else reasoning.effort
```

The same `None` means "suppress thinking" in one dialect and "send nothing" in the other.

## 4. The upstream half: a name regex decides whether a model can think

`infer_reasoning_control` classifies via `_EFFORT_LOCAL = qwen3|deepseek-r1|magistral|reasoning|thinking|qwq`.
A local thinking model whose name matches none of those (**gemma-4 26B-A4B QAT**) is classified
`"none"` → `resolve_reasoning` returns `effort=None` → `reasoning_fields` returns `{}` → nothing
on the wire → the chat template's own default wins → **thinking on** → the whole budget goes to
hidden reasoning → `text=""`.

That regex is also a **hardcoded model-name list in runtime code**, which the repo forbids. The
right home is `capability_flags.reasoning_control`, and the override hook **already exists and is
checked first** — it was simply never populated.

**The deeper defect is not the regex — no regex will ever be complete.** It is that a *guess*
fails **open**: when the platform is wrong about a model, thinking stays on and the author pays
for silence.

### Why fail-open was once correct, and no longer is

Sending `reasoning_effort` to OpenAI `gpt-4o` used to 400 the request
(`feedback_openai_reasoning_effort_o_series_only`). Fail-open protected that. But **LOOM-71 moved
that protection to the gateway** — `stripDefaultOpenAIUnsupportedFields` (verified live in
`adapters.go:702`) deletes both fields for real-OpenAI non-o-series and **keeps** them when a
custom `base_url` is set (i.e. every local server). The guard that fail-open existed to provide is
now enforced one layer down. Nobody went back and flipped the default.

## 5. The change

### SDK — `sdks/python/loreweave_llm/reasoning.py`

1. `ReasoningControl` gains **`"suppress"`**: *the endpoint accepts the suppression knobs, but we
   have no evidence this model reasons.* Distinct from `"none"` (*no knob exists at all*).
2. `infer_reasoning_control`: a **local** kind (`lm_studio`/`ollama`/`llama_cpp`/`vllm`/
   `openai_compatible`) with no reasoning-name match → `"suppress"` instead of falling to `"none"`.
   Non-local unknown → `"none"`, unchanged.
3. `resolve_reasoning`: `"suppress"` → `ReasoningDirective(effort="none", passthrough=False,
   source="suppress_unclassified")` — so the reason is visible in telemetry, not inferred.
4. New `directive_from_parts(source, effort, passthrough)` — the ONE way to rebuild a directive
   from serialized job input, replacing the two ad-hoc conventions.

Suppression is free when the guess is wrong in the harmless direction: `reasoning_effort="none"`
on a genuinely non-reasoning local model is a no-op. It is **not** free in the other direction —
that is the bug being fixed. A user who wants thinking still wins: an explicit `user_pref`
overrides everything, and `capability_flags.reasoning_control` overrides the heuristic.

### composition-service

5. Delete all 16 copies + the 4 cross-imports → `**no_thinking_fields()` at each call site.
6. `cowrite` / `select` / `stitch` / `canon_reflect`: take a **`ReasoningDirective`**, not a bare
   `effort: str | None`, and emit `**reasoning_fields(directive)` — both fields or neither.
7. `engine.py`: delete the 9 hand-rolled collapses; store all three raw parts consistently
   (fixes `:1352`).
8. `operations.py`: delete the 3 re-derives; one `directive_from_parts(...)`.

**No job_input schema migration.** The three flat keys stay exactly as they are on the wire and in
`generation_jobs`; only *who reconstructs the directive* is unified. An old queued job whose
`reasoning_effort` is null rebuilds to `effort=None, passthrough=False` → `{}` → identical to
today's behavior. In-flight jobs drain safely.

### The gate — so this cannot rot again

9. A test that reds if any module under `app/` defines a dict literal carrying **both**
   `reasoning_effort` and `chat_template_kwargs` (the copy's signature), asserting
   `reasoning_fields` / `no_thinking_fields` are the only producers.

A rule with no gate is a rule that drifts — and this one already drifted 16 times.

## 6. Accepted behavior change (deliberate, not incidental)

**chat-service** also calls `infer_reasoning_control`. A local model we cannot classify moves from
*"send nothing, whatever the chat template does"* to *"thinking off unless the user asks"*. This is
a real change and it is the intended one: template-roulette is replaced by a deterministic default
the user can override with the existing toggle. Recorded here rather than discovered later.

## 7. Verify

- SDK suite + composition full suite + chat-service suite.
- A test proving `stream_draft` forwards `chat_template_kwargs` — the field dialect 3 dropped.
- **Live smoke**: gemma-4 26B-A4B QAT through the FE Generate button must produce prose.
  Unit green is not evidence here — the bug was invisible to every mock.

---

## 8. What the review pass added (and what it deliberately did not)

### 8a. The fix depended on the client remembering to describe its own model — HIGH, fixed

`infer_reasoning_control(body.model_kind, body.model_name)` reads two OPTIONAL request hints, and
the FE spreads them conditionally:

```ts
...(args.modelKind ? { model_kind: args.modelKind } : {}),
```

`modelKind` comes from `selectedModel?.provider_kind`, so a generate fired before the model
metadata resolves omits both. That was harmless while the classifier only picked an effort
*level*. It stopped being harmless the moment the classifier also decided *suppression*: no hint
→ "not a local model" → nothing on the wire → the empty draft, straight back in through the front
door. **A server-side correctness decision was resting on a client-supplied hint.**

The registry already answers this — `/internal/models/{source}/{ref}/info` returns
`provider_kind` + `provider_model_name`, and its own test says it exists "so worker-ai can run the
reasoning-model advisory". It was built for this and never wired up. Now `_reasoning_control_for`
asks the registry first and keeps the client hint only as the degraded fallback.

Proven live: the same gemma draft, with **both hints removed from the request**, returned 3,149
characters of prose.

### 8b. Two blockers found *inside* the verification, fixed rather than worked around

Neither was in the plan; both were discovered because this cycle actually ran the suites and
rebuilt the image, and both would have silently degraded the evidence for everything else:

- **The SDK suite's counts were lying.** `test_loreweave_parse_roundtrip` popped `loreweave_*` out
  of `sys.modules` and never restored them, so a later test compared an exception class against a
  *second copy* of itself. It failed in the suite and passed alone. A suite whose counts move is a
  suite whose counts cannot be used as evidence.
- **Rebuilding composition-service broke it.** The SDK declared `"mcp>=1.27"` with no upper bound;
  `mcp` 2.0.0 removed `mcp.server.fastmcp`, so the service crash-looped on
  `ModuleNotFoundError` with no repo change but the calendar. chat-service and knowledge-service
  were unharmed only because they happen to re-pin `mcp==1.28.1` themselves — the service that
  trusted the SDK's declaration got no protection. Capped at `<2`.

### 8c. Deferred — the documented override is unreachable server-side

`capability_flags.reasoning_control` is the sanctioned way to correct a model this heuristic gets
wrong, and `infer_reasoning_control` checks it FIRST — but `/internal/models/.../info` returns only
`provider_kind` + `provider_model_name`, so the server can never actually pass it. The override
works only for a caller that already has the flags client-side.

~~Deferring under gate #2 (cross-service contract)~~ — **CLEARED in the same session.** The row was
challenged instead of left to age, and the "cross-service contract change" turned out to be one
column added to two SELECTs.

`/internal/models/{source}/{ref}/info` now returns `capability_flags`. Two things the fix had to
get right:

- **The column is a jsonb that is not always an object** — live data holds 58 objects and **5 bare
  JSON `null`s**, the shape that had already broken an ad-hoc `jsonb_object_keys` query during this
  investigation. `jsonObjectOrEmpty` renders anything non-object as `{}` so no consumer re-derives
  that defence per language; the Python side re-checks the type rather than trusting the peer.
- **Nothing sensitive is exposed** — checked against live rows, not assumed: `_capability`,
  `_display_name`, `_is_recommended`, `vision`, `extended_thinking`. Secrets live on
  `provider_credentials`; the route stays internal-token-gated.

Proven live in both directions: setting `reasoning_control: "effort"` on the real gemma row flipped
the classification from `suppress / suppress_unclassified / none` to `effort / rule_based / medium`
**with no code change and no client hint**, and removing it flipped it back. The Go integration
test was actually run against the throwaway `loreweave_provider_test`, covering NULL flags, the bare
json-null, and a `reasoning_control` round-trip.

**Not a blocker for this change:** with the registry now supplying the kind, the heuristic's
local-unknown branch fails safe, so a wrong guess costs a disabled `think` rather than an empty
billed draft. The override matters for the opposite direction — a user who WANTS thinking on an
unclassified local model — and they can still get it by choosing an explicit effort.
