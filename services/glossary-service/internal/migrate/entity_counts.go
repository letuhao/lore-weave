package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// entityCountsSQL denormalizes the per-entity appearance counters so the glossary
// list can SORT by them cheaply (D-GLOSSARY-SORT-BE counts-sort, deferred from M1).
//
// Why columns + triggers: chapter_link_count / evidence_count are correlated
// subqueries in the list projection (per page row — fine for display), but
// ORDER BY them would compute the count for EVERY matching row at 20K scale.
// Denormalized counters maintained by dedicated AFTER triggers make the sort an
// indexed column read.
//
// The counters are maintained by their OWN small triggers (not folded into
// recalculate_entity_snapshot) so this migration doesn't have to copy that
// 150-line function — the existing trig_cel_snapshot / trig_evid_snapshot still
// fire recalculate for the snapshot; these add a tiny COUNT-write alongside.
// The count-write UPDATEs only `cached_*_count`, which is NOT on the
// trig_entity_self_snapshot watch list, so they never re-trigger a snapshot
// rebuild (no recursion).
const entityCountsSQL = `
ALTER TABLE glossary_entities
  ADD COLUMN IF NOT EXISTS cached_chapter_link_count INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cached_evidence_count     INT NOT NULL DEFAULT 0;

-- chapter-link count: chapter_entity_links.entity_id → glossary_entities.
CREATE OR REPLACE FUNCTION trig_fn_entity_link_count()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_eid UUID;
BEGIN
  v_eid := CASE WHEN TG_OP = 'DELETE' THEN OLD.entity_id ELSE NEW.entity_id END;
  UPDATE glossary_entities
     SET cached_chapter_link_count =
         (SELECT COUNT(*) FROM chapter_entity_links WHERE entity_id = v_eid)
   WHERE entity_id = v_eid;
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trig_entity_link_count ON chapter_entity_links;
CREATE TRIGGER trig_entity_link_count
  AFTER INSERT OR UPDATE OR DELETE ON chapter_entity_links
  FOR EACH ROW EXECUTE FUNCTION trig_fn_entity_link_count();

-- evidence count: evidences.attr_value_id → entity_attribute_values.entity_id.
CREATE OR REPLACE FUNCTION trig_fn_entity_evidence_count()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_eid UUID;
BEGIN
  SELECT entity_id INTO v_eid
    FROM entity_attribute_values
   WHERE attr_value_id = CASE WHEN TG_OP = 'DELETE' THEN OLD.attr_value_id ELSE NEW.attr_value_id END;
  IF v_eid IS NOT NULL THEN
    UPDATE glossary_entities
       SET cached_evidence_count =
           (SELECT COUNT(*) FROM evidences ev
              JOIN entity_attribute_values eav ON eav.attr_value_id = ev.attr_value_id
             WHERE eav.entity_id = v_eid)
     WHERE entity_id = v_eid;
  END IF;
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trig_entity_evidence_count ON evidences;
CREATE TRIGGER trig_entity_evidence_count
  AFTER INSERT OR UPDATE OR DELETE ON evidences
  FOR EACH ROW EXECUTE FUNCTION trig_fn_entity_evidence_count();

-- Book-scoped DESC indexes so "most-appearing first" is an index read.
CREATE INDEX IF NOT EXISTS idx_ge_book_chlink_count
  ON glossary_entities (book_id, cached_chapter_link_count DESC)
  WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_ge_book_evidence_count
  ON glossary_entities (book_id, cached_evidence_count DESC)
  WHERE deleted_at IS NULL;

-- Backfill existing rows (one-time; the triggers keep them fresh thereafter).
UPDATE glossary_entities e SET
  cached_chapter_link_count =
    (SELECT COUNT(*) FROM chapter_entity_links WHERE entity_id = e.entity_id),
  cached_evidence_count =
    (SELECT COUNT(*) FROM evidences ev
       JOIN entity_attribute_values eav ON eav.attr_value_id = ev.attr_value_id
      WHERE eav.entity_id = e.entity_id);
`

// UpEntityCounts adds the denormalized appearance counters + their maintenance
// triggers + sort indexes + a one-time backfill. Idempotent. Runs through
// execGuarded (shares the migration advisory lock — see entity_search.go).
func UpEntityCounts(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "entity-counts", entityCountsSQL)
}
