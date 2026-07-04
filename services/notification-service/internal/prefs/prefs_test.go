package prefs

import (
	"context"
	"errors"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

// fakeRow scripts a single QueryRow(...).Scan outcome.
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

func (q fakeQuerier) QueryRow(context.Context, string, ...any) pgx.Row { return q.row }
func (q fakeQuerier) Query(context.Context, string, ...any) (pgx.Rows, error) {
	return nil, errors.New("unused")
}
func (q fakeQuerier) Exec(context.Context, string, ...any) (pgconn.CommandTag, error) {
	return pgconn.CommandTag{}, nil
}

// The gate's contract: default delivers, an enabled=false row suppresses, and a
// lookup MUST fail OPEN (an error or missing row never silently drops a
// notification — Suppressed returns false so the caller delivers).
func TestSuppressed_Semantics(t *testing.T) {
	uid := uuid.New()
	cases := []struct {
		name    string
		row     fakeRow
		wantSup bool
		wantErr bool
	}{
		{"no preference row → deliver", fakeRow{err: pgx.ErrNoRows}, false, false},
		{"enabled=true → deliver", fakeRow{enabled: true}, false, false},
		{"enabled=false → suppress", fakeRow{enabled: false}, true, false},
		{"db error → surfaced (caller fails open)", fakeRow{err: errors.New("boom")}, false, true},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			sup, err := Suppressed(context.Background(), fakeQuerier{row: c.row}, uid, "billing")
			if (err != nil) != c.wantErr {
				t.Fatalf("err=%v wantErr=%v", err, c.wantErr)
			}
			if sup != c.wantSup {
				t.Errorf("suppressed=%v want %v", sup, c.wantSup)
			}
		})
	}
}
