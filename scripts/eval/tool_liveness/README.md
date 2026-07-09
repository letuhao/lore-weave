# Tool Liveness Eval (TLE) harness — Track D · WS-D2 · P0

**Goal:** prove every MCP tool is callable, correct, **and effectful** when a real LLM
drives it over natural language — closing the gap every existing harness leaves open
(they stop before the write lands; the effect-verifying scripts have no model choosing
the tool). See `docs/specs/2026-07-09-mcp-tool-liveness-eval/` (README + CD1–CD5).

For each tool an authored **black-box NL ask** (never the tool name) is sent to a real
mid-tier model on a real stack, then four gates:

| Gate | Assertion |
|---|---|
| **G1 SELECT** | the model called this tool (seen through the lazy `tool_list`/`tool_load` facade + `invoke_tool` wrapper) |
| **G2 SHAPE** | args schema-valid — every required field present (from the live inventory) |
| **G3 EXECUTE** | returned without `isError`; **Tier-W: the `confirm_token` round-trip completed**; tier-A approval card resolved |
| **G4 EFFECT** | the system actually changed — read back via an **independent path** (the domain's Postgres DB), never the domain's own read tool |

## Components (`scripts/eval/tool_liveness/`)

| File | What it does | Status |
|---|---|---|
| `config.py` | endpoints, secrets (env), DB map | — |
| `auth.py` | real `/v1/auth/login` edge (auth path under test) + self-mint fallback | reused pattern |
| `sse.py` | **SSE driver** — post a turn, drain agui stream, fold tool records (name+args+ok+result) | adapted from `run_discoverability_scenario.py` |
| `confirm.py` | **Confirm resolver** — detect `confirm_token`, POST `/v1/<domain>/actions/confirm`, resume | **NEW (biggest gap)** |
| `fixtures.py` | **Fixture factory** — throwaway book+ontology+chapter+entities; `user_tool_approvals` allowlist; teardown scoped to created ids only | **NEW** |
| `mcp_direct.py` | direct MCP calls (no LLM) for deterministic fixture setup/teardown | dracula pattern |
| `oracle.py` | **Effect oracle** — DB read-back via the postgres container (independent path) | **NEW** |
| `poller.py` | **Async poller** — poll a status tool to terminal before G4 | **NEW** |
| `probes.py` | the 10-tool P0 probe set (R/A/W/async) + oracles | **NEW** |
| `matrix.py` | **Matrix reporter** — `matrix.json` + `matrix.md` | **NEW** |
| `run.py` | orchestrator: fixture → per-probe G1–G4 → reports; oracle negative-control | **NEW** |
| `tests/test_pure.py` | unit tests for the pure parsers (no live stack) | — |

## Run

```bash
# stack up (chat-service, ai-gateway, api-gateway-bff, auth-service, glossary, postgres…)
export TLE_MODEL_REF=<gemma_user_model_uuid>       # $0 local lm_studio; account has no default
export TLE_JWT_SECRET="$(docker exec infra-chat-service-1 printenv JWT_SECRET)"  # confirm fallback
python -m scripts.eval.tool_liveness.run            # add --allow-paid to opt paid probes in

# unit tests (no stack needed):
python -m pytest scripts/eval/tool_liveness/tests/test_pure.py -q
```

Reports land in `docs/eval/tool-liveness/<date>/`: `matrix.json`, `matrix.md`,
`transcript.jsonl`, `negative-control.json`, `meta.json`.

## Safety (the fixture is the boundary)

Destructive (Tier-W) and paid probes touch **only** ids the fixture factory created.
Teardown deletes **only** those recorded ids. Repo precedent for why this is mandatory:
`kg-integration-tests-truncate-shared-dev-db` (an ontology test once truncated the live
dev DB). Paid tools (`glossary_web_search`, `glossary_deep_research`) are excluded from
P0 (`UNTESTED-PAID`) — their spend gate is being built separately (WS-D0b).

## The oracle is proven non-trivial

`run.py::negative_control` runs the write-oracles against state that was deliberately
**never written** and asserts they return False — so a real G4 PASS is meaningful, not a
rubber stamp. Recorded each run in `negative-control.json`.
