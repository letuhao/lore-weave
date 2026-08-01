package api

// D-GLOSS-CREATE-DROPS-DOCUMENTED-FIELDS — the OpenAPI for POST /entities documents
// display_name, status and tags. The handler's request struct carried NONE of them, so
// json.Decode discarded all three in silence and the route answered 201.
//
// Measured 2026-08-01 while building a live fixture: a create sending display_name came back
// 201 with a NAMELESS entity, and the caller had to write the name attribute by hand with SQL
// afterwards. 201 is the worst possible way to say "ignored" — and `cached_name` is what the
// packer's <present> block renders, so a nameless entity is also an unjoinable one downstream.
//
// The display_name case is the one that needed a test most and would have been easiest to fake:
// the name is NOT a column on glossary_entities, it is an attribute VALUE row seeded later in
// the same transaction. The first version of the fix updated that row BEFORE the loop that
// creates it, so it matched zero rows and still returned 201 — the same silent no-op, one layer
// down. Hence this asserts the READ-BACK, never the status code.
//
// Requires GLOSSARY_TEST_DB_URL.

import (
	"encoding/json"
	"net/http"
	"testing"

	"github.com/google/uuid"
)

func TestCreateEntity_HonoursTheFieldsItsContractDocuments(t *testing.T) {
	pool := openTestDB(t)
	runGenreMigrations(t, pool)
	owner := uuid.New()
	book := uuid.New()
	srv := newAdoptServer(t, pool, book, owner)
	adoptTestBook(t, pool, book)
	base := "/v1/glossary/books/" + book.String() + "/entities"
	bk := bookKindID(t, pool, book, "character")

	body := `{"kind_id":"` + bk.String() + `","display_name":"Tô Thanh Dao",` +
		`"status":"active","tags":["protagonist","swordsman"]}`
	w := ukReq(t, srv, http.MethodPost, base, owner.String(), body)
	if w.Code != http.StatusCreated {
		t.Fatalf("create: want 201, got %d (%s)", w.Code, w.Body.String())
	}
	var created struct {
		EntityID string `json:"entity_id"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &created); err != nil || created.EntityID == "" {
		t.Fatalf("no entity_id in response: %s", w.Body.String())
	}

	// READ BACK, not the status code. A 201 proved nothing here for two years.
	var status string
	var tags []string
	var cachedName *string
	if err := pool.QueryRow(t.Context(),
		`SELECT status, tags, cached_name FROM glossary_entities WHERE entity_id=$1`,
		created.EntityID).Scan(&status, &tags, &cachedName); err != nil {
		t.Fatalf("read back: %v", err)
	}
	if status != "active" {
		t.Errorf("status: want active, got %q — the documented field was dropped", status)
	}
	if len(tags) != 2 || tags[0] != "protagonist" {
		t.Errorf("tags: want [protagonist swordsman], got %v", tags)
	}
	// cached_name is trigger-maintained from the name ATTRIBUTE VALUE, so this asserts the
	// seed landed on the row the trigger reads — not merely that a column was set.
	if cachedName == nil || *cachedName != "Tô Thanh Dao" {
		got := "<nil>"
		if cachedName != nil {
			got = *cachedName
		}
		t.Errorf("cached_name: want %q, got %q — display_name never reached the name attribute",
			"Tô Thanh Dao", got)
	}
}

func TestCreateEntity_DefaultsAreUnchangedWhenTheFieldsAreOmitted(t *testing.T) {
	// The counterweight. Without it, "always set status=active" satisfies the test above and
	// every entity created by the existing UI silently becomes active instead of draft — a
	// behaviour change smuggled in by a bug fix.
	pool := openTestDB(t)
	runGenreMigrations(t, pool)
	owner := uuid.New()
	book := uuid.New()
	srv := newAdoptServer(t, pool, book, owner)
	adoptTestBook(t, pool, book)
	base := "/v1/glossary/books/" + book.String() + "/entities"
	bk := bookKindID(t, pool, book, "character")

	w := ukReq(t, srv, http.MethodPost, base, owner.String(), `{"kind_id":"`+bk.String()+`"}`)
	if w.Code != http.StatusCreated {
		t.Fatalf("create: want 201, got %d (%s)", w.Code, w.Body.String())
	}
	var created struct {
		EntityID string `json:"entity_id"`
	}
	_ = json.Unmarshal(w.Body.Bytes(), &created)

	var status string
	var tags []string
	if err := pool.QueryRow(t.Context(),
		`SELECT status, tags FROM glossary_entities WHERE entity_id=$1`,
		created.EntityID).Scan(&status, &tags); err != nil {
		t.Fatalf("read back: %v", err)
	}
	if status != "draft" {
		t.Errorf("omitted status must stay draft, got %q", status)
	}
	if len(tags) != 0 {
		t.Errorf("omitted tags must stay empty, got %v", tags)
	}
}

func TestCreateEntity_RejectsAStatusOutsideTheClosedSet(t *testing.T) {
	// Enum-validate closed-set values on write (Frontend-Tool-Contract discipline). Without
	// this the CHECK constraint answers instead — a 500 that names nothing the caller can fix.
	pool := openTestDB(t)
	runGenreMigrations(t, pool)
	owner := uuid.New()
	book := uuid.New()
	srv := newAdoptServer(t, pool, book, owner)
	adoptTestBook(t, pool, book)
	base := "/v1/glossary/books/" + book.String() + "/entities"
	bk := bookKindID(t, pool, book, "character")

	w := ukReq(t, srv, http.MethodPost, base, owner.String(),
		`{"kind_id":"`+bk.String()+`","status":"published"}`)
	if w.Code != http.StatusUnprocessableEntity {
		t.Fatalf("bad status: want 422, got %d (%s)", w.Code, w.Body.String())
	}
}
