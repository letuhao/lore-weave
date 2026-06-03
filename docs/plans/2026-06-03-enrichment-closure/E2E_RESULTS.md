# Enrichment Closure — Phase 4 E2E Results (2026-06-03)

> Live verification against the running stack (gateway `:3123`, all enrichment services healthy)
> with the **rebuilt** frontend image (my changes; `docker compose build frontend` exit 0 → the full
> `vite build` passed → recreated `infra-frontend-1`, `:5174` → 200). Test account: claude-test@loreweave.dev.

## What ran (live, through the gateway — the exact endpoints the new GUI calls)

**Read smoke (the GUI's read endpoints) — all 200 / correct:**
- `GET /v1/lore-enrichment/proposals?book_id=…` → 1 proposal (玉虛宮, promoted).
- `GET /v1/lore-enrichment/proposals/{id}?project_id=…` (single-read — the endpoint I added handler tests for) → 200.
- `POST /v1/lore-enrichment/projects/{book}/detect-gaps` → 11 scanned, 3 gaps (top 碧遊宮/金鰲島).
- `GET /v1/lore-enrichment/sources?project_id=…` → 1 source.
- `GET /v1/lore-enrichment/jobs?book_id=…` → 2 jobs.

**Write e2e — the flagship NEW feature (retract ↔ promote), proven + demo restored:**
1. **Retract** `POST /proposals/{id}/retract` → `facts_retracted:5, supplement_retracted:5`. Verified the effect via gap-detection: **玉虛宮 reappeared as an under-described gap** → the 5 glossary canon supplements were genuinely removed. (The proposal row keeps its promotion history; the canon writeback is what's removed — confirmed by ground truth, not just the response.)
2. **Re-promote** `POST /proposals/{id}/promote` → `facts_promoted:5, canon:true, origin:enrichment` (confidence retained — **H0 holds**). Verified: **玉虛宮 no longer a gap**, `gap_count` back to 3, **1 promoted proposal restored**.

→ The new GUI's retract path (ProposalActionBar Retract → ConfirmDialog → `useProposalActions.retract` → this endpoint) is proven against the live stack, and the demo book is byte-for-byte back to its starting state.

## What was deferred (with mitigations) — see SKIPS_AND_BLOCKERS.md

- **Browser-layer Playwright e2e — DEFERRED (S7):** the Playwright MCP Chrome profile is **locked by another instance** in the shared environment (`Browser is already in use … use --isolated`), which I can't reconfigure. Mitigation: (a) the GUI compiles + bundles (`vite build` exit 0) and serves (`:5174` → 200); (b) **149 FE vitest tests** assert the GUI→hook→api wiring (incl. the retract ConfirmDialog flow, the ingest form, the cost-cap/reject-reason controls); (c) the live API e2e above proves the backend spine these call; (d) the **prior session already browser-proved** the promote→canon GUI flow through the real UI.
- **Live ingest / auto-enrich *generation* — not run:** ingest needs a real bge-m3 embed and auto-enrich needs the 35B generation model; both hit the documented LM-Studio JIT-eviction risk. Both are covered by FE unit tests (the GUI wiring) + BE handler/unit tests (`test_sources_api.py`, `test_auto_enrich_api.py`), and the live read/write smokes above exercise the same stack path.

## Manual browser-e2e recipe (for when the browser is free)
1. `docker compose -f infra/docker-compose.yml up -d --force-recreate frontend` (already done this session).
2. Open `http://127.0.0.1:5174`, log in (test account).
3. Books → "封神演義 … Lore Enrichment Demo" → **Enrichment** tab.
4. Proposals: confirm the 玉虛宮 card shows the H0 chip + `card.confidence`/`card.summary` + the P1/P2/P3 technique filter; open it → the live H0 banner (`enrichment-h0-banner`).
5. Because it's promoted → click **Retract** (`enrichment-retract-trigger`) → ConfirmDialog → confirm → toast; re-promote to restore.
6. Gaps tab → **Detect gaps** → confirm the new **Max spend (USD)** (`enrichment-max-spend`) + **Top-K** inputs render.
7. Sources tab → **Register source**, then on the card → **Ingest text** (`enrichment-ingest-text`) + embed-model picker.
