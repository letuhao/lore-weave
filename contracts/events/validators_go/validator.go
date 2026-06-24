package validatorsgo

import (
	"fmt"

	events "github.com/loreweave/foundation/contracts/events"
)

// FieldType is the minimal type-tag set the V1 validator enforces. Keep
// byte-identical with crates/dp-kernel::event_validator::FieldType.
type FieldType int

const (
	FieldString FieldType = iota
	FieldNumber
	FieldBool
	FieldObject
	FieldArray
)

func (f FieldType) String() string {
	switch f {
	case FieldString:
		return "string"
	case FieldNumber:
		return "number"
	case FieldBool:
		return "boolean"
	case FieldObject:
		return "object"
	case FieldArray:
		return "array"
	}
	return "unknown"
}

// matches checks whether v matches the field type. JSON-decoded payloads
// (map[string]any from encoding/json) produce these Go types:
//
//	JSON string → string
//	JSON number → float64 (encoding/json default)
//	JSON bool   → bool
//	JSON object → map[string]any
//	JSON array  → []any
//
// We accept float64 OR int OR int64 for FieldNumber (callers may pre-decode
// to typed numerics).
func (f FieldType) matches(v any) bool {
	switch f {
	case FieldString:
		_, ok := v.(string)
		return ok
	case FieldNumber:
		switch v.(type) {
		case float64, float32, int, int32, int64, uint, uint32, uint64:
			return true
		}
		return false
	case FieldBool:
		_, ok := v.(bool)
		return ok
	case FieldObject:
		_, ok := v.(map[string]any)
		return ok
	case FieldArray:
		_, ok := v.([]any)
		return ok
	}
	return false
}

// RequiredField names + types one required field.
type RequiredField struct {
	Name string
	Ty   FieldType
}

// SchemaDescriptor describes the shape for one (event_type, event_version).
type SchemaDescriptor struct {
	EventType        string
	EventVersion     uint32
	RequiredFields   []RequiredField
	StrictUnknown    bool // if true, payload may only contain RequiredFields[].Name
}

// Registry holds descriptors per (event_type, event_version).
type Registry struct {
	byKey map[key]*SchemaDescriptor
}

type key struct {
	eventType string
	version   uint32
}

func NewRegistry() *Registry {
	return &Registry{byKey: map[key]*SchemaDescriptor{}}
}

// Register adds a descriptor. Idempotent: re-registering the same key
// replaces (init-time wiring).
func (r *Registry) Register(d SchemaDescriptor) {
	dd := d
	r.byKey[key{d.EventType, d.EventVersion}] = &dd
}

// Knows returns true when a descriptor is registered for (type, version).
func (r *Registry) Knows(eventType string, eventVersion uint32) bool {
	_, ok := r.byKey[key{eventType, eventVersion}]
	return ok
}

// Validate runs the L2.I structural check.
//
// Errors:
//   - events.ErrUnknownEventSchema  if no descriptor is registered
//   - events.ErrSchemaViolation     if payload shape violates the descriptor
func (r *Registry) Validate(eventType string, eventVersion uint32, payload map[string]any) error {
	d, ok := r.byKey[key{eventType, eventVersion}]
	if !ok {
		return events.ErrUnknownEventSchema(eventType, eventVersion)
	}
	if payload == nil {
		return events.ErrSchemaViolation(eventType, eventVersion, "payload nil")
	}
	for _, f := range d.RequiredFields {
		v, present := payload[f.Name]
		if !present {
			return events.ErrSchemaViolation(eventType, eventVersion,
				fmt.Sprintf("missing required field %s", f.Name))
		}
		if !f.Ty.matches(v) {
			return events.ErrSchemaViolation(eventType, eventVersion,
				fmt.Sprintf("field %s expected %s got %T", f.Name, f.Ty, v))
		}
	}
	if d.StrictUnknown {
		known := map[string]struct{}{}
		for _, f := range d.RequiredFields {
			known[f.Name] = struct{}{}
		}
		for k := range payload {
			if _, ok := known[k]; !ok {
				return events.ErrSchemaViolation(eventType, eventVersion,
					fmt.Sprintf("unknown field %s (strict mode)", k))
			}
		}
	}
	return nil
}

// BuildSeedRegistry returns a registry pre-loaded with the cycle 8 seed
// event descriptors. Mirror of the test fixture in the Rust suite — services
// that need the seed-events validator can call this directly; production
// services build their own registry by reading _registry.yaml + per-event
// descriptors.
func BuildSeedRegistry() *Registry {
	r := NewRegistry()

	r.Register(SchemaDescriptor{
		EventType:    "reality.created",
		EventVersion: 1,
		RequiredFields: []RequiredField{
			{Name: "reality_id", Ty: FieldString},
			{Name: "owner_user_id", Ty: FieldString},
			{Name: "name", Ty: FieldString},
			{Name: "world_seed", Ty: FieldString},
			{Name: "locale_source", Ty: FieldString},
			{Name: "created_at", Ty: FieldString},
		},
	})

	r.Register(SchemaDescriptor{
		EventType:    "npc.said",
		EventVersion: 1,
		RequiredFields: []RequiredField{
			{Name: "npc_id", Ty: FieldString},
			{Name: "text", Ty: FieldString},
			{Name: "scene_id", Ty: FieldString},
			{Name: "said_at", Ty: FieldString},
		},
	})

	r.Register(SchemaDescriptor{
		EventType:    "npc.said",
		EventVersion: 2,
		RequiredFields: []RequiredField{
			{Name: "npc_id", Ty: FieldString},
			{Name: "text", Ty: FieldString},
			{Name: "scene_id", Ty: FieldString},
			{Name: "said_at", Ty: FieldString},
			{Name: "tone", Ty: FieldString},
		},
	})

	r.Register(SchemaDescriptor{
		EventType:    "world.tick",
		EventVersion: 1,
		RequiredFields: []RequiredField{
			{Name: "reality_id", Ty: FieldString},
			{Name: "tick_index", Ty: FieldNumber},
			{Name: "tick_at", Ty: FieldString},
		},
	})

	// ── L2.L xreality.* events (RAID cycle 10) ──────────────────────
	// Same validation surface as any other event_type; the cross-reality
	// fanout selection happens via Envelope.Metadata["cross_reality"]=true
	// at the publisher level (not here).
	r.Register(SchemaDescriptor{
		EventType:    "xreality.canon.promoted",
		EventVersion: 1,
		RequiredFields: []RequiredField{
			{Name: "source_reality_id", Ty: FieldString},
			{Name: "entry_id", Ty: FieldString},
			{Name: "entry_type", Ty: FieldString},
			{Name: "promoted_by", Ty: FieldString},
			{Name: "promoted_at", Ty: FieldString},
		},
	})

	r.Register(SchemaDescriptor{
		EventType:    "xreality.user.erased",
		EventVersion: 1,
		RequiredFields: []RequiredField{
			{Name: "user_id", Ty: FieldString},
			{Name: "erased_at", Ty: FieldString},
			{Name: "request_id", Ty: FieldString},
		},
	})

	return r
}
