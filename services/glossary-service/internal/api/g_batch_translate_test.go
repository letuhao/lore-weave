package api

// S4 — the public batch-translate routes (/v1/.../translation-candidates,
// /apply-translations) reuse the internal worker cores behind a GRANT gate. The
// tenancy-critical assertion: a non-grantee can neither list nor write another book's
// translations (the internal handlers themselves trust the caller — the grant gate is
// what makes them safe on the JWT path).

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
)

func signUserJWT(t *testing.T, userID uuid.UUID) string {
	t.Helper()
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		Subject: userID.String(), ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
	})
	s, err := tok.SignedString([]byte(versionTestSecret))
	if err != nil {
		t.Fatalf("sign: %v", err)
	}
	return s
}

func TestBatchTranslate_GrantGated(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	charKind := bookKindID(t, pool, f.bookID, "character")
	nameAttr := bookAttrID(t, pool, f.bookID, charKind, "name")
	var eid uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,short_description) VALUES($1,$2,'demon') RETURNING entity_id`,
		f.bookID, charKind).Scan(&eid); err != nil {
		t.Fatalf("seed entity: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id=$1`, eid) }) //nolint:errcheck
	if _, err := pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh','焰魔')`,
		eid, nameAttr); err != nil {
		t.Fatalf("seed name: %v", err)
	}

	do := func(method, path, auth, body string) *httptest.ResponseRecorder {
		var r *http.Request
		if body != "" {
			r = httptest.NewRequest(method, path, strings.NewReader(body))
			r.Header.Set("Content-Type", "application/json")
		} else {
			r = httptest.NewRequest(method, path, nil)
		}
		r.Header.Set("Authorization", "Bearer "+auth)
		w := httptest.NewRecorder()
		f.srv.Router().ServeHTTP(w, r)
		return w
	}

	candPath := "/v1/glossary/books/" + f.bookID.String() + "/translation-candidates?target_language=en"
	applyPath := "/v1/glossary/books/" + f.bookID.String() + "/apply-translations"
	stranger := signUserJWT(t, uuid.New())

	// owner → 200 (the seeded entity is an untranslated candidate)
	if w := do(http.MethodGet, candPath, f.jwt, ""); w.Code != http.StatusOK {
		t.Fatalf("owner candidates = %d, body=%s", w.Code, w.Body.String())
	}
	// stranger → 403 on both list and write (no grant)
	if w := do(http.MethodGet, candPath, stranger, ""); w.Code != http.StatusForbidden {
		t.Errorf("stranger candidates = %d, want 403", w.Code)
	}
	if w := do(http.MethodPost, applyPath, stranger, `{"target_language":"en","items":[]}`); w.Code != http.StatusForbidden {
		t.Errorf("stranger apply = %d, want 403", w.Code)
	}
	// owner apply (empty items) → 200, well-formed response
	if w := do(http.MethodPost, applyPath, f.jwt, `{"target_language":"en","items":[]}`); w.Code != http.StatusOK {
		t.Errorf("owner apply = %d, body=%s", w.Code, w.Body.String())
	}
}
