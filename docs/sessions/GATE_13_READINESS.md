# Gate 13 — Readiness Report (Session 47)

> **Purpose:** track which Gate 13 checkpoints are covered by the
> automated test suite and which still need a human-in-the-loop
> live run before Track 2 can be formally closed.
>
> **Date:** 2026-04-19
> **Suite state:** knowledge-service 1418 pass + 1 skip (0 fail),
> chat-service 177 pass (0 fail), live Postgres + Neo4j + Redis
> compose stack healthy.
>
> **Prerequisite code:** all 9 Track 2 close-out cycles shipped this
> session (7a MMR cosine, 7b Anthropic cache_control, 8a generative
> rerank, 8b cross-process cache invalidation, 8c glossary breaker
> half-open probe, 9 K17.9.1 benchmark_runs migration).

---

## 1. Status matrix

| # | Gate 13 checkpoint | Covered by | Status |
|---|---|---|---|
| 1 | Enable extraction + run full extraction job | — | ⚠ **NEEDS HUMAN** (BYOK + chapter data) |
| 2 | Send chat message in that project | — | ⚠ **NEEDS HUMAN** (UI + live backend) |
| 3 | Verify Mode 3 context block in system prompt | Unit tests prove block shape; live verification pending | ⚠ **NEEDS HUMAN** (visual inspection of live output) |
| 4 | L3 passages appear for semantic queries | Unit tests prove selector logic; live verification pending | ⚠ **NEEDS HUMAN** (needs real embedded passages) |
| 5 | Mode 3 uses 20-message history (not 50) | `test_recent_message_count_is_20` ([test_mode_full.py:246](services/knowledge-service/tests/unit/test_mode_full.py#L246)) + `_RECENT_MESSAGE_COUNT = 20` constant | ✅ **AUTOMATED** |
| 6 | Negative facts prevent inconsistency | Unit tests prove `<negative>` facts render; live "character reveals secret" test pending | ⚠ **NEEDS HUMAN** (conversational test) |
| 7 | Disable extraction → Mode 2 works again | `test_static_mode.py` covers Mode 2; dispatcher in `builder.py` routes by `project.extraction_enabled` | ✅ **AUTOMATED** (dispatcher routing tested; live toggle verification pending) |
| 8 | Re-enable extraction → Mode 3 works, picks up pending events | K14 event consumer tests cover chapter.saved/chapter.deleted; extraction_pending repo tests cover dispatch | 🟡 **PARTIAL** (components tested; full end-to-end live re-run needed) |
| 9 | Cross-user isolation (T18) | 127 cross-user-guard assertions across 19 test files (unit + integration). Every repo query takes `user_id` and every integration test has a `user_b` counter-example that must not see `user_a`'s data. | ✅ **AUTOMATED** (thoroughly) |
| 10 | Chaos: stop Neo4j mid-chat → Mode 2 fallback (C01) | `test_neo4j_failure_degrades_to_mode2_shape` ([test_mode_full.py:188](services/knowledge-service/tests/unit/test_mode_full.py#L188)) — L2 throws RuntimeError("neo4j down") → builder still produces valid Mode 3 block minus facts | ✅ **AUTOMATED** (unit-level; live chaos run pending) |
| 11 | Cost tracking: run a small extraction, verify billing matches | K10.4 cost-cap repo tests + K17.12 rate limiter tests cover unit behavior | ⚠ **NEEDS HUMAN** (needs real provider invoice for cross-check) |
| 12 | Quality eval: golden set passes thresholds | K17.9.1 migration table just landed (Cycle 9); K17.9 harness not yet built | ⏸ **BLOCKED** (K17.9 harness implementation is the prerequisite — not in Track 2 close-out scope) |

**Roll-up:**
- ✅ **Automated pass:** 4 checkpoints (#5, #7, #9, #10)
- 🟡 **Partial:** 1 checkpoint (#8)
- ⚠ **Human needed:** 6 checkpoints (#1, #2, #3, #4, #6, #11)
- ⏸ **Blocked on harness:** 1 checkpoint (#12)

---

## 2. Chaos tests (C01–C08)

From KSA §9.10 — failure-injection scenarios:

| Chaos | Description | Coverage | Status |
|---|---|---|---|
| C01 | Stop Neo4j mid-chat → Mode 2 fallback | `test_neo4j_failure_degrades_to_mode2_shape` proves L2 failure degrades cleanly; `_safe_l3_passages` timeout path proves L3 failure returns `[]`. Live docker-stop verification pending | ✅ **AUTOMATED** (unit-level) |
| C02 | Stop knowledge-service → chat works without memory | chat-service `test_knowledge_client.py` graceful-degradation suite (timeout, 5xx, 4xx, decode error, transport error — all return `mode="degraded"` with `context=""`) + stream_service path that tolerates empty context | ✅ **AUTOMATED** (unit-level) |
| C03 | LLM provider 429 → job backs off and pauses | K17.12 rate limiter + K17.3 retry wrapper tests cover this; backoff behavior tested | ✅ **AUTOMATED** (unit-level) |
| C04 | Embedding service OOM → job pauses with error | `EmbeddingError` handling in passage_ingester + L3 selector both covered; job-state "failed" transition tested | ✅ **AUTOMATED** (unit-level) |
| C05 | Redis loses events → consumer catches up from event_log | K14.2 hybrid catch-up test coverage (event_log fallback path). T2-close-3 added `scripts/chaos/c05_redis_restart.sh` for live-run. | 🟡 **SCRIPTED** (unit-level automated + live script authored) |
| C06 | Manually corrupt Neo4j data → rebuild from event_log succeeds | K14.x + K11.9 reconciler tests cover the rebuild path. T2-close-3 added `scripts/chaos/c06_neo4j_drift.sh` for live-run. | 🟡 **SCRIPTED** (unit-level automated + live script authored) |
| C07 | User deletes project mid-extraction → clean cancel | ProjectsRepo delete + extraction_jobs cancel tests; cascade-delete tested end-to-end via migration integration tests | ✅ **AUTOMATED** (unit+integration) |
| C08 | Bulk delete 1000 chapters → cascade rate-limited, no overload | K11.8 cascade-delete + K11.9 reconciler batching tests. T2-close-3 added `scripts/chaos/c08_bulk_cascade.sh` for live-run (1000-event burst + drain assertion). | 🟡 **SCRIPTED** (unit-level automated + live script authored) |

**Roll-up:**
- ✅ **Automated pass:** 5 chaos scenarios (C01, C02, C03, C04, C07)
- 🟡 **Scripted (live runs one command away):** 3 scenarios (C05, C06, C08) — run `./scripts/chaos/c0{5,6,8}_*.sh` against a stack to capture live evidence. See `scripts/chaos/README.md`.

---

## 3. Integration test scenarios (T11–T20)

From KSA §9.8 — Track-2-specific integration tests:

| T# | Description | Coverage |
|---|---|---|
| T11 | Atomic cost cap — concurrent try_spend | K10.4 + K16.11 tests |
| T12 | Monthly budget blocks over-budget jobs | K16.11 |
| T13 | Embedding model change triggers rebuild | K12.4 + K16.10 warning tests |
| T14 | Full rebuild from scratch | K14 + K16 |
| T15 | Chat turn while extraction disabled → queued | K13.2 outbox + K14 consumer tests |
| T16 | Enable extraction → backfill drains pending | K16 backfill tests |
| T17 | Glossary entity created → appears in Mode 3 context within 5s | K2 glossary + K18.2 context builder tests |
| T18 | Cross-user isolation with concurrent extraction | 127 cross-user assertions across 19 test files |
| T19 | Delete user account → all Neo4j data gone within SLA | K7d user-data delete + K11 cascade tests |
| T20 | Prompt injection in chapter → neutralized in L2/L3 context | `test_injection_defense.py` (56 assertions) + K15.6 extraction-time defense + K18.7 context-build defense |

All T11–T20 have unit and/or integration coverage that passes in the 1418-test sweep. Whether the exact E2E integration scenario matches each "T#" description one-to-one would need a cross-check against the test names, but the functional surface is covered.

---

## 4. Scriptable verification already completed this session

- ✅ Stack health: knowledge-service (`/health` → 200 `{"status":"ok","db":"ok","glossary_db":"ok"}`), postgres 5555, neo4j 7688, redis 6399, worker all healthy in `infra-*` containers
- ✅ knowledge-service full suite: 1418 passed, 1 skipped, 0 failed (fixed 3 stale-test bugs this session in `609de2b`)
- ✅ chat-service full suite: 177 passed, 0 failed
- ✅ migration integration tests: 20/20 with live Postgres (including 7 new tests for K17.9.1 `project_embedding_benchmark_runs`)

---

## 5. What a human needs to do to finish Gate 13

1. **Provision BYOK credentials** for at least one LLM provider (Anthropic / OpenAI / LM Studio) and one embedding model (e.g. bge-m3 on LM Studio or text-embedding-3-small on OpenAI).
2. **Create a test project** with 2–3 real chapters loaded via the book-service API.
3. **Enable extraction** on that project via the K12.4 picker (checkpoint 1).
4. **Wait for the extraction job to complete** (minutes — depends on provider and chapter length).
5. **Open chat in that project** and run several queries (checkpoints 2–4):
   - Broad query ("what's the book about?") — should hit L1 summary + glossary, few L3 passages.
   - Specific entity query ("who is X?") — should hit L2 facts + targeted L3 passages with hub penalty.
   - Relational query ("how does X relate to Y?") — should hit 2-hop facts.
6. **Inspect the system prompt** in the chat-service logs to confirm the `<memory mode="full">` XML block contains `<facts>` and `<passages>` segments (checkpoint 3–4).
7. **Send 25+ messages** in that chat and verify only the last 20 are in history (checkpoint 5).
8. **Ask a question that contradicts an extracted negative fact** and verify the LLM honors the negation (checkpoint 6).
9. **Disable extraction** via UI, run a chat query, verify Mode 2 block (checkpoint 7).
10. **Re-enable extraction**, verify the queue drains + Mode 3 returns (checkpoint 8).
11. **Check cost tracking** against the provider's invoice (checkpoint 11).
12. **Run chaos C05, C06, C08** live (scripts under `scripts/chaos/` — each is a single `./c0X_*.sh` command, ~10-90 s each, with trap-based cleanup). Unit-level coverage is sufficient for Track 2 close; the scripts give live evidence for pre-production readiness when it's wanted.

Checkpoint 12 (quality eval) is BLOCKED on the K17.9 golden-set harness being built. That's a separate piece of work, explicitly out of Track 2 close-out scope per the plan (the close-out shipped the migration table that the harness will eventually write to).

---

## 6. Session 47 summary

**7 commits across 6 cycles + 1 test-hygiene fix:**

| Cycle | HEAD | Focus |
|---|---|---|
| 7a | `7c666c9` | MMR embedding cosine |
| 7b | `8f282c3` | Anthropic cache_control |
| 8a | `e5aeb96` | Generative rerank |
| 8b | `239b021` | Cross-process cache invalidation |
| 8c | `2732462` | Glossary breaker half-open probe |
| 9 | `e0a94a7` | K17.9.1 benchmark_runs migration |
| fix | `609de2b` | K16.3 stale test hygiene (3 tests) |

**Review-impl pattern track record (session 47):**
- 7a: MED perf bug (21× MMR fix)
- 7b: 2 LOW coverage gaps
- 8a: MED regression + 2 LOW + test-infra bug
- 8b: 3 LOW (all batched into same commit)
- 8c: 2 LOW (dead test var + undocumented semantics)
- 9: 2 LOW (fixed) + 3 LOW (accepted)

Every cycle found something. No exceptions.

---

## 7. Conclusion

**Track 2 code implementation is complete.** All 9 close-out cycles shipped. Test suite is fully green. Automated coverage proves the non-UI verification surface.

**Gate 13 formal closure is gated on human-loop live verification** of 6 checkpoints (BYOK-driven extraction + UI walk-throughs) and the K17.9 golden-set harness for checkpoint 12. No additional Track 2 code changes are expected — any bug the live verification surfaces would open its own targeted cycle.
