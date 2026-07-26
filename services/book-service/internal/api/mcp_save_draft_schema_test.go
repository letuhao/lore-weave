package api

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	lwmcp "github.com/loreweave/loreweave_mcp"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// toolInputSchemaJSON drives the REAL in-process tools/list (same pattern as
// mcp_prefix_contract_test.go) and returns the named tool's advertised inputSchema.
// Reading the wire — not the struct — is the whole point: the M0a bug lived in what the
// reflector EMITTED, which no handler-level test can see.
func toolInputSchemaJSON(t *testing.T, name string) map[string]any {
	t.Helper()
	s := mcpTestServer(GrantOwner)
	srv := s.newMCPServer()

	ctx := context.Background()
	ct, st := mcp.NewInMemoryTransports()
	if _, err := srv.Connect(ctx, st, nil); err != nil {
		t.Fatalf("server connect: %v", err)
	}
	client := mcp.NewClient(&mcp.Implementation{Name: "save-draft-schema-test", Version: "0"}, nil)
	cs, err := client.Connect(ctx, ct, nil)
	if err != nil {
		t.Fatalf("client connect: %v", err)
	}
	defer cs.Close()

	res, err := cs.ListTools(ctx, nil)
	if err != nil {
		t.Fatalf("ListTools: %v", err)
	}
	for _, tool := range res.Tools {
		if tool.Name != name {
			continue
		}
		raw, err := json.Marshal(tool.InputSchema)
		if err != nil {
			t.Fatalf("marshal inputSchema: %v", err)
		}
		var out map[string]any
		if err := json.Unmarshal(raw, &out); err != nil {
			t.Fatalf("unmarshal inputSchema: %v", err)
		}
		return out
	}
	t.Fatalf("tool %q not advertised in tools/list", name)
	return nil
}

// REGRESSION (M0a, 2026-07-13) — book_chapter_save_draft's `body` was a json.RawMessage,
// which the Go MCP schema reflector renders as {"type":"array","items":{"type":"integer"}}
// (a []byte IS an array of bytes). The tool therefore ADVERTISED "give me a list of integers"
// for a chapter of prose: no model could ever satisfy it. The flagship wrote good prose, failed
// this call 3x, and left a titled chapter row with ZERO prose — which a count-based check read
// as "a drafted chapter". The tool had never once been callable by an agent with real content.
//
// This test pins the WIRE SCHEMA, not the handler: a handler test cannot catch a defect whose
// whole nature is that the advertised contract is impossible to satisfy.
func TestSaveDraftSchema_BodyIsProseNotAByteArray(t *testing.T) {
	schema := toolInputSchemaJSON(t, "book_chapter_save_draft")

	body, ok := schema["properties"].(map[string]any)["body"].(map[string]any)
	if !ok {
		t.Fatalf("body property missing from schema: %v", schema)
	}
	if got := body["type"]; got != "string" {
		t.Fatalf("body.type = %v, want \"string\" (prose). A non-string here means the reflector "+
			"turned it back into a byte/array shape no model can fill.", got)
	}
	// the exact bug: items:{type:integer}
	if items, present := body["items"]; present {
		t.Fatalf("body must not declare `items` (got %v) — that is the []byte→array-of-integers "+
			"regression that made this tool uncallable", items)
	}
	// the description must actually tell the model to write prose
	desc, _ := body["description"].(string)
	if !strings.Contains(strings.ToLower(desc), "prose") {
		t.Errorf("body.description should tell the model to write PROSE; got %q", desc)
	}
}

// NEGATIVE CONTROL — proves TestSaveDraftSchema_BodyIsProseNotAByteArray is not vacuous.
//
// A test that cannot fail on its own bug class is worse than none. Here the bug class is
// "the schema reflector turns a json.RawMessage body into an array of integers". This asserts
// that the reflector REALLY does that — so the assertions above (type=="string", no `items`)
// are the exact predicate that discriminates the broken shape from the fixed one. If a future
// SDK stopped emitting array-of-integers for []byte, this test reds and tells us the guard
// upstairs has gone toothless, instead of silently passing forever.
// brokenProbeIn carries the EXACT pre-fix shape: body as a json.RawMessage.
type brokenProbeIn struct {
	Body json.RawMessage `json:"body" jsonschema:"the new draft body (Tiptap JSON object)"`
}

func TestSaveDraftSchema_ByteArrayShapeIsTheBugClass_NotVacuous(t *testing.T) {
	// Register a throwaway tool carrying the OLD shape and read its schema off the wire —
	// the same surface the real defect lived on.
	srv := mcp.NewServer(&mcp.Implementation{Name: "negctl", Version: "0"}, nil)
	addTool(srv, "book_negctl_probe", "probe",
		lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, nil),
		func(_ context.Context, _ *mcp.CallToolRequest, _ brokenProbeIn) (*mcp.CallToolResult, struct{}, error) {
			return nil, struct{}{}, nil
		})

	ctx := context.Background()
	ct, st := mcp.NewInMemoryTransports()
	if _, err := srv.Connect(ctx, st, nil); err != nil {
		t.Fatalf("connect: %v", err)
	}
	client := mcp.NewClient(&mcp.Implementation{Name: "negctl-client", Version: "0"}, nil)
	cs, err := client.Connect(ctx, ct, nil)
	if err != nil {
		t.Fatalf("client connect: %v", err)
	}
	defer cs.Close()
	res, err := cs.ListTools(ctx, nil)
	if err != nil {
		t.Fatalf("ListTools: %v", err)
	}
	var raw []byte
	for _, tool := range res.Tools {
		if tool.Name == "book_negctl_probe" {
			raw, _ = json.Marshal(tool.InputSchema)
		}
	}
	if raw == nil {
		t.Fatal("probe tool not advertised")
	}
	var got map[string]any
	if err := json.Unmarshal(raw, &got); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	body, ok := got["properties"].(map[string]any)["body"].(map[string]any)
	if !ok {
		t.Fatalf("no body in reflected schema: %s", raw)
	}
	// The reflector emits a UNION: {"type":["null","array"], "items":{"type":"integer",0..255}}
	// — literally "a list of bytes". That is what the tool advertised for a chapter of prose.
	if !schemaTypeIncludes(body["type"], "array") {
		t.Fatalf("expected the []byte→array bug class, got type=%v (schema: %s). "+
			"If the reflector changed, the guard above may no longer discriminate.", body["type"], raw)
	}
	items, _ := body["items"].(map[string]any)
	if items["type"] != "integer" {
		t.Fatalf("expected items.type=integer (the array-of-BYTES shape), got %v", items["type"])
	}
	if items["maximum"] != float64(255) {
		t.Errorf("expected the byte range (max 255), got %v — is this really []byte?", items["maximum"])
	}
	// …and that is precisely the shape the real tool must NOT advertise.
}

// schemaTypeIncludes handles a JSON-schema `type` that is either a string or a union list.
func schemaTypeIncludes(v any, want string) bool {
	switch t := v.(type) {
	case string:
		return t == want
	case []any:
		for _, x := range t {
			if s, ok := x.(string); ok && s == want {
				return true
			}
		}
	}
	return false
}

// saveDraftBody is the normalizer the handler relies on — prove each declared format.
func TestSaveDraftBody_NormalizesEachFormat(t *testing.T) {
	// plain (default) → a Tiptap doc carrying the prose
	doc, err := saveDraftBody("Line one.\n\nLine two.", "")
	if err != nil {
		t.Fatalf("plain: %v", err)
	}
	if !json.Valid(doc) || !strings.Contains(string(doc), "Line one.") {
		t.Fatalf("plain body did not normalize into a doc carrying the prose: %s", doc)
	}
	// json → round-trip an existing Tiptap doc
	raw := `{"type":"doc","content":[{"type":"paragraph","_text":"kept"}]}`
	doc, err = saveDraftBody(raw, "json")
	if err != nil || string(doc) != raw {
		t.Fatalf("json round-trip failed: %s / %v", doc, err)
	}
	// json + invalid → rejected honestly, never silently swallowed
	if _, err = saveDraftBody("not json", "json"); err == nil {
		t.Fatal("invalid json body must be rejected")
	}
	// unknown format → rejected (closed set, not a silent fallback)
	if _, err = saveDraftBody("x", "yaml"); err == nil {
		t.Fatal("unknown body_format must be rejected")
	}
}
