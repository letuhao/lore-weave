package loreweave_mcp

import (
	"context"
	"strings"
	"testing"

	"github.com/google/jsonschema-go/jsonschema"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// unionOut reproduces the shape that took the whole glossary provider down on
// 2026-07-23: a typed struct with ONE `any`-typed field. The reflector renders
// `Items` as the boolean schema `true`, ai-gateway's validator rejects it, and
// `provider 'glossary' list-tools failed → PARTIAL` erased all 54 sibling tools.
type unionOut struct {
	View  string `json:"view"`
	Items any    `json:"items"`
}

func registerNoop[Out any](t *testing.T, tool *mcp.Tool) {
	t.Helper()
	srv := mcp.NewServer(&mcp.Implementation{Name: "d", Version: "0.0.1"}, nil)
	RegisterTool(srv, tool, func(context.Context, *mcp.CallToolRequest, struct{}) (*mcp.CallToolResult, Out, error) {
		var zero Out
		return nil, zero, nil
	})
}

// A nested `any` FIELD must be caught. This is the case the pre-existing
// `Out = any` substitution in RegisterTool does NOT cover — and the one that shipped.
func TestRegisterTool_NestedAnyField_PanicsWithActionableMessage(t *testing.T) {
	defer func() {
		r := recover()
		if r == nil {
			t.Fatal("registering a tool with a nested `any` field must PANIC — otherwise it " +
				"silently de-federates every tool of this provider")
		}
		msg, _ := r.(string)
		// The message has to name the offending PATH and the fix, or the next person
		// hits the same multi-service, multi-language dead end.
		if !strings.Contains(msg, "outputSchema/properties/items") {
			t.Errorf("panic must name the offending schema path, got: %s", msg)
		}
		if !strings.Contains(msg, "OutputSchema") {
			t.Errorf("panic must point at the fix (declare an explicit schema), got: %s", msg)
		}
	}()
	registerNoop[unionOut](t, &mcp.Tool{Name: "union_tool", Description: "d"})
}

// The escape hatch must work: an explicit schema stating the union's real shape
// registers cleanly. This is the documented fix, so it has to be provably viable.
func TestRegisterTool_ExplicitSchemaForUnion_IsAccepted(t *testing.T) {
	registerNoop[unionOut](t, &mcp.Tool{
		Name: "union_tool_fixed", Description: "d",
		OutputSchema: &jsonschema.Schema{
			Type: "object",
			Properties: map[string]*jsonschema.Schema{
				"view":  {Type: "string"},
				"items": {Type: "array", Items: &jsonschema.Schema{Type: "object"}},
			},
		},
	})
}

// Ordinary typed tools must be unaffected — the go-sdk infers
// `additionalProperties: false` on EVERY struct, so a guard that flagged booleans
// indiscriminately would panic on literally every tool in the repo.
func TestRegisterTool_TypedStruct_NotFlaggedByAdditionalProperties(t *testing.T) {
	type plainOut struct {
		Name  string   `json:"name"`
		Count int      `json:"count"`
		Tags  []string `json:"tags"`
	}
	registerNoop[plainOut](t, &mcp.Tool{Name: "plain_tool", Description: "d"})
}

// Out=any keeps working: register_tool.go substitutes an explicit object schema
// BEFORE this gate runs, so a GateOrConfirm tool (task handle OR confirm card)
// still registers. Guards the interaction between the two mechanisms.
func TestRegisterTool_AnyOut_StillPassesTheGate(t *testing.T) {
	registerNoop[any](t, &mcp.Tool{Name: "gate_tool_ok", Description: "d"})
}

func TestFindBooleanSubschemas_ExemptsNonSubschemaKeywords(t *testing.T) {
	// `additionalProperties`/`uniqueItems`/`deprecated` take real booleans and are
	// NOT subschemas — flagging them would be a false positive on valid schemas.
	// `default`/`const`/`enum`/`examples` hold instance VALUES, so `default: true` on
	// a bool flag is normal: measured live, ALL 12 apparent hits across the Python
	// providers were `.../<flag>/default`. Missing this exemption would panic a
	// service at boot over a boolean default — worse than the bug being prevented.
	schema := map[string]any{
		"type":                 "object",
		"additionalProperties": false,
		"deprecated":           true,
		"properties": map[string]any{
			"tags":    map[string]any{"type": "array", "uniqueItems": true},
			"dry_run": map[string]any{"type": "boolean", "default": true},
			"force":   map[string]any{"type": "boolean", "default": false, "examples": []any{true, false}},
			"mode":    map[string]any{"const": true},
			"flag":    map[string]any{"enum": []any{true, false}},
		},
	}
	if got := findBooleanSubschemas(schema, "t"); len(got) != 0 {
		t.Fatalf("false positive on non-subschema boolean keywords: %v", got)
	}
	// ...but a boolean where a SCHEMA belongs is exactly the defect.
	schema["properties"].(map[string]any)["anything"] = true
	got := findBooleanSubschemas(schema, "t")
	if len(got) != 1 || got[0] != "t/properties/anything" {
		t.Fatalf("want the boolean subschema at t/properties/anything, got %v", got)
	}
}
