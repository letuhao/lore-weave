package schema

import "testing"

// samples builds one payload per emittable event type, used to assert each
// builder satisfies its Spec.
func samples() map[string]Payload {
	return map[string]Payload{
		"npc.created":                NpcCreated("g-1", "region-1", "calm"),
		"npc.said":                   NpcSaid("hello"),
		"session.started":            SessionStarted("npc-1", "sess-1"),
		"session.ended":              SessionEnded("npc-1", "sess-1"),
		"session.participant_joined": SessionParticipantJoined("sess-1", "pc", "pc-1"),
		"session.participant_left":   SessionParticipantLeft("sess-1", "pc", "pc-1"),
		"pc.spawned":                 PcSpawned("user-1", "Alice", "region-1"),
		"pc.moved":                   PcMoved("region-2"),
		"pc.item_acquired":           PcItemAcquired("sword_iron", 1),
		"pc.relationship_changed":    PcRelationshipChanged("npc", "npc-7", 42, []string{"friendly"}),
		"npc.relationship_changed":   NpcRelationshipChanged("pc-1", 5, 1, "sess-1", []string{"acquaintance"}),
		"npc.memory_embedded":        NpcMemoryEmbedded("npc-1", "sess-1", "mem-1", []float64{0.1}),
		"region.created":             RegionCreated("r1", "Forest"),
		"region.ambient_changed":     RegionAmbientChanged(Payload{"weather": "rain"}),
		"world.kv_set":               WorldKvSet("quest.flag", true),
		"world.kv_unset":             WorldKvUnset("quest.flag"),
		"canon.entry.created":        CanonEntryCreated("c-1", "book-1", "characters/alice/race", "elf", "L2_seeded"),
		"canon.entry.updated":        CanonEntryUpdated("c-1", "half-elf", "L2_seeded"),
		"canon.entry.promoted":       CanonEntryPromoted("c-1", "L1_axiom"),
		"canon.entry.decanonized":    CanonEntryDecanonized("c-1"),
	}
}

// TestEveryBuilderSatisfiesItsSpec proves builder output ⊇ Spec.RequiredKeys.
// It does NOT prove Spec.RequiredKeys ⊇ the real projection arm's reads —
// RequiredKeys is hand-derived from crates/projections/*. A field an arm starts
// reading that isn't added here passes this test but would be missing at
// runtime; the live-smoke (integrity-checker) + a future C2 fixture are the real
// backstops for that drift (plan R1).
func TestEveryBuilderSatisfiesItsSpec(t *testing.T) {
	s := samples()
	for _, spec := range Specs {
		p, ok := s[spec.EventType]
		if !ok {
			t.Errorf("no sample payload for spec %q", spec.EventType)
			continue
		}
		for _, key := range spec.RequiredKeys {
			if _, present := p[key]; !present {
				t.Errorf("%s: payload missing required key %q (its projection arm reads it)", spec.EventType, key)
			}
		}
	}
}

func TestEverySampleHasASpec(t *testing.T) {
	specByType := map[string]bool{}
	for _, spec := range Specs {
		specByType[spec.EventType] = true
	}
	for et := range samples() {
		if !specByType[et] {
			t.Errorf("sample %q has no Spec entry", et)
		}
	}
}

func TestSpecsAreUniqueAndWellFormed(t *testing.T) {
	seen := map[string]bool{}
	known := map[string]bool{"npc": true, "pc": true, "region": true, "world": true, "session": true, "canon": true}
	for _, spec := range Specs {
		if seen[spec.EventType] {
			t.Errorf("duplicate Spec for %q", spec.EventType)
		}
		seen[spec.EventType] = true
		if !known[spec.AggregateType] {
			t.Errorf("%s: unknown aggregate_type %q", spec.EventType, spec.AggregateType)
		}
	}
}
