package api

// D-KG-LG-REAL — GET /internal/users/{user_id}/glossary-standards.
//
// The KG ontology resolver anchors its adopt-gate to this endpoint for book-less
// projects. The refinement under test: the response is the user's RESOLVED kind
// catalog — System defaults UNION the user's own per-user (user_kinds) tier, with
// per-user shadowing System by code (CLAUDE.md › User Boundaries resolution rule).
//
// Unit tests (no DB) run always. The union/shadow + tenant-isolation proofs need
// GLOSSARY_TEST_DB_URL and skip otherwise.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/glossary-service/internal/migrate"
)

const glossStandardsInternalToken = "gloss-standards-test-token"

func newGlossStandardsServer(t *testing.T) (*Server, string) {
	t.Helper()
	srv := newExportServer(t, nil)
	srv.cfg.InternalServiceToken = glossStandardsInternalToken
	return srv, glossStandardsInternalToken
}

func glossStandardsURL(userID string) string {
	return "/internal/users/" + userID + "/glossary-standards"
}

// glossStandards fires the internal read for userID and returns the recorder.
func glossStandards(t *testing.T, srv *Server, userID, internalToken string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, glossStandardsURL(userID), nil)
	if internalToken != "" {
		req.Header.Set("X-Internal-Token", internalToken)
	}
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	return w
}

// ── unit tests (no DB) ──────────────────────────────────────────────

func TestGlossStandards_RequiresInternalToken(t *testing.T) {
	srv, _ := newGlossStandardsServer(t)
	w := glossStandards(t, srv, uuid.NewString(), "")
	if w.Code != http.StatusUnauthorized {
		t.Errorf("no token: want 401, got %d", w.Code)
	}
}

func TestGlossStandards_WrongTokenReturns401(t *testing.T) {
	srv, _ := newGlossStandardsServer(t)
	w := glossStandards(t, srv, uuid.NewString(), "wrong")
	if w.Code != http.StatusUnauthorized {
		t.Errorf("wrong token: want 401, got %d", w.Code)
	}
}

func TestGlossStandards_BadUserUUIDReturns400(t *testing.T) {
	srv, token := newGlossStandardsServer(t)
	req := httptest.NewRequest(http.MethodGet, "/internal/users/not-a-uuid/glossary-standards", nil)
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("bad user uuid: want 400, got %d", w.Code)
	}
}

// ── integration (requires DB) ──────────────────────────────────────

// decodeStandards parses a 200 response into the kind list + a code→tier index.
func decodeStandards(t *testing.T, w *httptest.ResponseRecorder) (internalOntologyKinds, map[string]string) {
	t.Helper()
	if w.Code != http.StatusOK {
		t.Fatalf("glossary-standards: want 200, got %d body=%s", w.Code, w.Body.String())
	}
	var out internalOntologyKinds
	if err := json.Unmarshal(w.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode standards: %v (%s)", err, w.Body.String())
	}
	tierByCode := make(map[string]string, len(out.Kinds))
	for _, k := range out.Kinds {
		if _, dup := tierByCode[k.Code]; dup {
			t.Fatalf("duplicate code %q in resolved standards — union must shadow, not duplicate", k.Code)
		}
		tierByCode[k.Code] = k.Tier
	}
	return out, tierByCode
}

// TestGlossStandards_UnionsPerUserTierAndShadows is the D-KG-LG-REAL refinement
// proof:
//   - a fresh user sees ONLY System-tier kinds (the seeded baseline);
//   - a brand-new per-user kind is ADDED with tier="user";
//   - a per-user kind whose code collides with a System kind SHADOWS it
//     (same code, tier flips to "user", no duplicate, count unchanged).
func TestGlossStandards_UnionsPerUserTierAndShadows(t *testing.T) {
	pool := openTestDB(t)
	runUserKindMigrations(t, pool)

	srv, token := newGlossStandardsServer(t)
	srv.pool = pool
	srv.cfg.JWTSecret = exportTestSecret // user-kind CRUD uses the Bearer path

	userA := uuid.NewString()

	// Baseline: only System kinds, all tier="system".
	base, baseTier := decodeStandards(t, glossStandards(t, srv, userA, token))
	if base.Source != "user_standards" {
		t.Fatalf("source: want user_standards, got %q", base.Source)
	}
	if len(base.Kinds) == 0 {
		t.Fatalf("baseline must contain the seeded System kinds, got 0")
	}
	var systemCode string
	for _, k := range base.Kinds {
		if k.Tier != "system" {
			t.Fatalf("baseline kind %q: want tier=system, got %q", k.Code, k.Tier)
		}
		if systemCode == "" {
			systemCode = k.Code // borrow a real System code for the shadow test
		}
	}
	_ = baseTier

	// (1) A brand-new per-user kind is added with tier="user".
	mustCreateUserKind(t, srv, userA, `{"name":"Smoke Custom Kind","code":"smoke_custom_kind"}`)
	afterAdd, addTier := decodeStandards(t, glossStandards(t, srv, userA, token))
	if addTier["smoke_custom_kind"] != "user" {
		t.Fatalf("new per-user kind: want tier=user, got %q", addTier["smoke_custom_kind"])
	}
	if len(afterAdd.Kinds) != len(base.Kinds)+1 {
		t.Fatalf("after add: want %d kinds, got %d", len(base.Kinds)+1, len(afterAdd.Kinds))
	}

	// (2) A per-user kind colliding with a System code SHADOWS it: same code,
	// tier flips to "user", NO duplicate row, total count does not grow.
	mustCreateUserKind(t, srv, userA, `{"name":"My Override","code":"`+systemCode+`"}`)
	afterShadow, shadowTier := decodeStandards(t, glossStandards(t, srv, userA, token))
	if shadowTier[systemCode] != "user" {
		t.Fatalf("shadowed code %q: want tier=user, got %q", systemCode, shadowTier[systemCode])
	}
	if len(afterShadow.Kinds) != len(afterAdd.Kinds) {
		t.Fatalf("shadow must not add a row: want %d kinds, got %d",
			len(afterAdd.Kinds), len(afterShadow.Kinds))
	}

	// (3) Tenant isolation: user B never sees A's per-user kinds.
	userB := uuid.NewString()
	_, bTier := decodeStandards(t, glossStandards(t, srv, userB, token))
	if _, leaked := bTier["smoke_custom_kind"]; leaked {
		t.Fatalf("tenant leak: user B sees user A's per-user kind")
	}
	if bTier[systemCode] != "system" {
		t.Fatalf("user B's %q must be the unshadowed System kind, got %q", systemCode, bTier[systemCode])
	}
}

// TestGlossStandards_SystemKindsCarryViLabels — KG-ML M5 (C4): after the
// name_i18n migration, the resolved System kinds carry admin-seeded vi labels
// (e.g. "character" → "Nhân vật"), so a vi reader's KG/timeline can localize the
// kind. The English `Name` is unchanged (it IS the en label).
func TestGlossStandards_SystemKindsCarryViLabels(t *testing.T) {
	pool := openTestDB(t)
	runUserKindMigrations(t, pool)
	if err := migrate.UpKindNameI18n(context.Background(), pool); err != nil {
		t.Fatalf("migrate.UpKindNameI18n: %v", err)
	}

	srv, token := newGlossStandardsServer(t)
	srv.pool = pool

	out, _ := decodeStandards(t, glossStandards(t, srv, uuid.NewString(), token))
	byCode := make(map[string]internalOntologyKind, len(out.Kinds))
	for _, k := range out.Kinds {
		byCode[k.Code] = k
	}
	character, ok := byCode["character"]
	if !ok {
		t.Fatalf("seeded System kind 'character' missing from standards")
	}
	if character.Name != "Character" {
		t.Errorf("en name should be unchanged, got %q", character.Name)
	}
	if character.NameI18n["vi"] != "Nhân vật" {
		t.Errorf("character vi label: want \"Nhân vật\", got %q (full=%v)",
			character.NameI18n["vi"], character.NameI18n)
	}
	if loc, ok := byCode["location"]; ok && loc.NameI18n["vi"] != "Địa điểm" {
		t.Errorf("location vi label: want \"Địa điểm\", got %q", loc.NameI18n["vi"])
	}
}

// TestBookOntology_BookKindsInheritSystemViLabels — KG-ML M5 (C4/C7): a
// book-bound KG project resolves its kind labels from the BOOK ontology read.
// Per the LOCKED tier-merge, a book kind INHERITS the admin-seeded System vi
// label (book-kinds are adopted copies that carry no own label until per-book
// authoring lands), so a vi reader's book-bound graph-view localizes kinds.
func TestBookOntology_BookKindsInheritSystemViLabels(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	if err := migrate.UpKindNameI18n(context.Background(), pool); err != nil {
		t.Fatalf("migrate.UpKindNameI18n: %v", err)
	}
	f.srv.cfg.InternalServiceToken = "tok"

	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/"+f.bookID.String()+"/ontology", nil)
	req.Header.Set("X-Internal-Token", "tok")
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("book ontology: want 200, got %d %s", w.Code, w.Body.String())
	}
	var out internalOntologyKinds
	if err := json.Unmarshal(w.Body.Bytes(), &out); err != nil {
		t.Fatal(err)
	}
	var character *internalOntologyKind
	for i := range out.Kinds {
		if out.Kinds[i].Code == "character" {
			character = &out.Kinds[i]
		}
	}
	if character == nil {
		t.Fatalf("book kind 'character' missing (kinds=%+v)", out.Kinds)
	}
	if character.Tier != "book" {
		t.Errorf("tier: want book, got %q", character.Tier)
	}
	if character.NameI18n["vi"] != "Nhân vật" {
		t.Errorf("book kind should inherit System vi label: want \"Nhân vật\", got %q (full=%v)",
			character.NameI18n["vi"], character.NameI18n)
	}
}
