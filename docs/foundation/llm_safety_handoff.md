# LLM Safety Handoff (cycle 31 L6.L.4)

This document records the foundation → LLM-safety sub-program handoff for the three stubs cycle 31 ships: `IntentClassifier`, `WorldOracle`, `InjectionDefense`.

## What foundation ships (cycle 31)

Three interfaces in `contracts/prompt/`:

| Interface | File | V1 default impl | Q-L6L-1 semantics |
|---|---|---|---|
| `IntentClassifier` | `intent_classifier.go` | `NoopIntentClassifier` → always `IntentSessionTurn` | No-op |
| `WorldOracle` | `world_oracle.go` | `NoopWorldOracle` → returns empty fact list | No-op |
| `InjectionDefense` | `injection_defense.go` | `NoopInjectionDefense` → `Detected: false` | No-op |

All three interfaces are signature-frozen by `contracts/prompt/llm_safety_stubs_test.go` (the `*ShapeFreeze` test enforces compile-time assignability).

## Why foundation ships stubs (Q-L6L-1 LOCKED)

The LOCKED resolution is **"empty (no-op) V1; fail-closed in LLM-safety sub-program"**.

Foundation cannot ship policy without first:

1. Curating a canon of attacks (jailbreak phrases, marker-forgery patterns, instruction-hierarchy bypasses).
2. Classifying benign-vs-malicious — false-positives on benign turns are worse than missed jailbreaks at the foundation layer.
3. Choosing a tokenizer + pattern engine — both belong to the LLM-logic / LLM-safety sub-program scope.

A half-baked fail-closed at foundation would erode user trust + force every service to ship a workaround config to bypass. The foundation surface is a freeze, not a policy.

## What the LLM-safety sub-program owns

When the LLM-safety sub-program lands, it ships concrete impls that:

### IntentClassifier
- Pattern scan + small-model heuristic over `utterance`.
- Detect admin-trigger phrases (so `IntentAdminTriggered` routes correctly).
- Return error only on adversarial input that cannot be safely classified.

### WorldOracle
- Per-reality fact store with a query DSL respecting S2/S3 visibility filters.
- Cache in the prompt-assembly hot path (TTL matches cycle 1 L1.B 5min discipline).
- Deterministic fact resolution (same `(reality_id, keys)` → byte-equal output for replay).

### InjectionDefense (5 layers per S09 §12Y.6)
1. **Input pattern scan** — jailbreak phrases, marker forgery (e.g., a user crafting `<user_input>` literally).
2. **Section boundary check** — defense in depth on top of `DefaultSectionValidator` from cycle 31 L6.H.3.
3. **Canary post-scan** — consume `CanaryDetector` (cycle 31 L6.I.3) + emit `lw_prompt_canary_leak_count`.
4. **Instruction-hierarchy guard** — distinguish template-owned vs user-issued instructions.
5. **Output rejection** — flag model attempting to leak system prompt / bypass tool restrictions.

## How services wire the swap

Services that consume the prompt SDK (cycle 23+ wiring) should:

```go
// At service startup, depend on the foundation interface:
var classifier prompt.IntentClassifier = prompt.NoopIntentClassifier{}
var oracle prompt.WorldOracle = prompt.NoopWorldOracle{}
var defense prompt.InjectionDefense = prompt.NoopInjectionDefense{}

// When the LLM-safety sub-program lands, swap one line per dep:
//   classifier = llmsafety.NewProductionClassifier(cfg)
//   oracle     = llmsafety.NewProductionOracle(realityDB, cache)
//   defense    = llmsafety.NewProductionDefense(corpus, canaryDet)
```

The compile-time assignment in `llm_safety_stubs_test.go` guarantees the swap is type-safe.

## Cycle 31 deferred items

| ID | Note |
|---|---|
| D-LLM-SAFETY-IMPL | Real impls of IntentClassifier + WorldOracle + InjectionDefense. Owner: LLM-safety sub-program. |
| D-PROMPT-COPY | Per-intent template bodies (Q-L6K-1). Owner: LLM-logic sub-program / DF3 / feature team. |
| D-CANARY-METRIC-EMIT | Wire `lw_prompt_canary_leak_count` emit at LLM-gateway adapter layer (foundation ships the metric declaration only). Owner: LLM-gateway sub-program. |

## References

- `docs/plans/2026-05-29-foundation-mega-task/L6_ws_obs_llm_prespec.md` §L6.L (lines 287+)
- `docs/plans/2026-05-29-foundation-mega-task/OPEN_QUESTIONS_LOCKED.md` Q-L6L-1 (line 123)
- S09 §12Y.5 (capability + privacy filter chain)
- S09 §12Y.6 (5-layer injection defense)
