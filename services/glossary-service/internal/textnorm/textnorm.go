// Package textnorm holds the canonical list-value parsing + name-normalization
// helpers shared by the glossary writeback (internal/api) and the migration
// backfill (internal/migrate). Keeping ONE implementation guarantees dedup
// parity between the per-item child rows and the runtime append path — the
// "normalize parity" risk called out in D-GLOSSARY-MULTIROW-ATTR-VALUES.
package textnorm

import (
	"encoding/json"
	"regexp"
	"strings"

	"golang.org/x/text/unicode/norm"
)

var wsCollapse = regexp.MustCompile(`\s+`)

// Normalize prepares a string for dedup comparison: Unicode NFC, trim, collapse
// internal whitespace, lowercase. (The former api.normalizeEntity.)
func Normalize(s string) string {
	s = norm.NFC.String(s)
	s = strings.TrimSpace(s)
	s = wsCollapse.ReplaceAllString(s, " ")
	s = strings.ToLower(s)
	return s
}

// ParseList interprets a stored attribute value as a string list: a JSON array
// yields its non-empty string elements; a non-empty scalar is a single-element
// list; empty → nil. (The former api.parseListValue.)
func ParseList(s string) []string {
	s = strings.TrimSpace(s)
	if s == "" {
		return nil
	}
	if strings.HasPrefix(s, "[") {
		var arr []any
		if err := json.Unmarshal([]byte(s), &arr); err == nil {
			out := make([]string, 0, len(arr))
			for _, v := range arr {
				if str, ok := v.(string); ok && strings.TrimSpace(str) != "" {
					out = append(out, str)
				}
			}
			return out
		}
	}
	return []string{s}
}

// IsList reports whether a stored value is a JSON-array list (vs a scalar).
// The backfill only materializes child items for list values; scalars keep
// original_value as the sole authority.
func IsList(s string) bool {
	return strings.HasPrefix(strings.TrimSpace(s), "[")
}
