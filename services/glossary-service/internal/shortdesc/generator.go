// Package shortdesc generates short, context-friendly summaries of glossary
// entities for injection into LLM prompts. Pure functions — no DB, no
// network, no LLM. Output is CJK-safe (character-counted, not byte-counted).
package shortdesc

import (
	"strings"
	"unicode/utf8"
)

// DefaultMaxChars is the target ceiling for generated short descriptions.
// Chosen to fit comfortably in a dozen prompt rows without dominating
// context budgets.
const DefaultMaxChars = 150

// sentenceTerminators lists both ASCII and CJK end-of-sentence punctuation.
var sentenceTerminators = []rune{'.', '!', '?', '。', '！', '？'}

func isTerminator(r rune) bool {
	for _, t := range sentenceTerminators {
		if r == t {
			return true
		}
	}
	return false
}

// Generate produces a ~maxChars summary of an entity from its name,
// description, and kind name. Rules (KSA K3.1):
//
//  1. description empty → "{kindName}: {name}"  (e.g. "character: Kai")
//  2. first sentence of description is ≤ maxChars → return first sentence
//  3. otherwise → truncate at last word boundary before maxChars and
//     append "…". If no word boundary exists (e.g. one long CJK run),
//     truncate at the character boundary instead.
//
// All length comparisons count RUNES, not bytes — so CJK content gets
// the same character budget as Latin content.
//
// Output is guaranteed non-empty for non-empty `name`, and is always
// ≤ maxChars runes long.
func Generate(name, description, kindName string, maxChars int) string {
	if maxChars <= 0 {
		maxChars = DefaultMaxChars
	}

	desc := strings.TrimSpace(description)
	if desc == "" {
		n := strings.TrimSpace(name)
		k := strings.TrimSpace(kindName)
		var fallback string
		switch {
		case k != "" && n != "":
			fallback = k + ": " + n
		case n != "":
			fallback = n
		case k != "":
			fallback = k
		default:
			return "(unnamed)"
		}
		return truncateRunes(fallback, maxChars)
	}

	// Rule 2: first sentence if short enough.
	first := firstSentence(desc)
	if first != "" && utf8.RuneCountInString(first) <= maxChars {
		return first
	}

	// Rule 3: truncate with ellipsis.
	return truncateWithEllipsis(desc, maxChars)
}

// firstSentence returns the prefix of s up to and including the first
// sentence-terminator rune. Returns "" if no terminator is found.
func firstSentence(s string) string {
	var b strings.Builder
	for _, r := range s {
		b.WriteRune(r)
		if isTerminator(r) {
			return strings.TrimSpace(b.String())
		}
	}
	return ""
}

// truncateRunes returns the first n runes of s (or s unchanged if
// shorter). Never emits a partial rune.
func truncateRunes(s string, n int) string {
	if utf8.RuneCountInString(s) <= n {
		return s
	}
	var b strings.Builder
	count := 0
	for _, r := range s {
		if count == n {
			break
		}
		b.WriteRune(r)
		count++
	}
	return b.String()
}

// truncateWithEllipsis returns a version of s no longer than maxChars
// runes (inclusive of a trailing "…"), broken at the last word boundary
// before the limit when possible. Uses a single ellipsis character (1
// rune) rather than "..." (3 runes) to save budget.
func truncateWithEllipsis(s string, maxChars int) string {
	const ellipsis = "…"
	if utf8.RuneCountInString(s) <= maxChars {
		return s
	}
	// Target at most (maxChars - 1) runes of content + the ellipsis rune.
	budget := maxChars - 1
	if budget <= 0 {
		return ellipsis
	}

	// Collect runes up to budget and remember the last whitespace
	// position we crossed. If one exists past the halfway mark, truncate
	// there — otherwise hard-cut at the rune boundary.
	var runes []rune
	lastSpaceIdx := -1
	for _, r := range s {
		if len(runes) == budget {
			break
		}
		if r == ' ' || r == '\t' || r == '\n' {
			lastSpaceIdx = len(runes)
		}
		runes = append(runes, r)
	}
	if lastSpaceIdx > budget/2 {
		runes = runes[:lastSpaceIdx]
	}
	out := strings.TrimRight(string(runes), " \t\n")
	return out + ellipsis
}
