package loreweave_mcp

import (
	"context"
	"errors"
	"testing"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type registerToolTestOut struct {
	Value string `json:"value"`
}

// connectInMemory spins up a real client-server pair over the go-sdk's own
// in-memory transport so these tests exercise the ACTUAL wire path (the
// `toolForErr` wrapper's content-duplication logic lives deep inside
// `mcp.AddTool`'s dispatch, not something a unit test can fake without a
// real round trip).
func connectInMemory(t *testing.T, srv *mcp.Server) *mcp.ClientSession {
	t.Helper()
	ctx := context.Background()
	st, ct := mcp.NewInMemoryTransports()
	if _, err := srv.Connect(ctx, st, nil); err != nil {
		t.Fatalf("server connect: %v", err)
	}
	client := mcp.NewClient(&mcp.Implementation{Name: "test-client", Version: "0.0.1"}, nil)
	cs, err := client.Connect(ctx, ct, nil)
	if err != nil {
		t.Fatalf("client connect: %v", err)
	}
	t.Cleanup(func() { _ = cs.Close() })
	return cs
}

// External MCP discoverability audit #9 — every structured tool result used
// to duplicate its full payload into content[0].text (double-encoded, right
// next to the same data in structuredContent). RegisterTool is a drop-in
// replacement for mcp.AddTool that fills content with a short constant
// placeholder instead, whenever the handler itself left Content nil.
func TestRegisterTool_FillsCompactContentInsteadOfDuplicating(t *testing.T) {
	srv := mcp.NewServer(&mcp.Implementation{Name: "test", Version: "0.0.1"}, nil)
	RegisterTool(srv, &mcp.Tool{Name: "echo"},
		func(ctx context.Context, req *mcp.CallToolRequest, in struct{}) (*mcp.CallToolResult, registerToolTestOut, error) {
			return nil, registerToolTestOut{Value: "a real payload that would otherwise be duplicated verbatim"}, nil
		})
	cs := connectInMemory(t, srv)

	res, err := cs.CallTool(context.Background(), &mcp.CallToolParams{Name: "echo"})
	if err != nil {
		t.Fatalf("call tool: %v", err)
	}

	if len(res.Content) != 1 {
		t.Fatalf("Content = %d blocks, want exactly 1 (the compact placeholder)", len(res.Content))
	}
	tc, ok := res.Content[0].(*mcp.TextContent)
	if !ok {
		t.Fatalf("Content[0] is %T, want *mcp.TextContent", res.Content[0])
	}
	if tc.Text != compactContentPlaceholder {
		t.Errorf("Content[0].Text = %q, want the compact placeholder — got the duplicated payload instead", tc.Text)
	}
	if res.StructuredContent == nil {
		t.Fatal("StructuredContent must still be populated — this fix must never touch the field real clients read")
	}
}

// The fix must never clobber a handler that deliberately built its own
// Content (a genuine multi-block or non-JSON result) — it only ever fills a
// NIL Content, never overwrites one a handler explicitly set.
func TestRegisterTool_NeverOverwritesAHandlerBuiltContent(t *testing.T) {
	srv := mcp.NewServer(&mcp.Implementation{Name: "test", Version: "0.0.1"}, nil)
	RegisterTool(srv, &mcp.Tool{Name: "custom"},
		func(ctx context.Context, req *mcp.CallToolRequest, in struct{}) (*mcp.CallToolResult, registerToolTestOut, error) {
			return &mcp.CallToolResult{
				Content: []mcp.Content{&mcp.TextContent{Text: "custom content"}},
			}, registerToolTestOut{Value: "x"}, nil
		})
	cs := connectInMemory(t, srv)

	res, err := cs.CallTool(context.Background(), &mcp.CallToolParams{Name: "custom"})
	if err != nil {
		t.Fatalf("call tool: %v", err)
	}
	tc, ok := res.Content[0].(*mcp.TextContent)
	if !ok || tc.Text != "custom content" {
		t.Errorf("Content[0] = %+v, want the handler's own custom content, untouched", res.Content[0])
	}
}

// A handler error must still surface normally (isError result / returned
// error) — the compact-content fill only applies on the success path.
func TestRegisterTool_ErrorPathUnaffected(t *testing.T) {
	srv := mcp.NewServer(&mcp.Implementation{Name: "test", Version: "0.0.1"}, nil)
	RegisterTool(srv, &mcp.Tool{Name: "fails"},
		func(ctx context.Context, req *mcp.CallToolRequest, in struct{}) (*mcp.CallToolResult, registerToolTestOut, error) {
			return nil, registerToolTestOut{}, errors.New("boom")
		})
	cs := connectInMemory(t, srv)

	res, err := cs.CallTool(context.Background(), &mcp.CallToolParams{Name: "fails"})
	if err != nil {
		t.Fatalf("call tool transport error: %v", err)
	}
	if !res.IsError {
		t.Errorf("IsError = false, want true (handler returned an error)")
	}
}
