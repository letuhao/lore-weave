package loreweave_mcp

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

const testToken = "s3cret-internal-token"

func TestIdentityMiddleware_LiftsHeadersToCtx(t *testing.T) {
	userID := uuid.New()
	var gotUser uuid.UUID
	var gotUserOK bool
	var gotSession, gotTrace string
	var gotSessionOK, gotTraceOK bool

	h := IdentityMiddleware(testToken, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotUser, gotUserOK = UserIDFromCtx(r.Context())
		gotSession, gotSessionOK = SessionIDFromCtx(r.Context())
		gotTrace, gotTraceOK = TraceIDFromCtx(r.Context())
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodPost, "/mcp", nil)
	req.Header.Set(HeaderInternalToken, testToken)
	req.Header.Set(HeaderUserID, userID.String())
	req.Header.Set(HeaderSessionID, "sess-123")
	req.Header.Set(HeaderTraceID, "trace-abc")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rr.Code)
	}
	if !gotUserOK || gotUser != userID {
		t.Errorf("user from ctx = %v (ok=%v), want %v", gotUser, gotUserOK, userID)
	}
	if !gotSessionOK || gotSession != "sess-123" {
		t.Errorf("session from ctx = %q (ok=%v), want sess-123", gotSession, gotSessionOK)
	}
	if !gotTraceOK || gotTrace != "trace-abc" {
		t.Errorf("trace from ctx = %q (ok=%v), want trace-abc", gotTrace, gotTraceOK)
	}
}

func TestIdentityMiddleware_RejectsBadToken(t *testing.T) {
	called := false
	h := IdentityMiddleware(testToken, http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		called = true
	}))

	cases := map[string]string{
		"wrong token":   "nope",
		"missing token": "",
	}
	for name, tok := range cases {
		t.Run(name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost, "/mcp", nil)
			if tok != "" {
				req.Header.Set(HeaderInternalToken, tok)
			}
			rr := httptest.NewRecorder()
			h.ServeHTTP(rr, req)
			if rr.Code != http.StatusUnauthorized {
				t.Errorf("status = %d, want 401", rr.Code)
			}
		})
	}
	if called {
		t.Error("next handler should never be called on a bad token")
	}
}

func TestIdentityMiddleware_FailsClosedWhenServerTokenUnset(t *testing.T) {
	// An empty configured token must reject everything (even an empty presented
	// token) — never accept-all.
	called := false
	h := IdentityMiddleware("", http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		called = true
	}))
	req := httptest.NewRequest(http.MethodPost, "/mcp", nil)
	req.Header.Set(HeaderInternalToken, "")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != http.StatusUnauthorized {
		t.Errorf("status = %d, want 401", rr.Code)
	}
	if called {
		t.Error("next handler must not run when server token is unset")
	}
}

func TestUserIDFromCtx_MissingAndMalformed(t *testing.T) {
	h := IdentityMiddleware(testToken, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if _, ok := UserIDFromCtx(r.Context()); ok {
			t.Error("expected no user id in ctx")
		}
		if _, ok := SessionIDFromCtx(r.Context()); ok {
			t.Error("expected no session id in ctx")
		}
		w.WriteHeader(http.StatusOK)
	}))
	req := httptest.NewRequest(http.MethodPost, "/mcp", nil)
	req.Header.Set(HeaderInternalToken, testToken)
	req.Header.Set(HeaderUserID, "not-a-uuid") // malformed → ok=false
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rr.Code)
	}
}
