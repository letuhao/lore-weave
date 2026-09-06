package api

import (
	"strings"
	"testing"
)

// TOOLV2 LOOP #312 — a list that drops the rows it cannot read, and calls the remainder complete.
//
// world_map_list works: live, it returned exactly the maps in a world, empty [] for a world with
// none, "world_id must be a UUID" for a malformed id, and a foreign world's maps are unreachable
// because the query is owner-scoped.
//
// The defect was in how it read the rows:
//
//	if rows.Scan(...) == nil { maps = append(maps, d) }
//
// A scan failure SKIPPED the row and the tool still returned success. There was no rows.Err()
// check either, so an iteration error part-way through — a dropped connection — handed the caller
// the prefix as though it were the whole set. Nothing distinguishes "this world has two maps" from
// "this world has five maps and three of them failed to read".
//
// What makes it clearly a defect rather than a style choice is that toolWorldMapGet, TWENTY LINES
// UP IN THE SAME FILE, refuses this exact shape in a comment: "A sub-query / scan / iteration
// error is a TOOL FAILURE, not an empty result — otherwise a transient DB error on the markers
// read returns a map with all its pins silently dropped, presented as authoritative (the
// silent-success bug class)." The neighbouring handler named the hazard; the list handler had it.
//
// Grepping the mechanism found four more in the same feature, so this asserts over all five by
// name rather than the one under test. The worst was world_list: its pagination envelope is built
// from len(worlds), so a dropped row misreports `returned` against a `total` that comes from a
// separate COUNT — and a caller paging on next_offset would step straight over the lost record.
func TestNoWorldOrMapListSkipsARowItCannotRead(t *testing.T) {
	for _, site := range []struct{ file, what string }{
		{"mcp_maps.go", "world_map_list"},
		{"mcp_worlds.go", "world_list"},
		{"worlds.go", "the REST world + world-book lists"},
	} {
		src := mustReadFile(t, site.file)
		blocks := rowLoopBodies(src)
		if len(blocks) == 0 {
			t.Fatalf("%s: no row loops found — the guard is no longer looking at anything", site.file)
		}
		for _, b := range blocks {
			// Scoped to the LOOP BODY on purpose: `QueryRow(...).Scan(&x); err == nil` is a
			// legitimate idempotency lookup elsewhere in these files, and a whole-file match
			// would fail on the code that is right.
			for _, bad := range []string{"if rows.Scan(", "); err == nil {"} {
				if strings.Contains(b, bad) {
					t.Errorf("%s (%s): a row read inside a for-rows loop is guarded by %q, so a "+
						"scan failure drops the row and the shortened list is returned as the "+
						"complete set", site.file, site.what, bad)
				}
			}
		}
	}
}

// rowLoopBodies returns the body of every `for <x>rows.Next() {` loop in src, so an assertion
// applies to row iteration and nothing else.
func rowLoopBodies(src string) []string {
	var out []string
	for _, head := range []string{"for rows.Next() {", "for mrows.Next() {", "for rrows.Next() {"} {
		rest := src
		for {
			i := strings.Index(rest, head)
			if i < 0 {
				break
			}
			body := rest[i+len(head):]
			// The loop ends at the first line that closes it at one tab of indentation.
			if j := strings.Index(body, "\n\t}"); j > 0 {
				body = body[:j]
			}
			out = append(out, body)
			rest = rest[i+len(head):]
		}
	}
	return out
}

// An iteration error truncates the result set without any row ever failing to scan. Every list in
// this feature must check it, or a dropped connection is indistinguishable from a short list.
func TestEveryWorldAndMapListChecksTheIterationError(t *testing.T) {
	for _, site := range []struct {
		file  string
		lists int
	}{
		{"mcp_maps.go", 3},  // map_list + map_get's markers and regions
		{"mcp_worlds.go", 1}, // world_list
		{"worlds.go", 3},     // listWorlds + the two world-book lists
	} {
		src := mustReadFile(t, site.file)
		// The ":= " prefix is load-bearing: "mrows.Err()" CONTAINS "rows.Err()", so counting the
		// bare names double-counts and a removed guard stays green. Caught by injecting exactly
		// that removal and watching this test pass anyway.
		got := strings.Count(src, ":= rows.Err()") +
			strings.Count(src, ":= mrows.Err()") +
			strings.Count(src, ":= rrows.Err()")
		if got < site.lists {
			t.Errorf("%s: %d iteration-error checks for %d list reads — a truncated read would be "+
				"returned as a complete list", site.file, got, site.lists)
		}
	}
}

// The pagination envelope is the reason world_list was the worst of the five: it is computed from
// the slice length, so a silently dropped row corrupts the page math as well as the page.
func TestWorldListPageMathCannotBeFedADroppedRow(t *testing.T) {
	src := mustReadFile(t, "mcp_worlds.go")
	env := strings.Index(src, `listPage("worlds", len(worlds), total, offset, "world_list")`)
	if env < 0 {
		t.Fatal("the world_list pagination envelope is gone")
	}
	fail := strings.LastIndex(src[:env], `errors.New("failed to list worlds")`)
	loop := strings.LastIndex(src[:env], "for rows.Next()")
	if fail < loop {
		t.Error("the scan/iteration failure no longer returns before the envelope is built — " +
			"`returned` would be computed from a list that quietly lost rows, while `total` " +
			"still came from the COUNT")
	}
}
