package push

import (
	"context"
	"errors"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// Hand-rolled Querier mock (no pgxmock dep here) — enough to drive PushEnabled's three outcomes.
type fakeRow struct {
	enabled bool
	err     error
}

func (r fakeRow) Scan(dest ...any) error {
	if r.err != nil {
		return r.err
	}
	if len(dest) > 0 {
		if p, ok := dest[0].(*bool); ok {
			*p = r.enabled
		}
	}
	return nil
}

type fakeQuerier struct{ row fakeRow }

func (q fakeQuerier) QueryRow(ctx context.Context, sql string, args ...any) pgx.Row { return q.row }

// H2 — the push gate must FAIL CLOSED (unlike the in-app prefs.Suppressed which fails open).
func TestPushEnabled_FailsClosedOnError(t *testing.T) {
	q := fakeQuerier{row: fakeRow{err: errors.New("db exploded")}}
	enabled, err := PushEnabled(context.Background(), q, uuid.New(), "assistant", "notif.assistant.reflection")
	if err == nil {
		t.Fatal("expected the query error to propagate")
	}
	if enabled {
		t.Error("FAIL CLOSED violated: a gate error must yield enabled=false (do NOT push)")
	}
}

func TestPushEnabled_NoRowUsesTopicDefault(t *testing.T) {
	// social has NO row → its default is OFF; mcp_approval default is ON.
	social, err := PushEnabled(context.Background(), fakeQuerier{row: fakeRow{err: pgx.ErrNoRows}}, uuid.New(), "social", "")
	if err != nil {
		t.Fatalf("no-row is not an error: %v", err)
	}
	if social {
		t.Error("social with no row must default to OFF")
	}
	mcp, _ := PushEnabled(context.Background(), fakeQuerier{row: fakeRow{err: pgx.ErrNoRows}}, uuid.New(), "mcp_approval", "")
	if !mcp {
		t.Error("mcp_approval with no row must default to ON")
	}
}

func TestPushEnabled_ExplicitRowWins(t *testing.T) {
	// A user row that DISABLES an on-by-default topic must win.
	enabled, err := PushEnabled(context.Background(), fakeQuerier{row: fakeRow{enabled: false}}, uuid.New(), "assistant", "notif.assistant.reflection")
	if err != nil {
		t.Fatal(err)
	}
	if enabled {
		t.Error("an explicit push_enabled=false row must suppress the buzz")
	}
	on, _ := PushEnabled(context.Background(), fakeQuerier{row: fakeRow{enabled: true}}, uuid.New(), "social", "")
	if !on {
		t.Error("an explicit push_enabled=true row must enable an off-by-default topic")
	}
}
