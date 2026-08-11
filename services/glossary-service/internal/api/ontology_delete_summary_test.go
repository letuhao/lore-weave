package api

import (
	"os"
	"strings"
	"testing"
)

// TOOLV2 LOOP #237 — the delete summary counted no-ops as work, and the description promised an
// undo that cannot happen.
//
// Measured against the live tool, scope=user:
//
//	delete a real kind (first time)  -> status "trashed",         summary {trashed:1, failed:0}
//	delete the same kind again       -> status "already_trashed", summary {trashed:1, failed:0}
//	delete a code that never existed -> status "already_trashed", summary {trashed:1, failed:0}
//
// The per-row status already told the truth; the summary flattened all three into trashed:1. A
// caller deleting five codes of which four are typos was told {trashed: 5} — a count that always
// reads "done" regardless of how much work happened.
//
// The second finding is worse and was found by trying to undo the first delete. The description
// said "reversible soft-delete (undo via glossary_ontology_upsert to re-add)". It is not: the
// soft-deleted row keeps its code, the upsert path is a plain INSERT with no revive-on-conflict,
// and re-adding answers "a user kind with this code already exists". The documented reverse op is
// impossible, which is the same shape as #200's archived motif blocking its own code — except here
// a tool description names the unusable path as the recovery route.
func TestDeleteSummaryCountsByStatusNotByAbsenceOfError(t *testing.T) {
	src, err := os.ReadFile("ontology_tools.go")
	if err != nil {
		t.Fatalf("read source: %v", err)
	}
	body := strings.ReplaceAll(string(src), "\r\n", "\n")

	if strings.Contains(body, "if res.Status == \"error\" {\n\t\t\t\tsummary.Failed++\n\t\t\t} else {\n\t\t\t\tsummary.Trashed++") {
		t.Error("the else-branch is back: an already_trashed row counts as trashed again")
	}
	for _, want := range []string{
		"case \"already_trashed\":",
		"summary.AlreadyTrashed++",
	} {
		if !strings.Contains(body, want) {
			t.Errorf("the summary no longer separates a no-op from real work: missing %q", want)
		}
	}
	// The three counters must reconcile against the item count, which is the property that makes
	// the summary trustworthy at all.
	if !strings.Contains(body, "AlreadyTrashed int `json:\"already_trashed\"`") {
		t.Error("already_trashed must be exposed on the wire, or callers cannot reconcile the totals")
	}
}

// The description must not name a recovery path that does not work. A caller told the delete is
// reversible will not think twice before running it.
func TestTheDescriptionDoesNotPromiseAnUndoThatCannotHappen(t *testing.T) {
	src, err := os.ReadFile("ontology_tools.go")
	if err != nil {
		t.Fatalf("read source: %v", err)
	}
	body := strings.ReplaceAll(string(src), "\r\n", "\n")
	desc := body[strings.Index(body, `Name: "glossary_ontology_delete"`):]
	desc = desc[:strings.Index(desc, "InputSchema:")]

	if strings.Contains(desc, "undo via ") {
		t.Error("the description promises an undo again; upsert cannot re-add a soft-deleted code")
	}
	if !strings.Contains(desc, "KEEPS ITS CODE reserved") {
		t.Error("the description must state why a re-add fails, not merely drop the false claim")
	}
	// #241 CORRECTION: an earlier version of this guard demanded the description call a user-tier
	// delete "one-way from the tool surface". That was wrong — glossary_user_restore revives the
	// row (measured: status "restored", deleted_at cleared). Only ontology_upsert cannot, because
	// the code stays reserved. The description must name the recovery tool that WORKS.
	if !strings.Contains(desc, "glossary_user_restore") {
		t.Error("the description must name the recovery tool that actually works")
	}
	if strings.Contains(desc, "one-way") {
		t.Error("a user-tier delete is NOT one-way; glossary_user_restore undoes it")
	}
}
