package loreweave_mcp

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// tasksMeta builds a per-request _meta declaring the ext-tasks extension.
func tasksMeta() Meta {
	return Meta{
		clientCapsKey: map[string]any{
			extensionsKey: map[string]any{
				TasksExtension: map[string]any{},
			},
		},
	}
}

func TestClientSupportsTasksTrue(t *testing.T) {
	if !ClientSupportsTasks(tasksMeta()) {
		t.Fatal("expected true when the tasks extension is declared")
	}
}

func TestClientSupportsTasksFailClosed(t *testing.T) {
	cases := map[string]Meta{
		"nil meta":            nil,
		"empty meta":          {},
		"caps wrong type":     {clientCapsKey: "nope"},
		"no extensions":       {clientCapsKey: map[string]any{}},
		"exts wrong type":     {clientCapsKey: map[string]any{extensionsKey: 7}},
		"different extension": {clientCapsKey: map[string]any{extensionsKey: map[string]any{"io.other/x": map[string]any{}}}},
		// tasks declared but explicitly null ⇒ NOT supported (parity with Python
		// `_mget(...) is not None`); a null-valued key must fall back to confirm.
		"tasks value null": {clientCapsKey: map[string]any{extensionsKey: map[string]any{TasksExtension: nil}}},
	}
	for name, m := range cases {
		if ClientSupportsTasks(m) {
			t.Fatalf("%s: expected false (fail-closed)", name)
		}
	}
}

func TestGateOrConfirmOpensTaskWhenSupported(t *testing.T) {
	ran := false
	resolver := func(ctx context.Context, owner string, payload, inputs map[string]any) (any, error) {
		ran = true
		return "ok", nil
	}
	s := NewInMemoryTaskStore(TaskResolverRegistry{"composition.derive": resolver})
	fallback := func() any { t.Fatal("fallback must not run when tasks supported"); return nil }

	res, err := GateOrConfirm(context.Background(), tasksMeta(), s, "composition.derive", "u1",
		map[string]any{"name": "x"}, map[string]any{"title": "Derive?"}, fallback, 0)
	if err != nil {
		t.Fatalf("GateOrConfirm: %v", err)
	}
	handle, ok := res.(map[string]any)
	if !ok {
		t.Fatalf("result is not a handle map: %T", res)
	}
	if handle["type"] != GateHandleType {
		t.Fatalf("handle type = %v, want %q", handle["type"], GateHandleType)
	}
	if handle["status"] != TaskInputRequired {
		t.Fatalf("handle status = %v, want input_required", handle["status"])
	}
	if handle["inputRequests"].(map[string]any)["title"] != "Derive?" {
		t.Fatalf("inputRequests not carried: %v", handle["inputRequests"])
	}
	// Opening the gate must NOT run the resolver (that waits for provide-input).
	if ran {
		t.Fatal("resolver ran at gate-open; must wait for accept")
	}
	// The task is durably stored (owner + payload) and awaiting input.
	got, err := s.Get(handle["taskId"].(string), time.Time{})
	if err != nil || got.Status != TaskInputRequired {
		t.Fatalf("task not stored awaiting input: err=%v status=%q", err, got.Status)
	}
	if got.OwnerUserID != "u1" || got.Payload["name"] != "x" {
		t.Fatalf("owner/payload not durably stored: owner=%q payload=%v", got.OwnerUserID, got.Payload)
	}
}

func TestGateOrConfirmFallsBackWhenUnsupported(t *testing.T) {
	s := NewInMemoryTaskStore(nil)
	fallbackHit := false
	fallback := func() any {
		fallbackHit = true
		return map[string]any{"confirm_token": "tok_123", "descriptor": "composition.derive"}
	}

	res, err := GateOrConfirm(context.Background(), Meta{}, s, "composition.derive", "u1", nil, nil, fallback, 0)
	if err != nil {
		t.Fatalf("GateOrConfirm: %v", err)
	}
	if !fallbackHit {
		t.Fatal("fallback did not run for a non-tasks client")
	}
	m := res.(map[string]any)
	if m["confirm_token"] != "tok_123" {
		t.Fatalf("fallback result = %v, want confirm_token", res)
	}
	// No task minted when falling back — a non-tasks client can't drive it.
	if len(s.tasks) != 0 {
		t.Fatalf("minted %d tasks on fallback path, want 0", len(s.tasks))
	}
}

func TestOpenGateReturnsPollInterval(t *testing.T) {
	s := NewInMemoryTaskStore(TaskResolverRegistry{"d": noopResolver})
	handle, err := OpenGate(s, "d", "u1", nil, nil, 0)
	if err != nil {
		t.Fatalf("OpenGate: %v", err)
	}
	if handle["pollIntervalMs"] != DefaultPollIntervalMs {
		t.Fatalf("pollIntervalMs = %v, want %d", handle["pollIntervalMs"], DefaultPollIntervalMs)
	}
}

// End-to-end over the REAL go-sdk in-memory wire: register the provide-input
// tool, open a gate whose resolver performs the "real write", then drive accept
// through a client CallTool and assert the resolver ran and the result rode back.
func TestProvideInputTool_AcceptRunsResolverAndReturnsResult(t *testing.T) {
	ran := false
	resolver := func(ctx context.Context, owner string, payload, inputs map[string]any) (any, error) {
		ran = true
		return map[string]any{"derivativeId": "wf_new", "note": inputs["note"], "src": payload["src"]}, nil
	}
	store := NewInMemoryTaskStore(TaskResolverRegistry{"composition.derive": resolver})
	handle, err := OpenGate(store, "composition.derive", "u1",
		map[string]any{"src": "proj1"}, map[string]any{"title": "Derive?"}, 0)
	if err != nil {
		t.Fatalf("OpenGate: %v", err)
	}
	taskID := handle["taskId"].(string)

	srv := mcp.NewServer(&mcp.Implementation{Name: "domain", Version: "0.0.1"}, nil)
	RegisterTaskProvideInput(srv, store, "composition")
	cs := connectInMemory(t, srv)

	res, err := cs.CallTool(context.Background(), &mcp.CallToolParams{
		Name:      "composition_task_provide_input",
		Arguments: map[string]any{"task_id": taskID, "accepted": true, "inputs": map[string]any{"note": "go-e2e"}},
	})
	if err != nil {
		t.Fatalf("CallTool: %v", err)
	}
	if res.IsError {
		t.Fatalf("provide-input returned isError: %+v", res.Content)
	}
	if !ran {
		t.Fatal("resolver never ran on accept")
	}
	out, _ := res.StructuredContent.(map[string]any)
	if out["status"] != TaskCompleted {
		t.Fatalf("status = %v, want completed", out["status"])
	}
	result, _ := out["result"].(map[string]any)
	if result["derivativeId"] != "wf_new" || result["note"] != "go-e2e" || result["src"] != "proj1" {
		t.Fatalf("result did not ride back (payload+inputs): %v", out["result"])
	}
}

// The provide-input tool is a mechanism tool — it must be tagged visibility:legacy
// so find_tools/discovery never surfaces it to the LLM (CAT-4).
func TestProvideInputTool_IsVisibilityLegacy(t *testing.T) {
	srv := mcp.NewServer(&mcp.Implementation{Name: "domain", Version: "0.0.1"}, nil)
	RegisterTaskProvideInput(srv, NewInMemoryTaskStore(nil), "composition")
	cs := connectInMemory(t, srv)

	res, err := cs.ListTools(context.Background(), &mcp.ListToolsParams{})
	if err != nil {
		t.Fatalf("ListTools: %v", err)
	}
	var found *mcp.Tool
	for _, tl := range res.Tools {
		if tl.Name == "composition_task_provide_input" {
			found = tl
		}
	}
	if found == nil {
		t.Fatal("provide-input tool not listed")
	}
	if found.Meta[MetaKeyVisibility] != string(VisibilityLegacy) {
		t.Fatalf("visibility = %v, want legacy (a mechanism tool must not be discoverable)", found.Meta[MetaKeyVisibility])
	}
	// The result carries a dynamic `Result any` field; its outputSchema must be a valid
	// object (NOT the SDK-inferred properties.result the ai-gateway federation rejects).
	raw, _ := json.Marshal(found.OutputSchema)
	if !strings.Contains(string(raw), `"type":"object"`) || strings.Contains(string(raw), `"result"`) {
		t.Fatalf("provide-input outputSchema is not a valid object (or leaks properties.result): %s", raw)
	}
}

// Decline over the real wire must cancel WITHOUT running the resolver.
func TestProvideInputTool_DeclineDoesNotRunResolver(t *testing.T) {
	ran := false
	resolver := func(ctx context.Context, owner string, payload, inputs map[string]any) (any, error) {
		ran = true
		return nil, nil
	}
	store := NewInMemoryTaskStore(TaskResolverRegistry{"composition.derive": resolver})
	handle, _ := OpenGate(store, "composition.derive", "u1", nil, nil, 0)
	taskID := handle["taskId"].(string)

	srv := mcp.NewServer(&mcp.Implementation{Name: "domain", Version: "0.0.1"}, nil)
	RegisterTaskProvideInput(srv, store, "composition")
	cs := connectInMemory(t, srv)

	res, err := cs.CallTool(context.Background(), &mcp.CallToolParams{
		Name:      "composition_task_provide_input",
		Arguments: map[string]any{"task_id": taskID, "accepted": false},
	})
	if err != nil {
		t.Fatalf("CallTool: %v", err)
	}
	out, _ := res.StructuredContent.(map[string]any)
	if out["status"] != TaskCancelled {
		t.Fatalf("status = %v, want cancelled", out["status"])
	}
	if ran {
		t.Fatal("resolver ran on decline")
	}
}

// A second accept on an already-resolved task surfaces as an error result (the
// double-confirm guard) over the wire.
func TestProvideInputTool_DoubleAcceptIsError(t *testing.T) {
	store := NewInMemoryTaskStore(TaskResolverRegistry{"d": noopResolver})
	handle, _ := OpenGate(store, "d", "u1", nil, nil, 0)
	taskID := handle["taskId"].(string)

	srv := mcp.NewServer(&mcp.Implementation{Name: "domain", Version: "0.0.1"}, nil)
	RegisterTaskProvideInput(srv, store, "composition")
	cs := connectInMemory(t, srv)

	call := func() *mcp.CallToolResult {
		r, err := cs.CallTool(context.Background(), &mcp.CallToolParams{
			Name:      "composition_task_provide_input",
			Arguments: map[string]any{"task_id": taskID, "accepted": true},
		})
		if err != nil {
			t.Fatalf("CallTool: %v", err)
		}
		return r
	}
	if call().IsError {
		t.Fatal("first accept must succeed")
	}
	if !call().IsError {
		t.Fatal("second accept must be an error result (double-confirm guard)")
	}
}
