// Package guardstatus is the Go mirror of the check-status vocabulary.
//
// # The rule it carries
//
// A guard that COULD NOT RUN must not be shaped like a guard that ran and found nothing.
// Python has carried this since S1 as `loreweave_guard.CheckStatus`; the vocabulary stopped at
// the language boundary, and the two worst false-greens this project's red team found were
// both on the far side of it.
//
// The one in this service: `sweepKgDrift` fetches current KG hashes in chunks, and a failed
// chunk was logged and `continue`d. Its entities then reached the compare loop with no current
// hash and took the `!ok` branch — the SAME branch as "the hash is unchanged". The sweep
// returned one number, `flagged`, and reported nothing about how many articles were never
// compared. "The knowledge service was down" and "nothing has drifted" produced byte-identical
// output, and the caller had no field to tell them apart even if it wanted to.
//
// # Why a mirror and not an SDK
//
// The sealed S9 decision: do not extract a fourth guard SDK from one implementation. What is
// shared here is a VOCABULARY, not a mechanism — eleven strings and their ordering — and a
// vocabulary is exactly what a contract file plus a drift test is for. The Go side implements
// the three members it can actually produce and is machine-checked to be a SUBSET of the
// Python enum, so this file can never invent a status a consumer cannot interpret.
//
// SSOT: sdks/python/loreweave_guard/__init__.py → contracts/guard-status.contract.json.
// Drift test: guardstatus_test.go, which reads that contract.
package guardstatus

// Status is one check's honesty state. Its values are a subset of the vocabulary in
// contracts/guard-status.contract.json, pinned by the test in this package.
type Status string

const (
	// Checked — ran against a real, non-empty corpus and produced a usable answer.
	Checked Status = "checked"
	// NoSubject — there was nothing to check: no articles, no entities, no target. Distinct
	// from Checked-with-zero-findings, which is a real answer about a real corpus.
	NoSubject Status = "no_subject"
	// Degraded — a dependency was unavailable, so some or all of the corpus was never
	// compared. This is the member whose absence made a failed KG chunk indistinguishable
	// from a clean sweep.
	Degraded Status = "degraded"
	// NotApplicable — this check was never part of the call's scope (gated off, or its
	// prerequisite input was not supplied). Renders as nothing; it is not a coverage gap.
	// Present as a const rather than a bare string at the one call site that needs it: a
	// literal there is the closed-set defect this package exists to close, written by the
	// same hand that closed it.
	NotApplicable Status = "not_applicable"
)

// Report is what a Go generation/verification path returns instead of a bare count: the
// finding, and how much of the corpus the finding actually covers.
//
// `Unchecked` is the load-bearing field. `Flagged == 0` is only meaningful alongside it —
// zero findings over zero compared articles is not a clean result, and before this there was
// no way for a caller to notice the difference.
type Report struct {
	Status Status `json:"status"`
	// Flagged is the number of subjects the check positively flagged.
	Flagged int `json:"flagged"`
	// Checked is how many subjects were actually compared.
	Checked int `json:"checked"`
	// Unchecked is how many were in scope and could NOT be compared.
	Unchecked int `json:"unchecked"`
}

// Over derives the status from coverage, so a caller never writes the branch by hand.
//
//	total == 0            → NoSubject   (nothing in scope)
//	unchecked > 0         → Degraded    (some or all of the corpus was not compared)
//	otherwise             → Checked
//
// Deliberately NOT "degraded only when everything failed": a partially-compared corpus is a
// partially-verified answer, and rounding it up to Checked is how the original defect read as
// success. The count says how much; the status says whether to trust it at all.
func Over(total, unchecked int) Report {
	switch {
	case total <= 0:
		return Report{Status: NoSubject}
	case unchecked > 0:
		return Report{Status: Degraded, Checked: total - unchecked, Unchecked: unchecked}
	default:
		return Report{Status: Checked, Checked: total}
	}
}
