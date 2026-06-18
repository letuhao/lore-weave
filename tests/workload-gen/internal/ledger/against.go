package ledger

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"

	"github.com/google/uuid"

	events "github.com/loreweave/foundation/contracts/events"
)

// CheckAgainstExpected reconciles a stored Log against the deterministic
// generator's expected stream (the baseline). It catches what self-consistency
// cannot: a lost event (missing-event), an injected/duplicated event
// (unexpected-event), a mutated envelope field (field-mismatch), and — the
// deepest one — a byte-rotted payload (payload-mismatch via canonical hash).
//
// Pass the SAME (seed, profile) that produced the stored data:
//
//	CheckAgainstExpected(log, gen.New(seed).Generate(profile))
func CheckAgainstExpected(log Log, expected []events.Envelope) Report {
	var r Report

	exp := make(map[uuid.UUID]events.Envelope, len(expected))
	for _, e := range expected {
		exp[e.EventID] = e
	}
	stored := make(map[uuid.UUID]EventRow, len(log.Events))
	for _, e := range log.Events {
		stored[e.EventID] = e
	}

	for _, id := range sortedExpected(exp) {
		want := exp[id]
		got, ok := stored[id]
		if !ok {
			r.add(KindMissingEvent, fmt.Sprintf("event %s (%s, %s/%s v%d) expected but not stored",
				id, want.EventType, want.AggregateType, want.AggregateID, want.AggregateVersion))
			continue
		}
		if got.RealityID != want.RealityID || got.AggType != want.AggregateType ||
			got.AggID != want.AggregateID || got.EventType != want.EventType ||
			got.Version != want.AggregateVersion {
			r.add(KindFieldMismatch, fmt.Sprintf(
				"event %s: stored (%s, %s/%s v%d) != expected (%s, %s/%s v%d)",
				id, got.EventType, got.AggType, got.AggID, got.Version,
				want.EventType, want.AggregateType, want.AggregateID, want.AggregateVersion))
		}
		wantH, err1 := payloadHash(want.Payload)
		gotH, err2 := payloadHash(got.Payload)
		switch {
		case err1 != nil || err2 != nil:
			r.add(KindPayloadMismatch, fmt.Sprintf("event %s: payload hash error", id))
		case wantH != gotH:
			r.add(KindPayloadMismatch, fmt.Sprintf("event %s: payload hash %s… != expected %s…", id, gotH[:12], wantH[:12]))
		}
	}

	for _, id := range sortedStored(stored) {
		if _, ok := exp[id]; !ok {
			r.add(KindUnexpectedEvent, fmt.Sprintf("event %s (%s) stored but not expected", id, stored[id].EventType))
		}
	}
	return r
}

// payloadHash canonicalizes a payload and returns its SHA-256.
//
// It marshals → unmarshals → marshals so both the generator's Go-typed payload
// (int 1) and the JSONB-roundtripped stored payload (float64 1) normalize to the
// same bytes before hashing. encoding/json sorts map keys, so key order does not
// affect the hash; only the LOGICAL value does — a byte-rotted payload flips it.
func payloadHash(p map[string]any) (string, error) {
	b1, err := json.Marshal(p)
	if err != nil {
		return "", err
	}
	var norm map[string]any
	if err := json.Unmarshal(b1, &norm); err != nil {
		return "", err
	}
	b2, err := json.Marshal(norm)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(b2)
	return hex.EncodeToString(sum[:]), nil
}

func sortedExpected(m map[uuid.UUID]events.Envelope) []uuid.UUID {
	ids := make([]uuid.UUID, 0, len(m))
	for id := range m {
		ids = append(ids, id)
	}
	sort.Slice(ids, func(i, j int) bool { return ids[i].String() < ids[j].String() })
	return ids
}

func sortedStored(m map[uuid.UUID]EventRow) []uuid.UUID {
	ids := make([]uuid.UUID, 0, len(m))
	for id := range m {
		ids = append(ids, id)
	}
	sort.Slice(ids, func(i, j int) bool { return ids[i].String() < ids[j].String() })
	return ids
}
