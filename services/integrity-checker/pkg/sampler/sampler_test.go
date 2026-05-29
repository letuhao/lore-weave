package sampler

import (
	"context"
	"math/rand"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

func mkRow(id string, v uint64) ProjectionRow {
	return ProjectionRow{
		AggregateID:      id,
		AggregateType:    "pc",
		EventID:          uuid.New(),
		AggregateVersion: v,
		PayloadJSON:      []byte(`{"value":42}`),
	}
}

func TestNew_RejectsNilDeps(t *testing.T) {
	if _, err := New(nil, rand.New(rand.NewSource(1))); err == nil {
		t.Error("expected error for nil RowSource")
	}
	src := NewInMemRowSource()
	if _, err := New(src, nil); err == nil {
		t.Error("expected error for nil rng")
	}
}

func TestSampleTable_ReturnsUpToSampleSize(t *testing.T) {
	src := NewInMemRowSource()
	rid := uuid.New()
	for i := 0; i < 100; i++ {
		src.AddRow(rid, "pc_projection", mkRow("pc-"+string(rune('a'+i%26)), uint64(i)))
	}
	s, _ := New(src, rand.New(rand.NewSource(42)))
	out, err := s.SampleTable(context.Background(), rid, types.TableConfig{TableName: "pc_projection", SampleSize: 20})
	if err != nil {
		t.Fatalf("SampleTable: %v", err)
	}
	if len(out) != 20 {
		t.Errorf("SampleSize=20 expected, got %d", len(out))
	}
}

func TestSampleTable_BoundedByActualRowCount(t *testing.T) {
	src := NewInMemRowSource()
	rid := uuid.New()
	for i := 0; i < 5; i++ {
		src.AddRow(rid, "pc_projection", mkRow("pc-1", uint64(i)))
	}
	s, _ := New(src, rand.New(rand.NewSource(42)))
	out, err := s.SampleTable(context.Background(), rid, types.TableConfig{TableName: "pc_projection", SampleSize: 20})
	if err != nil {
		t.Fatalf("SampleTable: %v", err)
	}
	if len(out) != 5 {
		t.Errorf("expected 5 (all available), got %d", len(out))
	}
}

func TestSampleTable_RejectsZeroSampleSize(t *testing.T) {
	s, _ := New(NewInMemRowSource(), rand.New(rand.NewSource(1)))
	_, err := s.SampleTable(context.Background(), uuid.New(), types.TableConfig{TableName: "pc_projection", SampleSize: 0})
	if err == nil {
		t.Fatal("expected error for SampleSize=0")
	}
}

func TestSampleTable_ShuffleProvidesNonDegenerateOrder(t *testing.T) {
	src := NewInMemRowSource()
	rid := uuid.New()
	for i := 0; i < 50; i++ {
		src.AddRow(rid, "pc_projection", mkRow("pc-"+string(rune('a'+i)), uint64(i)))
	}
	s, _ := New(src, rand.New(rand.NewSource(42)))
	out, _ := s.SampleTable(context.Background(), rid, types.TableConfig{TableName: "pc_projection", SampleSize: 50})
	// Insertion order is "pc-a", "pc-b", … ; after shuffle at least one
	// position should differ.
	allInOrder := true
	for i, r := range out {
		expected := "pc-" + string(rune('a'+i))
		if r.AggregateID != expected {
			allInOrder = false
			break
		}
	}
	if allInOrder {
		t.Error("shuffle did not perturb order (would degrade daily-sample randomness)")
	}
}

func TestSampleTable_CarriesVerificationMetaThrough(t *testing.T) {
	src := NewInMemRowSource()
	rid := uuid.New()
	want := mkRow("pc-special", 99)
	src.AddRow(rid, "pc_projection", want)
	s, _ := New(src, rand.New(rand.NewSource(1)))
	out, _ := s.SampleTable(context.Background(), rid, types.TableConfig{TableName: "pc_projection", SampleSize: 1})
	if len(out) != 1 {
		t.Fatalf("1 row expected, got %d", len(out))
	}
	if out[0].EventID != want.EventID {
		t.Errorf("EventID drift: got %v want %v", out[0].EventID, want.EventID)
	}
	if out[0].AggregateVersion != want.AggregateVersion {
		t.Errorf("AggregateVersion drift: got %d want %d", out[0].AggregateVersion, want.AggregateVersion)
	}
}
