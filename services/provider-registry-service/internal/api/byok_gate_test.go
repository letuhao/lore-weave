package api

// Unit coverage for the shared PUB-12 (BYOK-only) gate helpers. Pure functions —
// the per-handler wiring (jobs / stream / proxy) is exercised in jobs_byok_test.go.

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func TestIsPublicMcpKeyCall(t *testing.T) {
	key := uuid.NewString()
	cases := []struct {
		name    string
		header  string
		jobMeta string
		want    bool
	}{
		{"header present", key, "", true},
		{"job_meta tag present", "", `{"mcp_key_id":"` + key + `"}`, true},
		{"header wins even if job_meta absent", key, `{"campaign_id":"` + uuid.NewString() + `"}`, true},
		{"neither (first-party)", "", `{"campaign_id":"` + uuid.NewString() + `"}`, false},
		{"neither, nil job_meta", "", "", false},
		{"malformed job_meta, no header", "", `{not json`, false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			r := httptest.NewRequest(http.MethodPost, "/", nil)
			if tc.header != "" {
				r.Header.Set("X-Mcp-Key-Id", tc.header)
			}
			var jm json.RawMessage
			if tc.jobMeta != "" {
				jm = json.RawMessage(tc.jobMeta)
			}
			if got := isPublicMcpKeyCall(r, jm); got != tc.want {
				t.Fatalf("isPublicMcpKeyCall = %v, want %v", got, tc.want)
			}
		})
	}
}

func TestRejectPlatformDrawForPublicKey(t *testing.T) {
	cases := []struct {
		name        string
		modelSource string
		isPublic    bool
		wantReject  bool
	}{
		{"public + platform → 402", "platform_model", true, true},
		{"public + user_model → allow", "user_model", true, false},
		{"first-party + platform → allow", "platform_model", false, false},
		{"first-party + user_model → allow", "user_model", false, false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			w := httptest.NewRecorder()
			got := rejectPlatformDrawForPublicKey(w, tc.modelSource, tc.isPublic)
			if got != tc.wantReject {
				t.Fatalf("rejectPlatformDrawForPublicKey = %v, want %v", got, tc.wantReject)
			}
			if tc.wantReject {
				if w.Code != http.StatusPaymentRequired {
					t.Fatalf("expected 402, got %d", w.Code)
				}
				if body := w.Body.String(); !strings.Contains(body, "LLM_BYOK_ONLY") {
					t.Fatalf("expected LLM_BYOK_ONLY in body, got %s", body)
				}
			}
		})
	}
}
