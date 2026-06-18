package expunge

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/loreweave/foundation/tests/conformance/internal/verdict"
)

func writeFile(t *testing.T, dir, name, body string) string {
	t.Helper()
	p := filepath.Join(dir, name)
	if err := os.WriteFile(p, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestLoadValid(t *testing.T) {
	dir := t.TempDir()
	p := writeFile(t, dir, "expunge.yaml", "# header\ncatastrophic-rebuild: DEFERRED-149\nmonthly-l3f: DEFERRED-L3F\n")
	l, err := Load(p)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if l.Len() != 2 {
		t.Fatalf("want 2 entries, got %d", l.Len())
	}
	if !l.Has("catastrophic-rebuild") || l.Has("not-listed") {
		t.Error("Has() wrong")
	}
}

func TestLoadMissingFileIsEmptyNotError(t *testing.T) {
	l, err := Load(filepath.Join(t.TempDir(), "does-not-exist.yaml"))
	if err != nil {
		t.Fatalf("missing file must not error: %v", err)
	}
	if l.Len() != 0 {
		t.Errorf("missing file → empty list, got %d", l.Len())
	}
}

func TestLoadEmptyFileIsEmpty(t *testing.T) {
	dir := t.TempDir()
	p := writeFile(t, dir, "expunge.yaml", "# only a comment\n")
	l, err := Load(p)
	if err != nil {
		t.Fatalf("comment-only file must not error: %v", err)
	}
	if l.Len() != 0 {
		t.Errorf("comment-only → empty list, got %d", l.Len())
	}
}

func TestLoadRejectsUntrackedExpunge(t *testing.T) {
	dir := t.TempDir()
	p := writeFile(t, dir, "expunge.yaml", "some-case: \"\"\n")
	if _, err := Load(p); err == nil {
		t.Fatal("Load must reject an expunge with no Deferred-Items ref")
	}
}

func TestDowngradeFailOnListed(t *testing.T) {
	l := List{refs: map[string]string{"flaky": "DEFERRED-149"}}
	in := []verdict.Result{
		{ID: "flaky", Kind: "lint", Verdict: verdict.Fail, Reason: "boom"},
	}
	out := l.Downgrade(in)

	if out[0].Verdict != verdict.Skip {
		t.Fatalf("expunged fail must become skip, got %q", out[0].Verdict)
	}
	if !strings.Contains(out[0].Reason, "DEFERRED-149") {
		t.Errorf("reason must name the ref: %q", out[0].Reason)
	}
	if !strings.Contains(out[0].Reason, "boom") {
		t.Errorf("reason must preserve the original failure: %q", out[0].Reason)
	}
	if !WasExpunged(out[0]) {
		t.Error("WasExpunged should detect the downgrade")
	}
	if out[0].Verdict.GateBreaking() {
		t.Error("an expunged result must not break the gate")
	}
	// input must not be mutated
	if in[0].Verdict != verdict.Fail {
		t.Error("Downgrade must not mutate its input")
	}
}

func TestDowngradeFailOnUnlistedStaysFail(t *testing.T) {
	l := List{refs: map[string]string{"flaky": "DEFERRED-149"}}
	out := l.Downgrade([]verdict.Result{{ID: "real-bug", Verdict: verdict.Fail}})
	if out[0].Verdict != verdict.Fail {
		t.Errorf("unlisted fail must stay fail, got %q", out[0].Verdict)
	}
	if WasExpunged(out[0]) {
		t.Error("unlisted fail is not expunged")
	}
}

func TestDowngradePassOnListedStaysPass(t *testing.T) {
	// An expunged case that unexpectedly passes still reports pass (xfstests note).
	l := List{refs: map[string]string{"flaky": "DEFERRED-149"}}
	out := l.Downgrade([]verdict.Result{{ID: "flaky", Verdict: verdict.Pass}})
	if out[0].Verdict != verdict.Pass {
		t.Errorf("pass on expunged must stay pass, got %q", out[0].Verdict)
	}
}

func TestDangling(t *testing.T) {
	l := List{refs: map[string]string{"real": "D-1", "ghost": "D-2"}}
	known := map[string]bool{"real": true, "other": true}
	d := l.Dangling(known)
	if len(d) != 1 || d[0] != "ghost" {
		t.Errorf("Dangling should report only the unmatched id, got %v", d)
	}
	if len(l.Dangling(map[string]bool{"real": true, "ghost": true})) != 0 {
		t.Error("no dangling when every expunge id maps to a known case")
	}
}
