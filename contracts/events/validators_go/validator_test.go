package validatorsgo

import (
	"errors"
	"testing"

	events "github.com/loreweave/foundation/contracts/events"
)

func TestSeedRegistry_BuildsCorrectly(t *testing.T) {
	r := BuildSeedRegistry()
	for _, c := range []struct {
		t string
		v uint32
	}{
		{"reality.created", 1},
		{"npc.said", 1},
		{"npc.said", 2},
		{"world.tick", 1},
	} {
		if !r.Knows(c.t, c.v) {
			t.Errorf("seed registry missing %s v%d", c.t, c.v)
		}
	}
}

func TestValidate_HappyPath_NpcSaidV2(t *testing.T) {
	r := BuildSeedRegistry()
	err := r.Validate("npc.said", 2, map[string]any{
		"npc_id":   "00000000-0000-0000-0000-000000000001",
		"text":     "hello",
		"scene_id": "00000000-0000-0000-0000-000000000002",
		"said_at":  "2026-05-29T12:00:00Z",
		"tone":     "neutral",
	})
	if err != nil {
		t.Fatalf("happy path rejected: %v", err)
	}
}

func TestValidate_MissingFieldRejected(t *testing.T) {
	r := BuildSeedRegistry()
	err := r.Validate("npc.said", 2, map[string]any{
		"npc_id": "x", "text": "x", "scene_id": "x", "said_at": "x",
		// missing tone
	})
	if err == nil {
		t.Fatal("expected violation for missing tone")
	}
	var typed events.ErrSchemaViolationText
	if !errors.As(err, &typed) {
		t.Errorf("expected ErrSchemaViolationText; got %T", err)
	}
}

func TestValidate_WrongTypeRejected(t *testing.T) {
	r := BuildSeedRegistry()
	// tick_index expected number; pass string
	err := r.Validate("world.tick", 1, map[string]any{
		"reality_id": "x",
		"tick_index": "not-a-number",
		"tick_at":    "x",
	})
	if err == nil {
		t.Fatal("expected violation for wrong type")
	}
	var typed events.ErrSchemaViolationText
	if !errors.As(err, &typed) {
		t.Errorf("expected ErrSchemaViolationText; got %T", err)
	}
}

func TestValidate_AcceptsFloat64ForNumberField(t *testing.T) {
	// encoding/json decodes JSON numbers to float64 by default; tick_index
	// must still validate (we accept the lossy form because event payloads
	// arrive as map[string]any from json.Unmarshal).
	r := BuildSeedRegistry()
	err := r.Validate("world.tick", 1, map[string]any{
		"reality_id": "x",
		"tick_index": float64(42),
		"tick_at":    "x",
	})
	if err != nil {
		t.Fatalf("float64 tick_index rejected: %v", err)
	}
}

func TestValidate_AcceptsIntegerTypesForNumberField(t *testing.T) {
	r := BuildSeedRegistry()
	for _, n := range []any{int(1), int32(1), int64(1), uint(1), uint64(1)} {
		err := r.Validate("world.tick", 1, map[string]any{
			"reality_id": "x",
			"tick_index": n,
			"tick_at":    "x",
		})
		if err != nil {
			t.Errorf("integer %T rejected: %v", n, err)
		}
	}
}

func TestValidate_UnknownEventTypeRejected(t *testing.T) {
	r := BuildSeedRegistry()
	err := r.Validate("nonexistent.event", 1, map[string]any{})
	if err == nil {
		t.Fatal("expected unknown-schema error")
	}
	var typed events.ErrUnknownEventSchemaText
	if !errors.As(err, &typed) {
		t.Errorf("expected ErrUnknownEventSchemaText; got %T", err)
	}
}

func TestValidate_UnknownVersionRejected(t *testing.T) {
	r := BuildSeedRegistry()
	err := r.Validate("npc.said", 99, map[string]any{})
	if err == nil {
		t.Fatal("expected unknown-schema error")
	}
	var typed events.ErrUnknownEventSchemaText
	if !errors.As(err, &typed) {
		t.Errorf("expected ErrUnknownEventSchemaText; got %T", err)
	}
}

func TestValidate_LenientModeAcceptsExtraFields(t *testing.T) {
	r := BuildSeedRegistry()
	err := r.Validate("npc.said", 2, map[string]any{
		"npc_id": "x", "text": "x", "scene_id": "x", "said_at": "x", "tone": "x",
		"future_extension_field": "ignored",
	})
	if err != nil {
		t.Errorf("lenient mode rejected extra field: %v", err)
	}
}

func TestValidate_StrictModeRejectsUnknownFields(t *testing.T) {
	r := NewRegistry()
	r.Register(SchemaDescriptor{
		EventType:    "strict.test",
		EventVersion: 1,
		RequiredFields: []RequiredField{
			{Name: "a", Ty: FieldString},
		},
		StrictUnknown: true,
	})
	err := r.Validate("strict.test", 1, map[string]any{
		"a":         "x",
		"extra":     "boom",
	})
	if err == nil {
		t.Fatal("expected strict-mode rejection")
	}
	var typed events.ErrSchemaViolationText
	if !errors.As(err, &typed) {
		t.Errorf("expected ErrSchemaViolationText; got %T", err)
	}
}

func TestValidate_NilPayloadRejected(t *testing.T) {
	r := BuildSeedRegistry()
	err := r.Validate("npc.said", 2, nil)
	if err == nil {
		t.Fatal("expected violation for nil payload")
	}
}
