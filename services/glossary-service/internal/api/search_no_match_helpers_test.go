package api

import (
	"os"
	"strings"
	"testing"
)

func readAPISourceForSearch(t *testing.T) string {
	t.Helper()
	b, err := os.ReadFile("mcp_server.go")
	if err != nil {
		t.Fatalf("cannot read mcp_server.go: %v — this guard has gone blind", err)
	}
	return string(b)
}

func containsAll(src string, needles ...string) bool {
	for _, n := range needles {
		if !strings.Contains(src, n) {
			return false
		}
	}
	return true
}
