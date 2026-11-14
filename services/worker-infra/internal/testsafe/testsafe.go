// Package testsafe guards DB-gated tests from ever running their destructive
// setup/cleanup against a REAL service database.
//
// The incident this exists to prevent (2026-07): a migration test's cleanup ran an
// UNSCOPED `DELETE FROM books` (no WHERE), and `BOOK_TEST_DATABASE_URL` was pointed
// at the real `loreweave_book` dev database (committed that way in
// .github/workflows/domain-db-smoke.yml). Running the test hard-deleted EVERY user's
// books — no trash, no owner scope, unrecoverable. The test's own doc claimed it
// needed "a THROWAWAY database", but nothing enforced it.
//
// This guard makes that impossible regardless of how *_TEST_DATABASE_URL is set: a
// DB-gated test calls EnsureThrowawayDB(current_database()) right after connecting
// and BEFORE any destructive statement, and it FAILS LOUDLY if the target is not a
// recognizable disposable database. It is deliberately fail-CLOSED — a name with no
// throwaway marker is treated as production.
package testsafe

import (
	"fmt"
	"regexp"
	"strings"
)

// throwawayMarker matches a substring that only a disposable test/smoke database
// name carries. The real service DBs (loreweave_book, loreweave_glossary,
// loreweave_composition, loreweave_statistics, …) contain none of these — verified
// against the live database list. "statistics" does NOT contain "test" (no 'e').
var throwawayMarker = regexp.MustCompile(`(?i)(test|smoke|audit|scratch|throwaway|tmp|sandbox|ephemeral)`)

// IsThrowawayDBName reports whether dbName looks like a disposable database a
// destructive DB-gated test may safely wipe. Fail-closed: no marker ⇒ not throwaway.
func IsThrowawayDBName(dbName string) bool {
	return throwawayMarker.MatchString(dbName)
}

// EnsureThrowawayDB returns a non-nil error when dbName is NOT a recognizable
// throwaway database. Call it after connecting, BEFORE any destructive statement:
//
//	var db string
//	pool.QueryRow(ctx, `SELECT current_database()`).Scan(&db)
//	if err := testsafe.EnsureThrowawayDB(db); err != nil { t.Fatal(err) }
func EnsureThrowawayDB(dbName string) error {
	if strings.TrimSpace(dbName) == "" {
		return fmt.Errorf("testsafe: refusing a destructive DB test against an empty database name")
	}
	if !IsThrowawayDBName(dbName) {
		return fmt.Errorf(
			"testsafe: REFUSING to run a destructive DB-gated test against database %q — "+
				"it is not a recognizable throwaway DB (the name must contain "+
				"test/smoke/audit/scratch/tmp). Point the *_TEST_DATABASE_URL at a "+
				"DISPOSABLE database, never a real service DB. This guard exists because an "+
				"unscoped `DELETE FROM books` cleanup pointed at the real loreweave_book once "+
				"hard-deleted every user's books",
			dbName,
		)
	}
	return nil
}
