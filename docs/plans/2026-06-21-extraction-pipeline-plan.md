# Extraction / LLM-Pipeline — Parallel Build Plan

**Status:** PLAN — for next session's BUILD. All design resolved
([detailed design](../specs/2026-06-21-extraction-pipeline-detailed-design.md) · [architecture rev 2](../specs/2026-06-21-extraction-pipeline-architecture.md) · [reasoning-effort](../specs/2026-06-21-reasoning-effort-control.md)).
**Branch:** `feat/extraction-knowledge-architecture` (open lane sub-branches off it).
**Gate:** Option A (pipeline-first, in translation-service + glossary-service; cache behind an interface).

This plan turns the design into **parallelizable workstreams (lanes)** with an explicit dependency
DAG, so multiple agents/devs work concurrently next session without colliding. The hard rule:
**the foundation lane (FND) lands first** — almost every other lane writes through the seam it
builds, so starting them before FND would mean rebasing onto a moving writeback contract.

---

## 1. The dependency DAG

```
            ┌──────────────────────────────────────────────┐
 Phase 0    │  FND:  M0 finish_reason → M1 concurrency/2-ledger  │   (serial within lane; the blocker)
 (parallel) │  RE:   reasoning-effort resolver + wiring + /no_think + MCP param │   (independent)
            │  PLAN: planner SDK (against a STUBBED effort resolver iface) │   (independent of the seam)
            └──────────────────────────────────────────────┘
                          │ FND lands
            ┌─────────────┼───────────────────────────────┐
 Phase 1    │  OBS (needs M0+M1)   PROV (needs M1)         │
 (parallel) │  PLAN finalizes against RE's real resolver   │
            └─────────────┼───────────────────────────────┘
                          │ PROV + PLAN land
 Phase 2    │  MERGE (needs M1+PROV)     CACHE (needs M1+PLAN) │
            └──────────────────────────────────────────────┘
```

**Critical path:** `FND(M0→M1) → PROV → MERGE`. Everything else fans off FND.
**Longest independent lane:** RE and PLAN can start at minute 0 (PLAN stubs the resolver iface).

---

## 2. Lanes

| Lane | Milestone(s) | Depends on | Primary surfaces | Exit criteria (VERIFY) |
|---|---|---|---|---|
| **FND** | M0 `finish_reason`; M1 concurrency + two-ledger | — | provider-registry (result shape), translation-service worker, **glossary-service `extraction_handler.go`** (the seam), migrations | `finish_reason` present in SDK result (live); `UNIQUE(book,kind,normalized_name)` + `ON CONFLICT` create-or-merge; per-book advisory-lock + whole-chapter txn; `extraction_writeback_log` + idempotency key; content-hash 409; idempotent evidence. **Live**: 2 concurrent same-chapter jobs → 0 duplicates; failed writeback re-drives + lands on retry. |
| **RE** | reasoning-effort | — | shared kit (`reasoning_fields`/`resolve_effort`), chat-service `_stream_via_gateway` (wiring fix) + inline parser, MCP tool param, FE effort selector | Effort actually forwarded (no-op bug fixed); `/no_think` strips + applies; capability-gated selector; MCP `reasoning_effort` param; `thinking:bool` alias normalizes. **Live**: a turn with `/no_think` sends no thinking; `effort=high` reaches the provider. |
| **PLAN** | M4 planner SDK | RE (resolver iface) | NEW `sdks/python/loreweave_planner`; rewire translation-service extraction + glossary-translate to call it | Two-phase plan (split→pack); `Unplannable` surfaced; effort-aware budget; fan-out warning; `unit_id` attribution echoed + validated; **extraction chapter-chunking**. **Unit**: 1000 attrs/30 kinds → bounded call count; oversized unit → split or `Unplannable`, never silent truncate. |
| **OBS** | M2 observability | FND (M0+M1) | translation-service worker (BatchOutcome rows + transactional outbox), statistics-service (extraction aggregates + reconciliation sweep), notification-service (terminal rollup) | Outcome taxonomy persisted; events = same-txn projection w/ stable `event_id`; stats dedup + reconcile; per-batch→stats / terminal→notification (debounced). **Live**: truncated batch → queryable `truncation_rate`; redelivery doesn't double-count. |
| **PROV** | M3 provenance | FND (M1) | translation-service preprocess (block-offset map, INV-6 neutralize), glossary-service evidence INSERT (populate `chapter_index/title/block_or_line/char_*` + `provenance_status`) | Evidence traces to book/chapter/block; model offset validated (hint-only), taxonomy `exact/resolved/ambiguous/unmatched`; `original_text` neutralized before reuse. **Live**: an evidence row resolves to the right paragraph; a hallucinated quote stores `unverified`, not a wrong offset. |
| **MERGE** | M5 merge policy | FND (M1) + PROV | glossary-service ontology (`merge_strategy` col + migration), `extraction_handler.go` merge path; FE attr editor (strategy picker) | `merge_strategy` ∈ {replace,fill_if_empty,append,overwrite,manual}; **verified-clobber guard** downgrades to `manual`; atomic idempotent append-dedup + tombstone check; skip-reason surfaced; safe System default. **Live**: "new power in ch.3" appends (not skips); overwrite on a verified value is blocked + queued. |
| **CACHE** | M6 raw-cache + replay | FND (M1, two-ledger) + PLAN (executor seam) | translation-service (cache-gate in executor, `extraction_raw_outputs`, replay endpoint, retention job) | Cache-gate skips LLM on hit (incl. `effort_band`); replay re-applies cached parse at $0 LLM but **grant+confirm-gated**; retention keep-latest+K=3+purge. **Live**: re-extract unchanged chapter = 0 LLM calls; replay under a new profile writes via the gated path. |

---

## 3. Phasing for next session

**Phase 0 (start in parallel):**
- **FND** — the foundation team. Serial M0→M1. *Blocks Phase 1/2.* Highest priority, most senior.
- **RE** — independent; ships the resolver iface + the no-op wiring fix early (a real user-visible bug fix on its own).
- **PLAN** — starts the SDK against a stubbed `resolve_effort`/`reasoning_fields`; swaps to RE's real impl when RE lands.

**Phase 1 (after FND/M1 merges to the lane branch):**
- **OBS**, **PROV** fan out (both need the seam). PLAN finalizes against RE.
- Re-sync each lane onto the merged FND seam before starting (avoid the moving-contract trap).

**Phase 2:**
- **MERGE** (after PROV — shares `extraction_handler.go`, so sequence to avoid conflicts).
- **CACHE** (after PLAN's executor seam + FND's two-ledger).

**Integration milestone (end):** a cross-service **live smoke** — extract an entity-dense chapter end-to-end exercising all lanes (plan→cache-gate→execute→validate→provenance→merge→observe→notify), then a replay, then a concurrent double-run (0 duplicates). This is the epic's VERIFY gate.

---

## 4. Coordination / conflict notes

- **`glossary-service/internal/api/extraction_handler.go` is the hot file** — FND, PROV, MERGE all touch it. Sequence: **FND rewrites the writeback (txn + lock + constraint + idempotency); PROV adds evidence provenance to the same INSERT; MERGE adds the strategy/guard to the merge branch.** Do them in that order on the lane branch; never two of them concurrently on the same function.
- **Migrations** land per lane (FND: entity unique + writeback_log; OBS: batch_outcomes; PROV: evidence cols + provenance_status; MERGE: merge_strategy; CACHE: raw_outputs). Each takes the advisory lock + ledger entry per the migration protocol.
- **The planner SDK** is greenfield (no conflict); its only integration points are the two extraction/translate call sites.
- **Invariants doc** (§4 of the detailed design) is the shared contract every lane references; if a lane needs to deviate, it amends the invariant first, not silently.

## 5. Sizing + workflow

- Whole effort = **XL** (new SDK + 5 migrations + cross-service contracts + tenant/concurrency invariants). Each lane is independently **M–L**.
- Per-lane: follow the 12-phase workflow (CLARIFY is done — this plan; each lane does DESIGN-lite→BUILD→VERIFY→REVIEW). **VERIFY needs a live cross-service smoke** (≥2 services per lane).
- **The 4 HIGH evaluation findings are FND + PROV + MERGE + RE-adjacent** (concurrency, model-offset trust, verified-clobber, effort-auth) — these lanes get `/review-impl` before commit (load-bearing: tenancy + concurrency + integrity).
- Push only with explicit approval; stage only changed files.

## 6. What "done" looks like

All 15 invariants (detailed design §4) enforced + live-smoked; the integration smoke green
(extract→replay→concurrent-double-run); the 3 deferred rows (`D-GLOSSARY-MULTIROW-ATTR-VALUES`,
`D-EXTRACTION-REHOME-KNOWLEDGE`, `D-RAWCACHE-MINIO-OFFLOAD`) tracked; SESSION_HANDOFF updated.
Then the epic PRs to `main`.
