package api

// MCP tool-schema CONTRACT guard (W0 #2 — the FE-tools CLOSED_SET_ARGS rule,
// extended to the glossary MCP servers).
//
// A tool arg whose valid values are a FINITE, code-known set MUST declare a real
// JSON-schema `enum` — a closed set living only in description prose is invisible
// to a weak model, which then guesses a value ("Genre", "string", …) and the call
// dies (the live MCP audit measured this as a top-3 hard-error class). This test
// lists every closed-set arg (mirroring chat-service's
// tests/test_frontend_tools_contract.py CLOSED_SET_ARGS) and asserts the ADVERTISED
// inputSchema — read over the real wire path (tools/list) — declares the enum.
//
// Adding a new tool with a closed-set arg? Register the arg here AND build its
// schema with closedSetSchemaFor — a bare string schema turns this test red.

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"sort"
	"strings"
	"testing"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// closedSetArgs maps tool name → the dotted arg paths (arrays via "[]") that MUST
// be enums on the USER/BOOK MCP server (/mcp).
var closedSetArgs = map[string][]string{
	"glossary_book_create":           {"level", "field_type"},
	"glossary_book_patch":            {"level", "field_type"},
	"glossary_book_delete":           {"level"},
	"glossary_book_revert":           {"level"},
	"glossary_book_sync_apply":       {"items[].entity", "items[].choice"},
	"glossary_user_create":           {"level", "field_type"},
	"glossary_user_patch":            {"level", "field_type"},
	"glossary_user_delete":           {"level"},
	"glossary_user_restore":          {"level"},
	"glossary_propose_new_kind":      {"attributes[].field_type"},
	"glossary_propose_kinds":         {"kinds[].attributes[].field_type"},
	"glossary_propose_new_attribute": {"field_type"},
	"glossary_propose_batch":         {"ops[].type"},
	"glossary_propose_status_change": {"status"},
	"glossary_list_merge_candidates": {"status"},
	"glossary_create_chapter_link":   {"relevance"},
	"glossary_create_evidence":       {"evidence_type"},
	"glossary_ontology_upsert":       {"scope", "items[].level", "items[].field_type"},
	"glossary_ontology_delete":       {"scope", "items[].level"},
}

// legacyTaggedTools — CAT-4 (mcp-tool-io.md Part 4): the 6 tools superseded by
// glossary_ontology_upsert/delete MUST carry `_meta.visibility:"legacy"` so both
// federation surfaces (chat-service tool_discovery.py / ai-gateway find-tools.ts)
// exclude them from find_tools/hot-seeding. This is the Go-side half of the drift
// lock those consumer-side tests already prove for their OWN filtering logic —
// this test instead guards the SOURCE data those filters read: a future edit that
// drops the WithVisibility(...) wrapper on any of these 6 (e.g. an accidental
// copy-paste during a refactor) would silently un-hide a superseded tool, and
// nothing else in this repo's Go suite would catch it.
var legacyTaggedTools = []string{
	"glossary_book_create", "glossary_book_patch", "glossary_book_delete",
	"glossary_user_create", "glossary_user_patch", "glossary_user_delete",
	"glossary_propose_new_entity", // superseded by glossary_propose_entities (§3.3)
}

// closedSetAdminArgs — same rule for the SEPARATE admin server (/mcp/admin).
var closedSetAdminArgs = map[string][]string{
	"glossary_admin_propose_create":  {"level", "field_type"},
	"glossary_admin_propose_patch":   {"level", "field_type"},
	"glossary_admin_propose_delete":  {"level"},
	"glossary_admin_propose_restore": {"level"},
}

// closedSetValueSets pins the exact VALUE SETS for the shared closed-set args —
// enum presence alone doesn't catch a silently narrowed/renamed value (W0 #6:
// pin values, not just presence). Keyed by the arg path's LAST segment; args
// not listed here are only checked for enum presence.
var closedSetValueSets = map[string][]string{
	"level":      {"genre", "kind", "attribute"},
	"field_type": {"text", "textarea", "select", "number", "date", "tags", "url", "boolean"},
}

// listToolsWire fetches tools/list over the real streamable-HTTP wire path of the
// user/book server (token-authed), returning name → inputSchema.
func listToolsWire(t *testing.T) map[string]map[string]any {
	t.Helper()
	schemas, _ := listToolsWireFull(t)
	return schemas
}

// listToolsWireFull is listToolsWire plus each tool's `_meta` block (raw, decoded
// as map[string]any) — the CAT-4 visibility drift-lock needs `_meta.visibility`,
// which the schema-only helper above doesn't carry.
func listToolsWireFull(t *testing.T) (map[string]map[string]any, map[string]map[string]any) {
	t.Helper()
	ts := mcpTestServer(t)
	req, _ := http.NewRequest(http.MethodPost, ts.URL,
		strings.NewReader(`{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}`))
	req.Header.Set("X-Internal-Token", "right-token")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json, text/event-stream")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("tools/list request failed: %v", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("tools/list: want 200, got %d (%s)", resp.StatusCode, body)
	}
	var rpc struct {
		Result struct {
			Tools []struct {
				Name        string         `json:"name"`
				InputSchema map[string]any `json:"inputSchema"`
				Meta        map[string]any `json:"_meta"`
			} `json:"tools"`
		} `json:"result"`
	}
	if err := json.Unmarshal(body, &rpc); err != nil {
		t.Fatalf("tools/list: bad JSON: %v (%s)", err, body)
	}
	schemas := make(map[string]map[string]any, len(rpc.Result.Tools))
	metas := make(map[string]map[string]any, len(rpc.Result.Tools))
	for _, tool := range rpc.Result.Tools {
		schemas[tool.Name] = tool.InputSchema
		metas[tool.Name] = tool.Meta
	}
	return schemas, metas
}

// listAdminToolsInMemory lists the admin server's tools over an in-memory MCP
// session (registration only — the HTTP admin-JWT gate is covered elsewhere).
func listAdminToolsInMemory(t *testing.T) map[string]map[string]any {
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
		raw, err := json.Marshal(tool.InputSchema)
		if err != nil {
			t.Fatalf("marshal inputSchema of %s: %v", tool.Name, err)
		}
		var m map[string]any
		if err := json.Unmarshal(raw, &m); err != nil {
			t.Fatalf("unmarshal inputSchema of %s: %v", tool.Name, err)
		}
		out[tool.Name] = m
	}
	return out
}

// schemaNodeAt walks a dotted path (arrays via "[]") into a decoded JSON schema.
func schemaNodeAt(t *testing.T, tool string, schema map[string]any, dotted string) map[string]any {
	t.Helper()
	node := schema
	for _, seg := range strings.Split(dotted, ".") {
		key := strings.TrimSuffix(seg, "[]")
		props, _ := node["properties"].(map[string]any)
		next, _ := props[key].(map[string]any)
		if next == nil {
			t.Fatalf("%s: arg path %q — property %q not in schema", tool, dotted, key)
		}
		node = next
		if strings.HasSuffix(seg, "[]") {
			items, _ := node["items"].(map[string]any)
			if items == nil {
				t.Fatalf("%s: arg path %q — %q has no array items schema", tool, dotted, key)
			}
			node = items
		}
	}
	return node
}

func assertClosedSetEnums(t *testing.T, tools map[string]map[string]any, want map[string][]string) {
	t.Helper()
	names := make([]string, 0, len(want))
	for n := range want {
		names = append(names, n)
	}
	sort.Strings(names)
	for _, name := range names {
		schema, ok := tools[name]
		if !ok {
			t.Errorf("tool %q not advertised (closed-set contract expects it)", name)
			continue
		}
		for _, path := range want[name] {
			node := schemaNodeAt(t, name, schema, path)
			enum, _ := node["enum"].([]any)
			if len(enum) == 0 {
				t.Errorf("%s.%s: closed-set arg MUST declare a JSON-schema enum (got none)", name, path)
				continue
			}
			// The enum must hold at least two real (non-null) choices — a
			// degenerate enum pins nothing.
			nonNull := make([]string, 0, len(enum))
			for _, v := range enum {
				if v != nil {
					nonNull = append(nonNull, toString(v))
				}
			}
			if len(nonNull) < 2 {
				t.Errorf("%s.%s: enum %v has fewer than 2 non-null values", name, path, enum)
			}
			// Value-set pinning: for the canonical shared args, the enum must be
			// EXACTLY the expected set (order-insensitive) — presence alone lets a
			// silently dropped/renamed value ship.
			segs := strings.Split(path, ".")
			if want, pinned := closedSetValueSets[strings.TrimSuffix(segs[len(segs)-1], "[]")]; pinned {
				got := append([]string(nil), nonNull...)
				exp := append([]string(nil), want...)
				sort.Strings(got)
				sort.Strings(exp)
				if strings.Join(got, ",") != strings.Join(exp, ",") {
					t.Errorf("%s.%s: enum value set %v != pinned set %v", name, path, nonNull, want)
				}
			}
		}
	}
}

func toString(v any) string {
	s, _ := v.(string)
	return s
}

// TestMCPClosedSetArgsAreEnums — the user/book /mcp server, over the real wire.
func TestMCPClosedSetArgsAreEnums(t *testing.T) {
	assertClosedSetEnums(t, listToolsWire(t), closedSetArgs)
}

// TestAdminMCPClosedSetArgsAreEnums — the separate /mcp/admin server.
func TestAdminMCPClosedSetArgsAreEnums(t *testing.T) {
	assertClosedSetEnums(t, listAdminToolsInMemory(t), closedSetAdminArgs)
}

// TestLegacyToolsCarryVisibilityMeta — CAT-4 drift lock (see legacyTaggedTools
// doc comment). Reads `_meta.visibility` over the REAL wire, not the Go source,
// so it fails if the wrapper is dropped OR if the SDK ever stops serializing
// `_meta` for a Tool (the passthrough this whole mechanism depends on).
func TestLegacyToolsCarryVisibilityMeta(t *testing.T) {
	_, metas := listToolsWireFull(t)
	for _, name := range legacyTaggedTools {
		meta, ok := metas[name]
		if !ok || meta == nil {
			t.Errorf("%s: no _meta on the wire at all (want visibility:\"legacy\")", name)
			continue
		}
		vis, _ := meta["visibility"].(string)
		if vis != "legacy" {
			t.Errorf("%s: _meta.visibility = %q, want \"legacy\" — CAT-4 requires this tool stay hidden from find_tools/hot-seed", name, vis)
		}
	}
	// Control: the tools that supersede them must NOT be tagged legacy, or they
	// would hide themselves from discovery too.
	for _, name := range []string{"glossary_ontology_upsert", "glossary_propose_entities"} {
		if meta := metas[name]; meta != nil {
			if vis, _ := meta["visibility"].(string); vis == "legacy" {
				t.Errorf("%s must not be legacy-tagged — it's the replacement, not the superseded tool", name)
			}
		}
	}
}

// TestBookPatch409IncludesCurrentVersion pins the W0 #1a contract at the unit
// level: the 409 message embeds the row's CURRENT version so a model can retry
// in one step (the audit's #1 failure class was a 409 retry storm).
func TestBookPatch409IncludesCurrentVersion(t *testing.T) {
	err := errUserPatchConflict("2026-07-01T00:00:00Z")
	if err == nil || !strings.Contains(err.Error(), "2026-07-01T00:00:00Z") {
		t.Fatalf("409 error must embed the current version, got %v", err)
	}
}
