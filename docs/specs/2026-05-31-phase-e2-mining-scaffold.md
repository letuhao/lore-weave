# Phase E2 — Config Data-Mining Scaffold

**Date:** 2026-05-31  
**Status:** DESIGN LOCKED  
**Size:** L (10 files, DB migrations, cross-service)  
**Entry gate:** B2 shipped ✓ (data volume near-zero at scaffold time — queries return empty; that's expected)

---

## 1 · Goal

Scaffold the config-vs-outcome mining layer so it fills automatically as `extraction_runs` / `config_adjustment_events` / `corrections` accumulate. No FE this cycle.

---

## 2 · Data model changes

### 2.1 `knowledge_projects.genre TEXT` (KS)

```sql
ALTER TABLE knowledge_projects ADD COLUMN IF NOT EXISTS genre TEXT;
```

Free-text (no enum). Examples: `"Tiên hiệp"`, `"trinh thám"`, `"sci-fi"`. NULL = unclassified. User-settable via PATCH.

### 2.2 `extraction_runs.genre TEXT` (learning-service)

```sql
ALTER TABLE extraction_runs ADD COLUMN IF NOT EXISTS genre TEXT;
```

Copied from `knowledge_projects.genre` at run-emit time. NULL when project has no genre. Enables all genre-segment queries without a cross-DB join at query time.

---

## 3 · Emit path

`worker-ai._get_running_jobs` already JOINs `knowledge_projects` (for `embedding_dimension` + `extraction_config`). Adding `p.genre` to that SELECT is the only worker-ai change beyond `JobRow` + payload.

Payload key: `"genre": job.genre` (top-level, not inside `resolved_config`). `handle_run_completed` reads it and passes to the INSERT.

---

## 4 · Mining queries (all within `loreweave_learning`)

### Q1 — Genre-specific config quality

```sql
SELECT er.genre, er.config_hash,
       count(*) AS run_count,
       count(*) FILTER (WHERE er.outcome = 'succeeded') AS succeeded,
       avg((er.metrics->>'entities_merged')::int)
           FILTER (WHERE er.outcome = 'succeeded') AS avg_entities_on_success,
       count(*) FILTER (WHERE er.outcome = 'succeeded')::float
           / NULLIF(count(*), 0) AS success_rate   -- quality proxy, outcome-gated
FROM extraction_runs er
WHERE ($1::text IS NULL OR er.genre = $1)           -- genre filter
  AND ($2::bool IS FALSE OR (                       -- power-user segmentation
         SELECT count(*) FROM config_adjustment_events c
         WHERE c.user_id = er.user_id AND c.project_id = er.project_id
       ) <= $3)                                     -- power_user_threshold
GROUP BY er.genre, er.config_hash
HAVING count(*) >= 2                                -- suppress single-run noise
ORDER BY er.genre NULLS LAST, success_rate DESC NULLS LAST
LIMIT $4;
```

**Guardrail baked in:** `success_rate` = succeeded/total, never raw popularity.

### Q2 — Model × task matrix

```sql
SELECT er.model_ref,
       er.scope,
       (cr.resolved_config->>'precision_filter') IS NOT NULL AS has_filter,
       count(*) AS run_count,
       avg(CASE er.outcome
             WHEN 'succeeded' THEN 1.0
             WHEN 'skipped'   THEN 0.3
             ELSE 0.0 END) AS weighted_outcome
FROM extraction_runs er
JOIN config_registry cr USING (config_hash)
WHERE ($1::text IS NULL OR er.scope = $1)
GROUP BY er.model_ref, er.scope, has_filter
HAVING count(*) >= 2
ORDER BY weighted_outcome DESC;
```

### Q3 — Default-drift detection

```sql
SELECT cae.target, cae.base_default_version,
       count(DISTINCT cae.project_id) AS affected_projects,
       count(DISTINCT cae.after_structural::text) AS distinct_after_values,
       CASE WHEN count(DISTINCT cae.after_structural::text) = 1
            THEN 'convergent' ELSE 'divergent' END AS drift_pattern,
       count(DISTINCT er.run_id) AS runs_with_outcome  -- popularity≠quality
FROM config_adjustment_events cae
JOIN extraction_runs er
  ON er.user_id = cae.user_id AND er.project_id = cae.project_id
WHERE cae.before_structural IS DISTINCT FROM cae.after_structural
  AND ($1::text IS NULL OR cae.target = $1)
GROUP BY cae.target, cae.base_default_version
ORDER BY affected_projects DESC, drift_pattern;
```

### Q4 — Correction-join outcome recompute (recipe scaffold)

```sql
SELECT er.run_id, er.project_id, er.outcome AS pipeline_outcome,
       er.created_at,
       count(c.id) AS post_run_corrections,
       CASE
         WHEN count(c.id) = 0 THEN er.outcome
         WHEN count(c.id) <= 3 THEN 'minor_corrected'
         ELSE 'major_corrected'
       END AS recomputed_outcome
FROM extraction_runs er
LEFT JOIN corrections c
  ON c.user_id = er.user_id
  AND (c.project_id = er.project_id OR c.project_id IS NULL)
  AND c.correction_ts > er.created_at
  AND c.correction_ts <= er.created_at + ($2::int * INTERVAL '1 day')
  AND (c.source_extraction_run_id = er.run_id
       OR c.source_extraction_run_id IS NULL)
WHERE er.user_id = $1
GROUP BY er.run_id, er.project_id, er.outcome, er.created_at
ORDER BY er.created_at DESC
LIMIT $3 OFFSET $4;
```

Returns empty today (`source_extraction_run_id` is NULL; the `IS NULL` arm joins all corrections to all runs — intentionally loose for cold-start, will tighten once the FK is populated). Establishes the join recipe per plan §2.4 Q2.

---

## 5 · API surface

All under `/v1/learning/mining/`. JWT-authenticated. Gateway already proxies `/v1/learning/*` — no gateway changes.

```
GET /v1/learning/mining/config-quality
    ?genre=<str>&limit=20&exploration_fraction=0.1&power_user_threshold=10&segment_power_users=false
    Response: { items: [ConfigQualityRow], exploration: [ConfigQualityRow] }

GET /v1/learning/mining/model-matrix
    ?scope=chapter
    Response: { items: [ModelMatrixRow] }

GET /v1/learning/mining/default-drift
    ?target=<str>&base_default_version=<str>
    Response: { items: [DriftRow] }

GET /v1/learning/mining/outcome-recompute
    ?project_id=<uuid>&window_days=30&limit=100&offset=0
    Response: { items: [OutcomeRecomputeRow], total: int }
```

`exploration_fraction` (default 0.1): fraction of top-N to replace with random alternatives from the tail. Implements the explore/exploit guardrail.

---

## 6 · Guardrails checklist

- [ ] Q1 `success_rate` is `succeeded/total`, NOT raw `run_count`
- [ ] Q3 joins `extraction_runs` to confirm runs happened (runs_with_outcome, not adj-frequency)
- [ ] `exploration` array on config-quality endpoint (random sample from tail)
- [ ] `segment_power_users`/`power_user_threshold` exposed on config-quality
- [ ] `source_extraction_run_id` IS NULL fallback documented (loose cold-start)

---

## 7 · Build order

| Step | Files | Atomic commit |
|------|-------|---------------|
| E2-1 | KS migrate.py + models.py + repositories/projects.py | `feat(ks): add genre field to knowledge_projects` |
| E2-2 | worker-ai runner.py | `feat(worker-ai): emit genre on extraction_run_completed` |
| E2-3 | learning-service migrate.py + handlers.py | `feat(learning): store genre on extraction_runs` |
| E2-4 | learning-service db/mining.py (new) | `feat(learning): mining query layer (4 queries)` |
| E2-5 | learning-service routers/mining.py (new) + models.py + main.py | `feat(learning): mining read API (/v1/learning/mining/*)` |

E2-1 through E2-3 must land before E2-4 (query shape depends on genre column).  
E2-4 before E2-5 (router imports query functions).
