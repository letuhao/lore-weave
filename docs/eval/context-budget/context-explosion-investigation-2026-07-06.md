# Context explosion investigation — book 019f33f1, chat 019f33fd / 019f3420

**Date:** 2026-07-06 · **Reporter:** user (Gemma-26B local run) · **Verdict:** NOT a chat-history
accumulation bug. Two real, quantified causes: **(A) a fixed ~28K-token tool-schema tax advertised on
every LLM call** + **(B) the tool-loop re-sends that catalog on every iteration and sums it**. A
reasoning local model with no prompt caching turns this into ~3M processed tokens + continuous
compaction for an 8K-token conversation.

## Evidence (session 019f33fd, model = Gemma 4 26B A4B QAT, 200K window)

- **Actual conversation is tiny:** 20 assistant + 22 user messages = **~33 KB text ≈ 8K tokens total.**
- **Per-turn `input_tokens` is enormous and correlates with tool-call count, NOT turn number:**

  | tool calls in turn | recorded input_tokens |
  |---|---|
  | 0 | 26,775 – 33,385 |
  | 1 | 57,838 – 80,555 |
  | 2 | 82,654 – 137,476 |
  | 4 | 137,476 |
  | 6 | 148,818 |

  Fits `input_tokens ≈ (n_tool_calls + 1) × ~30K` almost exactly.
- **`context_breakdown.mcp_tool_schemas = 24388` is FLAT across all 20 turns** (frontend_tool_schemas
  = 3854, also flat). Not accumulating → a **fixed base**, present from turn 1.
- **`enabled_tools` and `activated_tools` are both EMPTY** for the session → the 24K is neither
  user-pinned nor `find_tools`-accumulated. It's the **surface hot-seed**.
- **Totals:** 26 tool calls / 20 turns / **summed input_tokens = 1,408,365**. Both given sessions +
  the reasoning model's find_tools/retry sub-calls reach the user's observed ~3M / 67 LLM calls.
- The budget system knows it's over: `pct_of_target: 4.30` (430% of the 32K target), yet the
  `breakdown` categories sum to only ~34K on a 137K turn — the other ~103K is the loop re-send, which
  the per-turn breakdown doesn't attribute.

## Root cause A — the book-scoped hot-seed advertises two ENTIRE domains

`surface_hot_domains(book_scoped=True)` = `_BOOK_SCOPED_HOT_DOMAINS = {"glossary", "story"}`
([`tool_discovery.py:131`](../../services/chat-service/app/services/tool_discovery.py)). `hot_tool_names`
then seeds **every** `glossary_*` and `story_*` tool into the always-advertised active set. The
glossary domain alone is ~64 tools; glossary+story ≈ the **24,388 tokens** measured.

The discovery design (tool_discovery.py header) is sound — `ALWAYS_ON_CORE` is **≤8 tools**, the full
~200-tool catalog is meant to stay lazy behind `find_tools`. But the **per-surface "hot domain"
assumption — that a domain is a handful of tools — breaks for glossary**, which is a ~64-tool domain.
Seeding the whole domain re-inflates the base the discovery mechanism exists to shrink. Result: every
book-scoped chat pays a 24K tool tax on turn 1, before the user has done anything.

(Second, latent amplifier: `find_tools` matches are merged into `activated_tools` up to
`ACTIVATED_TOOLS_CAP = 64` and persisted across turns — so a chat that leans on `find_tools` can grow
a *second* ~24K on top. It happened to stay empty this session, but it's the same failure mode the
user described as "MCP tools loaded too much after find_tools.")

## Root cause B — the tool-loop re-sends the catalog every iteration and SUMS it

`_stream_with_tools` accumulates usage: `total_input += ev.input_tokens` per loop iteration
([`stream_service.py:926`](../../services/chat-service/app/services/stream_service.py)), and records the
SUM as the message's `input_tokens`. A turn with N tool calls makes N+1 provider calls, and **each
call re-sends the full ~28K tool array + the growing tool-call/result/reasoning messages** (OpenAI-
compatible tool calling is stateless — tools ride every request). So the 28K base is paid N+1 times
per turn: seq 22 (6 calls) = 148K, seq 2 (4 calls) = 137K.

## Root cause C — reasoning local model + no prompt caching amplifies both

The model is a local **reasoning** Gemma (`extended_thinking: true`). Two effects: (1) verbose
`reasoning_content` per iteration inflates each call and, kept across the loop, pushes a single turn
toward the `0.75×window` in-loop compaction trigger → the "continuous compaction"; (2) a weaker model
needs MORE tool-loop iterations (extra `find_tools`, retries) than Sonnet → higher N → higher sum.
Crucially, **local inference (lm_studio) has no prompt caching**, so all ~1.4–3M re-sent tokens are
really processed and burned.

## Why Sonnet 200K "rarely compacts" (the user's comparison)

Same 28K tool base, but: (1) **Anthropic prompt caching** makes the re-sent tool+history prefix
~free and fast — the re-send cost that dominates locally nearly vanishes; (2) stronger reasoning →
fewer tool-loop iterations → lower summed input per turn; (3) 28K tools is ~14% of a 200K window
(a non-issue) vs a punishing fraction once a local model's *effective* usable context and the in-loop
reasoning growth are factored in. So the SAME architecture is survivable on Sonnet and pathological on
a local reasoning model.

## Correcting the user's hypothesis

"Next turn accumulates the previous turn's context" — **cross-turn history is NOT the driver**: the
`history` category is 14–1,315 tokens (compaction keeps it small). The accumulation is **within a
turn** (the tool-loop re-send) plus the **fixed hot-seed base**, not turn-over-turn history growth.

## Proposed fixes (highest leverage first — NOT yet built)

1. **Shrink the book-scoped hot-seed from "whole domains" to a curated ≤8–12 tool subset**
   (token-budgeted, not count-unbounded). The glossary/story *skill* names a handful of tools the
   surface truly needs hot; everything else stays lazy via `find_tools`. Cuts the base ~24K → ~4K,
   i.e. a 6-call turn from ~148K → ~40K. Single highest-impact change.
2. **Token-budget the hot-seed + the activated set** (`ACTIVATED_TOOLS_CAP` is a *count* of 64 — cap
   by tokens instead, e.g. ≤6K).
3. **Prompt caching for local models** where the backend supports it (lm_studio / vLLM prefix cache),
   so the re-sent tool+system prefix isn't reprocessed each iteration.
4. **Confirm `reasoning_content` is stripped from the messages carried across loop iterations / turns**
   (kept only for the immediate provider round-trip), so extended-thinking output can't accumulate.
5. **Attribute the loop re-send in `context_breakdown`** so `pct_of_target` and the breakdown reconcile
   (today ~103K is unexplained on a tool turn) — an observability gap that hid this.

## Industry precedent (web research 2026-07-06) — this is a named, well-documented problem

Both root causes are textbook, with established fixes. Our diagnosis matches the literature exactly.

**A. Tool-schema bloat = "the bloat tax" / "MCP tool overload".**
- Standard MCP setups burn **72% of the context window on tool defs before the first user message**;
  one report: 3 MCP servers = 143K of 200K on schemas the agent mostly never calls. Ours (24K/64
  tools on a book chat) is the same class, smaller scale.
- **It degrades QUALITY, not just cost:** the RAG-MCP study measured tool-selection accuracy
  **collapsing 43% → <14%** as the tool set bloats ("context rot", tools blur together). → Shrinking
  our hot-seed should make the *weak local model pick tools better*, not only cheaper.
- **Fixes:** tool-RAG / dynamic loading (vector-index tools, surface only relevant per query →
  "triples accuracy, halves tokens"); **Anthropic shipped "Tool Search" to GA** to bypass bloated
  toolsets; Cloudflare compressed 1.17M tokens of tool defs to 1K. **Our `find_tools` IS this pattern
  — the hot-seed of whole domains is what defeats it.**

**B. Agent-loop token accumulation is a known QUADRATIC cost.**
- "Naive agent loops rebill prior context on every call, so input token cost grows quadratically." A
  5-step task is typically **8–15× a single call** (not 5×); 20-step >10×. The full tool set rides
  every call (e.g. "GitHub MCP 40 tools = 10–15 KB schema per turn"). Our `(N+1)×~30K` is exactly this.
- This **confirms the user's intuition** and their Cursor comparison: the 8–15× multiplier is NORMAL,
  and Cursor's "millions of tokens" are for genuinely LONG tasks (many steps). **Our anomaly is a
  SHORT task (8K content) exploding — caused by the fixed 24K tool base, not the loop itself.**

**C. Prompt/prefix caching is THE mitigation — and explains local-vs-Sonnet.**
- Anthropic prompt caching: **90% discount** on a cached tool+system prefix reused across an agent
  session ("well over 80% of total spend" saved). → why the user's Sonnet "rarely compacts/cheap".
- vLLM/llama.cpp automatic prefix caching: cached tokens **10× cheaper**, prefill can drop **60s →
  200ms** for a stable system/tool prefix.
- **BUT for THIS local model it likely doesn't work:** LM Studio bug-tracker #1563 reports **KV-cache
  reuse is NOT supported for A3B/A4B (MoE) architectures → full prompt recompute every request.** The
  user's model is **Gemma 4 26B A4B** — that exact class. So each of the ~67 calls very likely
  re-prefills the whole 24K tool base from scratch → the pathology. This makes **shrinking the base
  (fix #1) the primary lever for local**, since we can't rely on prefix caching there.

**Sources:**
- [The bloat tax — Agentpmt](https://www.agentpmt.com/articles/thousands-of-mcp-tools-zero-context-left-the-bloat-tax-breaking-ai-agents)
- [RAG-MCP: too many tools become too much context — WRITER](https://writer.com/engineering/rag-mcp/)
- [The MCP Context Window Problem — Junia](https://www.junia.ai/blog/mcp-context-window-problem)
- [10 strategies to reduce MCP token bloat — The New Stack](https://thenewstack.io/how-to-reduce-mcp-token-bloat/)
- [AI Agent Loop Token Costs — Augment Code](https://www.augmentcode.com/guides/ai-agent-loop-token-cost-context-constraints)
- [Anthropic prompt caching deep dive — Agentbrisk](https://agentbrisk.com/blog/prompt-caching-deep-dive-2026/)
- [Automatic Prefix Caching — vLLM docs](https://docs.vllm.ai/en/stable/design/prefix_caching/)
- [LM Studio: KV-cache reuse not supported for A3B/A4B (MoE) — bug #1563](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1563)
- [Host-memory prompt caching in llama-server — llama.cpp #20574](https://github.com/ggml-org/llama.cpp/discussions/20574)
