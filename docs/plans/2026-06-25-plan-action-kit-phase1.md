# Implementation Plan — Plan/Action Kit Phase 1 (multi-agent execution)

**Size:** XL (new shared abstraction + cross-service: `sdks/go/loreweave_mcp`, glossary-service, chat-service).
**Design source:** `docs/specs/2026-06-25-plan-action-kit.md` (Part II §13–§20 are implementation-ready) +
companion `2026-06-25-glossary-assistant-planner.md`.
**Goal:** "dựng ontology cho <book>" → ONE `glossary_plan` call → ONE confirm → deterministic idempotent
executor creates genres+kinds+attributes → agent reports the real summary. Additive-only (no destructive
ops, no FE change — kit §18).
**Strategy:** freeze the kit contract once (serial), then fan out disjoint files to parallel sub-agents,
each with a *tight* context (spec §-refs + only the files it touches), returning structured diffs — not
file dumps. This is the token-optimization core: N agents each read ~3 files, not the whole repo.

---

## 1. Workstreams & file map (disjoint where possible)

| ID | Workstream | Files (new unless noted) | Lang | Depends on |
|---|---|---|---|---|
| **K0** | **Kit contract** (types + validation + ids/dedupe + registry/ledger ifaces) | `sdks/go/loreweave_mcp/plan.go` (+`plan_test.go`) | Go | — |
| K1 | Executor | `sdks/go/loreweave_mcp/execute.go` (+test) | Go | K0 |
| K2 | Propose/mint (wraps existing `mintActionToken` spine) | `sdks/go/loreweave_mcp/propose.go` (+test) | Go | K0 |
| K3 | Planner helper (loose-emit→validate→repair, model resolve) | `sdks/go/loreweave_mcp/planner.go` (+test) | Go | K0 |
| G1 | Glossary op registry + handlers (4 additive ops → existing cores) | `services/glossary-service/internal/api/plan_ops.go` (+test) | Go | K0 |
| G2 | `glossary_plan` MCP tool | `…/api/action_plan_tools.go` (+test); edit `mcp_server.go` | Go | K0,K2,K3,G1 |
| G3 | `execute_plan` confirm + preview wiring | edit `action_confirm.go`, `action_confirm_token.go`, `action_confirm_test.go` | Go | K0,K1,G1 |
| S1 | Skill: plan→review→execute routing + K=2 stop | edit `services/chat-service/app/services/glossary_skill.py` | Py | — (text) |
| V | Integration: `go build/vet/test` both modules + cross-service live-smoke | — | — | all |

**Python kit port** (`sdks/python/loreweave_mcp/*`) is **DEFERRED to Phase 2** — Phase 1 has no Python
consumer (the planner tool + executor are Go in glossary-service). Building it now spends tokens on unused
code; the COMPOSE-A alignment is honored when the first Python consumer (entity ops) arrives. *(Decision —
flag for the human; reverse if they want the port now as a parallel stream.)*

## 2. Dependency DAG → execution waves

```
Wave 0 (SERIAL, orchestrator):   K0  ── freeze the contract everything keys off
                                  │
Wave 1 (PARALLEL, 5 agents):     K1   K2   K3   G1   S1
                                          │    │
Wave 2 (PARALLEL, 2 agents):              └─ G2 ─┘   G3
                                  │
Wave 3 (SERIAL, orchestrator):   V  ── build/vet/test/live-smoke, fix integration
```

- **K0 is serial and done first** because every other unit imports its types (`Plan/Op/OpSpec/Registry/
  Summary/TokenLedger`). Freezing it once removes all cross-agent coupling — Wave-1 agents never block on
  each other.
- Wave 1 files are **disjoint** (different files, even within the kit package) → zero merge conflict.
- G2/G3 depend on G1's registry + K2/K1 → Wave 2.
- S1 (skill, prompt text) is independent → rides Wave 1 for free.

## 3. Multi-agent orchestration (Workflow script shape)

Run as ONE `Workflow` (the user opted into multi-agent). Each `agent()` gets a **scoped prompt**: the exact
spec §-refs + the explicit file paths it may read/write + a strict "return a structured result, not file
contents" instruction. Worktree isolation is **NOT** needed (files are disjoint; same module is fine) —
saves the ~300ms/agent worktree cost.

```js
// Wave 0 — orchestrator writes K0 directly (small, contract-critical) OR one agent:
phase('Contract'); await agent(K0_PROMPT, {schema: FILE_RESULT})   // plan.go + plan_test.go

// Wave 1 — disjoint, parallel:
phase('Build')
const w1 = await parallel([K1,K2,K3,G1,S1].map(t => () => agent(t.prompt, {schema: FILE_RESULT})))

// Wave 2 — parallel, after registry+mint exist:
phase('Wire')
const w2 = await parallel([G2,G3].map(t => () => agent(t.prompt, {schema: FILE_RESULT})))

// Wave 3 — orchestrator verifies (NOT an agent — needs the real toolchain + live stack):
phase('Verify')   // go build/vet/test ×2 modules; live-smoke; loop-fix on failure
```

`FILE_RESULT` schema = `{files_written:[path], tests_added:int, test_cmd:string, notes:string}` — so each
agent returns ~200 tokens, not the file body. The orchestrator reads results, not diffs, keeping the main
context lean. Verification (Wave 3) runs in the **main loop** (real `go`/`docker`, not a sandboxed agent).

## 4. Token-optimization tactics (the explicit asks)

1. **Tight per-agent context** — each prompt names the 2–4 files it needs + the spec §-numbers, nothing
   else. No "read the codebase." K0's frozen types are pasted INTO each Wave-1 prompt (≈40 lines) so agents
   don't re-derive them.
2. **Structured returns, not file dumps** — `FILE_RESULT` schema; the orchestrator never ingests full file
   bodies into the main context.
3. **Contract-first kills rework** — freezing K0 once prevents the classic multi-agent waste of N agents
   inventing N incompatible type shapes that then need a reconciliation pass.
4. **Disjoint files, no worktrees** — avoids worktree setup cost and merge passes.
5. **Verification batched at Wave 3**, not per-agent — agents write + unit-test their own file; the
   expensive cross-module build + live-smoke runs once, centrally.
6. **Defer the Python port** — biggest single token saving (a whole parallel module with no consumer).

## 5. Per-unit acceptance (TDD — each agent writes failing test first)

| Unit | Must prove |
|---|---|
| K0 | envelope validates; dedupe collapses identical, `duplicate_conflict` on same-id-diff-params; ids `op-N` frozen; `MaxPlanOps`/empty-plan rejected; `RegisterOp` panics on non-idempotent |
| K1 | error-class→outcome table (§5) exact: unique→skip, FK→target_gone, stale→changed, validation→bad_params, internal→abort; base_version re-check; summary shape |
| K2 | mint reuses `mintActionToken`; descriptor `execute_plan`; 30-min TTL; round-trips through verify |
| K3 | loose-emit parsed; invalid op → 1 repair round → else `notes[]`; zero-valid → "nothing actionable"; model resolve order planner→chat→model_ref→422 |
| G1 | each of 4 ops maps to its core; identity keys; slug-code + non-empty-description validate rejects |
| G2 | reads ontology, builds delta plan, mints card; registered in `mcp_server.go` |
| G3 | `execute_plan` in `liveDescriptor`; confirm dispatches to kit `ConfirmPlan` (jti single-use preserved); preview re-validates each op |
| S1 | skill routes plan→review→execute; forbids write-tool-loops for multi-step; K=2 stop text |
| V | `go build/vet/test` green both modules; **live-smoke**: real `glossary_plan`→confirm→executor on live PG + a local lm_studio model creates an ontology end-to-end |

## 6. Verify gate (Phase 6, orchestrator-run)

- `go -C sdks/go/loreweave_mcp test ./...` and `go -C services/glossary-service test ./...` — read full output.
- `frontend` untouched (additive-only, §18) — no FE test needed; confirm by `git diff --stat` showing no
  `frontend/` changes.
- **Cross-service live-smoke token** (CLAUDE.md VERIFY rule, ≥2 services touched): bring up glossary +
  provider-registry + PG, drive `glossary_plan` then `glossary_confirm_action` for the test account, assert
  the kinds/attributes exist. Evidence string carries `live smoke: <result>` or an explicit deferral.

## 7. Review & checkpoint

- 2-stage REVIEW (spec-compliance vs §13–§14; then quality) on the merged diff.
- `/review-impl` on the **kit** (new load-bearing abstraction + a token/confirm security boundary) — the
  CLAUDE.md trigger (new service boundary / confirm path) applies.
- POST-REVIEW human checkpoint before COMMIT.

## 8. Risks specific to the build

- **Existing core signatures** (`createKindFromParams`, `createAttrDefFromParams`, `adoptBookOntologyCore`,
  the `book_patch` core) — G1 agent must read them and adapt; if a core lacks a needed return/error, that's
  a real finding to surface, not paper over.
- **`book_patch` core for `edit_attribute`** — confirm it raises a stale-version error K1 can map; if not,
  that's a small addition (in scope).
- **Planner structured-output on local models** — §15's loose-emit+validate handles weak models; the
  live-smoke uses a local model to prove it (not just gpt-4o).
- **Module boundary** — kit and glossary are separate Go modules; glossary's `go.mod` needs a `require` +
  `replace ../../sdks/go/loreweave_mcp` (like its existing `grantclient`/`observability` replaces). The G2/G3
  agents must add it; Wave-3 build catches a miss.
```
