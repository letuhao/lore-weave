package commands

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

type fakeArchiveReader struct {
	rows []ArchiveEntry
	err  error
}

func (f fakeArchiveReader) ListArchives(context.Context, uuid.UUID) ([]ArchiveEntry, error) {
	return f.rows, f.err
}

func TestRunArchiveList_FormatsRows(t *testing.T) {
	rid := uuid.New()
	out, err := RunArchiveList(context.Background(), rid, fakeArchiveReader{rows: []ArchiveEntry{
		{PartitionName: "events_p_2025_11", ObjectKey: "events/r/2025-11.parquet", ByteSize: 1024, RowCount: 42, ArchivedAt: time.Unix(0, 0)},
	}})
	if err != nil {
		t.Fatalf("RunArchiveList: %v", err)
	}
	if !strings.Contains(out, "events_p_2025_11") || !strings.Contains(out, "42 rows") || !strings.Contains(out, ": 1\n") {
		t.Errorf("formatting missing expected fields:\n%s", out)
	}
}

func TestRunArchiveList_EmptyIsNotError(t *testing.T) {
	out, err := RunArchiveList(context.Background(), uuid.New(), fakeArchiveReader{rows: nil})
	if err != nil {
		t.Fatalf("empty list must not error: %v", err)
	}
	if !strings.Contains(out, ": 0\n") {
		t.Errorf("empty list should report 0, got:\n%s", out)
	}
}

func TestRunArchiveList_ReaderErrorPropagates(t *testing.T) {
	sentinel := errors.New("db down")
	_, err := RunArchiveList(context.Background(), uuid.New(), fakeArchiveReader{err: sentinel})
	if !errors.Is(err, sentinel) {
		t.Fatalf("reader error must propagate, got %v", err)
	}
}

func TestRunArchiveList_NilReader(t *testing.T) {
	if _, err := RunArchiveList(context.Background(), uuid.New(), nil); err == nil {
		t.Fatal("nil reader must error")
	}
}
