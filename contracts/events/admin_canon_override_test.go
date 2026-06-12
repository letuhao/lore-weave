package events

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/google/uuid"
)

// Cycle 27 L5.H — admin.canon.override.* event family tests.

func TestAdminOverrideReasonIsValid(t *testing.T) {
	cases := []struct {
		r    AdminCanonOverrideReason
		want bool
	}{
		{AdminOverrideReasonAuthorPush, true},
		{AdminOverrideReasonGovernance, true},
		{AdminOverrideReasonSafetyRollback, true},
		{AdminCanonOverrideReason(""), false},
		{AdminCanonOverrideReason("bogus"), false},
	}
	for _, c := range cases {
		if got := c.r.IsValid(); got != c.want {
			t.Errorf("IsValid(%q)=%v want %v", c.r, got, c.want)
		}
	}
}

func TestAdminCanonOverrideRequestedV1_RoundTrip(t *testing.T) {
	now := time.Now().UTC().Truncate(time.Second)
	src := AdminCanonOverrideRequestedV1{
		OverrideID:        uuid.New(),
		CanonEntryID:      uuid.New(),
		BookID:            uuid.New(),
		AttributePath:     "world.climate",
		NewValue:          []byte(`{"climate":"arid"}`),
		CanonLayer:        CanonLayerL2Seeded,
		Reason:            AdminOverrideReasonAuthorPush,
		RequestedBy:       uuid.New(),
		RequestedAt:       now,
		ConsentDeadlineAt: now.Add(24 * time.Hour),
	}
	raw, err := json.Marshal(src)
	if err != nil {
		t.Fatal(err)
	}
	var dst AdminCanonOverrideRequestedV1
	if err := json.Unmarshal(raw, &dst); err != nil {
		t.Fatal(err)
	}
	if dst.OverrideID != src.OverrideID {
		t.Error("override_id mismatch")
	}
	if dst.ConsentDeadlineAt.Sub(dst.RequestedAt) != 24*time.Hour {
		t.Errorf("Q-L5H-1: 24h consent deadline must round-trip; got delta=%s", dst.ConsentDeadlineAt.Sub(dst.RequestedAt))
	}
}

func TestAdminCanonOverrideRequestedV1_WireFieldNames(t *testing.T) {
	src := AdminCanonOverrideRequestedV1{
		OverrideID:        uuid.New(),
		CanonEntryID:      uuid.New(),
		BookID:            uuid.New(),
		AttributePath:     "x",
		NewValue:          []byte(`"v"`),
		CanonLayer:        CanonLayerL1Axiom,
		Reason:            AdminOverrideReasonGovernance,
		RequestedBy:       uuid.New(),
		RequestedAt:       time.Unix(1780000000, 0).UTC(),
		ConsentDeadlineAt: time.Unix(1780086400, 0).UTC(),
	}
	raw, err := json.Marshal(src)
	if err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{
		`"override_id"`, `"canon_entry_id"`, `"book_id"`, `"attribute_path"`,
		`"new_value"`, `"canon_layer"`, `"reason"`, `"requested_by"`,
		`"requested_at"`, `"consent_deadline_at"`,
	} {
		if !contains(string(raw), key) {
			t.Errorf("wire-stable field %s missing from %s", key, string(raw))
		}
	}
}

func TestAdminCanonOverrideConsentedV1_DefaultConsentFlag(t *testing.T) {
	src := AdminCanonOverrideConsentedV1{
		OverrideID:     uuid.New(),
		RealityID:      uuid.New(),
		ConsentedAt:    time.Now().UTC(),
		DefaultConsent: true,
		// ConsentedBy intentionally zero (Q-L5H-1 default path).
	}
	raw, err := json.Marshal(src)
	if err != nil {
		t.Fatal(err)
	}
	if !contains(string(raw), `"default_consent":true`) {
		t.Errorf("Q-L5H-1: default_consent flag must serialize: %s", string(raw))
	}
}

func TestAdminCanonOverrideVetoedV1_CarriesReason(t *testing.T) {
	src := AdminCanonOverrideVetoedV1{
		OverrideID: uuid.New(),
		RealityID:  uuid.New(),
		VetoedAt:   time.Now().UTC(),
		VetoedBy:   uuid.New(),
		Reason:     "reality lore conflict",
	}
	raw, err := json.Marshal(src)
	if err != nil {
		t.Fatal(err)
	}
	var dst AdminCanonOverrideVetoedV1
	if err := json.Unmarshal(raw, &dst); err != nil {
		t.Fatal(err)
	}
	if dst.Reason != "reality lore conflict" {
		t.Errorf("veto reason lost: %q", dst.Reason)
	}
}

func TestAdminCanonOverrideCompensatingV1_AuditDistinguishable(t *testing.T) {
	// The compensating event MUST carry both old + new value so audit can
	// reconstruct the per-reality canon-projection delta WITHOUT a join.
	src := AdminCanonOverrideCompensatingV1{
		OverrideID:     uuid.New(),
		RealityID:      uuid.New(),
		CanonEntryID:   uuid.New(),
		BookID:         uuid.New(),
		AttributePath:  "world.climate",
		OldValue:       []byte(`"temperate"`),
		NewValue:       []byte(`"arid"`),
		CanonLayer:     CanonLayerL2Seeded,
		AppliedAt:      time.Now().UTC(),
		DefaultConsent: false,
	}
	raw, err := json.Marshal(src)
	if err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{
		`"override_id"`, `"reality_id"`, `"old_value"`, `"new_value"`,
		`"default_consent"`, `"applied_at"`,
	} {
		if !contains(string(raw), key) {
			t.Errorf("compensating event MUST carry %s for audit; missing in %s", key, string(raw))
		}
	}
}

// (uses the `contains` helper already defined in canon_test.go).
