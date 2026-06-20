package api

// Pipeline M4 — glossary_propose_translation (class-W). Proves: Edit-gated, batch
// per-entity results, writes a DRAFT translation on the entity's name, NEVER overwrites
// a verified one, and skips entities not in the book / without a name. Requires
// GLOSSARY_TEST_DB_URL.

import (
	"context"
	"testing"

	"github.com/google/uuid"
)

func TestPipelineTranslateTool_Guards(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	octx := ctxWithUser(f.ownerID)

	charKind := bookKindID(t, pool, f.bookID, "character")
	nameAttr := bookAttrID(t, pool, f.bookID, charKind, "name")

	seedNamed := func(name string) uuid.UUID {
		var eid uuid.UUID
		if err := pool.QueryRow(ctx,
			`INSERT INTO glossary_entities(book_id, kind_id, short_description) VALUES($1,$2,'tr') RETURNING entity_id`,
			f.bookID, charKind).Scan(&eid); err != nil {
			t.Fatalf("seed entity: %v", err)
		}
		t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id=$1`, eid) }) //nolint:errcheck
		if _, err := pool.Exec(ctx,
			`INSERT INTO entity_attribute_values(entity_id, attr_def_id, original_language, original_value)
			 VALUES($1,$2,'zh',$3)`, eid, nameAttr, name); err != nil {
			t.Fatalf("seed name value: %v", err)
		}
		return eid
	}

	withName := seedNamed("姜子牙")

	// an entity with NO name attribute value
	var noName uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, short_description) VALUES($1,$2,'noname') RETURNING entity_id`,
		f.bookID, charKind).Scan(&noName); err != nil {
		t.Fatalf("seed noname: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id=$1`, noName) }) //nolint:errcheck

	book := f.bookID.String()

	// grant gate — a non-grantee is denied
	if _, _, err := f.srv.toolProposeTranslation(ctxWithUser(uuid.New()), nil,
		proposeTranslationToolIn{BookID: book, LanguageCode: "en", Items: []translateItem{{EntityID: withName.String(), Value: "Jiang Ziya"}}}); err == nil {
		t.Error("non-grantee must be denied")
	}
	// empty items rejected
	if _, _, err := f.srv.toolProposeTranslation(octx, nil,
		proposeTranslationToolIn{BookID: book, LanguageCode: "en"}); err == nil {
		t.Error("empty items must error")
	}
	// missing language rejected
	if _, _, err := f.srv.toolProposeTranslation(octx, nil,
		proposeTranslationToolIn{BookID: book, Items: []translateItem{{EntityID: withName.String(), Value: "x"}}}); err == nil {
		t.Error("missing language_code must error")
	}

	// happy path — writes a draft translation; skips the no-name + not-in-book entities
	_, out, err := f.srv.toolProposeTranslation(octx, nil, proposeTranslationToolIn{
		BookID: book, LanguageCode: "en",
		Items: []translateItem{
			{EntityID: withName.String(), Value: "Jiang Ziya"},
			{EntityID: noName.String(), Value: "Nameless"},
			{EntityID: uuid.NewString(), Value: "Ghost"},
		},
	})
	if err != nil {
		t.Fatalf("happy path: %v", err)
	}
	if out.Written != 1 || out.Skipped != 2 {
		t.Errorf("want written=1 skipped=2, got written=%d skipped=%d (%+v)", out.Written, out.Skipped, out.Results)
	}
	var got string
	pool.QueryRow(ctx, `
		SELECT t.value FROM attribute_translations t
		JOIN entity_attribute_values av ON av.attr_value_id = t.attr_value_id
		WHERE av.entity_id=$1 AND t.language_code='en'`, withName).Scan(&got)
	if got != "Jiang Ziya" {
		t.Errorf("draft translation not written: %q", got)
	}

	// re-propose updates the draft (upsert)
	if _, out2, err := f.srv.toolProposeTranslation(octx, nil, proposeTranslationToolIn{
		BookID: book, LanguageCode: "en", Items: []translateItem{{EntityID: withName.String(), Value: "Jiang Zi-Ya"}},
	}); err != nil || out2.Written != 1 {
		t.Errorf("re-propose should update the draft: %+v err=%v", out2, err)
	}

	// verified-protection — promote to verified, then a propose is SKIPPED + unchanged
	if _, err := pool.Exec(ctx, `
		UPDATE attribute_translations SET confidence='verified'
		WHERE attr_value_id=(SELECT attr_value_id FROM entity_attribute_values WHERE entity_id=$1 AND attr_def_id=$2)
		  AND language_code='en'`, withName, nameAttr); err != nil {
		t.Fatalf("promote verified: %v", err)
	}
	_, out3, err := f.srv.toolProposeTranslation(octx, nil, proposeTranslationToolIn{
		BookID: book, LanguageCode: "en", Items: []translateItem{{EntityID: withName.String(), Value: "OVERWRITE ATTEMPT"}},
	})
	if err != nil {
		t.Fatalf("verified-protection call: %v", err)
	}
	if out3.Written != 0 || out3.Skipped != 1 {
		t.Errorf("verified must be protected: written=%d skipped=%d", out3.Written, out3.Skipped)
	}
	var afterVerified string
	pool.QueryRow(ctx, `
		SELECT t.value FROM attribute_translations t
		JOIN entity_attribute_values av ON av.attr_value_id = t.attr_value_id
		WHERE av.entity_id=$1 AND t.language_code='en'`, withName).Scan(&afterVerified)
	if afterVerified == "OVERWRITE ATTEMPT" {
		t.Error("a verified translation was overwritten")
	}
}

func TestPipelineProposeAliases_Guards(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	octx := ctxWithUser(f.ownerID)

	charKind := bookKindID(t, pool, f.bookID, "character")
	// an entity with NO pre-existing aliases value row (exercises resolve-or-create)
	var eid uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, short_description) VALUES($1,$2,'al') RETURNING entity_id`,
		f.bookID, charKind).Scan(&eid); err != nil {
		t.Fatalf("seed entity: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id=$1`, eid) }) //nolint:errcheck

	book := f.bookID.String()

	// grant gate
	if _, _, err := f.srv.toolProposeAliases(ctxWithUser(uuid.New()), nil,
		proposeAliasesToolIn{BookID: book, LanguageCode: "en", Items: []aliasItem{{EntityID: eid.String(), Aliases: []string{"X"}}}}); err == nil {
		t.Error("non-grantee must be denied")
	}
	// empty items
	if _, _, err := f.srv.toolProposeAliases(octx, nil,
		proposeAliasesToolIn{BookID: book, LanguageCode: "en"}); err == nil {
		t.Error("empty items must error")
	}

	// happy path — resolve-or-create the aliases value, write a JSON-array draft
	_, out, err := f.srv.toolProposeAliases(octx, nil, proposeAliasesToolIn{
		BookID: book, LanguageCode: "en",
		Items: []aliasItem{
			{EntityID: eid.String(), Aliases: []string{"Jiang Ziya", "Jiang Shang", "", "Jiang Ziya"}}, // dup + empty cleaned
			{EntityID: uuid.NewString(), Aliases: []string{"Ghost"}},                                   // not in book → skip
		},
	})
	if err != nil {
		t.Fatalf("happy path: %v", err)
	}
	if out.Written != 1 || out.Skipped != 1 {
		t.Errorf("want written=1 skipped=1, got %+v", out)
	}
	var got string
	pool.QueryRow(ctx, `
		SELECT t.value FROM attribute_translations t
		JOIN entity_attribute_values av ON av.attr_value_id = t.attr_value_id
		JOIN book_attributes ba ON ba.attr_id = av.attr_def_id
		WHERE av.entity_id=$1 AND ba.code='aliases' AND t.language_code='en'`, eid).Scan(&got)
	if got != `["Jiang Ziya","Jiang Shang"]` {
		t.Errorf("alias-set not written as a deduped JSON array: %q", got)
	}

	// re-propose updates the draft set
	if _, out2, err := f.srv.toolProposeAliases(octx, nil, proposeAliasesToolIn{
		BookID: book, LanguageCode: "en", Items: []aliasItem{{EntityID: eid.String(), Aliases: []string{"Jiang Zi-Ya"}}},
	}); err != nil || out2.Written != 1 {
		t.Errorf("re-propose should update the draft set: %+v err=%v", out2, err)
	}

	// verified-protection
	if _, err := pool.Exec(ctx, `
		UPDATE attribute_translations SET confidence='verified'
		WHERE attr_value_id IN (
			SELECT av.attr_value_id FROM entity_attribute_values av
			JOIN book_attributes ba ON ba.attr_id = av.attr_def_id
			WHERE av.entity_id=$1 AND ba.code='aliases')
		  AND language_code='en'`, eid); err != nil {
		t.Fatalf("promote verified: %v", err)
	}
	_, out3, err := f.srv.toolProposeAliases(octx, nil, proposeAliasesToolIn{
		BookID: book, LanguageCode: "en", Items: []aliasItem{{EntityID: eid.String(), Aliases: []string{"OVERWRITE"}}},
	})
	if err != nil {
		t.Fatalf("verified-protection call: %v", err)
	}
	if out3.Written != 0 || out3.Skipped != 1 {
		t.Errorf("verified alias set must be protected: %+v", out3)
	}
}
