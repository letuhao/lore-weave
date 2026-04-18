package tasks

import (
	"errors"
	"testing"

	"github.com/jackc/pgx/v5/pgconn"
)

func TestMaxLenFor(t *testing.T) {
	cases := []struct {
		aggregateType string
		want          int64
	}{
		{"chapter", 10000},
		{"chat", 50000},
		{"glossary", 10000},
		{"unknown", defaultStreamMaxLen},
		{"", defaultStreamMaxLen},
	}
	for _, c := range cases {
		if got := maxLenFor(c.aggregateType); got != c.want {
			t.Errorf("maxLenFor(%q) = %d, want %d", c.aggregateType, got, c.want)
		}
	}
}

func TestIsUndefinedTable(t *testing.T) {
	cases := []struct {
		name string
		err  error
		want bool
	}{
		{"nil error", nil, false},
		{"generic error", errors.New("boom"), false},
		{"undefined table", &pgconn.PgError{Code: "42P01"}, true},
		{"other pg error", &pgconn.PgError{Code: "23505"}, false},
		{"wrapped undefined table", fmtWrap(&pgconn.PgError{Code: "42P01"}), true},
	}
	for _, c := range cases {
		if got := isUndefinedTable(c.err); got != c.want {
			t.Errorf("%s: isUndefinedTable = %v, want %v", c.name, got, c.want)
		}
	}
}

// fmtWrap wraps an error using errors.Join so errors.As still walks to the pgconn.PgError.
func fmtWrap(err error) error {
	return errors.Join(errors.New("query failed"), err)
}

func TestNoteTableStateTransitions(t *testing.T) {
	r := &OutboxRelay{}

	// First observation: missing. Should record state.
	r.noteTableState("chat", true)
	if !r.tableMissing["chat"] {
		t.Fatalf("expected tableMissing[chat] = true after first missing report")
	}

	// Repeated missing: still true, no crash, map entry stable.
	r.noteTableState("chat", true)
	if !r.tableMissing["chat"] {
		t.Fatalf("expected tableMissing[chat] to stay true on repeat")
	}

	// Recovery.
	r.noteTableState("chat", false)
	if r.tableMissing["chat"] {
		t.Fatalf("expected tableMissing[chat] = false after recovery")
	}

	// Second source tracked independently.
	r.noteTableState("book", true)
	if !r.tableMissing["book"] || r.tableMissing["chat"] {
		t.Fatalf("expected per-source state independence")
	}
}
