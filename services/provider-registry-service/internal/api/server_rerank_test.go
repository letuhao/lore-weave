package api

// server_rerank_test.go — D-RERANK-NOT-BYOK: /internal/rerank is now BYOK
// (resolves the user's rerank model from provider-registry like /internal/embed).
// These tests lock the VALIDATION rejections that return BEFORE any DB access
// (no pool needed). The credential-resolution + upstream-dispatch path needs a
// live DB + a fake rerank upstream → covered by live smoke (same strategy as the
// stream/embed handlers; see D-PHASE5A-STREAM-INTEGRATION-TESTS).

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestInternalRerank_Validation(t *testing.T) {
	s := &Server{} // pool nil — every case below returns 400 before touching it

	validUser := "11111111-1111-1111-1111-111111111111"
	validModel := "22222222-2222-2222-2222-222222222222"

	cases := []struct {
		name string
		url  string
		body string
		want int
	}{
		{"no user_id", "/internal/rerank", `{"model_source":"user_model","model_ref":"` + validModel + `","query":"q","documents":["d"]}`, http.StatusBadRequest},
		{"invalid user_id", "/internal/rerank?user_id=not-a-uuid", `{"model_source":"user_model","model_ref":"` + validModel + `","query":"q","documents":["d"]}`, http.StatusBadRequest},
		{"bad json", "/internal/rerank?user_id=" + validUser, `{not json`, http.StatusBadRequest},
		{"empty query", "/internal/rerank?user_id=" + validUser, `{"model_source":"user_model","model_ref":"` + validModel + `","query":"  ","documents":["d"]}`, http.StatusBadRequest},
		{"empty documents", "/internal/rerank?user_id=" + validUser, `{"model_source":"user_model","model_ref":"` + validModel + `","query":"q","documents":[]}`, http.StatusBadRequest},
		{"missing model_ref", "/internal/rerank?user_id=" + validUser, `{"model_source":"user_model","query":"q","documents":["d"]}`, http.StatusBadRequest},
		{"invalid model_ref", "/internal/rerank?user_id=" + validUser, `{"model_source":"user_model","model_ref":"nope","query":"q","documents":["d"]}`, http.StatusBadRequest},
		{"non-user_model source", "/internal/rerank?user_id=" + validUser, `{"model_source":"platform_model","model_ref":"` + validModel + `","query":"q","documents":["d"]}`, http.StatusBadRequest},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost, c.url, strings.NewReader(c.body))
			rec := httptest.NewRecorder()
			s.internalRerank(rec, req)
			if rec.Code != c.want {
				t.Fatalf("got %d, want %d (body=%s)", rec.Code, c.want, rec.Body.String())
			}
		})
	}
}
