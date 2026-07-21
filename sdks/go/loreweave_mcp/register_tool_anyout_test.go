package loreweave_mcp

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// An Out=any tool (a GateOrConfirm tool returns a task-handle OR a card) must get an
// explicit VALID object outputSchema — not the SDK's inferred `properties.result` empty
// schema that strict federation validators (ai-gateway) reject, which would drop the
// whole provider's tools from the catalog.
func TestRegisterTool_AnyOut_HasValidObjectOutputSchema(t *testing.T) {
	srv := mcp.NewServer(&mcp.Implementation{Name: "d", Version: "0.0.1"}, nil)
	RegisterTool(srv, &mcp.Tool{Name: "gate_tool", Description: "returns a handle or a card"},
		func(ctx context.Context, _ *mcp.CallToolRequest, _ struct{}) (*mcp.CallToolResult, any, error) {
			return nil, map[string]any{"ok": true}, nil
		})
	cs := connectInMemory(t, srv)
	res, err := cs.ListTools(context.Background(), &mcp.ListToolsParams{})
	if err != nil {
		t.Fatalf("ListTools: %v", err)
	}
	var found *mcp.Tool
	for _, tl := range res.Tools {
		if tl.Name == "gate_tool" {
			found = tl
		}
	}
	if found == nil || found.OutputSchema == nil {
		t.Fatalf("gate_tool missing or has nil outputSchema: %+v", found)
	}
	raw, _ := json.Marshal(found.OutputSchema)
	s := string(raw)
	if !strings.Contains(s, `"type":"object"`) {
		t.Fatalf("outputSchema is not a top-level object: %s", s)
	}
	// It must NOT be the inferred wrapper whose `result` property is the bare
	// permissive schema the gateway rejects.
	if strings.Contains(s, `"properties"`) && strings.Contains(s, `"result"`) {
		t.Fatalf("outputSchema still carries the inferred properties.result wrapper: %s", s)
	}
}
