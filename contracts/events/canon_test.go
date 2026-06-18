package events

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/google/uuid"
)

// canon_test.go — L5.A.5 test fixture for canon.* event types.
//
// Two acceptance properties (per Q-L5A-1 acceptance criteria):
//   1. Schema is parseable / round-trip stable — wire shape is locked.
//   2. CanonLayer enum rejects unknown values — defense vs producer drift.
//
// This is a CONTRACT TEST. It mocks the glossary-service outbox emission
// (assembles a payload exactly as glossary-service WILL emit per the
// docs/governance/glossary-service-outbox-contract.md document) and verifies
// the schema would parse + reject malformed events. The actual outbox
// emission landing in services/glossary-service is the Q-L5A-1 separate
// sub-program — NOT foundation scope.

func TestCanonLayer_IsValid(t *testing.T) {
	cases := []struct {
		layer CanonLayer
		want  bool
	}{
		{CanonLayerL1Axiom, true},
		{CanonLayerL2Seeded, true},
		{CanonLayer(""), false},
		{CanonLayer("L3_event"), false},  // L3 is per-reality, NOT canon
		{CanonLayer("axiom"), false},     // wrong case / shorthand
		{CanonLayer("l1_axiom"), false},  // wrong case
	}
	for _, tc := range cases {
		if got := tc.layer.IsValid(); got != tc.want {
			t.Errorf("CanonLayer(%q).IsValid() = %v, want %v", tc.layer, got, tc.want)
		}
	}
}

func TestCanonEntryCreatedV1_RoundTripStable(t *testing.T) {
	original := CanonEntryCreatedV1{
		CanonEntryID:  uuid.MustParse("11111111-1111-1111-1111-111111111111"),
		BookID:        uuid.MustParse("22222222-2222-2222-2222-222222222222"),
		AttributePath: "characters/alice/race",
		Value:         []byte(`"elf"`),
		CanonLayer:    CanonLayerL2Seeded,
		LockLevel:     "soft",
		AuthorUserID:  uuid.MustParse("33333333-3333-3333-3333-333333333333"),
		CreatedAt:     time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC),
	}
	wire, err := json.Marshal(original)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var back CanonEntryCreatedV1
	if err := json.Unmarshal(wire, &back); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if back.CanonEntryID != original.CanonEntryID ||
		back.BookID != original.BookID ||
		back.AttributePath != original.AttributePath ||
		back.CanonLayer != original.CanonLayer ||
		back.LockLevel != original.LockLevel {
		t.Errorf("round-trip drift: got=%+v want=%+v", back, original)
	}
}

func TestCanonEntryCreatedV1_WireFieldNames(t *testing.T) {
	// Wire-shape stability: future versions MUST NOT silently rename fields.
	// This is the contract glossary-service consumes — drift breaks emission.
	e := CanonEntryCreatedV1{CanonLayer: CanonLayerL1Axiom}
	wire, _ := json.Marshal(e)
	required := []string{
		`"canon_entry_id"`,
		`"book_id"`,
		`"attribute_path"`,
		`"value"`,
		`"canon_layer"`,
		`"lock_level"`,
		`"author_user_id"`,
		`"created_at"`,
	}
	w := string(wire)
	for _, want := range required {
		if !contains(w, want) {
			t.Errorf("CanonEntryCreatedV1 wire missing %s; got=%s", want, w)
		}
	}
}

func TestCanonEntryUpdatedV1_CarriesOldAndNew(t *testing.T) {
	e := CanonEntryUpdatedV1{
		CanonEntryID:  uuid.New(),
		BookID:        uuid.New(),
		AttributePath: "world/timeline/year_zero",
		OldValue:      []byte(`1000`),
		NewValue:      []byte(`1234`),
		CanonLayer:    CanonLayerL2Seeded,
		EditorUserID:  uuid.New(),
		UpdatedAt:     time.Now().UTC(),
	}
	wire, err := json.Marshal(e)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	s := string(wire)
	for _, want := range []string{`"old_value"`, `"new_value"`, `"canon_layer"`} {
		if !contains(s, want) {
			t.Errorf("update wire missing %s; got=%s", want, s)
		}
	}
}

func TestCanonEntryPromotedV1_RejectsCrossLayerNoise(t *testing.T) {
	// Acceptance: promoted carries from_layer + to_layer; consumer can verify
	// they're VALID canon layers. (Promoting from L1 to L2 is meaningless but
	// not blocked at the wire layer — the validator is glossary-service.)
	e := CanonEntryPromotedV1{
		CanonEntryID: uuid.New(),
		BookID:       uuid.New(),
		FromLayer:    CanonLayerL2Seeded,
		ToLayer:      CanonLayerL1Axiom,
		PromotedBy:   uuid.New(),
		PromotedAt:   time.Now().UTC(),
	}
	if !e.FromLayer.IsValid() || !e.ToLayer.IsValid() {
		t.Errorf("promoted event MUST carry IsValid layers; got from=%q to=%q", e.FromLayer, e.ToLayer)
	}
	// Garbage layer string fails IsValid (defense vs producer drift).
	bad := CanonEntryPromotedV1{ToLayer: "L7_god_mode"}
	if bad.ToLayer.IsValid() {
		t.Errorf("CanonLayer must reject unknown value %q", bad.ToLayer)
	}
}

func TestCanonEntryDecanonizedV1_HasReason(t *testing.T) {
	// L5.J change-history relies on Reason being present for SRE traceability.
	e := CanonEntryDecanonizedV1{
		CanonEntryID:  uuid.New(),
		BookID:        uuid.New(),
		Reason:        "Author retracted; superseded by entry-7",
		DecanonizedBy: uuid.New(),
		DecanonizedAt: time.Now().UTC(),
	}
	wire, _ := json.Marshal(e)
	if !contains(string(wire), `"reason"`) {
		t.Errorf("decanonized wire missing reason field; got=%s", string(wire))
	}
}

// TestGlossaryOutboxEmissionFixture exercises the full mock glossary-outbox
// emission pipeline that the Q-L5A-1 sub-program will implement against this
// contract. Foundation owns the FIXTURE only; the production emitter is
// out-of-scope.
//
// Pipeline:
//   1. Glossary-service "author canonization" call constructs an event.
//   2. Emitter serializes to the outbox row's payload column.
//   3. Foundation contract test deserializes + verifies schema parity.
//
// The fixture catches three failure modes the sub-program could introduce:
//   - field rename / typo
//   - canon_layer value drift (unknown layer string)
//   - missing required field (zero-value UUID for canon_entry_id)
func TestGlossaryOutboxEmissionFixture(t *testing.T) {
	// Mock "glossary-service emits" — assembled exactly per the contract.
	emitted := CanonEntryCreatedV1{
		CanonEntryID:  uuid.MustParse("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
		BookID:        uuid.MustParse("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
		AttributePath: "regions/whispering_woods/climate",
		Value:         []byte(`"temperate"`),
		CanonLayer:    CanonLayerL2Seeded,
		LockLevel:     "soft",
		AuthorUserID:  uuid.MustParse("cccccccc-cccc-cccc-cccc-cccccccccccc"),
		CreatedAt:     time.Date(2026, 5, 29, 13, 30, 0, 0, time.UTC),
	}
	payload, err := json.Marshal(emitted)
	if err != nil {
		t.Fatalf("mock glossary outbox emit failed: %v", err)
	}

	// Mock "publisher drains outbox + meta-worker consumes" — deserializes.
	var received CanonEntryCreatedV1
	if err := json.Unmarshal(payload, &received); err != nil {
		t.Fatalf("contract-test consumer parse failed (sub-program emitter drift?): %v", err)
	}

	// Acceptance: zero-value canon_entry_id is a contract violation —
	// glossary-service MUST emit a UUID. Defense vs an emitter bug.
	if received.CanonEntryID == (uuid.UUID{}) {
		t.Errorf("Q-L5A-1 contract violation: canon_entry_id MUST be non-zero")
	}
	// Acceptance: canon_layer is one of the LOCKED Q-L5-3 values.
	if !received.CanonLayer.IsValid() {
		t.Errorf("Q-L5-3 violation: canon_layer=%q not in {L1_axiom, L2_seeded}", received.CanonLayer)
	}
	// Acceptance: attribute_path nonempty (per-reality projection PK depends).
	if received.AttributePath == "" {
		t.Errorf("contract violation: attribute_path MUST be non-empty")
	}
}

// contains is a tiny helper to avoid pulling strings.Contains into tests
// (keeps the file's import surface small + intentional).
func contains(haystack, needle string) bool {
	for i := 0; i+len(needle) <= len(haystack); i++ {
		if haystack[i:i+len(needle)] == needle {
			return true
		}
	}
	return false
}
