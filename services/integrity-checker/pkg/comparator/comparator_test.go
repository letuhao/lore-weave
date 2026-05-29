package comparator

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

func frozenClock(t time.Time) func() time.Time { return func() time.Time { return t } }

func TestNew_RejectsNilDeps(t *testing.T) {
	if _, err := New(Config{Loader: nil, Clock: time.Now}); err == nil {
		t.Error("expected error for nil Loader")
	}
	if _, err := New(Config{Loader: NewInMemLoader(), Clock: nil}); err == nil {
		t.Error("expected error for nil Clock")
	}
}

func TestCompareOne_MatchesProjection_NoDrift(t *testing.T) {
	loader := NewInMemLoader()
	rid := uuid.New()
	loader.AddState(rid, "pc", "pc-1", 5, []byte(`{"b":2,"a":1}`))
	c, _ := New(Config{Loader: loader, Clock: frozenClock(time.Unix(1700000000, 0))})

	ref := types.AggregateRef{RealityID: rid, AggregateType: "pc", AggregateID: "pc-1", AggregateVersion: 5}
	// Projection serializes keys in different order — comparator MUST
	// canonicalize and consider them equal.
	res := c.CompareOne(context.Background(), ref, []byte(`{"a":1,"b":2}`))
	if res.Drifted {
		t.Errorf("expected no drift after canonicalization; reason=%s", res.Reason)
	}
	if res.Skipped {
		t.Errorf("unexpected skip: %s", res.SkipReason)
	}
}

func TestCompareOne_BytesDiffer_Drift(t *testing.T) {
	loader := NewInMemLoader()
	rid := uuid.New()
	loader.AddState(rid, "pc", "pc-1", 5, []byte(`{"value":42}`))
	c, _ := New(Config{Loader: loader, Clock: frozenClock(time.Unix(1700000000, 0))})

	ref := types.AggregateRef{RealityID: rid, AggregateType: "pc", AggregateID: "pc-1", AggregateVersion: 5}
	res := c.CompareOne(context.Background(), ref, []byte(`{"value":99}`))
	if !res.Drifted {
		t.Error("expected drift")
	}
	if res.Reason == "" {
		t.Error("drift reason should be populated")
	}
}

func TestCompareOne_LoaderError_Skipped(t *testing.T) {
	loader := NewInMemLoader()
	loader.SetErr(errors.New("event store down"))
	c, _ := New(Config{Loader: loader, Clock: frozenClock(time.Unix(1700000000, 0))})

	rid := uuid.New()
	ref := types.AggregateRef{RealityID: rid, AggregateType: "pc", AggregateID: "pc-1", AggregateVersion: 5}
	res := c.CompareOne(context.Background(), ref, []byte(`{"value":42}`))
	if !res.Skipped {
		t.Error("expected SKIPPED on loader error")
	}
	if res.Drifted {
		t.Error("loader error should NOT count as drift")
	}
}

func TestCompareOne_CanonicalizesNestedStructures(t *testing.T) {
	loader := NewInMemLoader()
	rid := uuid.New()
	loader.AddState(rid, "pc", "pc-1", 5, []byte(`{"inv":[{"id":2,"name":"b"},{"id":1,"name":"a"}],"meta":{"z":1,"a":2}}`))
	c, _ := New(Config{Loader: loader, Clock: frozenClock(time.Unix(1700000000, 0))})

	ref := types.AggregateRef{RealityID: rid, AggregateType: "pc", AggregateID: "pc-1", AggregateVersion: 5}
	// Same structure, different key/value order in nested objects.
	res := c.CompareOne(context.Background(), ref,
		[]byte(`{"meta":{"a":2,"z":1},"inv":[{"name":"b","id":2},{"name":"a","id":1}]}`))
	if res.Drifted {
		t.Errorf("nested canonicalization failed; reason=%s", res.Reason)
	}
}

func TestCompareOne_DistinguishesNumericTypes(t *testing.T) {
	// json.Number preserves int-vs-float — 1 and 1.0 are distinct.
	loader := NewInMemLoader()
	rid := uuid.New()
	loader.AddState(rid, "pc", "pc-1", 5, []byte(`{"v":1}`))
	c, _ := New(Config{Loader: loader, Clock: frozenClock(time.Unix(1700000000, 0))})

	ref := types.AggregateRef{RealityID: rid, AggregateType: "pc", AggregateID: "pc-1", AggregateVersion: 5}
	// Projection wrote 1.0 — this IS drift (the projector lost the integer type).
	res := c.CompareOne(context.Background(), ref, []byte(`{"v":1.0}`))
	if !res.Drifted {
		t.Error("expected drift between 1 and 1.0 (json.Number preserves distinction)")
	}
}

func TestCompareOne_EmptyPayloads_NoDrift(t *testing.T) {
	loader := NewInMemLoader()
	rid := uuid.New()
	loader.AddState(rid, "pc", "pc-1", 5, []byte(``))
	c, _ := New(Config{Loader: loader, Clock: frozenClock(time.Unix(1700000000, 0))})

	ref := types.AggregateRef{RealityID: rid, AggregateType: "pc", AggregateID: "pc-1", AggregateVersion: 5}
	res := c.CompareOne(context.Background(), ref, []byte(``))
	if res.Drifted {
		t.Errorf("empty == empty should not drift; reason=%s", res.Reason)
	}
}

func TestCompareOne_RecordsCheckedAt(t *testing.T) {
	want := time.Unix(1700000000, 0).UTC()
	loader := NewInMemLoader()
	rid := uuid.New()
	loader.AddState(rid, "pc", "pc-1", 5, []byte(`{"a":1}`))
	c, _ := New(Config{Loader: loader, Clock: frozenClock(want)})

	ref := types.AggregateRef{RealityID: rid, AggregateType: "pc", AggregateID: "pc-1", AggregateVersion: 5}
	res := c.CompareOne(context.Background(), ref, []byte(`{"a":1}`))
	if !res.CheckedAt.Equal(want) {
		t.Errorf("CheckedAt drift: got %v want %v", res.CheckedAt, want)
	}
}
