package api

// S6 — per-language aliases, end-to-end at the BE: an entity given an English alias set
// via glossary_propose_aliases becomes resolvable BY that English name through the
// extraction dedup resolver (findEntityByNameOrAlias Step 3), even though its source name
// is Chinese. This is the cross-language anti-resurrection payoff. Requires
// GLOSSARY_TEST_DB_URL.

import (
	"context"
	"testing"

	"github.com/google/uuid"
)

func TestPerLanguageAliases_ResolverCrossLanguage(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	octx := ctxWithUser(f.ownerID)

	charKind := bookKindID(t, pool, f.bookID, "character")
	nameAttr := bookAttrID(t, pool, f.bookID, charKind, "name")

	var eid uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, short_description) VALUES($1,$2,'demon') RETURNING entity_id`,
		f.bookID, charKind).Scan(&eid); err != nil {
		t.Fatalf("seed entity: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id=$1`, eid) }) //nolint:errcheck
	if _, err := pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id, attr_def_id, original_language, original_value)
		 VALUES($1,$2,'zh','焰魔')`, eid, nameAttr); err != nil {
		t.Fatalf("seed name: %v", err)
	}

	// Before: the English name does NOT resolve.
	if got, err := f.srv.findEntityByNameOrAlias(ctx, f.srv.pool, f.bookID, charKind, "Flame Demon", ""); err != nil || got != uuid.Nil {
		t.Fatalf("pre: 'Flame Demon' must not resolve yet (got %v, err %v)", got, err)
	}

	// Propose an English alias set for the entity.
	if _, out, err := f.srv.toolProposeAliases(octx, nil, proposeAliasesToolIn{
		BookID: f.bookID.String(), LanguageCode: "en",
		Items: []aliasItem{{EntityID: eid.String(), Aliases: []string{"Flame Demon", "Yan Mo"}}},
	}); err != nil || out.Written != 1 {
		t.Fatalf("propose aliases: %+v err=%v", out, err)
	}

	// After: the English alias resolves to the entity (Step 3 cross-language match).
	if got, err := f.srv.findEntityByNameOrAlias(ctx, f.srv.pool, f.bookID, charKind, "Flame Demon", ""); err != nil || got != eid {
		t.Errorf("'Flame Demon' must resolve to the entity via its en alias set (got %v want %v, err %v)", got, eid, err)
	}
	if got, _ := f.srv.findEntityByNameOrAlias(ctx, f.srv.pool, f.bookID, charKind, "Yan Mo", ""); got != eid {
		t.Errorf("'Yan Mo' must resolve via the en alias set (got %v)", got)
	}
	// The source-language name still resolves (Step 1 unchanged).
	if got, _ := f.srv.findEntityByNameOrAlias(ctx, f.srv.pool, f.bookID, charKind, "焰魔", ""); got != eid {
		t.Errorf("source name must still resolve (got %v)", got)
	}
	// A genuinely unknown name still misses.
	if got, _ := f.srv.findEntityByNameOrAlias(ctx, f.srv.pool, f.bookID, charKind, "Nobody", ""); got != uuid.Nil {
		t.Errorf("an unknown name must not resolve (got %v)", got)
	}
}

// /review-impl S6 #1 — the resolver excludes SOFT-DELETED entities across all 3 steps
// (name, source aliases, per-language aliases). A deleted row must never be a resolution
// target (anti-resurrection: a merged-away loser must not capture an incoming name).
func TestPerLanguageAliases_ResolverExcludesDeleted(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	octx := ctxWithUser(f.ownerID)

	charKind := bookKindID(t, pool, f.bookID, "character")
	nameAttr := bookAttrID(t, pool, f.bookID, charKind, "name")

	// A soft-deleted entity named "幽灵" with an en alias "Ghost".
	var dead uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, short_description, deleted_at)
		 VALUES($1,$2,'gone', now()) RETURNING entity_id`, f.bookID, charKind).Scan(&dead); err != nil {
		t.Fatalf("seed deleted entity: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id=$1`, dead) }) //nolint:errcheck
	if _, err := pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id, attr_def_id, original_language, original_value)
		 VALUES($1,$2,'zh','幽灵')`, dead, nameAttr); err != nil {
		t.Fatalf("seed name: %v", err)
	}
	// Author an en alias on it (resolveOrCreate works regardless of deleted state).
	if _, _, err := f.srv.toolProposeAliases(octx, nil, proposeAliasesToolIn{
		BookID: f.bookID.String(), LanguageCode: "en", Items: []aliasItem{{EntityID: dead.String(), Aliases: []string{"Ghost"}}},
	}); err != nil {
		t.Fatalf("propose aliases on deleted: %v", err)
	}

	// None of the three steps resolve to the deleted entity.
	if got, _ := f.srv.findEntityByNameOrAlias(ctx, f.srv.pool, f.bookID, charKind, "幽灵", ""); got != uuid.Nil {
		t.Errorf("Step 1: a deleted entity's name must not resolve (got %v)", got)
	}
	if got, _ := f.srv.findEntityByNameOrAlias(ctx, f.srv.pool, f.bookID, charKind, "Ghost", ""); got != uuid.Nil {
		t.Errorf("Step 3: a deleted entity's per-language alias must not resolve (got %v)", got)
	}
}

// /review-impl S6 #4 — the resolve (not create) branch + no-duplicate-row guard: an
// entity that ALREADY has a source aliases value gets its per-language translation attached
// to the SAME row (resolveOrCreateEntityAliasesValue resolves, never creates a second row).
func TestPerLanguageAliases_ResolveExistingNoDuplicate(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	octx := ctxWithUser(f.ownerID)

	charKind := bookKindID(t, pool, f.bookID, "character")
	aliasAttr := bookAttrID(t, pool, f.bookID, charKind, "aliases")
	var eid uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, short_description) VALUES($1,$2,'has-aliases') RETURNING entity_id`,
		f.bookID, charKind).Scan(&eid); err != nil {
		t.Fatalf("seed entity: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id=$1`, eid) }) //nolint:errcheck
	// Pre-existing SOURCE aliases value (the resolve branch, not create).
	if _, err := pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id, attr_def_id, original_language, original_value)
		 VALUES($1,$2,'zh','["源一","源二"]')`, eid, aliasAttr); err != nil {
		t.Fatalf("seed source aliases: %v", err)
	}

	if _, out, err := f.srv.toolProposeAliases(octx, nil, proposeAliasesToolIn{
		BookID: f.bookID.String(), LanguageCode: "en", Items: []aliasItem{{EntityID: eid.String(), Aliases: []string{"Src One"}}},
	}); err != nil || out.Written != 1 {
		t.Fatalf("propose: %+v err=%v", out, err)
	}

	// Exactly ONE aliases EAV row (resolved the existing one, did not create a second).
	var rowCount int
	pool.QueryRow(ctx, `
		SELECT count(*) FROM entity_attribute_values av
		JOIN book_attributes ba ON ba.attr_id = av.attr_def_id
		WHERE av.entity_id=$1 AND ba.code='aliases'`, eid).Scan(&rowCount)
	if rowCount != 1 {
		t.Errorf("want exactly 1 aliases EAV row (resolved), got %d", rowCount)
	}
	// The source value is untouched; the en translation attached to it.
	var src, enVal string
	pool.QueryRow(ctx, `SELECT original_value FROM entity_attribute_values WHERE entity_id=$1 AND attr_def_id=$2`, eid, aliasAttr).Scan(&src)
	pool.QueryRow(ctx, `
		SELECT t.value FROM attribute_translations t
		WHERE t.attr_value_id=(SELECT attr_value_id FROM entity_attribute_values WHERE entity_id=$1 AND attr_def_id=$2)
		  AND t.language_code='en'`, eid, aliasAttr).Scan(&enVal)
	if src != `["源一","源二"]` {
		t.Errorf("source aliases mutated: %q", src)
	}
	if enVal != `["Src One"]` {
		t.Errorf("en translation not attached to the existing row: %q", enVal)
	}
}

func TestPerLanguageAliases_ContextComposition(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	octx := ctxWithUser(f.ownerID)

	charKind := bookKindID(t, pool, f.bookID, "character")
	var eid uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, short_description) VALUES($1,$2,'ctx') RETURNING entity_id`,
		f.bookID, charKind).Scan(&eid); err != nil {
		t.Fatalf("seed entity: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id=$1`, eid) }) //nolint:errcheck

	// Give it an English alias set that OVERLAPS the source ("源别名" appears in both) so
	// the compose-dedup is exercised, plus a unique en entry.
	if _, out, err := f.srv.toolProposeAliases(octx, nil, proposeAliasesToolIn{
		BookID: f.bookID.String(), LanguageCode: "en",
		Items: []aliasItem{{EntityID: eid.String(), Aliases: []string{"Flame Demon", "源别名"}}},
	}); err != nil || out.Written != 1 {
		t.Fatalf("propose aliases: %+v err=%v", out, err)
	}

	items := []glossaryEntityForContext{{EntityID: eid.String(), CachedAliases: []string{"源别名"}}}

	// language="" → unchanged (back-compat).
	f.srv.composePerLanguageAliases(ctx, f.bookID, items, "")
	if len(items[0].CachedAliases) != 1 {
		t.Errorf("no language must leave aliases untouched: %v", items[0].CachedAliases)
	}

	// language="en" → source ∪ en alias set, DEDUPED (the overlapping "源别名" appears once).
	f.srv.composePerLanguageAliases(ctx, f.bookID, items, "en")
	counts := map[string]int{}
	for _, a := range items[0].CachedAliases {
		counts[a]++
	}
	if !(counts["源别名"] == 1 && counts["Flame Demon"] == 1) {
		t.Errorf("composed aliases must be source ∪ en, deduped: %v", items[0].CachedAliases)
	}
}
