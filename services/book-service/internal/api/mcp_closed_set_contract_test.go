package api

// Closed-set contract — a tool arg whose DESCRIPTION enumerates its legal values must
// declare them as a real JSON-Schema `enum`.
//
// WHY THIS EXISTS. The Frontend-Tool Contract's sharpest input rule is "closed-set arg ⇒
// enum", and breaking it shipped a live bug: `panel_id` was advertised as a bare string,
// gemma sent `panel:"editor"`, the resolver matched nothing, and the model then reported
// success for work that never happened. A closed set the schema does not declare is a set
// the model is free to miss — and the miss is SILENT, which is why no suite caught it.
//
// The defect has a signature worth naming, because it is what this test detects: the author
// KNEW the set. They wrote it down — in the description ("the structure operation:
// create_part | rename_part | …") — but in the one place the validator never reads. Prose is
// for the model's judgement; `enum` is for the model's constraints. Writing a closed set
// only as prose keeps the documentation and loses the guarantee.
//
// FOUND LIVE 2026-07-23, auditing all 299 federated tools: four such args, all in this
// service, and two of them (`book_structure_edit.op`, `book_list.kind`) are the ENUM
// DISCRIMINATORS the catalog unification itself introduced — the args where a dispatch miss
// IS the failure mode. glossary-service already had the helper for this
// (`closedSetSchemaFor`); book-service did not, which is exactly how the second service
// ended up without it. The helper now lives in the kit (lwmcp.ClosedSetSchema) and this test
// keeps the rule from decaying again.
//
// Sibling of TestEveryAdvertisedToolMatchesAFederationPrefix: same in-process tools/list
// walk, asserting over the ADVERTISED tools rather than over the source.

import (
	"context"
	"encoding/json"
	"testing"

	lwmcp "github.com/loreweave/loreweave_mcp"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// The CLIENT sees inputSchema as raw JSON (`any`), not the server's typed *jsonschema.Schema
// — so decode the two fields this contract needs. Reading the ADVERTISED bytes (rather than
// the server-side struct) is deliberate: it is what the model actually receives.
type advertisedSchema struct {
	Properties map[string]struct {
		Description string `json:"description"`
		Enum        []any  `json:"enum"`
	} `json:"properties"`
}

func TestEveryEnumeratedClosedSetHasAnEnum(t *testing.T) {
	s := mcpTestServer(GrantOwner)
	srv := s.newMCPServer()

	ctx := context.Background()
	ct, st := mcp.NewInMemoryTransports()
	if _, err := srv.Connect(ctx, st, nil); err != nil {
		t.Fatalf("server connect: %v", err)
	}
	client := mcp.NewClient(&mcp.Implementation{Name: "closed-set-contract-test", Version: "0"}, nil)
	cs, err := client.Connect(ctx, ct, nil)
	if err != nil {
		t.Fatalf("client connect: %v", err)
	}
	defer cs.Close()

	res, err := cs.ListTools(ctx, nil)
	if err != nil {
		t.Fatalf("ListTools: %v", err)
	}
	if len(res.Tools) == 0 {
		t.Fatal("tools/list returned no tools — the catalog failed to register")
	}

	checked := 0
	for _, tool := range res.Tools {
		if tool.InputSchema == nil {
			continue
		}
		raw, err := json.Marshal(tool.InputSchema)
		if err != nil {
			t.Fatalf("%s: marshal inputSchema: %v", tool.Name, err)
		}
		var sch advertisedSchema
		if err := json.Unmarshal(raw, &sch); err != nil {
			t.Fatalf("%s: decode inputSchema: %v", tool.Name, err)
		}
		for name, prop := range sch.Properties {
			vals := lwmcp.EnumeratedValuesInDescription(prop.Description)
			if vals == nil {
				continue
			}
			checked++
			if len(prop.Enum) == 0 {
				t.Errorf(
					"%s.%s enumerates %v in its DESCRIPTION but advertises no `enum` — the "+
						"model is validated against a set the schema never declares, so a near-miss "+
						"value is accepted and silently does nothing (the panel_id bug). Register it "+
						"with addToolClosedSet(..., map[string][]any{%q: {...}}, ...).",
					tool.Name, name, vals, name)
			}
		}
	}

	// Guard the guard. If the detector stops matching anything — a description reworded, or
	// EnumeratedValuesInDescription made too strict — this test would pass vacuously while
	// the rule it protects quietly stopped being enforced.
	if checked == 0 {
		t.Fatal("the detector matched NO enumerated description anywhere in the catalog — " +
			"it has almost certainly gone blind; this test would now pass vacuously")
	}
}

// The detector is the load-bearing half, so pin its edges directly: it must catch the real
// wire strings this service uses, and must NOT fire on prose that merely contains a pipe.
func TestEnumeratedValuesDetector(t *testing.T) {
	cases := []struct {
		desc string
		want int // 0 = must NOT be treated as an enumeration
	}{
		{"the structure operation: create_part | rename_part | reorder_parts | home_chapter | reorder_chapters", 5},
		{"what to list: books | chapters | revisions | scenes (default books)", 4},
		{`how to read body: "plain" (default — prose text) | "markdown" | "json"`, 0}, // parenthetical splits it
		{"when the rule fires: always|scene_match|manual|auto (default always)", 4},
		{"a free-text note about the chapter", 0},
		{"pick the part you want | then tell me which chapter to move", 0}, // prose, has spaces
		{"", 0},
	}
	for _, c := range cases {
		got := lwmcp.EnumeratedValuesInDescription(c.desc)
		if len(got) != c.want {
			t.Errorf("EnumeratedValuesInDescription(%q) = %v (%d values), want %d",
				c.desc, got, len(got), c.want)
		}
	}
}
