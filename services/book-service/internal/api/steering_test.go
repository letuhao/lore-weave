package api

// RAID C1 — steering store unit tests (no DB). Validation runs BEFORE any pool
// access (authBook is stubbed; a nil pool never gets touched on these paths),
// mirroring grant_mapping_test.go's harness. Real-PG CRUD/caps/409 coverage
// lives in steering_db_test.go (BOOK_TEST_DATABASE_URL-gated).

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func steeringReq(t *testing.T, s *Server, method, path, body string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+grantMapJWT(t))
	if body != "" {
		req.Header.Set("Content-Type", "application/json")
	}
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

// A VIEW grantee must NOT write steering (DR-C1 edge #13: writes are edit-tier).
// 403 fires in authBook before the payload is even parsed.
func TestSteering_ViewGranteeCannotWrite(t *testing.T) {
	t.Parallel()
	s := denyServer(GrantView)
	base := "/v1/books/" + uuid.NewString() + "/steering"
	for _, tc := range []struct{ method, path, body string }{
		{http.MethodPost, base, `{"name":"tone","body":"x"}`},
		{http.MethodPut, base + "/" + uuid.NewString(), `{"name":"tone","body":"x"}`},
		{http.MethodDelete, base + "/" + uuid.NewString(), ``},
	} {
		if rr := steeringReq(t, s, tc.method, tc.path, tc.body); rr.Code != http.StatusForbidden {
			t.Errorf("%s %s as view: got %d want 403\n%s", tc.method, tc.path, rr.Code, rr.Body.String())
		}
	}
}

// A non-grantee gets a uniform 404 on the list (no existence oracle).
func TestSteering_ListDeniesNonGrantee(t *testing.T) {
	t.Parallel()
	s := denyServer(GrantNone)
	rr := steeringReq(t, s, http.MethodGet, "/v1/books/"+uuid.NewString()+"/steering", "")
	if rr.Code != http.StatusNotFound {
		t.Errorf("list as non-grantee: got %d want 404\n%s", rr.Code, rr.Body.String())
	}
}

// Validation 422s — all fire before the (nil) pool is touched.
func TestSteering_CreateValidation(t *testing.T) {
	t.Parallel()
	base := "/v1/books/" + uuid.NewString() + "/steering"
	cases := []struct {
		name     string
		body     string
		wantCode int
		wantFrag string
	}{
		{"missing name", `{"body":"x"}`, http.StatusUnprocessableEntity, "name is required"},
		{"blank name", `{"name":"   ","body":"x"}`, http.StatusUnprocessableEntity, "name is required"},
		{"name too long", `{"name":"` + strings.Repeat("n", 201) + `","body":"x"}`, http.StatusUnprocessableEntity, "200"},
		{"missing body", `{"name":"tone"}`, http.StatusUnprocessableEntity, "body is required"},
		{"body over 8000 chars", `{"name":"tone","body":"` + strings.Repeat("a", 8001) + `"}`, http.StatusUnprocessableEntity, "8000"},
		{"invalid inclusion_mode", `{"name":"tone","body":"x","inclusion_mode":"sometimes"}`, http.StatusUnprocessableEntity, "always|scene_match|manual|auto"},
		{"scene_match without pattern", `{"name":"tone","body":"x","inclusion_mode":"scene_match"}`, http.StatusUnprocessableEntity, "match_pattern"},
		{"malformed json", `{"name":`, http.StatusBadRequest, "invalid payload"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			s := denyServer(GrantEdit)
			rr := steeringReq(t, s, http.MethodPost, base, tc.body)
			if rr.Code != tc.wantCode {
				t.Fatalf("got %d want %d\n%s", rr.Code, tc.wantCode, rr.Body.String())
			}
			if !strings.Contains(rr.Body.String(), tc.wantFrag) {
				t.Fatalf("body %q missing %q", rr.Body.String(), tc.wantFrag)
			}
		})
	}
}

// The 8000-char cap counts RUNES (matches Postgres char_length), not bytes —
// 8000 CJK chars is ~24000 bytes and must still pass validation. Exercised on
// the pure validator so the nil-pool row-cap COUNT is never reached.
func TestSteering_BodyCapIsRunesNotBytes(t *testing.T) {
	t.Parallel()
	rr := httptest.NewRecorder()
	_, _, mode, _, enabled, ok := validateSteeringInput(rr, steeringInput{
		Name: "tone", Body: strings.Repeat("宮", 8000),
	})
	if !ok {
		t.Fatalf("8000 CJK runes rejected as over-cap — cap is counting bytes, want runes\n%s", rr.Body.String())
	}
	// Defaults resolve: omitted inclusion_mode → always, omitted enabled → true.
	if mode != "always" || !enabled {
		t.Fatalf("defaults broke: mode=%q enabled=%v, want always/true", mode, enabled)
	}
}

// The invalid-mode message must carry the v1 honesty note for `auto` (DR-C1:
// authors must not be misled — auto is #name-triggered until model-pull ships).
func TestSteering_AutoModeNoteOnAPI(t *testing.T) {
	t.Parallel()
	s := denyServer(GrantEdit)
	base := "/v1/books/" + uuid.NewString() + "/steering"
	rr := steeringReq(t, s, http.MethodPost, base, `{"name":"n","body":"x","inclusion_mode":"bogus"}`)
	if rr.Code != http.StatusUnprocessableEntity {
		t.Fatalf("got %d want 422", rr.Code)
	}
	if !strings.Contains(rr.Body.String(), "triggered like manual") {
		t.Fatalf("enum error must document the auto-mode v1 behavior, got %q", rr.Body.String())
	}
}
