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

-- ── THE INPUT PIN ─────────────────────────────────────────────────────────────────────────────
-- Decision 2 failed on exactly this: freezing the OUTPUT of an unfrozen input is not freezing.
-- The catalog snapshot has a content hash; this derivation reads a live, mutable database, so its
-- numbers can move under it with no diff anywhere. There is no `AS OF` in Postgres, so the honest
-- substitute is a fingerprint: if these three values differ from the frozen run, the numbers below
-- are NOT comparable to it and nothing may be concluded from the difference.
\echo '== PIN · corpus fingerprint (numbers below are valid ONLY for this fingerprint) =='
-- Hashes the FIELDS THE DERIVATION READS, not the primary-key set. The first version hashed only
-- message_id, so a verifier mutated finish_reason/tool_calls/is_error inside a rolled-back
-- transaction — moving class 4 from 4.9% to 0.0% — and the fingerprint did not change one
-- character. It certified that the same ROWS existed, which is not what any number here depends on.
-- chat_sessions.title is included because the ENTIRE decontamination rests on it and it was not
-- covered at all.
SELECT (SELECT count(*) FROM chat_messages) AS messages,
       (SELECT max(created_at) FROM chat_messages) AS newest,
       md5(
         (SELECT string_agg(message_id::text || coalesce(finish_reason,'') || coalesce(outcome,'')
                            || is_error::text || coalesce(tool_calls::text,''), ',' ORDER BY message_id)
          FROM chat_messages)
         || (SELECT string_agg(session_id::text || coalesce(title,''), ',' ORDER BY session_id)
             FROM chat_sessions)
       ) AS corpus_md5;

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
-- WITH ORDINALITY is load-bearing and its absence invalidated the first version of this file.
-- Every element of a turn's tool_calls array carries the MESSAGE's created_at, so a predicate
-- written as `success.created_at < failure.created_at` can NEVER fire within a turn — it silently
-- measured "succeeded in an earlier MESSAGE" while its own comment claimed "already succeeded".
-- The array position IS the intra-turn order; (created_at, ord) is the real clock.
CREATE OR REPLACE TEMP VIEW _calls AS
SELECT m.message_id, m.session_id, m.created_at, o.ord,
       (tc->>'tool')                          AS tool,
       COALESCE((tc->>'ok')::boolean, false)  AS ok,
       tc->>'error'                           AS error,
       tc->>'source'                          AS source,      -- NULL for every pre-CP-0 row
       COALESCE(tc->'args', '{}'::jsonb)      AS args,
       (m.session_id IN (SELECT session_id FROM _organic)) AS organic
FROM chat_messages m
CROSS JOIN LATERAL jsonb_array_elements(m.tool_calls) WITH ORDINALITY AS o(tc, ord)
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
-- 🔴 Classes 1 and 2 were measuring THE SAME 1,017 ROWS and pooling them as two independent
-- targets. 91.1% of "carry-forward" failures were our own repeat-breaker prose — the model calling
-- a tool that had already succeeded IS what trips the repeat breaker, so the breaker's own refusal
-- became the evidence of carry-forward. It also moved with an integer constant (REPEAT_READ_CAP=2),
-- which means the metric could be "improved" by editing one line and changing nothing real.
-- Carry-forward is now measured over REAL errors only, and reported both ways.
WITH f AS (SELECT * FROM _calls WHERE NOT ok),
     fr AS (SELECT * FROM _calls WHERE NOT ok
              AND NOT (error ILIKE '%already ran this turn%' OR error ILIKE '%You have already called%'
                       OR error ILIKE '%times this turn%' OR error ILIKE '%this turn%'
                       OR tool IN ('tool_list','tool_load','find_tools','conversation_search',
                                   'chat_search_sessions','load_skill','workflow_list','workflow_load'))),
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
                   AND (s.created_at, s.ord) < (f.created_at, f.ord)) AS strict,
         EXISTS (SELECT 1 FROM s WHERE s.session_id = f.session_id AND s.tool = f.tool) AS loose
  FROM f
  UNION ALL
  SELECT 'organic', f.*,
         EXISTS (SELECT 1 FROM s WHERE s.session_id = f.session_id AND s.tool = f.tool
                   AND (s.created_at, s.ord) < (f.created_at, f.ord) AND s.organic),
         EXISTS (SELECT 1 FROM s WHERE s.session_id = f.session_id AND s.tool = f.tool AND s.organic)
  FROM f WHERE f.organic
  UNION ALL
  SELECT 'organic_real_errors', fr.*,
         EXISTS (SELECT 1 FROM s WHERE s.session_id = fr.session_id AND s.tool = fr.tool
                   AND (s.created_at, s.ord) < (fr.created_at, fr.ord) AND s.organic),
         EXISTS (SELECT 1 FROM s WHERE s.session_id = fr.session_id AND s.tool = fr.tool AND s.organic)
  FROM fr WHERE fr.organic
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
         -- The single largest error string in the corpus was MISSING from the first version:
         -- "You have already called 'X' ... N times this turn" (495 rows). It is our own
         -- middleware prose, and omitting it understated this class by 26pp.
         (error ILIKE '%already ran this turn%' OR error ILIKE '%Do not ask to run it again%'
          OR error ILIKE '%You have already called%' OR error ILIKE '%times this turn%'
          OR error ILIKE '%this turn%'
          -- REMOVED: '%budget%', '%not permitted%', '%blocked%'. They caught 21 REAL dispatches
          -- that failed pydantic validation — `Extra inputs are not permitted` is a pydantic
          -- constant, so every extra_forbidden failure in the product was misclassified as our
          -- prose, and `%budget%` matched because a CALLER'S OWN ARGUMENT is named budget_usd.
          OR error ILIKE '%repeated%'
          OR tool IN ('tool_list','tool_load','find_tools','conversation_search',
                      'chat_search_sessions','load_skill','workflow_list','workflow_load')) AS ours
  -- The blank-arg exclusion removed 288 UNSCRIPTED rows, the largest block being 157x
-- "find_tools has been called with no intent ... STOP" — which is our own middleware prose, i.e.
-- THE CLASS'S OWN SUBJECT deleted from its own numerator. A decontamination rule that removes the
-- thing being counted is not decontamination. Blank-arg probes are excluded only where they are
-- also scripted.
FROM _calls WHERE NOT ok AND NOT (args = '{}'::jsonb AND NOT organic)
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
          -- REMOVED '%missing required%': of the 27 rows it uniquely added, ~19 are missing
          -- CONTENT arguments (['body'], ['items'], ['args']) — the error text itself says they
          -- are not ids. A class named "identifier resolution" must not count them.
          ) AS id_err
  FROM _calls
  WHERE NOT ok
    -- ONE definition of "a real error", shared with class 1. This denominator previously used a
    -- SECOND, weaker one and so retained 763 rows (30.9%) of our own breaker prose — inflating the
    -- denominator and DEFLATING the rate, in the direction that looked like less of a problem.
    -- Two classes in one file disagreeing about what "real error" means is how that survived.
    AND NOT (error ILIKE '%already ran this turn%' OR error ILIKE '%You have already called%'
             OR error ILIKE '%times this turn%' OR error ILIKE '%this turn%'
             OR tool IN ('tool_list','tool_load','find_tools','conversation_search',
                         'chat_search_sessions','load_skill','workflow_list','workflow_load'))
) x GROUP BY organic ORDER BY organic;

-- ── CLASS 4 · TERMINAL OUTCOME ────────────────────────────────────────────────────────────────
-- The CP-0.4 deliverable that was NOT delivered: `interrupted` was never frozen. Reported through
-- CP-0's own shim so the baseline is stated in the SAME vocabulary the new runtime writes —
-- otherwise the comparison is between two different words.
--
-- NULL maps to `interrupted` because that is what the shim does with an unrecognised value, and
-- reporting NULLs as anything else would flatter the baseline by pretending we knew.
-- 🔴 COLUMN-AGE ARTIFACT, and the first version of this class did not control for it.
-- `finish_reason` shipped 2026-07-19. Before that date every row is unclassified BY CONSTRUCTION
-- (the column did not exist), so a corpus-wide 90.7% measures the column's age, not the runtime's
-- behaviour — and the acceptance target "<5%" is ALREADY MET by rows written after it landed.
-- Windowed below. The pre-column rows are reported separately, never blended in.
\echo '== 4 · TERMINAL OUTCOME, through the CP-0.4 shim, WINDOWED on column age =='
SELECT CASE WHEN organic THEN 'organic' ELSE 'raw' END AS scope,
       count(*) AS assistant_turns,
       count(*) FILTER (WHERE mapped = 'completed')         AS completed,
       count(*) FILTER (WHERE mapped = 'awaiting_input')    AS awaiting_input,
       count(*) FILTER (WHERE mapped = 'failed')            AS failed,
       count(*) FILTER (WHERE mapped = 'crashed')           AS crashed,
       count(*) FILTER (WHERE mapped = 'interrupted')       AS interrupted_recorded,
       count(*) FILTER (WHERE mapped = 'unrecorded')        AS unrecorded,
       round(100.0 * count(*) FILTER (WHERE mapped = 'unrecorded') / NULLIF(count(*), 0), 1)
         AS pct_unrecorded
FROM (
  SELECT (m.session_id IN (SELECT session_id FROM _organic)) AS organic,
         CASE WHEN m.is_error THEN 'failed'
              WHEN m.finish_reason = 'stop' THEN 'completed'
              WHEN m.finish_reason = 'awaiting_input' THEN 'awaiting_input'
              WHEN m.finish_reason = 'error' THEN 'failed'
              WHEN m.finish_reason = 'streaming' THEN 'crashed'
              -- 'interrupted' is a RECORDED outcome, not an absent one. Counting it as
              -- unclassified made the genuine interruption rate wear the label "we failed to
              -- classify this", inflating 0.0% to 4.9%.
              WHEN m.finish_reason = 'interrupted' THEN 'interrupted'
              ELSE 'unrecorded' END AS mapped
  FROM chat_messages m WHERE m.role = 'assistant'
    AND m.created_at >= TIMESTAMPTZ '2026-07-19'   -- after finish_reason existed
) x GROUP BY organic ORDER BY organic;
-- (An earlier draft UNIONed the organic rows back in, double-counting them. The PERCENTAGE was
-- unaffected — which is exactly why it survived a glance, and why counts are printed beside it.)

-- ── 5 · WHAT THE TRAFFIC CAN ACTUALLY SUPPORT ─────────────────────────────────────────────────
-- The input to the acceptance arithmetic. Reported here rather than asserted in prose, because the
-- previous plan set a per-declaration bound that needed 5-12 YEARS of this traffic to move.
\echo '== 5 · WEEKLY TRAFFIC (the ceiling on any bound) =='
SELECT date_trunc('week', created_at)::date AS week,
       count(*) AS calls, count(*) FILTER (WHERE NOT ok) AS failures
FROM _calls WHERE organic AND created_at > TIMESTAMPTZ '2026-05-25'  -- absolute, not now()-relative
GROUP BY 1 ORDER BY 1 DESC;
