// Package textdiff computes a line-level diff between two plain-text documents
// (used by the chapter-revision compare endpoint). The output is a flat list of
// equal/insert/delete line ops driving both the inline (git-style) and the
// side-by-side views on the frontend. Word-level refinement within a changed
// line is a frontend presentation concern — this package stays line-level.
package textdiff

import "strings"

// Op is the kind of a diff line.
type Op string

const (
	OpEqual  Op = "equal"  // unchanged line (present on both sides)
	OpInsert Op = "insert" // present only on the right (b)
	OpDelete Op = "delete" // present only on the left (a)
)

// Line is one diff op.
type Line struct {
	Op   Op     `json:"op"`
	Text string `json:"text"`
}

// maxCells caps the LCS DP table. Above it, an O(n·m) table would be too large
// (memory + latency), so we fall back to a whole-document replace. 4M cells ≈
// a 2000×2000 line pair — far beyond any real chapter.
const maxCells = 4_000_000

// Lines computes a line diff transforming a → b. The result, read top to bottom,
// reconstructs a (equal+delete) and b (equal+insert). The bool is true when the
// perf guard tripped and the diff was degraded to a full replace.
func Lines(a, b string) ([]Line, bool) {
	// Identical fast-path (also covers left==right compare): all equal.
	if a == b {
		return allOps(a, OpEqual), false
	}
	aLines := splitLines(a)
	bLines := splitLines(b)

	// Strip the common prefix and suffix BEFORE the O(n·m) DP. Edits are almost
	// always localized, so a large chapter with a small change collapses to a
	// tiny changed middle — the perf guard then never trips for the common case.
	var head, tail []Line
	p := 0
	for p < len(aLines) && p < len(bLines) && aLines[p] == bLines[p] {
		head = append(head, Line{Op: OpEqual, Text: aLines[p]})
		p++
	}
	aMid, bMid := aLines[p:], bLines[p:]
	s := 0
	for s < len(aMid) && s < len(bMid) && aMid[len(aMid)-1-s] == bMid[len(bMid)-1-s] {
		s++
	}
	if s > 0 {
		for k := len(aMid) - s; k < len(aMid); k++ {
			tail = append(tail, Line{Op: OpEqual, Text: aMid[k]})
		}
		aMid = aMid[:len(aMid)-s]
		bMid = bMid[:len(bMid)-s]
	}

	if len(aMid)*len(bMid) > maxCells {
		// Degraded: keep the common head/tail equal, replace the whole middle.
		out := make([]Line, 0, len(head)+len(aMid)+len(bMid)+len(tail))
		out = append(out, head...)
		out = append(out, opsFor(aMid, OpDelete)...)
		out = append(out, opsFor(bMid, OpInsert)...)
		out = append(out, tail...)
		return out, true
	}

	// LCS dynamic-programming table over the trimmed middle. lcs[i][j] = length
	// of the longest common subsequence of aMid[i:] and bMid[j:].
	n, m := len(aMid), len(bMid)
	lcs := make([][]int, n+1)
	for i := range lcs {
		lcs[i] = make([]int, m+1)
	}
	for i := n - 1; i >= 0; i-- {
		for j := m - 1; j >= 0; j-- {
			if aMid[i] == bMid[j] {
				lcs[i][j] = lcs[i+1][j+1] + 1
			} else if lcs[i+1][j] >= lcs[i][j+1] {
				lcs[i][j] = lcs[i+1][j]
			} else {
				lcs[i][j] = lcs[i][j+1]
			}
		}
	}

	// Backtrack to emit ops in document order. A delete is emitted before an
	// insert at the same divergence point so the left/right reconstruct cleanly.
	out := make([]Line, 0, len(head)+n+m+len(tail))
	out = append(out, head...)
	i, j := 0, 0
	for i < n && j < m {
		if aMid[i] == bMid[j] {
			out = append(out, Line{Op: OpEqual, Text: aMid[i]})
			i++
			j++
		} else if lcs[i+1][j] >= lcs[i][j+1] {
			out = append(out, Line{Op: OpDelete, Text: aMid[i]})
			i++
		} else {
			out = append(out, Line{Op: OpInsert, Text: bMid[j]})
			j++
		}
	}
	for ; i < n; i++ {
		out = append(out, Line{Op: OpDelete, Text: aMid[i]})
	}
	for ; j < m; j++ {
		out = append(out, Line{Op: OpInsert, Text: bMid[j]})
	}
	out = append(out, tail...)
	return out, false
}

// splitLines splits on "\n". An empty document yields zero lines (not one empty
// line) so an empty side contributes no ops.
func splitLines(s string) []string {
	if s == "" {
		return nil
	}
	return strings.Split(s, "\n")
}

func opsFor(lines []string, op Op) []Line {
	out := make([]Line, 0, len(lines))
	for _, l := range lines {
		out = append(out, Line{Op: op, Text: l})
	}
	return out
}

func allOps(s string, op Op) []Line {
	return opsFor(splitLines(s), op)
}
