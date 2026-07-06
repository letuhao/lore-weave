# P2 Stateful Transport — architecture design

**Date:** 2026-07-06 · **Branch:** `feat/context-budget-law` · **Status:** DESIGN (awaiting sign-off
before P2.c build) · Elaborates [`2026-07-06-provider-context-strategy.md`](2026-07-06-provider-context-strategy.md)
§5/§6 · **Depends on:** P2.a transport (shipped `d1f967ab2`), P2.b migration (written).

This design answers the open question **"does stateful need a special gateway route?"** and specifies
the full stateful-chain lifecycle before the risky hot-path build (P2.c).

---

## 1. The route question — decision: NO special route

**Decision: stateful rides the EXISTING `/internal/llm/stream` route via the `stateful` flag** (what
P2.a built). A dedicated `/internal/llm/responses` route is rejected.

**Why.** The gateway already abstracts *wire differences between providers behind ONE route*: Anthropic
speaks `/v1/messages` with a different SSE shape, OpenAI/LM-Studio speak `/v1/chat/completions` — and
there is **no per-provider route**; `ResolveAdapter` picks the adapter and the adapter owns the wire.
Stateful `/v1/responses` is the **same kind of difference** — a transport the adapter handles — so it
belongs behind the same route, selected by capability, exactly like the SSE-shape difference is.

A parallel route would **duplicate every cross-cutting concern** `doLlmStream` already owns: auth,
rate-limit, **billing + usage recording**, cancellation/job registration (`stream_job_id`), the tools
support-guard, model resolution, the SSE prelude, and provider-gateway routing. That duplication is
pure drift risk for zero semantic gain — the operation is still `chat`, same model, same billing, same
trace. The only genuinely-new surface is **additive to the shared envelope**, not a new route (§4):
a response-id OUT and one new error code IN.

**Observability is preserved, not lost:** same usage/billing/trace, PLUS the P1 `caching` frame already
labels the strategy (`stateful_responses`) and carries the cache split — a stateful turn is already
distinguishable in telemetry without a distinct route.

> If, after this rationale, a dedicated route is still preferred for operational reasons, that is a
> conscious call to make here — but the recommendation is the shared route.

## 2. Two-layer architecture (unchanged split, made concrete)

```
chat-service  (CONTEXT POLICY — owns the chain)          provider-registry (TRANSPORT)
─────────────────────────────────────────────           ──────────────────────────────
StatefulResponses strategy:                              doLlmStream (shared route):
 • select (capability ∧ flag ∧ own LLM_STATEFUL_CACHE)    • gate stateful (cap ∧ flag) else strip
 • read chain head (chat_messages.response_id)            • ResolveAdapter → openai/lm_studio
 • build DELTA input (not full history)          ──────▶  • adapter.Stream: isStatefulRequest →
 • thread previous_response_id through tool loop            streamViaResponses → /v1/responses
 • capture response_id from Done, persist head    ◀──────  • Done carries ResponseID (chain head)
 • E1 re-establish on CHAIN_NOT_FOUND                     • CHAIN_NOT_FOUND error code on invalid id
```

**Load-bearing principle (spec §2):** the PROVIDER holds the KV/context state (keyed by
`previous_response_id`); **chat-service holds the AUTHORITATIVE state** (Postgres history) and treats the
chain id as an ephemeral, degrade-safe hint. Any id failure rebuilds from DB. The gateway/adapter is
**stateless per call** — one `/v1/responses` request per SDK `stream()`; it never manages a chain, only
forwards the id it's given and returns the id it got.

## 3. Chain lifecycle — the state machine

A "chain" is per `(session_id, branch_id)`. Its head is the newest `chat_messages.response_id` for that
pair (P2.b). Per-turn:

```
                    ┌─────────────── establish (no head, or re-chain) ───────────────┐
   turn start       │  send: FULL context (system+history+user+grounding)             │
   read head R  ───▶│         stateful=true, previous_response_id=None                 │──▶ get R0
   (nullable)       └────────────────────────────────────────────────────────────────┘
        │
        │ head R present ──▶ continue:
        │        send: DELTA only (new user msg + this turn's grounding)
        │              stateful=true, previous_response_id=R                      ──▶ get R1
        ▼
   ┌── in-turn tool loop (E2) ──────────────────────────────────────────────────┐
   │  response requests tool → chat-service executes → next call:                 │
   │  send: [function_call_output items], previous_response_id = the JUST-returned │
   │        id (R0/R1/…)                                          ──▶ get R_next   │
   │  repeat until no tool call. The turn's FINAL id = the chain head to persist.  │
   └──────────────────────────────────────────────────────────────────────────────┘
        │
        ▼  persist: assistant row.response_id = final id     (next turn reads it as head)
```

**Establish vs continue is decided by chat-service** from the presence of a head, NOT by the gateway.

## 4. The ONLY new API surface (both additive to the shared envelope)

1. **`response_id` OUT** — on the terminal `DoneEvent` (P2.a: `StreamChunk.ResponseID` → openapi
   `DoneEvent.response_id` → SDK `DoneEvent.response_id`). Already built.
2. **`LLM_RESPONSE_CHAIN_NOT_FOUND` IN** — a DISTINCT error code the gateway emits when the provider
   rejects `previous_response_id` (e.g. LM Studio restart / `lms` reload / TTL / different instance
   returns 404 "previous response not found"). chat-service catches exactly this to E1-re-establish;
   any OTHER upstream error propagates as today. **New work for P2.c/gateway:** the responses adapter
   must classify the provider's "previous response not found" HTTP/SSE error into this code (map in
   `ClassifyUpstreamHTTP` or the responses SSE `response.failed` handler), and `errors.py`/openapi must
   register it. Without this distinct code, E1 can't fire precisely and a stale id would surface as a
   generic error → broken turn.

Everything else (model, messages→input, tools, usage, billing, cancellation) is unchanged.

## 5. Delta construction rules (chat-service — the sharp part)

What chat-service puts in each `/v1/responses` call:

| Call | `previous_response_id` | `input` (messages) | `instructions` (system) |
|---|---|---|---|
| **Establish** (no valid head) | None | full: history + user turn + grounding | **current system, every call** |
| **Continue** (valid head) | head R | delta: new user turn + this turn's grounding only | **current system, every call** |
| **Tool-loop step** | just-returned id | `[function_call_output]` for the executed tools | **current system, every call** |

**System prompt → always `instructions`, never chained (solves the system-change trap).** The Responses
API does NOT inherit `instructions` across `previous_response_id` — they are per-request. So we send the
**current** system prompt in the `instructions` field on EVERY call (establish AND continue). This (a)
makes a mid-session system-prompt change take effect immediately without a re-chain, and (b) keeps the
system OUT of the chained `input`, so the "delta" is purely conversational. Cost is trivial (system ≪
history) and it is the idiomatic Responses usage. `buildResponsesBody` must move system from an input
item to the `instructions` field.

**Flag-consistency invariant (the conversation-safety rule).** chat-service sends a DELTA only when it
is CERTAIN the stateful path is live. Certainty = `creds.capabilities.responses_api` **AND** chat-service's
OWN read of `LLM_STATEFUL_CACHE` (same env the gateway gates on, same deploy) **AND** a valid head (§5a).
If any is false, chat-service builds the FULL context and sends stateless — never a bare delta the gateway
might run stateless. The gateway's strip-on-mismatch (§P2.a) is defense-in-depth, not the primary guard.

## 5a. Head validity & re-chain triggers (the correctness core — solves 4 traps)

A stored `chat_messages.response_id` is a valid head to CONTINUE from **only if ALL** hold; otherwise the
chain is stale and chat-service must **establish fresh** (full context, `previous_response_id=None`):

1. **It is the LATEST assistant turn's id** for `(session, branch)` — i.e. the most-recent assistant
   message carries a non-NULL `response_id`. *(Trap A2/G1/E6: an intervening STATELESS turn — flag was
   off, or a degrade, or a concurrent multi-device fork — leaves a newer assistant row with a NULL
   response_id, or a second assistant row after the head. The provider's chain does NOT contain that
   turn. Continuing from an older head would silently DROP the intervening exchange. Rule: the head must
   BE the newest assistant turn; any newer stateless/forked turn ⇒ re-establish, which self-heals the
   drift from DB truth.)*
2. **Same model** — the head-producing row's `model_ref` == this turn's `model_ref`. *(Trap A3: a chain
   is model-specific; sending an id from model A to model B is invalid / wrong-context.)*
3. **No compaction since** — `chat_sessions.compacted_before_seq` did not advance past the head turn.
   *(Trap G1: compaction rewrites the DB history; the provider chain still holds the UN-compacted full
   history. To apply the compaction we must re-establish with the compacted context.)*
4. **Under the window** — the head turn's provider-reported `input_tokens` (= the accumulated server-side
   size) is below the compaction trigger (`COMPACT_TRIGGER_RATIO × effective_limit`). *(Trap A5/E5: the
   chained context grows every turn and WILL overflow. When it nears the window, re-establish with the
   current — existing-W3-compaction-bounded — DB history, resetting the accumulation. This is the P2
   safety guard; the Phase-3 Planner makes the compaction smarter, but P2 must not overflow.)*

This consolidates the model-switch, stateless-interleave, compaction, and overflow cases into ONE
predicate evaluated at turn start. Cheap: it reads the latest assistant row (id, model_ref, input_tokens)
+ the session's `compacted_before_seq` — columns already present.

## 6. Edge cases — concrete mechanics

| # | Case | Mechanic |
|---|---|---|
| **E1** | invalid `previous_response_id` | provider rejects (404/400) → gateway classifies into `LLM_RESPONSE_CHAIN_NOT_FOUND` → chat-service catches (like the D8 tools retry at stream_service:952), rebuilds FULL context, resends with `previous_response_id=None`, gets a fresh head. One transparent re-establish. **The provider's exact error shape (status + body) MUST be probed live first** (P2.d step 0) so the classifier matches it and doesn't mis-map a real error into a silent re-establish (or vice-versa). |
| **E2** | in-turn tool loop | the EXISTING chat-service tool loop; each iteration threads `previous_response_id` = the prior response's id and captures the new one. Tools still execute in chat-service (approvals/scoping intact). FINAL id = persisted head. |
| **E4** | grounding changes per turn | grounding rides the current turn's delta; prior grounding lingers server-side (additive, low-harm for a novel assistant). Re-chain only on a HARD change (system/model/settings). |
| **E5** | window boundary (Phase 3) | when server-side accumulated size nears the window, the Planner compacts intelligently → `previous_response_id=None` + compacted-full → fresh chain. P2 supports the MECHANISM (establish path); the smart trigger is Phase 3. |
| **E7** | branch / edit-and-resend | head is per `(session, branch_id)` (P2.b index). A new branch has no head → establishes its own chain. Linear per branch. |
| **E6** | concurrent multi-device turns on one session | two devices read the same head → both chain onto it → provider FORKS; DB persists both assistant rows. The §5a rule-1 ("head must be the LATEST assistant turn") means the next turn sees >1 recent assistant turn ⇒ re-establish → self-heals from DB truth. Worst case: one turn's context is briefly absent from the provider chain until the next re-establish (DB never loses it). Same race class as stateless `sequence_num`; rare; accepted. |
| **model / system switch** | model_ref change ⇒ §5a rule-2 re-establish. System-prompt change ⇒ handled WITHOUT re-chain by always sending `instructions` (§5). |
| **compaction (W3 / auto)** | §5a rule-3: `compacted_before_seq` advancing ⇒ re-establish with the compacted history (the provider chain still had the un-compacted full; re-establish applies the compaction). |
| **overflow / unbounded growth** | §5a rule-4: server-side accumulation nears the window ⇒ re-establish with the (W3-compaction-bounded) current history. P2 safety guard against overflow; P3 makes the compaction smarter. |
| **frontend-tool suspend + stateful** | a stateful turn that suspends for a frontend tool (chat_suspended_runs holds the FULL `working` list) RESUMES by re-establishing — the resume already sends the full working context, so it starts a fresh chain and persists the new head. No new suspended-runs column for P2; the cache benefit is simply forgone for that one resume. |
| **budget meter vs delta (Inspector)** | in continue-mode the ASSEMBLED prompt is just the delta, but `used_tokens` is taken from the provider-reported `input_tokens` (= the true accumulated server-side size, incl. cached) — so the budget/overflow trigger is CORRECT. The per-category `breakdown` (computed from the delta) will sum to LESS than `used_tokens`; the gap == `caching.read_tok` (the cached server-side history). Documented, not a bug; the caching section reconciles it. |
| **billing of cached re-reads** | a stateful tool-loop reports `input_tokens` incl. the cached context on every iteration; summed, this over-counts real cost. Billed at full rate = CONSERVATIVE (spec E9 — platform keeps the cache discount). Same fold as P1. Accepted. |

## 7. Failure & degrade modes (all fall back toward stateless — never break a turn)

- Capability absent / flag off → StatelessFullContext (full context, chat/completions). No delta ever.
- Chain id invalid → E1 re-establish (full context once, fresh id).
- Provider transient error → existing retry/propagate path (unchanged).
- `response_id` missing on Done (provider quirk) → persist nothing; next turn establishes fresh.
- DB read of head fails → treat as no head → establish. DB is truth; the id is a hint.

## 8. What's built vs. what P2.c needs

**Built (P2.a + P2.b):** the `/v1/responses` adapter transport, capability+flag gate, `response_id`
return channel, SDK contract, the `response_id` column + chain-head index.

**P2.c — gateway:** (a) move system → `instructions` in `buildResponsesBody` (§5); (b) classify the
provider's "previous response not found" (shape probed in P2.d step 0) into
`LLM_RESPONSE_CHAIN_NOT_FOUND` (responses adapter error mapping + `errors.py` + openapi). Small.

**P2.c — chat-service (the hot-path policy):**
1. `StatefulResponses` strategy selection (capability ∧ own-read of `LLM_STATEFUL_CACHE` ∧ valid head).
2. **Head-validity check (§5a)** at turn start — the 4-part predicate (latest-turn ∧ same-model ∧
   no-compaction-since ∧ under-window); invalid ⇒ establish. This is the correctness core.
3. Delta construction per §5 (establish = full+system-instructions; continue = delta+system-instructions).
4. Thread `previous_response_id` through the tool loop; capture `DoneEvent.response_id` each step; the
   FINAL id (post-tool-loop) is the head.
5. Persist the turn's final head onto the assistant row's `response_id`.
6. E1 re-establish on `LLM_RESPONSE_CHAIN_NOT_FOUND` (one retry, full context).
7. (model/system/compaction/overflow re-chain all fold into the §5a head-validity check — no separate code.)

## 9. Verification plan

- **Unit (chat-service):** strategy selection truth table (cap×flag×head); delta-vs-full builder;
  E1 re-establish path (mock a CHAIN_NOT_FOUND → asserts full-context resend with id=None);
  head-persist + head-read round-trip.
- **Unit (gateway):** the responses error→`LLM_RESPONSE_CHAIN_NOT_FOUND` mapping.
- **Live-smoke (P2.d):**
  - **Step 0 (probe, BEFORE coding the classifier):** POST `/v1/responses` to LM Studio with a bogus
    `previous_response_id` → record the exact status + body, so `LLM_RESPONSE_CHAIN_NOT_FOUND` matches
    reality. Also confirm `store:true` + `previous_response_id` chaining works and the tool-call
    `call_id` round-trips.
  - **Main:** with `LLM_STATEFUL_CACHE=1`, a 2-turn chat where turn 2 sends delta + head → the persisted
    `caching` frame shows `read_tok > 0` (the 99%, the nonzero proof P1 couldn't reach).
  - **E1:** kill/reload LM Studio mid-session (`lms` reload) → next turn transparently re-establishes,
    no user-visible break, and a fresh head is persisted.
  - **Head-validity:** force a stateless turn in the middle (flag toggle) → confirm the following turn
    re-establishes (rule-1) rather than dropping the stateless turn's exchange.

## 10. Standards touched

Provider-gateway invariant (transport stays in provider-registry ✓); Settings & Config Boundary
(capability = provider fact; `LLM_STATEFUL_CACHE` = deploy kill-switch, read consistently by both
layers ✓); machine-contract (the new error code + `response_id` move across openapi ↔ SDK ↔ Go
together); Context Budget Law (Planner owns strategy selection + delta policy). No new user-scoped
table (chain head is per-session state already owner-scoped).
