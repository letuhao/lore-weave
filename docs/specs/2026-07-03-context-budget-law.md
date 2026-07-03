# Spec: Context Budget Law + Session Compiler — **v2**

**Status:** DRAFT (DESIGN, post adversarial-review) · **Date:** 2026-07-03 · **Size:** XL
**Supersedes:** v1 (same file). v2 folds two cold-start adversarial reviews (runtime + Law/contract) and adopts a **tier-by-tier build with per-tier validation gates**.
**Related:** [[llm-client-first-tool-refactor]], [[writing-studio-fragmented-not-underbuilt]], [[compaction-resume-path-carries-tool-pairs]], [[default-model-per-capability-byok]], [[agent-gui-loop-needs-live-browser-smoke-not-raw-stream]]

> Build discipline (user-locked 2026-07-03): **build in tiers, prove each tier's effectiveness in isolation before combining.** Each tier below has its own before/after measurement and a GATE that must pass before the next tier integrates. This is how we evaluate and improve each part instead of shipping one opaque blob.

---

## 1. Problem (grounded)

The chat agent has **no per-request context planning**: `stream_service.stream_response` (≈1614–1707) is a straight-line **unconditional concat** of system + full skill bodies + a rebuilt-every-turn RAG block + history. There is measurement (`token_budget.context_breakdown`) and a reactive overflow guard (`compaction.py`, trigger `0.75 × whole model window`), but **nothing reads session state and decides what to compile under a budget**.

**The 146K case study (one real turn — "change this scene's status to drafting"):**
1. `composition_list_outline` dumped the **entire** outline (1 arc + 12 ch + ~36 scenes w/ full synopses, ~40–55K tok) — the agent was forced to, because `outline_node_update` needs `expected_version` and there's no cheap single-node version read. **← response bloat.**
2. `json.dumps(payload)` at [stream_service.py:907](../../services/chat-service/app/services/stream_service.py#L907)/[:1154](../../services/chat-service/app/services/stream_service.py#L1154) defaults `ensure_ascii=True` → Vietnamese `Lâm Uyển` → `Lâm Uyển`, ~2–3× inflation. **← the `\uXXXX` tax.**
3. Two full skill bodies (glossary + KG, ~5–6K tok) for a task touching neither.
4. `build_context` grounding (5 passages + 12 entities, [stream_service.py:1349](../../services/chat-service/app/services/stream_service.py#L1349)) for a turn needing zero lore.
5. A tool-contract error triggered the expensive recovery ([[llm-client-first-tool-refactor]]).

Every abstract failure mode is visible in **one** request → we need a **repo-wide discipline**, not a one-off fix.

---

## 2. Goals / Non-goals

**Goals:** a repo-wide, **correctly-enforced** rule set governing MCP tool returns + prompt assembly; a **Planner + Compiler** layer enforcing an absolute, **task-elastic** budget; an actionable GUI monitor; cut the 146K-class baseline ≥60% on a typical turn **without degrading answer quality on weak local models** (measured).

**Non-goals:** rebuild long-term memory (knowledge-service already IS the archival/recall tier); adopt an external memory framework (see §4); touch the background/deployed-agent path (chat agent only).

**Corrected from v1:** prompt caching is **NOT** wholly moot — the code has a live **Anthropic prompt-cache path** ([stream_service.py:1618–1660](../../services/chat-service/app/services/stream_service.py#L1618), `cache_control: ephemeral` on system + each skill body) and the test account runs Claude/gpt-4o. So per-turn gating that varies the cached prefix is a **cost regression on the paid path** — see D12.

---

## 3. Prior art (studied)

- **MemGPT/Letta** (`arXiv:2310.08560`) — *main context* (bounded) vs *external context* (unbounded); **memory blocks** `{label, description, value, limit, read_only, version}` rendered with live `chars_current/limit` shown to the model; **FIFO queue + recursive summary head**; block overflow → **self-correcting error**, never silent; JIT paging tools (`archival_memory_search(query, tags, page)`).
- **Cline** — trigger `max(window−40k, window×0.8)`; truncate-middle keeping the **first exchange** anchor; **Auto Compact** summarize as a separate tier; **reversible dup-read collapse** (raw kept, compacted view replayed at send, persisted); **Focus Chain** — task-state `.md` re-injected every 6 msgs, **surviving compaction**.
- **Anthropic — context engineering** — smallest high-signal token set; **just-in-time retrieval** (mirrors human indexing); **compaction**; **agentic memory**; **sub-agent isolation** (explore 10K+, return 1–2K); **tool-result clearing**.
- **MCP token optimization** — two costs: **schema bloat** (we already fixed via `find_tools`) + **response bloat** (our gap). Fix: reference-first + field selection + concise wire.

---

## 4. Build vs. integrate → **BUILD (borrow design, not dependency)**

Mem0/Zep/Letta call LLM/embeddings **directly** → violate the **provider-gateway invariant**; Letta discourages proxy endpoints + has a hardcoded-embedding leak (#3210); all assume single-user vs our tenancy. We already own the "disk" (knowledge-service). We build the **MMU/pager** natively (every LLM/embed via provider-registry, tenancy-scoped), borrowing the *designs*: block model, recursive queue summary, Focus Chain, reversible collapse.

---

## 5. Architecture

Two responsibilities, **one layer, two phases** (NOT the same thing — locked 2026-07-03):

- **Context Planner** = POLICY. Given session state + turn intent + budget → a **CompilePlan** (include grounding? which skill/surface? history depth? which blocks? tool seed? retrieval mode? task-weight). This is where L4/L5 policy lives; it's where we "turn the knobs."
- **Session Compiler** = MECHANISM. Given the CompilePlan + state → materialize the prompt (render blocks, serialize L3, enforce the budget, run compaction/collapse). This is where L1/L2/L3 enforcement lives; deterministic.

```
SessionState(SSOT in DB) + intent + budget
        │  ┌──────────────┐ plan           ┌───────────────┐ compile
        └─▶│   Planner    │───CompilePlan──▶│   Compiler    │──▶ ephemeral prompt (messages + tools)
           └──────────────┘                 └───────────────┘
                  │ JIT pull (tools, model-tier elastic)
                  ▼
   EXTERNAL CONTEXT (unbounded, NOT prepended): knowledge-service (PG SSOT + Neo4j + salience) · glossary · composition
```

**Tier model of the main context:** System(persona) · **Core Memory Blocks** (`persona`,`steering`,`focus`,`story_state`) · **Recall** (recent turns + rolling summary) · **Tools** (seed + `find_tools` union). Archival = knowledge-service, pulled JIT.

---

## 6. THE CONTEXT BUDGET LAW — restructured by **enforceability** (key v2 change)

v1's mistake: it made all 6 rules a "lint," but "returns bounded bodies" is **not statically decidable** across Go/Py/TS → the lint would only check *signature presence*, not *honoring* → a rubber-stamp (the exact silent-no-op class the repo bled on with `ui_open_studio_panel`). So enforcement is split three ways:

### 6a. Ratify NOW as a lint (regex/AST-decidable, real teeth)
- **L3 — Concise wire.** Tool-result serialization uses `ensure_ascii=False`, no indent, omits null/empty/default fields. *(Checkable at every `json.dumps` tool-result site.)*
- **Cross-cutting — self-correcting, never silent.** Any reject / overflow / drop returns an actionable error/notice, never a silent no-op or silent truncation. *(Already our Frontend-Tool-Contract standard.)*

### 6b. Standard + **per-tool contract-snapshot test** (NOT a lint)
Reuse the existing `frontend-tools.contract.json` machinery (record real output for a fixture, assert `len ≤ limit` and no full-body fields under `detail=summary`). A lint can only verify the `limit`/`detail` **params exist**; only a snapshot test proves the body **honors** them.
- **L1 — Reference-first, content-on-demand.** A tool returning a *set* returns `{id, title, ≤1-line, version}` by default; full content via `get_by_id`. **Exemption:** inherently-small returns (a status, a count, a single ≤N-byte item set — e.g. `list_canon_rules`) annotate `@small_return` and are exempt. The exemption is honesty-checked by the snapshot test, not the lint.
- **L2 — Granularity + bounds.** `detail: summary|full`, optional `fields` allow-list, mandatory `limit` (default + hard max). **Single-object reads (`get_by_id`) are exempt from the `summary` default.** **Migration:** version the flip — ship `detail` defaulting to **`full`** with a deprecation notice, and let the **chat-compiler pass `detail=summary`** while federated/legacy callers keep `full`; flip the global default only after consumers migrate. *(Avoids the unversioned breaking change across the federated MCP surface.)*

### 6c. Compiler behavior + tests (NOT an invariant — runtime, verified by §9)
- **L4 — Grounding & skills intent-gated** (see D2/D4/D12). **L5 — Absolute, task-elastic budget + tiered proactive compaction** (see D3/D7). **L6 — Expensive exploration isolated in a sub-agent** returning a distilled summary.

---

## 7. Key design decisions (folded from adversarial review)

**D1 — Retrieval mode is model-tier-elastic.** The Law mandates the *tool contract* (refs + `get_by_id`) universally, but the *assembly policy* adapts to the session model: **weak local (≤~30B) → `prepend`/`hybrid`** (grounding gist stays in context); **strong (Claude/gpt-4o) → `pull`** (JIT). Rationale: JIT push→pull is strictly harder for a 7B model → confident confabulation; we never degrade a weak-model answer to buy tokens the strong model didn't need. `story_state` summary is **always prepended** as the safety net regardless of mode.

**D2 — Intent gate = entity-presence + heuristic-only (NO LLM classifier).** Gate on "does the message contain a known glossary/entity token for this book?" (the salience substrate — latest branch commit — already tracks entity access), **not** on surface verb. Rationale: "change status of **Lâm Uyển's arc**" is a confident-wrong false-negative for a verb heuristic; entity-presence catches it. **Bias to include.** Heuristic-only sidesteps the provider-gateway trap (empty `user_default_models` → no model to resolve). Feedback metric: if a "no-lore" turn then calls `memory_search`, log it = a measurable false-negative rate + optional re-inject.

**D3 — Budget is task-elastic within a surface band.** The Planner emits a `task_weight`; the content allowance scales `[floor, surface_max]` (status-op → floor; "rewrite whole chapter" → surface_max with the chapter body **whitelisted as a required contributor**, not a compaction victim). A single per-surface number can't serve both extremes.

**D4 — Continuity invariant: blocks project every turn, before the gate.** `story_state`/`focus` are projected **unconditionally every turn**; the intent gate controls only the *expensive `build_context` pull*, never the always-on blocks. When grounding is materialized, the Compiler **distills load-bearing entities/facts into `story_state`** — so gating a follow-up turn ("make it darker") never strips the lore the rewrite still needs. *Grounding may be gated; the block projection may not.*

**D5 — `story_state` is cached, refreshed on cadence.** It's a `chat_session_blocks` row refreshed only on a trigger (every N turns, scene change, or an explicit "lore needed" gate), else projected from cache for free. Rationale: refreshing every turn = the always-on `build_context` round-trip we're killing, reintroduced.

**D6 — Load-bearing facts live in blocks, not the prose summary.** Established hard facts/decisions are extracted into `focus`/`story_state` (which never truncate); the lossy weak-model rolling summary is a *convenience*, not the system of record. Summarize with a **fact-preserving extractive prompt** (list entities/decisions verbatim, then prose). Raw evicted turns stay in Postgres → give the agent a `conversation_search` fallback so a fact lost from the summary is recoverable by pull.

**D7 — Single-item overflow + reasoning budget.** A tool result that alone exceeds a per-contributor ceiling is rejected at the tool with a self-correcting error (`"chapter is 12K tok > 8K cap; use detail=summary or a block range"`) or summarize-on-ingest. The model's own reasoning/output is budgeted against the target too (the 146K case had reasoning bloat).

**D8 — Planner owns the SEED; it does NOT post-filter the active set.** The Planner subsumes `discovery_seed_for_surface` + `surface_hot_domains` + skill selection **together** (fixing the skill↔hot-domain coupling), then hands off to the **existing `find_tools` union loop untouched**. It **never removes a tool the model already discovered this turn** (that would loop find→drop→find). `find_tools` is **never gated**. The L5 token target **folds into** the existing `write_passes`/`MAX_TOOL_ITERATIONS` governor — no second parallel budget.

**D9 — Tenancy on Core Blocks.** `chat_session_blocks` carries its **own `owner_user_id NOT NULL`** and filters on `session_id AND owner_user_id` (matching every sibling table — not join-only). OCC version mismatch (multi-device) → **self-correcting error** to the agent (re-read + re-apply), never silent last-writer-wins. **Grantee `story_state`:** knowledge `build_context` is owner-only today (grantee → `ProjectNotFound` → empty story_state); for now **document owner-only + grantee falls back to JIT `memory_search`** (which IS grant-gated); a VIEW-grant-aware build is a separate, deferred scope.

**D10 — Provider-gateway compliance.** Intent gate is **heuristic-only** (no model → no hardcode trap). If a summarizer LLM is wired (L5/D6), it resolves via a **per-user provider-registry default** ([[default-model-per-capability-byok]] pattern: add a `summarize` capability default), never an env var or literal; both new call sites are added to the `ai-provider-gate` allowlist review.

**D11 — Enforcement split** = §6 (L3 lint / L1-L2 contract-snapshot + versioned flip / L4-L6 behavior+tests).

**D12 — Cache-aware skill gating.** Keep skill selection **by surface** (cache-stable, as the code already does via `resolve_skills_to_inject`) on the Anthropic cache prefix; the per-turn *intent* gate must **not** vary the cached prefix. (Fixes the paid-path cost regression.)

**D13 — Atom + resume invariants.** (a) The reversible-collapse transform operates on **whole tool-exchange atoms** and preserves every `tool_call_id ↔ role:tool` pairing (reuse `_atoms`/`_recent_tail`; add an orphan-free contract test — the [[compaction-resume-path-carries-tool-pairs]] bug class). (b) **Resume-monotonicity:** within a suspended→resumed turn the compiled prompt is monotonic — the intent-gate decision + block snapshot are **frozen at turn start**, and anything the model already saw (tool results, grounding) is **pinned** for the rest of that turn, never re-gated/re-collapsed.

---

## 8. Tiered build plan (each tier: isolated, measured, GATED before the next integrates)

| Tier | Scope | Isolated validation | GATE to pass |
|---|---|---|---|
| **T0 — Wire hygiene (L3)** | Funnel the ~14 `stream_service.py`/`voice_stream_service.py` tool-result `json.dumps` sites through ONE `_tool_result_content` helper (`ensure_ascii=False` + drop-empty) — 1 file, fixes all 94 tools (§14a); the L3 lint | Replay the 146K turn; measure token delta on VI/CJK content | ≥ target token cut proven on the replay; L3 lint green |
| **T1 — Tool response contract (L1/L2)** | `detail/fields/limit` + reference-first on the **~32 SET-returning tools ranked by measured bytes×freq** (§14b; port the knowledge byte-histogram to composition/translation/jobs first), worst-first; per-tool contract-snapshot + one live-e2e each (§14c); versioned default (compiler passes `summary`, federated keep `full`); cheap single-node version read | Per-call token delta on the ranked offenders; snapshot green; federated caller still gets `full` | worst-offender token cut proven; **zero consumer regression** |
| **T2 — Budget meter + target** | `compute_budget` vs an absolute target; GUI monitor upgrade. **Measure-only first**, then flip compaction to fire at target | Meter accuracy vs provider-reported tokens; does compaction fire at target (not window)? | meter within ±X%; compaction triggers at target |
| **T3 — Planner/Compiler extraction (into shared kernel)** | Extract assembly into the shared **`sdks/python/loreweave_context`** kernel (§12), NOT a chat-local module; chat = first consumer wiring the ports; **behavior-preserving** (byte-identical, no policy yet); Planner owns the tool seed (D8) | Golden test: output identical to pre-refactor on a fixture set; full chat suite green; kernel imports no provider SDK | byte-identical + suite green + kernel provider-gate clean |
| **T4 — Core Memory Blocks** | `chat_session_blocks` (`focus`,`story_state`) w/ `owner_user_id`+OCC (D9); always-on projection (D4); cadence+cache (D5). **No gating yet.** | Continuity: a follow-up turn still carries `story_state` lore; block token cost ≤ ceiling; refresh cadence works; OCC conflict → self-correcting | continuity proven **with blocks as the safety net**; block cost bounded |
| **T5 — Intent gate + elastic policy** | Entity-presence heuristic (D2); retrieval-mode by model-tier (D1); task-elastic budget (D3); cache-aware skill gating (D12). Built ON the T4 net. | False-negative rate (entity-presence accuracy on a labeled set); **answer-correctness on lore-needing turns** (weak model); token savings vs T4 baseline | answer-correctness ≥ baseline **AND** token savings proven |
| **T6 — Compaction upgrades** | Atom-safe reversible collapse + resume-monotonic (D13); fact-preserving summary + `conversation_search` fallback (D6); single-item overflow (D7) | Atom integrity (no orphan, contract test); resume stability (recompile == pre-suspend); fact-preservation on a 40-turn eval | no orphan; resume-stable; load-bearing fact survives |
| **T7 — Sub-agent isolation (L6)** *(defer-eligible)* | Planner/extractor/multi-step reads → distilled summary | tokens in vs summary out; quality unchanged | — |
| **FINAL — integrate** | All tiers on, end-to-end | Full evaluation on the 12-ch POC book: compose quality unchanged, tokens down, answer-correctness maintained ([[prefer-e2e-and-evaluation-over-live-smoke-poc]]) | end-to-end eval passes |

**T0–T1 are shippable immediately and independent of the contested tiers.** T4 must land before T5 (the block safety net is what makes gating safe). Each GATE is a real measurement, not a checkbox.

### 8a. Measured tier results (updated as tiers land)

> **Sequencing decision (2026-07-04, sealed #2 re-decide after T0–T2):** the numbers show T1 (reference-first) is the dominant lever and the remaining chat-agent wins are in T4+T5 (block net + intent-gating). Since **T3 is a byte-identical refactor with no direct token win**, and §12b mandates *proving the kernel interfaces against ONE consumer (chat) before extracting*, the build order is **reordered to T4 → T5 (policy built + live-validated in chat-service) → T3 (extract the proven Planner/Compiler into `loreweave_context`) → Inspector GUI → T6.** T4–T6 are confirmed worth building (that is where the remaining bloat — irrelevant skills/grounding per turn — is cut).

- **T2 — GATE MET (2026-07-04), measure-only.** Added the task-elastic **soft target** (`compute_target`: `floor=min(6K,0.1×win)` → `surface_max=min(32K,0.35×win)`, slid by `task_weight`; sealed #4) + `ContextBudget.target`/`pct_of_target`, emitted additively in the `contextBudget` frame (default `task_weight=1.0` ⇒ surface_max ⇒ **behavior unchanged** — the compaction *flip* is correctly sequenced AFTER T4's block safety net, per §8). Forward-declared the Inspector allocation categories (`summary`/`chapter`/`reasoning`, present-0 until their tier lands). **Meter-accuracy GATE — clean live calibration PASS** (`scripts/context-budget-t2-live-calibration.py`, gemma-4-12b `prompt_tokens` ground truth): estimator within **±22%**, median **1.13** — errs **HIGH (safe** for a compaction trigger). **Key lesson:** the persisted-corpus comparison (`context-budget-t2-meter-accuracy.py`) reads as a spurious −27% *under*-estimate purely from the reasoning/tool-arg token confound; the live probe reversed it, so **no recalibration** (a naive 1.15× bump would have broken it to +35%). token_budget suite 28 + full chat suite 824 green. **Deferred (tracked):** per-tool A5 byte histograms → fold into the Inspector allocation-map telemetry; compaction-fires-at-target flip → after T4.
- **T1 — GATE MET (2026-07-04); remainder manifest-tracked.** Flagship + `jobs_list` refactored + the reusable helper proven cross-service; the other ~28 SET tools are worst-first backlog in [`context-budget-t1-refactor-manifest.md`](context-budget-t1-refactor-manifest.md) (silent-cap tracked). A5 byte histograms folded into T2; response-shape snapshot harness into the §13 CI check. Reusable L1/L2 helper `apply_response_contract` added to the shared `loreweave_mcp` kit (reference-first + `detail`/`limit`/`fields` + never-silent `{total,returned,truncated}` meta; kit-tested). Flagship offender `composition_list_outline` now takes `detail=summary|full` (default `full` — versioned, zero regression) + `limit`; NEW `composition_get_outline_node` exposes the cheap single-node version read that was missing (the 146K forced-dump root cause). **Live-e2e GATE PASS** (`scripts/context-budget-t1-live-e2e.py`, real 48-node outline through ai-gateway federation, test account): `list_outline` **full 53,222 B → summary 13,673 B (−74.3%)**; `get_outline_node` returns one node+version in **538 B** vs the 53 KB forced dump (**−99%** for the update-needs-version case). Contract guard `test_outline_response_contract.py` (prose dropped, version kept) + kit tests green; composition unit suite 1477 green. **Remaining T1:** replicate to the other ranked SET tools (knowledge `story_search`/`memory_search`/`kg_*_query`, translation `list_versions`, jobs `jobs_list`) + port byte histograms (A5) for data-driven ranking + the response-shape contract-snapshot harness (§13b).
- **T0 — SHIPPED (2026-07-04).** L3 funnel `tool_result_content()` (`ensure_ascii=False` + drop-`None`) wired at all 14 model-facing tool-result `content` sites in `stream_service.py`; L3 lint (`scripts/context-budget-l3-lint.py`) green; helper unit-tested (`tests/test_tool_result_wire.py`, 10 tests). **GATE measurement** (`scripts/context-budget-t0-measure.py`, over 244 real persisted tool results in dev `loreweave_chat`): **−3.6% bytes / −3.6% est-tokens repo-wide** (24 KB unicode-unescape + 29 KB null-drop, ~even split). **Key finding:** the 146K bloat was dominated by response **structure** (the full outline dump), NOT unicode escaping — so T0 is the cheap zero-risk baseline (one file, all 94 tools) and the large reduction lives in **T1** (reference-first / `detail=summary` on the SET-returning tools). Unicode win scales to 30 %+ on VI-prose-dense results (unit-proven); diluted on the structural-JSON corpus. Voice path confirmed to have **no** tool-result funnel sites (its dumps are SSE/persistence).

---

## 9. Verification
- **Every tier:** the GATE in §8 (numbers, not assertions) + unit tests. Cross-service tiers (T1, T5, T6 touch chat↔composition/knowledge) get a live cross-service smoke.
- **T0 anchor:** the 146K turn replayed on the live stack (test account, local LM Studio) is the standing benchmark across tiers.
- **T5/FINAL:** answer-correctness needs a small **gold Q&A set** over the POC book (lore-needing questions with known answers) — the metric v1 lacked. Tokens-down alone would score a fluent confabulation as a pass.

---

## 10. Sealed decisions (user-approved 2026-07-03)

1. **Retrieval mode = `prepend`/`hybrid` for ALL by default.** `pull` (true JIT) is deferred to a future strong-model capability; the Law still mandates the tool contract (refs + `get_by_id`) universally. Removes most T5 risk on local models.
2. **Tier scope = commit T0–T3; re-decide T4–T6 after seeing T0–T2 real numbers.** No blind commitment to all tiers.
3. **T4 = `story_state` only first** (auto-projected, no agent-write tool). `focus` deferred to a later tier.
4. **Budget = fraction-of-window + absolute cap, tuned from T2.** `surface_max = min(32K, 0.35×window)`, `floor = min(6K, 0.1×window)`; **soft target triggers compaction, hard ceiling = model window (never exceeded).**
5. **`story_state` refresh cadence** = on lore-gate OR scene/chapter change OR fallback every 5 turns; cached otherwise.
6. **Grantee `story_state` = owner-only + collaborator JIT `memory_search` fallback** (grant-gated). VIEW-grant-aware build is deferred, separate scope.
7. **Answer-correctness gold set** = agent drafts ~10–15 lore-needing Q&A from the POC book's glossary/outline; **user validates**.

Agent-resolved (front-loaded 2026-07-03 — all in **Appendix A**, no re-investigation at implementation): **entity-presence index (D2) = RESOLVED BUILDABLE** via glossary-service `/internal/books/{id}/known-entities` + in-process cache, no new table (A3); the `frontend-tools.contract.json` snapshot machinery mapped for reuse (A6); the L3 funnel = ~14 sites → 1 helper, all 94 tools (A1/§14a); the tool-discovery seam + assembly surface mapped for T3 (A1/A2); `chat_session_blocks` DDL mirror ready, OCC `version` is the one net-new bit (A4); per-tool byte telemetry chokepoints = one-place per service (A5). Plan-shaping surprises (resume-path frozen assembly de-risks D13; voice second assembly; cache/plain duplication) in **A7**.

**Next action:** T0–T1 (serialization hygiene + `composition_list_outline` projection) are unblocked and measurable on the 146K replay — shippable independent of any contested tier.

---

## 11. Inspector GUI — "Context Compiler · Trace Inspector"

Draft mockup: [`design-drafts/context-management/context-compiler-inspector.html`](../../design-drafts/context-management/context-compiler-inspector.html). The observability tool a power user drives to **trace what context management did per turn** (budget pressure gauge · allocation map · Planner→Compiler trace waterfall · filter + pagination). It reads the per-turn telemetry the compiler emits (this is the FE half of the T2 "GUI monitor upgrade" and the acceptance surface for T2–T6).

**Dockable — LOCKED requirement.** The Inspector MUST be a **dockable studio panel**, openable inside the writing studio (dockview host), not only a standalone page. It follows the studio panel contract: registered in `features/studio/panels/catalog.ts`, added to the `ui_open_studio_panel` enum + `contracts/frontend-tools.contract.json` (so the agent can open it), self-titles via `props.api.setTitle`, mounts-without-unmounting on hide (CSS `hidden`, MVC rule), and is session/book-scoped. It also remains reachable standalone. `panelCatalogContract.test.ts` (studio enum ⊆ dock catalog) must stay green.

### 11a. Implementation checklist (item-level — track BE + FE coverage; do not miss a line)

> Every discrete data/behavior item on the draft. `(BE)` = telemetry/data the compiler or an endpoint must produce; `(FE)` = render/interaction; `(BE+FE)` = both. The BE items double as the **compiler telemetry contract** for T2–T6.

**Telemetry / BE contract (per turn) — emitted by Planner+Compiler, persisted, tenancy-scoped by session→`owner_user_id`:**
- [ ] `raw_tokens` — naive-concat estimate before compile (BE)
- [ ] `compiled_tokens` — actual tokens sent (BE)
- [ ] `target` — task-elastic budget resolved for this turn (BE)
- [ ] `ceiling` — model context window (BE)
- [ ] `reduction_pct` — raw→compiled (BE-derive or FE-derive)
- [ ] `model` name/ref + `context_length` (BE)
- [ ] `intent` label (BE)
- [ ] `entity_presence` — matched entity tokens, or none (BE)
- [ ] `retrieval_mode` — prepend / hybrid / pull (BE)
- [ ] `status_flags[]` — gated / included / compacted / overflow / elastic / continuity / collapsed / wire (BE)
- [ ] allocation map per category: system · blocks · skills · grounding · history · summary · tools · results · chapter · reasoning (BE — extend existing `context_breakdown`; NEW cats: summary, chapter, reasoning, blocks split)
- [ ] compile **trace spans[]** — ordered `{phase, tier(T0–T6), category, action_text, delta_tokens, is_error}` (BE — NEW telemetry)
- [ ] session aggregate: avg reduction %, total tokens saved (BE or FE-aggregate)
- [ ] endpoint: paginated turn-trace list `GET …/context-trace?session&page&filter` (BE)
- [ ] endpoint: single-turn trace detail (BE)
- [ ] all telemetry owner-gated + session-scoped (BE)

**Top bar:**
- [ ] tool title + subtitle (FE)
- [ ] session selector + current session id (FE + BE list-sessions)
- [ ] KPI: avg reduction % (FE)
- [ ] KPI: total tokens saved (FE)
- [ ] KPI: model window (FE)

**Turn list (left rail):**
- [ ] search input — filter by user message + intent (FE)
- [ ] status filter: all (FE)
- [ ] status filter: gated (FE)
- [ ] status filter: compacted (FE)
- [ ] status filter: overflow (FE)
- [ ] status filter: elastic (FE)
- [ ] per-turn: turn id (FE)
- [ ] per-turn: reduction % + threshold color (FE)
- [ ] per-turn: user message snippet (FE)
- [ ] per-turn: mini budget bar (compiled vs target) + over-target color (FE)
- [ ] per-turn: compiled/target numbers (FE)
- [ ] per-turn: status chips (cap 2) (FE)
- [ ] selected/active highlight (FE)
- [ ] pagination: prev (FE)
- [ ] pagination: next (FE)
- [ ] pagination: page label (page/total + count) (FE)

**Inspector header:**
- [ ] turn id badge (FE)
- [ ] full user message (FE)
- [ ] intent chip (FE)
- [ ] entity-presence chip (FE)
- [ ] retrieval-mode chip (FE)
- [ ] model chip (FE)

**Hero — context pressure gauge:**
- [ ] semicircle gauge fill = compiled (FE)
- [ ] target tick mark (FE)
- [ ] color state: under / over-target / over-ceiling (FE)
- [ ] gauge center: compiled number + target label (FE)
- [ ] raw tokens number (FE)
- [ ] compiled tokens number (FE)
- [ ] reduction % number (FE)
- [ ] full status chips list (FE)
- [ ] gauge fill transition animation (FE)

**Allocation map:**
- [ ] allocation total (FE)
- [ ] segmented bar — width ∝ tokens per category (FE)
- [ ] segment grow-in animation (FE)
- [ ] hover tooltip: category label + tokens + % (FE)
- [ ] legend row per category: color swatch + label + tokens (FE)
- [ ] 10 category colors defined + stable (FE)

**Compile trace (waterfall):**
- [ ] trace filter: all (FE)
- [ ] trace filter: planner (FE)
- [ ] trace filter: compiler (FE)
- [ ] trace filter: saved-only (FE)
- [ ] per-span: phase badge (planner/compiler) (FE)
- [ ] per-span: tier tag T0–T6 (FE)
- [ ] per-span: category dot (FE)
- [ ] per-span: action text (FE)
- [ ] per-span: delta bar (width ∝ |delta|; color save/include/reject) (FE)
- [ ] per-span: delta value (+ / − / reject / ·) (FE)
- [ ] per-span: error/reject red state (FE)
- [ ] empty state when filter yields no span (FE)

**Interactions / behavior:**
- [ ] click turn → load inspector (FE)
- [ ] keyboard j/k turn navigation (FE)
- [ ] any filter resets page to 0 (FE)
- [ ] mount-without-unmount on hide (CSS hidden — MVC rule) (FE)
- [ ] split volatile per-turn state vs stable session state (re-render rule) (FE)
- [ ] loading / empty / error states (FE)
- [ ] live update as new turns arrive — SSE or poll (FE + BE)

**Dockable studio integration:**
- [ ] register panel in `features/studio/panels/catalog.ts` (FE)
- [ ] add panel id to `ui_open_studio_panel` enum (FE + BE `frontend_tools.py`)
- [ ] regenerate `contracts/frontend-tools.contract.json` (BE+FE)
- [ ] panel self-titles via `props.api.setTitle` (FE)
- [ ] panel session/book-scoped from studio context (FE)
- [ ] standalone route also available (FE)
- [ ] `panelCatalogContract.test.ts` green (studio enum ⊆ dock catalog) (FE)

---

## 12. Reusability — the Context Kernel as a shared standard

**Motivation (user-raised 2026-07-03):** context assembly is NOT chat-only, and "not making it a standard = certain death" (user). Confirmed and near-term consumers:
- **Role-play agent** — the confirmed second consumer. Verified in code: `services/roleplay-service` is a **thin Rust domain/orchestration service with NO LLM calls** (`src/lib.rs`) — it freezes a scenario into a `charter` + a `working_memory_seed` that **"MUST be byte-compatible with chat-service's `WorkingMemory` model"** (`src/charter.rs`) and **delegates the turn-loop / voice / debrief to chat-service** (the Python loop does the actual context assembly). So role-play's "inheritance" of the chat agent = **delegation + a hand-maintained byte-compatible `WorkingMemory` seed across a Rust↔Python boundary** — a genuine cross-language-contract-drift risk the standard exists to formalize. Strong fit: the kernel's **Block / working-memory anchor** model was *originally built for roleplay* (`stream_service.resolve_anchor`, the "interview-roleplay" anchor, `working_memory_seed`) — persona + character + charter state ARE core-memory Blocks. Under the kernel, role-play becomes a **Block/`ContextSource` configuration inside the shared loop**, and the `WorkingMemory` seed becomes a **defined Block contract** (not a byte-copied shape) — retiring the fragile coupling. A future standalone role-play loop wires the kernel via ports without forking chat-service.
- **`composition-service/app/packer/pack.py`** — a de-facto second *implementation* today (the drafting packer, flagged as a *parallel grounding stack* in review).
- Further: the **background/deployed agent**, the **autonomy critic/drafting** loop, the **extraction** pipeline, "and a whole bunch more like this" (user).

If the compiler is baked into `chat-service`, every consumer clones/forks (or inherits) it → divergence. So it is built as a **shared standard from day one**. With **two confirmed consumers already** (role-play + packer), the extraction is justified, not speculative.

### 12a. Two reusable pieces (they are different, keep them separate)

**A. Context Kernel** — a shared **Python package** `sdks/python/loreweave_context` (the AI/LLM consumers are all Python). It is **provider-agnostic, source-agnostic, tenancy-agnostic** — a pure engine wired to ports by each consumer:
- **Core types:** `Block` (label/description/value/limit/read_only/version), `CompilePlan`, `Budget` (target/floor/ceiling/task_weight), `TraceSpan` (`{phase, tier, category, action, delta, is_error}` — the §11 telemetry), `CompiledContext` (messages + tools + trace + allocation).
- **Core engine:** `Planner.plan(state, intent, budget) → CompilePlan` (policy) and `Compiler.compile(plan, state) → CompiledContext` (mechanism), plus `CompactionStrategy` (tiered: clear→summarize→truncate, atom-safe).
- **Ports (injected by the consumer, never imported by the kernel):** `Tokenizer`, `Summarizer` (LLM), `Embedder` — each the consumer wires to **provider-registry** (honors the provider-gateway invariant; the kernel imports **no** provider SDK, no model literal). `ContextSource` — the plugin that yields candidate content with metadata (category, tokens, salience, references) — chat wires conversation+knowledge sources; composition wires its packer lenses; extraction wires chapter text.
- **Payoff:** every consumer emits the **same `TraceSpan` telemetry**, so the one Inspector GUI (§11) works for ALL of them for free; the budget/compaction/blocks logic exists **once**.

**B. Tool Response Contract** — the L1/L2/L3 discipline (§6b/6a) is **cross-language** (MCP tools are Go + Python + TS), so it is NOT part of the Python kernel: it's a written standard (`docs/context-budget-law.md`) + a small **per-language serialization helper** (`ensure_ascii=false`, drop-empty, reference-first shape) + the **contract-snapshot test** harness. This governs the *edges* (tool returns); the kernel governs the *assembly*.

### 12b. Design-reusable, but validate-with-ONE (the honest caveat)

Building a "framework" before a second real consumer exists is the premature-abstraction trap — but here we have TWO confirmed consumers, so the risk is *over-shaping the interface*, not building it at all. We avoid over-shaping by: **design the interfaces for reuse now, prove them against ONE consumer (chat) before extracting, and resist any port/feature no current consumer needs.** Concretely — **T3 extracts the Planner/Compiler into `sdks/python/loreweave_context`** (not a chat-local module) with `chat-service` as the **first consumer wiring the ports**. The interface is **"proven" when role-play is expressed as kernel Blocks + a role-play `ContextSource`** — its `charter`/persona/`working_memory_seed` become a **defined Block contract** instead of a byte-copied `WorkingMemory` shape, **with no kernel change**. That is the reusability acceptance test (it also *retires* the fragile Rust↔Python seed coupling). The composition packer plugging in as a `ContextSource` is the second proof.

### 12c. Convergence path (don't rewrite, adopt)
Two directions:
- **New consumers build ON the kernel from the start** — the **role-play agent** does NOT inherit chat-service; it is a fresh kernel consumer (its own persona/character Blocks + role-play `ContextSource`). This is the whole point: the next "whole bunch of agents like this" (user) start compliant instead of cloning chat.
- **Existing implementations migrate later (deferred, tracked)** — `composition-service/packer/pack.py` is NOT rewritten now; it is designed to **later become a `ContextSource` + adopt the kernel's budget/compaction/trace** (kernel subsumes its priority-ladder trim; packer keeps its domain lenses). Same for the background agent and the autonomy critic.

A consumer is **"context-kernel-compliant"** when it (1) wires the ports through provider-registry, (2) emits `TraceSpan` telemetry, (3) passes the shared conformance suite. The standard is fixed now so consumers converge instead of diverge; the current role-play-inherits-chat coupling is the anti-pattern it retires.

**Spec impact:** T3 in §8 now reads "extract into the shared `loreweave_context` kernel package, chat = first consumer" (not a chat-local module). The kernel's port interfaces + `TraceSpan` schema are the frozen contract; the Law (§6) applies repo-wide to every MCP tool regardless of consumer.

---

## 13. Enforcing the checklist — definition-of-done as TESTS (not self-report)

**The problem (observed):** a subagent on another track followed its checklist and **still shipped missing implementation.** Root cause: **a checklist is a self-report, and self-reports are the rubber-stamp class this repo repeatedly bleeds on** — the silent-no-op resolver (`ui_open_studio_panel`, f1f9e9966), the lint that checks a param *exists* but not that it's *honored* (§6a rationale), an agent ticking ✓ from INTENT ("I'll add X") not EFFECT ("X is present + proven"). A box with no test bound to it fails **silently**: skipping the item leaves the build green.

**The rule (LOCKED for this effort; generalizes repo-wide):**
> **A checklist item is DONE ⟺ a test asserts it by its EFFECT. An item with no proving test is treated as NOT done — never "trust the implementer."** The §11a checklist is a **coverage manifest**, not a to-do list.

### 13a. Every item carries a proof reference
Each of the 86 lines gets one of:
- `✓test:<id>` — the test that proves it (the default; most items),
- `⊘manual:<reason>` — genuinely un-automatable (visual polish only) — must be the **small minority**, each with a reason.
An item with neither is a **red** in CI (see 13c).

### 13b. Proof mechanism BY ITEM TYPE (reuse existing machinery, don't invent)
- **Telemetry / BE-contract items** → a committed `contracts/context-trace.contract.json` (the required per-turn fields + the `TraceSpan` shape) + a **conformance test that runs a REAL turn and asserts each field is present AND non-null** (a field the compiler forgot to emit → red). Mirror the existing `frontend-tools.contract.json` + `test_frontend_tools_contract.py` pattern — do NOT hand-roll a new one.
- **Cross-side items** (panel enum ⊆ dock catalog; resolver reads every arg) → the existing **cross-language contract test** (`panelCatalogContract.test.ts`, `frontendToolContract.test.ts`). Drift on either side → red.
- **FE render / interaction items** → a **component/E2E test asserting the EFFECT, not existence**: not "the gauge component renders" but "compiled>target ⇒ gauge shows the over-target color"; "click 'gated' filter ⇒ only gated turns remain"; "`ui_open_studio_panel('context-inspector')` ⇒ the panel actually mounts" (verify-by-effect, per [[agent-gui-loop-needs-live-browser-smoke-not-raw-stream]]).
- **`⊘manual` items** → only pure aesthetics (e.g. animation easing feel). Each names why it can't be a test.

### 13c. CI meta-check (the forcing function)
A small script parses §11a and **FAILS the build if any non-`⊘manual` item lacks a referenced test that (a) exists and (b) is in the passing set.** "Unproven item ⇒ red." This is what makes the manifest un-gameable: you cannot mark the effort done with an item that has no green test behind it. (Same philosophy as `language-rule-lint` failing on a service with no row.)

### 13d. Belt-and-suspenders (catches what tests miss)
- **Adversarial refute-pass:** after the implementer claims a tier done, a **cold-start agent tries to REFUTE each checked item against the code** (default: refuted-unless-proven). The two adversarial reviews in this very spec's history are the evidence this catches real gaps a self-review rubber-stamps.
- **Tier GATES already force a subset:** a tier's *measured* GATE (§8) can't pass unless its items exist — e.g. T2's "meter within ±X% of provider-reported tokens" is impossible unless the telemetry fields (BE items) are actually emitted; T0's "≥ token cut on the 146K replay" is impossible unless `ensure_ascii=false` actually shipped. Bind each checklist item to the tier whose GATE exercises it, so the measurement is a second net under the per-item test.

**Net:** the checklist stops being "did the agent tick the box?" and becomes "does a green test observe the effect, does the CI meta-check confirm every item has one, and did an adversary fail to refute it?" — three independent nets, none of which is a self-report.

---

## 14. MCP tool refactor — scope + targeted e2e live-test (do NOT refactor all)

**Question (user):** with "hundreds" of MCP tools, does the Law force refactoring ALL of them, and if so live-test them all?
**Answer: NO.** Grounded inventory (read-only sweep, 2026-07-03): there are **94 domain MCP tools**, not hundreds — 5 Python FastMCP services (**knowledge 30 + admin 2 · composition 44 · translation 12 · jobs 5 · lore-enrichment 1**), **0 in Go, 0 in the TS gateways** (ai-gateway/mcp-public/knowledge-gateway only *federate/relay*; glossary + book are Go and surface *through* knowledge tools). The refactor is **targeted, not all-94**:

### 14a. L3 (ensure_ascii / concise wire) = ONE place, fixes all 94
The bytes the model sees are NOT serialized by the 94 domain tools — FastMCP returns each tool's `dict` and chat-service **re-parses then re-dumps** it into the provider message at **~14 `json.dumps(payload)` sites in `stream_service.py` (+ `voice_stream_service.py`)**, every one at Python's default `ensure_ascii=True` (the `\uXXXX` tax). So L3 = **funnel those ~14 sites through one `_tool_result_content(payload)` helper with `ensure_ascii=False` + drop-empty** — **one file, one language, zero domain-tool edits, fixes CJK/VI escaping for all 94 tools at once.** (Corrects v2's earlier "one-liner at :907" — it's ~14 sites → 1 helper.) This is **T0**.

### 14b. L1/L2 (reference-first / detail·fields·limit) = ~32 SET-returning tools, ranked by MEASURED bytes
Only **SET-returning** tools (list_/search_/*_query/read-collection) bloat. The ~62 mutation/propose/confirm/single-read tools return small status/token/id payloads → **`@small_return` exempt or already compliant** (no edit). The **~32 targets** (many already carry a `limit` cap — partial plumbing):
- **knowledge (13):** `story_search`, `memory_search`, `memory_timeline`, `memory_recall_entity`, `kg_graph_query`, `kg_world_query`, `kg_multi_query`, `kg_entity_edge_timeline`, `kg_schema_read`, `kg_list_templates`, `kg_view_read`, `kg_triage_list`, `kg_project_list`
- **composition (~13):** `composition_list_outline`, `composition_get_prose`, `composition_get_work`, `composition_list_canon_rules`, `composition_motif_search`, `composition_motif_get`, `composition_motif_book_list`, `composition_motif_link_list`, `composition_motif_suggest_for_chapter`, `composition_arc_suggest`, `composition_arc_import_analyze`, `composition_motif_mine`, `composition_get_generation_job`
- **translation (4):** `translation_coverage`, `translation_list_versions`, `translation_segment_status`, `translation_job_status`
- **jobs (2):** `jobs_list`, `jobs_get`

**Prerequisite (data-driven ranking, not guessing):** knowledge-service ALREADY has per-tool Prometheus `knowledge_tool_call_result_size_bytes{tool_name}` + call-count histograms (`app/metrics.py`, all 30 flow through `execute_tool`). composition/translation/jobs do **not** — so **port that histogram to their executors** (or mine the persisted `tool_calls_json` per message) → rank all 32 by **bytes × frequency** and refactor the worst first. Measured worst offenders to start: the `kg_*_query` graph tools, `story_search`/`memory_search`, `composition_get_prose`/`list_outline`/`motif_mine`, `translation_list_versions`.

### 14c. Targeted e2e live-test checklist (NOT all 94; NOT even all 32 upfront)
Live-e2e is expensive — the **contract-snapshot tests (§13) + byte histograms do the BULK coverage**; live-e2e is the **acceptance proof** for (i) the L3 chokepoint and (ii) each SET-tool actually refactored. Rows (each: `✓test:<live-e2e id>` per §13):

**L3 chokepoint (prove once per distinct service path — CJK/VI content):**
- [ ] live: `story_search` (VI passages) through chat→gateway→knowledge → bytes drop ≥40% vs ensure_ascii=true baseline
- [ ] live: `composition_list_outline` (VI synopses) → same
- [ ] live: `translation_list_versions` (VI text) → same
- [ ] (one per remaining service path if its results carry CJK/VI)

**Per REFACTORED SET-tool (only the ones actually refactored this pass — start with the ranked top offenders):**
- [ ] live: `kg_graph_query` — `detail=summary`/`limit` returns bounded refs, not full node+edge tree; token drop measured; `get_by_id` fetches full on demand
- [ ] live: `kg_world_query` / `kg_multi_query` — bounded cross-book union
- [ ] live: `memory_search` — reference-first snippets, `limit` honored
- [ ] live: `composition_get_prose` — `detail=summary` (no full chapter body unless asked)
- [ ] live: `composition_list_outline` — `{id,title,status,version}` refs, no synopses at `summary`
- [ ] live: `composition_motif_mine` — bounded output
- [ ] live: `translation_list_versions` — no full translated bodies at `summary`
- [ ] … one row per additional SET-tool as it is refactored (the 32-list above is the backlog; rows are added when the tool is picked up, gated by its measured rank)

**Explicitly NOT live-tested:** the ~62 small/mutation tools (contract-snapshot + `@small_return` lint covers them) and any SET-tool not yet refactored (still covered by the byte histogram showing it's below the refactor threshold). Silent-cap rule (§CLAUDE.md): if a tool is deferred below the threshold, `log()` it in the refactor manifest so "not refactored" ≠ "forgotten".

**Scope summary:** L3 = 1 file (all 94). L1/L2 = ~32 tools, ranked by measured bytes, worst-first. Live-e2e = the L3 chokepoint samples + one per refactored SET-tool. Everything else = lint + contract-snapshot + telemetry. This fits the existing tiers: **14a = T0, 14b = T1**, both already GATE-measured on the 146K replay + the byte histograms.

---

## Appendix A — Grounded code map (front-loaded 2026-07-03; do NOT re-investigate at implementation)

Everything an implementer needs to start each tier without re-reading the codebase. All `file:line` verified by read-only investigation. **Surprises that shape the plan are in A7 — read them first.**

### A1. Prompt ASSEMBLY surface (T3 — Planner/Compiler extraction contract)
`chat-service/app/services/stream_service.py`, `stream_response` (def **1592**), assembly between session load (**1651**) and `_emit_chat_turn` (**2200**).
- **System message is built TWICE** in lockstep: Anthropic **cache path** (`parts`, **1971–2012**) and **plain-string path** (`system_parts`, **2014–2044**). 12 blocks in identical order in both; a new block goes in BOTH ladders. The Compiler should collapse these to ONE ordered block list rendered two ways (A7).
- **The 12 blocks (var · cache-line · plain-line):** memory stable `kctx.stable_context` 1972 / `kctx.context` 2015 · memory volatile `kctx.volatile_context` 1978 · wm_pinned 1981/2019 · system_prompt 1988/2021 · steering 1994/2025 · glossary_skill 1996/2027 · knowledge_skill 1998/2029 · universal_skill 2000/2031 · plan_forge_skill 2002/2033 · user_skills 2004/2035 · plan_mode 2006/2037 · skill_meta 2008/2039 · book_note 2010/2041. Insert as messages[0]: 2012 / 2043. Two extra system msgs inserted at `[-1]`: attached context 2047, wm_tail 2050.
- **Block computation** (before the branch): build_context **1700–1707** (target `resolve_grounding_target` 1697); resolve_anchor **1715–1718**; resolve_skills_to_inject **1822–1832** + skill_prompts 1833; plan_mode_block 1843; skill_metadata_block 1849; book_context_note 1881–1895; steering 1904–1924; user_skills + built-in shadow 1932–1964.
- **Inputs:** session_row **1651–1657** (cols: system_prompt, generation_params, project_id, project_ids, composer_model_source/ref, planner_model_ref, working_memory_seed, enabled_tools, enabled_skills, activated_tools, compact_summary, compacted_before_seq); model_source/ref = params 1595; display_language param 1611 (only into build_context); permission_mode param 1615 (skills 1831, plan_mode 1844); reasoning `_resolve_and_stash_reasoning` 1667–1671; history 1742–1762 → messages 1763.
- **tools=** set at **791** (`request_kwargs["tools"]=advertised`, tool_choice 792), recomputed every pass 767–789; seed resolved 2124–2194. **`working`** init `= list(messages)` **668**, grown per pass (assistant turn 904, results at the funnel sites), in-loop re-compaction 725–743.
- **contextBudget/context_breakdown:** `ContextBreakdown(...)` 2066–2092; runtime buckets folded 2648–2650; **persist** `_ctx_payload = context_budget_event(compute_budget(...), context_breakdown)` **2651–2658**, INSERT into `chat_messages.context_breakdown` (`$12`) **2660–2671** — same payload emitted as the `contextBudget` frame.
- **Anthropic cache path** gate `use_anthropic_cache` **1966–1969**; `cache_control:{ephemeral}` markers on stable-memory 1976, system_prompt 1992, steering 1995, glossary/knowledge/universal/plan_forge 1997–2003, user_skills 2005, plan_mode 2007, skill_meta 2009, book_note 2011 (NOT volatile-memory, NOT wm_pinned). (D12: skill markers vary the cached prefix per surface — the intent gate must not vary it per-turn.)
- **L3 funnel — the ~14 tool-result `json.dumps(payload)` sites** (in `_stream_with_tools` unless noted): 970 find_tools · 1013 run_subagent · 1048/1183/1236/1342 subagent errors · 1085 compose_prose · 1123 ask/plan · 1216 hook deny · 1278 planner-cap · **1377 the MAIN backend-tool (MCP execute) result** · resume path 2929/3013/3043. (NOT results: 801 schema estimate; 2624/2628/2641/2645/2670 persistence.)

### A2. tool_discovery SEAM (D8 — Planner owns seed, not the union)
`tool_discovery.py` + `tool_surface.py` + stream_service.
- `ALWAYS_ON_CORE_NAMES` **tool_discovery.py:85–93** (find_tools, ui_navigate, ui_open_book, ui_show_panel, ui_watch_job, propose_record_edit, confirm_action). `surface_hot_domains` **130–143** (studio→{glossary,composition}; book/editor→{glossary}; universal→∅). `_advertise_discovery_tools` **stream_service.py:511–572** (the single per-pass advertise chokepoint; called 768, seed 2172, resume 3108). find_tools union: `active_tool_names.update(matched)` **952**; init from seed **695**.
- **THE SEAM:** the Planner replaces how `discovery_seed_for_surface(...)` (`tool_surface.py:50–80`) produces the seed at the single call site **stream_service.py:2161–2168** (feeds 2172/2236/2463 → `active_tool_names = set(discovery_seed_names)` at 695). It **hands off untouched** to the find_tools union (952) + per-pass advertise (768). Replace seed production; feed the same `set[str]`; the existing selector is unchanged. Skill↔domain coupling: `resolve_skills_to_inject` 1822 + glossary-skill force-unions glossary hot tools (`tool_surface.py:87–98`).

### A3. Entity-presence index (D2) — **VERDICT: BUILDABLE NOW, no new table**
Authored SSOT = **glossary-service** (Go), not knowledge-service.
- **Names + aliases (best for the gate):** internal `GET /internal/books/{book_id}/known-entities` (X-Internal-Token gated) — `glossary-service/internal/api/extraction_handler.go:206–289` (name code `'name'` + `aliases_raw` code `'aliases'`, `min_frequency` default 2, LIMIT 500). Public mirror (Bearer+GrantView, spoiler-windowed): `canon_at_chapter_handler.go:36–155`.
- **Names only (feeds the Tiptap highlighter today):** `GET /v1/glossary/books/{book_id}/entity-names` — `entity_handler.go:1427–1458` (LIMIT 500); FE `glossary/api.ts:237`, wired at `ChapterEditorPage.tsx:405–410`.
- **Build:** chat-service calls the internal known-entities route once per book + caches the token set in-process (invalidate on a glossary-change signal). knowledge-service `entity_access.py`/`salience.py` track by entity **id** (ranking), NOT a name set. **⇒ D2 open question RESOLVED — buildable via an existing endpoint + an in-process cache; no new index/table.**

### A4. `chat_session_blocks` tenancy (T4) — DDL mirror + one net-new bit
Mirror sibling tables in `chat-service/app/db/migrate.py`: `chat_messages` (22–40), `chat_outputs` (45–66), `chat_suspended_runs` (217–242). Pattern: `session_id UUID NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE`, **`owner_user_id UUID NOT NULL`**, PK `UUID DEFAULT uuidv7()`, `created_at/updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `CREATE INDEX ... (session_id)`. Migration idiom: `CREATE TABLE IF NOT EXISTS` in the one `DDL` string (run at 390–393); additive cols via the `DO $$ IF NOT EXISTS(information_schema.columns)` block (84–91, 179–183). Filter idiom (all reads/writes): `WHERE session_id=$1 AND owner_user_id=$2` (mirror `messages.py:170`; owner-scoped precedent `suspended_runs.py:88`; upsert `tool_approvals.py:31–38`). **NET-NEW (no in-service precedent):** the `version INT NOT NULL DEFAULT 1` OCC column + compare-and-set `UPDATE ... SET version=version+1 WHERE ... AND version=$expected` — chat-service has NO Postgres OCC pattern to copy (the only OCC in-repo is glossary's HTTP If-Match). Small, but write it fresh.

### A5. Per-tool byte telemetry chokepoints (T1 ranking prerequisite)
- **Pattern (knowledge, already emits):** `knowledge-service/app/metrics.py` — `tool_call_result_size_bytes` Histogram (label `tool_name`, buckets 64…65536) **514–522**; recorded in the central `execute_tool` `finally` — `app/tools/executor.py:647–650` (`len(json.dumps(result_payload, default=str))`, only on outcome ok). Single chokepoint (`mcp/server.py:309 _dispatch → execute_tool 320`).
- **Port targets (one-place each):** **jobs** — add to the existing `_install_validation_error_rewriter` `call_tool` wrap `mcp/server.py:88–104` (insertion at **:95**); jobs has no `metrics.py` → add one. **translation** — existing wrap `mcp/server.py:102–118` (insertion **:109**); `metrics.py` exists. **composition** — **NO wrap exists**; add the ~15-line `_install_validation_error_rewriter` (verbatim copy from jobs/translation) on `mcp_server._tool_manager.call_tool` (`server.py:80`), then measure inside it; `metrics.py` exists. All one-place, no per-tool `return` edits. Confirmed none of the three emit any tool-size metric today.

### A6. Contract-snapshot harness to MIRROR (§13 enforcement)
- Committed SSOT `contracts/frontend-tools.contract.json` (sorted, indent=2, trailing newline). BE generator+test `chat-service/tests/test_frontend_tools_contract.py`: `_normalize(tool)` reduces to wire-invariant slice (required + per-arg type/enum) **72–84**; **regen gated by env** `WRITE_FRONTEND_CONTRACT=1` → write + skip **130–138**; else `assert on_disk == built` **143–147**. FE lockstep tests read the SAME JSON: `frontendToolContract.test.ts:23` (Proxy get-trap proves each resolver reads every required arg), `panelCatalogContract.test.ts:15` (enum ⊆ catalog). **A new `context-trace.contract.json` + per-tool response-shape snapshot copies this exactly:** a `_normalize`-style reducer over the registry, `WRITE_<NAME>_CONTRACT=1` regen, commit under `contracts/`, consumer test asserts drift.

### A7. Surprises that SHAPE the plan (read before building)
1. **Resume path does NOT re-assemble the system message** — `resume_stream_response` (~2879) rehydrates `working = list(susp.working)` (**2907**), the assembled system block is FROZEN in the suspended run; it re-derives only gen_params + tool_defs. ⇒ **D13 resume-monotonicity is PARTLY already true** (assembly is frozen across suspend); the Compiler must keep persisting the assembled prompt into the suspended run (not re-compile on resume). Also: resume hardcodes `editor=True, book_scoped=True, studio=True` (superset) for skills + seed (2965–2975, 3101–3107) — a deliberate divergence from the fresh path's real surface flags.
2. **Second, divergent assembly in `voice_stream_service.py`** (~300–378): only `kctx.context → wm_pinned → system_prompt → VOICE_SYSTEM_PROMPT → wm_tail` — NO cache path, NO skills/steering/book-note/plan-nudge, NO context_breakdown, build_context WITHOUT `language=`. The Compiler must decide: share it or keep voice a separate minimal path. (T0's L3 funnel must still cover its dumps.)
3. **Cache-path vs plain-path duplication** (A1) is a live footgun — 12 blocks in two independent `if` ladders that must stay in sync. The Compiler is the natural place to unify them (one block list, two renderers).
4. **T4 OCC `version`** is net-new to chat-service (A4) — no query to copy for the compare-and-set guard.
```
