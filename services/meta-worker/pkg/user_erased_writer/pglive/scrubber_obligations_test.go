package pglive

import (
	"os"
	"strings"
	"testing"
)

// The three erasure obligations `reality-layer-bite-harness.py` claims to prove,
// finally given tests that exist.
//
// WHY THIS FILE EXISTS
// --------------------
// Three rows in that harness named tests that are not in this repository:
//
//	TestScrubberSourceNamesEveryTableItClaims   (bites 2 and 3)
//	TestRealitiesForUser_IncludesOwnedRealities (bite 4)
//
// `go test -run <a-name-that-does-not-exist>` exits **0** and prints
// `ok <pkg> [no tests to run]`. The harness read that zero as "the mutation did
// not break anything" and printed:
//
//	[VACUOUS] erasure clears the owner id but leaves the tier
//	           -> ... stayed GREEN with the guard broken
//
// which says *the guard is weak*. The truth was *the bite never ran*. Three
// erasure obligations — the GDPR ones, on the tree that holds `owner_user_id` —
// read as measured for as long as the rows have existed. The harness now
// separates the two (`[NOTEST]`), and these are the tests it was looking for.
//
// 🔴 THESE ARE SOURCE TESTS, AND THAT IS A CHOICE WITH A REASON.
// `PgMetaScrubber.meta` is a concrete `*pgxpool.Pool`, not an interface, so
// there is no seam to drive these paths without a live database — and the live
// suites here are gated on `PIIKMS_TEST_PG_URL`, i.e. they do not run per-PR.
// A guard that only runs on the nightly live leg cannot hold a per-PR bite.
// This package already carries the same shape for the same reason
// (`per_reality_pii_test.go`, `meta_erasure_test.go`), and those files say so.
//
// ⚠️ The failure mode of a source test is matching text that is not the
// behaviour — a comment, an import, a doc string. Every assertion below is
// therefore scoped to ONE function's body, never the whole file, and each one
// is proven to red under its own mutation by the bite harness rather than by
// being read and believed. The scoping is load-bearing: `reassignOwnedRealities`
// appears in a comment, in its own `func` line and at the call site, so a
// whole-file search for it would stay green with the call deleted.

// funcBody returns the body of a top-level function, from its `func` line to
// the closing brace in column 0. Gofmt guarantees that brace's position, which
// is why this needs no brace counting (and cannot be fooled by braces inside a
// composite literal or a raw string).
func funcBody(t *testing.T, src, decl string) string {
	t.Helper()
	i := strings.Index(src, decl)
	if i < 0 {
		t.Fatalf("pglive.go no longer declares %q — this test is anchored on a "+
			"function that moved or was renamed; re-point it rather than deleting it", decl)
	}
	rest := src[i:]
	if end := strings.Index(rest, "\n}\n"); end >= 0 {
		return rest[:end]
	}
	t.Fatalf("no column-0 closing brace after %q", decl)
	return ""
}

func pgliveSource(t *testing.T) string {
	t.Helper()
	b, err := os.ReadFile("pglive.go")
	if err != nil {
		t.Fatalf("read pglive.go: %v", err)
	}
	// Anti-vacuity: a truncated or empty read would make every assertion below
	// pass by matching nothing. This file is ~350 lines.
	if len(b) < 4000 {
		t.Fatalf("pglive.go read back as %d bytes — too small to be the real file", len(b))
	}
	return string(b)
}

// Bite 2: "user erasure never reassigns the realities the user owns".
//
// Migration 036 declares `@erasure_method: reassign_to_system_on_user_erasure`
// on `reality_registry`. `ScrubUserMetaRefs` is where that obligation is
// discharged, and it discharges three of them; dropping this one leaves the
// erased user's id on every reality they owned while the scrub reports success.
func TestScrubberReassignsRealitiesOwnedByTheErasedUser(t *testing.T) {
	body := funcBody(t, pgliveSource(t),
		"func (s *PgMetaScrubber) ScrubUserMetaRefs(")
	if !strings.Contains(body, "s.reassignOwnedRealities(ctx, userID)") {
		t.Fatalf("ScrubUserMetaRefs no longer calls reassignOwnedRealities — "+
			"migration 036's @erasure_method is undischarged and the erasure "+
			"would report success with owner_user_id intact.\nbody:\n%s", body)
	}
	// The obligation is only discharged if a failure PROPAGATES. A swallowed
	// error here is the same defect wearing a call.
	if !strings.Contains(body, "if err := s.reassignOwnedRealities(ctx, userID); err != nil {") {
		t.Errorf("the reassignment's error must propagate, not be discarded")
	}
}

// Bite 3: "erasure clears the owner id but leaves the tier (a half-written
// erasure)".
//
// `reality_registry` carries a CHECK that ties `owner_kind` to `owner_user_id`
// (system => NULL id). Writing one without the other is not a partial success;
// it is a row the database will reject, or worse, accept in an inconsistent
// pair. `pglive.go` says so itself: "BOTH columns, together".
func TestReassignWritesBothOwnerColumnsTogether(t *testing.T) {
	body := funcBody(t, pgliveSource(t),
		"func (s *PgMetaScrubber) reassignOwnedRealities(")
	i := strings.Index(body, "NewValues:")
	if i < 0 {
		t.Fatalf("reassignOwnedRealities no longer builds a NewValues map:\n%s", body)
	}
	line := body[i:]
	if end := strings.IndexByte(line, '\n'); end >= 0 {
		line = line[:end]
	}
	for _, want := range []string{`"owner_kind": "system"`, `"owner_user_id": nil`} {
		if !strings.Contains(line, want) {
			t.Errorf("the reassignment must write %s together with the other "+
				"owner column — a half-written pair violates reality_registry's "+
				"owner_system_null CHECK.\ngot: %s", want, line)
		}
	}
}

// Bite 4: "a user who OWNS a reality but drives no actor is invisible to the
// cascade".
//
// `RealitiesForUser` feeds the erasure cascade. Before migration 036 a user
// reached their realities only by DRIVING an actor in one
// (`actor_control_binding`). Ownership arrived and the query did not move with
// it, so a user who owned a reality but drove nothing in it was invisible: the
// cascade skipped every reality they owned. The UNION's second arm is that fix,
// and it is the whole of it.
func TestRealitiesForUser_IncludesOwnedRealities(t *testing.T) {
	body := funcBody(t, pgliveSource(t),
		"func (l *PgUserRealityLookup) RealitiesForUser(")
	for _, want := range []string{
		"actor_control_binding", // the binding arm: drives an actor
		"UNION",
		"reality_registry", // the ownership arm: owns the reality
		"owner_user_id = $1",
	} {
		if !strings.Contains(body, want) {
			t.Errorf("RealitiesForUser must reach realities by OWNERSHIP as well as "+
				"by actor binding; %q is missing, so a user who owns a reality but "+
				"drives no actor in it would survive the erasure cascade.\nbody:\n%s",
				want, body)
		}
	}
}
