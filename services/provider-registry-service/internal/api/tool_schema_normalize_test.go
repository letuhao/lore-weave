package api

import (
	"encoding/json"
	"testing"
)

// A no-argument tool must reach the provider with `properties: {}`.
//
// 🔴 THE MEASUREMENT THIS ENCODES. LM Studio's streaming /v1/responses rejects a function whose
// parameters are an object schema with no `properties`, with HTTP 400 "Invalid input" naming the
// index — and it rejects the WHOLE request, so one such tool kills the turn and every other tool
// in it. Four of 316 catalogue tools shipped that shape, all of them the no-argument ones, and
// the resulting turn death is what D-UPSTREAM-ERROR-WITH-NO-MESSAGE recorded for weeks as
// "the provider reported a failure without saying why".
func params(t *testing.T, tools any, i int) map[string]any {
	t.Helper()
	arr := tools.([]any)
	tm := arr[i].(map[string]any)
	if fn, ok := tm["function"].(map[string]any); ok {
		tm = fn
	}
	p, ok := tm["parameters"].(map[string]any)
	if !ok {
		t.Fatalf("tool %d has no parameters map", i)
	}
	return p
}

func TestANoArgumentToolGetsAnEmptyPropertiesObject(t *testing.T) {
	// The shape as shipped by glossary_list_system_standards, verbatim.
	tools := []any{map[string]any{
		"type": "function",
		"function": map[string]any{
			"name":       "glossary_list_system_standards",
			"parameters": map[string]any{"additionalProperties": false, "type": "object"},
		},
	}}
	got := params(t, normalizeToolParameters(tools), 0)
	props, ok := got["properties"].(map[string]any)
	if !ok {
		t.Fatalf("properties missing or not an object: %v — the provider rejects the WHOLE "+
			"request for this, not just this tool", got)
	}
	if len(props) != 0 {
		t.Errorf("properties = %v, want an EMPTY object", props)
	}
	if got["additionalProperties"] != false {
		t.Errorf("additionalProperties was disturbed: %v", got["additionalProperties"])
	}
}

func TestTheFlatResponsesShapeIsAlsoNormalised(t *testing.T) {
	tools := []any{map[string]any{
		"type": "function", "name": "settings_get_profile",
		"parameters": map[string]any{"type": "object"},
	}}
	if _, ok := params(t, normalizeToolParameters(tools), 0)["properties"]; !ok {
		t.Fatal("the flat (Responses) tool shape was left without properties")
	}
}

// A declared schema must come through untouched. A normaliser that rewrites real properties
// would be a far worse defect than the one it fixes.
func TestADeclaredSchemaIsUntouched(t *testing.T) {
	before := `{"type":"object","properties":{"book_id":{"type":"string"}},"required":["book_id"]}`
	var p map[string]any
	if err := json.Unmarshal([]byte(before), &p); err != nil {
		t.Fatal(err)
	}
	tools := []any{map[string]any{"type": "function", "name": "book_read", "parameters": p}}
	normalizeToolParameters(tools)

	after, _ := json.Marshal(params(t, tools, 0))
	var a, b any
	_ = json.Unmarshal(after, &a)
	_ = json.Unmarshal([]byte(before), &b)
	if string(canonJSON(t, a)) != string(canonJSON(t, b)) {
		t.Errorf("a declared schema was rewritten:\n  before %s\n  after  %s", before, after)
	}
}

// Everything it does not recognise is left exactly as found — including a non-object schema,
// which JSON Schema permits and which `properties` would be meaningless on.
func TestUnrecognisedShapesAreLeftAlone(t *testing.T) {
	cases := []any{
		nil,
		"not a list",
		[]any{"not a map"},
		[]any{map[string]any{"type": "web_search"}},                          // no parameters
		[]any{map[string]any{"type": "function", "parameters": "not a map"}}, // wrong type
		[]any{map[string]any{"type": "function",
			"parameters": map[string]any{"type": "string"}}}, // non-object
	}
	for i, c := range cases {
		func() {
			defer func() {
				if r := recover(); r != nil {
					t.Errorf("case %d panicked: %v", i, r)
				}
			}()
			normalizeToolParameters(c)
		}()
	}
	// The non-object schema specifically must NOT have gained properties.
	last := cases[len(cases)-1]
	p := last.([]any)[0].(map[string]any)["parameters"].(map[string]any)
	if _, has := p["properties"]; has {
		t.Errorf("a non-object schema gained properties: %v", p)
	}
}

// canonJSON re-marshals a decoded value so two schemas compare by CONTENT, not key order.
func canonJSON(t *testing.T, v any) []byte {
	t.Helper()
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	return b
}

// 🔴 THE HELPER PASSING PROVES NOTHING IF NOTHING CALLS IT. Every test above invokes
// normalizeToolParameters directly, so all four stayed green when the call site in
// buildChatStreamInput was reverted — verified by doing exactly that. This one goes through the
// function that assembles the provider request, which is the only thing the wire sees.
func TestTheREQUESTBUILDERNormalisesTools(t *testing.T) {
	in := streamRequest{Tools: []any{map[string]any{
		"type": "function",
		"function": map[string]any{
			"name":       "glossary_list_system_standards",
			"parameters": map[string]any{"additionalProperties": false, "type": "object"},
		},
	}}}

	got := buildChatStreamInput(in)
	tools, ok := got["tools"]
	if !ok {
		t.Fatal("buildChatStreamInput dropped tools entirely")
	}
	if _, has := params(t, tools, 0)["properties"]; !has {
		t.Fatal("the assembled provider request carries a no-argument tool with no " +
			"`properties` — the provider rejects the WHOLE request for this, and the helper " +
			"being correct is no help if the builder does not call it")
	}
}

// No tools at all must stay ABSENT, not become an empty list: `tools: []` is a different
// request from sending none, and providers do not agree on what it means.
func TestNoToolsStaysAbsent(t *testing.T) {
	if _, has := buildChatStreamInput(streamRequest{})["tools"]; has {
		t.Fatal("a request with no tools gained a tools key")
	}
}
