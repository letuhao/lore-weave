package observability

import (
	"bytes"
	"io"
	"strings"
)

// bytesReader is a tiny helper to avoid importing bytes.NewReader at
// every call site. Returns an io.Reader over the provided bytes.
func bytesReader(b []byte) io.Reader { return bytes.NewReader(b) }

// containsAny returns true if s contains any of the needles. Used by
// the yaml.v3 error-string heuristic in ParseAndValidate (strict mode).
func containsAny(s string, needles ...string) bool {
	for _, n := range needles {
		if strings.Contains(s, n) {
			return true
		}
	}
	return false
}
