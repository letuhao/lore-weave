// sql_helpers_test.go — shared `mustApply` helper for integration tests.
//
// Reads a .sql file from the repo root and runs it against the supplied DB.
// Fails the test on any error.
//
//go:build integration
// +build integration

package integration

import (
	"database/sql"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

// mustApply reads the given .sql file (path relative to the repo root)
// and runs it against db. Fails the test if the file is missing or the
// statements error out.
func mustApply(t *testing.T, db *sql.DB, relPath string) {
	t.Helper()
	root := repoRoot(t)
	abs := filepath.Join(root, filepath.FromSlash(relPath))
	b, err := os.ReadFile(abs)
	if err != nil {
		t.Fatalf("mustApply read %s: %v", abs, err)
	}
	if _, err := db.Exec(string(b)); err != nil {
		t.Fatalf("mustApply exec %s: %v", abs, err)
	}
}

// repoRoot returns the foundation repo root. Found by walking up from
// this file's location until we hit the root `Cargo.toml`.
func repoRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	dir := filepath.Dir(file)
	for i := 0; i < 6; i++ { // expect to find within 6 ancestors
		if _, err := os.Stat(filepath.Join(dir, "Cargo.toml")); err == nil {
			return dir
		}
		dir = filepath.Dir(dir)
	}
	t.Fatalf("could not locate repo root walking up from %s", file)
	return ""
}
