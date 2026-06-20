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
	if got, err := f.srv.findEntityByNameOrAlias(ctx, f.bookID, charKind, "Flame Demon"); err != nil || got != uuid.Nil {
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
	if got, err := f.srv.findEntityByNameOrAlias(ctx, f.bookID, charKind, "Flame Demon"); err != nil || got != eid {
		t.Errorf("'Flame Demon' must resolve to the entity via its en alias set (got %v want %v, err %v)", got, eid, err)
	}
	if got, _ := f.srv.findEntityByNameOrAlias(ctx, f.bookID, charKind, "Yan Mo"); got != eid {
		t.Errorf("'Yan Mo' must resolve via the en alias set (got %v)", got)
	}
	// The source-language name still resolves (Step 1 unchanged).
	if got, _ := f.srv.findEntityByNameOrAlias(ctx, f.bookID, charKind, "焰魔"); got != eid {
		t.Errorf("source name must still resolve (got %v)", got)
	}
	// A genuinely unknown name still misses.
	if got, _ := f.srv.findEntityByNameOrAlias(ctx, f.bookID, charKind, "Nobody"); got != uuid.Nil {
		t.Errorf("an unknown name must not resolve (got %v)", got)
	}
}
