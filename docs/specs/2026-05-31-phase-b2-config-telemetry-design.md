# DESIGN — Phase B2: Axis-2 config telemetry + per-novel tuning

**Date:** 2026-05-31 · **Status:** DESIGN (human-in-loop v2.2; AMAW off) · **Size:** XL+
**CLARIFY ref:** [`2026-05-31-phase-b2-config-telemetry-clarify.md`](2026-05-31-phase-b2-config-telemetry-clarify.md) · **Plan ref:** extraction-accuracy-and-eval-plan §2.1 / §2.4 · **Deferred:** D#055
**Predecessor:** Phase B (Axis-1 correction capture) — shipped session 75 (learning-service + corrections spine).

---

## 0 · Scope (PO-locked this session)
Design the **full B2** (A+B+C) as one coherent architecture, build incrementally:
- **B2-A (foundation):** config-resolution assembly + content-addressed `config_registry` + per-chapter `extraction_runs` emission at chapter completion. No UI.
- **B2-B (per-novel tuning BE):** `knowledge_projects.extraction_config` actually drives the pipeline (per-project override of global defaults) + edit endpoint + `config_adjustment_events` emission.
- **B2-C (FE):** project extraction-tuning panel + browser smoke.

---

## 1 · Code-ground (verified this session, not from CLARIFY agents)

| Fact | Location | Design impact |
|---|---|---|
| Per-chapter metrics ALREADY exist + discarded | `worker-ai/app/runner.py:1046-1123` — `ExtractionResult{entities_merged, relations_created, events_merged, facts_merged}` used in `_append_log` then dropped | per-chapter `extraction_runs` needs **no accumulator threading** — read `result` at the success point |
| Production extraction runs in **worker-ai**, in-process | `runner.py:797` `extract_pass2(...)` | resolve-config + emit live in worker-ai, not knowledge-service |
| Config is global env singletons | `runner.py:102` `_PRECISION_FILTER_CONFIG`, `:214` `_ENTITY_RECOVERY_CONFIG`; KS parallel copy `pass2_orchestrator.py:134` | B2-B introduces per-project override resolution; Q6 unifies the hash boundary |
| Extractor model is per-job only | `JobRow.llm_model` `runner.py:332`; job query already JOINs `knowledge_projects` `runner.py:357-368` | add `extraction_config` to that SELECT — one-line surface to get per-project overrides into the worker |
| Prompt content-hash foundation | `sdks/python/loreweave_extraction/_version.py` — `get_extractor_version(op)` = `v1-<op>-<8hex>` of prompt files | this IS `config_registry`'s prompt dimension; no new hashing of prompt text |
| Outbox→relay→consumer spine | KS `app/events/outbox_emit.py` (`emit_correction`, best-effort, `outbox_events` table) → worker-infra relay → `loreweave:events:knowledge` → learning-service `consumer.py` (`learning-collector` group, DLQ, `outbox_id` dedup) | **reuse for run + adjustment emission** — no new transport |
| worker-ai shares KS Postgres | `JobRow` query reads `extraction_jobs` + `knowledge_projects` (KS tables) | worker-ai CAN `INSERT INTO outbox_events` exactly like `emit_correction` |
| Cost is a flat estimate | `runner.py:309` `_DEFAULT_COST_PER_ITEM = $0.004` | `extraction_runs.metrics.cost_usd` is an estimate, labelled as such; no real token counts yet |
| corrections forward-FK reserved | learning `migrate.py:49` `source_extraction_run_id UUID` (no enforced REFERENCES — logical join) | run-emit ordering is decoupled from correction-emit; a lost run only degrades analytics |
| Edit-endpoint precedent | KS `projects.py:208` PATCH (If-Match/ETag, `model_fields_set` gating); side-effect fields get a **dedicated** endpoint (`PUT /embedding-model?confirm=true`) | extraction-config edits route through a **dedicated sub-resource endpoint**, not generic PATCH |
| FE dialog pattern | `frontend/.../ChangeModelDialog.tsx` — `FormDialog` + local `useState` + `knowledgeApi` + `toast` + i18n + `readBackendError` + reset-on-open | tuning panel mirrors this |

---

## 2 · The 6 open questions — RESOLVED (Lead recommendations; PO veto at checkpoint)

### Q1 · Run granularity → **per-chapter** ✅
A chapter run is the useful outcome-vs-config unit (a job spans chapters under ONE config). Metrics are already per-chapter in `result` — zero threading cost. `config_hash` is computed **once per job** (config is constant across a job) and reused across that job's chapter runs.

### Q2 · Outcome derivation → **two-tier: provisional-at-emit + refined-by-join (deferred to E2)** ✅
- **At emit** (cold-start, no user label): `outcome` = chapter terminal state — `'succeeded'` (persisted), `'skipped'` (retry-exhausted, `runner.py:1064`), or **`'failed'`** (non-retryable error / job fail on this chapter, `runner.py:1057`). `outcome_source = 'pipeline'`. Emitting `'failed'` is deliberate (PO-approved): a config that reliably **crashes** the pipeline must be visible-as-bad, not invisible. The failure path doesn't advance the cursor, so its emit is **best-effort** (not transactional) — a lost failure-run only under-counts the rarer failure case.
- **Refined later** (Phase E2 mining, NOT this build): a join recomputes a quality outcome and sets `outcome_source = 'correction_join' | 'rerun' | 'discard'`:
  - `corrected` (negative): ≥1 row in `corrections` joinable to this run within N days. Join key = `(user_id, project_id, source_chapter)` today; tightens to `corrections.source_extraction_run_id` once the graph carries its producing run_id (a later wiring, out of B2).
  - `clean` (positive): no correction + not re-run/discarded within the window.
- B2 ships the **columns + the provisional value + the documented join recipe**. It does NOT build the derivation engine (that's E2 + needs volume). This honours "outcome emission … IMPLICIT at cold-start" without inventing a labeling UI.

### Q3 · Transport (runs AND adjustments) → **reuse the existing outbox→relay→learning-collector spine** ✅ *(PO-confirmed at design review — supersedes the CLARIFY "non-outbox" lean)*
One transport for both flows. The spine gives DLQ + `outbox_id` dedup; a parallel Redis-stream consumer is a second thing to operate for no benefit.
- `knowledge.extraction_run_completed` — producer **worker-ai**, **TRANSACTIONAL** (see Q-runs below): the `INSERT INTO outbox_events` shares the worker's cursor-advance Postgres transaction → 100% run coverage.
- `knowledge.config_adjusted` — producer **knowledge-service** edit endpoint, **best-effort** (`emit_correction` pattern — analytics, lossy-OK).
- learning-collector gains handlers for both; `STREAMS` already includes `loreweave:events:knowledge` — **no consumer wiring change**, just dispatcher registrations.

### Q-runs · Run durability → **TRANSACTIONAL** ✅ *(PO-confirmed; resolves self-review #1)*
`extraction_runs` is the core join target for config-vs-outcome analysis, so best-effort gaps would inject the exact **selection bias** the plan §2.4 guards against. worker-ai already writes the cursor-advance (`_advance_cursor`) to Postgres at chapter success — the outbox insert goes in the **same transaction**. Run-emit and cursor-advance commit or roll back together: a chapter that advanced the cursor always has a run row. Adjustments stay best-effort (analytics on user actions, not the join target).

### Q4 · Per-project override scope → **safe structural subset + raw-prompt editing (PO-chosen IN)** ✅ *(sampling params still deferred)*
Overridable in `extraction_config` for B2:
| Key | Type | Source today |
|---|---|---|
| `llm_model` `{model_ref, model_source}` | UUID + enum | per-job → promote to per-project default |
| `precision_filter` `{enabled, categories[], partial_policy}` | bool + subset of `{entity,relation,event}` + `keep\|drop` | validated quality lever (c73b) |
| `entity_recovery` `{enabled}` | bool | c73d |
| `writer_autocreate` `{enabled}` | bool | c73 |
| **`prompts` `{<op>: {system?, user?}}`** | **raw text per op** (entity/relation/event/fact/summarize_level), **≤ 16 kB/field** | **NEW — PO-chosen IN.** Overrides the SDK default prompt files for that op. Partial: a project can override one op and inherit defaults for the rest. |

*(`prompt_pack_id` dropped from B2 — raw-prompt editing + implicit default supersedes it; custom-vs-default is captured by `prompt_versions`. Curated named packs = a later feature.)*

**Deferred (later tier, documented not built):** `temperature`/`max_tokens`/`thinking` (SDK constants; high footgun, low extraction-quality value).

**Raw-prompt editing = security-critical surface** (CLAUDE.md POST-REVIEW trigger). Three defenses, all in §2.5:
1. **Output-schema enforcement is independent of the user prompt** — the SDK appends the structured-output instruction + JSON-schema AFTER the user text, and validation/`tolerate-filter` (memory `llm-schema-tolerate-filter`) runs regardless of what the user prompt says, so a prompt that "asks" for free-form output still can't break persistence.
2. **No cross-tenant reach** — extraction only ever sees the requesting user's own corpus (per-user/project isolation), so a crafted prompt cannot exfiltrate another tenant's data; the BYOK LLM call bills the user's own provider.
3. **Bounds + redaction** — per-op `system`/`user` capped at **16 kB each** (~2.5× the largest default prompt; the SDK `context_budget` degrades a big prompt to more chunks, so the cap only stops the absurd whole-novel-paste case); raw text is the user's own data in their own project row, but is **hashed, never copied raw**, when it crosses to learning-service (Q5).

### Q5 · Privacy → **redact-by-default, now ACTIVE for raw prompts** ✅
Raw prompt text is legitimately the user's own data living in **their** `knowledge_projects.extraction_config` row (KS, owner-isolated). But it must NOT be copied raw into learning-service (the cross-tenant analytics store):
- `config_registry.resolved_config` stores, per overridden op, a **`prompt_content_hash`** (sha256) — never the text. Default-prompt ops keep the `_version.py` file-hash. So two projects with byte-identical custom prompts dedup to one registry row; the text itself never leaves KS.
- `config_adjustment_events` stores **`before_content_hash`/`after_content_hash`** for prompt-text targets (structural targets keep `before_structural`/`after_structural`). `before_content`/`after_content` raw columns are **reserved/NULL** until a tenant opts into raw retention — mirrors `corrections` exactly.

### Q6 · Config-singleton duplication → **shared resolve+hash in the `loreweave_extraction` SDK** ✅
`PrecisionFilterConfig`/`EntityRecoveryConfig`/`_version.py` already live in the SDK that both worker-ai and KS import. Add there:
- `resolve_effective_config(*, global_defaults, project_overrides) -> ResolvedConfig`
- `config_hash(ResolvedConfig) -> str` — canonical (sorted keys) `hashlib.sha256` over the structural fields; **mirror Phase-B `_stable_hash` discipline** (NOT Python `hash()` — PYTHONHASHSEED-randomized; memory `etag-stable-hash-all-response-fields`).

Both services hash identical fields through one function → identical `config_hash`. The two module-level env caches can stay; they feed the same resolver.

### Self-review folds (resolved this review)
- **#2 config snapshot pinned at job start.** The c73f filter Redis-pubsub reload can fire mid-job; if it did, a once-per-job hash would go stale. **Resolution:** worker-ai snapshots the resolved config at job start and pins it for the whole job (mid-job reloads do not retro-apply to a running job) → deterministic attribution. `config_hash` computed once from that snapshot.
- **#3 `base_default_version` is a content-hash, not hand-maintained semver.** Derive it as `sha256` of the canonicalized global-default values (same discipline as `_version.py`) so it cannot drift when someone changes a default and forgets to bump.
- **#4 `embedding_model` EXCLUDED from `config_hash`.** It selects the retrieval vector space, not extraction text output — including it would fragment config-vs-quality dedup for no extraction signal. It stays a denormalized column on `extraction_runs` for filtering, but is not in the hash.

### §2.5 · Raw-prompt injection defense (security-critical — detail)
Prompt assembly order in the SDK is **fixed and non-overridable**: `[default-or-custom system] + [default-or-custom user + chapter text] + [SDK-appended OUTPUT CONTRACT block: "respond ONLY with JSON matching <schema>"]`. The output-contract block is always last and always SDK-controlled — a custom prompt cannot delete or precede it. Persistence then runs Pydantic validate + `tolerate-filter` regardless of prompt content. Net: the worst a hostile/garbage custom prompt can do is **degrade the user's own extraction quality** (their problem, their BYOK spend) — it cannot break the JSON contract, cannot reach another tenant's data, cannot escalate. Length caps (system ≤ 16 kB, user ≤ 16 kB) bound payload size. This is the surface that should get a `/review-impl` pass before B2-B ships.

---

## 3 · Schema — 3 tables in learning-service (`loreweave_learning`)

Idempotent DDL appended to `learning-service/app/db/migrate.py` (house style: `CREATE TABLE IF NOT EXISTS`).

```sql
-- ── config_registry ─────────────────────────────────────────────────
-- Content-addressed effective config. N runs → 1 row (dedup by hash).
CREATE TABLE IF NOT EXISTS config_registry (
  config_hash           TEXT PRIMARY KEY,           -- sha256 of canonical resolved_config (embedding_model NOT included)
  resolved_config       JSONB NOT NULL,             -- structural only; custom prompts as content-hash, NEVER raw text
  base_default_version  TEXT NOT NULL,              -- content-hash of the global-default values (not hand-maintained semver)
  prompt_versions       JSONB NOT NULL,             -- {op: "v1-op-8hex"} for default ops; {op: "custom-<sha256-8>"} for overridden ops
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── extraction_runs ─────────────────────────────────────────────────
-- One row per CHAPTER processed. Emitted at chapter completion.
CREATE TABLE IF NOT EXISTS extraction_runs (
  run_id            UUID PRIMARY KEY,               -- minted by producer (worker-ai) for dedup
  user_id           UUID NOT NULL,                  -- corpus owner; every read filters on it
  project_id        UUID,
  book_id           UUID,
  job_id            UUID,                            -- the extraction_jobs job this chapter belonged to
  scope             TEXT,                            -- 'chapter' (today); reserves 'chat'/'glossary_sync'
  chapter_ref       TEXT,                            -- source chapter id
  config_hash       TEXT NOT NULL REFERENCES config_registry(config_hash),
  model_ref         TEXT,                            -- extractor model UUID (denorm for fast filter)
  metrics           JSONB NOT NULL DEFAULT '{}',     -- {entities_merged, relations_created, events_merged, facts_merged, latency_ms?, cost_usd(est)}
  outcome           TEXT,                            -- 'succeeded'|'skipped'|'failed' at emit; refined later
  outcome_source    TEXT,                            -- 'pipeline' at emit; 'correction_join'|'rerun'|'discard' later
  -- capture provenance / idempotency (mirror corrections)
  origin_service    TEXT NOT NULL,
  origin_event_id   TEXT NOT NULL,                   -- producer outbox row id
  emitted_at        TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT extraction_runs_origin_uniq UNIQUE (origin_service, origin_event_id)
);
CREATE INDEX IF NOT EXISTS idx_runs_user_project ON extraction_runs(user_id, project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_config ON extraction_runs(config_hash);
CREATE INDEX IF NOT EXISTS idx_runs_chapter ON extraction_runs(user_id, project_id, chapter_ref);

-- ── config_adjustment_events ─────────────────────────────────────────
-- Append-only user-tuning log. Async/lossy-OK. Structural diffs only.
CREATE TABLE IF NOT EXISTS config_adjustment_events (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id               UUID NOT NULL,
  project_id            UUID,
  actor_type            TEXT NOT NULL,              -- 'user'
  actor_id              UUID,
  base_default_version  TEXT,
  target                TEXT NOT NULL,              -- e.g. 'precision_filter.categories' | 'prompts.entity.system'
  op                    TEXT NOT NULL,             -- 'set'
  before_structural     JSONB,                      -- structural targets (categories, model, booleans)
  after_structural      JSONB,
  before_content_hash   TEXT,                       -- raw-prompt targets: sha256 of prior text
  after_content_hash    TEXT,
  before_content        JSONB,                      -- RESERVED/NULL until tenant opts into raw retention (mirrors corrections)
  after_content         JSONB,                      -- RESERVED/NULL
  reason                TEXT,
  origin_service        TEXT NOT NULL,
  origin_event_id       TEXT NOT NULL,
  emitted_at            TIMESTAMPTZ,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT config_adj_origin_uniq UNIQUE (origin_service, origin_event_id)
);
CREATE INDEX IF NOT EXISTS idx_adj_user_project ON config_adjustment_events(user_id, project_id, created_at DESC);
```

Note: `corrections.source_extraction_run_id` stays a **logical** join (no enforced cross-table FK added — preserves the decoupled, best-effort emit ordering Phase B chose).

---

## 4 · Data flow

### 4.1 Run emission (B2-A) — TRANSACTIONAL
```
worker-ai job start: snapshot = resolve_effective_config(global_defaults, job.extraction_config)  # pinned for whole job
                     config_hash = config_hash(snapshot)                                            # once, from snapshot

worker-ai chapter loop (runner.py ~1097, success point) — ONE Postgres transaction:
  BEGIN
    ├─ _advance_cursor(...)                              # existing write
    └─ INSERT INTO outbox_events (event_type='knowledge.extraction_run_completed',
         payload={run_id:uuid7, user_id, project_id, book_id, job_id, scope:'chapter',
                  chapter_ref, config_hash, resolved_config(hashed prompts), prompt_versions,
                  base_default_version, model_ref, metrics:{...result counts, cost_usd},
                  outcome:'succeeded', outcome_source:'pipeline', emitted_at})
  COMMIT                                                  # run row guaranteed iff cursor advanced
            ↓ worker-infra relay → loreweave:events:knowledge (carries outbox_id)
            ↓ learning-collector consumer → RunCompletedHandler
                ├─ UPSERT config_registry (ON CONFLICT (config_hash) DO NOTHING)   # idempotent dedup
                └─ INSERT extraction_runs (ON CONFLICT (origin_service, origin_event_id) DO NOTHING)
```
Skip path (`runner.py:1083`, retry-exhausted) emits `outcome='skipped'` in the same cursor-advance txn there. **Failure path** (`runner.py:1057`, non-retryable) emits `outcome='failed'` **best-effort** (no cursor advance to ride). **Implication:** worker-ai's emit cannot reuse `emit_correction` (which acquires its own pool + swallows errors) — it needs a variant that runs `INSERT INTO outbox_events` on the **caller's connection/transaction**. New helper `emit_extraction_run(conn, payload)` (takes the txn connection).

### 4.2 Config adjustment (B2-B)
```
FE tuning panel → PUT /v1/knowledge/projects/{id}/extraction-config  (If-Match/ETag)
  KS endpoint:
    ├─ validate override against allowed-subset schema (Q4); enforce prompt length caps; reject out-of-subset keys → 422
    ├─ diff vs current extraction_config → per-target diff:
    │     • structural targets → before_structural/after_structural
    │     • prompts.* targets   → before_content_hash/after_content_hash (sha256); raw text NOT in the event
    ├─ UPDATE knowledge_projects.extraction_config (version-bumped, If-Match guarded)   # raw prompt text lives HERE (owner row)
    └─ for each changed target: emit_config_adjustment(outbox, 'knowledge.config_adjusted', {...})   # best-effort
            ↓ relay → learning-collector → ConfigAdjustedHandler → INSERT config_adjustment_events
```

### 4.3 Per-project override drives the pipeline (B2-B)
```
worker-ai job start:
  JobRow query SELECT … , p.extraction_config            # add column to existing JOIN
  resolved = resolve_effective_config(
     global_defaults = {filter/recovery/autocreate/model from env singletons + SDK constants},
     project_overrides = job.extraction_config)
  → extract_pass2(precision_filter=resolved.filter, entity_recovery=resolved.recovery,
                  model_ref=resolved.model_ref, prompt_overrides=resolved.prompts, ...)   # was module globals
```
`resolve_effective_config` precedence: **project override > global env default > SDK constant**. Missing override key → fall through to global. This is what finally makes `knowledge_projects.extraction_config` (live since K-era, unused) drive extraction.

**SDK prompt-override plumbing:** `extract_pass2` gains a `prompt_overrides: dict[op, {system?, user?}] | None` param. The per-op extractor builds its prompt as `[override.system or default_system] + [override.user or default_user + chapter text] + [SDK output-contract block]` (fixed order, §2.5). `get_extractor_version(op)` returns `custom-<sha256-8>` of the override text when an override is present, else the default file-hash — so `config_hash` and the `extraction_leaves` cache key both reflect the custom prompt.

---

## 5 · Build seam (for PLAN) — 3 sub-cycles, each independently live-smokeable

- **B2-A** — SDK `resolve_effective_config`+`config_hash`; learning migrate (3 tables); learning `RunCompletedHandler` + dispatcher reg; worker-ai `emit_extraction_run` + call at success/skip points; add `extraction_config` to JobRow query (read-only, resolve uses it but B2-A keeps global behaviour by passing empty overrides). **Live-smoke:** run a job → `config_registry` row + per-chapter `extraction_runs` rows appear; re-run same config → registry dedups (1 row), runs accrue.
- **B2-B** — (b1, non-security) wire `resolved` into `extract_pass2` for the structural levers (model/filter/recovery/autocreate); KS `PUT /extraction-config` endpoint + `ProjectExtractionConfig` model + repo + `emit_config_adjustment` for structural targets; learning `ConfigAdjustedHandler`. (b2, **security-sensitive**) SDK `prompt_overrides` plumbing + fixed-order output-contract (§2.5) + `custom-<hash>` version; prompt length caps + 422 validation; content-hash diff for prompt targets; **`/review-impl` pass on b2 before it ships**. **Live-smoke:** edit filter categories → adjustment row + next job's runs show new `config_hash`; set a custom entity prompt → extraction uses it + registry shows `custom-<hash>` + learning event carries hash-not-text.
- **B2-C** — FE `api.ts` method + `useExtractionConfig` hook + `ExtractionTuningPanel` (structural controls) + a guarded raw-prompt editor (textarea per op, with a "advanced / affects quality" warning) + dialog; mount in project settings. **Browser-smoke:** toggle a filter category + set a custom prompt in the UI → persists → re-extraction uses both.

---

## 6 · Decisions — status after design review
1. ✅ **Q3 transport** — reuse outbox for both (PO-confirmed).
2. ✅ **Run durability** — transactional run-emit (PO-confirmed; self-review #1).
3. ✅ **Override scope** — safe subset **+ raw-prompt editing IN** (PO-chosen); sampling params deferred.
4. ✅ **config_hash field set** — extractor `model_ref`+`model_source`, filter `{enabled,categories(sorted),partial_policy}`, recovery `{enabled}`, autocreate `{enabled}`, per-op prompt versions (`v1-op-*` or `custom-*`). **`embedding_model` EXCLUDED** (self-review #4); **`prompt_pack_id` DROPPED** (PO-approved — superseded by raw-prompt editing).
5. ✅ **config snapshot pinned at job start** (self-review #2) · **`base_default_version` = content-hash** (self-review #3).
6. ✅ **Resolved at PLAN sign-off (PO-approved):**
   - **outcome** — emit `'succeeded'`/`'skipped'`/**`'failed'`**; failure path emits best-effort so crash-inducing configs are visible-as-bad (reversal of the original "no run on fail" lean).
   - **`prompt_pack_id`** — **DROPPED** from B2 (raw-prompt editing + implicit default covers it; packs are a later curated-preset feature).
   - **prompt length caps** — **16 kB/field** (~2.5× largest default; `context_budget` absorbs oversize as more chunks).

---

## 7 · Test plan (checklist — diff at VERIFY per memory `design-test-plan-is-a-checklist`)
- SDK: `config_hash` stable across process restarts (not `hash()`); identical for reordered category lists (canonical sort); differs when any structural field changes; **identical when only `embedding_model` differs** (exclusion proof); `resolve_effective_config` precedence (override > env > constant; missing key falls through); `base_default_version` content-hash changes when a global default changes; `get_extractor_version(op)` returns `custom-<hash>` when a prompt override is present, file-hash otherwise.
- learning: `RunCompletedHandler` upserts registry once for N runs (dedup); `extraction_runs` origin-uniq dedup on relay re-emit; `ConfigAdjustedHandler` insert; **prompt-target events carry `*_content_hash`, NOT raw text** (privacy regression-lock); DLQ on handler raise.
- worker-ai: **run-emit is transactional** — a failed outbox insert rolls back the cursor-advance (chapter re-processed, never a silent missing run); skip-path emits `outcome='skipped'`; config snapshot pinned at job start (a mid-job `set_precision_filter_config` does NOT change the running job's `config_hash`); resolved config passed to `extract_pass2` (non-default override produces a DIFFERENT `config_hash` — guard the default-equals-expected false-negative, memory `happy-path-default-value-false-negative`).
- SDK prompt-override (security): output-contract block present + LAST even when custom `system`/`user` try to suppress it; JSON validation still rejects non-conforming output under a hostile prompt; length-cap returns 422; custom prompt actually changes extraction output (non-default-equals-expected).
- KS endpoint: If-Match required (428); override schema rejects out-of-subset keys (422); prompt length cap (422); structural vs content-hash diff routing correct; emit on change only (no-op edit → no event).
- FE: panel renders current config; toggle → PUT → toast + invalidate; raw-prompt editor warning visible; ETag 412 refresh path; visibility/open-close (memory `visibility-transition-coverage`).
- **Cross-service live-smoke** (≥2 services touched → mandatory token): B2-A run→registry/runs; B2-B adjustment→learning + new hash on next job + custom-prompt round-trip shows hash-not-text in learning.
