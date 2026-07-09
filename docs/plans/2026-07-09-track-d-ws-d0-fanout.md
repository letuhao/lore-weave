# Track D · WS-D0 — parallel fan-out plan

**Spec:** [`../specs/2026-07-09-mcp-tool-liveness-eval/`](../specs/2026-07-09-mcp-tool-liveness-eval/README.md)
· **Contracts:** CD1–CD5 (frozen) · **Status:** ready to execute · **All open questions closed.**

**Size:** L→XL. **Strategy:** *parallel BUILD on provably-disjoint files → serial integrate → ONE verify.*
(Repo precedent: `fanout-independent-slices-parallel-build-serial-integrate`.)

---

## 0. The one rule that makes this safe

> **A file has exactly one owner across a wave.** Two slices touching the same file in parallel
> worktrees will conflict, and a silent bad merge in `tool_discovery.py` or `tool-policy.ts` breaks
> the whole discovery spine.

Two files are contested and therefore **pre-assigned to Wave 0**, done serially, before anyone forks:

| Contested file | Wanted by | Resolution |
|---|---|---|
| `chat-service/app/services/tool_discovery.py` | S-CAT (`GROUP_DIRECTORY`, `_DOMAIN_ALIASES`) **and** S-SPEND (`tool_paid()`) | both land in **Wave 0** |
| `mcp-public-gateway/src/scope/tool-policy.ts` | S-CAT (`Domain` union) **and** S-WEB (`web_search` entry) | both land in **Wave 0** |

---

## Wave 0 — foundations (SERIAL, one agent, ~small)

Everything downstream imports these. Nothing forks until Wave 0 is green.

| # | Task | Files |
|---|---|---|
| **0a** | **Kit fields.** Go: `MetaKeyPaid` + `WithPaid(m)`, `MetaKeySupersededBy` + `WithSupersededBy(m, name)`. Py: `require_meta(..., paid=True)`. | `sdks/go/loreweave_mcp/meta.go`, `sdks/python/loreweave_mcp/meta.py` |
| **0b** | **C1 `research` category.** `GROUP_DIRECTORY += research` on **both** engines; `_DOMAIN_ALIASES: web → research` on both; `Domain` union `+= 'research'`. Update the **two drift-lock arrays**. | `ai-gateway/src/federation/find-tools.ts`, `chat-service/app/services/tool_discovery.py`, `mcp-public-gateway/src/scope/tool-policy.ts`, `ai-gateway/test/find-tools.spec.ts:207`, `chat-service/tests/test_tool_discovery.py` |
| **0c** | **`tool_paid()` reader** (mirrors `tool_async()`). | `chat-service/app/services/tool_discovery.py` |
| **0d** | **C-GW prefix map:** `EXTRA_PREFIX_MAP.settings += 'web_'` — **without this the new tool is silently dropped** (`catalog.ts:71`). | `ai-gateway/src/config/config.ts` |

**Exit:** `ai-gateway` + `chat-service` discovery suites green; `CATEGORY_ENUM` contains `research`.

---

## Wave 1 — parallel fan-out (6 slices, provably disjoint)

Each slice = one worktree agent. **No two slices share a file.**

### S-GLOSSARY *(long pole — size L)*
Adopt `_meta` on all ~55 glossary tools: `tier` + `scope`, `paid` on `glossary_web_search` /
`glossary_deep_research` / `glossary_plan` / `glossary_extract_entities_from_doc`.
**Calibrate exactly as knowledge did** (`f191cb858`): reversible→`A`, destructive/`confirm_token`→`W`,
read/derive→`R`. Read each handler; do **not** trust names — `propose_*` spans both W(token) and
A(draft). Add the `tools/list` wire gate.
- **Owns:** `services/glossary-service/internal/api/*.go` (+ its tests)
- **Watch:** `glossary_web_search` is *demoted in place* here only if S-WEB lands after — see Wave 2.

### S-COMPOSITION *(size M)*
Mark the **8 audited** async omissions. ~~+ fix `lore_enrichment_auto_enrich` `A`→`W`~~
**[corrected 2026-07-10]** `lore_enrichment_auto_enrich` **stays Tier A** — the handler mints **no
`confirm_token`, so it cannot satisfy the Tier-W contract (the consumer would await a token never
sent), and its module docstring records Tier A as a deliberate choice: the job only produces
**quarantined** proposals (never a canon write) and is **cost-bounded** (`max_spend_tokens` + per-job
cap). It was already `async_job=True`. No source change; the "A→W" line was a wrong premise.
- 5 Tier-W confirm-then-job: `motif_mine`, `arc_import_analyze`, `conformance_run`,
  `authoring_run_start`, `authoring_run_resume` *(precedent: `kg_build_graph` is W **and** async)*
- 3 Tier-A enqueue-at-tool-time: `plan_propose_spec`, `plan_apply_revision`, `plan_compile`
- **Owns:** `services/composition-service/app/mcp/server.py`, `services/lore-enrichment-service/app/mcp/server.py`

### S-SPEND *(size M — the exposure)*
**Layer 1 (MVV).** Gate branch in the tool loop, **orthogonal to tier**, mode-independent:
`if tool_paid(def) and not spend_approved(user, tool): suspend with a spend-approval card`.
Reuse the existing `tool_approval` suspend/resume + `user_tool_approvals` allowlist.
- **Owns:** `chat-service/app/services/stream_service.py`, `chat-service/app/db/tool_approvals.py`
- **Consumes:** `tool_paid()` from Wave 0. **Does not touch** `tool_discovery.py`.

### S-PRODUCER *(size M)*
Move INV-6 neutralization (caps + `_neutralize` + `_safe_http_url`) to the **producer**
(`/internal/web-search`) so glossary-Go / composition-Py / the new tool stop triplicating it. Then
**delete** `composition-service/app/clients/web_search_client.py`'s copy (keep its HTTP client — it is
a service-to-service call with a graceful-degrade contract; do **not** convert it to an MCP tool call).
- **Owns:** `provider-registry-service/internal/api/server.go` (web-search path),
  `provider-registry-service/internal/provider/web_search.go`,
  `composition-service/app/clients/web_search_client.py`

### S-HARNESS *(size L — fully independent)*
TLE P0: SSE driver · **confirm resolver** · **fixture factory** · effect oracle · async poller ·
matrix reporter. Prove on 10 tools spanning R/A/W/async.
- **Owns:** `scripts/eval/tool_liveness/**` (all new), `docs/eval/tool-liveness/**`
- **Zero overlap with any other slice.** Start it first — it has the longest lead time.

### S-GATES *(size S — but must run LAST in the wave)*
Per-service `tools/list` wire gate (CD1 enforcement), pattern from
`knowledge-service/tests/test_mcp_server.py`.
- **Owns:** one new/edited test file per service
- **Depends on** S-GLOSSARY + S-COMPOSITION having tiered their tools ⇒ schedule at the **end of
  Wave 1**, or fold into Wave 2.

---

## Wave 2 — serial integrate (single agent, no forks)

1. **S-WEB — universalize `web_search`.** *(Serial: it spans 4 services and depends on 0a/0b/0d + S-PRODUCER.)*
   - Register **`web_search`** on **provider-registry** (`internal/api/mcp_server.go`), handler calls its
     **own** internal web-search (no HTTP hop). `_meta`: `tier R`, `scope none`, **`paid true`**.
   - **Demote `glossary_web_search` in place** on glossary-service: `VisibilityLegacy` +
     `WithSupersededBy("web_search")`. It **cannot move** (prefix gate).
   - `tool-policy.ts`: `web_search: { tier: 'paid_read', domains: ['research'] }`; keep the legacy row so
     existing public keys keep working.
   - Prompt + skill text: `universal_skill.py` → `web_search`, `tool_list(category="research")`.
   - **Fix the compaction bug:** `DEFAULT_EXCLUDE_TOOLS` finally matches the wire name. Add a test
     pinning it (it has silently matched **nothing** since it was written).
2. **Hot-path** `web_search` → `ALWAYS_ON_CORE_NAMES` (**9→10 of 10**). *Only after S-SPEND is green.*
3. **ONE combined VERIFY** across every touched service (see below).

---

## Dependency graph

```
Wave 0 (serial)  0a kit ─┬─────────────────────────────────────────┐
                 0b C1 ──┤                                          │
                 0c tool_paid ─┐                                    │
                 0d prefix-map ┤                                    │
                               │                                    │
Wave 1 (parallel)              ▼                                    ▼
   S-GLOSSARY ─┐        S-SPEND (needs 0c)                    S-WEB needs
   S-COMPOSITION ┤      S-PRODUCER                            0a+0b+0d+S-PRODUCER
   S-HARNESS ────┤                                                  │
                 └────► S-GATES (needs GLOSSARY+COMPOSITION)        │
                                                                    ▼
Wave 2 (serial)                                          S-WEB → hot-path (needs S-SPEND)
                                                              → ONE VERIFY
```

---

## Verify (serial, once — never per-slice)

Cross-service change ⇒ unit-green is **insufficient** (CLAUDE.md VERIFY gate).

- `ai-gateway` jest · `mcp-public-gateway` jest · glossary Go · provider-registry Go · composition +
  lore-enrichment + knowledge pytest · chat-service discovery + `test_tool_discovery.py` +
  `test_workflow_runner.py` (avoid the 5-min `test_stream_service.py` unless the loop changed — S-SPEND
  changes it, so run it).
- **Live smoke (required):**
  1. `tools/list` on the rebuilt gateway shows `web_search`, **not** dropped, and category `research`.
  2. A real gemma turn: an NL research ask elicits `web_search` → the **spend-approval card appears**
     (first use) → approve → the call runs. *This is the whole point of D0b.*
  3. `glossary_web_search` still resolves (legacy alias) and is labeled `superseded_by: web_search`.

---

## Risk register

| Risk | Mitigation |
|---|---|
| **C-GW prefix gate silently drops `web_search`** (`catalog.ts:71`) — a *warn*, not an error | 0d lands in Wave 0; live-smoke #1 asserts presence in `tools/list` |
| Legacy alias is a **new pattern** (same handler, two names) + **first prod use** of `superseded_by` | glossary keeps its own handler; only `_meta` changes. Low risk |
| `tool_discovery.py` / `tool-policy.ts` merge conflict | pre-assigned to Wave 0 (serial) |
| Glossary tier assignment is **judgment-heavy** (55 tools) | require the agent to read each handler + cite `confirm_token` presence; reviewer spot-checks the W set |
| Tiering glossary **changes gating** (ask-mode blocks; approval cards appear) | same, intended, change as knowledge `f191cb858`; call it out in the commit |
| `paid` tools whose spend already flows through the **job path** are already reserved | only mark `paid`; do **not** double-gate. The exposure is the **sync** path only |
| Public keys lack `domain:research` | legacy `glossary_web_search` row retained ⇒ no public break |

---

## Explicitly out of scope for WS-D0

- **Layer 2 spend** (`per_call` pricing dimension + `Reserve/Reconcile` on the sync path + deriving
  `paid_read` from `_meta.paid`). Real budgeting for web-search; **needs a pricing dimension that does
  not exist**. → its own workstream after WS-D0.
- WS-D1 (`propose_*` lint), WS-D2+ (harness beyond P0), the frontend 12, the macro journeys.
