package events

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/google/uuid"
)

func TestCanonChangeKindIsValid(t *testing.T) {
	cases := []struct {
		k    CanonChangeKind
		want bool
	}{
		{CanonChangeKindAuthored, true},
		{CanonChangeKindForcePropagate, true},
		{CanonChangeKindPropagationCompleted, true},
		{CanonChangeKind(""), false},
		{CanonChangeKind("bogus"), false},
	}
	for _, c := range cases {
		if got := c.k.IsValid(); got != c.want {
			t.Errorf("IsValid(%q)=%v want %v", c.k, got, c.want)
		}
	}
}

func TestCanonChangeRecordedV1_RoundTrip(t *testing.T) {
	src := CanonChangeRecordedV1{
		ChangeID:        uuid.New(),
		CanonEntryID:    uuid.New(),
		BookID:          uuid.New(),
		AttributePath:   "world.climate",
		RealityID:       uuid.New(),
		Kind:            CanonChangeKindForcePropagate,
		OldValue:        []byte(`"temperate"`),
		NewValue:        []byte(`"arid"`),
		CanonLayer:      CanonLayerL2Seeded,
		SourceEventID:   uuid.New(),
		SourceEventType: "admin.canon.override.compensating",
		RecordedAt:      time.Now().UTC().Truncate(time.Second),
	}
	raw, err := json.Marshal(src)
	if err != nil {
		t.Fatal(err)
	}
	var dst CanonChangeRecordedV1
	if err := json.Unmarshal(raw, &dst); err != nil {
		t.Fatal(err)
	}
	if dst.ChangeID != src.ChangeID {
		t.Error("change_id mismatch")
	}
	if dst.Kind != CanonChangeKindForcePropagate {
		t.Error("kind drift")
	}
}

func TestCanonChangeRecordedV1_WireFieldNames(t *testing.T) {
	src := CanonChangeRecordedV1{
		ChangeID:        uuid.New(),
		CanonEntryID:    uuid.New(),
		BookID:          uuid.New(),
		AttributePath:   "x",
		Kind:            CanonChangeKindAuthored,
		NewValue:        []byte(`"v"`),
		CanonLayer:      CanonLayerL1Axiom,
		SourceEventID:   uuid.New(),
		SourceEventType: "canon.entry.created",
		RecordedAt:      time.Unix(1780000000, 0).UTC(),
	}
	raw, err := json.Marshal(src)
	if err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{
		`"change_id"`, `"canon_entry_id"`, `"book_id"`, `"attribute_path"`,
		`"kind"`, `"new_value"`, `"canon_layer"`, `"source_event_id"`,
		`"source_event_type"`, `"recorded_at"`,
	} {
		if !contains(string(raw), key) {
			t.Errorf("wire-stable field %s missing from %s", key, string(raw))
		}
	}
}

func TestCanonChangeRecordedV1_BookWideOmitsReality(t *testing.T) {
	// When RealityID is zero (book-wide change), JSON output may omit
	// the field (omitempty). The decoder is OK either way.
	src := CanonChangeRecordedV1{
		ChangeID:        uuid.New(),
		CanonEntryID:    uuid.New(),
		BookID:          uuid.New(),
		AttributePath:   "x",
		Kind:            CanonChangeKindAuthored,
		NewValue:        []byte(`"v"`),
		CanonLayer:      CanonLayerL2Seeded,
		SourceEventID:   uuid.New(),
		SourceEventType: "canon.entry.created",
		RecordedAt:      time.Now().UTC(),
		// RealityID intentionally zero
	}
	raw, err := json.Marshal(src)
	if err != nil {
		t.Fatal(err)
	}
	// Note: uuid.Nil serializes as "00000000-...". The contract permits
	// either zero-uuid or omitted; we just confirm round-trip works.
	var dst CanonChangeRecordedV1
	if err := json.Unmarshal(raw, &dst); err != nil {
		t.Fatal(err)
	}
	if dst.Kind != CanonChangeKindAuthored {
		t.Error("kind drift on book-wide change")
	}
}
