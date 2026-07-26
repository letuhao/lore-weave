# Track D · WS-D0 Wave 2 — live smoke: universal `web_search` + the spend gate

**Date:** 2026-07-10 · **Branch:** `feat/context-budget-law` · **Model:** `gemma-4-26b-a4b-qat`
(lm_studio BYOK, `019ebb72-…`, $0) · **Search backend:** keyless `searxng` BYOK credential
(`019ee9ee-…`) · **Account:** `claude-test@loreweave.dev`

**Images REBUILT before the run** (`provider-registry-service`, `ai-gateway`, `chat-service`,
`glossary-service`). This is mandatory: S-HARNESS's Wave-1 run measured the *stale* images and
faithfully reported the pre-wave state (38 untiered tools, zero `paid`) — a false-green in the
opposite direction. Stale images make a live smoke meaningless.

---

## Result: ALL GATES PASS

| Gate | Assertion | Evidence |
|---|---|---|
| **G0** | `web_search` on provider-registry's own MCP wire | `tools/list` → 13 tools; `_meta = {tier:"R", scope:"user", paid:true}`; `required:["query"]` |
| **G1** | Survives the C-GW prefix gate into the federated catalog | ai-gateway `tools/list` → 175 tools, `web_search` present; **0** `dropping tool 'web_search'` warnings |
| **G2** | Always-on core — reachable with **no** discovery round-trip | `agentSurface.advertised.core` = 10 names incl. `web_search`; `tool_list`/`tool_load`/`find_tools` called **0** times |
| **G3** | Turn **suspends** on a spend card | `TOOL_CALL_ARGS.delta` = `{"kind":"tool_approval","tool":"web_search","tier":"R","spend":true,"approval_kinds":["spend"]}`; `RUN_FINISHED.status="suspended"` |
| **G4** | **No spend before consent** | billing ledger `usage_logs` where `model_ref=<searxng>`: **N0=10 → N1=10** across a suspended-but-unapproved turn |
| **G5** | Approval releases exactly one call | **N2=11** (delta **+1**); tool `ok=true`, **5** real sources; assistant answered *"discovered in 1799"* / Young + Champollion, with Britannica cited |
| **G6** | `approved_once` persists nothing | `user_tool_approvals … LIKE 'spend::%'` → **0** rows |
| **G7** | Legacy alias survives, correctly labeled | federated `glossary_web_search._meta` = `{tier:"R", scope:"user", paid:true, visibility:"legacy", superseded_by:"web_search"}` |

**G3 is the tier-orthogonality proof.** The turn ran in `permission_mode="write"`, and the card
reports `tier:"R"` with `approval_kinds:["spend"]` — a Tier-A *mutation* gate cannot fire for a
Tier-R tool, so the suspend can only have come from the spend gate. A spend gate implemented as a
branch of the tier check would have let this call through silently.

**G4 is the property the workstream exists for**, and it is measured on the **billing ledger**
(`loreweave_usage_billing.usage_logs`) through an independent path (`docker exec psql`), never
from chat-service's own reporting.

---

## Two oracle mistakes worth recording

Both were mine, and both would have produced a *confident wrong answer*:

1. **Wrong table.** First probe queried `loreweave_provider_registry.usage_outbox` — 0 rows, which
   read as "the audit is broken / the call never ran." In fact `recordSyncUsage` early-returns on a
   nil guardrail and otherwise POSTs to **usage-billing-service**; the row lands in
   `loreweave_usage_billing.usage_logs`. `usage_outbox` is a *different* (job-path) mechanism —
   it holds `kg_summary` rows, which is what made it look alive.
2. **Wrong event shape.** The first smoke reported "no spend card" because it matched
   `'"tool_approval"'` against `json.dumps(event)`. The card rides inside `TOOL_CALL_ARGS.delta`
   as a JSON **string**, so the quotes arrive escaped (`\"tool_approval\"`) and the match failed.
   The gate had worked the entire time.

Generalization: *a negative result from an oracle you have not independently validated is not
evidence.* The correct discriminator here was `model_ref = <the searxng credential>`, which
uniquely identifies a web-search spend — not `operation`, not token counts (web search records
`tokens=0`), and not `provider_kind` (empty for this credential; 711 rows share that shape).

---

## Reproduce

```bash
# stack (rebuild first!)
cd infra && docker compose build provider-registry-service ai-gateway chat-service glossary-service
docker compose up -d postgres redis rabbitmq auth-service provider-registry-service \
  glossary-service ai-gateway chat-service api-gateway-bff
# provider-registry races rabbitmq on cold start and exits(1); just `up -d` it again.

# the ledger discriminator
docker exec infra-postgres-1 psql -U loreweave -d loreweave_provider_registry -t -A -c "
SELECT um.user_model_id FROM user_models um
JOIN provider_credentials pc ON pc.provider_credential_id=um.provider_credential_id
WHERE um.owner_user_id='019d5e3c-7cc5-7e6a-8b27-1344e148bf7c' AND um.is_active
  AND pc.status='active' AND um.capability_flags @> '{\"web_search\": true}'::jsonb
ORDER BY um.is_favorite DESC, um.created_at ASC LIMIT 1;"

# count before/after a suspended turn — it must NOT move until approval
docker exec infra-postgres-1 psql -U loreweave -d loreweave_usage_billing -t -A -c \
  "SELECT count(*) FROM usage_logs WHERE model_ref='<that uuid>';"
```

Drive the turn with the TLE harness (`scripts/eval/tool_liveness/`): `create_session` →
`send_turn(..., permission_mode="write")` → read the card from `TOOL_CALL_ARGS.delta` and the
`pendingToolCall` from `RUN_FINISHED.result` → `POST /v1/chat/sessions/{sid}/tool-results`
with `{run_id, tool_call_id, outcome:"approved_once"}`.

---

## Known-good ask

> "What year was the Rosetta Stone discovered, and who deciphered it? Look it up on the web and
> cite your sources."

gemma-4-26b selects `web_search` directly on the first pass. Note S-HARNESS's F5 finding still
holds for *other* tool classes (the mid-tier model under-selects Tier-W/async tools) — but a
hot-path, well-described Tier-R tool is selected reliably.
