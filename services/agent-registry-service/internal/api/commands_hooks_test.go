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
	// only WIRED (event, kind) pairs are valid (the engine implements exactly these).
	good := []struct{ event, raw, kind string }{
		{"pre_tool_call", `{"kind":"deny","message":"blocked"}`, "deny"},
		{"pre_tool_call", `{"kind":"require_approval"}`, "require_approval"},
		{"pre_turn", `{"kind":"inject_text","text":"remember the tone"}`, "inject_text"},
	}
	for _, g := range good {
		if kind, ok := validateHookAction(g.event, json.RawMessage(g.raw)); !ok || kind != g.kind {
			t.Errorf("%s/%s should be valid (got kind=%q ok=%v)", g.event, g.raw, kind, ok)
		}
	}
	bad := []struct{ event, raw string }{
		{"pre_tool_call", `{"kind":"exec","cmd":"rm -rf"}`},      // no code execution
		{"pre_tool_call", `{"kind":"inject_text","text":"x"}`},   // inject_text not wired for pre_tool_call
		{"pre_turn", `{"kind":"deny"}`},                          // deny not wired for pre_turn
		{"pre_turn", `{"kind":"inject_text"}`},                   // missing text
		{"post_tool_call", `{"kind":"annotate","text":"noted"}`}, // event not wired at the API
		{"post_turn", `{"kind":"inject_text","text":"x"}`},       // event not wired
		{"pre_turn", `not json`},
	}
	for _, b := range bad {
		if _, ok := validateHookAction(b.event, json.RawMessage(b.raw)); ok {
			t.Errorf("%s/%s should be INVALID", b.event, b.raw)
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

func TestCreateSubagent_Validation(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	tok := mintJWT(t, "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c", "user")

	rec := doJSON(s, http.MethodPost, "/v1/agent-registry/subagents", tok, `{"name":"Bad Name","system_prompt":"x"}`)
	if rec.Code != http.StatusBadRequest {
		t.Errorf("invalid name → want 400, got %d", rec.Code)
	}
	rec = doJSON(s, http.MethodPost, "/v1/agent-registry/subagents", tok, `{"name":"lore-scout","system_prompt":""}`)
	if rec.Code != http.StatusBadRequest {
		t.Errorf("empty system_prompt → want 400, got %d", rec.Code)
	}
	rec = doJSON(s, http.MethodPost, "/v1/agent-registry/subagents", tok, `{"name":"lore-scout","system_prompt":"You scout lore.","tool_scope":"not-an-array"}`)
	if rec.Code != http.StatusBadRequest {
		t.Errorf("non-array tool_scope → want 400, got %d", rec.Code)
	}
}
