package api

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"

	"github.com/loreweave/glossary-service/internal/config"
)

// P1 · D-WIKI-PERSON-USER-TIER — drive the REAL user-kind HTTP handlers end-to-end through the router,
// proving the privacy fix + the two cold-review findings:
//   • HIGH — CLONING a system person-kind inherits is_person (the primary user-tier path; must not drop to false).
//   • parity — clearing is_person on a system-cloned person kind is REFUSED (third-party protection > owner pref);
//     a from-scratch kind stays freely togglable.
func TestUserKindHTTP_IsPerson_CloneInheritsAndClearGuard(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	ctx := context.Background()

	srv := NewServer(pool, &config.Config{
		JWTSecret: versionTestSecret, BookServiceURL: "http://127.0.0.1:1", InternalServiceToken: "tok",
	})
	owner := uuid.New()
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		Subject: owner.String(), ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
	})
	signed, err := tok.SignedString([]byte(versionTestSecret))
	if err != nil {
		t.Fatalf("sign jwt: %v", err)
	}

	// A system PERSON kind to clone from (is_person=true).
	var sysKindID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO system_kinds (code, name, is_default, is_person) VALUES ('p1testcolleague','Colleague',false,true)
		 ON CONFLICT (code) DO UPDATE SET is_person=true RETURNING kind_id`).Scan(&sysKindID); err != nil {
		t.Fatalf("seed system person kind: %v", err)
	}
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM user_kinds WHERE owner_user_id=$1`, owner)
		pool.Exec(ctx, `DELETE FROM system_kinds WHERE code='p1testcolleague'`)
	})

	do := func(method, path string, body any) *httptest.ResponseRecorder {
		b, _ := json.Marshal(body)
		req := httptest.NewRequest(method, path, bytes.NewReader(b))
		req.Header.Set("Authorization", "Bearer "+signed)
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		return w
	}
	readIsPerson := func(code string) bool {
		var v bool
		if err := pool.QueryRow(ctx,
			`SELECT is_person FROM user_kinds WHERE owner_user_id=$1 AND code=$2`, owner, code).Scan(&v); err != nil {
			t.Fatalf("read user kind %q: %v", code, err)
		}
		return v
	}

	// (1) HIGH — clone a system person-kind WITHOUT sending is_person → must inherit true.
	w := do(http.MethodPost, "/v1/glossary/user-kinds",
		map[string]any{"name": "My Colleague", "code": "mycolleague", "clone_from_kind_id": sysKindID.String()})
	if w.Code != http.StatusCreated {
		t.Fatalf("clone create: want 201, got %d (%s)", w.Code, w.Body.String())
	}
	if !readIsPerson("mycolleague") {
		t.Fatal("HIGH: cloning a system person-kind dropped is_person to false — the leak is re-opened")
	}
	// the response must expose the effective value (Settings-Boundary: effective-value-visible).
	var detail map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &detail)
	if detail["is_person"] != true {
		t.Errorf("create response must surface is_person=true, got %v", detail["is_person"])
	}

	// (2) from-scratch with is_person=true → true.
	if w := do(http.MethodPost, "/v1/glossary/user-kinds",
		map[string]any{"name": "My Client", "code": "myclient", "is_person": true}); w.Code != http.StatusCreated {
		t.Fatalf("scratch person create: want 201, got %d (%s)", w.Code, w.Body.String())
	}
	if !readIsPerson("myclient") {
		t.Fatal("from-scratch is_person=true was dropped")
	}

	// (3) from-scratch NON-person → stays false, and is freely clearable/settable.
	if w := do(http.MethodPost, "/v1/glossary/user-kinds",
		map[string]any{"name": "A Place", "code": "myplace"}); w.Code != http.StatusCreated {
		t.Fatalf("scratch non-person create: want 201, got %d (%s)", w.Code, w.Body.String())
	}
	if readIsPerson("myplace") {
		t.Fatal("a non-person kind defaulted to is_person=true")
	}

	ukID := func(code string) string {
		var id uuid.UUID
		if err := pool.QueryRow(ctx, `SELECT user_kind_id FROM user_kinds WHERE owner_user_id=$1 AND code=$2`, owner, code).Scan(&id); err != nil {
			t.Fatalf("resolve id %q: %v", code, err)
		}
		return id.String()
	}

	// (4) parity guard — clearing is_person on the CLONED colleague is REFUSED (403).
	if w := do(http.MethodPatch, "/v1/glossary/user-kinds/"+ukID("mycolleague"),
		map[string]any{"is_person": false}); w.Code != http.StatusForbidden {
		t.Fatalf("clearing is_person on a system-cloned person kind must be 403, got %d (%s)", w.Code, w.Body.String())
	}
	if !readIsPerson("mycolleague") {
		t.Fatal("the refused clear still mutated the row — guard is not atomic")
	}

	// (5) a from-scratch person kind (no clone source) IS clearable — owner classified it.
	if w := do(http.MethodPatch, "/v1/glossary/user-kinds/"+ukID("myclient"),
		map[string]any{"is_person": false}); w.Code != http.StatusOK {
		t.Fatalf("clearing is_person on a from-scratch kind must be allowed (200), got %d (%s)", w.Code, w.Body.String())
	}
	if readIsPerson("myclient") {
		t.Fatal("clearing is_person on a from-scratch kind did not persist")
	}
}
