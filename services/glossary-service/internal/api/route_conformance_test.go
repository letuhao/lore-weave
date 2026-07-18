package api

// OpenAPI ROUTE-CONFORMANCE gate (D-GLOSSARY-CONTRACT-FIRST, spec
// docs/specs/2026-07-18-glossary-contract-first-restoration.md).
//
// Contract-first was aspirational for glossary: ~149 public /v1 routes are served
// but the OpenAPI YAMLs (contracts/api/glossary-service/) document ~30, are stale,
// and NOTHING checks the docs against the code — so the entity route family grew
// for weeks undocumented and no test caught it. This test makes contract-first
// LIVED: it walks the REAL router, parses the REAL contract, and reds on drift in
// BOTH directions. Mirrors mcp_tool_schema_contract_test.go (enumerate expected,
// assert reality, red on drift).
//
// Scope (SD-1): only routes whose pattern starts with /v1/ are contract-subject.
// /health, /metrics, /mcp, /mcp/admin, /internal/* are exempt BY PREFIX (infra /
// MCP-transport / service-to-service — a distinct contract-consumer story).
//
// The two directions:
//   - No undocumented /v1 route — every walked /v1 (method,path) is in the contract
//     OR in testdata/route_coverage_exempt.txt (the shrinking backfill allowlist).
//   - No phantom contract path — every documented /v1 (method,path) is actually
//     routed (catches a YAML describing a renamed/removed route). No allowlist here:
//     a documented path that isn't served is always a doc bug.
//   - Honest allowlist (SD-5) — every allowlist entry must still be walked AND still
//     undocumented; a stale entry reds ("regenerate").
//
// Add a public /v1 route without a contract entry → this test names it and fails.
// Deliberate exemption (or after documenting a family) → regenerate the allowlist:
//   REGEN_ROUTE_ALLOWLIST=1 go test ./internal/api/ -run TestOpenAPIRouteConformance
// (the repo's WRITE_FRONTEND_CONTRACT=1 idiom.)

import (
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"testing"

	"github.com/go-chi/chi/v5"

	"github.com/loreweave/glossary-service/internal/config"
)

const (
	contractDir   = "../../../../contracts/api/glossary-service"
	allowlistPath = "testdata/route_coverage_exempt.txt"
	// phantomExemptPath holds documented-but-NOT-yet-routed contract paths that are
	// intentional (contract-first AHEAD of implementation), NOT stale docs — SD-8's
	// "documented-but-unbuilt intent, handled case-by-case." Today: the /v1/canon/*
	// L5.F canon RPC family, whose YAMLs declare the impl "a separate sub-program"
	// (Q-L5A-1) that glossary-service does not (yet) serve. Kept HONEST (like SD-5):
	// an entry that becomes routed, or whose YAML is deleted, reds — so building the
	// canon sub-program forces a real conformance check instead of a silent pass.
	phantomExemptPath = "testdata/route_phantom_unbuilt.txt"
	// A 32-char dummy — NewServer only requires len(JWTSecret) >= 32 to build the
	// secret slice; Router() never touches the DB (the pool is dereferenced only
	// inside handlers at request time), so a nil pool walks fine.
	conformanceDummySecret = "conformance-test-dummy-secret-32ch"
)

var braceParamRe = regexp.MustCompile(`\{[^}]*\}`)

// Structural matchers for the OpenAPI `paths:` block. We line-scan rather than
// full-parse: these YAMLs carry unquoted colons in prose descriptions ("Carried in
// `Authorization: Bearer <svid>`") that a strict lexer rejects mid-document, yet the
// path/method structure is trivially regular — path keys at 2-space indent, method
// keys at 4-space. Indentation makes this immune to colons inside deeper-indented
// (8-space) description block-scalars.
var (
	pathsSectionRe = regexp.MustCompile(`^paths:\s*$`)
	topLevelKeyRe  = regexp.MustCompile(`^[^\s#]`) // a column-0 key ends the paths block
	yamlPathKeyRe  = regexp.MustCompile(`^  (/\S*):\s*$`)
	yamlMethodRe   = regexp.MustCompile(`^    (get|post|put|patch|delete):\s*(#.*)?$`)
)

// normalizePath makes the two sides param-name-AGNOSTIC (SD-2): every path param
// {book_id}/{bookId}/{name:regex} and every wildcard segment * collapses to {}, and
// a trailing slash is stripped. So chi's ".../books/{book_id}/entities/{entity_id}"
// and OpenAPI's ".../books/{bookId}/entities/{id}" both key the same.
func normalizePath(p string) string {
	p = braceParamRe.ReplaceAllString(p, "{}")
	if strings.Contains(p, "*") {
		segs := strings.Split(p, "/")
		for i, s := range segs {
			if s == "*" {
				segs[i] = "{}"
			}
		}
		p = strings.Join(segs, "/")
	}
	if len(p) > 1 {
		p = strings.TrimRight(p, "/")
	}
	return p
}

// routeKey is the per-(method, normalized-path) comparison unit (SD-3).
func routeKey(method, path string) string {
	return strings.ToLower(method) + " " + normalizePath(path)
}

// walkedV1Routes returns the set of normalized (method,path) keys the service
// actually serves under /v1/ (SD-1 prefix filter applied).
func walkedV1Routes(t *testing.T) map[string]bool {
	t.Helper()
	srv := NewServer(nil, &config.Config{JWTSecret: conformanceDummySecret})
	router, ok := srv.Router().(chi.Routes)
	if !ok {
		t.Fatal("Router() did not return a chi.Routes — cannot walk the route tree")
	}
	got := map[string]bool{}
	err := chi.Walk(router, func(method, route string, _ http.Handler, _ ...func(http.Handler) http.Handler) error {
		if !strings.HasPrefix(route, "/v1/") {
			return nil // SD-1: infra / mcp / internal are prefix-exempt
		}
		got[routeKey(method, route)] = true
		return nil
	})
	if err != nil {
		t.Fatalf("chi.Walk failed: %v", err)
	}
	return got
}

// documentedV1Routes parses every contract YAML and returns the set of normalized
// (method,path) keys documented under /v1/.
func documentedV1Routes(t *testing.T) map[string]bool {
	t.Helper()
	entries, err := os.ReadDir(contractDir)
	if err != nil {
		t.Fatalf("read contract dir %s: %v", contractDir, err)
	}
	documented := map[string]bool{}
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".yaml") {
			continue
		}
		raw, err := os.ReadFile(filepath.Join(contractDir, e.Name()))
		if err != nil {
			t.Fatalf("read %s: %v", e.Name(), err)
		}
		inPaths := false
		currentPath := ""
		for _, line := range strings.Split(strings.ReplaceAll(string(raw), "\r\n", "\n"), "\n") {
			switch {
			case pathsSectionRe.MatchString(line):
				inPaths = true
				currentPath = ""
			case inPaths && topLevelKeyRe.MatchString(line):
				// left the paths block (e.g. `components:`) — stop scanning this file.
				inPaths = false
			case inPaths:
				if m := yamlPathKeyRe.FindStringSubmatch(line); m != nil {
					currentPath = m[1]
				} else if m := yamlMethodRe.FindStringSubmatch(line); m != nil && strings.HasPrefix(currentPath, "/v1/") {
					documented[routeKey(m[1], currentPath)] = true
				}
			}
		}
	}
	return documented
}

// exemptComments reads a testdata exemption file into route-key → trailing comment
// (the "# <class>: <reason>" text, or "" if none). Each line is "method /normalized/
// path" optionally followed by that comment (SD-9); blank / full-comment lines are
// skipped. Missing file → empty map.
func exemptComments(t *testing.T, path string) map[string]string {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return map[string]string{}
		}
		t.Fatalf("read %s: %v", path, err)
	}
	out := map[string]string{}
	for _, line := range strings.Split(strings.ReplaceAll(string(raw), "\r\n", "\n"), "\n") {
		comment := ""
		if i := strings.Index(line, "#"); i >= 0 {
			comment = strings.TrimSpace(line[i:])
			line = line[:i]
		}
		key := strings.TrimSpace(line)
		if key == "" {
			continue // blank or full-comment line
		}
		out[key] = comment
	}
	return out
}

// loadExemptFile reads a testdata exemption file into a set of route keys.
func loadExemptFile(t *testing.T, path string) map[string]bool {
	t.Helper()
	set := map[string]bool{}
	for k := range exemptComments(t, path) {
		set[k] = true
	}
	return set
}

func TestOpenAPIRouteConformance(t *testing.T) {
	walked := walkedV1Routes(t)
	documented := documentedV1Routes(t)

	// The undocumented /v1 set = walked − documented. It's the backfill debt.
	var undocumented []string
	for k := range walked {
		if !documented[k] {
			undocumented = append(undocumented, k)
		}
	}
	sort.Strings(undocumented)

	// REGEN (SD-4) — write the current undocumented set as the allowlist, each a
	// "# backfill" line (the shrinking debt), and stop. Mirrors WRITE_FRONTEND_CONTRACT=1.
	if os.Getenv("REGEN_ROUTE_ALLOWLIST") == "1" {
		if err := os.MkdirAll(filepath.Dir(allowlistPath), 0o755); err != nil {
			t.Fatalf("mkdir testdata: %v", err)
		}
		// Preserve any existing per-route comment class (SD-9) — a maintainer-set
		// "# permanent: <reason>" must survive a regen run (regen is triggered to add
		// a NEW backfill route, and must not silently revert an unrelated route's class).
		existing := exemptComments(t, allowlistPath)
		var b strings.Builder
		b.WriteString("# glossary-service — route-coverage exemptions (D-GLOSSARY-CONTRACT-FIRST).\n")
		b.WriteString("# GENERATED by REGEN_ROUTE_ALLOWLIST=1 go test -run TestOpenAPIRouteConformance.\n")
		b.WriteString("# Each line: <method> <normalized /v1 path>. \"# backfill\" = undocumented /v1\n")
		b.WriteString("# route awaiting an OpenAPI entry (the shrinking debt); document it in\n")
		b.WriteString("# contracts/api/glossary-service/ then regenerate to remove it. \"# permanent: <reason>\"\n")
		b.WriteString("# = a /v1 route that legitimately never gets a public contract entry (rare);\n")
		b.WriteString("# set it by hand — regen PRESERVES an existing class for a still-present route.\n")
		for _, k := range undocumented {
			comment := "# backfill"
			if c := existing[k]; c != "" {
				comment = c // carry forward a hand-set # permanent: / annotated class
			}
			b.WriteString(k + " " + comment + "\n")
		}
		if err := os.WriteFile(allowlistPath, []byte(b.String()), 0o644); err != nil {
			t.Fatalf("write allowlist: %v", err)
		}
		t.Logf("REGEN: wrote %d undocumented /v1 routes to %s", len(undocumented), allowlistPath)
		return
	}

	allow := loadExemptFile(t, allowlistPath)
	phantomExempt := loadExemptFile(t, phantomExemptPath)

	// Direction 1 (SD-1/-4/-6) — no undocumented /v1 route that isn't allowlisted.
	var undocNotExempt []string
	for _, k := range undocumented {
		if !allow[k] {
			undocNotExempt = append(undocNotExempt, k)
		}
	}
	if len(undocNotExempt) > 0 {
		t.Errorf("%d public /v1 route(s) are UNDOCUMENTED and not exempt:\n  %s\n"+
			"→ add each to a contract in contracts/api/glossary-service/, OR for a deliberate "+
			"exemption run: REGEN_ROUTE_ALLOWLIST=1 go test ./internal/api/ -run TestOpenAPIRouteConformance",
			len(undocNotExempt), strings.Join(undocNotExempt, "\n  "))
	}

	// Direction 2 (SD-8) — no phantom contract path. A documented (method,path) that
	// isn't routed is a stale/renamed doc, UNLESS it's an explicit unbuilt-ahead-of-impl
	// exemption (phantomExempt). No backfill: a genuine phantom is fixed in the YAML.
	var phantom []string
	for k := range documented {
		if !walked[k] && !phantomExempt[k] {
			phantom = append(phantom, k)
		}
	}
	if len(phantom) > 0 {
		sort.Strings(phantom)
		t.Errorf("%d contract path(s) are PHANTOM (documented but not routed) — a renamed/removed "+
			"route, or a param/path typo the SD-2 normalization can't bridge:\n  %s\n"+
			"→ fix or delete the entry in contracts/api/glossary-service/ (documented ≠ served is always a doc "+
			"bug), OR — if it's an intentional contract-ahead-of-impl — add it with a reason to %s",
			len(phantom), strings.Join(phantom, "\n  "), phantomExemptPath)
	}

	// SD-8 honesty — every phantom-exempt entry must STILL be documented AND STILL not
	// walked. If it became routed (the sub-program shipped) or its YAML was deleted, the
	// exemption is stale → red, forcing a real conformance check.
	var stalePhantom []string
	for k := range phantomExempt {
		if !documented[k] {
			stalePhantom = append(stalePhantom, k+"  (no longer documented — remove the exemption)")
		} else if walked[k] {
			stalePhantom = append(stalePhantom, k+"  (now routed — remove the exemption; it's a real route to keep documented)")
		}
	}
	if len(stalePhantom) > 0 {
		sort.Strings(stalePhantom)
		t.Errorf("%d STALE phantom-exemption(s) in %s:\n  %s",
			len(stalePhantom), phantomExemptPath, strings.Join(stalePhantom, "\n  "))
	}

	// SD-5 — honest allowlist: every entry must STILL be walked AND STILL undocumented.
	// A removed route, or one since documented, left in the file → red.
	undocumentedSet := map[string]bool{}
	for _, k := range undocumented {
		undocumentedSet[k] = true
	}
	var stale []string
	for k := range allow {
		if !undocumentedSet[k] {
			reason := "no longer an undocumented /v1 route"
			if !walked[k] {
				reason = "route no longer exists"
			} else if documented[k] {
				reason = "route is now documented — remove from allowlist"
			}
			stale = append(stale, k+"  ("+reason+")")
		}
	}
	if len(stale) > 0 {
		sort.Strings(stale)
		t.Errorf("%d STALE allowlist entr(y/ies) in %s:\n  %s\n"+
			"→ regenerate: REGEN_ROUTE_ALLOWLIST=1 go test ./internal/api/ -run TestOpenAPIRouteConformance",
			len(stale), allowlistPath, strings.Join(stale, "\n  "))
	}
}
