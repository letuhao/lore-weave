// Package schema holds the per-event-type payload builders.
//
// Each builder produces the JSON payload that the corresponding Rust projection
// `apply_event` arm reads (crates/projections/*/src/lib.rs). The generator
// supplies valid references (region ids, session ids, …) from world-state; the
// builders are pure functions of their inputs.
//
// Spec is the contract: for every emittable event type it names the aggregate
// it mutates and the payload keys its projection arm reads. The schema tests
// assert each builder satisfies its Spec — the guard against drift if a
// projection arm changes the fields it reads (plan §4 R1).
//
// SCOPE (the currently-handled projecting surface). Verified against the
// cycle-13 projection arms: admin.canon.override.compensating and
// canon.change.recorded are NOT yet handled (TODO arms → no projection), so the
// generator does not emit them.
package schema

// Payload is one event's JSON payload.
type Payload = map[string]any

// Spec describes one emittable event type.
type Spec struct {
	EventType     string
	AggregateType string
	RequiredKeys  []string // payload keys the projection arm reads
}

// Specs is the authoritative list of event types the generator emits, with the
// payload keys each projection arm requires.
var Specs = []Spec{
	{"npc.created", "npc", []string{"glossary_entity_id", "spawn_region_id", "initial_mood"}},
	{"npc.said", "npc", []string{}}, // npc_projection bumps version; session_id rides in metadata
	{"session.started", "session", []string{"npc_id", "session_id", "aggregate_id"}},
	{"session.ended", "session", []string{"npc_id", "session_id"}},
	{"session.participant_joined", "session", []string{"session_id", "participant_type", "participant_id"}},
	{"session.participant_left", "session", []string{"session_id", "participant_type", "participant_id"}},
	{"pc.spawned", "pc", []string{"user_id", "name", "spawn_region_id"}},
	{"pc.moved", "pc", []string{"to_region_id"}},
	{"pc.item_acquired", "pc", []string{"item_code", "quantity"}},
	{"pc.relationship_changed", "pc", []string{"other_entity_type", "other_entity_id", "score", "labels"}},
	{"region.created", "region", []string{"code", "display_name"}},
	{"region.ambient_changed", "region", []string{"ambient_state"}},
	{"world.kv_set", "world", []string{"key", "value"}},
	{"world.kv_unset", "world", []string{"key"}},
	{"canon.entry.created", "canon", []string{"canon_entry_id", "book_id", "attribute_path", "value", "canon_layer"}},
	{"canon.entry.updated", "canon", []string{"canon_entry_id", "new_value", "canon_layer"}},
	{"canon.entry.promoted", "canon", []string{"canon_entry_id", "to_layer"}},
	{"canon.entry.decanonized", "canon", []string{"canon_entry_id"}},
}

// --- npc ---

func NpcCreated(glossaryEntityID, spawnRegionID, mood string) Payload {
	return Payload{
		"glossary_entity_id": glossaryEntityID,
		"spawn_region_id":    spawnRegionID,
		"initial_mood":       mood,
		"core_beliefs":       Payload{},
	}
}

// NpcSaid carries the utterance text for realism; the projection reads nothing
// from the payload (it bumps the version and fans out via metadata.session_id,
// which the generator sets on the envelope).
func NpcSaid(text string) Payload { return Payload{"text": text} }

// --- session ---

func SessionStarted(npcID, sessionID string) Payload {
	return Payload{"npc_id": npcID, "session_id": sessionID, "aggregate_id": sessionID}
}

func SessionEnded(npcID, sessionID string) Payload {
	return Payload{"npc_id": npcID, "session_id": sessionID}
}

func SessionParticipantJoined(sessionID, participantType, participantID string) Payload {
	return Payload{"session_id": sessionID, "participant_type": participantType, "participant_id": participantID}
}

func SessionParticipantLeft(sessionID, participantType, participantID string) Payload {
	return Payload{"session_id": sessionID, "participant_type": participantType, "participant_id": participantID}
}

// --- pc ---

func PcSpawned(userID, name, spawnRegionID string) Payload {
	return Payload{"user_id": userID, "name": name, "spawn_region_id": spawnRegionID, "stats": Payload{}}
}

func PcMoved(toRegionID string) Payload { return Payload{"to_region_id": toRegionID} }

func PcItemAcquired(itemCode string, quantity int) Payload {
	return Payload{"item_code": itemCode, "quantity": quantity, "metadata": Payload{}}
}

func PcRelationshipChanged(otherType, otherID string, score int, labels []string) Payload {
	return Payload{"other_entity_type": otherType, "other_entity_id": otherID, "score": score, "labels": labels}
}

// --- region ---

func RegionCreated(code, displayName string) Payload {
	return Payload{
		"code": code, "display_name": displayName,
		"description": "", "parent_region_id": nil,
		"exits": []any{}, "ambient_state": Payload{},
	}
}

func RegionAmbientChanged(ambient Payload) Payload { return Payload{"ambient_state": ambient} }

// --- world ---

func WorldKvSet(key string, value any) Payload { return Payload{"key": key, "value": value} }
func WorldKvUnset(key string) Payload          { return Payload{"key": key} }

// --- canon ---

func CanonEntryCreated(canonEntryID, bookID, attributePath string, value any, canonLayer string) Payload {
	return Payload{
		"canon_entry_id": canonEntryID, "book_id": bookID, "attribute_path": attributePath,
		"value": value, "canon_layer": canonLayer, "lock_level": "soft",
	}
}

func CanonEntryUpdated(canonEntryID string, newValue any, canonLayer string) Payload {
	return Payload{"canon_entry_id": canonEntryID, "new_value": newValue, "canon_layer": canonLayer}
}

func CanonEntryPromoted(canonEntryID, toLayer string) Payload {
	return Payload{"canon_entry_id": canonEntryID, "to_layer": toLayer}
}

func CanonEntryDecanonized(canonEntryID string) Payload {
	return Payload{"canon_entry_id": canonEntryID}
}
