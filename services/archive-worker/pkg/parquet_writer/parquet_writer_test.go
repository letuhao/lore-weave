package parquet_writer

import (
	"bytes"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/archive-worker/pkg/types"
)

func mkRow(seed int) types.EventRow {
	return types.EventRow{
		EventID:          uuid.New(),
		RealityID:        uuid.New(),
		AggregateType:    "npc",
		AggregateID:      "npc-1",
		AggregateVersion: uint64(seed),
		EventType:        "npc.said",
		EventVersion:     1,
		Payload:          []byte(`{"text":"hello"}`),
		Metadata:         nil,
		OccurredAt:       time.Date(2025, 11, 1, 12, 0, 0, 0, time.UTC),
		RecordedAt:       time.Date(2025, 11, 1, 12, 0, 1, 0, time.UTC),
	}
}

func TestEncodeDecode_RoundTrip(t *testing.T) {
	rows := []types.EventRow{mkRow(1), mkRow(2), mkRow(3)}
	blob, err := NewEncoder().Encode(rows)
	if err != nil {
		t.Fatal(err)
	}
	got, err := NewDecoder().Decode(blob)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != len(rows) {
		t.Fatalf("row count: got %d want %d", len(got), len(rows))
	}
	for i := range rows {
		if got[i].EventID != rows[i].EventID {
			t.Errorf("row %d EventID mismatch: got=%s want=%s", i, got[i].EventID, rows[i].EventID)
		}
		if got[i].AggregateVersion != rows[i].AggregateVersion {
			t.Errorf("row %d AggregateVersion mismatch", i)
		}
	}
}

func TestEncodeDecode_EmptyRows(t *testing.T) {
	blob, err := NewEncoder().Encode(nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(blob) != MinBlobSize {
		t.Fatalf("empty blob size: got %d want %d", len(blob), MinBlobSize)
	}
	got, err := NewDecoder().Decode(blob)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 0 {
		t.Fatalf("expected 0 rows decoded, got %d", len(got))
	}
}

func TestDecode_BadHeaderMagic(t *testing.T) {
	rows := []types.EventRow{mkRow(1)}
	blob, _ := NewEncoder().Encode(rows)
	blob[0] = 'X'
	if _, err := NewDecoder().Decode(blob); err == nil {
		t.Fatal("expected bad header magic error")
	}
}

func TestDecode_BadFooterMagic(t *testing.T) {
	rows := []types.EventRow{mkRow(1)}
	blob, _ := NewEncoder().Encode(rows)
	blob[len(blob)-1] = 'X'
	if _, err := NewDecoder().Decode(blob); err == nil {
		t.Fatal("expected bad footer magic error")
	}
}

func TestDecode_RowCountFooterMismatch(t *testing.T) {
	rows := []types.EventRow{mkRow(1), mkRow(2)}
	blob, _ := NewEncoder().Encode(rows)
	// Tamper the row count footer (last 12..-8 bytes).
	blob[len(blob)-9] = 99
	if _, err := NewDecoder().Decode(blob); err == nil {
		t.Fatal("expected row count mismatch error")
	}
}

func TestDecode_TooSmall(t *testing.T) {
	if _, err := NewDecoder().Decode([]byte("LWP1")); err == nil {
		t.Fatal("expected blob too small error")
	}
}

func TestDecode_UnknownSchemaVersion(t *testing.T) {
	rows := []types.EventRow{mkRow(1)}
	blob, _ := NewEncoder().Encode(rows)
	// Tamper schema_version (bytes 4..8).
	blob[4] = 0
	blob[5] = 0
	blob[6] = 0
	blob[7] = 9
	if _, err := NewDecoder().Decode(blob); err == nil {
		t.Fatal("expected unknown schema_version error")
	}
}

func TestVerifyHeader_OK(t *testing.T) {
	rows := []types.EventRow{mkRow(1), mkRow(2)}
	blob, _ := NewEncoder().Encode(rows)
	if err := VerifyHeader(blob, 2); err != nil {
		t.Fatalf("VerifyHeader unexpected err: %v", err)
	}
}

func TestVerifyHeader_RowCountMismatch(t *testing.T) {
	rows := []types.EventRow{mkRow(1), mkRow(2)}
	blob, _ := NewEncoder().Encode(rows)
	if err := VerifyHeader(blob, 5); err == nil {
		t.Fatal("expected row count mismatch (5 vs 2)")
	}
}

func TestVerifyHeader_RejectsCorrupt(t *testing.T) {
	rows := []types.EventRow{mkRow(1)}
	blob, _ := NewEncoder().Encode(rows)
	blob[0] = 'X'
	if err := VerifyHeader(blob, 1); err == nil {
		t.Fatal("expected corrupt header rejection")
	}
}

func TestMagicMarker_DocumentedConstant(t *testing.T) {
	// Anti-regression: if someone changes Magic, downstream
	// cmd/archive-restore + integrity-checker (L3) break silently.
	if !bytes.Equal(Magic[:], []byte("LWP1")) {
		t.Fatalf("Magic changed without coordinated update! got %q", Magic[:])
	}
	if SchemaVersion != 1 {
		t.Fatalf("SchemaVersion changed: got %d", SchemaVersion)
	}
}
