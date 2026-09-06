package api

import (
	"os"
	"strings"
	"testing"
)

// TOOLV2 LOOP #308 — a refusal whose own prescribed remedy could not clear it.
//
// world_delete is otherwise correct, and the parts that matter were measured live:
//
//	world_create -> world 019ff362-ca23-7d4b-ad51-c349d1015fd7, bible book …ca24, chapter …ca26,
//	                all three `active`, purge_eligible_at NULL
//	world_delete -> {"deleted": true}; the worlds row is gone (count 0) and BOTH the bible book
//	                and its chapter are `purge_pending` with purge_eligible_at stamped
//	world_delete on an unknown UUID -> "world not found" (owner-scoped, no existence oracle)
//
// The defect was the member-book guard. Measured, `world_move_book` accepts a book that is
// already `trashed` ({"moved": true}), and the world then refuses to delete:
//
//	"world still has 1 member book(s) — move or delete them first (deleting the world would
//	 orphan them)"
//
// Neither remedy in that sentence clears it:
//
//   - "delete them first" — `delete_book` transitions a book to `trashed` (mcp_actions.go), and
//     `trashed` was counted. Doing exactly what the message says changes nothing.
//   - "move them out (world_move_book to another world)" — world_id is REQUIRED and must parse as
//     a UUID. null, omitted and "" were each rejected live, so there is no detach; moving only
//     hands the block to the next world, which then cannot be deleted either.
//
// The one state that DID clear the count was `purge_pending`, reachable only via `purge_book` —
// "PERMANENTLY purging a trashed book (irreversible)". So a guard whose stated purpose is to stop
// the user's books being discarded had permanent destruction as its only exit.
//
// Excluding `trashed` alongside `purge_pending` makes the message's own remedy work.
func TestWorldDeleteGuardIgnoresAlreadyDiscardedBooks(t *testing.T) {
	q := guardQuery(t)
	for _, state := range []string{"purge_pending", "trashed"} {
		if !strings.Contains(q, "'"+state+"'") {
			t.Errorf("the member-book count no longer excludes %q — a book the user has already "+
				"discarded blocks the delete, and the refusal's own remedy cannot clear it", state)
		}
	}
	if strings.Contains(q, "lifecycle_state!='purge_pending'") {
		t.Error("the guard is back to excluding only purge_pending; `delete_book` yields `trashed`, " +
			"so following the refusal literally leaves the count unchanged")
	}
}

// The exclusion must not widen past discarded books: an ACTIVE member book is exactly what the
// guard exists for, and SET-NULLing it is the implicit orphaning an agent must not do.
func TestWorldDeleteGuardStillCountsActiveBooks(t *testing.T) {
	q := guardQuery(t)
	if strings.Contains(q, "'active'") {
		t.Error("'active' appears in the guard's exclusion list — a live member book would no " +
			"longer block the delete, which removes the guard rather than fixing it")
	}
	if !strings.Contains(q, "is_bible=false") {
		t.Error("the count must stay non-bible: the hidden world-bible is purged deliberately " +
			"below and must never count as a member blocking its own world")
	}
	if !strings.Contains(q, "owner_user_id=$2") {
		t.Error("the count must stay owner-scoped, or a non-owner learns whether a world exists " +
			"from the refusal instead of getting a uniform not-found")
	}
}

// `delete_book` is the verb the refusal names. If it ever stops producing `trashed`, the state the
// guard excludes and the state the remedy produces have drifted apart again — which is the whole
// defect, in the opposite direction.
func TestTheRemedyTheRefusalNamesProducesAnExcludedState(t *testing.T) {
	src := mustReadFile(t, "mcp_actions.go")
	i := strings.Index(src, `case "delete_book", "purge_book":`)
	if i < 0 {
		t.Fatal("the delete_book/purge_book branch is gone; the refusal names a verb that no longer exists")
	}
	branch := src[i:]
	if j := strings.Index(branch, "\n\tcase "); j > 0 {
		branch = branch[:j]
	}
	if !strings.Contains(branch, `target := "trashed"`) {
		t.Error("delete_book no longer lands on `trashed`; the guard's exclusion list was written " +
			"to match the state this verb produces")
	}
	if !strings.Contains(branch, `target = "purge_pending"`) {
		t.Error("purge_book no longer lands on `purge_pending`")
	}
}

// The bible book is purged rather than SET-NULLed — a world-less hidden book is collected by no
// sweeper. Measured live: book and chapter both `purge_pending` with purge_eligible_at stamped.
func TestTheBibleIsPurgedNotStranded(t *testing.T) {
	src := mustReadFile(t, "mcp_worlds_verbs_s07.go")
	for _, want := range []string{
		"UPDATE chapters SET lifecycle_state='purge_pending'",
		"UPDATE books SET lifecycle_state='purge_pending'",
		"is_bible=true",
		"DELETE FROM worlds WHERE id=$1 AND owner_user_id=$2",
	} {
		if !strings.Contains(src, want) {
			t.Errorf("the bible purge lost %q — a world delete would leave an active, world-less "+
				"hidden book that no sweeper collects", want)
		}
	}
}

// guardQuery returns just the member-book count statement, so an assertion cannot accidentally
// match one of the several other lifecycle predicates in the world files.
func guardQuery(t *testing.T) string {
	t.Helper()
	src := mustReadFile(t, "mcp_worlds_verbs_s07.go")
	i := strings.Index(src, "SELECT count(*) FROM books")
	if i < 0 {
		t.Fatal("the member-book guard query is gone")
	}
	end := strings.Index(src[i:], "`")
	if end < 0 {
		t.Fatal("the guard query is unterminated")
	}
	return src[i : i+end]
}

func mustReadFile(t *testing.T, name string) string {
	t.Helper()
	b, err := os.ReadFile(name)
	if err != nil {
		t.Fatalf("read %s: %v", name, err)
	}
	return string(b)
}
