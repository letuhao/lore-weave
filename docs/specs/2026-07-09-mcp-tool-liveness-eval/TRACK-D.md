# Track D brief — Tool Liveness & Metadata Correctness

**One-liner:** make every MCP tool *declare what it is* and *prove it works when an LLM calls it* —
then make that proof a precondition for shipping workflows.

- **Read first:** [`README.md`](README.md) (the measured gap + phasing) · [`contracts.md`](contracts.md)
  (CD1–CD4 — Track D **owns** all four).
- **Why it's a track, not a chore:** Tracks A/B/C built the machinery to *find*, *load*, and
  *sequence* tools. None of them proved the tools **work** when an LLM drives them. The flagship S06
  baseline recorded **`effectful_tool_calls: 0`** while the agent claimed *"I have locked that into
  the core of the project."* Shipping curated workflows on unproven tools ships that lie at scale.

---

## Owns (services · files)

| Area | Files |
|---|---|
| Kit (`_meta`) | `sdks/go/loreweave_mcp/meta.go` (`WithPaid`), `sdks/python/loreweave_mcp/meta.py` (`paid=`) |
| glossary-service (Go) | `internal/api/mcp_server.go`, `*_tool.go`, `RegisterBookTools` — `_meta` adoption |
| composition · lore-enrichment (Py) | `app/mcp/server.py` — `async`/`paid`/tier corrections |
| Every domain service | a `tools/list` meta gate test (pattern: `knowledge-service/tests/test_mcp_server.py`) |
| mcp-public-gateway (TS) | `src/scope/tool-policy.ts` — derive `paid_read` from `_meta.paid` |
| Harness | `scripts/eval/tool_liveness/**` (new) |
| Reports | `docs/eval/tool-liveness/<date>/{matrix.json,matrix.md,transcript.jsonl}` |
| **Coordinated (Track A owns)** | `agent-registry .../workflows.go` `validateWorkflow` — the CD4 ship gate |

---

## Deliver in order

### WS-D0 · Metadata correctness — **fix the spend hole first** *(size L)*
> Must land before any glossary probe runs, or every probe tests the wrong gating.

- **D0a — `_meta.paid`** (CD1): kit field in Go + Py; mark the ~25 money-spending tools.
- **D0b — glossary `_meta` adoption**: assign `tier` + `scope` to all `/mcp` + `/mcp/admin` tools,
  calibrating exactly as knowledge did (reversible→`A`, destructive/`confirm_token`→`W`,
  read/derive→`R`). **Highest priority within D0b:** `glossary_web_search` and
  `glossary_deep_research` are untiered ⇒ `R` ⇒ runnable in read-only *ask* mode with no approval
  card, and both are **paid**. Fix these two first.
- **D0c — async audit** *(do not trust the inventory)*: for each of `composition_motif_mine`,
  `composition_arc_import_analyze`, `composition_conformance_run`, `plan_propose_spec(mode=llm)` —
  **read the handler**, confirm it enqueues, and only then mark `async`.
- **D0d — `lore_enrichment_auto_enrich` `A` → `W`**: it is `async` **and** `paid` (verified). An
  auto-applying paid async tool contradicts the money model; `mcp-public-gateway` already
  reclassifies it `write_confirm`. Reconcile the internal tier, then derive the public one.
- **D0e — per-service wire gates** (CD1 enforcement) for every domain service.

**Exit:** zero tools with absent `tier`/`scope`; `paid ⇒ tier != R` holds repo-wide; each service has
a `tools/list` gate. → **ND1**

### WS-D1 · `propose_*` semantics (CD2) *(size S)*
Declare each `propose_*` tool's pattern (token vs draft) in its description; add the
`propose ⇒ tier ∈ {A,W}` lint. **Audit `glossary_propose_aliases`** (it touches
`entity_attribute_values` — confirm draft-only). No renames: the "propose = direct write" finding was
**verified false** (see `contracts.md` → Rejected findings).

### WS-D2 · TLE harness P0 *(size L)*
Build the six components (`README.md` §5). Reuse the SSE driver + tool-record parser; **build** the
three that don't exist:
1. **Confirm resolver** — the single biggest gap: no NL harness in the repo posts to
   `/v1/<domain>/actions/confirm`. Without it all 37 Tier-W tools suspend and never execute.
2. **Fixture factory** — throwaway book + project + chapter, torn down after. The safety boundary:
   *no probe may touch an id it did not create.*
3. **Effect oracle** + async poller + matrix reporter.

Auth through the real `/v1/auth/login` edge. Agent model = local gemma (**$0**). Pre-allowlist
`user_tool_approvals` so Tier-A writes don't stall — and add one test asserting the card *does*
appear when not allowlisted.

**Exit:** 10 tools spanning R/A/W/async, all four gates, ≥1 genuine bug found. → **ND2**

### WS-D3 · TLE P1 — the workflow-critical set + ship gate *(size M)*
Probe every tool an authored C3 workflow can reference. Wire CD4 into `validateWorkflow`
(**warn** at this stage) and enforce "no RED-G3 tool in `tool_list`".
**Exit:** the ship gate is real. → **ND3** *(this is the actual "before we ship workflow" gate)*

### WS-D4 · TLE P2 — full sweep *(size XL, grind)*
All 206 domain tools, batched per service (glossary 55 + composition 56 are the long poles).
Flip CD4 from warn → **reject**.
**Exit:** matrix ≥95% non-RED or explicitly `WAIVED` with a reason.

### WS-D5 · Frontend tools (12) via Playwright *(size M)*
The loop must **suspend**; the real FE resolver executes; G4 asserts the human-applied effect.
Simulated resolver is acceptable for G3; G4 needs the browser
(precedent: `agent-gui-loop-needs-live-browser-smoke-not-raw-stream`).

### WS-D6 · Macro journeys *(size M)*
S00–S06 + authored workflows: ordering, gates honored, async honesty, **zero false persist-claims**.
**Exit:** flagship S06 passes with `effectful_tool_calls > 0`. → **ND4**

---

## Integration nodes

| Node | Gate |
|---|---|
| **ND1** — after WS-D0 | every tool declares tier/scope; `paid ⇒ tier != R`; wire gates green ⇒ probes test the *right* gating |
| **ND2** — after WS-D2 | harness proven end-to-end incl. confirm resolution + effect read-back |
| **ND3** — after WS-D3 | CD4 ship gate live ⇒ **Track C's curated workflows may ship** |
| **ND4** — after WS-D6 | flagship S06 green with real effects ⇒ the platform's headline claim is true |

---

## Definition of done

1. No MCP tool ships without `tier` + `scope`; job-starters declare `async`; money-spenders declare
   `paid` and are never tier `R`. A CI gate per service enforces it on the real wire.
2. `docs/eval/tool-liveness/<date>/matrix.json` exists, is **generated** from the live gateway, and a
   tool without an authored probe is a RED cell.
3. Every tool in the workflow-critical set passes **G1–G4** — including the confirm round-trip for
   Tier-W and terminal-status polling for async.
4. A workflow cannot reference an unproven tool (CD4), and `tool_list` never advertises a RED-G3 tool.
5. Flagship S06 shows `effectful_tool_calls > 0` and `persist_claims_without_write == []`.

## Watch

- **Safety:** destructive probes (`book_purge`, `glossary_entity_delete`, `memory_forget`, …) run
  **only** against the fixture. Repo precedent: `kg-integration-tests-truncate-shared-dev-db` — an
  ontology test once truncated the live dev DB. Never scope a probe to a real book.
- **Cost:** the agent is free (local gemma); **tools** are not. ~25 spend real money. Default
  `SKIP → UNTESTED-PAID`; opt in with `--allow-paid` + a hard USD cap and minimal inputs.
- **Don't trust the inventory.** One of its four "findings" was verified **false** and one is still
  unproven. Read the handler before you mark a tool `async` or rename anything.
- **Shared checkout:** Tracks B/C are owned by other sessions. Track D touches `validateWorkflow`
  (Track A's file) for CD4 only — coordinate via the board.
