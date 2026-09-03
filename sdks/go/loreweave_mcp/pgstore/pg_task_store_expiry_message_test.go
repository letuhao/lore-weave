package pgstore

import (
	"os"
	"strings"
	"testing"
)

// MOVED HERE FROM glossary-service 2026-09-03, WITH THE CODE IT GUARDS. The store was promoted
// into this kit because it existed three times and none of them was an SDK; glossary's copy was
// the one carrying this fix, and book's — the version promoted first — did NOT. Merging the
// SUPERSET is the whole point of a promotion, and this guard is what proves the better half
// survived. Left in glossary it read a path that no longer exists and failed for the wrong reason.
//
// TOOLV2 LOOP #239 — the expiry reason was computed, persisted, and then withheld.
//
// Measured on a real gate task: 60 tasks sat in status input_required, one of them created
// 2026-07-25 with ttl_ms = 600000. Declining it answered:
//
//	task is not awaiting input
//
// while the same call wrote error='task_expired' onto the row. So the store knew the task had
// lapsed 17 days earlier, recorded that fact in the database, and told the only party who needed it
// something generic. A caller looking at a task still listed as input_required is left with a
// refusal it cannot explain.
//
// This is #216's shape in another service: the diagnostic exists and does not reach the wire. The
// error is WRAPPED rather than replaced so errors.Is(err, lwmcp.ErrTaskNotWaiting) keeps working
// for callers that branch on it — sharpening a message must not break the contract around it.
func TestTheExpiryBranchSaysWhyNotJustThatItRefused(t *testing.T) {
	src, err := os.ReadFile("pg_task_store.go")
	if err != nil {
		t.Fatalf("read source: %v", err)
	}
	body := strings.ReplaceAll(string(src), "\r\n", "\n")

	fellThrough := "error='task_expired', updated_at=now()\n\t\t\tWHERE task_id=$1 AND " +
		"status NOT IN ('completed','failed','cancelled')`, taskID)\n\t}\n\treturn nil, lwmcp.ErrTaskNotWaiting"
	if strings.Contains(body, fellThrough) {
		t.Error("the expiry branch falls through to the bare ErrTaskNotWaiting again — " +
			"the reason is written to the row and withheld from the caller")
	}

	if !strings.Contains(body, "it EXPIRED") {
		t.Error("the refusal must name expiry as the cause")
	}
	if !strings.Contains(body, "TTL lapsed before anyone answered it") {
		t.Error("naming the mechanism is what lets a caller tell expiry from 'already resolved'")
	}
	if !strings.Contains(body, "re-run the action") {
		t.Error("a terminal refusal needs a next step, or the caller can only retry identically")
	}
}

// The wrap must preserve the sentinel: existing callers use errors.Is on ErrTaskNotWaiting, and a
// message improvement that silently changes the error identity is a worse bug than the one fixed.
func TestTheWrapKeepsTheSentinelIntact(t *testing.T) {
	src, err := os.ReadFile("pg_task_store.go")
	if err != nil {
		t.Fatalf("read source: %v", err)
	}
	body := strings.ReplaceAll(string(src), "\r\n", "\n")

	if !strings.Contains(body, "fmt.Errorf(") || !strings.Contains(body, "%w") {
		t.Error("the expiry error must WRAP ErrTaskNotWaiting (%w), not replace it")
	}
	if !strings.Contains(body, "lwmcp.ErrTaskNotWaiting, cur.TTLMs)") {
		t.Error("ErrTaskNotWaiting must remain the wrapped sentinel, with the TTL as the detail")
	}
	// The non-expired path keeps returning the bare sentinel — expiry is the only case with a
	// reason to add, and inventing one for 'already resolved' would be a guess.
	if !strings.Contains(body, "\t}\n\treturn nil, lwmcp.ErrTaskNotWaiting") {
		t.Error("the non-expiry terminal path must still return the plain sentinel")
	}
}
