package ledger

import (
	"encoding/json"
	"testing"

	"github.com/loreweave/foundation/tests/workload-gen/internal/gen"
)

// storedFromStream maps the generator's expected stream into a stored Log,
// roundtripping each payload through JSON so numbers become float64 — exactly
// what LoadLog returns from JSONB. A clean reconcile therefore also proves the
// hash is robust to the int→float64 normalization (plan R1).
func storedFromStream(t *testing.T, s gen.Stream) Log {
	t.Helper()
	var log Log
	for _, e := range s {
		b, err := json.Marshal(e.Payload)
		if err != nil {
			t.Fatal(err)
		}
		var p map[string]any
		if err := json.Unmarshal(b, &p); err != nil {
			t.Fatal(err)
		}
		log.Events = append(log.Events, EventRow{
			EventID: e.EventID, RealityID: e.RealityID, AggType: e.AggregateType,
			AggID: e.AggregateID, EventType: e.EventType, Version: e.AggregateVersion, Payload: p,
		})
		log.OutboxIDs = append(log.OutboxIDs, e.EventID)
	}
	return log
}

func TestAgainstExpectedCleanReconcile(t *testing.T) {
	stream := gen.New(1).Generate(gen.Profiles["single-reality"])
	log := storedFromStream(t, stream)
	r := CheckAgainstExpected(log, stream)
	if !r.OK() {
		t.Errorf("a faithfully-stored stream must reconcile clean (incl int→float64 payloads), got: %s", r)
	}
}

func TestAgainstExpectedPayloadByteRot(t *testing.T) {
	stream := gen.New(2).Generate(gen.Profiles["micro"])
	log := storedFromStream(t, stream)
	// byte-rot: mutate a stored payload value
	for i := range log.Events {
		if len(log.Events[i].Payload) > 0 {
			log.Events[i].Payload["__rot__"] = "corrupted"
			break
		}
	}
	if !CheckAgainstExpected(log, stream).Has(KindPayloadMismatch) {
		t.Error("a mutated stored payload must be a payload-mismatch")
	}
}

func TestAgainstExpectedMissingEvent(t *testing.T) {
	stream := gen.New(3).Generate(gen.Profiles["micro"])
	log := storedFromStream(t, stream)
	log.Events = log.Events[1:] // drop one stored event that is still expected
	if !CheckAgainstExpected(log, stream).Has(KindMissingEvent) {
		t.Error("an expected-but-not-stored event must be a missing-event")
	}
}

func TestAgainstExpectedUnexpectedEvent(t *testing.T) {
	stream := gen.New(4).Generate(gen.Profiles["micro"])
	log := storedFromStream(t, stream)
	extra := log.Events[0]
	extra.EventID = gen.New(99).Generate(gen.Profiles["micro"])[0].EventID // a different id
	log.Events = append(log.Events, extra)
	if !CheckAgainstExpected(log, stream).Has(KindUnexpectedEvent) {
		t.Error("a stored-but-not-expected event must be an unexpected-event")
	}
}

func TestAgainstExpectedFieldMismatch(t *testing.T) {
	stream := gen.New(5).Generate(gen.Profiles["micro"])
	log := storedFromStream(t, stream)
	log.Events[0].Version = 999 // mutate an envelope field
	if !CheckAgainstExpected(log, stream).Has(KindFieldMismatch) {
		t.Error("a mutated envelope field must be a field-mismatch")
	}
}
