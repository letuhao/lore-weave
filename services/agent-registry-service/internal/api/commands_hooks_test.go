package api

import (
	"encoding/json"
	"net/http"
	"testing"
)

func TestCommandNameValidation(t *testing.T) {
	ok := []string{"mycmd", "plan-scene", "a", "x1", "review-arc-2"}
	bad := []string{"", "/leading", "Upper", "has space", "under_score", "toolongtoolongtoolongtoolongtoolong", "-lead"}
	for _, n := range ok {
		if !commandNameRE.MatchString(n) {
			t.Errorf("expected VALID command name %q", n)
		}
	}
	for _, n := range bad {
		if commandNameRE.MatchString(n) {
			t.Errorf("expected INVALID command name %q", n)
		}
	}
	for _, r := range []string{"think", "effort", "compact", "no_think", "help"} {
		if !reservedCommandNames[r] {
			t.Errorf("%q must be reserved", r)
		}
	}
}

func TestValidateHookAction(t *testing.T) {
	good := map[string]string{
		"deny":             `{"kind":"deny","message":"blocked"}`,
		"require_approval": `{"kind":"require_approval"}`,
		"inject_text":      `{"kind":"inject_text","text":"remember the tone"}`,
		"annotate":         `{"kind":"annotate","text":"noted"}`,
	}
	for want, raw := range good {
		if kind, ok := validateHookAction(json.RawMessage(raw)); !ok || kind != want {
			t.Errorf("action %s should be valid (got kind=%q ok=%v)", raw, kind, ok)
		}
	}
	bad := []string{
		`{"kind":"exec","cmd":"rm -rf"}`, // not an allowed kind (no code execution)
		`{"kind":"inject_text"}`,          // missing text
		`{"kind":"annotate","text":"  "}`, // blank text
		`{}`,                              // no kind
		`not json`,
	}
	for _, raw := range bad {
		if _, ok := validateHookAction(json.RawMessage(raw)); ok {
			t.Errorf("action %s should be INVALID", raw)
		}
	}
}

// Handler rejection paths (reject before any DB op → mock needs no expectations).
func TestCreateCommand_ReservedAndInvalid(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	tok := mintJWT(t, "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c", "user")

	rec := doJSON(s, http.MethodPost, "/v1/agent-registry/commands", tok, `{"name":"think","template_md":"x"}`)
	if rec.Code != http.StatusConflict {
		t.Errorf("reserved name → want 409, got %d", rec.Code)
	}
	rec = doJSON(s, http.MethodPost, "/v1/agent-registry/commands", tok, `{"name":"Bad Name","template_md":"x"}`)
	if rec.Code != http.StatusBadRequest {
		t.Errorf("invalid name → want 400, got %d", rec.Code)
	}
	rec = doJSON(s, http.MethodPost, "/v1/agent-registry/commands", tok, `{"name":"good","template_md":""}`)
	if rec.Code != http.StatusBadRequest {
		t.Errorf("empty template → want 400, got %d", rec.Code)
	}
}

func TestCreateHook_InvalidEventAndAction(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	tok := mintJWT(t, "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c", "user")

	rec := doJSON(s, http.MethodPost, "/v1/agent-registry/hooks", tok, `{"on_event":"on_boot","action":{"kind":"deny"}}`)
	if rec.Code != http.StatusBadRequest {
		t.Errorf("invalid on_event → want 400, got %d", rec.Code)
	}
	rec = doJSON(s, http.MethodPost, "/v1/agent-registry/hooks", tok, `{"on_event":"pre_tool_call","action":{"kind":"exec"}}`)
	if rec.Code != http.StatusBadRequest {
		t.Errorf("code-execution action → want 400, got %d", rec.Code)
	}
}
