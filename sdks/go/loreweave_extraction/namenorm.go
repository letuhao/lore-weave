// Package loreweave_extraction holds the multi-language entity-name normalizer
// shared by Go domain services (glossary-service first). It is the Go mirror of
// the Python SDK module loreweave_extraction.name_normalize and folds the SAME
// equivalence classes so entity dedup agrees across languages:
//
//  1. NFKC   — Unicode compatibility composition (full-width Ｋ→K, composed↔
//     decomposed accents, ligatures, compatibility chars). Language-agnostic.
//  2. casefold — Unicode-correct lowercasing for every script (ß→ss), stronger
//     and more correct than a plain ToLower.
//  3. Han simplified fold — traditional→simplified per the frozen vendored table
//     (張→张), gated on the presence of any Han character (cheap no-op otherwise).
//
// It folds *equivalence* (same identity, different encoding/script) but NOT
// *similarity* — diacritics/accents are deliberately PRESERVED (vi má≠ma,
// Müller≠Muller), exactly as the Python side does.
//
// The Han table (t2s_table.go) is GENERATED from sdks/data/han_t2s.tsv — the one
// source of truth shared with the Python dict. Regenerate with `go generate`;
// TestT2SParityWithSoT guards against drift.
package loreweave_extraction

//go:generate go run gen/main.go

import (
	"golang.org/x/text/cases"
	"golang.org/x/text/unicode/norm"
)

// _hanRanges — CJK ideograph blocks, used ONLY as a cheap gate so the simplified
// fold is skipped for non-CJK text (the common case). Mirrors the Python
// name_normalize._HAN_RANGES exactly.
var _hanRanges = [...][2]rune{
	{0x3400, 0x4DBF},   // CJK Extension A
	{0x4E00, 0x9FFF},   // CJK Unified Ideographs
	{0xF900, 0xFAFF},   // CJK Compatibility Ideographs
	{0x20000, 0x2A6DF}, // CJK Extension B
}

// foldCaser is stateless and safe for concurrent use (cases.Caser docs).
var foldCaser = cases.Fold()

// HasHan reports whether s contains any Han ideograph (the simplified-fold gate).
func HasHan(s string) bool {
	for _, r := range s {
		for _, rg := range _hanRanges {
			if r >= rg[0] && r <= rg[1] {
				return true
			}
		}
	}
	return false
}

// NfkcCasefold NFKC-normalizes then Unicode-casefolds. Language-agnostic; idempotent.
func NfkcCasefold(s string) string {
	return foldCaser.String(norm.NFKC.String(s))
}

// FoldHanSimplified maps each traditional Han rune to its simplified form via the
// vendored table. No-op when s has no Han rune (cheap guard) and for any rune
// absent from the curated table (a residual duplicate, never a wrong fold).
// Non-Han runes always pass through unchanged.
func FoldHanSimplified(s string) string {
	if !HasHan(s) {
		return s
	}
	out := make([]rune, 0, len(s))
	for _, r := range s {
		if mapped, ok := T2S[r]; ok {
			out = append(out, mapped)
		} else {
			out = append(out, r)
		}
	}
	return string(out)
}

// NormalizeEntityName is the multi-language equivalence key: NFKC + casefold then
// the Han simplified fold. Two variant spellings of the SAME name return the same
// string. Callers layer their own honorific/whitespace/punctuation steps on top
// (e.g. glossary's textnorm.Normalize). Mirror of the Python normalize_entity_name.
func NormalizeEntityName(name string) string {
	return FoldHanSimplified(NfkcCasefold(name))
}
