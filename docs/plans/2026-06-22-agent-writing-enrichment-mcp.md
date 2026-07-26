# Plan — agent-complete the writing assistant + enrichment (MCP-first) · 2026-06-22

Branch `feat/knowledge-graph-ontology`. Closes the last two agent-driven gaps in the
Dracula scenario so the journey runs through the ASSISTANT (MCP), not curl:

- **Step 11 (write a chapter):** composition-service has the full grounded cowrite
  engine at REST (`POST /v1/composition/works/{id}/generate` scene + `/chapters/{id}/generate`)
  but NO MCP tool to invoke it — the agent can scaffold/save prose it wrote itself but
  cannot drive the engine.
- **Step 10 (enrich):** lore-enrichment auto-enrich is REST-only; the service has **no
  `/mcp` facade at all**.

## Decisions (PO checkpoint 2026-06-22)
- `composition_generate` gates spend via **propose→confirm** (like `kg_build_graph` +
  the existing `composition_publish`), NOT a direct trigger.
- It exposes **both** engine paths via ONE discriminated tool: `chapter_id` →
  chapter single-pass (persists the book draft); `outline_node_id` → scene auto-generate.

## M1 — `composition_generate` (composition-service)
- **`app/mcp/server.py`**: new Tier-W tool `composition_generate`. Arg model
  `_GenerateArgs(project_id, chapter_id?, outline_node_id?, model_source, model_ref,
  operation?, guide?, max_output_tokens?, reasoning?)`. EXACTLY ONE of chapter_id /
  outline_node_id (XOR; else tool error). Gate: resolve Work (user-scoped) + EDIT on
  book. Mint a `composition.generate` confirm token (resource = the target id; payload
  captures the resolved spec). NO spend here.
- **`app/routers/actions.py`**: handle the new `composition.generate` descriptor in
  `confirm_action`. Re-gate EDIT, mint the service bearer, then call the engine
  **in-process** (deps are trivial factories): scene → `engine.generate(..., mode="auto")`;
  chapter → `engine.generate_chapter(..., persist=True)`. Parse the JSONResponse body,
  return `{outcome: action_done, descriptor, job_id, text, persisted?, canon, ...}`.
  `GET /preview` already decodes generically — no change needed beyond the descriptor map.
- Worker is OFF by default in the live stack (`COMPOSITION_WORKER_ENABLED=false`) → the
  engine runs synchronously and returns JSON, so the confirm completes the generation.
- **Tests** (`tests/unit/test_mcp_server.py` + `tests/unit/test_mcp_actions.py`):
  add `composition_generate` to `EXPECTED_TOOLS` (+ TIER_W); propose mints a verifiable
  token w/ the right descriptor/payload for both scene + chapter; XOR validation; confirm
  effect dispatches the right engine coroutine (stubbed) for each path.

## M2 — `lore_enrichment_auto_enrich` (lore-enrichment-service — NEW facade)
- **`app/mcp/server.py`** (NEW): minimal `loreweave_mcp` facade. ONE Tier-A tool
  `lore_enrichment_auto_enrich(project_id, book_id, embedding_model_ref,
  generation_model_ref, technique?, max_gaps?, coverage_limit?, max_spend_usd?, top_k?,
  targets?)`. Identity from the envelope (X-Internal-Token + X-User-Id) — stricter than
  the REST principal (which is unverified-JWT). Reuse the auto-enrich core (detect →
  top-N → create job + request → enqueue). Auto-enrich only ever produces QUARANTINED
  proposals + is cost-capped (`max_spend_usd`) → Tier-A (not a confirm-gated W).
- **`app/main.py`**: mount `/mcp` + run the session manager in the lifespan (mirror
  composition `main.py`).
- **`infra/docker-compose.yml`**: add `lore-enrichment=http://lore-enrichment-service:<port>/mcp`
  to `AI_GATEWAY_PROVIDERS` so the gateway federates it.
- **Tests** (`tests/test_mcp_server.py` NEW): catalogue (1 tool, valid `_meta`, no scope
  leak), auth rejection, handler enqueues with envelope identity.

## VERIFY / live-smoke
- Unit suites green (composition + lore-enrichment); `python scripts/ai-provider-gate.py` clean.
- Rebuild composition-service + lore-enrichment-service (+ ai-gateway) images; live MCP
  `tools/list` shows both new tools over the wire; drive each once on the live stack
  (≥2 services: gateway + owning service + book/glossary).

## Scenario (the supreme goal)
One continuous agent-driven run on a FRESH book: create → web-search+suggest ontology →
approve → import → extract glossary → translate glossary+chapter to vi → build KG → build
wiki → enrich (via `lore_enrichment_auto_enrich`) → write a new chapter (via
`composition_generate`) — proving the journey through the assistant.
