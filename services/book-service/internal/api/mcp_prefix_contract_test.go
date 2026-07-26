package api

// C-GW prefix-enforcement contract (closes the W10-M1 self-disclosed follow-on).
//
// ai-gateway federates each provider's tools under an allowed name-prefix set and
// SILENTLY DROPS any tool whose name escapes it (computeCatalog, the C-GW gate in
// services/ai-gateway/src/federation/catalog.ts:71). A dropped tool is invisible to
// every agent — no error, no test red. That exact drop class has bitten this repo
// THREE times (story_search, then world_* AND lore_* together) and each time the
// unit suites stayed green because they assert over the prefix MAP (providers.spec.ts),
// never over the advertised TOOLS. This test closes the gap AT THE SOURCE: it drives
// the real in-process tools/list and asserts every advertised tool falls under one of
// the book provider's federation namespaces, so a future tool registered under an
// un-federated prefix reds HERE instead of vanishing live.
//
// Keep bookFederationPrefixes in lockstep with ai-gateway config.ts:
//   DEFAULT_PREFIX_MAP.book ('book_') + EXTRA_PREFIX_MAP.book (['world_']).
// Adding a new book-service namespace means: add the prefix here AND to
// EXTRA_PREFIX_MAP.book AND to providers.spec.ts — all three, or one of the two
// sides silently drops the new tools.

import (
	"context"
	"strings"
	"testing"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// bookFederationPrefixes mirrors ai-gateway's allowlist for the `book` provider.
var bookFederationPrefixes = []string{"book_", "world_"}

func TestEveryAdvertisedToolMatchesAFederationPrefix(t *testing.T) {
	s := mcpTestServer(GrantOwner)
	srv := s.newMCPServer()

	ctx := context.Background()
	ct, st := mcp.NewInMemoryTransports()
	if _, err := srv.Connect(ctx, st, nil); err != nil {
		t.Fatalf("server connect: %v", err)
	}
	client := mcp.NewClient(&mcp.Implementation{Name: "prefix-contract-test", Version: "0"}, nil)
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

	for _, tool := range res.Tools {
		matched := false
		for _, p := range bookFederationPrefixes {
			if strings.HasPrefix(tool.Name, p) {
				matched = true
				break
			}
		}
		if !matched {
			t.Errorf("tool %q matches no book-service federation prefix %v — ai-gateway's "+
				"C-GW gate would SILENTLY DROP it from the catalog (invisible to every agent). "+
				"Rename it under book_/world_, or add its prefix to EXTRA_PREFIX_MAP.book in "+
				"services/ai-gateway/src/config/config.ts AND providers.spec.ts AND this test.",
				tool.Name, bookFederationPrefixes)
		}
	}
}
