package api

// AC1 + AC2 — the two acceptance cases of the knowledge-architecture refactor, written
// as conformance tests BEFORE the endpoint they describe exists (plan T4 → T5).
//
// The substrate is already correct: `entity_facts` is bitemporal, `emitChapterFacts`
// writes every extracted attribute at its chapter ordinal, `maintain_chain` maintains
// pin-aware supersession, and the as-of predicate is index-served. What is missing is a
// READ. `composition-service` contains **zero** occurrences of `as_of`, so the drafting
// agent has never once asked what was true at a story position — it asks what is true
// now, and gets the end of the book while writing chapter 12.
//
// THIS FILE IS ALSO THE CONTRACT. T5 implements
// `GET /internal/books/{book_id}/state?as_of=N` against the shape asserted here:
//
//	{
//	  "book_id": "…", "as_of_ordinal": 30,
//	  "entities": [ { "entity_id": "…",
//	                  "facts": [ {"attr":"rank", "value":"inner disciple",
//	                              "fact_kind":"attribute", "valid_from_ordinal":25} ] } ]
//	}
//
// `facts` is a LIST, deliberately, not a map keyed by attribute. AC2's claim is "exactly
// one value per attribute"; a map would satisfy that by construction and the assertion
// would be vacuous — it could not tell a correct `DISTINCT ON` from a read that returned
// all three intervals and let the last write win.
//
// Requires GLOSSARY_TEST_DB_URL; skips otherwise (openTestDB).

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/migrate"
)

// ── the shape T5 must return ─────────────────────────────────────────────────

type stateFactOut struct {
	Attr             string `json:"attr"`
	Value            string `json:"value"`
	FactKind         string `json:"fact_kind"`
	ValidFromOrdinal int64  `json:"valid_from_ordinal"`
}

type stateEntityOut struct {
	EntityID string         `json:"entity_id"`
	Facts    []stateFactOut `json:"facts"`
}

type stateResp struct {
	BookID      string           `json:"book_id"`
	AsOfOrdinal int64            `json:"as_of_ordinal"`
	Entities    []stateEntityOut `json:"entities"`
}

// ── fixture ──────────────────────────────────────────────────────────────────

// seedFact opens a half-open story interval [from, to) on the entity. A nil `to` leaves
// the interval open, which is how the substrate represents "still true at the head".
func seedFact(t *testing.T, pool *pgxpool.Pool, bookID, entityID uuid.UUID, kind, attr, value string, from int64, to *int64) {
	t.Helper()
	if _, err := pool.Exec(context.Background(), `
		INSERT INTO entity_facts
		  (book_id, entity_id, fact_kind, attr_or_predicate, value,
		   valid_from_ordinal, valid_to_ordinal, cardinality)
		VALUES ($1,$2,$3,$4,$5,$6,$7,'single')`,
		bookID, entityID, kind, attr, value, from, to); err != nil {
		t.Fatalf("seed fact %s=%q [%d,%v): %v", attr, value, from, to, err)
	}
}

func ord(n int64) *int64 { return &n }

// newStateFixture gives a book + entity on the full migration chain (entity_facts lives
// in the ledger chain, not in the K2a set newVersionFixture applies).
func newStateFixture(t *testing.T, pool *pgxpool.Pool) *versionFixture {
	t.Helper()
	f := newVersionFixture(t, pool)
	if err := migrate.RunChain(context.Background(), pool); err != nil {
		t.Fatalf("migrate chain: %v", err)
	}
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM entity_facts WHERE entity_id=$1`, f.entityID) //nolint:errcheck
	})
	return f
}

// getState calls the endpoint under test and returns the status plus the decoded body.
func getState(t *testing.T, f *versionFixture, query string) (int, stateResp) {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet,
		fmt.Sprintf("/internal/books/%s/state%s", f.bookID, query), nil)
	req.Header.Set("X-Internal-Token", "tok")
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	var body stateResp
	_ = json.Unmarshal(w.Body.Bytes(), &body) //nolint:errcheck — a non-200 has no body to decode
	return w.Code, body
}

// factsFor returns every fact the response carries for one entity+attribute. Returning a
// slice rather than a single value is the point: AC2 asserts on its LENGTH.
func factsFor(body stateResp, entityID uuid.UUID, attr string) []stateFactOut {
	var out []stateFactOut
	for _, e := range body.Entities {
		if e.EntityID != entityID.String() {
			continue
		}
		for _, fct := range e.Facts {
			if fct.Attr == attr {
				out = append(out, fct)
			}
		}
	}
	return out
}

func hasEntity(body stateResp, entityID uuid.UUID) bool {
	for _, e := range body.Entities {
		if e.EntityID == entityID.String() {
			return true
		}
	}
	return false
}

// ── AC1 ──────────────────────────────────────────────────────────────────────

// TestStateAsOf_AC1_DeathIsTemporalNotAFlag locks the first acceptance case.
//
// A character dies in chapter 40. Read at 41 they are dead; read at 39 they are PRESENT
// and ALIVE. The second half is the whole test. An implementation that models death as a
// `deleted_at`-style flag — an untimed column, which is exactly what `glossary_entities.alive`
// is today (7290 true / 0 false) — passes the first half and fails the second, because a
// flag has no position: it makes the character retroactively dead in every chapter of the
// book, including the ones they are alive in.
func TestStateAsOf_AC1_DeathIsTemporalNotAFlag(t *testing.T) {
	pool := openTestDB(t)
	f := newStateFixture(t, pool)

	// Alive from the start of the book until chapter 40, dead from 40 onward.
	seedFact(t, pool, f.bookID, f.entityID, "attribute", "life_status", "alive", 0, ord(40))
	seedFact(t, pool, f.bookID, f.entityID, "attribute", "life_status", "dead", 40, nil)

	t.Run("as_of=41 reports dead", func(t *testing.T) {
		code, body := getState(t, f, "?as_of=41")
		if code != http.StatusOK {
			t.Fatalf("want 200, got %d", code)
		}
		got := factsFor(body, f.entityID, "life_status")
		if len(got) != 1 || got[0].Value != "dead" {
			t.Fatalf("as_of=41 life_status = %+v, want exactly one 'dead'", got)
		}
	})

	t.Run("as_of=39 reports PRESENT and ALIVE", func(t *testing.T) {
		code, body := getState(t, f, "?as_of=39")
		if code != http.StatusOK {
			t.Fatalf("want 200, got %d", code)
		}
		if !hasEntity(body, f.entityID) {
			t.Fatal("the entity is ABSENT at as_of=39 — a character who dies in ch.40 must " +
				"still exist in ch.39. This is the deleted_at-shaped failure: liveness " +
				"modelled as an untimed flag erases them from every earlier chapter too")
		}
		got := factsFor(body, f.entityID, "life_status")
		if len(got) != 1 || got[0].Value != "alive" {
			t.Fatalf("as_of=39 life_status = %+v, want exactly one 'alive'", got)
		}
	})

	t.Run("the boundary is half-open at the death ordinal", func(t *testing.T) {
		// [0,40) then [40,∞): chapter 40 itself is the first chapter of being dead.
		// Asserted because an off-by-one here is invisible in prose and decides whether
		// the chapter in which someone dies describes a living or a dead character.
		code, body := getState(t, f, "?as_of=40")
		if code != http.StatusOK {
			t.Fatalf("want 200, got %d", code)
		}
		got := factsFor(body, f.entityID, "life_status")
		if len(got) != 1 || got[0].Value != "dead" {
			t.Fatalf("as_of=40 life_status = %+v, want exactly one 'dead' (intervals are half-open)", got)
		}
	})
}

// ── AC2 ──────────────────────────────────────────────────────────────────────

// TestStateAsOf_AC2_OneValuePerAttributeAtAPosition locks the second acceptance case.
//
// An attribute changes at chapters 10, 25 and 60. Read at 30, the answer is EXACTLY the
// chapter-25 value — one row, not three. The length assertion is the load-bearing half:
// a read that forgets `DISTINCT ON (entity_id, attr_or_predicate)` still contains the
// right value, so a "does it contain X" test passes while the caller receives three
// contradictory ranks and picks whichever the serializer emitted last.
func TestStateAsOf_AC2_OneValuePerAttributeAtAPosition(t *testing.T) {
	pool := openTestDB(t)
	f := newStateFixture(t, pool)

	seedFact(t, pool, f.bookID, f.entityID, "attribute", "rank", "outer disciple", 10, ord(25))
	seedFact(t, pool, f.bookID, f.entityID, "attribute", "rank", "inner disciple", 25, ord(60))
	seedFact(t, pool, f.bookID, f.entityID, "attribute", "rank", "core disciple", 60, nil)

	code, body := getState(t, f, "?as_of=30")
	if code != http.StatusOK {
		t.Fatalf("want 200, got %d", code)
	}
	got := factsFor(body, f.entityID, "rank")
	if len(got) != 1 {
		t.Fatalf("as_of=30 returned %d rank values, want exactly 1 — a caller handed three "+
			"overlapping intervals cannot know which is current: %+v", len(got), got)
	}
	if got[0].Value != "inner disciple" {
		t.Errorf("as_of=30 rank = %q, want %q (the ch.25 interval covers 30)", got[0].Value, "inner disciple")
	}
	if got[0].ValidFromOrdinal != 25 {
		t.Errorf("as_of=30 rank valid_from = %d, want 25 — the response must say WHICH "+
			"interval answered, or a caller cannot tell fresh canon from ancient canon",
			got[0].ValidFromOrdinal)
	}

	t.Run("a position before the first interval yields nothing for that attribute", func(t *testing.T) {
		code, body := getState(t, f, "?as_of=5")
		// Assert the status FIRST. Without it this "expect nothing" check is satisfied by
		// any failure that returns no body at all — including the endpoint not existing —
		// so it would sit green forever while proving nothing.
		if code != http.StatusOK {
			t.Fatalf("want 200, got %d", code)
		}
		if got := factsFor(body, f.entityID, "rank"); len(got) != 0 {
			t.Errorf("as_of=5 rank = %+v, want none — the attribute is not established until ch.10", got)
		}
	})
}

// TestStateAsOf_AC2_OverlappingIntervalsCollapseToTheFreshest is the test that actually
// exercises `DISTINCT ON`, and it exists because the one above does NOT.
//
// AC2 seeds [10,25) [25,60) [60,∞) — three intervals that do not overlap. Exactly one of
// them covers position 30, so the WHERE clause alone already returns one row and the
// length assertion holds with `DISTINCT ON` deleted from the query. Measured, not argued:
// removing it left the whole file green. The comment at the top of this file claimed that
// shape was the guard; it was not, and this test is the correction.
//
// The condition `DISTINCT ON` really defends against is an UNCLOSED CHAIN: `maintain_chain`
// fails to stamp `valid_to_ordinal` on the superseded row, so two values of the same
// attribute are simultaneously current. That is a substrate bug rather than a read bug —
// which is the point. The read must degrade to "the freshest interval wins" instead of
// handing the drafting agent two contradictory ranks and letting the serializer choose.
func TestStateAsOf_AC2_OverlappingIntervalsCollapseToTheFreshest(t *testing.T) {
	pool := openTestDB(t)
	f := newStateFixture(t, pool)

	// The ch.10 interval was never closed — it still claims to be true at the head while
	// the ch.25 interval also covers 30.
	seedFact(t, pool, f.bookID, f.entityID, "attribute", "rank", "outer disciple", 10, nil)
	seedFact(t, pool, f.bookID, f.entityID, "attribute", "rank", "inner disciple", 25, ord(60))

	code, body := getState(t, f, "?as_of=30")
	if code != http.StatusOK {
		t.Fatalf("want 200, got %d", code)
	}
	got := factsFor(body, f.entityID, "rank")
	if len(got) != 1 {
		t.Fatalf("as_of=30 returned %d rank values, want exactly 1 — an unclosed chain must "+
			"not reach the caller as two simultaneously-current values: %+v", len(got), got)
	}
	if got[0].Value != "inner disciple" || got[0].ValidFromOrdinal != 25 {
		t.Errorf("as_of=30 rank = %+v, want the ch.25 value — when intervals collide the "+
			"freshest one wins, deterministically, not whichever the scan emitted last", got[0])
	}
}

// ── the required parameter ───────────────────────────────────────────────────

// TestStateAsOf_MissingAsOfIsRejected locks the decision that `as_of` is REQUIRED.
//
// A default would silently answer a different question than the one asked — "what is true
// now" wearing the shape of "what was true then" — and the caller has no way to notice.
// That failure mode is the one this whole refactor exists to remove, so it must not be
// reintroduced as a convenience.
func TestStateAsOf_MissingAsOfIsRejected(t *testing.T) {
	pool := openTestDB(t)
	f := newStateFixture(t, pool)

	if code, _ := getState(t, f, ""); code != http.StatusBadRequest {
		t.Errorf("missing as_of: want 400, got %d — a defaulted position returns a "+
			"confidently wrong answer", code)
	}
	if code, _ := getState(t, f, "?as_of=not-a-number"); code != http.StatusBadRequest {
		t.Errorf("non-numeric as_of: want 400, got %d", code)
	}
	if code, _ := getState(t, f, "?as_of=-1"); code != http.StatusBadRequest {
		t.Errorf("negative as_of: want 400, got %d — there is no chapter before the first", code)
	}
}

// ── invalidated facts are not current belief ─────────────────────────────────

// TestStateAsOf_InvalidatedFactsAreExcluded guards the belief axis.
//
// `entity_facts` is bitemporal: a fact can be true in story time and no longer believed
// (a chapter revision supersedes it). The as-of read answers on the CURRENT belief, so an
// invalidated row must not surface however well its story interval matches.
func TestStateAsOf_InvalidatedFactsAreExcluded(t *testing.T) {
	pool := openTestDB(t)
	f := newStateFixture(t, pool)
	ctx := context.Background()

	seedFact(t, pool, f.bookID, f.entityID, "attribute", "affiliation", "Cloud Sect", 5, nil)
	if _, err := pool.Exec(ctx, `
		UPDATE entity_facts SET invalidated_at = now(), invalidated_reason = 'episode_superseded'
		WHERE entity_id = $1 AND attr_or_predicate = 'affiliation'`, f.entityID); err != nil {
		t.Fatalf("invalidate: %v", err)
	}

	// A second, NON-invalidated fact on the same entity. Without it this test is an
	// "expect nothing" assertion, which passes whenever the response is empty for any
	// reason at all — a 404, a broken fixture, the wrong book. The control below forces
	// the read to demonstrate it can see this entity's facts before its silence about
	// the invalidated one counts as evidence.
	seedFact(t, pool, f.bookID, f.entityID, "attribute", "weapon", "jade flute", 5, nil)

	code, body := getState(t, f, "?as_of=10")
	if code != http.StatusOK {
		t.Fatalf("want 200, got %d", code)
	}
	if got := factsFor(body, f.entityID, "weapon"); len(got) != 1 {
		t.Fatalf("control: as_of=10 weapon = %+v, want exactly 1 — the absence asserted "+
			"below only means something if this read can see the entity at all", got)
	}
	if got := factsFor(body, f.entityID, "affiliation"); len(got) != 0 {
		t.Errorf("as_of=10 returned an invalidated fact %+v — story time and belief time are "+
			"different axes; a superseded fact is not canon at any position", got)
	}
}

// ── the authoring axis (added with T5, not part of T4's contract) ────────────

// TestStateAsOf_TrashedEntityIsExcluded guards the THIRD axis.
//
// Story time and belief time are the two the substrate models. `glossary_entities.deleted_at`
// is neither: it is the author moving an entity to the recycle bin, and it has no story
// position at all. An entity in the bin is not canon at ANY ordinal, so the cast read must
// not hand it to the drafting agent — the same guard T1 put on `entityExistsInBook`, and the
// unit twin of QC-4's "absent from composition's cast read".
//
// The control matters more than the assertion here: the read is filtered on the ENTITY, and
// a filter written against the wrong table (or the wrong lifecycle column) empties the whole
// response rather than one entity's worth of it, which an "expect nothing" test cannot tell
// apart from success.
func TestStateAsOf_TrashedEntityIsExcluded(t *testing.T) {
	pool := openTestDB(t)
	f := newStateFixture(t, pool)
	ctx := context.Background()

	seedFact(t, pool, f.bookID, f.entityID, "attribute", "rank", "outer disciple", 5, nil)

	// Control: live, the fact is visible. Asserted BEFORE the delete so the absence below
	// is attributable to the delete and not to a fixture that never worked.
	code, body := getState(t, f, "?as_of=10")
	if code != http.StatusOK {
		t.Fatalf("control: want 200, got %d", code)
	}
	if got := factsFor(body, f.entityID, "rank"); len(got) != 1 {
		t.Fatalf("control: a live entity's fact = %+v, want exactly 1", got)
	}

	if _, err := pool.Exec(ctx,
		`UPDATE glossary_entities SET deleted_at = now() WHERE entity_id = $1`, f.entityID); err != nil {
		t.Fatalf("soft-delete: %v", err)
	}

	code, body = getState(t, f, "?as_of=10")
	if code != http.StatusOK {
		t.Fatalf("want 200 after the delete (an empty book is a valid state), got %d", code)
	}
	if hasEntity(body, f.entityID) {
		t.Errorf("a trashed entity is still in the state read — the drafting agent would be "+
			"handed canon the author deleted: %+v", body.Entities)
	}
}
