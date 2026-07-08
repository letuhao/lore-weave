# Spec: MCP Tool-Discovery Architecture Fix + Reliability Hardening

**Status:** DRAFT (CLARIFY phase, 2026-07-07), **reframed same day** — §0.5 below demotes this spec's
Layer A fix from "the fix" to "defense-in-depth"; the strategic fix is a new, larger tier (Intent→Skill
routing) tracked as a separate follow-on, not built here. **Size:** XL — spans chat-service, ai-gateway,
mcp-public-gateway, glossary-service, provider-registry-service; touches composition-service for one
item. User explicitly asked for a combined spec across all three evidence layers before any code
changes (2026-07-07): "viết spec/plan tổng hợp cả 3 lớp trước."

**Origin — three independent evidence sources, gathered in one session (2026-07-07):**
1. A live Postgres pull of 4 real `chat_sessions` on THIS running stack (not a synthetic repro) —
   all four are the identical user query, submitted 15:43→15:48 the same day, all effectively
   failed. Full transcripts + tool_calls JSONB pulled from `loreweave_chat` (host `localhost:5555`).
2. An external cold-start MCP discoverability audit against `ai-gateway`'s public MCP endpoint,
   user-supplied, now tracked verbatim at
   [`docs/bugs/2026-07-07-mcp-discoverability-external-audit.md`](../bugs/2026-07-07-mcp-discoverability-external-audit.md).
3. Direct code read of the discovery/search internals on both engines
   (`chat-service/app/services/tool_discovery.py` + `tool_surface.py`, `ai-gateway/src/federation/find-tools.ts`,
   `mcp-public-gateway/src/scope/invoke-tool.ts` + `tool-policy.ts`) plus the web-search test suites
   in `glossary-service` and `provider-registry-service`.

**User's framing (verbatim intent, translated):** the current `find_tools` design has the *wrong
job description*. It should answer "how do I use a tool I already roughly know exists" — instead
it's being used as the *only* way to answer "does a tool exist at all," via a lossy similarity
search, so the agent has to loop guessing phrasings until something scores above threshold. The
token-saving design (lazy discovery instead of shipping ~200 tool schemas every turn) is directionally
right, but the specific mechanism chosen — fuzzy top-K over free-text intent, with no true
enumeration — is the wrong way to save tokens, because it trades reliability for savings instead of
finding both. Combined with an unverified web-search backend and the external audit's 11 findings,
the user's assessment: **the MCP surface is not usable as shipped today** ("test mấy ngày nay, cơ
bản không thể sử dụng").

**Related, not superseded:** [`docs/plans/2026-07-05-search-tool-unification.md`](../plans/2026-07-05-search-tool-unification.md)
(story_search/memory_search merge — a different overlapping-tool problem, already shipped, does not
touch discovery architecture). [`docs/specs/2026-07-06-tool-catalog-simplification.md`](2026-07-06-tool-catalog-simplification.md)
(Part A group-directory + CAT-4 legacy-visibility — this spec's Layer A extends it one level deeper).
[`docs/specs/2026-07-07-skill-authoring-and-mcp-exposure-standard.md`](2026-07-07-skill-authoring-and-mcp-exposure-standard.md)
Part D (hot-domain-derivation refactor, in flight as uncommitted diff at spec time) — **confirmed
orthogonal to this spec's findings**, see §1.0 below. [`docs/standards/mcp-tool-io.md`](../standards/mcp-tool-io.md)
IN-6 ("errors are self-correcting one-liners") — Layer C items #8/#10 are direct violations of this
already-adopted standard, not a new rule.

---

## 0.5. Reframing (same-day, post-CLARIFY discussion): tool search is defense-in-depth, not the fix

A follow-up discussion with the user (2026-07-07, after this spec's first draft) produced a sharper
diagnosis that changes how this whole effort should be prioritized, though it does not invalidate
the work already scoped below.

**The core claim:** `find_tools` (fuzzy, top-K, similarity-scored) can only ever answer "is there a
tool that might match these words" — it cannot answer "given this ambiguous request, what sequence
of steps and tools should I actually run." Those are two different problems (existence-discovery vs.
procedure-selection), and no amount of hardening the first one solves the second. The correct
architecture separates four tiers:

```
User Intent → Skill Selection (which workflow applies) → Workflow (ordered tool sequence) → Tool Calls
```

`find_tools`-style search belongs only at the bottom tier, as a fallback for the long tail a
workflow doesn't already name — never as the *primary* mechanism an agent uses to figure out what to
do with an ambiguous ask.

**Confirmed against LoreWeave's actual code, not just abstractly:**
- The repo already has the right *shape* of Skill tier: `SkillDef`/`SYSTEM_SKILLS`
  (`chat-service/app/services/skill_registry.py`), and `plan_forge_skill` is a genuine first-class
  **Workflow** (propose→self_check→interpret_feedback→apply_revision→review_checkpoint→
  handoff_autofix→validate→compile) — not just a tool-use guide. So this is a maturity/coverage gap,
  not a from-scratch build.
- `docs/specs/2026-07-07-skill-authoring-and-mcp-exposure-standard.md` §1(B) already documents the
  **coverage** half of the gap: only 3/11 tool-domains (`glossary`, `knowledge`, `plan_forge`) have a
  real workflow-depth skill; the rest fall back to generic `universal_skill` + raw `find_tools`.
- **Not yet documented anywhere, confirmed newly in this session:** the **routing** half of the gap.
  `resolve_skills_to_inject()` (`skill_registry.py:258-269`) takes zero intent/query-text parameter —
  its own module docstring says it plainly: *"filters by session pins + **surface flags**"*
  (`skill_registry.py:4`). On the universal surface (no book open) it unconditionally injects
  `["universal", "knowledge"]` regardless of what the user actually asks. This is exactly why the 4
  failed sessions in §1 got no workflow guidance at all: a general web-search request has no
  book/editor/studio signal to key off of, so it can never reach a skill that would say "for this,
  call `glossary_web_search` directly, here is the exact shape" — it falls straight to generic
  discovery-and-guess.

**What this means for scope, concretely:**
- **Keep Layer A's fix (§2) as scoped below** — true per-domain enumeration + removing the unbounded
  retry bias. It is cheap, and it is real defense-in-depth: even a mature Skill/Workflow tier will
  occasionally hit an uncovered domain or a genuinely novel ask, and `find_tools` must degrade
  gracefully (bounded, honest "not supported") rather than looping or under-returning, regardless of
  whether the Router tier above it exists yet.
- **Do not treat Layer A as sufficient, or as the main deliverable of this effort.** It is a
  stopgap ("chữa cháy" — the user's own words) that prevents the acute failure modes (infinite loop,
  silent empty turn, under-return), not a fix for the underlying "agent has no procedure to follow"
  problem.
- **The actual fix is a new tier: an Intent→Skill Router**, deciding which skill(s)/workflow(s) apply
  from the user's actual words, independent of (additive to) the existing surface-flag path. This is
  a distinct, larger design question from anything in this spec — proposed as a new **Part F** to
  `2026-07-07-skill-authoring-and-mcp-exposure-standard.md` (which already owns the Skill-tier
  concept and its §1(B) coverage gap), not folded into this discovery-hardening spec. Not yet
  designed — see that spec's Part F (to be drafted) for the CLARIFY/DESIGN pass on: what signal
  drives routing (a cheap classifier? the same LLM turn, one extra system-prompt instruction? a
  small dedicated router call?), how it composes with the existing surface-flag auto-inject (additive
  union, or override?), and how skill coverage (Part B, already tracked as uneven) must expand in
  lockstep — a router that selects among 3 well-built workflows and 8 stubs doesn't fix much.

**External validation (2026-07-07, quick web search, not a full research pass):** checked this
diagnosis against the current (2026) industry consensus on production LLM agent architecture. The
standard 6-layer breakdown (reasoning engine, tool router, planner, orchestration runtime, memory,
observability/guardrails) maps cleanly onto what LoreWeave already has — multi-model BYOK, `find_tools`,
PlanForge (domain-specific planner), saga/outbox/idempotency orchestration, the knowledge-service KG
(arguably deeper than typical off-the-shelf agent-memory layers like Mem0/Letta/Zep), and existing
OTel-style tracing (`trace_id`/`span_id` already present across ~15 files). Of the 6 layers, exactly
**two** gaps were found — loop/give-up guardrails (this spec's Layer A) and an intent-based
routing/planning tier (Part F) — matching, not expanding, the scope already identified independently
from the 4 real sessions + the Part E eval. No additional missing pieces surfaced. Also confirms this
spec's progressive-disclosure design (L1 metadata always-on, L2 full body on inject) already matches
Anthropic's own documented "Agent Skills" pattern (`docs.anthropic.com`'s Agent Skills guide) — not a
gap, a convergent independent design.

## 0. Why the in-flight "Part D" work doesn't resolve this

Before scoping new work: `tool_discovery.py`/`tool_surface.py` currently carry an uncommitted diff
(Part D of the skill-authoring spec — folding 3 hand-authored hot-domain constants into one
skill-registry-derived lookup). Traced against the 4 failed sessions below: all four ran on the
**universal surface with manually curated pins** (`enabled_tools` DB column non-empty), which reach
`assemble_initial_active_names()` (`tool_surface.py:263-272`) — a path that already always includes
a pinned tool regardless of hot-domain derivation. Part D only changes which domains are
**auto-hot-seeded** for default-injected skills on book/editor/studio surfaces. It is legitimate,
narrow, correct work — and it is **provably not the cause of, nor a fix for, any of the failures
below.** This spec is additive to it, not a correction of it.

---

## 1. Problem (grounded)

### Layer A — `find_tools` conflates existence-discovery with usage-detail retrieval

**The architecture today** (`chat-service/app/services/tool_discovery.py`):
- `GROUP_DIRECTORY` (lines 49-68) is a **correct** cheap enumeration — ~15 domains, one-liner each,
  injected as plain text, near-zero token cost. This is genuine existence-discovery, done right, but
  only at the *domain* level.
- One level down — "which tools exist inside domain X" — there is **no equivalent**. The only
  mechanism is `search_catalog()` (lines 411-463): pure token-overlap + difflib fuzzy scoring, no
  embeddings, gated by `INCLUSION_FLOOR=0.20` (line 356) and `CONFIDENCE_THRESHOLD=0.30` (line 352).
  A tool that scores below the floor is **silently absent from the result** — the caller cannot
  distinguish "this domain truly has nothing matching" from "the phrasing didn't overlap enough
  tokens."
- The `find_tools` tool's own schema description bakes in an unbounded retry bias: *"If it returns
  nothing useful, you may try once more with broader wording before telling the user you can't"*
  (`tool_discovery.py:79-80`). The runtime empty-result note repeats this with no state: *"No tool
  matched. Reconsider the wording and search once more before telling the user this isn't
  supported"* (`tool_discovery.py:551-554`) — no counter, no memory of prior phrasings tried this
  turn, no permission to stop.
- The identical shape exists on the ai-gateway/mcp-public-gateway (TS) side per the external audit
  (issue #1, #5) — `find_tools` under-returns badly on generic/exploratory intents (0/15 tools for
  `book` domain depending on phrasing) with no "list everything in this group" affordance there
  either.

**Measured production impact — 4 real sessions, same query, same day:**
Pulled directly from `loreweave_chat` Postgres (session_ids below; query: "tìm kiếm thông tin về
chiến tranh Mỹ và Iran hôm nay trên internet" — a general, non-book-scoped web-search request; all
4 sessions had `glossary_web_search` manually pinned in `enabled_tools`, no `book_id`, same local
model `019f33f5-fa03-7acd-887d-8da1bf8a1b26`):

| Session ID (short) | `enabled_skills` | Outcome |
|---|---|---|
| `...ea03` | `{universal}` | `glossary_web_search` called with valid args, immediately followed by a 2nd EMPTY call → repeated `missing properties: ["query"]` validation errors (13 attempts) → falls back to `find_tools` (still empty) → final answer is **hallucinated training-data content dressed as live news**, glossing the failure as "kỹ thuật sự cố" |
| `...308d` | `{universal}` | identical pattern to `ea03` — same duplicate-call bug, same fallback, same hallucinated-answer outcome |
| `...533f` | `{universal}` | `glossary_web_search` **never attempted** despite being pinned — model's own reasoning concluded "I do not have a general web search tool," called `find_tools` once (empty), gave an honest "I can't do this" answer. Best of the 4 outcomes, but only because the model didn't try — not because discovery worked |
| `...9738` | `{}` (no skill) | same duplicate-call bug on first ~8 attempts, then pivots to `find_tools` with **near-identical intent phrasing repeated 20+ times**, iteration counter reaches 40, 53.8s elapsed, reasoning field shows literal repeated-sentence degeneration ("I'll try to use find_tools with the intent 'search the web' to see if it works." × 20+) → **turn ends with 0-length content, no answer delivered to the user at all** |

Three independent, compounding bugs are visible across these 4 transcripts:
1. **Tool-call duplication** — the model emits a valid call immediately followed by a same-tool
   empty call in 3/4 sessions; the model's own chain-of-thought narrates awareness of the bug but
   cannot self-correct it. This is a harness/decoding-layer defect (same family as the already-fixed
   `D-TOOLCALL-GEMMA-TOKEN-LEAK`, commit `873829f42`), not a prompting problem.
2. **Unbounded `find_tools` retry** — directly caused by the description/note wording above; no cap
   exists on repeated near-identical `find_tools` calls within one turn, and in the worst case (session
   `9738`) this combines with a known local-model failure mode (`reasoning-model-burns-max-tokens-
   before-real-answer`) to produce a completely empty, silent turn.
3. **Naming/framing bias** — `glossary_web_search`'s "glossary_" prefix, sitting inside a domain
   literally described as lore/book tooling, appears to bias the model (non-deterministically — only
   1/4 sessions) toward concluding no general web search exists, even when the tool is present and
   pinned in its own tool list.

**Independent corroboration (2026-07-07, discovered concurrently in a separate track):** the
skill-authoring spec's Part E eval loop (`docs/eval/skill-authoring/2026-07-07-part-e-first-pass.md`)
ran 37 scenarios across 5 skills through a dedicated harness (different model prompts, different
scenarios, different measurement method entirely from the 4 sessions above) and found the **same
`find_tools`-loop-then-silence pattern** as the dominant failure mode (14 WEAK + 4 NEEDS-RERUN + 5/7
FAILs) — and reproduced it on a **control run against the untouched `glossary_skill`**, ruling out
any of that session's new skill prose as the cause. Tracked there as `D-SKILL-EVAL-DISCOVERY-LOOP-FLAKE`,
explicitly not yet root-caused (candidates named: `find_tools` search-relevance friction, the local
model's tool-loop persistence, or a `max_iterations`/termination heuristic in `stream_service.py`).
**This spec's Layer A fix (§2) directly root-causes and closes that deferred item** — the two
findings are the same bug, found twice, independently.

### Layer B — web-search/deep-research reliability is genuinely unverified

Confirmed by direct test-suite audit (not assumed):
- `glossary-service`'s `web_search_tool_test.go` / `g_deep_research_test.go` assert real result
  *content* (source count, URL, snippet text, DB-persisted evidence rows) — but always against an
  `httptest.Server` stub, never a live provider.
- `provider-registry-service`'s `web_search_test.go` / `web_search_handler_integration_test.go`
  likewise assert real parsed content, always against a stub.
- The only test that touches a real upstream is `server_websearch_verify_test.go`'s `verifyWebSearch`
  — and its own doc comment states it does a **connectivity ping**, asserting `verified`/
  `result_count`/reachability only, never that a real query returns relevant results.
- **No test anywhere in the repo calls `glossary_web_search`/`glossary_deep_research` with a real
  query against a real configured provider and asserts real hits.** The only "live" callers are two
  manual smoke scripts (`scripts/run_dracula_fresh_journey.py`, `scripts/run_dracula_mcp_scenario.py`)
  that print `"ok"` on `not isError` with no content assertion.
- Net: **we do not know today whether the real provider call works.** The 4 sessions above never
  reached this layer (they failed earlier, at the duplicate-call/validation stage) — so Layer A's
  bugs are actively masking whether Layer B has its own separate defect.

### Layer C — the external audit's 11 findings, triaged against current code state

| # | Finding | Status as of this spec |
|---|---|---|
| 1 | `find_tools` under-returns on generic queries | Subsumed by Layer A fix |
| 2 | `knowledge` domain (`kg_*`/`memory_*`) totally unreachable via `find_tools`→`invoke_tool` | **Already fixed in code**, commit `46af3c2cd` same day — `DOMAIN_ALIASES={kg:knowledge, memory:knowledge}` added to `ai-gateway/src/federation/find-tools.ts:121`, unit-tested (`find-tools.spec.ts:171-190`). **Not yet live-re-verified** against a running stack with a real MCP client — this is the still-open `D-INVOKE-TOOL-LIVE-SMOKE` item already tracked in `SESSION_HANDOFF.md`. The audit's own repro must be re-run once the stack is up to confirm in practice, not just in unit tests. |
| 3 | Built-in prompts reference tools unreachable per #2 | Resolves automatically once #2 is live-confirmed |
| 4 | `invoke_tool` allowlist inconsistent with raw `tools/call` | **Real, still open.** `invoke_tool`'s "not available yet" refusal (`invoke-tool.ts:105-107`, `requiresActivation`) was never actually blocking `kg_*`/`memory_*` at the policy layer — `tool-policy.ts` already lists them under `domains:['knowledge']`. The refusal was purely a *downstream symptom* of #2 (no domain alias ⇒ `find_tools` never "activates" them ⇒ `invoke_tool` never sees them as activated). With #2 fixed, whether raw `tools/call` should still be allowed to bypass `invoke_tool` entirely is a **separate, still-unresolved architecture question** — see Open Question 1. |
| 5 | No "list all tools in a domain" affordance | Subsumed by Layer A fix |
| 6 | `registry`/`story` domains — entitlement-gated or unfinished, unclear from API | **Not yet investigated this pass** — needs a `TOOL_POLICY`/key-scope check (cheap) to determine which |
| 7 | `composition_create_work` requires undocumented `project_id` | Real, open — needs a product decision, see Open Question 2 |
| 8 | `confirm_action` fails a valid token with a non-actionable error | Real, open — cheap fix, no product decision needed (violates `mcp-tool-io.md` IN-6 directly) |
| 9 | Every response duplicates payload (`content` + `structuredContent`) | Real, open — cheap fix, no product decision needed |
| 10 | 4 incompatible error shapes, no common envelope | Real, open — structural, cross-cutting; violates IN-6's spirit at scale. See Open Question 3 |
| 11 | A no-op propose call succeeds silently instead of warning | Real, open — cheap fix |

---

## 2. Design direction

### Layer A
1. **Add true per-domain enumeration.** `find_tools` called with `group` set and no/empty `intent`
   (or a new dedicated mode) returns **every** non-legacy tool name + one-line description in that
   group, unranked, unfiltered by score floor — mirroring what `GROUP_DIRECTORY` already does one
   level up. This is the direct fix for audit issues #1/#5 and for the "existence discovery" half of
   the user's framing.
2. **Remove the unbounded-retry bias.** Reword `FIND_TOOLS_TOOL`'s description (drop "you may try
   once more... before telling the user you can't" as an unconditional invitation) and add a
   per-turn attempt tracker so a 2nd+ call with a near-duplicate `intent` string (or a repeated empty
   result for the same `group`) gets a note that explicitly permits concluding "not supported" —
   instead of an infinite invitation to keep guessing. Must land identically on both engines
   (chat-service `tool_discovery.py` + ai-gateway `find-tools.ts`), per the existing CAT-4
   "documented to rank identically" discipline — extended here to "must also enumerate/cap
   identically." This directly closes `D-SKILL-EVAL-DISCOVERY-LOOP-FLAKE` (§1's independent
   corroboration above) — the root cause named there (search-relevance friction vs. model persistence
   vs. a loop-termination heuristic) resolves to a mix of #1 (relevance) and this retry-cap (the loop
   never had a chance to terminate honestly before).
3. **Fix tool-call duplication.** Harness-side: when a single turn contains 2+ calls to the identical
   tool name where a later one has empty/missing required args right after a well-formed earlier
   one, drop the malformed duplicate silently rather than surfacing a validation error to the model.
   Needs its own root-cause dig into the streaming/tool-call-parsing path (`stream_service.py`) —
   likely adjacent to the already-fixed `D-TOOLCALL-GEMMA-TOKEN-LEAK` (commit `873829f42`); may be a
   regression or an unhandled sibling case of the same local-model decoding quirk.
4. **Embeddings upgrade to `search_catalog` (OQ4, resolved yes).** Port `knowledge-service`'s
   `EmbeddingClient` pattern into chat-service (first embedding call site there): embed each catalog
   tool's name+description+synonyms ONCE per tool-catalog refresh (the catalog is already
   process-cached per-user with a 60s TTL — `knowledge_client.py`'s `get_tool_definitions()` — so tool
   vectors amortize across many turns, not recomputed per call), then embed the user's `intent` string
   fresh each `find_tools` call and rank by cosine similarity instead of token-overlap/difflib. Needs:
   (a) a shared cosine-similarity helper — 3 near-identical copies already exist
   (`lore-enrichment-service`, `composition-service`, `knowledge-service`), each with the exact
   "if a 3rd/4th site appears, promote to a shared lib" comment already in the code; a 4th duplicate
   in chat-service should instead be promoted to `sdks/python` and the existing 3 migrated, not
   copy-pasted again; (b) an explicit, tested **fallback to the existing token-overlap scorer** on
   embedding-call failure/timeout — the provider-registry embed round trip carries a documented 30s
   timeout "because first calls to cold local models can be slow," and no latency benchmark exists
   anywhere in the repo, so this MUST degrade gracefully, never block or worsen a turn if the embed
   call is slow/unavailable (defense-in-depth, same discipline as Layer A items 1-2). **Synergy with
   Part F:** the skill-authoring spec's new Part F (Intent→Skill Router, CLARIFY drafted alongside
   this spec) is designed to embed the SAME per-turn user intent string once and score it against
   BOTH skill descriptions (routing) and tool descriptions (this item) — one embedding call serving
   two consumers, not two separate round trips. Coordinate the client/cache implementation so it is
   built once and shared, not duplicated across the two efforts.

### Layer B
Add a **live-smoke test** (explicitly marked, not part of the default CI unit run — a `live`/manual
marker per repo convention) that calls `glossary_web_search` with a real, non-empty query against the
actually-configured provider credential and asserts non-trivial real result content. This is the only
way to close the "logic bug vs connection bug" question the user raised. Depending on outcome:
- If it passes: Layer A's fixes are sufficient — the 4 sessions' failures were 100% harness-layer,
  never reached the provider.
- If it fails: a real Layer B defect exists and gets root-caused/fixed here, informed by whatever the
  live call actually returns (not guessed).

### Layer C (per item — full detail already in §1 triage table above)
- **#8, #9, #11 — fix now**, no product decision blocking them (error-message detail, drop duplicate
  payload, add no-op warning).
- **#2/#3 — live-verify only** (code fix already shipped); re-run the audit's exact repro against a
  running stack.
- **#6 — investigate first** (cheap `TOOL_POLICY`/key-scope check), then fix-or-document depending on
  what's found.
- **#4, #7, #10 — need a PO decision each** before design can finalize; see Open Questions below.

---

## 3. Open questions — ALL RESOLVED 2026-07-07

1. ~~`invoke_tool` hard gate vs advisory?~~ — **RESOLVED: advisory.** Keep raw `tools/call` working
   as today; only fix `invoke_tool`'s refusal wording so "not available yet" no longer reads as "this
   tool doesn't exist." Cheapest option, no behavior change for any existing client.
2. ~~Auto-create a knowledge project per book?~~ — **RESOLVED: yes, auto-create.** Matches
   `composition_create_work`'s own "idempotently" language — every book gets an implicit default
   knowledge project so the tool never needs a `project_id` the caller has no way to obtain.
3. ~~Fold error-envelope normalization (#10) into this effort?~~ — **RESOLVED: split into its own
   follow-on plan.** Too cross-cutting (ai-gateway + mcp-public-gateway + every domain service's error
   path) to bundle into an already-XL effort. Tracked as a new, separate plan — not scoped further
   here.
4. ~~Token-overlap enumeration sufficient, or upgrade `search_catalog` to embeddings now?~~ —
   **RESOLVED: yes, build the embeddings upgrade in this same pass** (reverses this spec's original
   recommendation — user's explicit choice). This is a bigger addition than originally scoped: it is
   the **first embedding-provider call site in chat-service** (confirmed by code audit — zero existing
   embedding client there today; `knowledge-service`'s `EmbeddingClient.embed()` is the pattern to
   port, a single async HTTP call to `provider-registry-service`'s `/internal/embed`, BYOK, no direct
   provider SDK per the Provider Gateway invariant). See §2 Layer A design below for the concrete
   shape and the latency/reliability tradeoffs this decision commits to.

---

## 4. Touch list (by service)

- **chat-service (Py):** `app/services/tool_discovery.py` (enumeration mode, retry-cap wording,
  embeddings-backed `search_catalog`), `app/services/tool_surface.py` (if enumeration needs its own
  token-budget treatment), `app/services/stream_service.py` (tool-call-duplication root cause + fix),
  a NEW embedding client module (port of `knowledge-service/app/clients/embedding_client.py`'s
  pattern — first embedding call site in this service).
- **sdks/python:** promote the 3 existing duplicated cosine-similarity helpers (lore-enrichment-service,
  composition-service, knowledge-service) plus chat-service's new 4th need into one shared module,
  per the "promote on the 3rd/4th site" comment already left in the existing copies.
- **ai-gateway (TS):** `src/federation/find-tools.ts` (mirror enumeration + retry-cap fix; embeddings
  parity is a judgment call at PLAN time — may stay token-overlap there if chat-service's upgrade
  alone resolves the measured failures, since the ai-gateway surface wasn't implicated in the 4
  sessions).
- **mcp-public-gateway (TS):** `src/scope/invoke-tool.ts` refusal-wording fix only (OQ1: advisory,
  not a hard gate).
- **glossary-service (Go):** `internal/api/web_search_tool.go` test suite (live-smoke addition),
  `confirm_action` error detail (#8), `glossary_adopt_standards` no-op warning (#11).
- **provider-registry-service (Go):** live-smoke test for the real web-search provider round trip.
- **composition-service:** auto-create a default per-book knowledge project so
  `composition_create_work` never needs a caller-supplied `project_id` (OQ2).

## 5. Out of scope (this pass, explicitly)

- Error-envelope normalization (audit #10) — split into its own follow-on plan per OQ3, not scoped
  further here.
- Full entitlement/tiering UX or documentation overhaul for #6 — this pass only determines root
  cause (gated vs unfinished); any user-facing entitlement UI is separate follow-on work.
- Re-litigating the already-shipped Part D hot-domain-derivation refactor (§0) — confirmed orthogonal,
  left alone.
- Building Part F (Intent→Skill Router) itself — tracked as its own CLARIFY in the skill-authoring
  spec; this spec only coordinates the shared embedding infrastructure with it (§2 Layer A item 4).

## 6. Evidence appendix

- 4 session IDs (full transcripts pulled from `loreweave_chat` Postgres, `localhost:5555`):
  `019f3d43-ea03-765c-8271-2e167d2ffd3d`, `019f3d43-308d-78e9-a0e1-5b2c9bec7d5c`,
  `019f3d42-533f-7f73-9520-2a3282e0afd0`, `019f3d3f-9738-718d-a663-7500dc51c48c`.
- External audit: [`docs/bugs/2026-07-07-mcp-discoverability-external-audit.md`](../bugs/2026-07-07-mcp-discoverability-external-audit.md).
- Code citations: `services/chat-service/app/services/tool_discovery.py` (lines 49-68, 74-104,
  346-463, 523-562), `services/chat-service/app/services/tool_surface.py` (lines 86-306),
  `services/ai-gateway/src/federation/find-tools.ts` (line 121, `DOMAIN_ALIASES`),
  `services/mcp-public-gateway/src/scope/invoke-tool.ts` (lines 105-107), `tool-policy.ts` (lines
  80-90, 159-166, 228-232, 249-252).

## 7. Next step

Open Questions 1-4 are now RESOLVED (§3). Two parallel tracks, per §0.5's reframing — they do not
block each other:

1. **This spec (tactical, defense-in-depth):** PLAN phase — will produce a per-service task
   breakdown (mirroring the `2026-07-05-search-tool-unification.md` plan format, see
   `docs/plans/2026-07-07-mcp-discovery-and-reliability-hardening.md`) with a VERIFY section requiring
   both the new live-smoke tests (Layer B) and a live re-verification of the external audit's exact
   repro steps (Layer C #2/#3), not unit-test-only evidence, given this effort's origin is 2 separate
   "unit tests pass but real usage fails" incidents.
2. **Part F — Intent→Skill Router (strategic, the actual fix, separate CLARIFY/DESIGN):** drafted as
   a new Part (§12-15) in `2026-07-07-skill-authoring-and-mcp-exposure-standard.md`. User's explicit
   choice: build the full dedicated router (embedding-based skill selection), not just the narrower
   "patch the one orphaned web-research coverage gap" option. Coordinates its embedding infrastructure
   with this spec's Layer A item 4 (one shared client/cache, two consumers).
