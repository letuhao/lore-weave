package textdiff

import (
	"strings"
	"testing"
)

// reconstruct rebuilds the left (equal+delete) and right (equal+insert) docs
// from the op stream — the core invariant a diff must satisfy.
func reconstruct(lines []Line) (string, string) {
	var left, right []string
	for _, l := range lines {
		switch l.Op {
		case OpEqual:
			left = append(left, l.Text)
			right = append(right, l.Text)
		case OpDelete:
			left = append(left, l.Text)
		case OpInsert:
			right = append(right, l.Text)
		}
	}
	return strings.Join(left, "\n"), strings.Join(right, "\n")
}

func countOp(lines []Line, op Op) int {
	n := 0
	for _, l := range lines {
		if l.Op == op {
			n++
		}
	}
	return n
}

func TestLines_Identical(t *testing.T) {
	a := "one\ntwo\nthree"
	out, trunc := Lines(a, a)
	if trunc {
		t.Fatal("identical should not truncate")
	}
	if countOp(out, OpInsert) != 0 || countOp(out, OpDelete) != 0 {
		t.Fatalf("identical → only equal ops, got %+v", out)
	}
	if countOp(out, OpEqual) != 3 {
		t.Fatalf("want 3 equal lines, got %d", countOp(out, OpEqual))
	}
}

func TestLines_EmptyLeft_AllInsert(t *testing.T) {
	out, _ := Lines("", "a\nb")
	if countOp(out, OpInsert) != 2 || countOp(out, OpEqual) != 0 || countOp(out, OpDelete) != 0 {
		t.Fatalf("empty left → all insert, got %+v", out)
	}
}

func TestLines_EmptyRight_AllDelete(t *testing.T) {
	out, _ := Lines("a\nb", "")
	if countOp(out, OpDelete) != 2 || countOp(out, OpInsert) != 0 {
		t.Fatalf("empty right → all delete, got %+v", out)
	}
}

func TestLines_CommonPrefixSuffix_ChangedMiddle(t *testing.T) {
	a := "intro\nold middle\noutro"
	b := "intro\nnew middle line\noutro"
	out, trunc := Lines(a, b)
	if trunc {
		t.Fatal("small input should not truncate")
	}
	// intro + outro survive as equal; the middle is delete(old)+insert(new).
	if countOp(out, OpEqual) != 2 {
		t.Fatalf("want 2 equal (intro,outro), got %d in %+v", countOp(out, OpEqual), out)
	}
	if countOp(out, OpDelete) != 1 || countOp(out, OpInsert) != 1 {
		t.Fatalf("want 1 delete + 1 insert, got %+v", out)
	}
	// the reconstruct invariant must hold
	left, right := reconstruct(out)
	if left != a || right != b {
		t.Fatalf("reconstruct mismatch:\n left=%q want %q\n right=%q want %q", left, a, right, b)
	}
}

func TestLines_FullReplace(t *testing.T) {
	out, _ := Lines("aaa\nbbb", "xxx\nyyy")
	if countOp(out, OpEqual) != 0 {
		t.Fatalf("no common lines → 0 equal, got %+v", out)
	}
	left, right := reconstruct(out)
	if left != "aaa\nbbb" || right != "xxx\nyyy" {
		t.Fatalf("reconstruct mismatch: left=%q right=%q", left, right)
	}
}

func TestLines_ReconstructInvariant_Interleaved(t *testing.T) {
	a := "a\nb\nc\nd\ne"
	b := "a\nB\nc\nD\ne\nf"
	out, _ := Lines(a, b)
	left, right := reconstruct(out)
	if left != a {
		t.Fatalf("left reconstruct: got %q want %q", left, a)
	}
	if right != b {
		t.Fatalf("right reconstruct: got %q want %q", right, b)
	}
	// common a,c,e survive
	if countOp(out, OpEqual) != 3 {
		t.Fatalf("want 3 equal (a,c,e), got %d", countOp(out, OpEqual))
	}
}

func TestLines_TrailingNewline(t *testing.T) {
	// a trailing newline produces a trailing empty line on one side only
	out, _ := Lines("x", "x\n")
	if countOp(out, OpEqual) != 1 || countOp(out, OpInsert) != 1 {
		t.Fatalf("trailing newline → 1 equal + 1 insert(empty), got %+v", out)
	}
}

func TestLines_LargeDocSmallEdit_NoTruncate(t *testing.T) {
	// /review-impl MED#1: a large chapter with a localized edit must NOT trip
	// the perf guard — common prefix/suffix is stripped before the DP, so the
	// changed middle is tiny.
	lines := make([]string, 3000)
	for i := range lines {
		lines[i] = "line " + string(rune('a'+i%26))
	}
	a := strings.Join(lines, "\n")
	bLines := append([]string(nil), lines...)
	bLines[1500] = "CHANGED LINE"
	b := strings.Join(bLines, "\n")

	out, trunc := Lines(a, b)
	if trunc {
		t.Fatal("localized edit in a large doc must not truncate (prefix/suffix trim)")
	}
	if countOp(out, OpDelete) != 1 || countOp(out, OpInsert) != 1 {
		t.Fatalf("want exactly 1 delete + 1 insert, got del=%d ins=%d",
			countOp(out, OpDelete), countOp(out, OpInsert))
	}
	left, right := reconstruct(out)
	if left != a || right != b {
		t.Fatal("reconstruct mismatch after trim")
	}
}

func TestLines_PerfGuardTruncates(t *testing.T) {
	// build two large, fully-distinct docs that exceed maxCells (2000×2000 = 4M)
	mk := func(prefix string, n int) string {
		lines := make([]string, n)
		for i := range lines {
			lines[i] = prefix
		}
		return strings.Join(lines, "\n") // exactly n lines, no trailing newline
	}
	a := mk("a", 2100)
	b := mk("b", 2100)
	out, trunc := Lines(a, b)
	if !trunc {
		t.Fatal("oversized distinct input must trip the perf guard")
	}
	// degraded = delete-all-a then insert-all-b
	if countOp(out, OpEqual) != 0 {
		t.Fatalf("degraded diff has no equal ops, got %d", countOp(out, OpEqual))
	}
	if countOp(out, OpDelete) != 2100 || countOp(out, OpInsert) != 2100 {
		t.Fatalf("degraded → all delete + all insert, got del=%d ins=%d",
			countOp(out, OpDelete), countOp(out, OpInsert))
	}
}
