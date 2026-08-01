package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// entityKindVotesSQL -- chain step 0058. The observation ledger + the kind hierarchy.
// Spec: docs/specs/2026-08-02-entity-kind-resolution.md
//
// An entity's kind was decided by whichever extraction batch named it FIRST and never
// revisited: findEntityCrossKind is oldest-wins and returns the STORED kind, so every later
// answer was discarded silently. Measured on 封神演義: 173 of 1,531 stored entities (11%) hold
// a kind the model disagrees with by majority, including the protagonist -- 64 observations
// calling him a character against 20 calling him a species, stored as `species` because the
// species answer arrived at 07:56 on the first run this book ever had.
//
// So the store answered a question the model answered 84 times by keeping the first draw.
//
// `glossary_entities.kind_id` STAYS a single non-null FK -- it is read by ~470 sites in this
// service, mirrored as a NOT NULL scalar in knowledge-service and projected into Neo4j. It
// simply stops being frozen: it becomes the argmax over this ledger (domain.ResolveKind).
//
// Tenancy: entity_id scopes to a book and kind_id to book_kinds, both already book-scoped, so
// the table inherits the scope key and opens no new tenancy surface.
const entityKindVotesSQL = `
CREATE TABLE IF NOT EXISTS entity_kind_votes (
  entity_id  UUID NOT NULL REFERENCES glossary_entities(entity_id) ON DELETE CASCADE,
  kind_id    UUID NOT NULL REFERENCES book_kinds(book_kind_id) ON DELETE CASCADE,
  votes      INT  NOT NULL DEFAULT 0,
  first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (entity_id, kind_id)
);

-- The challenger that LED but failed the switch threshold. Recorded rather than dropped: the
-- writeback reported updated and never conflict, so a persistent model-vs-store
-- disagreement was invisible for as long as it persisted. NULL = no live disagreement.
ALTER TABLE glossary_entities ADD COLUMN IF NOT EXISTS kind_conflict_id UUID;

-- The secondary readings (facets), as a CACHE of what ResolveKind derived. Denormalised on
-- purpose: a list endpoint would otherwise re-resolve every row it returns. 西岐 is an
-- organization 52 times and a location 38 -- both true, and erasing one is the lossy
-- behaviour multi-label exists to end.
ALTER TABLE glossary_entities ADD COLUMN IF NOT EXISTS kind_labels UUID[] NOT NULL DEFAULT '{}';

-- The hierarchy, per tier, self-referencing within its own tier (a book kind's parent is a
-- book kind, so the copy-down stays book-local and no cross-tier FK is introduced).
ALTER TABLE system_kinds ADD COLUMN IF NOT EXISTS parent_kind_id UUID REFERENCES system_kinds(kind_id) ON DELETE SET NULL;
ALTER TABLE user_kinds   ADD COLUMN IF NOT EXISTS parent_kind_id UUID REFERENCES user_kinds(user_kind_id) ON DELETE SET NULL;
ALTER TABLE book_kinds   ADD COLUMN IF NOT EXISTS parent_kind_id UUID REFERENCES book_kinds(book_kind_id) ON DELETE SET NULL;

-- The declared hierarchy, which DESCRIBES what the model already does rather than inventing a
-- taxonomy: terminology collected 崑崙之妙術, 土遁, 五行方位 and 八九變化 because it was the
-- nearest generic home for a named concept. Making that official is what lets a later, more
-- specific answer REFINE the earlier one instead of contradicting it -- and a refinement needs
-- no majority, which is the only way a corrected ontology can ever correct the data the wrong
-- one produced.
UPDATE system_kinds c SET parent_kind_id = p.kind_id
FROM system_kinds p
WHERE p.code = 'terminology' AND c.code IN ('technique', 'power_system')
  AND c.parent_kind_id IS NULL;

-- Books that already adopted these kinds get the same link, book-locally, by code.
UPDATE book_kinds c SET parent_kind_id = p.book_kind_id
FROM book_kinds p
WHERE p.book_id = c.book_id AND p.code = 'terminology'
  AND c.code IN ('technique', 'power_system')
  AND c.parent_kind_id IS NULL;
`

// UpEntityKindVotes creates the kind-vote ledger, the conflict/label columns, and the kind
// hierarchy. Idempotent; chain step 0058.
func UpEntityKindVotes(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "entity-kind-votes", entityKindVotesSQL)
}
