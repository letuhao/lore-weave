package migrate

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/loreweave/glossary-service/internal/domain"
)

// SeedGenreKindLinks applies curated system genre-kind defaults to the system catalogue and existing books.
func SeedGenreKindLinks(ctx context.Context, pool *pgxpool.Pool) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("seed genre-kind links: begin: %w", err)
	}
	defer tx.Rollback(ctx)

	for _, k := range domain.DefaultKinds {
		for _, genre := range k.GenreTags {
			if _, err := tx.Exec(ctx, "INSERT INTO system_kind_genres (kind_id, genre_id) SELECT sk.kind_id, sg.genre_id FROM system_kinds sk JOIN system_genres sg ON sg.code = $2 WHERE sk.code = $1 ON CONFLICT DO NOTHING", k.Code, genre); err != nil {
				return fmt.Errorf("seed system link %s/%s: %w", k.Code, genre, err)
			}
		}
	}
	if _, err := tx.Exec(ctx, "INSERT INTO book_kind_genres (book_id, kind_id, genre_id) SELECT bk.book_id, bk.book_kind_id, bg.genre_id FROM system_kind_genres skg JOIN system_kinds sk ON sk.kind_id = skg.kind_id AND sk.is_default JOIN system_genres sg ON sg.genre_id = skg.genre_id AND sg.is_default JOIN book_kinds bk ON bk.code = sk.code JOIN book_genres bg ON bg.book_id = bk.book_id AND bg.code = sg.code ON CONFLICT DO NOTHING"); err != nil {
		return fmt.Errorf("seed book genre-kind links: %w", err)
	}
	return tx.Commit(ctx)
}

// SeedGenreKindAttributes propagates GENRE-SPECIFIC system attributes to already-adopted
// book ontologies.
//
// It also copied every UNIVERSAL attribute definition onto every genre linked to a kind,
// and that statement is removed. Universal attributes already reach an entity through the
// universal genre — `book_active_genres` includes it, and the create handler seeds one
// attribute value per (genre, code) over the entity's whole genre set — so the copy added
// nothing an entity could not already see, and multiplied every identity field by the
// genre count. A `character` in a six-genre book had SEVEN `name` attributes, all with
// sort_order 1.
//
// Two of this repo's own tests, green since June and untouched since, went red on it:
//
//   - TestCreateEntity_HonoursTheFieldsItsContractDocuments — POST /entities writes
//     display_name to the universal `name` row, while `recalculate_entity_snapshot`
//     picked one of the seven arbitrarily. The name was stored correctly and
//     `cached_name` still came back empty, which is what every downstream reader joins
//     on. (That ORDER BY was non-deterministic on its own merits and is now a total
//     order — a separate fix, and the right one whatever this seed does.)
//   - TestF1SystemAttrDesc_PropagatesThroughAdoptAndSync — sync/apply reconciles ONE
//     attribute row, so `take_theirs` on `aliases` left six identical siblings still
//     reporting update_available. The reconciliation was correct; there were just six
//     more rows than the model has ever had.
//
// The genre→book propagation below is kept: that is the part that does something the
// universal genre cannot, and it already excludes the universal genre explicitly.
func SeedGenreKindAttributes(ctx context.Context, pool *pgxpool.Pool) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("seed genre-kind attributes: begin: %w", err)
	}
	defer tx.Rollback(ctx)
	if _, err := tx.Exec(ctx, "INSERT INTO book_attributes (book_id, kind_id, genre_id, code, name, description, field_type, is_required, sort_order, options, auto_fill_prompt, translation_hint, source_ref, source_hash, merge_strategy) SELECT bk.book_id, bk.book_kind_id, bg.genre_id, sa.code, sa.name, sa.description, sa.field_type, sa.is_required, sa.sort_order, sa.options, sa.auto_fill_prompt, sa.translation_hint, 'system:' || sa.attr_id::text, sa.content_hash, sa.merge_strategy FROM system_attributes sa JOIN system_kinds sk ON sk.kind_id = sa.kind_id AND sk.is_default JOIN system_genres sg ON sg.genre_id = sa.genre_id AND sg.is_default JOIN book_kinds bk ON bk.code = sk.code JOIN book_genres bg ON bg.book_id = bk.book_id AND bg.code = sg.code WHERE sa.genre_id <> (SELECT genre_id FROM system_genres WHERE code = 'universal') AND NOT EXISTS (SELECT 1 FROM book_attributes ba WHERE ba.book_id = bk.book_id AND ba.kind_id = bk.book_kind_id AND ba.genre_id = bg.genre_id AND ba.code = sa.code)"); err != nil {
		return fmt.Errorf("seed book genre attributes: %w", err)
	}
	return tx.Commit(ctx)
}
