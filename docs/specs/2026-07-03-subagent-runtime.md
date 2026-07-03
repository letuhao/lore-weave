# Spec — Subagent Runtime (scoped nested execution) · REG-P5-01 runtime

**Status:** DESIGN (clears `D-REG-P5-SUBAGENT-RUNTIME`). The `subagent_defs` CRUD +
`/internal/subagents` resolver already shipped (P5-M1, `b64262cc3`); this spec is the
execution half.

**Owner surface:** chat-service (agent loop) + agent-registry (resolver, shipped).

---

## 1. Goal

Let the main chat agent delegate a bounded sub-task to a **subagent persona** and get a
synthesized answer back — without polluting the main context and without the subagent
being able to touch anything outside its declared `tool_scope`.

A subagent def (shipped schema) is: `{ name, description, system_prompt, tool_scope
(JSON array of tool-name globs), model_ref }`, tiered (system/user/book), enabled/off.

## 2. Non-goals (v1)

- Multi-level nesting (a subagent spawning a subagent). **Depth is capped at 1.**
- Parallel fan-out of subagents. v1 is one synchronous sub-run per tool call.
- Subagent-authored writes escaping the caller's permission mode (a subagent can never
  escalate; see §7).
- A new provider path — the sub-run reuses the existing `_stream_with_tools` loop, so
  every model/tool call still goes through ai-gateway / provider-registry.

## 3. Acceptance criteria (from REG-P5-01 + E2E-P5-A)

1. Invoking a subagent runs a **nested turn** using ONLY its scoped tools; an
   out-of-scope tool is **provably unavailable** (negative test: the sub-model cannot
   call `book_write` when `tool_scope=["glossary_*","kg_*"]`, even if it tries).
2. The subagent's nested messages **do not leak** into the main window — only the final
   synthesized text returns to the main turn as the tool result.
3. The sub-run's token usage is attributed (summed into the turn, tagged as a subagent).
4. The subagent inherits (cannot exceed) the caller's permission mode.

## 4. Architecture decision — where `run_subagent` lives (Q-RUNTIME-HOST)

**Chosen: a chat-service agent-loop primitive** (peer to `find_tools`), NOT a federated
domain MCP tool.

- Rationale: running a nested turn requires the tool loop (`_stream_with_tools`), which
  lives in chat-service. Modeling it as a federated MCP tool on agent-registry would
  force agent-registry to call back into chat-service to run the LLM (a cross-service
  cycle: chat→ai-gateway→agent-registry→chat) for zero benefit. `run_subagent` is
  loop-orchestration plumbing, the same class as `find_tools` — the MCP-first invariant
  targets *bespoke HTTP endpoints driven by raw prompts*, which this is not: the sub-run's
  actual model + tool calls all still flow through ai-gateway / provider-registry.
- Alternative (documented, rejected for v1): host `registry_run_subagent` on
  agent-registry's `/mcp` and delegate execution to a new chat-service
  `POST /internal/subagent/run`. Revisit only if subagents must be callable by an
  *external* agent through the public MCP edge.

## 5. Tool contract (`run_subagent`)

Advertised in the main turn's core tool set **iff** the user has ≥1 enabled subagent
(resolved once per turn from `/internal/subagents`, degrade-safe → tool absent).

```
run_subagent(subagent: <enum of the caller's enabled subagent names>, task: string)
```

- `subagent` is a **closed-set enum** built from the resolved names (Frontend-Tool-
  Contract rule: closed set ⇒ enum, so a weak model can't pass a bogus name; a miss
  returns a `result.error` naming the available subagents — never a silent no-op).
- `task` is the natural-language sub-task the persona should perform.

## 6. Execution flow

1. Main loop sees a `run_subagent` call → look up the def by name in the per-turn
   resolved set (reject with `result.error` if unknown/disabled).
2. **Resolve the scoped tool set:** intersect the caller's *full* tool catalog with the
   def's `tool_scope` globs (`fnmatch`). Always exclude meta/loop tools (`run_subagent`,
   `find_tools`) → no recursion, no self-call. Result = the subagent's advertised tools.
3. **Build the nested context (isolated):** a FRESH `messages` list = `[{system:
   def.system_prompt}, {user: task}]`. The main turn's history is NOT included (isolation);
   optionally inject a compact, read-only summary of the current book/project context if
   `tool_scope` implies it (behind a flag, off by default).
4. **Run** `_stream_with_tools(messages=nested, tools=scoped, model=def.model_ref or the
   turn's model, permission_mode=<caller's, clamped>, hooks=<caller's hooks still apply>,
   max_iterations=<a smaller sub-cap>)` — recursively, with a **depth guard** (a
   `subagent_depth` param; refuse if already ≥1).
5. **Collect** the sub-run's final assistant text + its usage. Return the text as the
   `run_subagent` tool result (`{ subagent, result: <text>, tools_used: [...] }`); the
   nested tool-call chunks are emitted as **nested activity** (grouped under the
   subagent, visually distinct) but the nested *messages* never enter the main `working`
   array — only the tool-result atom does.

## 7. Security & isolation (the crux)

- **tool_scope is a hard whitelist, enforced twice** (defense-in-depth): at *advertise*
  time (only scoped tools are offered) AND at *execute* time (a sub-model call to a
  non-scoped tool returns a `result.error`, never executes — mirrors the C2 ask-mode
  defense-in-depth block). This is the negative-test guarantee.
- **No escalation:** the sub-run's `permission_mode` is `min(caller_mode, ...)` — a
  subagent in a `write` turn still hits the same Tier-A approval gate; a subagent can
  never run a write the caller couldn't. In `ask`/`plan` mode the scope filters to Tier-R
  as usual.
- **No context leak:** the nested `messages` are isolated; the main model sees only the
  synthesized result text. The sub-run's system_prompt (persona) never enters the main
  window.
- **Tenancy:** the def is resolved for the caller (`/internal/subagents?user_id=&book_id=`)
  — a user can only invoke their own / System / their book's subagents (already enforced
  by the resolver + tenancy).
- **Recursion/DoS:** depth cap = 1; the sub-run has its own (smaller) iteration cap; the
  scoped set excludes `run_subagent`. A subagent cannot spawn another.

## 7b. Edge cases & residual risks (from an industry-practice review)

Grounded in Claude Code subagents + the 2025-26 multi-agent-security literature
(isolated context / final-output-only, per-agent tool whitelisting, delegation-chain
logging, indirect-prompt-injection). Each below is a MUST unless marked.

1. **Frontend tools are excluded from `tool_scope`.** A frontend/UI tool (`propose_edit`,
   `ui_open_studio_panel`, `confirm_action`, …) SUSPENDS for client execution — there is
   no browser in a nested server-side loop, so it would hang/no-op. The scoped set
   excludes frontend tools AND meta tools; a `tool_scope` glob that would match one is
   silently dropped from the sub-run (documented in the def's UI: "subagents run
   headless — UI tools don't apply").
2. **Result-size cap.** The synthesized result returned to the main turn is capped
   (e.g. ~4 KB / a token budget); a subagent that returns 50 KB would re-pollute the main
   context and defeat the whole isolation benefit. Over-cap → truncate + a note.
3. **Cancellation threads through.** The main turn's `cancel_check` is passed into the
   nested `_stream_with_tools`; cancelling the main turn cancels the sub-run (no orphaned
   background LLM spend). Mirrors the repo's existing cancel_check contract.
4. **Empty scope is allowed (text-only).** If `tool_scope` resolves to zero tools (globs
   match nothing / empty catalog), the sub-run still executes as a pure reasoning pass
   (no tools advertised) rather than erroring — a "persona rewrite/summarize" subagent is
   valid. `tool_scope=["*"]` is permitted but the builder WARNS ("this grants the subagent
   your full tool access — scoping is the safety benefit").
5. **Token/cost budget.** Industry note: subagent-heavy flows can cost ~7× a single
   thread (each keeps its own context). The sub-run carries a smaller iteration cap AND
   the nested tokens are debited against the SAME turn budget (`budget.remaining()` style)
   so a subagent can't run the turn past its ceiling.
6. **Indirect prompt injection (residual, mitigated not eliminated).** A scoped tool can
   return attacker-controlled text that steers the sub-model to misuse another *in-scope*
   tool. The `tool_scope` whitelist BOUNDS the blast radius (the whole point — a
   `glossary_*` subagent can never be injected into `book_write`); the caller's permission
   clamp bounds writes. Full injection defense (causal attribution / provenance) is out of
   scope — documented as residual, same posture as the main loop.
7. **model_ref fallback.** An invalid/deleted `model_ref` falls back to the turn's model
   (never hard-fails the delegation); logged.
8. **Delegation-chain audit.** The `subagent_run` event records the caller→subagent edge
   (who delegated what, which tools ran) — the "delegation-chain logging" the multi-agent
   access-control literature calls for.

## 8. Observability

- Emit a `subagent_run` activity event (name, tools_used, ok, latency, tokens).
- Attribute the sub-run's usage into the turn total (design D10 summing), tagged
  `subagent=<name>` so billing/telemetry can split it out.

## 9. Testing

- **Unit (chat-service):** `resolve_scoped_tools(catalog, tool_scope)` — glob intersect
  + meta-tool exclusion; the execute-time reject of a non-scoped tool; the depth guard.
- **Live E2E-P5-A (real turn, local model):** create a `lore-scout` subagent
  (`tool_scope=["glossary_search","kg_*"]`); a main turn asks the agent to delegate a
  lore lookup → assert (a) the sub-run called only in-scope tools, (b) a planted
  out-of-scope tool (`book_write`) is NOT in the sub-run's advertised set AND a forced
  call returns a `result.error`, (c) the main transcript contains the synthesized result
  but NOT the nested messages/persona prompt.

## 10. Milestones

- **M1** — pure `resolve_scoped_tools` + the depth/recursion guards + unit tests.
- **M2** — the nested `_stream_with_tools` invocation + isolation (result-only return) +
  the `run_subagent` tool contract (enum, no-silent-no-op) + CLOSED_SET_ARGS registration.
- **M3** — permission-mode clamp + execute-time scope enforcement (defense-in-depth).
- **M4** — activity event + usage attribution.
- **M5** — live E2E-P5-A + `/review-impl` (isolation + scope-escape are the load-bearing
  checks) + session update.

## 11. Estimated size

**L** (1 service, deep logic in the hot loop, a recursive call + isolation invariants,
security-critical scope enforcement). Write the plan file at build time; `/review-impl`
mandatory (context-isolation + privilege boundaries).
