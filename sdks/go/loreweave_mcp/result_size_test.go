package loreweave_mcp

import (
	"context"
	"strings"
	"testing"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type bigOut struct {
	Blob string `json:"blob"`
}

func TestResultSize_UnderTheCeilingPasses(t *testing.T) {
	if err := checkResultSize("glossary_search", bigOut{Blob: strings.Repeat("x", 100)}); err != nil {
		t.Fatalf("a small result must pass, got: %v", err)
	}
}

// The one that matters. `glossary_list_system_standards` shipped a 44,254-byte result: 86%
// of it attribute definitions the caller could not act on. gemma called it 24 times in one
// run and built nothing — each call pushed the previous answer out of the window, so the
// model never saw what it had already fetched. Every unit test was green.
func TestResultSize_TheFortyFourKilobyteBombIsRejected(t *testing.T) {
	err := checkResultSize("glossary_list_system_standards", bigOut{Blob: strings.Repeat("x", 44_254)})
	if err == nil {
		t.Fatal("a 44KB tool result must be REJECTED — this is the exact payload that made the " +
			"agent loop 24 times and build nothing")
	}
	var tooLarge *ErrResultTooLarge
	if !asErrResultTooLarge(err, &tooLarge) {
		t.Fatalf("want *ErrResultTooLarge, got %T", err)
	}
	if tooLarge.Tool != "glossary_list_system_standards" {
		t.Fatalf("the error must name the offending tool, got %q", tooLarge.Tool)
	}
	// The message has to be actionable for BOTH readers: the agent (do not retry) and the
	// human (fix the tool).
	msg := err.Error()
	for _, want := range []string{"BUG IN THE TOOL", "Do not retry", "paginate"} {
		if !strings.Contains(msg, want) {
			t.Fatalf("the error must say %q — it is read by the model AND by whoever fixes the tool.\ngot: %s", want, msg)
		}
	}
}

func TestResultSize_TheCeilingIsTunableByEnv(t *testing.T) {
	t.Setenv("LW_MCP_RESULT_MAX_BYTES", "50")
	if err := checkResultSize("tiny_tool", bigOut{Blob: strings.Repeat("x", 200)}); err == nil {
		t.Fatal("a lowered ceiling must be honoured (services ratchet this down as tools are fixed)")
	}
	t.Setenv("LW_MCP_RESULT_MAX_BYTES", "100000")
	if err := checkResultSize("tiny_tool", bigOut{Blob: strings.Repeat("x", 200)}); err != nil {
		t.Fatalf("a raised ceiling must be honoured, got: %v", err)
	}
}

// The gate is ON by default. A soft warning would be filed under "known noise" within a
// week; an error gets the tool fixed. This test fails if anyone makes it opt-in.
func TestResultSize_IsOnByDefault(t *testing.T) {
	if ResultMaxBytes() != defaultResultMaxBytes {
		t.Fatalf("the hard ceiling must default to %d with no env set, got %d",
			defaultResultMaxBytes, ResultMaxBytes())
	}
	if err := checkResultSize("some_tool", bigOut{Blob: strings.Repeat("x", defaultResultMaxBytes+1)}); err == nil {
		t.Fatal("with NO env configured, a payload over the default ceiling must still be rejected")
	}
}

func asErrResultTooLarge(err error, target **ErrResultTooLarge) bool {
	e, ok := err.(*ErrResultTooLarge)
	if ok {
		*target = e
	}
	return ok
}

// ── the WIRING: the gate must fire through the REAL RegisterTool + wire path ──
//
// checkResultSize passing in isolation proves the check works. It does NOT prove the check
// is CONNECTED — and an unwired guard is worse than none, because it reads as protection.
// This goes through the same in-memory client/server round trip every real MCP call takes.

type bombOut struct {
	Blob string `json:"blob"`
}

func TestResultSizeGate_FiresThroughTheRealToolCallPath(t *testing.T) {
	srv := mcp.NewServer(&mcp.Implementation{Name: "test", Version: "0.0.1"}, nil)
	RegisterTool(srv, &mcp.Tool{Name: "context_bomb"},
		func(ctx context.Context, req *mcp.CallToolRequest, in struct{}) (*mcp.CallToolResult, bombOut, error) {
			// the exact size the real glossary tool shipped
			return nil, bombOut{Blob: strings.Repeat("x", 44_254)}, nil
		})
	cs := connectInMemory(t, srv)
	defer cs.Close()

	res, err := cs.CallTool(context.Background(), &mcp.CallToolParams{Name: "context_bomb"})
	if err == nil && (res == nil || !res.IsError) {
		t.Fatal("a 44KB tool result went straight through the real call path — the gate is " +
			"NOT wired into RegisterTool. This is the bug that cost a flagship scenario.")
	}
}

func TestResultSizeGate_DoesNotBreakANormalTool(t *testing.T) {
	srv := mcp.NewServer(&mcp.Implementation{Name: "test", Version: "0.0.1"}, nil)
	RegisterTool(srv, &mcp.Tool{Name: "normal_tool"},
		func(ctx context.Context, req *mcp.CallToolRequest, in struct{}) (*mcp.CallToolResult, bombOut, error) {
			return nil, bombOut{Blob: "a perfectly reasonable answer"}, nil
		})
	cs := connectInMemory(t, srv)
	defer cs.Close()

	res, err := cs.CallTool(context.Background(), &mcp.CallToolParams{Name: "normal_tool"})
	if err != nil {
		t.Fatalf("a normal tool must still work: %v", err)
	}
	if res.IsError {
		t.Fatalf("a normal tool must not be gated: %+v", res.Content)
	}
}
