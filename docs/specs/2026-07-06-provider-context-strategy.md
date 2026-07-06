# Provider Context Strategy — capability-gated stateful caching

**Date:** 2026-07-06 · **Branch:** `feat/context-budget-law` · **Status:** SPEC (design; not yet built)
· **Size:** XL (cross-service: chat-service + provider-registry + `loreweave_llm` SDK + DB migration;
Context Budget Law's Planner/Compiler seam). **Author checkpoint:** design resolved with the user
(architecture + 12 edge cases + monitoring), phased build to follow.

---

## 1. Problem & evidence

The context-explosion investigation
([`docs/eval/context-budget/context-explosion-investigation-2026-07-06.md`](../eval/context-budget/context-explosion-investigation-2026-07-06.md))
found that a 20-turn / 8K-content chat burned ~1.4M input tokens on local Gemma-26B-A4B: a fixed ~24K
tool-schema base is re-sent on **every** LLM call, and the tool-loop **sums** `(N+1)×~30K` per turn.
The shipped fixes (hot-seed token-budget, activated-tools cap, Anthropic `cache_control`,
`llm_call_count` observability) cut the base and made caching work **where the provider supports it**.

But the decisive lever was found by **live-testing the provider APIs directly** (2026-07-06):

| API (LM Studio :1234, model = gemma-4-26b-**a4b**) | Req 1 | Req 2 (same context) |
|---|---|---|
| `/v1/chat/completions` (what we use today) | cached_tokens 0 | cached_tokens **0** — no reuse |
| `/v1/responses` + `previous_response_id` | cached_tokens 0 | **cached_tokens 1711 / 1727 (99%)** |

The **stateful Responses API caches 99% of prior context on the exact A4B model** that LM Studio bug
#1563 says can't prefix-cache on chat/completions. Server-side response-chaining (explicit KV state)
works where prefix-hash matching fails. This is the industry-standard stateful optimization and the
real solution to per-turn re-prefill — for the providers that support it (OpenAI + LM Studio today).

**This spec adds a capability-gated stateful-caching strategy WITHOUT abandoning the unified path.**

## 2. Guiding principles (what does NOT change)

- **Unified transport stays the baseline.** Every provider MUST work via the normalized
  chat/completions path (the provider-registry's job). Stateful is an *option*, never a requirement.
- **Provider-gateway invariant holds.** All provider I/O stays inside `provider-registry`; chat-service
  never speaks a provider API directly. The Responses transport is a new adapter *there*.
- **DB stays the source of truth.** `previous_response_id` is an ephemeral optimization hint, never
  authoritative state — the message history in Postgres is. Any id failure rebuilds from DB.
- **Capability, not provider name.** Strategy selection keys on a declared *capability*
  (`responses_api`, `prompt_cache_control`), not `if kind == "lm_studio"` — OpenAI also has Responses;
  keying on the name is the "model-picked-in-8-places" smell the repo forbids (closed-set discipline).
- **Proven-by-effect.** Caching is not free (write premium). It must be *monitored and proven to help*
  (hit-rate / thrashing), or it's silently costing money — the repo's no-silent-no-op rule applied to $.
- **Two-layer split — already the established pattern.** chat-service already branches on
  `creds.provider_kind` for Anthropic (`use_anthropic_cache`, [`stream_service.py:2230`](../../services/chat-service/app/services/stream_service.py)),
  marking the cacheable **system** prefix via `build_system_message(use_cache=…)`; provider-registry
  shapes the provider **request**. We extend this exact split.

**The load-bearing principle:** **chat-service owns CONTEXT POLICY (semantic: what's the stable prefix,
stateful-or-not, what's the delta, when to compact/re-chain); provider-registry owns TRANSPORT (how to
express it for this provider's API).**

## 3. Capability model

Provider-registry maps `provider_kind → capabilities` (a static, code-owned table — no per-user knob):

```
anthropic         → { prompt_cache_control: true }
openai            → { responses_api: true, auto_prefix_cache: true }
lm_studio         → { responses_api: true, auto_prefix_cache: true }   // live-verified
vllm / openai-compat → { auto_prefix_cache: true }                     // server-side, send nothing
ollama            → { auto_prefix_cache: true }
```

- Exposed to chat-service on `ProviderCredentials.capabilities` (new field, resolved when the
  credential is looked up — the same path that already yields `provider_kind`).
- `auto_prefix_cache` = "the server caches automatically; send nothing" (OpenAI/vLLM/LM-Studio
  chat/completions) — informational (drives monitoring, not request-shaping).
- Deploy kill-switch `LLM_PROMPT_CACHE=0` (existing) disables ALL caching strategies (falls back to
  plain unified). A second `LLM_STATEFUL_CACHE=0` can disable *only* the stateful strategy (keeping
  Anthropic cache_control) for staged rollout.

## 4. ContextStrategy — chat-service policy layer

A `ContextStrategy` interface (chat-service) selected per-turn by the **Planner** (the Context Budget
Law policy owner — extends its existing "Planner owns the SEED / the compaction plan" role):

| Strategy | Selected when | Behavior |
|---|---|---|
| `StatelessFullContext` (default) | no special capability | today's behavior: rebuild the full message array from DB, send via chat/completions |
| `AnthropicPromptCache` | `prompt_cache_control` | today's `use_anthropic_cache`: mark the system prefix; provider-registry marks tools (§8) |
| `StatefulResponses` | `responses_api` AND a valid chain id AND `LLM_STATEFUL_CACHE` on | send `previous_response_id` + the **delta** (new user turn + this turn's grounding); server holds the prefix |

The Planner records the chosen strategy on the turn's Inspector frame (§6). Selection is deterministic
+ degrade-safe: any strategy failure falls back one step toward `StatelessFullContext`.

## 5. Transport layer — provider-registry

- **`responsesAdapter`** (new): speaks `/v1/responses`. Builds `{model, input, previous_response_id?,
  tools?, stream:true}`; parses the Responses SSE (`response.output_text.delta`,
  `response.function_call_arguments.delta`, `response.completed` carrying `id` + `usage`).
  `ResolveAdapter` routes here when the request carries the stateful marker + the credential has
  `responses_api`.
- **Tool loop over Responses (E2):** a `function_call` output → the next call in the chain submits
  `function_call_output` with `previous_response_id` = the prior response's id. The whole turn's
  tool-loop is a chain; the FINAL id is returned to chat-service as the session chain head.
- **SDK contract (`loreweave_llm`):** `StreamRequest` gains optional `previous_response_id: str | None`
  and `stateful: bool`. When set, the SDK routes to the responses transport. Additive — the
  chat/completions path is byte-identical when unset. (The SDK schema + the Go adapter move together —
  machine-contract discipline.)
- **Usage:** Responses `input_tokens` INCLUDES cached (live: 1727 = 1711 cached + 16 new) → parse as-is;
  additionally capture `input_tokens_details.cached_tokens`. (Contrast: Anthropic `input_tokens`
  EXCLUDES cached — already folded in `anthropic_streamer.go`, commit 676f31c23.)

## 6. Edge cases (simulated → resolved)

| # | Edge case | Resolution |
|---|---|---|
| E1 | `previous_response_id` invalid (LM Studio restart / `lms` reload / TTL / different instance) | DB is truth; id is a hint. A "response not found" error → **re-establish**: send full context once from DB, get a fresh id, continue. Degrade-safe, transparent. |
| E2 | Tool-loop within a turn (the `(N+1)×base` explosion) | Chain **inside the turn** (each iteration's `previous_response_id` = prior). Server keeps KV warm → the re-send collapses. Turn's final id = next turn's chain head. |
| E3 | `find_tools` activates new tools (tool surface changes mid-conversation) | `tools` ride each request in the chain; changing them misses only the *tools* slice, **history stays cached**. Fix #1 keeps the hot-seed stable → changes are rare. |
| E4 | Grounding changes per turn (volatile context) | Grounding is part of the current turn's delta; prior grounding lingers server-side (additive lore, low-harm for a novel assistant). Re-chain only on a **hard** context change (story_state delta, model/settings switch). |
| E5 | Compaction (the cost↔accuracy tension) | Run stateful until **near the window limit**, then **re-chain with OUR intelligently-compacted history** (fresh id) → continue. No mid-window re-send cost; deliberate (not lossy-by-overflow) truncation. **Resolves the tension.** |
| E6 | Multi-device | Self-hosted single instance → id valid across devices. Cloud/multi-instance → id won't route → E1 re-establish. |
| E7 | Branch / edit-and-resend (`branch_id`, `parent_message_id`) | The chain is linear; a branch = a **new chain** from the fork. Track the id per `(session_id, branch_id)`. |
| E8 | Reasoning models (`reasoning_content`) | The Responses API holds reasoning items server-side → not re-sent; keeps reasoning context warm. |
| E9 | Cost accounting | Responses `input_tokens` already includes cached → parse as-is; capture `cached_tokens`. Bill full = conservative (platform keeps the read discount) — same policy as Anthropic. |
| E10 | Provider without Responses (Anthropic / vLLM / ollama) | Capability-gated → `AnthropicPromptCache` or `StatelessFullContext`. |
| E11 | Streaming shape differs | `responsesAdapter` parses the Responses SSE event types. Transport-local. |
| E12 | SDK/StreamRequest contract | Add `previous_response_id` + `stateful`; SDK routes to the responses transport; unset = byte-identical chat/completions. |

## 7. Caching cost-monitoring + thrashing (the guardrail)

Caching is **not free**: Anthropic `cache_creation` is billed at **1.25×** (a 25% write premium),
`cache_read` at **0.1×**. If the cached prefix keeps *changing*, you pay the write premium every turn
and never read it back → **net loss** ("thrashing"). Monitoring exists to *prove caching helps*, per
the repo's proven-by-effect rule.

**Data model (per turn, persisted alongside usage):**
- `cache_creation_tok`, `cache_read_tok`, `uncached_input_tok` (Anthropic) / `cached_tok` + `uncached`
  (Responses/OpenAI). Sourced from the provider-registry usage split — extend the `Usage` type to carry
  the split through to chat-service + usage-billing (today `anthropic_streamer.go` folds it into
  `InputTokens`; keep the fold for billing volume BUT also emit the split for monitoring).
- Derived: **hit_rate** = read / (read + create + uncached); **cost_delta** = naive_cost − actual_cost
  (negative ⇒ caching is *losing*); **write_premium_paid** = create × 0.25.
- **Thrashing detector:** over a rolling window of N turns, `create ≫ read` (e.g. read/create < 0.5 for
  ≥3 turns) → WARN "prompt cache is net-negative — the prefix isn't stable" (points ops at Fix #1 /
  a re-chain misconfig).

## 8. Inspector extension + §11a gate

Extend the `contextBudget` frame (`context_budget_event` / persisted `context_breakdown` — the same
frame that carries `llm_call_count` from the explosion-fix #5) with a `caching` section:

```
caching: {
  strategy: "stateless" | "anthropic_cache" | "stateful_responses",
  create_tok, read_tok, uncached_tok, hit_rate, cost_delta_usd,
  thrashing: bool,
  chain: { id_present: bool, rechained_this_turn: bool }   // stateful only
}
```

- Inspector UI per turn: *"cached 92% (read 1711 / wrote 16 tok) · saved $A"* or *"⚠ paid $B
  write-premium, 0 reads — thrashing"*.
- `scripts/context-inspector-checklist-gate.py` (§11a) gains a proof-bound row: the caching metrics
  must be asserted by a test that drives a real cached turn and checks the split is surfaced (not a
  stored-but-unread blob).

## 9. Cache-aware context management (Planner/Compiler)

The Context Budget Law's Planner becomes cache-aware — it already owns strategy selection (§4), now
also:
- **Budget/compaction trigger in stateful mode is computed on the SERVER-SIDE accumulated size**
  (chat-service tracks Σ tokens since the last re-chain), NOT the per-turn delta. Today the trigger is
  `estimated_tokens > 0.75 × effective_limit` on the *assembled* prompt
  ([`compaction.py:58`](../../sdks/python/loreweave_context/compaction.py) `COMPACT_TRIGGER_RATIO`); in
  stateful mode the assembled prompt is just the delta, so without this change the trigger never fires
  and the model overflows.
- **Compaction now carries a cache-write penalty.** Compacting rewrites the prefix → invalidates the
  cache → the next turn pays a full cache-write. So the Planner compacts **less eagerly** when caching
  is active (re-tune the T2 trigger by cache state; a compaction is no longer "free space reclamation").
- **Re-chain = the Planner's intelligent compaction at the window boundary** (E5): when the server-side
  size approaches the window, the Planner compacts with its smart policy and resets the chain (fresh id)
  — the ONE place lossy truncation happens, deliberately, instead of on model overflow.

## 10. Reconcile the shipped Anthropic caching (found during this design)

chat-service **already marks `cache_control` on the system prefix** (`use_anthropic_cache` →
`build_system_message`), and the shipped `applyAnthropicPromptCache`
([`provider/prompt_cache.go`](../../services/provider-registry-service/internal/provider/prompt_cache.go))
*also* marks system — a redundant breakpoint. **Fix:** provider-registry marks **tools only** (which
chat-service cannot reach — tools are converted in the adapter); chat-service keeps the system marking
(it owns the semantic boundary). Two coordinated breakpoints, no overlap. (Small, do in Phase 1.)

## 11. Phasing

- **Phase 1 (no new transport — safe, immediate value):** capability model on `ProviderCredentials`;
  cost-monitoring data model + thrashing detector; Inspector `caching` section + §11a gate; reconcile
  §10 (tools-only). All on the *existing* stateless/anthropic paths. Ships the *observability + the
  Anthropic fix* with zero stateful risk.
- **Phase 2 (stateful transport):** `responsesAdapter` + SDK `StreamRequest` fields; DB column
  `previous_response_id` per `(session, branch_id)`; `StatefulResponses` strategy with E1 re-establish
  + E2 in-turn tool chaining. Behind `LLM_STATEFUL_CACHE` (default off first, flip after live-smoke).
- **Phase 3 (cache-aware Planner):** server-side budget for stateful; compaction write-penalty tuning;
  re-chain-at-boundary (E5).

## 12. Verification

- **Phase 1:** unit tests for the split/hit-rate/thrashing math; Inspector frame test asserts the
  caching section is populated + surfaced (proof-bound, §11a); reconcile test asserts provider-registry
  marks tools-only.
- **Phase 2:** live-smoke on the running LM Studio — a real chained turn returns `cached_tokens > 0`
  (the 99% we measured), and an invalidated id (kill/reload) transparently re-establishes. A/B the
  per-turn input tokens stateless-vs-stateful on a real book chat (target: the ~148K tool-turn → the
  delta + cached).
- **Phase 3:** eval that stateful + re-chain keeps answer quality (no lossy-overflow) while cost drops,
  on the `docs/eval/context-budget/` harness.

## Standards touched

Provider-gateway invariant (transport stays in provider-registry ✓); Settings & Config Boundary
(capability = a provider fact + deploy kill-switches, not a per-user knob ✓); Context Budget Law
(Planner owns strategy + cache-aware budget — extends the Planner/Compiler seam); no-hardcoded-model
(capability keyed on kind, not model literal ✓); machine-contract (SDK schema ↔ Go adapter move
together). Not touched: tenancy (no new user-scoped table — `previous_response_id` is per-session state
already scoped by the session's owner), MCP-first.
