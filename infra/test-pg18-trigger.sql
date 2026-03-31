-- ============================================================================
-- LoreWeave — PG18 Trigger + JSON_TABLE Pre-Flight Test
-- Run: docker exec pg18test psql -U loreweave -d loreweave_book -f /test.sql
-- ============================================================================

\echo '=== D0-03: Testing JSON_TABLE inside PL/pgSQL trigger ==='

-- ── Setup ──────────────────────────────────────────────────────────────────

DROP TABLE IF EXISTS test_blocks CASCADE;
DROP TABLE IF EXISTS test_drafts CASCADE;

CREATE TABLE test_drafts (
  chapter_id UUID PRIMARY KEY DEFAULT uuidv7(),
  body JSONB NOT NULL,
  body_format TEXT NOT NULL DEFAULT 'json'
);

CREATE TABLE test_blocks (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  chapter_id UUID NOT NULL REFERENCES test_drafts(chapter_id) ON DELETE CASCADE,
  block_index INT NOT NULL,
  block_type TEXT NOT NULL,
  text_content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  heading_context TEXT,
  attrs JSONB,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(chapter_id, block_index)
);

-- ── Trigger Function ───────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION fn_test_extract_blocks()
RETURNS TRIGGER AS $$
DECLARE
  _max_idx INT;
BEGIN
  -- UPSERT blocks from JSON_TABLE reading _text
  INSERT INTO test_blocks (chapter_id, block_index, block_type, text_content, content_hash, attrs)
  SELECT
    NEW.chapter_id,
    (jt.block_index - 1),
    jt.block_type,
    COALESCE(jt.text_content, ''),
    encode(sha256(COALESCE(jt.text_content, '')::bytea), 'hex'),
    jt.block_attrs
  FROM JSON_TABLE(
    NEW.body, '$.content[*]'
    COLUMNS (
      block_index FOR ORDINALITY,
      block_type TEXT PATH '$.type',
      text_content TEXT PATH '$._text',
      block_attrs JSONB PATH '$.attrs'
    )
  ) AS jt
  WHERE jt.block_type IS NOT NULL
  ON CONFLICT (chapter_id, block_index)
  DO UPDATE SET
    block_type = EXCLUDED.block_type,
    text_content = EXCLUDED.text_content,
    content_hash = EXCLUDED.content_hash,
    attrs = EXCLUDED.attrs,
    updated_at = CASE
      WHEN test_blocks.content_hash = EXCLUDED.content_hash
      THEN test_blocks.updated_at
      ELSE now()
    END;

  -- Delete blocks beyond new count
  SELECT count(*) INTO _max_idx
  FROM JSON_TABLE(NEW.body, '$.content[*]' COLUMNS (i FOR ORDINALITY)) AS jt;

  DELETE FROM test_blocks
  WHERE chapter_id = NEW.chapter_id AND block_index >= _max_idx;

  -- Fill heading_context
  UPDATE test_blocks cb SET
    heading_context = sub.ctx
  FROM (
    SELECT
      id,
      MAX(CASE WHEN block_type = 'heading' THEN text_content END)
        OVER (PARTITION BY chapter_id ORDER BY block_index
              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS ctx
    FROM test_blocks
    WHERE chapter_id = NEW.chapter_id
  ) sub
  WHERE cb.id = sub.id AND cb.chapter_id = NEW.chapter_id;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_test_extract
  AFTER INSERT OR UPDATE OF body ON test_drafts
  FOR EACH ROW
  EXECUTE FUNCTION fn_test_extract_blocks();

\echo '--- Setup complete ---'

-- ── Test 1: Basic INSERT with 3 blocks ─────────────────────────────────────

\echo ''
\echo '=== TEST 1: INSERT 3 blocks (heading + paragraph + callout) ==='

INSERT INTO test_drafts (chapter_id, body) VALUES (
  '00000000-0000-0000-0000-000000000001',
  '{
    "type": "doc",
    "content": [
      {"type": "heading", "attrs": {"level": 2}, "_text": "Chapter One"},
      {"type": "paragraph", "_text": "First paragraph of the story."},
      {"type": "callout", "attrs": {"type": "note"}, "_text": "Author note here"}
    ]
  }'::jsonb
);

SELECT block_index, block_type, text_content, heading_context,
       left(content_hash, 12) AS hash_prefix
FROM test_blocks
WHERE chapter_id = '00000000-0000-0000-0000-000000000001'
ORDER BY block_index;

-- Expected: 3 rows, heading_context propagates from heading

-- ── Test 2: UPDATE changes only one block ──────────────────────────────────

\echo ''
\echo '=== TEST 2: UPDATE — change paragraph text, verify UPSERT stability ==='

-- Record current IDs and timestamps
CREATE TEMP TABLE pre_update AS
  SELECT id, block_index, content_hash, updated_at
  FROM test_blocks
  WHERE chapter_id = '00000000-0000-0000-0000-000000000001';

-- Small delay to detect updated_at changes
SELECT pg_sleep(0.1);

UPDATE test_drafts SET body = '{
  "type": "doc",
  "content": [
    {"type": "heading", "attrs": {"level": 2}, "_text": "Chapter One"},
    {"type": "paragraph", "_text": "MODIFIED paragraph text."},
    {"type": "callout", "attrs": {"type": "note"}, "_text": "Author note here"}
  ]
}'::jsonb
WHERE chapter_id = '00000000-0000-0000-0000-000000000001';

SELECT
  b.block_index,
  b.block_type,
  b.text_content,
  CASE WHEN b.id = p.id THEN 'SAME' ELSE 'NEW' END AS id_stable,
  CASE WHEN b.content_hash = p.content_hash THEN 'SAME' ELSE 'CHANGED' END AS hash_status,
  CASE WHEN b.updated_at = p.updated_at THEN 'SAME' ELSE 'UPDATED' END AS timestamp_status
FROM test_blocks b
JOIN pre_update p ON p.block_index = b.block_index
WHERE b.chapter_id = '00000000-0000-0000-0000-000000000001'
ORDER BY b.block_index;

-- Expected: block 0 (heading) = SAME id, SAME hash, SAME timestamp
--           block 1 (paragraph) = SAME id, CHANGED hash, UPDATED timestamp
--           block 2 (callout) = SAME id, SAME hash, SAME timestamp

DROP TABLE pre_update;

-- ── Test 3: Block count shrinks ────────────────────────────────────────────

\echo ''
\echo '=== TEST 3: UPDATE — remove callout (3 blocks → 2) ==='

UPDATE test_drafts SET body = '{
  "type": "doc",
  "content": [
    {"type": "heading", "attrs": {"level": 2}, "_text": "Chapter One"},
    {"type": "paragraph", "_text": "MODIFIED paragraph text."}
  ]
}'::jsonb
WHERE chapter_id = '00000000-0000-0000-0000-000000000001';

SELECT count(*) AS block_count FROM test_blocks
WHERE chapter_id = '00000000-0000-0000-0000-000000000001';

-- Expected: 2

-- ── Test 4: Empty document ─────────────────────────────────────────────────

\echo ''
\echo '=== TEST 4: INSERT empty document ==='

INSERT INTO test_drafts (chapter_id, body) VALUES (
  '00000000-0000-0000-0000-000000000002',
  '{"type": "doc", "content": []}'::jsonb
);

SELECT count(*) AS block_count FROM test_blocks
WHERE chapter_id = '00000000-0000-0000-0000-000000000002';

-- Expected: 0

-- ── Test 5: HorizontalRule (no _text) ──────────────────────────────────────

\echo ''
\echo '=== TEST 5: INSERT with horizontalRule (missing _text) ==='

INSERT INTO test_drafts (chapter_id, body) VALUES (
  '00000000-0000-0000-0000-000000000003',
  '{"type": "doc", "content": [
    {"type": "paragraph", "_text": "Before"},
    {"type": "horizontalRule"},
    {"type": "paragraph", "_text": "After"}
  ]}'::jsonb
);

SELECT block_index, block_type, text_content
FROM test_blocks
WHERE chapter_id = '00000000-0000-0000-0000-000000000003'
ORDER BY block_index;

-- Expected: 3 rows, horizontalRule has text_content = ''

-- ── Test 6: Unicode (CJK + emoji) ──────────────────────────────────────────

\echo ''
\echo '=== TEST 6: Unicode text ==='

INSERT INTO test_drafts (chapter_id, body) VALUES (
  '00000000-0000-0000-0000-000000000004',
  '{"type": "doc", "content": [
    {"type": "paragraph", "_text": "Xin chào thế giới 🌍"},
    {"type": "paragraph", "_text": "你好世界"},
    {"type": "paragraph", "_text": "こんにちは世界"}
  ]}'::jsonb
);

SELECT block_index, text_content
FROM test_blocks
WHERE chapter_id = '00000000-0000-0000-0000-000000000004'
ORDER BY block_index;

-- Expected: 3 rows with correct Unicode preserved

-- ── Test 7: CASCADE delete ─────────────────────────────────────────────────

\echo ''
\echo '=== TEST 7: CASCADE delete — remove draft, blocks follow ==='

DELETE FROM test_drafts WHERE chapter_id = '00000000-0000-0000-0000-000000000001';

SELECT count(*) AS remaining_blocks FROM test_blocks
WHERE chapter_id = '00000000-0000-0000-0000-000000000001';

-- Expected: 0

-- ── Cleanup ────────────────────────────────────────────────────────────────

\echo ''
\echo '=== CLEANUP ==='
DROP TABLE test_blocks CASCADE;
DROP TABLE test_drafts CASCADE;
DROP FUNCTION fn_test_extract_blocks;

\echo ''
\echo '=== ALL TESTS COMPLETE ==='
