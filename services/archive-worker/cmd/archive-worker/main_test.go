package main

import (
	"testing"

	"github.com/loreweave/foundation/services/archive-worker/pkg/parquet_writer"
)

// TestParquetABI_DocumentedConstants — anti-regression. If someone bumps
// SchemaVersion or rotates Magic, downstream readers break silently. main()
// guards against this at startup; this test guards at build time.
func TestParquetABI_DocumentedConstants(t *testing.T) {
	if parquet_writer.SchemaVersion != 1 {
		t.Fatalf("SchemaVersion drift: got %d, want 1", parquet_writer.SchemaVersion)
	}
	if string(parquet_writer.Magic[:]) != "LWP1" {
		t.Fatalf("Magic drift: got %q, want LWP1", parquet_writer.Magic[:])
	}
}
