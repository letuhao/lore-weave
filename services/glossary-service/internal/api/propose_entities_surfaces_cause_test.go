package api

// T13-D2 — a failed item must not discard its cause.
//
// `proposeNewEntity` wraps every failure with the operation that produced it ("begin tx: …",
// "book lock: …", "entity lookup: …", "tombstone check: …", "create draft: …"). The batch
// handler replaced ALL of it with the constant "propose failed", and logged nothing, so a
// failed item was undiagnosable from both ends at once.
//
// MEASURED LIVE 2026-08-13 (session 019ffa96): a single-item propose returned
// results[0] = {"status":"error","error":"propose failed"} and `docker logs glossary-service`
// had nothing for the request. After surfacing the cause the very first re-run printed it:
//
//	create draft: kind 6730db4a-… has no display attribute (neither 'name' nor 'term'):
//	refusing to create a nameless entity, which cannot be deduped or linked
//
// — a real, specific, actionable condition that had been invisible.
//
// The wrapped error can carry storage detail, so it goes to the LOG; the caller gets a message
// that says what KIND of failure it is. That distinction is the actionable part: the old text
// left "fix your argument" and "the database is down" indistinguishable, so a model could only
// retry the identical item.

import (
	"os"
	"strings"
	"testing"
)

func proposeBatchSource(t *testing.T) string {
	t.Helper()
	b, err := os.ReadFile("entity_batch_tools.go")
	if err != nil {
		t.Fatalf("cannot read entity_batch_tools.go: %v — this guard has gone blind", err)
	}
	return string(b)
}

func TestTheItemFailureCauseIsLogged(t *testing.T) {
	src := proposeBatchSource(t)
	idx := strings.Index(src, "s.proposeNewEntity(ctx, bookID, kindID, name")
	if idx < 0 {
		t.Fatal("the proposeNewEntity call site moved — re-point this guard")
	}
	branch := src[idx:]
	if end := strings.Index(branch, "res.EntityID = entityID.String()"); end > 0 {
		branch = branch[:end]
	}
	if !strings.Contains(branch, "slog.Error") {
		t.Error("the failed-item branch no longer logs — the wrapped cause is discarded and the " +
			"failure becomes undiagnosable server-side (T13-D2)")
	}
	if !strings.Contains(branch, `"error", err`) {
		t.Error("the log no longer carries the wrapped error itself, so the operation that failed " +
			"(begin tx / book lock / entity lookup / create draft) is lost")
	}
	for _, k := range []string{`"book_id"`, `"name"`, `"kind"`} {
		if !strings.Contains(branch, k) {
			t.Errorf("the log omits %s — a cause with no subject cannot be traced to the call", k)
		}
	}
}

func TestTheCallerIsToldItIsNotTheirArgument(t *testing.T) {
	src := proposeBatchSource(t)
	if strings.Contains(src, `"error", "propose failed"`) {
		t.Error(`the constant "propose failed" is back: it collapses every distinct cause into ` +
			`four words that leave "fix your argument" and "the database is down" ` +
			`indistinguishable, so a model can only retry the identical item (T13-D2)`)
	}
	if !strings.Contains(src, "server-side failure") {
		t.Error("the caller-facing message no longer says the failure is server-side, which is " +
			"the one thing that tells a caller retrying will not help")
	}
}

func TestTheSiblingBranchesStillSurfaceTheirOwnCauses(t *testing.T) {
	// CONTROL. The branches that ALREADY surfaced a caller-fixable cause must keep doing so —
	// this fix must not sweep them into the generic server-side message.
	src := proposeBatchSource(t)
	for _, want := range []string{`"unknown kind: "+kind`, `res.Status, res.Error = "error", err.Error()`} {
		if !strings.Contains(src, want) {
			t.Errorf("a caller-fixable cause stopped being surfaced verbatim: %s", want)
		}
	}
}
