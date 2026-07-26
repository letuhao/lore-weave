package consumer

import (
	"context"
	"errors"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgconn"
)

// fakeExecer records the SQL issued so the guard's EFFECT (it deletes, or it does
// not touch the DB at all) can be asserted without a real Postgres.
type fakeExecer struct {
	calls   []string
	rows    int64
	execErr error
}

func (f *fakeExecer) Exec(_ context.Context, sql string, _ ...any) (pgconn.CommandTag, error) {
	f.calls = append(f.calls, sql)
	if f.execErr != nil {
		return pgconn.CommandTag{}, f.execErr
	}
	// Build a DELETE tag with the configured RowsAffected.
	tag := "DELETE 0"
	if f.rows == 1 {
		tag = "DELETE 1"
	}
	return pgconn.NewCommandTag(tag), nil
}

func TestPurgeDiaryFromStats(t *testing.T) {
	t.Parallel()
	bookID := uuid.New()

	t.Run("a diary is deleted and the caller skips the upsert", func(t *testing.T) {
		db := &fakeExecer{rows: 1}
		skip := purgeDiaryFromStats(context.Background(), db, bookID, "diary")
		if !skip {
			t.Fatal("diary must return skip=true so refreshBookMetadata does NOT upsert book_stats")
		}
		if len(db.calls) != 1 {
			t.Fatalf("diary must issue exactly one DELETE, got %d calls: %v", len(db.calls), db.calls)
		}
	})

	t.Run("a diary with no pre-existing row still skips (idempotent)", func(t *testing.T) {
		db := &fakeExecer{rows: 0}
		if !purgeDiaryFromStats(context.Background(), db, bookID, "diary") {
			t.Fatal("diary must skip even when there was no row to delete")
		}
	})

	t.Run("a normal book is tracked — NO DB touch, NO skip", func(t *testing.T) {
		for _, kind := range []string{"novel", "document", "lore", ""} {
			db := &fakeExecer{}
			if purgeDiaryFromStats(context.Background(), db, bookID, kind) {
				t.Fatalf("kind=%q must NOT skip (only a diary is excluded)", kind)
			}
			if len(db.calls) != 0 {
				t.Fatalf("kind=%q must not touch book_stats in the guard, got %v", kind, db.calls)
			}
		}
	})

	t.Run("a DELETE error still skips — a diary is never tracked even if cleanup fails", func(t *testing.T) {
		db := &fakeExecer{execErr: errors.New("boom")}
		if !purgeDiaryFromStats(context.Background(), db, bookID, "diary") {
			t.Fatal("a diary must be excluded from stats regardless of the DELETE outcome")
		}
	})
}
