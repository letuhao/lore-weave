package api

// MCP `_meta` tier/scope WIRE gate (C-TOOL / Track D S-GLOSSARY meta adoption).
//
// Every glossary MCP tool MUST declare a valid `_meta.tier` + `_meta.scope`. This is
// load-bearing, not cosmetic: a consumer reads `_meta.tier` to gate execution, and an
// ABSENT tier silently defaults to "R" (read/inert) — so an untiered WRITE tool would be
// runnable in read-only `ask` mode AND skip the Tier-A approval card / write budget.
// `lwmcp.RegisterTool` forwards straight to `mcp.AddTool` and does NOT validate meta, so
// nothing else catches an omission. This test asserts over the REAL `tools/list` wire
// output (the user/book /mcp server + the admin /mcp/admin server) so a new tool that
// forgets its meta — or a future SDK that stops serializing `_meta` — goes red here.
//
// It also pins the PAID set (tools that spend real money on/behind their call) and guards
// that no tool spuriously declares `_meta.async` (glossary has no async job-starting tool;
// a future one must be added to asyncTools here AND declare async, or this reds).

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

var validMetaTiers = map[string]bool{"R": true, "A": true, "W": true, "S": true}
var validMetaScopes = map[string]bool{"book": true, "project": true, "user": true, "none": true}

// paidTools — the glossary MCP tools that SPEND real money. web_search + the doc-extractor
// hit a paid provider/LLM SYNCHRONOUSLY on call; plan calls the planner LLM at mint time;
// deep_research's paid web search is gated behind its human confirm (the tool is the paid
// action's entry point + its confirm card shows the cost). All must declare `_meta.paid`.
var paidTools = map[string]bool{
	"glossary_web_search":                true,
	"glossary_plan":                      true,
	"glossary_deep_research":             true,
	"glossary_extract_entities_from_doc": true,
}

// asyncTools — tools that ENQUEUE a background job and return a job id rather than the
// result. Glossary currently has NONE (the entity_research_jobs worker is driven by the
// deep-research CONFIRM effect, not an MCP tool that returns a job id). A future async
// tool MUST be added here AND declare `_meta.async`, or a gate below reds.
var asyncTools = map[string]bool{}

// listAdminToolsMeta lists the admin (/mcp/admin) server's tools over an in-memory MCP
// session and returns name → `_meta` (the embedded mcp.Meta is map[string]any). Mirrors
// listAdminToolsInMemory (mcp_tool_schema_contract_test.go), which reads inputSchema only.
func listAdminToolsMeta(t *testing.T) map[string]map[string]any {
	t.Helper()
	s := &Server{}
	srv := mcp.NewServer(&mcp.Implementation{Name: "glossary-admin-test", Version: "0"}, nil)
	s.RegisterAdminTools(srv)

	ctx := context.Background()
	ct, st := mcp.NewInMemoryTransports()
	if _, err := srv.Connect(ctx, st, nil); err != nil {
		t.Fatalf("server connect: %v", err)
	}
	client := mcp.NewClient(&mcp.Implementation{Name: "test-client", Version: "0"}, nil)
	cs, err := client.Connect(ctx, ct, nil)
	if err != nil {
		t.Fatalf("client connect: %v", err)
	}
	defer cs.Close()
	res, err := cs.ListTools(ctx, nil)
	if err != nil {
		t.Fatalf("ListTools: %v", err)
	}
	out := make(map[string]map[string]any, len(res.Tools))
	for _, tool := range res.Tools {
		// Round-trip through JSON so the values match the on-the-wire shape (bool stays
		// bool, string stays string) exactly like the streamable-HTTP path parses them.
		raw, merr := json.Marshal(map[string]any(tool.Meta))
		if merr != nil {
			t.Fatalf("marshal _meta of %s: %v", tool.Name, merr)
		}
		var m map[string]any
		if uerr := json.Unmarshal(raw, &m); uerr != nil {
			t.Fatalf("unmarshal _meta of %s: %v", tool.Name, uerr)
		}
		out[tool.Name] = m
	}
	return out
}

// allToolMetas merges the two servers' name → `_meta` maps (user/book over the real wire,
// admin over the in-memory session), asserting no name collides across servers.
func allToolMetas(t *testing.T) map[string]map[string]any {
	t.Helper()
	_, wire := listToolsWireFull(t)
	admin := listAdminToolsMeta(t)
	if len(wire) == 0 {
		t.Fatal("tools/list returned no user/book tools")
	}
	if len(admin) == 0 {
		t.Fatal("admin tools/list returned no tools")
	}
	all := make(map[string]map[string]any, len(wire)+len(admin))
	for n, m := range wire {
		all[n] = m
	}
	for n, m := range admin {
		if _, dup := all[n]; dup {
			t.Fatalf("tool %q registered on BOTH the user/book and admin servers", n)
		}
		all[n] = m
	}
	return all
}

// TestMCPEveryToolDeclaresMetaTierAndScope — the core regression gate. Over the REAL wire,
// every tool on BOTH servers declares a valid tier ∈ {R,A,W,S} and scope ∈ {book,project,
// user,none}. A new untiered write (which silently defaults to R and un-gates itself)
// fails here rather than shipping.
func TestMCPEveryToolDeclaresMetaTierAndScope(t *testing.T) {
	for name, meta := range allToolMetas(t) {
		if meta == nil {
			t.Errorf("tool %q carries no _meta on the wire (tier+scope required)", name)
			continue
		}
		tier, _ := meta["tier"].(string)
		if !validMetaTiers[tier] {
			t.Errorf("tool %q has invalid/absent _meta.tier %q — an absent tier defaults to R (inert) and un-gates a write", name, tier)
		}
		scope, _ := meta["scope"].(string)
		if !validMetaScopes[scope] {
			t.Errorf("tool %q has invalid/absent _meta.scope %q (want book|project|user|none)", name, scope)
		}
	}
}

// TestMCPPaidToolsDeclarePaid — the paid set declares `_meta.paid == true`, and a control
// (a read that spends nothing) does NOT — so a spend-bearing tool can't ship without the
// flag a spend gate reads, and the flag doesn't creep onto free tools.
func TestMCPPaidToolsDeclarePaid(t *testing.T) {
	metas := allToolMetas(t)
	for name := range paidTools {
		meta, ok := metas[name]
		if !ok {
			t.Errorf("paid tool %q is not advertised on the wire", name)
			continue
		}
		if paid, _ := meta["paid"].(bool); !paid {
			t.Errorf("tool %q must declare _meta.paid=true (it spends real money)", name)
		}
	}
	// Control: a pure read must NOT be flagged paid.
	if meta := metas["glossary_search"]; meta != nil {
		if paid, _ := meta["paid"].(bool); paid {
			t.Errorf("glossary_search must not declare _meta.paid — it spends nothing")
		}
	}
}

// TestMCPAsyncFlagIsHonest — a tool declaring `_meta.async` must be in asyncTools (the
// known job-starters), and vice-versa. Glossary has none today, so this asserts NO tool
// carries a stray async flag; a future async tool that forgets to register here (or to
// declare async) reds.
func TestMCPAsyncFlagIsHonest(t *testing.T) {
	for name, meta := range allToolMetas(t) {
		declared, _ := meta["async"].(bool)
		want := asyncTools[name]
		if declared && !want {
			t.Errorf("tool %q declares _meta.async but is not a known async job-starter (add it to asyncTools if it truly enqueues a job)", name)
		}
		if want && !declared {
			t.Errorf("tool %q is a known async job-starter but does not declare _meta.async", name)
		}
	}
}
