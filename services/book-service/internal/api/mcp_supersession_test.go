package api

// CP-4 brick 2 — the supersession edge must be DATA, not prose.
//
// book_list is the first declaration the agent-runtime admits, and it was chosen because it
// "supersedes three legacy tools, so it exercises consolidation, our primary migration operation".
// Measured on the frozen 315-tool baseline (contracts/agent-runtime-baseline/tools-list.snapshot.json)
// on 2026-08-09: 54 tools carry _meta.superseded_by and every single one is composition_* pointing at
// composition_*. Not one book_* tool carried a pointer. The edge existed only as an English sentence
// in a Go comment and in each legacy tool's DEPRECATED description -- readable by a human, joinable
// by nothing.
//
// WithSupersededBy had been in the kit the whole time and composition used it 54 times.
//
// The interesting guard is not the three names below; it is TestSupersessionProseAndDataAgree, which
// takes its expected set from the DESCRIPTIONS the registry actually serves. A hand-typed list would
// have been green on the day this defect shipped, because the defect was that nobody typed the list.

import (
	"context"
	"strings"
	"testing"

	"github.com/modelcontextprotocol/go-sdk/mcp"

	lwmcp "github.com/loreweave/loreweave_mcp"
)

// listBookToolDescriptions — the served description text, from the same real registry
// listBookToolMetas reads. Kept beside it rather than folded into it so the existing helper's
// callers are untouched.
func listBookToolDescriptions(t *testing.T) map[string]string {
	t.Helper()
	s := mcpTestServer(GrantOwner)
	srv := s.newMCPServer()
	ctx := context.Background()
	ct, st := mcp.NewInMemoryTransports()
	if _, err := srv.Connect(ctx, st, nil); err != nil {
		t.Fatalf("server connect: %v", err)
	}
	client := mcp.NewClient(&mcp.Implementation{Name: "book-supersession", Version: "0"}, nil)
	cs, err := client.Connect(ctx, ct, nil)
	if err != nil {
		t.Fatalf("client connect: %v", err)
	}
	defer cs.Close()
	res, err := cs.ListTools(ctx, nil)
	if err != nil {
		t.Fatalf("ListTools: %v", err)
	}
	out := make(map[string]string, len(res.Tools))
	for _, tl := range res.Tools {
		out[tl.Name] = tl.Description
	}
	return out
}

// The reads folded into the unified "ls". Kept explicit as well as derived: this pins the exact
// three the CP-4 board names, so a change to book_list's own scope is a deliberate edit here.
var supersededByBookList = []string{
	"book_list_chapters", "book_list_revisions", "book_scene_list",
}

func TestSupersededByBookListIsDeclared(t *testing.T) {
	metas := listBookToolMetas(t)
	for _, name := range supersededByBookList {
		m, ok := metas[name]
		if !ok {
			t.Errorf("%s NOT registered -- a superseded tool stays registered, never deleted", name)
			continue
		}
		got, _ := m[lwmcp.MetaKeySupersededBy].(string)
		if got != "book_list" {
			t.Errorf("%s _meta.superseded_by=%q, want %q -- without it the consolidation is "+
				"invisible to every consumer and the first admitted declaration produces data that "+
				"cannot be joined to anything (CP-4 brick 2)", name, got, "book_list")
		}
	}
}

// A pointer at a tool nobody can discover is a migration hint into a dead end.
func TestSupersessionTargetsAreDiscoverable(t *testing.T) {
	metas := listBookToolMetas(t)
	for name, m := range metas {
		target, _ := m[lwmcp.MetaKeySupersededBy].(string)
		if target == "" {
			continue
		}
		tm, ok := metas[target]
		if !ok {
			t.Errorf("%s is superseded by %q, which this server does not register -- an agent told "+
				"to migrate has nowhere to go", name, target)
			continue
		}
		if vis, _ := tm[lwmcp.MetaKeyVisibility].(string); vis == string(lwmcp.VisibilityLegacy) {
			t.Errorf("%s is superseded by %q, which is itself tagged legacy -- the replacement is "+
				"hidden from discovery, so the edge points out of the catalogue", name, target)
		}
		if target == name {
			t.Errorf("%s is superseded by itself", name)
		}
	}
}

// TestSupersessionProseAndDataAgree -- the guard that would have caught the shipped defect.
//
// Every legacy book tool whose description TELLS the reader to use another tool must carry that
// same fact as _meta.superseded_by. The expected set is derived from what the registry serves, so a
// fourth folded-in read is covered the moment its description says so -- which is exactly the case
// the three-name list above cannot cover, and exactly how this defect survived: the prose was
// written three times and the data zero times.
func TestSupersessionProseAndDataAgree(t *testing.T) {
	metas := listBookToolMetas(t)
	descs := listBookToolDescriptions(t)

	checked := 0
	for name, desc := range descs {
		m, ok := metas[name]
		if !ok {
			continue
		}
		if vis, _ := m[lwmcp.MetaKeyVisibility].(string); vis != string(lwmcp.VisibilityLegacy) {
			continue
		}
		// "DEPRECATED: use book_list with kind=chapters" / "use book_read with book_id alone"
		idx := strings.Index(desc, "DEPRECATED: use ")
		if idx < 0 {
			continue
		}
		rest := desc[idx+len("DEPRECATED: use "):]
		replacement := rest
		if cut := strings.IndexAny(replacement, " ,.\n"); cut >= 0 {
			replacement = replacement[:cut]
		}
		if _, isTool := metas[replacement]; !isTool {
			continue // the sentence named something that is not a tool on this server
		}
		checked++
		got, _ := m[lwmcp.MetaKeySupersededBy].(string)
		if got != replacement {
			t.Errorf("%s says %q in its description but declares _meta.superseded_by=%q -- the "+
				"prose and the data disagree, and only the data is machine-readable",
				name, "DEPRECATED: use "+replacement, got)
		}
	}
	// A guard whose subject set is empty is green over nothing -- this run has a standard about it.
	if checked == 0 {
		t.Fatal("no legacy tool description matched the DEPRECATED-use form; this guard just " +
			"asserted nothing, so either the convention changed or the extraction is broken")
	}
	t.Logf("checked %d legacy tools whose description names a replacement", checked)
}
