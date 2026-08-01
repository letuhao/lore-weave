package redisemit

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/publisher/pkg/types"
)

func TestStreamFor(t *testing.T) {
	if got := StreamFor("abc"); got != "lw.events.abc" {
		t.Errorf("StreamFor=%q want lw.events.abc", got)
	}
}

func TestEnvelopeFields_CoreAndJSON(t *testing.T) {
	eid := uuid.New()
	rid := uuid.New()
	row := types.OutboxRow{
		EventID:          eid,
		RealityID:        rid,
		EventType:        "npc.said",
		EventVersion:     2,
		AggregateType:    "npc",
		AggregateID:      "npc-7",
		AggregateVersion: 42,
		OccurredAt:       time.Date(2026, 5, 30, 10, 0, 0, 0, time.UTC),
		RecordedAt:       time.Date(2026, 5, 30, 10, 0, 1, 0, time.UTC),
		Payload:          map[string]any{"text": "hi"},
		Metadata:         map[string]any{"cross_reality": true},
	}
	f := envelopeFields(row)
	if f["event_id"] != eid.String() || f["reality_id"] != rid.String() {
		t.Errorf("ids wrong: %v", f)
	}
	if f["event_type"] != "npc.said" || f["aggregate_version"] != uint64(42) {
		t.Errorf("core fields wrong: %v", f)
	}
	// After scalarize, payload/metadata must be JSON strings.
	vals, err := scalarize(f)
	if err != nil {
		t.Fatal(err)
	}
	pj, ok := vals["payload"].(string)
	if !ok {
		t.Fatalf("payload should scalarize to string, got %T", vals["payload"])
	}
	var back map[string]any
	if err := json.Unmarshal([]byte(pj), &back); err != nil {
		t.Fatalf("payload not valid json: %v", err)
	}
	if back["text"] != "hi" {
		t.Errorf("payload round-trip wrong: %v", back)
	}
}

func TestScalarize_PassesScalars(t *testing.T) {
	in := map[string]any{
		"s": "str", "i": 7, "u": uint64(9), "f": 1.5, "b": true, "raw": []byte("x"),
		"nilv": nil,
	}
	out, err := scalarize(in)
	if err != nil {
		t.Fatal(err)
	}
	if out["s"] != "str" || out["i"] != 7 || out["u"] != uint64(9) || out["f"] != 1.5 || out["b"] != true {
		t.Errorf("scalars mutated: %v", out)
	}
	if out["nilv"] != "" {
		t.Errorf("nil should map to empty string, got %v", out["nilv"])
	}
}

func TestScalarize_EncodesComposites(t *testing.T) {
	out, err := scalarize(map[string]any{"arr": []int{1, 2, 3}})
	if err != nil {
		t.Fatal(err)
	}
	if out["arr"] != "[1,2,3]" {
		t.Errorf("slice should JSON-encode, got %v", out["arr"])
	}
}

func TestEnvelopeFields_OmitsNilPayloadMetadata(t *testing.T) {
	row := types.OutboxRow{EventID: uuid.New(), RealityID: uuid.New(), EventType: "x.y.z"}
	f := envelopeFields(row)
	if _, ok := f["payload"]; ok {
		t.Error("nil payload should be omitted")
	}
	if _, ok := f["metadata"]; ok {
		t.Error("nil metadata should be omitted")
	}
}

// D-PUBLISHER-DROPS-RULESET-PIN — the pin must survive the last hop.
//
// It did not: the outbox SELECT never fetched `e.ruleset_digest`, and
// `contracts/events/envelope.go`'s json tag is `omitempty`, so the field left
// the reality DB and simply ceased to exist with nothing anywhere reporting it.
// RLS-A13 makes the digest the thing that ties an event to the rules that
// produced it; QTY-A14 makes it the thing that gives a per-reality quantity
// ordinal its meaning. A consumer holding an ordinal and no digest resolves it
// against whatever table it happens to have.
func TestEnvelopeFields_CarriesRulesetPin(t *testing.T) {
	digest := "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
	f := envelopeFields(types.OutboxRow{RulesetDigest: &digest})
	if f["ruleset_digest"] != digest {
		t.Errorf("ruleset_digest=%v want %q", f["ruleset_digest"], digest)
	}
}

// ABSENT, not empty — a consumer must be able to tell "this event has no
// ruleset" from "this event is pinned to the empty string". Same discipline the
// channel-ordering fields above already follow.
func TestEnvelopeFields_OmitsAbsentRulesetPin(t *testing.T) {
	if f := envelopeFields(types.OutboxRow{}); f["ruleset_digest"] != nil {
		t.Errorf("nil pin must be ABSENT, got %v", f["ruleset_digest"])
	}
	empty := ""
	if f := envelopeFields(types.OutboxRow{RulesetDigest: &empty}); f["ruleset_digest"] != nil {
		t.Errorf("empty pin must be ABSENT, got %v", f["ruleset_digest"])
	}
}
