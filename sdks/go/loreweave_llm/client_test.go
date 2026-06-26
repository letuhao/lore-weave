package loreweave_llm

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// sseFrame builds one SSE frame: "event: <type>\ndata: <json>\n\n".
func sseFrame(t *testing.T, typ string, payload any) string {
	t.Helper()
	b, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal %s frame: %v", typ, err)
	}
	return "event: " + typ + "\ndata: " + string(b) + "\n\n"
}

// ── 1. NewClient validation ──────────────────────────────────────────────────

func TestNewClientValidation(t *testing.T) {
	tests := []struct {
		name    string
		opts    Options
		wantErr bool
	}{
		{
			name:    "empty BaseURL",
			opts:    Options{AuthMode: AuthInternal, InternalToken: "tok"},
			wantErr: true,
		},
		{
			name:    "internal without InternalToken",
			opts:    Options{BaseURL: "http://gw", AuthMode: AuthInternal},
			wantErr: true,
		},
		{
			name:    "jwt without BearerToken",
			opts:    Options{BaseURL: "http://gw", AuthMode: AuthJWT},
			wantErr: true,
		},
		{
			name:    "unknown auth mode",
			opts:    Options{BaseURL: "http://gw", AuthMode: AuthMode("weird")},
			wantErr: true,
		},
		{
			name:    "valid internal",
			opts:    Options{BaseURL: "http://gw", AuthMode: AuthInternal, InternalToken: "tok", UserID: "u1"},
			wantErr: false,
		},
		{
			name:    "valid jwt",
			opts:    Options{BaseURL: "http://gw", AuthMode: AuthJWT, BearerToken: "jwt"},
			wantErr: false,
		},
		{
			name:    "empty AuthMode defaults to internal (valid with token)",
			opts:    Options{BaseURL: "http://gw", InternalToken: "tok"},
			wantErr: false,
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c, err := NewClient(tt.opts)
			if tt.wantErr {
				if err == nil {
					t.Fatalf("expected error, got nil (client=%v)", c)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if c == nil {
				t.Fatal("expected non-nil client")
			}
		})
	}
}

// ── 2. Complete (AuthInternal) happy path + request assertions ───────────────

func TestCompleteInternalHappyPath(t *testing.T) {
	type captured struct {
		method      string
		path        string
		query       string
		internalTok string
		accept      string
		body        map[string]any
	}
	var cap captured

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cap.method = r.Method
		cap.path = r.URL.Path
		cap.query = r.URL.Query().Get("user_id")
		cap.internalTok = r.Header.Get("X-Internal-Token")
		cap.accept = r.Header.Get("Accept")
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &cap.body)

		w.Header().Set("Content-Type", "text/event-stream")
		io.WriteString(w, sseFrame(t, "token", tokenData{Delta: "Hello, ", Index: 0}))
		io.WriteString(w, sseFrame(t, "token", tokenData{Delta: "world", Index: 1}))
		io.WriteString(w, sseFrame(t, "usage", usageData{InputTokens: 10, OutputTokens: 5, ReasoningTokens: 2}))
		io.WriteString(w, sseFrame(t, "done", doneData{FinishReason: "stop"}))
	}))
	defer srv.Close()

	c, err := NewClient(Options{
		BaseURL:       srv.URL,
		AuthMode:      AuthInternal,
		InternalToken: "secret-token",
		UserID:        "user-123",
	})
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}

	req := StreamRequest{
		ModelSource: ModelSourceUser,
		ModelRef:    "model-uuid",
		Messages:    []Message{{Role: "user", Content: "hi"}},
		// MaxTokens left 0 → must be absent from the wire.
	}
	res, err := c.Complete(context.Background(), req)
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}

	if res.Text != "Hello, world" {
		t.Errorf("Text = %q, want %q", res.Text, "Hello, world")
	}
	if res.Usage != (Usage{InputTokens: 10, OutputTokens: 5, ReasoningTokens: 2}) {
		t.Errorf("Usage = %+v, want {10 5 2}", res.Usage)
	}
	if res.FinishReason != "stop" {
		t.Errorf("FinishReason = %q, want %q", res.FinishReason, "stop")
	}

	// Request-side assertions.
	if cap.method != http.MethodPost {
		t.Errorf("method = %q, want POST", cap.method)
	}
	if cap.path != "/internal/llm/stream" {
		t.Errorf("path = %q, want /internal/llm/stream", cap.path)
	}
	if cap.query != "user-123" {
		t.Errorf("user_id query = %q, want user-123", cap.query)
	}
	if cap.internalTok != "secret-token" {
		t.Errorf("X-Internal-Token = %q, want secret-token", cap.internalTok)
	}
	if cap.accept != "text/event-stream" {
		t.Errorf("Accept = %q, want text/event-stream", cap.accept)
	}
	if cap.body["model_source"] != "user_model" {
		t.Errorf("body model_source = %v, want user_model", cap.body["model_source"])
	}
	if cap.body["model_ref"] != "model-uuid" {
		t.Errorf("body model_ref = %v, want model-uuid", cap.body["model_ref"])
	}
	if _, ok := cap.body["messages"]; !ok {
		t.Error("body missing messages")
	}
	if cap.body["stream_format"] != "openai" {
		t.Errorf("body stream_format = %v, want defaulted openai", cap.body["stream_format"])
	}
	if _, ok := cap.body["max_tokens"]; ok {
		t.Errorf("body unexpectedly contains max_tokens (should be omitted when 0): %v", cap.body["max_tokens"])
	}
}

// ── 3. reasoning frames accumulate separately from text ──────────────────────

func TestCompleteReasoningSeparateFromText(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, sseFrame(t, "reasoning", tokenData{Delta: "thinking ", Index: 0}))
		io.WriteString(w, sseFrame(t, "reasoning", tokenData{Delta: "hard", Index: 1}))
		io.WriteString(w, sseFrame(t, "token", tokenData{Delta: "answer", Index: 0}))
		io.WriteString(w, sseFrame(t, "done", doneData{FinishReason: "stop"}))
	}))
	defer srv.Close()

	c, err := NewClient(Options{BaseURL: srv.URL, AuthMode: AuthInternal, InternalToken: "tok", UserID: "u"})
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	res, err := c.Complete(context.Background(), StreamRequest{ModelRef: "m", Messages: []Message{{Role: "user", Content: "x"}}})
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if res.Text != "answer" {
		t.Errorf("Text = %q, want %q", res.Text, "answer")
	}
	if res.Reasoning != "thinking hard" {
		t.Errorf("Reasoning = %q, want %q", res.Reasoning, "thinking hard")
	}
}

// ── 4. SSE error frame → *Error with Code/Message; errors.Is sentinel ────────

func TestCompleteErrorFrame(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, sseFrame(t, "token", tokenData{Delta: "partial", Index: 0}))
		io.WriteString(w, sseFrame(t, "error", errorData{Code: "LLM_RATE_LIMITED", Message: "slow down"}))
	}))
	defer srv.Close()

	c, err := NewClient(Options{BaseURL: srv.URL, AuthMode: AuthInternal, InternalToken: "tok", UserID: "u"})
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	_, err = c.Complete(context.Background(), StreamRequest{ModelRef: "m", Messages: []Message{{Role: "user", Content: "x"}}})
	if err == nil {
		t.Fatal("expected error, got nil")
	}

	var llmErr *Error
	if !errors.As(err, &llmErr) {
		t.Fatalf("errors.As(*Error) failed for %T: %v", err, err)
	}
	if llmErr.Code != "LLM_RATE_LIMITED" {
		t.Errorf("Code = %q, want LLM_RATE_LIMITED", llmErr.Code)
	}
	if llmErr.Message != "slow down" {
		t.Errorf("Message = %q, want %q", llmErr.Message, "slow down")
	}
	if llmErr.StatusCode != 0 {
		t.Errorf("StatusCode = %d, want 0 for an SSE-frame error", llmErr.StatusCode)
	}
	if !errors.Is(err, ErrRateLimited) {
		t.Errorf("errors.Is(err, ErrRateLimited) = false, want true")
	}
}

// ── 5. HTTP 400 with JSON {code,message} body → *Error + StatusCode ──────────

func TestCompleteHTTP400(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(errorData{Code: "LLM_INVALID_REQUEST", Message: "bad model_ref"})
	}))
	defer srv.Close()

	c, err := NewClient(Options{BaseURL: srv.URL, AuthMode: AuthInternal, InternalToken: "tok", UserID: "u"})
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	_, err = c.Complete(context.Background(), StreamRequest{ModelRef: "m", Messages: []Message{{Role: "user", Content: "x"}}})
	if err == nil {
		t.Fatal("expected error, got nil")
	}

	var llmErr *Error
	if !errors.As(err, &llmErr) {
		t.Fatalf("errors.As(*Error) failed for %T: %v", err, err)
	}
	if llmErr.Code != "LLM_INVALID_REQUEST" {
		t.Errorf("Code = %q, want LLM_INVALID_REQUEST", llmErr.Code)
	}
	if llmErr.Message != "bad model_ref" {
		t.Errorf("Message = %q, want %q", llmErr.Message, "bad model_ref")
	}
	if llmErr.StatusCode != http.StatusBadRequest {
		t.Errorf("StatusCode = %d, want 400", llmErr.StatusCode)
	}
	if !errors.Is(err, ErrInvalidRequest) {
		t.Errorf("errors.Is(err, ErrInvalidRequest) = false, want true")
	}
}

// ── 6. AuthInternal missing user_id everywhere → error before any HTTP ───────

func TestCompleteInternalNoUserIDFailsBeforeHTTP(t *testing.T) {
	var hit bool
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hit = true
	}))
	defer srv.Close()

	// Built WITHOUT a default UserID; none passed to Complete either.
	c, err := NewClient(Options{BaseURL: srv.URL, AuthMode: AuthInternal, InternalToken: "tok"})
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	_, err = c.Complete(context.Background(), StreamRequest{ModelRef: "m", Messages: []Message{{Role: "user", Content: "x"}}})
	if err == nil {
		t.Fatal("expected error for missing user_id, got nil")
	}
	if hit {
		t.Error("server was hit; expected the error to short-circuit before any HTTP request")
	}
	var llmErr *Error
	if !errors.As(err, &llmErr) {
		t.Fatalf("errors.As(*Error) failed for %T: %v", err, err)
	}
	if llmErr.Code != "LLM_INVALID_REQUEST" {
		t.Errorf("Code = %q, want LLM_INVALID_REQUEST", llmErr.Code)
	}
}

func TestCompleteInternalPerCallUserIDOverride(t *testing.T) {
	var gotUserID string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotUserID = r.URL.Query().Get("user_id")
		io.WriteString(w, sseFrame(t, "done", doneData{FinishReason: "stop"}))
	}))
	defer srv.Close()

	// Default UserID is "default-user"; per-call override should win.
	c, err := NewClient(Options{BaseURL: srv.URL, AuthMode: AuthInternal, InternalToken: "tok", UserID: "default-user"})
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	_, err = c.Complete(context.Background(), StreamRequest{ModelRef: "m", Messages: []Message{{Role: "user", Content: "x"}}}, "override-user")
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if gotUserID != "override-user" {
		t.Errorf("user_id query = %q, want override-user (per-call override)", gotUserID)
	}
}

// ── 7. AuthJWT path → /v1/llm/stream, Bearer header, no user_id query ────────

func TestCompleteJWTPath(t *testing.T) {
	var (
		gotPath   string
		gotAuth   string
		gotUserID string
		hasUserID bool
	)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotAuth = r.Header.Get("Authorization")
		gotUserID = r.URL.Query().Get("user_id")
		_, hasUserID = r.URL.Query()["user_id"]
		io.WriteString(w, sseFrame(t, "token", tokenData{Delta: "ok", Index: 0}))
		io.WriteString(w, sseFrame(t, "done", doneData{FinishReason: "stop"}))
	}))
	defer srv.Close()

	c, err := NewClient(Options{BaseURL: srv.URL, AuthMode: AuthJWT, BearerToken: "the-jwt"})
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	res, err := c.Complete(context.Background(), StreamRequest{ModelRef: "m", Messages: []Message{{Role: "user", Content: "x"}}})
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if res.Text != "ok" {
		t.Errorf("Text = %q, want ok", res.Text)
	}
	if gotPath != "/v1/llm/stream" {
		t.Errorf("path = %q, want /v1/llm/stream", gotPath)
	}
	if gotAuth != "Bearer the-jwt" {
		t.Errorf("Authorization = %q, want %q", gotAuth, "Bearer the-jwt")
	}
	if hasUserID {
		t.Errorf("user_id query present (=%q); JWT path must not send it", gotUserID)
	}
}

// ── 8. Direct scanSSE behaviors ──────────────────────────────────────────────

func TestScanSSE(t *testing.T) {
	t.Run("multi-line data joined with newline", func(t *testing.T) {
		input := "event: token\ndata: line1\ndata: line2\n\n"
		var got []sseEvent
		err := scanSSE(strings.NewReader(input), func(ev sseEvent) error {
			got = append(got, ev)
			return nil
		})
		if err != nil {
			t.Fatalf("scanSSE: %v", err)
		}
		if len(got) != 1 {
			t.Fatalf("got %d events, want 1", len(got))
		}
		if got[0].Type != "token" {
			t.Errorf("Type = %q, want token", got[0].Type)
		}
		if string(got[0].Data) != "line1\nline2" {
			t.Errorf("Data = %q, want %q", string(got[0].Data), "line1\nline2")
		}
	})

	t.Run("comment/heartbeat line ignored", func(t *testing.T) {
		input := ": this is a heartbeat\nevent: done\ndata: {}\n\n"
		var got []sseEvent
		err := scanSSE(strings.NewReader(input), func(ev sseEvent) error {
			got = append(got, ev)
			return nil
		})
		if err != nil {
			t.Fatalf("scanSSE: %v", err)
		}
		if len(got) != 1 {
			t.Fatalf("got %d events, want 1", len(got))
		}
		if got[0].Type != "done" || string(got[0].Data) != "{}" {
			t.Errorf("event = %+v, want {done {}}", got[0])
		}
	})

	t.Run("trailing event with no final blank line is delivered", func(t *testing.T) {
		input := "event: done\ndata: {\"finish_reason\":\"stop\"}"
		var got []sseEvent
		err := scanSSE(strings.NewReader(input), func(ev sseEvent) error {
			got = append(got, ev)
			return nil
		})
		if err != nil {
			t.Fatalf("scanSSE: %v", err)
		}
		if len(got) != 1 {
			t.Fatalf("got %d events, want 1 (trailing event must flush)", len(got))
		}
		if got[0].Type != "done" {
			t.Errorf("Type = %q, want done", got[0].Type)
		}
		if string(got[0].Data) != `{"finish_reason":"stop"}` {
			t.Errorf("Data = %q, want the finish_reason json", string(got[0].Data))
		}
	})
}
