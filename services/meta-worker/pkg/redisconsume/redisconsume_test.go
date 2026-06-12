package redisconsume

import "testing"

func TestFlatten_MergesPayloadToTopLevel(t *testing.T) {
	in := map[string]interface{}{
		"event_id":          "ev-1",
		"event_type":        "canon.entry.created",
		"aggregate_version": "3",
		"payload":           `{"canon_entry_id":"ce-1","book_id":"bk-1","attribute_path":"a/b"}`,
		"metadata":          `{"cross_reality":true}`,
	}
	out := flatten(in)
	// Domain fields from payload surface at the top level.
	if out["canon_entry_id"] != "ce-1" || out["book_id"] != "bk-1" || out["attribute_path"] != "a/b" {
		t.Errorf("payload not flattened: %v", out)
	}
	// Envelope fields preserved.
	if out["event_id"] != "ev-1" || out["event_type"] != "canon.entry.created" || out["aggregate_version"] != "3" {
		t.Errorf("envelope fields lost: %v", out)
	}
	// metadata also merged.
	if out["cross_reality"] != true {
		t.Errorf("metadata not merged: %v", out)
	}
}

func TestFlatten_EnvelopeWinsOnConflict(t *testing.T) {
	in := map[string]interface{}{
		"event_type": "canon.entry.created", // envelope (inner) — must win
		"payload":    `{"event_type":"WRONG","x":1}`,
	}
	out := flatten(in)
	if out["event_type"] != "canon.entry.created" {
		t.Errorf("envelope event_type should win, got %v", out["event_type"])
	}
	if out["x"] != float64(1) {
		t.Errorf("non-conflicting payload key should merge, got %v", out["x"])
	}
}

func TestFlatten_NonJSONPayloadIgnored(t *testing.T) {
	in := map[string]interface{}{
		"event_id": "ev-1",
		"payload":  "not-json",
	}
	out := flatten(in)
	if out["event_id"] != "ev-1" {
		t.Errorf("envelope lost: %v", out)
	}
	// payload stays as the raw string; no panic.
	if out["payload"] != "not-json" {
		t.Errorf("payload should remain raw, got %v", out["payload"])
	}
}

func TestFlatten_NoPayload(t *testing.T) {
	in := map[string]interface{}{"event_id": "ev-1", "user_id": "u-1"}
	out := flatten(in)
	if out["event_id"] != "ev-1" || out["user_id"] != "u-1" {
		t.Errorf("flatten dropped fields: %v", out)
	}
}
