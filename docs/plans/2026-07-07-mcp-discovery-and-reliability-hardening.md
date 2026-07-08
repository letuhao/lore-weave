# Plan: MCP tool-discovery hardening (find_tools enumeration + embeddings, tool-call dedup) + web-search live-verify + external-audit fixes

**Date:** 2026-07-07 · **Branch:** `feat/context-budget-law` · **Origin:**
[`docs/specs/2026-07-07-mcp-discovery-and-reliability-hardening.md`](../specs/2026-07-07-mcp-discovery-and-reliability-hardening.md)
(CLARIFY, all 4 Open Questions resolved) — 4 real chat sessions failed on the identical general
web-search query (Postgres-pulled transcripts), an external cold-start MCP discoverability audit
(`docs/bugs/2026-07-07-mcp-discoverability-external-audit.md`), and a code audit of the fuzzy
tool-search + web-search test suites. **Size: XL.** Explicitly scoped as the *tactical,
defense-in-depth* track — the strategic fix (Intent→Skill Router) is a separate, parallel effort,
Part F of `docs/specs/2026-07-07-skill-authoring-and-mcp-exposure-standard.md`.

## Problem (measured, not assumed — see spec §1 for full detail)

Three independent, compounding bugs across 4 real sessions (same query, same day, same account):
(1) the model emits a valid `glossary_web_search` call immediately followed by a same-tool EMPTY
call, tripping `missing properties: ["query"]` validation repeatedly; (2) `find_tools`'s own
description + empty-result note give an UNBOUNDED invitation to keep retrying ("reconsider the
wording and search once more"), with no per-turn cap — one session hit 40 iterations, 53.8s, and
delivered a 0-length answer; (3) 3 of 4 sessions' "successful" answers were hallucinated
training-data content dressed as live news. Independently corroborated by
`D-SKILL-EVAL-DISCOVERY-LOOP-FLAKE` (skill-authoring spec's Part E eval, 37 scenarios, 5 skills,
same failure signature, reproduced on a control run). Separately: no test anywhere calls the real
web-search provider and asserts real results (stub-only coverage); and the external audit's 11
findings triage to 3 already-fixed (needing live re-verify), 3 cheap fix-now, 1 needs investigation,
1 split to its own plan (error-envelope, out of scope here), 2 resolved by OQ2/OQ1 below.

## Resolved decisions (spec §3, all 4 answered 2026-07-07)
- OQ1: `invoke_tool` stays **advisory** — fix refusal wording only, no hard-gate behavior change.
- OQ2: `composition_create_work` **auto-creates** a default per-book knowledge project.
- OQ3: error-envelope normalization (audit #10) **split into its own follow-on plan** — not built here.
- OQ4: **build the embeddings upgrade** to `search_catalog` in this same pass (first embedding call
  site in chat-service) — reused by Part F's Router (separate effort) for skill-vector scoring.

## Concurrent fix note (2026-07-08, verified compatible before BUILD)

A separate track shipped `1a4983b7b` (root-causing `D-SKILL-EVAL-DISCOVERY-LOOP-FLAKE`) while this
plan was being written. Verified against current code before dispatching BUILD:
- **Already fixed, complementary:** `find_tools_result()` now rejects a missing/blank `intent` with
  a directive message instead of silently degrading to a zero-token search (`tool_discovery.py:552-564`).
  Confirmed this did NOT fix `gemma-4-26b-a4b-qat`'s behavior on its own — the model kept sending
  empty `intent` regardless (the eval report's own finding) — i.e. **the retry-cap in this plan's
  design item 1 is still the only mechanism that bounds the damage** for this known-defective model,
  not made redundant by the intent-directive fix. Both fixes are needed, not overlapping.
- **Confirmed NOT touched, still fully in scope:** `FIND_TOOLS_TOOL`'s top-level description
  (`tool_discovery.py:74-81`, the "you may try once more... before telling the user you can't" bias)
  and the generic no-match `note` (`tool_discovery.py:578-581`) are byte-for-byte unchanged — design
  item 1's retry-cap work is still fully needed.
- **Orthogonal, no plan change needed:** the other fix (`is_curated()` not recognizing skill-only
  pins) is a different code path (curated-mode detection for user-pinned sessions) from anything in
  this plan or Part F's router (which adds to the AUTO/default path via `resolve_skills_to_inject()`,
  already fixed by the shipped Part D to derive hot domains from actually-injected skills — never
  routes through `is_curated()`). No overlap, no rework needed.

## Design (per touch point)

### 1. chat-service — `find_tools` enumeration + retry-cap + embeddings (`tool_discovery.py`)
- **Enumeration mode:** `find_tools(group=<g>)` called with no/empty `intent` returns every
  non-legacy tool name + one-line description in that group, unranked, unfiltered by
  `INCLUSION_FLOOR`/`CONFIDENCE_THRESHOLD` — mirrors `GROUP_DIRECTORY`'s existing domain-level
  enumeration one level down.
- **Retry-cap:** reword `FIND_TOOLS_TOOL`'s description (drop the unconditional "try once more
  before telling the user you can't") and the empty-result `note` in `find_tools_result()`; add a
  per-turn tracker (session/turn-scoped, not global) of prior `(group, normalized-intent)` attempts
  so a repeated/near-duplicate call gets a note that explicitly permits "tell the user this isn't
  supported" instead of another invitation to keep guessing.
- **Embeddings:** new `app/clients/embedding_client.py` (port of `knowledge-service`'s
  `EmbeddingClient.embed()` — one async HTTP call to `provider-registry-service`'s `/internal/embed`,
  BYOK, no direct provider SDK). Precompute tool-description vectors once per tool-catalog refresh
  (already 60s-TTL process-cached per user via `knowledge_client.py`'s `get_tool_definitions()` — no
  new per-call cost). Embed the user's `intent` string fresh per `find_tools` call; rank by cosine
  similarity via the new shared helper (below) instead of token-overlap/difflib. **Mandatory
  fallback:** on embed-call failure/timeout, fall back to the existing token-overlap scorer
  unconditionally — never block or degrade a turn below today's behavior.
- Land the enumeration + retry-cap fix identically on ai-gateway's `find-tools.ts` (CAT-4
  "must rank identically" discipline, extended to "must enumerate/cap identically"). Embeddings
  parity on ai-gateway is a judgment call at BUILD time — only port if chat-service's fix alone
  doesn't resolve the measured ai-gateway-side audit findings (#1/#5).

### 2. sdks/python — shared cosine-similarity helper
3 near-duplicate implementations already exist (`lore-enrichment-service/app/retrieval/store.py`,
`composition-service/app/db/repositories/motif_retrieve.py`, `knowledge-service/app/context/
selectors/passages.py`), each carrying an inline "promote to a shared lib if a 3rd/4th site appears"
comment. Chat-service's new need is that 4th site — promote to `sdks/python` (a new small module,
e.g. `loreweave_internal_client/vecmath.py` or sibling), migrate the 3 existing call sites to import
it, delete the 3 inline copies. Not a new dependency (pure stdlib math, as today).

### 3. chat-service — tool-call duplication (`stream_service.py`)
Root-cause the streaming/tool-call-parsing path: when a single turn contains 2+ calls to the
identical tool name where a later one has empty/missing required args immediately after a
well-formed earlier one, drop the malformed duplicate silently (never surface a validation error for
it to the model). Investigate whether this is a regression/sibling case of the already-fixed
`D-TOOLCALL-GEMMA-TOKEN-LEAK` (commit `873829f42`) before writing a new fix from scratch.

### 4. glossary-service / provider-registry-service — Layer B live-smoke
One new, explicitly-marked (`live`/manual, not default CI) test per side that calls
`glossary_web_search` with a real, non-empty query against the actually-configured provider
credential and asserts non-trivial real result content — closes the "logic bug vs. connection bug"
question with real data instead of guessing. If it fails, root-cause and fix here, informed by
whatever the live call actually returns.

### 5. glossary-service — cheap external-audit fixes
- `confirm_action`'s `AUTH_APPROVAL_EXECUTE_FAILED` gets a concrete reason string (self-confirm
  disabled / owner-approval-queued / expired / domain mismatch) instead of the current
  non-actionable message — direct `mcp-tool-io.md` IN-6 compliance fix.
- `glossary_adopt_standards` (and any other propose-tool with a genuinely empty payload) returns a
  `"warning": "..."` field when the confirmable action is a no-op, instead of silently returning a
  valid-looking confirm token.

### 6. mcp-public-gateway — `invoke_tool` wording only
Per OQ1 (advisory, not a hard gate): fix the "is not available yet" refusal message so it doesn't
read as "this tool doesn't exist" — no behavior/access-control change, wording only.

### 7. composition-service — auto-create default knowledge project
Per OQ2: `composition_create_work` no longer requires a caller-supplied `project_id` — resolves (or
creates, idempotently, matching the tool's own existing language) a default per-book knowledge
project transparently.

### 8. registry/story entitlement investigation (audit #6)
Cheap `TOOL_POLICY`/key-scope check on the `registry`/`story` domains to determine whether the
"not available to this key" errors the audit hit are intentional tier-gating or an incomplete
rollout. Fix-or-document depending on what's found — no product decision needed either way, this is
a factual determination.

## Touch list
- **chat-service (Py):** `app/services/tool_discovery.py`, `app/services/tool_surface.py` (if
  enumeration needs its own budget treatment), `app/services/stream_service.py`, NEW
  `app/clients/embedding_client.py`, tests: `test_tool_discovery.py`, `test_tool_surface.py`,
  `test_stream_service.py`, `test_stream_tools.py`.
- **sdks/python:** NEW shared cosine-similarity module; update `lore-enrichment-service`,
  `composition-service`, `knowledge-service` call sites to import it.
- **ai-gateway (TS):** `src/federation/find-tools.ts` + `test/find-tools.spec.ts`.
- **mcp-public-gateway (TS):** `src/scope/invoke-tool.ts` (wording only) + its test.
- **glossary-service (Go):** `internal/api/web_search_tool.go` (+ new live-smoke test file),
  `confirm_action` handler (error detail), `glossary_adopt_standards` handler (no-op warning),
  `entity_search.go`/registry-story investigation.
- **provider-registry-service (Go):** new live-smoke test for the real web-search provider round
  trip.
- **composition-service:** `composition_create_work` handler + its knowledge-project resolution
  path.

## Fan-out execution slices (parallel BUILD on disjoint files, serial ONE VERIFY)

Per this repo's fan-out convention: slice by DISJOINT files/services first, only sequence where two
slices would otherwise touch the same file. One shared final VERIFY pass (cross-service live-smoke,
above) after every slice lands — not a per-slice VERIFY.

**Group A — fully independent services, safe to run as parallel worktree agents, any order:**
- A1. ai-gateway `find-tools.ts` (design item 1, mirror half) + its test.
- A2. mcp-public-gateway `invoke-tool.ts` wording (design item 6) + its test.
- A3. glossary-service: web-search live-smoke test (item 4) + `confirm_action` error detail (item 5)
  + `glossary_adopt_standards` no-op warning (item 5) + registry/story investigation (item 8) — one
  agent, same service, likely different files/handlers within it; split further only if the agent
  finds file-level contention.
- A4. provider-registry-service live-smoke test (item 4).
- A5. composition-service auto-create-project (item 7).

**Group B — chat-service, sequence-sensitive (shared files: `tool_discovery.py` is touched by both
the enumeration/retry-cap fix AND the embeddings upgrade — do NOT run these as two parallel agents on
the same file):**
- B1 (prerequisite, run first or in parallel with Group A — no chat-service dependency yet): the
  `sdks/python` shared cosine-similarity module (design item 2) + migrating the 3 existing call
  sites. Blocks B3 below.
- B2 (parallel-safe with B1 and Group A — different file): `stream_service.py` tool-call-dedup
  (design item 3).
- B3 (sequenced: needs B1 merged first): `tool_discovery.py` enumeration + retry-cap (design item 1,
  chat-service half) AND the embeddings integration (design item 1, embeddings sub-item) — **one
  agent/session, not two**, since both land in the same file; do enumeration+retry-cap first, then
  layer the embeddings-backed scorer on top in the same pass, to avoid a merge conflict between two
  independently-scoped diffs to `search_catalog()`.

**Reconciliation:** once A1-A5 and B1-B3 all land, one integration pass confirms no cross-slice
assumption broke (e.g., B3's new embedding client import path matches what B1 actually named the
shared module) before the mandatory live-smoke VERIFY below runs.

**Cross-plan dependency:** [`docs/plans/2026-07-07-intent-skill-router.md`](2026-07-07-intent-skill-router.md)
(Part F, running in the same combined fan-out round) has its own F2 slice that consumes B3's
embedding client directly — F2 must not start until B3 lands here. F0 in that plan is fully
independent and can run in parallel with everything in this plan.

## Verify (per piece, then cross-service)
- chat-service: unit tests for enumeration mode (returns full unranked set, respects
  legacy-visibility exclusion), retry-cap (2nd near-duplicate `find_tools` call gets the
  "tell the user" note), embeddings fallback (embed-call failure still returns token-overlap
  results, never an error), tool-call-dedup (malformed duplicate silently dropped, no validation
  error surfaced).
- **Live-smoke, mandatory (this effort's origin is 2 separate "unit tests pass, real usage fails"
  incidents — unit-test-only evidence is not sufficient here):**
  - Re-run the exact 4-session repro (the Vietnamese general web-search query, no book context,
    `glossary_web_search` pinned) against the fixed stack — confirm a real, non-hallucinated answer
    or an honest "not supported" is delivered, never a loop or empty content.
  - Real-provider web-search live-smoke (Layer B) — confirm actual result content, not just
    connectivity.
  - Re-run the external audit's exact repro steps for issues #2/#3 (knowledge domain reachability)
    against a running stack with a real MCP client — not just the existing unit tests
    (`find-tools.spec.ts`) — this is the still-open `D-INVOKE-TOOL-LIVE-SMOKE` deferred item,
    closed by this verification.
  - `composition_create_work` end-to-end with no pre-existing project — confirm it succeeds without
    a caller-supplied `project_id`.
- Cross-service: since ≥2 services change (chat-service, glossary-service, at minimum), live-smoke
  evidence is required per `CLAUDE.md`'s cross-service VERIFY rule, not mock-only coverage.

## Out of scope (consciously, per resolved OQ3 + spec §5)
Error-envelope normalization (audit #10) — separate follow-on plan. Full entitlement/tiering UX
overhaul for #6 — this pass only determines root cause. Re-litigating the already-shipped Part D
hot-domain-derivation refactor — confirmed orthogonal. Building Part F (Intent→Skill Router) itself —
separate CLARIFY/DESIGN in the skill-authoring spec; this plan only builds the embedding
client/cosine-helper infrastructure Part F will also consume, not the router itself.
