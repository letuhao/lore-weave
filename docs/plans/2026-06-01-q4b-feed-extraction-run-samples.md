# Q4b-feed — run-attributable items+source feed for the online LLM judge

**Date:** 2026-06-01 · **Size:** XL (3 services, new table+migration, raw-retention side effect, multi-system contract)
**Track:** Production Eval + Feedback Flywheel (`docs/plans/2026-06-01-production-eval-feedback-flywheel-track.md`, phase Q4b)
**Status:** DESIGN+PLAN

---

## 0. Why this exists

Q4b shipped the online LLM-judge **engine** (`bd6fc161`): `run_online_judge` + `persist_online_judge`
score extraction PRECISION (item-supported-vs-source, no gold) and persist per-item verdicts. It is
live-verified against real LM Studio (alice_ch01 26 items → overall 0.846). But it is **off by default**
because nothing feeds it `items` + `source_text` for real production runs — the
`knowledge.extraction_run_completed` event carries only **counts**.

This cycle builds the **feed**.

## 1. CLARIFY finding — both pre-planned options are invalid

The handoff offered two feed options. CLARIFY (reading the live code) killed both:

| Planned option | Why it's dead |
|---|---|
| **A: event carries items+source** | Writes raw novel content into `outbox_events` (knowledge DB) + the durable Redis stream — a **redact-by-default violation** (track plan §6 L233: "raw novel text only under `save_raw_extraction`"; the broker is the wrong place for it). |
| **B: consumer fetches `extraction_leaves`** | The live `_extract_and_persist` → `/persist-pass2` path (`runner.py:930,1238`) writes only to **Neo4j**, never `extraction_leaves` (that's the separate orchestrator path). Neo4j is **post-merge, not run-attributable** (Q2 established graph nodes carry no `run_id`). Nothing run-keyed to fetch. |

**Key fact:** the only place `run_id` + `items` + `source_text` coexist is **worker-ai at extraction
time, in memory** — `extract_pass2(text)` returns `candidates`, and `text` is the chapter source. Every
downstream store loses run-attribution (Neo4j merge) or violates redact (broker).

## 2. Design (run-attributable + redact-respecting + per-service DB ownership)

```
worker-ai (live path)                      knowledge DB                 learning-service
─────────────────────                      ────────────                 ────────────────
extract_pass2(text) → candidates ─┐
                                  │  save_raw_extraction opted-in?
                                  ├─ YES → INSERT extraction_run_samples   ┌─ eval-runner samples
                                  │        {run_id, items_proj, source}    │  event (save_raw=true)
                                  └─ NO  → write nothing (redact default)   │
emit extraction_run_completed ────────────────────────────────────────────┤  GET /internal/extraction/
  payload += save_raw_extraction (bool, structural metadata)               │     runs/{run_id}/sample
                                                                            │  → {items, source_text}
                                                                            └─ run_online_judge + persist
```

### 2.1 Consent gate
`knowledge_projects.save_raw_extraction` (migrate.py:670, default OFF) is the **existing** raw-retention
opt-in. It already gates `extraction_leaves_raw`. We reuse it as the consent gate for the sample store —
**no new consent surface**. Stored sample content (entity names, relation triples, event summaries,
chapter source) is novel content, retained only under this opt-in, exactly like `extraction_leaves_raw`.

### 2.2 Redact minimization
The sample stores the **minimal judge-shape projection only** — not full candidates:
- entity → `{name, kind}`
- relation → `{subject, predicate, object, polarity}`
- event → `{summary, participants}`

(Confidence, canonical_ids, offsets, evidence are dropped — the judge doesn't render them.)

### 2.3 TTL
`extraction_run_samples` is a **transient judging buffer**, not history. A row only needs to live long
enough for the (sampled) eval-runner to consume it. Prune rows older than **7 days** on knowledge-service
startup (reuse the `reset_stale_claims` startup-hook pattern). Bounds storage of novel text.

## 3. Schema — `extraction_run_samples` (knowledge DB)

```sql
CREATE TABLE IF NOT EXISTS extraction_run_samples (
  run_id        UUID PRIMARY KEY,           -- worker-ai's fresh per-chapter run_id
  user_id       UUID NOT NULL,
  project_id    UUID,
  book_id       UUID,
  config_hash   TEXT,
  items_jsonb   JSONB NOT NULL,             -- {entity:[...], relation:[...], event:[...]}
  source_text   TEXT NOT NULL,              -- chapter source snapshot (judged-against)
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_extraction_run_samples_created
  ON extraction_run_samples (created_at);   -- TTL prune scan
```

Idempotent: `run_id` PK; worker-ai uses `ON CONFLICT (run_id) DO NOTHING` (a run_id is fresh per chapter,
so conflict only on a re-emit race — first write wins).

## 4. Phase plan (per-service)

### B1 — knowledge-service (store + endpoint)
- `migrate.py`: append `extraction_run_samples` DDL + index.
- `app/db/repositories/extraction_run_samples.py` (new): `insert_sample(...)`, `fetch_sample(run_id)`,
  `prune_older_than(days)`.
- `internal_extraction.py`: `GET /internal/extraction/runs/{run_id}/sample` → 200 `{items, source_text,
  ...}` or 404. Behind `require_internal_token` (existing router dep).
- `main.py`: add a startup prune call (best-effort, like `reset_stale_claims`).
- Tests: repo round-trip + prune; endpoint 200/404 + auth.

### B2 — worker-ai (sample write)
- `_get_running_jobs` SELECT + `JobRow`: add `save_raw_extraction` (LEFT JOIN already pulls `p.*`).
- `_extract_and_persist`: return `(ExtractionResult, Pass2Candidates | None)` so the loop can project items
  (or attach candidates to a richer result — pick least-invasive in BUILD).
- New `app/sample_emit.py`: `project_items(candidates) -> dict` + `persist_run_sample(pool, payload,
  source_text, items)` (best-effort, `ON CONFLICT DO NOTHING`). Mirrors `outbox_emit.py` precedent.
- chapter loop: after a **succeeded** extraction, if `job.save_raw_extraction` → `persist_run_sample`
  keyed by the **same** `run_id` used in `_run_payload`. (Generate `run_id` once, thread it to both the
  sample write and the payload, so they match.)
- `_run_payload`: add `save_raw_extraction` bool to the payload (structural metadata).
- Tests: projection mapping; sample written only when opted-in; run_id parity payload↔sample.

### B3 — learning-service (fetch + judge)
- `config.py`: `knowledge_internal_url` + `internal_service_token` (token already present for gateway).
- `app/clients/knowledge_client.py` (new): `KnowledgeClient.fetch_run_sample(run_id) -> dict | None`.
- `eval_runner._maybe_judge`: gate on `payload.save_raw_extraction` + `rule.judge_panel_id` +
  `online_judge_enabled`; **fetch** the sample via the client (production path), then run the existing
  `run_online_judge` + `persist_online_judge`. Keep the **inline-payload override** (test/demo) — if the
  event already carries `items`+`source_text`, use them and skip the fetch.
- Tests: fetch-path judge; gated-out without `save_raw_extraction`; client 404 → skip; inline override
  still works.

## 5. Verify / live-smoke (cross-3-service)

Per CLAUDE.md cross-service evidence gate (≥2 services → live smoke mandatory):
1. Unit suites green in all 3 services.
2. Live: opt a project into `save_raw_extraction`, run a real chapter extraction on the stack → confirm
   `extraction_run_samples` row written → enable `online_judge_enabled` + a rule judge panel → confirm
   eval-runner fetches the sample and persists `online_judge_precision`. Token: `live smoke: <result>`.

## 6. Risks / decisions

- **R1 — source_text duplication.** Storing the chapter snapshot duplicates novel text per sampled run.
  Mitigated by save_raw opt-in (consented) + 7-day TTL prune. Chosen over a book-service hop at judge time
  for reproducibility (judge against the text *as extracted*) and a single self-contained fetch.
- **R2 — write point (W1 chosen).** worker-ai writes the sample directly to the shared knowledge DB
  (matches `outbox_emit` precedent; keeps run-telemetry concerns together; no `/persist-pass2` contract
  change). W2 (knowledge-service writes via persist-pass2) rejected: bloats persist payload + mixes
  eval-sampling into the persist endpoint.
- **R3 — best-effort sample write.** A lost sample only drops a judging opportunity (online eval is
  droppable by design); it must never fail the extraction. Wrapped try/except like
  `emit_extraction_run_best_effort`.
- **R4 — sample written only on `succeeded`.** Skipped/failed runs have no meaningful items to judge.

## 7. Out of scope (Track-2 / later)
- Sorted-set paced judge queue (cost governor) — only needed at higher sample volume; today
  `online_judge_enabled` is off and sampling is 10%.
- Cross-tenant rollup of judge scores — gated behind Q9 privacy gate.
