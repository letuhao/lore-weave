package api

// MCP tool-schema CONTRACT guard (mirrors glossary-service's
// internal/api/mcp_tool_schema_contract_test.go — the FE-tools CLOSED_SET_ARGS
// rule, extended to the registry MCP server).
//
// A tool arg whose valid values are a FINITE, code-known set MUST declare a real
// JSON-schema `enum` — a closed set living only in description prose is invisible
// to a weak model, which then guesses a value and the call silently mis-dispatches
// (or the call dies on an unrecognized value). This test lists every closed-set
// arg on the registry MCP server and asserts the ADVERTISED inputSchema — read
// over the real wire path (tools/list) — declares the enum.
//
// Adding a new tool with a closed-set arg? Register the arg here AND build its
// schema with closedSetSchemaFor — a bare string/[]string schema turns this test
// red.

import (
	"encoding/json"
	"io"
	"net/http"
	"sort"
	"strings"
	"testing"
)

// closedSetArgs maps tool name → the dotted arg paths (arrays via "[]") that
// MUST be enums on the registry MCP server.
var closedSetArgs = map[string][]string{
	"registry_list_skills":   {"surface"},
	"registry_propose_skill": {"surfaces[]"},
	"registry_update_skill":  {"surfaces[]"},
}

// closedSetValueSets pins the exact VALUE SET for the shared "surface(s)" arg —
// enum presence alone doesn't catch a silently narrowed/renamed value. Keyed by
// the arg path's LAST segment.
var closedSetValueSets = map[string][]string{
	"surface":  {"chat", "compose", "translate", "admin"},
	"surfaces": {"chat", "compose", "translate", "admin"},
}

// listToolsWire fetches tools/list over the real streamable-HTTP wire path of
// the registry MCP server (token-authed), returning name → inputSchema.
func listToolsWire(t *testing.T) map[string]map[string]any {
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
			} `json:"tools"`
		} `json:"result"`
	}
	if err := json.Unmarshal(body, &rpc); err != nil {
		t.Fatalf("tools/list: bad JSON: %v (%s)", err, body)
	}
	out := make(map[string]map[string]any, len(rpc.Result.Tools))
	for _, tool := range rpc.Result.Tools {
		out[tool.Name] = tool.InputSchema
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
			// Value-set pinning: presence alone lets a silently
			// dropped/renamed value ship — pin the EXACT expected set
			// (order-insensitive).
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

// TestMCPClosedSetArgsAreEnums — the registry /mcp server, over the real wire.
func TestMCPClosedSetArgsAreEnums(t *testing.T) {
	assertClosedSetEnums(t, listToolsWire(t), closedSetArgs)
}
