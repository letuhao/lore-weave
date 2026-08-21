package api

import (
	"context"

	"github.com/google/uuid"
)

// ensureDefaultBookOntology makes a book usable even when an older/imported book
// has no book-tier ontology yet. It copies only system rows marked is_default;
// ON CONFLICT keeps existing book customizations intact.
func (s *Server) ensureDefaultBookOntology(ctx context.Context, bookID uuid.UUID) error {
	if s.pool == nil {
		return nil
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext('gloss-defaults:' || $1::text))`, bookID); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO book_genres (book_id, code, name, icon, color, sort_order, source_ref, source_hash)
		SELECT $1, sg.code, sg.name, sg.icon, sg.color, sg.sort_order, 'system:' || sg.genre_id::text, sg.content_hash
		FROM system_genres sg WHERE sg.is_default AND sg.deprecated_at IS NULL
		ON CONFLICT (book_id, code) DO NOTHING`, bookID); err != nil {
		return err
	}
	// ONLY when the book has no active-genre rows at all.
	//
	// `ON CONFLICT DO NOTHING` protects a row that EXISTS. It cannot protect a row the
	// user deliberately REMOVED, because "this genre is off" is expressed here as the
	// absence of a row — indistinguishable from "never set up". So this statement,
	// reached from `loadBookOntology` on every GET /ontology, re-activated every default
	// genre on every read: PUT /ontology/active-genres with universal+faction returned
	// 200, and the next page load brought xianxia back. A read path silently undoing a
	// write, and the user's setting could not be made to stick by any number of retries.
	//
	// The NOT EXISTS restores what this function's own doc says it is for — making a
	// book with NO book-tier ontology usable. Topping up a book that already has one is
	// safe for catalogue rows (a genre/kind/attribute the user has not got yet), and is
	// exactly wrong for a user's on/off choice.
	if _, err := tx.Exec(ctx, `
		INSERT INTO book_active_genres (book_id, genre_id)
		SELECT $1, bg.genre_id FROM book_genres bg JOIN system_genres sg ON sg.code = bg.code
		WHERE bg.book_id = $1 AND sg.is_default AND sg.deprecated_at IS NULL
		  AND NOT EXISTS (SELECT 1 FROM book_active_genres bag WHERE bag.book_id = $1)
		ON CONFLICT DO NOTHING`, bookID); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO book_kinds (book_id, code, name, description, icon, color, sort_order, is_hidden, is_person, source_ref, source_hash)
		SELECT $1, sk.code, sk.name, sk.description, sk.icon, sk.color, sk.sort_order, sk.is_hidden, sk.is_person,
		       'system:' || sk.kind_id::text, md5(sk.code || '|' || sk.name || '|' || coalesce(sk.description, ''))
		FROM system_kinds sk WHERE sk.is_default AND sk.deprecated_at IS NULL
		ON CONFLICT (book_id, code) DO NOTHING`, bookID); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO book_kind_genres (book_id, kind_id, genre_id)
		SELECT $1, bk.book_kind_id, bg.genre_id FROM system_kind_genres skg
		JOIN system_kinds sk ON sk.kind_id = skg.kind_id JOIN system_genres sg ON sg.genre_id = skg.genre_id
		JOIN book_kinds bk ON bk.book_id = $1 AND bk.code = sk.code JOIN book_genres bg ON bg.book_id = $1 AND bg.code = sg.code
		WHERE sk.is_default AND sg.is_default ON CONFLICT DO NOTHING`, bookID); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO book_attributes (book_id, kind_id, genre_id, code, name, description, field_type, is_required, sort_order, options, auto_fill_prompt, translation_hint, source_ref, source_hash, merge_strategy)
		SELECT $1, bk.book_kind_id, bg.genre_id, sa.code, sa.name, sa.description, sa.field_type, sa.is_required, sa.sort_order, sa.options, sa.auto_fill_prompt, sa.translation_hint,
		       'system:' || sa.attr_id::text, sa.content_hash, sa.merge_strategy
		FROM system_attributes sa JOIN system_kinds sk ON sk.kind_id = sa.kind_id JOIN system_genres sg ON sg.genre_id = sa.genre_id
		JOIN book_kinds bk ON bk.book_id = $1 AND bk.code = sk.code JOIN book_genres bg ON bg.book_id = $1 AND bg.code = sg.code
		WHERE sk.is_default AND sg.is_default AND sa.deprecated_at IS NULL ON CONFLICT (book_id, kind_id, genre_id, code) DO NOTHING`, bookID); err != nil {
		return err
	}
	return tx.Commit(ctx)
}
