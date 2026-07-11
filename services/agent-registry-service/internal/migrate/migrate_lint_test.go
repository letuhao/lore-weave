package migrate

import (
	"strings"
	"testing"
)

// The seed prose in schemaSQL lives inside Postgres E'...' literals. A BARE apostrophe
// inside one terminates the string and the whole migration dies with a syntax error at
// boot — while every unit test stays green, because nothing here talks to a database.
//
// This has now bitten twice while authoring the System workflow seeds:
//   1. a backtick in a comment terminated the Go raw string (compile error — caught fast),
//   2. an apostrophe in notes_md terminated the SQL string (runtime error — caught ONLY by
//      reading the container logs, after a full rebuild and a 4-minute eval run).
//
// So: lint it statically. Inside an E'...' literal the only legal ways to write a quote
// are '' (doubled) or \' (backslash-escaped); anything else ends the literal.
func TestSchemaSQL_NoBareApostropheInsideEStringLiterals(t *testing.T) {
	for _, lit := range eStringLiterals(t, schemaSQL) {
		// Remove the two legal escape forms, then any quote left is a terminator.
		s := strings.ReplaceAll(lit.body, `\'`, "")
		s = strings.ReplaceAll(s, "''", "")
		if strings.Contains(s, "'") {
			t.Errorf("bare apostrophe inside an E'...' literal starting at offset %d — it "+
				"terminates the SQL string and breaks the migration at boot.\nWrite '' or "+
				"\\' (or reword). First 160 chars:\n%s", lit.start, head(lit.body, 160))
		}
	}
}

func TestSchemaSQL_HasTheSystemWorkflowSeeds(t *testing.T) {
	// A rail that never seeds is a pin that never fires.
	for _, slug := range []string{"glossary-bootstrap", "entity-triage", "vision-to-book"} {
		if !strings.Contains(schemaSQL, "'"+slug+"'") {
			t.Errorf("System workflow %q is not seeded", slug)
		}
	}
	// And every one must be able to CORRECT an already-seeded row: DO NOTHING would freeze
	// a bad rail forever (the "migration never revisits its default" trap). Checked per
	// INSERT INTO workflows statement — the `skills` seed legitimately still uses DO
	// NOTHING (its bodies are served by chat-service, not this table), so a blanket
	// substring check over the whole schema would false-positive on it.
	// NB: the statement cannot be split on ";" — the seed PROSE contains semicolons
	// ("…returns a confirm_token; pass that exact token…"), which is what made the first
	// version of this lint report false failures. Bound each seed by the next statement.
	const ins = "INSERT INTO workflows ("
	seen := 0
	for at := 0; ; {
		i := strings.Index(schemaSQL[at:], ins)
		if i < 0 {
			break
		}
		i += at
		rest := schemaSQL[i+len(ins):]
		end := len(rest)
		for _, next := range []string{"\nINSERT INTO ", "\nCREATE TABLE ", "\nCREATE INDEX ", "\nCREATE UNIQUE "} {
			if k := strings.Index(rest, next); k >= 0 && k < end {
				end = k
			}
		}
		stmt := rest[:end]
		if !strings.Contains(stmt, "DO UPDATE SET") {
			t.Errorf("a System workflow seed does not DO UPDATE — an already-seeded row can "+
				"never be corrected by a deploy:\n%s", head(stmt, 120))
		}
		seen++
		at = i + len(ins) + end
	}
	if seen < 3 {
		t.Errorf("expected at least 3 System workflow seeds, scanned %d", seen)
	}
}

type eLit struct {
	start int
	body  string
}

// eStringLiterals finds each E'...' literal's body. It walks the raw SQL and, on E',
// scans to the terminating quote while honoring the two legal escapes — which is exactly
// the rule Postgres itself applies, so a body we fail to terminate is a body Postgres
// would also mis-terminate.
func eStringLiterals(t *testing.T, sql string) []eLit {
	t.Helper()
	var out []eLit
	for i := 0; i+1 < len(sql); i++ {
		if sql[i] != 'E' || sql[i+1] != '\'' {
			continue
		}
		j := i + 2
		var b strings.Builder
		for j < len(sql) {
			c := sql[j]
			if c == '\\' && j+1 < len(sql) { // \' and friends
				b.WriteByte(c)
				b.WriteByte(sql[j+1])
				j += 2
				continue
			}
			if c == '\'' {
				if j+1 < len(sql) && sql[j+1] == '\'' { // '' escape
					b.WriteString("''")
					j += 2
					continue
				}
				break // real terminator
			}
			b.WriteByte(c)
			j++
		}
		out = append(out, eLit{start: i, body: b.String()})
		i = j
	}
	if len(out) == 0 {
		t.Fatal("no E'...' literals found — the lint would be vacuously green")
	}
	return out
}

func head(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}
