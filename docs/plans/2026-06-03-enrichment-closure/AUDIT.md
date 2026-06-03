# Enrichment Closure — Phase 0 Audit (2026-06-03)

> Source: parallel 4-auditor workflow `wf_44c142cf-e54` (full structured output archived in the
> run transcript). This is the synthesized, prioritized, actionable gap report that drives Phases 1–4.

## 1. GUI write-action wiring (12 actions traced onClick→hook→api.ts)

**Functional (8):** detect-gaps · register-source · resume-job · approve · edit · promote · list/filter proposals · view detail.

**Partial (2):**
| Action | Gap | Priority |
|---|---|---|
| **auto-enrich** | Form collects model refs + technique + max_gaps and gates on both refs, but does NOT collect `max_spend_usd` (the **cost-cap safety control**) or `top_k`. Both are typed through the hook+api but have no input. `GapsPanel.tsx:153-159` omits them. | **HIGH** (cost safety) |
| **reject** | Button reaches the API but `ProposalDetail.tsx:98` always calls `reject(proposal)` with no reason; no reason input exists → the supported rejection-reason capability is dead. | MED |

**Missing entirely (2) — these are the "users can't enrich" gaps:**
| Action | Gap | Priority |
|---|---|---|
| **ingest-source** | `enrichmentApi.ingestSource` (api.ts:143-159) is never imported by any hook/component. `useEnrichmentSources` exposes only list+register; SourcesPanel cards are display-only. **A registered corpus can never receive text/embeddings from the GUI** — register creates an empty shell. Recook/retrieval grounding therefore has no UI path to data. | **HIGH** |
| **retract** | `enrichmentApi.retract` + `useProposalActions.retract` exist but `retract` is omitted from the `ProposalActions` interface (`ProposalDetail.tsx:11-18`) and never rendered. Promoted proposals show only a static note. **An author can never un-promote canon from the GUI.** | **HIGH** |

## 2. Draft-vs-code parity (vs enrichment-review.html / enrichment-gaps-sources.html)

The load-bearing ④ promote gate is faithfully built (PromoteDialog copy, action bar, auto-approve-then-promote, two-pane review, VerifyPanel flag/clean/degraded, ProvenancePanel grounding+license, all 4 panels incl. Jobs). Several code additions are **good depth beyond the mockup** (terminal-state collapse, skipped-unlicensed-sources row, empty/loading states, inline edit, client project filter, provider-registry model pickers instead of hard-coded names). **Intentional spec override:** Enrichment is a book TAB, not the sidebar item the mockup drew — keep (documented D-PARITY-SIDEBAR).

**Build-driving parity gaps (missing/partial):**
- **ProposalCard** (thin vs mockup): missing H0 chip · confidence value · "N dimensions · grounded on N sources" line · per-card advisory-flag preview · auto_rejected dimming+reason · content clamps 1 line (mockup 2).
- **Proposals filter:** missing the **P1/P2/P3 Technique filter** entirely; default status `all` vs mockup `proposed`.
- **Tab strip:** missing numeric count badges (7/5/5).
- **ProposalDetail header:** missing "kind · descriptor · book" subtitle; H0 banner is a static one-liner chip, not the warning-colored banner with **live** origin/confidence/review_status. **DimensionList:** missing inline recook-highlight spans · "+ show remaining" expander · "· N dimensions" count.
- **VerifyPanel:** one combined "clean" line vs the mockup's four explicit ✓ rows (contradiction/anachronism/injection/regurgitation).
- **ProvenancePanel:** missing "recook · abstracted-facts (②)" attribution row + gen model_ref display.
- **Action bar:** missing the author-only caption copy (no i18n key).
- **Proposals:** no error-state branch (failed query silently shows empty state).
- **GapsPanel:** missing per-row checkboxes · per-row "enrich →" · already-enriched "(5/5)"+"re-enrich" state (`present_dimensions` unused); config uses a Max-gaps numeric input vs the mockup's cost-cap display.
- **SourcesPanel:** card meta missing chunk-count + "embedded ✓"; copyrighted card not dimmed; **no ingest step** (registration only); no "+ Register & ingest" tile.

## 3. FE test coverage — **ZERO tests across 21 files**

No co-located `*.test.*`, no `__tests__/`. Files: api, types, context, 5 hooks, 13 components.

**House style (verified vs knowledge/ + chat/):** Vitest 2 + jsdom + RTL 16. Global `frontend/vitest.setup.ts` mocks `react-i18next` so `t(key)` returns the **dotted key verbatim** (ignores defaultValue) → **assert on KEY strings**, not English. No QueryClient/i18n provider in setup — each file builds its own `QueryClientProvider` (retry:false). Mock the **api facade** (`vi.mock('../../api', importActual + enrichmentApi:{…})`), NOT `apiJson`. `@/auth` → `{ accessToken:'tok' }`. `sonner` mocked via `vi.hoisted`. **GapsPanel extra dep:** `providerApi.listUserModels` from `@/features/settings/api` (capability chat/embedding) — mock it. New tests → `features/enrichment/{hooks,components}/__tests__/*.test.tsx`. Run: `pnpm --filter frontend test`.

Priority targets (full per-target case lists in the workflow output): `useProposalActions` (esp. the auto-approve-then-promote branch + retract), `useGaps`, `useEnrichmentSources` (+ingest once built), `useEnrichmentJobs`, then the panels.

## 4. Backend test coverage — 609 pytest, strong on logic, **thin on the HTTP handler layer**

26 endpoints across 7 routers. "tested" = TestClient-driven handler OR exhaustively-tested delegate class. **Untested handler surfaces (the "other features not tested"):**
1. **Job lifecycle** `start/pause/resume/cancel` + `_transition_job()` — Q3 owner+project scoping SQL, 404/409 mapping, resume Redis enqueue best-effort. **Zero handler tests** (JobStateMachine tested in isolation only). resume is the F-C14-1/051 load-bearing path.
2. **GET /internal/eval/{project_id}/gate-status** — the **fail-CLOSED P2/P3 unlock** surface + `require_internal_token` guard. Untested handler → a regression could false-green-unlock paid P2/P3.
3. **GET /jobs/{id}** & **GET /proposals/{id}** single-reads — owner/project scoping → 404 "no existence oracle" (**IDOR risk**), untested.
4. **auto-enrich cost-cap round-trip** — `max_spend_usd`/`eval_reserve_fraction`/`top_k` persisted to job+request (prior false-green: "cost-cap inert" F-C14-1); zero-gaps no-enqueue branch; unknown-technique 400.
5. **POST /jobs handler** exception→status mapping — InactiveStrategyError→409 + persisted failed-job audit row; UnknownStrategyError→400; all-described→400.

**Infra:** host venv `python -m pytest` from `services/lore-enrichment-service/`; `requirements-test.txt` = `-r requirements.txt` + `-e ../../sdks/python`. `conftest.py` sets throwaway env before `import app.*` (fail-fast Settings). Two tiers: host TestClient with `dependency_overrides[get_db]` fake pool + respx for cross-service; DB-integration `tests/db/` skips without a real Postgres DSN (compose PG host:5555). 609 collected (579 host + 30 DB-skip).

## 5. Phase plan derived from this audit

- **Phase 1a (functional — make it usable):** ingest-source UI+hook · retract UI · auto-enrich cost-cap(`max_spend_usd`)+`top_k` · reject-reason input.
- **Phase 1b (parity — close meaningful draft gaps):** Technique filter · count badges · ProposalCard enrichments · live H0 banner · author-only caption · Proposals error-state · DimensionList count/expander · VerifyPanel 4-rows · ProvenancePanel attribution+model_ref · GapsPanel per-row/already-enriched · SourcesPanel chunk/embedded meta + copyrighted dimming. (Items where the code is a deliberate improvement over the mockup → document as accepted divergence, don't slavishly match.)
- **Phase 2 (FE tests):** full vitest suite per the §3 plan, asserting parity per §2.
- **Phase 3 (BE tests):** the 5 untested handler surfaces in §4 (TestClient `test_jobs_api.py`, `test_eval_api.py`, `test_proposals_api.py` + auto-enrich cost-cap assertions).
- **Phase 4 (e2e):** Playwright full loop (register→ingest→detect→auto-enrich→review→promote→retract) or documented skip.
