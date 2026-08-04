-- CP-0.5 — THE BASELINE DERIVATION. The four numbers, with their queries attached.
--
-- Spec: docs/specs/2026-08-03-agent-runtime-unification/ · run: docs/plans/2026-08-04-agent-runtime-RUNSTATE.md
--
-- Why this file exists. The four baseline classes were carried in markdown prose, and one of them
-- ("65.7%") had NO derivation anywhere in the repo — it survived by being repeated, and was
-- compiled from there into a migration comment, the instrument, and three test docstrings before
-- an independent verifier recomputed it at 57.7% and withdrew it. A number without its query is a
-- rumour with a decimal point.
--
-- Every class below states its predicate, its numerator and its denominator, and reports BOTH the
-- raw population and the decontaminated one. The gap between them is not a footnote: 57.5% of the
-- raw failure population is test-harness traffic, and every organic figure moves in the FLATTERING
-- direction, which is exactly the direction that would have gone unquestioned.
--
-- Run:  docker exec -i infra-postgres-1 psql -U loreweave -d loreweave_chat -f - < this file

\pset footer off

-- ── CONTAMINATION, declared before anything is counted ────────────────────────────────────────
-- Excluded, and why each one is not a judgement call:
--   * sessions titled 'F17 monitor verify' — a 4-session harness run that alone contributes 1,180
--     tool_list breaker fires, 29.4% of every failure in the corpus;
--   * blank-argument calls — a harness sweep that calls tools with '{}' to probe schemas.
CREATE OR REPLACE TEMP VIEW _organic AS
SELECT m.*
FROM chat_messages m
JOIN chat_sessions s ON s.session_id = m.session_id
WHERE COALESCE(s.title, '') NOT ILIKE '%F17 monitor verify%'
  AND COALESCE(s.title, '') NOT ILIKE '%[THROWAWAY]%';

-- One row per recorded tool call, both populations, so every class below shares one definition of
-- "a call" and cannot drift between metrics.
CREATE OR REPLACE TEMP VIEW _calls AS
SELECT m.message_id, m.session_id, m.created_at,
       (tc->>'tool')                          AS tool,
       COALESCE((tc->>'ok')::boolean, false)  AS ok,
       tc->>'error'                           AS error,
       tc->>'source'                          AS source,      -- NULL for every pre-CP-0 row
       (m.session_id IN (SELECT session_id FROM _organic)) AS organic
FROM chat_messages m
CROSS JOIN LATERAL jsonb_array_elements(m.tool_calls) AS tc
WHERE m.tool_calls IS NOT NULL;

\echo '== 0 · POPULATION =='
SELECT count(*) FILTER (WHERE true)            AS calls_raw,
       count(*) FILTER (WHERE organic)         AS calls_organic,
       count(*) FILTER (WHERE NOT ok)          AS failures_raw,
       count(*) FILTER (WHERE NOT ok AND organic) AS failures_organic
FROM _calls;

-- ── CLASS 1 · CARRY-FORWARD ───────────────────────────────────────────────────────────────────
-- PINNED DEFINITION. The published 61.8% used "succeeded ANYWHERE in the session, including
-- later", which counts a failure as carry-forward on the strength of a success that had not
-- happened yet. That is not the claim. The claim is that the model failed on a capability it had
-- ALREADY been shown to work, so the success must PRECEDE the failure.
--   numerator   — failures whose tool succeeded EARLIER in the same session
--   denominator — all failures
-- Reported alongside the loose reading, so the 4.7pp difference stays visible instead of becoming
-- an improvement someone claims later by writing a more correct query.
\echo '== 1 · CARRY-FORWARD (strict: success STRICTLY EARLIER) =='
WITH f AS (SELECT * FROM _calls WHERE NOT ok),
     s AS (SELECT * FROM _calls WHERE ok)
SELECT scope,
       count(*)                                    AS failures,
       count(*) FILTER (WHERE strict)              AS carry_strict,
       round(100.0 * count(*) FILTER (WHERE strict) / NULLIF(count(*), 0), 1) AS pct_strict,
       count(*) FILTER (WHERE loose)               AS carry_loose,
       round(100.0 * count(*) FILTER (WHERE loose) / NULLIF(count(*), 0), 1)  AS pct_loose
FROM (
  SELECT 'raw' AS scope, f.*,
         EXISTS (SELECT 1 FROM s WHERE s.session_id = f.session_id AND s.tool = f.tool
                   AND s.created_at < f.created_at) AS strict,
         EXISTS (SELECT 1 FROM s WHERE s.session_id = f.session_id AND s.tool = f.tool) AS loose
  FROM f
  UNION ALL
  SELECT 'organic', f.*,
         EXISTS (SELECT 1 FROM s WHERE s.session_id = f.session_id AND s.tool = f.tool
                   AND s.created_at < f.created_at AND s.organic),
         EXISTS (SELECT 1 FROM s WHERE s.session_id = f.session_id AND s.tool = f.tool AND s.organic)
  FROM f WHERE f.organic
) x
GROUP BY scope ORDER BY scope;

-- ── CLASS 2 · OUR OWN PROSE COUNTED AS A TOOL ERROR ───────────────────────────────────────────
-- MEASURED CLASS = "not a real dispatch". Pre-CP-0 rows have no `source`, so the baseline is
-- derived from the breaker's own prose signatures — a LOWER BOUND, and labelled as one. That
-- limitation is the entire reason `source` exists.
--
-- The trap this pins: CP-0's classifier routes tool_list/find_tools failures to `meta`. Scoring
-- the new runtime on `breaker` alone against a blended baseline moves the class ~33pp on IDENTICAL
-- rows — a 41pp "win" before a request is served. So both arms are scored on NOT-A-REAL-DISPATCH,
-- and `meta` is reported inside it, never deducted from it.
\echo '== 2 · NOT-A-REAL-DISPATCH, as a share of failures (LOWER BOUND pre-CP-0) =='
SELECT CASE WHEN organic THEN 'organic' ELSE 'raw-only' END AS scope,
       count(*)                                        AS failures,
       count(*) FILTER (WHERE ours)                    AS not_real_dispatch,
       round(100.0 * count(*) FILTER (WHERE ours) / NULLIF(count(*), 0), 1) AS pct,
       count(*) FILTER (WHERE ours AND is_meta)        AS of_which_meta
FROM (
  SELECT organic,
         tool IN ('tool_list','tool_load','find_tools','conversation_search',
                  'chat_search_sessions','load_skill','workflow_list','workflow_load') AS is_meta,
         (error ILIKE '%already ran this turn%' OR error ILIKE '%Do not ask to run it again%'
          OR error ILIKE '%repeated%' OR error ILIKE '%blocked%' OR error ILIKE '%not permitted%'
          OR error ILIKE '%budget%' OR error ILIKE '%cap%'
          OR tool IN ('tool_list','tool_load','find_tools','conversation_search',
                      'chat_search_sessions','load_skill','workflow_list','workflow_load')) AS ours
  FROM _calls WHERE NOT ok
) x GROUP BY organic ORDER BY organic;

-- ── CLASS 3 · IDENTIFIER RESOLUTION ───────────────────────────────────────────────────────────
-- Denominator is REAL errors — failures that are not our own prose — because an id-resolution rate
-- computed over a population that is majority breaker output measures the breaker, not the model.
\echo '== 3 · IDENTIFIER RESOLUTION, as a share of REAL errors =='
SELECT CASE WHEN organic THEN 'organic' ELSE 'raw-only' END AS scope,
       count(*) AS real_errors,
       count(*) FILTER (WHERE id_err) AS id_errors,
       round(100.0 * count(*) FILTER (WHERE id_err) / NULLIF(count(*), 0), 1) AS pct
FROM (
  SELECT organic,
         (error ILIKE '%not found%' OR error ILIKE '%invalid%id%' OR error ILIKE '%uuid%'
          OR error ILIKE '%placeholder%' OR error ILIKE '%does not exist%'
          OR error ILIKE '%missing required%') AS id_err
  FROM _calls
  WHERE NOT ok
    AND tool NOT IN ('tool_list','tool_load','find_tools','conversation_search',
                     'chat_search_sessions','load_skill','workflow_list','workflow_load')
    AND COALESCE(error, '') NOT ILIKE '%already ran this turn%'
) x GROUP BY organic ORDER BY organic;

-- ── CLASS 4 · TERMINAL OUTCOME ────────────────────────────────────────────────────────────────
-- The CP-0.4 deliverable that was NOT delivered: `interrupted` was never frozen. Reported through
-- CP-0's own shim so the baseline is stated in the SAME vocabulary the new runtime writes —
-- otherwise the comparison is between two different words.
--
-- NULL maps to `interrupted` because that is what the shim does with an unrecognised value, and
-- reporting NULLs as anything else would flatter the baseline by pretending we knew.
\echo '== 4 · TERMINAL OUTCOME, through the CP-0.4 shim =='
SELECT CASE WHEN organic THEN 'organic' ELSE 'raw' END AS scope,
       count(*) AS assistant_turns,
       count(*) FILTER (WHERE mapped = 'completed')         AS completed,
       count(*) FILTER (WHERE mapped = 'awaiting_input')    AS awaiting_input,
       count(*) FILTER (WHERE mapped = 'failed')            AS failed,
       count(*) FILTER (WHERE mapped = 'crashed')           AS crashed,
       count(*) FILTER (WHERE mapped = 'interrupted')       AS unclassified,
       round(100.0 * count(*) FILTER (WHERE mapped = 'interrupted') / NULLIF(count(*), 0), 1)
         AS pct_unclassified
FROM (
  SELECT (m.session_id IN (SELECT session_id FROM _organic)) AS organic,
         CASE WHEN m.is_error THEN 'failed'
              WHEN m.finish_reason = 'stop' THEN 'completed'
              WHEN m.finish_reason = 'awaiting_input' THEN 'awaiting_input'
              WHEN m.finish_reason = 'error' THEN 'failed'
              WHEN m.finish_reason = 'streaming' THEN 'crashed'
              ELSE 'interrupted' END AS mapped
  FROM chat_messages m WHERE m.role = 'assistant'
) x GROUP BY organic ORDER BY organic;
-- (An earlier draft UNIONed the organic rows back in, double-counting them. The PERCENTAGE was
-- unaffected — which is exactly why it survived a glance, and why counts are printed beside it.)

-- ── 5 · WHAT THE TRAFFIC CAN ACTUALLY SUPPORT ─────────────────────────────────────────────────
-- The input to the acceptance arithmetic. Reported here rather than asserted in prose, because the
-- previous plan set a per-declaration bound that needed 5-12 YEARS of this traffic to move.
\echo '== 5 · WEEKLY TRAFFIC (the ceiling on any bound) =='
SELECT date_trunc('week', created_at)::date AS week,
       count(*) AS calls, count(*) FILTER (WHERE NOT ok) AS failures
FROM _calls WHERE organic AND created_at > now() - interval '10 weeks'
GROUP BY 1 ORDER BY 1 DESC;
