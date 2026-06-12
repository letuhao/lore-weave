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
		// Phase B: glossary + knowledge feed learning-service's append-only
		// correction log — large budget so MAXLEN trim can't drop unread
		// events during a learning-service outage (design §10.1).
		{"glossary", 200000},
		{"knowledge", 200000},
		{"unknown", defaultStreamMaxLen},
		{"", defaultStreamMaxLen},
	}
	for _, c := range cases {
		if got := maxLenFor(c.aggregateType); got != c.want {
			t.Errorf("maxLenFor(%q) = %d, want %d", c.aggregateType, got, c.want)
		}
	}
}

// Phase B §4.0 (F1/F2) — the relay MUST carry the producer's outbox row id on
// the stream as `outbox_id`, equal to the row PK. Consumers dedup on it; a
// missing/wrong field re-introduces the F2 correction-collapse bug.
func TestRelayStreamValues_CarriesOutboxID(t *testing.T) {
	v := relayStreamValues("glossary.entity_updated", "agg-123", `{"x":1}`, "glossary", "outbox-row-pk-abc")

	got, ok := v["outbox_id"]
	if !ok {
		t.Fatal("relay stream values MUST include outbox_id (the dedup key)")
	}
	if got != "outbox-row-pk-abc" {
		t.Fatalf("outbox_id = %v, want the outbox row PK", got)
	}
	// outbox_id must NOT be the aggregate_id (the reused target id — F2).
	if v["outbox_id"] == v["aggregate_id"] {
		t.Fatal("outbox_id must be distinct from aggregate_id (F2: aggregate_id is reused per edit)")
	}
	for _, k := range []string{"event_type", "aggregate_id", "payload", "source", "outbox_id"} {
		if _, present := v[k]; !present {
			t.Errorf("relay stream values missing field %q", k)
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
