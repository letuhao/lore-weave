# Track 2 Acceptance Pack

> **Consolidated evidence that Track 2 close-out is complete.** Mirrors the shape of [GATE_13_READINESS.md](GATE_13_READINESS.md) — read that for the checkpoint-by-checkpoint Gate 13 view, read this for the Track 2 delivery view.

- **Compiled**: session 47 (2026-04-19) at HEAD `ff9ef11`
- **Source of truth for cycle status**: [SESSION_PATCH.md](SESSION_PATCH.md) "Recently cleared" table
- **Primary planning doc**: [../03_planning/KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md](../03_planning/KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md)

---

## 1. What Track 2 was

Track 2 turned loreweave's knowledge-service from a Mode-1 / Mode-2 fallback surface into a production Mode-3 RAG stack with:

- Event-driven extraction from chapters → Postgres SSOT → Neo4j projection
- Anchor-preloaded entity resolution (K13.0)
- Passage ingestion + embedding (K18.3)
- Listwise rerank on top of MMR (K18.3 Path-C)
- Benchmark gate on extraction-enable (K17.9)
- Atomic try_spend cost guard (K10.4 / K16.11)
- End-to-end chat provenance via KSA §4 context-build contract
- Anthropic prompt caching (K18.9)

Session 46 landed the K14 / K15 / K16 / K17 / K18 core. Session 47 closed ~24 deferred items across 9 roadmap cycles so the stack is actually shippable rather than just feature-complete.

---

## 2. Cycles shipped (session 46 → 47)

| Cycle | Scope | Session | Commit |
|---|---|---|---|
| 1a | K18.3 passage ingestion (D-K18.3-01) | 46 | d6455b8 |
| 1b | K12.4 embedding picker | 46 | 2025951 |
| 2 | Debris sweep (3 of 7 items) | 46 | 06e5c30 |
| 3 | Lifecycle + scheduler cleanup | 46 | d4527e0 |
| 4 | Provider-registry hardening + /metrics | 46 | — |
| 5 | Extraction quality + perf (4 items) | 46 | — |
| 6a | D-T2-01 tiktoken swap | 46 | — |
| 6b | D-T2-02 ts_rank_cd | 46 | b57b278 |
| 6c | D-T2-03 unify recent_message_count | 46 | 9cb6217 |
| 7a | P-K18.3-02 MMR embedding cosine | 47 | 7c666c9 |
| 7b | K18.9 Anthropic prompt cache_control (stable memory) | 47 | 8f282c3 |
| 8a | D-K18.3-02 generative rerank | 47 | e5aeb96 |
| 8b | D-T2-04 cross-process cache invalidation | 47 | 239b021 |
| 8c | D-T2-05 glossary breaker half-open probe | 47 | 2732462 |
| 9 | K17.9.1 `project_embedding_benchmark_runs` | 47 | e0a94a7 |
| T2-close-1a | K17.9 golden-set harness core wiring | 47 | 525eaa5 |
| T2-close-1b-BE | K17.9 benchmark gate + status endpoint | 47 | 849be7f |
| T2-close-1b-FE | K17.9 picker benchmark badge + public endpoint | 47 | a484e25 |
| T2-close-5 | D-K16.2-01 per-model USD pricing | 47 | ed9f13d |
| T2-close-6 | D-K16.2-02 scope_range.chapter_range filter | 47 | 01b8eda |
| T2-close-7 | P-K2a-02 + P-K3-02 glossary trigger perf | 47 | 02067e2 |
| T2-close-3 | Scripted C05/C06/C08 chaos harness | 47 | fae8ce1 |
| T2-polish-1 | Python isolation audit + 2 Go test fixes | 47 | 8e3410d |
| T2-polish-2a | /metrics for glossary-service | 47 | 0464919 |
| T2-polish-2b | /metrics for book-service | 47 | 98623aa |
| T2-polish-3 | D-K18.9-01 cache_control on system_prompt | 47 | ff9ef11 |

**Scoped out by user decision (not deferred):**

- T2-close-1b-CI — GitHub Actions job for the K17.9 benchmark on every PR. No CI/CD in scope for this project.
- T2-polish-4 — CI-related polish. Same reason.

---

## 3. Test evidence per service

| Service | Unit | Integration | Notes |
|---|---|---|---|
| knowledge-service | **1154 pass, 0 fail** | 17 pass with live Postgres (pool fixture TRUNCATEs), 20/20 migration pass, 7 new K17.9.1 benchmark-run DDL smoke tests | Context-cache tests run under `conftest.py` autouse `_clear_context_cache` fixture — no order-dependent leaks (confirmed by T2-polish-1 audit) |
| chat-service | **177 pass, 0 fail** | n/a | Includes 13 stream_service tests covering K18.9 stable-memory caching + T2-polish-3 system_prompt caching |
| glossary-service | api package **100% green** (3.0 s) | live DB tests pass | T2-polish-1 fixed 2 pre-existing broken tests (bad-hex UUID + `short_desc_len` CHECK violation + missing `chapter_index` value) |
| book-service | api package **green** (0.25 s) incl. T2-close-6 `parseSortRange` + `buildSortRangeFilter` units | live-DB tests pass | `TestLoadValidation` in `internal/config` has a pre-existing env-var gap unrelated to anything session 47 touched |
| provider-registry | api green | — | — |

Pre-existing failures verified via `git stash` as **not caused by this session's work**:

- `book-service/internal/config TestLoadValidation` — missing `INTERNAL_SERVICE_TOKEN` in test setenv; added later but test not updated.
- (No other pre-existing failures in the other services after T2-polish-1.)

---

## 4. Chaos scenarios (KSA §9.10)

From [GATE_13_READINESS.md §2](GATE_13_READINESS.md), updated after T2-close-3.

| ID | Scenario | Status |
|---|---|---|
| C01 | Stop Neo4j mid-chat → Mode 2 fallback | ✅ automated (unit-level) |
| C02 | Stop knowledge-service → chat works without memory | ✅ automated (unit-level) |
| C03 | LLM provider 429 → job backs off + pauses | ✅ automated (unit-level) |
| C04 | Embedding service OOM → job pauses with error | ✅ automated (unit-level) |
| C05 | Redis loses events → consumer catches up | 🟡 scripted ([scripts/chaos/c05_redis_restart.sh](../../scripts/chaos/c05_redis_restart.sh)) |
| C06 | Manually corrupt Neo4j → rebuild from event_log | 🟡 scripted ([scripts/chaos/c06_neo4j_drift.sh](../../scripts/chaos/c06_neo4j_drift.sh)) |
| C07 | User deletes project mid-extraction → clean cancel | ✅ automated (unit + integration) |
| C08 | Bulk delete 1000 chapters → cascade rate-limited, no overload | 🟡 scripted ([scripts/chaos/c08_bulk_cascade.sh](../../scripts/chaos/c08_bulk_cascade.sh)) |

"🟡 scripted" means: unit-level code-path coverage exists AND a one-command bash script is authored. Live runs are a pre-production readiness task, not a Track 2 close-out blocker. See [scripts/chaos/README.md](../../scripts/chaos/README.md) for prereqs + cleanup.

---

## 5. Observability surfaces

All three Go services on the knowledge-service hot paths now expose `/metrics`:

| Service | Counters | Outcomes |
|---|---|---|
| provider-registry | 4 (proxy / invoke / embed / verify requests) | 12 (from session 46 Cycle 4) |
| glossary-service | 4 (select_for_context / bulk_extract / known_entities / entity_count) | 4 (ok / validation_error / invalid_body / query_failed) |
| book-service | 3 (projection / chapters_list / chapter_fetch) | 4 (ok / validation_error / not_found / query_failed) |

**Cross-service label divergence is intentional** and documented in both glossary-service and book-service metrics.go: book-service GETs have real `pgx.ErrNoRows` 404s (→ `not_found`); glossary-service POSTs have real JSON-decode paths (→ `invalid_body`). Dashboards that union the two services will see partial label overlap on `{outcome}` — forcing alignment would re-introduce the dead-label pollution T2-polish-2a's review-impl caught and fixed.

Process-local Prometheus registry per service (no default Go-runtime metrics ship). `/metrics` mounted outside `/internal` on every service so scrapers don't need `X-Internal-Token`.

---

## 6. Cleared deferrals (session 47)

Full list lives in [SESSION_PATCH.md](SESSION_PATCH.md) "Recently cleared". Short form:

- **D-K16.2-01** — per-model USD pricing for cost-estimate preview
- **D-K16.2-02** — scope_range.chapter_range forwarded to book-service
- **D-K17.2b-01** — tool_calls parser support (session 46)
- **D-K17.2c-01** — router-layer tests (session 46)
- **D-K18.3-01** — passage ingestion pipeline end-to-end (session 46)
- **D-K18.3-02** — generative rerank with fail-safe timeout
- **D-K18.9-01** — cache_control on system_prompt (this cycle closed the last K18.9 deferral)
- **D-T2-01/02/03/04/05** — the full T2-planning deferral row shipped
- **P-K2a-01** — backfill snapshot set-based SQL (session 46)
- **P-K2a-02** — pin toggle no longer fires recalc
- **P-K3-02 (partial)** — description PATCH no-op regen skips self-trigger
- **P-K13.0-01** — anchor preload cache
- **P-K15.8-01** — entity detection reuse across passes
- **P-K18.3-01** — query-embedding cache
- **P-K18.3-02** — MMR embedding cosine + top_n early-exit
- **K17.9 (harness core + BE gate + FE badge)** — all three sub-cycles
- **K17.9.1** — `project_embedding_benchmark_runs` migration
- **K18.9** — Anthropic prompt cache split + structured system content

---

## 7. Remaining gaps → Track 3 preload

Every remaining item has a specific target; nothing is "we'll come back to it".

| ID | Description | Target |
|---|---|---|
| **T2-close-2** | Gate 13 human-interactive checkpoints (BYOK + real project + chat turns). See [GATE_13_READINESS.md §5](GATE_13_READINESS.md) step-by-step. | Whenever the user runs the loop — not a code task |
| D-K16.2-02b | Runner-side `chapter_range` enforcement. Preview filters; runner (event-driven) currently ignores. Latent today (frontend doesn't send scope_range yet). | Track 3, when FE range-picker ships OR when batch-iterative runner lands |
| D-K11.9-01 (partial) | Reconciler cursor state for resumable-from-mid-scan. LIMIT shipped in session 46; cursor-state needs a job-state table. | K19/K20 scheduler cleanup |
| P-K15.10-01 (partial) | Quarantine sweep cursor state. Same pattern as D-K11.9-01. | Paired with D-K11.9-01 |
| D-K8-02 (remaining) | Project card stat tiles (entity / fact / event / glossary counts) — needs Track 2 K11/K17 data surfaces + FE wiring | Track 2 Gate 12 or Track 3 |
| D-K17.10-02 | Xianxia + Vietnamese K17.10 fixtures (CJK canonicalisation, mixed-script predicates). | K17.10-v2 after thresholds stabilise |
| P-K3-01 / P-K3-02 (full path) | Per-row short_description backfill needs `shortdesc.Generate` ported to SQL so the backfill becomes one set-based UPDATE. | Track 3 (same port blocks both) |
| Chaos C05/C06/C08 live runs | Scripts authored; running them captures evidence | Pre-production readiness |

See [SESSION_PATCH.md](SESSION_PATCH.md) "Deferred Items" for the authoritative table with full descriptions.

---

## 8. How to replay verification

```bash
# knowledge-service unit sweep
cd services/knowledge-service && python -m pytest tests/unit/ -q

# chat-service unit sweep
cd services/chat-service && python -m pytest tests/ -q

# glossary-service api (needs live Postgres via compose infra stack)
cd services/glossary-service && \
  GLOSSARY_TEST_DB_URL='postgres://loreweave:loreweave_dev@localhost:5555/loreweave_glossary?sslmode=disable' \
  go test ./internal/api/

# book-service api
cd services/book-service && go test ./internal/api/

# Each Go service's /metrics (with stack up)
curl -s http://localhost:8083/metrics | grep '^glossary_service_' | head
curl -s http://localhost:8082/metrics | grep '^book_service_' | head
curl -s http://localhost:8085/metrics | grep '^provider_registry_' | head

# Chaos scripts (run on an idle stack)
./scripts/chaos/c05_redis_restart.sh
./scripts/chaos/c06_neo4j_drift.sh
./scripts/chaos/c08_bulk_cascade.sh
```

The last number each pytest invocation reports should match §3: knowledge-service 1154, chat-service 177. Numbers drift when new tests land — trust the live `git log` output for the ultimate baseline.

---

## 9. Sign-off

This pack is evidence that Track 2's shipped surface matches the plan in [KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md](../03_planning/KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md). Gate 13 sign-off still requires the human-interactive checkpoints in [GATE_13_READINESS.md §5](GATE_13_READINESS.md); those are scoped out of Track 2 close-out because they can't be automated.

When the Gate 13 human loop completes, add a §10 **Gate 13 attestation** section pointing at the captured evidence (chat-service logs showing the `<memory mode="full">` block, the Anthropic API invoice, a screenshot of the benchmark badge turning green, etc.).
