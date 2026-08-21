package guardstatus

// The Go half of the check-status polyglot lock, plus teeth for `Over`.
//
// The contract is generated from `loreweave_guard.CheckStatus`; this reads it. A member
// renamed in Python reds here instead of leaving Go emitting a string no consumer can
// interpret — the closed-set drift the Frontend-Tool Contract exists to prevent, arrived at
// from the backend side.

import (
	"encoding/json"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"testing"
)

func contract(t *testing.T) map[string]any {
	t.Helper()
	// internal/guardstatus -> services/glossary-service -> services -> repo root
	p := filepath.Join("..", "..", "..", "..", "contracts", "guard-status.contract.json")
	raw, err := os.ReadFile(p)
	if err != nil {
		t.Fatalf("read guard-status contract: %v", err)
	}
	var c map[string]any
	if err := json.Unmarshal(raw, &c); err != nil {
		t.Fatalf("parse guard-status contract: %v", err)
	}
	return c
}

func contractStatuses(t *testing.T) map[string]bool {
	t.Helper()
	raw, _ := contract(t)["statuses"].([]any)
	if len(raw) == 0 {
		t.Fatal("contract declares no statuses")
	}
	out := make(map[string]bool, len(raw))
	for _, v := range raw {
		s, _ := v.(string)
		out[s] = true
	}
	return out
}

// declaredStatuses parses THIS package's source for every `X Status = "..."` const, rather
// than listing them in the test. A test that restates its subject checks the author's memory:
// a fourth const added tomorrow would be invisible to a hardcoded list, which is precisely how
// an invented member would reach the wire unnoticed.
func declaredStatuses(t *testing.T) map[string]string {
	t.Helper()
	fset := token.NewFileSet()
	f, err := parser.ParseFile(fset, "guardstatus.go", nil, 0)
	if err != nil {
		t.Fatalf("parse guardstatus.go: %v", err)
	}
	out := map[string]string{}
	ast.Inspect(f, func(n ast.Node) bool {
		vs, ok := n.(*ast.ValueSpec)
		if !ok {
			return true
		}
		id, ok := vs.Type.(*ast.Ident)
		if !ok || id.Name != "Status" {
			return true
		}
		for i, name := range vs.Names {
			if i >= len(vs.Values) {
				continue
			}
			lit, ok := vs.Values[i].(*ast.BasicLit)
			if !ok {
				continue
			}
			out[name.Name] = lit.Value[1 : len(lit.Value)-1] // strip the quotes
		}
		return true
	})
	return out
}

func TestEveryGoStatusExistsInTheContract(t *testing.T) {
	declared := declaredStatuses(t)
	if len(declared) == 0 {
		t.Fatal("parsed no Status consts — the scanner is broken, not the package")
	}
	allowed := contractStatuses(t)
	for name, value := range declared {
		if !allowed[value] {
			t.Fatalf("drift: %s = %q is not in contracts/guard-status.contract.json. Go may "+
				"implement a SUBSET of the vocabulary; it may never invent a member.",
				name, value)
		}
	}
}

func TestTheScannerCanSeeAnInventedMember(t *testing.T) {
	// A control. The assertion above passes trivially if `declaredStatuses` returns nothing,
	// which is exactly what a broken parser returns — so pin that it finds what it should.
	declared := declaredStatuses(t)
	for _, want := range []string{"Checked", "NoSubject", "Degraded"} {
		if _, ok := declared[want]; !ok {
			t.Fatalf("scanner missed the %s const — it would also miss an invented one", want)
		}
	}
	if declared["Degraded"] != "degraded" {
		t.Fatalf("scanner read the wrong value for Degraded: %q", declared["Degraded"])
	}
}

func TestOverSeparatesAnEmptyCorpusFromACleanOneFromADegradedOne(t *testing.T) {
	// The three cases the original defect collapsed into one integer.
	if got := Over(0, 0); got.Status != NoSubject {
		t.Fatalf("empty corpus: want no_subject, got %q", got.Status)
	}
	clean := Over(10, 0)
	if clean.Status != Checked || clean.Checked != 10 || clean.Unchecked != 0 {
		t.Fatalf("clean sweep: %+v", clean)
	}
	// The case that used to be indistinguishable from `clean`: the sweep ran, found nothing,
	// and had never looked at four of the ten.
	partial := Over(10, 4)
	if partial.Status != Degraded {
		t.Fatalf("partial coverage must be degraded, got %q", partial.Status)
	}
	if partial.Checked != 6 || partial.Unchecked != 4 {
		t.Fatalf("partial counts: %+v", partial)
	}
	// …and total failure is the same STATUS with a different count, not a fourth state.
	if all := Over(10, 10); all.Status != Degraded || all.Checked != 0 {
		t.Fatalf("total failure: %+v", all)
	}
}

func TestAPartiallyCheckedSweepIsNotRoundedUpToChecked(t *testing.T) {
	// Pinned separately because "degraded only when EVERYTHING failed" is the tempting
	// version, and it is how the original bug read as success: one failed chunk out of
	// twenty leaves those entities uncompared, and the answer covers less than it claims.
	if got := Over(1000, 1); got.Status != Degraded {
		t.Fatalf("999/1000 compared is still not a complete answer, got %q", got.Status)
	}
}
