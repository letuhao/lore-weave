# Cycle 5: PLATFORM D4-03 wiki-from-KG

> RAID cycle brief. Cross-service (glossary-service + knowledge-service). Additive only.
> Resolves H3: a real renderer for enriched lore, replacing the empty `generateWikiStubs`.

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Generate rich wiki **content** (article body) from an entity's KG neighborhood, replacing the empty `generateWikiStubs` (which today only inserts blank `wiki_articles` rows). Walk the entity + its 1-hop KG neighborhood (relations, facts) via the knowledge-service read API, render a structured body, and persist it through the wiki feature **hosted inside glossary-service** (`wiki_articles`/`wiki_revisions`). Carry a `source_type` distinction so the body shows whether facts came from authored `glossary` canon vs `enriched` quarantine. **Additive only** — extend the existing handler/path, do not rewrite the wiki schema or its ownership/auth.
- **Acceptance gate:** `scripts/raid/verify-cycle-5.sh` exits 0 (created by this runner).
- **Top 3 LOCKED decisions consumed:** Q4, H0, Q2.
- **DPS count:** 2
- **Estimated wall time:** 3–4 hours

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C1
- Files expected to exist (grep-able paths):
  - `services/lore-enrichment-service/app/clients/` (KG-read port from C1 — `KnowledgeReadPort` Protocol: graph, graph-stats, context)
  - `services/glossary-service/internal/api/wiki_handler.go` (`generateWikiStubs`, ~line 794)
  - `services/glossary-service/internal/api/server.go` (route `/v1/glossary/books/{book_id}/wiki/generate`, ~line 122)

## Scope (IN)
- **Wiki body renderer in glossary-service:** extend `generateWikiStubs` (or add a sibling generator behind the same `/wiki/generate` route) so it produces a non-empty article **body** per entity instead of a blank stub. Body is assembled from the entity + its KG neighborhood (relations + facts) read via knowledge-service.
- **KG-neighborhood read:** call the knowledge-service graph/context read API for the entity's 1-hop neighborhood. NEVER write Neo4j canonical content directly (Q2).
- **`source_type` distinction carried into the body:** each rendered fact/section is tagged/visually distinct as `glossary` (authored canon, conf=1.0) vs `enriched` (quarantined, `pending_validation=true`, conf<1.0). Enriched material is clearly marked, never silently merged as canon (H0).
- **Persist through the wiki feature:** write body + a `wiki_revisions` entry through the existing glossary wiki path; preserve current owner-auth (`verifyBookOwner`) and per-book scoping.
- **`scripts/raid/verify-cycle-5.sh`:** boots glossary + knowledge-service, seeds one entity with a small neighborhood, calls `/wiki/generate`, asserts a non-empty body persisted with correct `source_type` markers. Exits 0 on pass.
- Unit tests: renderer over a fixed KG-neighborhood fixture → expected body sections; `source_type` tagging correct; empty-neighborhood → graceful minimal body (no crash).

## Scope (OUT — explicitly)
- NO enrichment generation/strategies (C9–C11), NO gap detection (C6/C7), NO proposal store/review (C13).
- NO write to Neo4j canonical content; NO new RAG framework / langchain / llamaindex.
- NO change to wiki ownership, auth, or `wiki_articles`/`wiki_revisions` table shape beyond additive columns if strictly required (prefer none).
- NO edits to `world-service`/`game-server`/`tilemap`, `infra/existing-prod/`, or other agents' files.
- NO hardcoded model names — if LLM-assisted prose is used, resolve via provider-registry. (Prefer deterministic templated rendering for P1; LLM prose optional and registry-resolved only.)
- NO eval-file edits (climate/geo eval untouched).

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: glossary-service `go test ./internal/api/...` (wiki renderer + `source_type` tagging + empty-neighborhood unit tests).
- Lints pass: `gofmt`/`go vet` clean on touched glossary files; lore-enrichment client touched files pass ruff/mypy if any.
- Integration smoke: **`live smoke: entity → generated wiki body persisted`** — real cross-service call on a stack-up (glossary calls running knowledge-service for the neighborhood, persists a non-empty body with `source_type` markers). This token is MANDATORY (CLAUDE.md VERIFY rule, ≥2 services). If full stack unbootable, record `live infra unavailable: <reason>` or `LIVE-SMOKE deferred to D-C5-LIVE-SMOKE` in SESSION_PATCH.
- `scripts/raid/verify-cycle-5.sh` exits 0.

## DPS parallelism plan
- DPS 1: glossary-service wiki body renderer + `source_type` tagging + persist via wiki revision; unit tests (worktree: `services/glossary-service/internal/api/wiki_handler.go`, new `wiki_render*.go`, `*_test.go`). (return budget: 1500 tokens summary)
- DPS 2: KG-neighborhood read wiring (consume C1 `KnowledgeReadPort`/glossary→knowledge read client) + `scripts/raid/verify-cycle-5.sh` + fixtures (worktree: `services/lore-enrichment-service/app/clients/`, `scripts/raid/verify-cycle-5.sh`). (return budget: 1500 tokens summary)

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **H0 leak:** does any enriched-sourced fact render as canon, or lose its `source_type='enriched'` / quarantine marker on the way into the wiki body? Enriched must stay visibly distinct from `glossary` canon.
- **Mock-only false-green:** are the wiki-body tests proving real cross-service reads, or do they mock the KG and never exercise the neighborhood call? Demand the live-smoke token evidence.
- **Q2 violation:** any direct Neo4j canonical write? Must read-only from KG, write only through the glossary wiki path.
- **Additive regression:** did `generateWikiStubs` lose its prior behavior (owner-auth via `verifyBookOwner`, per-book scoping, `kind_codes`/`limit` filtering, "skip entities that already have an article")? Confirm backward-compat.
- **Hardcoded model name** if any LLM prose path was added (must be registry-resolved).
- **Empty/missing neighborhood:** does a sparse entity crash or produce a malformed body?

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (renderer, KG-neighborhood read, `source_type` distinction, persist, verify script, tests).
- No OUT items touched (no Neo4j canonical write, no enrichment gen, no wiki-schema rewrite, no prod/world-service edits, no hardcoded model).
- All acceptance criteria met incl. live-smoke token.
- Cross-cycle invariants intact: H0 (enriched ≠ canon, marked + quarantined), Q2 (glossary SSOT write path only), additive/backward-compatible platform edit.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle row + parallelism: [CYCLE_DECOMPOSITION.md](../../plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md) (C5 row, Notes "Platform deferrals Option B").
- LOCKED decisions: [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md) (H0, Q2, Q4, "pull in drifting platform deferrals", D4-03 wiki-from-KG).
- Plan + ground truth: [PLAN.md](../../03_planning/lore-enrichment/PLAN.md) · [CLARIFY_GROUND_TRUTH.md](../../03_planning/lore-enrichment/CLARIFY_GROUND_TRUTH.md).
- Code anchors: `services/glossary-service/internal/api/wiki_handler.go` §9 `generateWikiStubs`; `server.go` `/wiki/generate` route.
- LOCKED consumed (full list): Q4 (knowledge-service D4-03 renders known facts; enrichment feeds it, no fork), H0 (enriched quarantine + permanent origin marker), Q2 (write through glossary SSOT, never Neo4j directly), Q3 (per-user/per-project scoping), Q6 (thin KG-read port for graceful degradation).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Top LOCKED 1 (H0):** enriched lore is NOT canon — every enriched fact rendered in the wiki body MUST carry `source_type='enriched'` + quarantine marking, visibly distinct from `source_type='glossary'`. Never silently merge enriched as canon.
- 🔴 **Top LOCKED 2 (Q2):** write back through the glossary SSOT wiki path ONLY (`wiki_articles`/`wiki_revisions`). NEVER write Neo4j canonical content directly — read the KG neighborhood, write the wiki.
- 🔴 **Top LOCKED 3 (Q4):** this is the extractive renderer for KNOWN facts (replaces empty `generateWikiStubs`); it does NOT generate enrichment. Do not pull in gap-detection or strategies.
- 🔴 **Acceptance MUST include:** the live-smoke token `live smoke: entity → generated wiki body persisted` (≥2 services — real cross-service read), AND `scripts/raid/verify-cycle-5.sh` exits 0.
- 🔴 **Do NOT touch:** Neo4j canonical writes, wiki ownership/auth/schema (additive only), `world-service`/`game-server`/`infra/existing-prod/`, climate/geo eval files; no hardcoded model names (provider-registry only).
- 🔴 **Fresh session reminder:** this is a new `/raid 5` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + OPEN_QUESTIONS_LOCKED.md ONLY.
